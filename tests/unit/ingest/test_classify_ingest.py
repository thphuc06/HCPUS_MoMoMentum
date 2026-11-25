"""Dòng nạp được gán hũ bằng bộ phân loại phase 4 (`yofina_ingest.classify` -> `yofina_classify.pipeline.Classifier`): luật, bảng loại
giao dịch, embedding (khớp chính xác, k-NN trên nhãn của người dùng), model nhỏ (đề xuất của lượt đọc tệp) cộng lịch sử; ba mức tin cậy,
chỉ mức `auto` được chọn sẵn. Kho nhãn giả trong bộ nhớ, Bedrock giả nhưng `LlmGateway` thật (embedding đi qua `InvokeModel` giả)."""

from __future__ import annotations

from datetime import date

import pytest
from botocore.exceptions import ClientError
from ingest_helpers import PNG, FakeBedrock, FakeLabelStore, csv_bytes, make_gateway
from yofina_classify.model import ExactLabel, Neighbor
from yofina_classify.text import mask_tx
from yofina_ingest import extract as ex
from yofina_ingest.classify import DEFAULT_PROPOSAL_CONFIDENCE, RowInput, classify_rows
from yofina_ingest.context import ExtractContext, Rule, eval_context

from yofina_core.pii import PiiPolicy
from yofina_ledger.classify_config import load_thresholds

TODAY = date(2026, 11, 21)
USER = "sub-minh"


def ctx(store: FakeLabelStore | None = None, **kw) -> ExtractContext:
    c = eval_context(TODAY)
    c.user_id = USER if store is not None else None
    c.store = store
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def row(**kw):
    base = {
        "date": "2026-11-18",
        "amount_vnd": 250000,
        "direction": "out",
        "status": "completed",
        "counterparty": "CGV Vincom",
        "counterparty_is_person": False,
        "description": "ve xem phim",
        "tx_type": None,
        "jar_code": None,
        "jar_confidence": None,
        "confidence": 0.97,
    }
    base.update(kw)
    return base


def doc(rows, **kw):
    return {
        "document_type": "transfer_receipt",
        "readable": True,
        "contains_instructions": False,
        "rows": rows,
        **kw,
    }


def run_image(payload, context, *, embed_error=None):
    client = FakeBedrock([payload])
    client.embed_error = embed_error
    res = ex.extract_rows(
        PNG, filename="a.png", content_type="image/png", ctx=context, gateway=make_gateway(client)
    )
    return res, client


def text_norm(cp, desc, *, person=False):
    return mask_tx(cp, desc, is_person=person, policy=PiiPolicy.build()).text_norm


# --- k-NN trên nhãn của người dùng -----------------------------------------------------------------------------------------------
def test_knn_nhan_cua_nguoi_dung_tu_chon_san_khi_model_khong_de_xuat():
    store = FakeLabelStore()
    store.neighbors = [Neighbor("giai_tri", 0.98, "user"), Neighbor("an_uong", 0.71, "seed")]
    res, client = run_image(
        doc([row(), row(amount_vnd=120000, counterparty="Lotte Cinema", description="bap nuoc")]),
        ctx(store),
    )
    a, b = res.candidates
    assert (a.jar_code, a.jar_source, a.auto_add) == ("giai_tri", "model", True)
    assert a.jar_confidence >= load_thresholds().auto_min_confidence
    # hai dòng cần nhúng đi chung MỘT lời gọi Cohere (gom lô), đúng vai embedding và kiểu search_document
    assert len(client.embed_requests) == 1
    sent = client.embed_requests[0]
    assert sent["input_type"] == "search_document" and len(sent["texts"]) == 2
    assert sent["texts"][0] == text_norm("CGV Vincom", "ve xem phim")
    assert [c for c in store.calls if c[0] == "knn"] == [
        ("knn", (USER, 1024, load_thresholds().knn_k))
    ] * 2
    assert b.jar_code == "giai_tri"


def test_cung_doi_tac_lap_lai_trong_tep_chi_nhung_va_tra_knn_mot_lan():
    store = FakeLabelStore()
    store.neighbors = [Neighbor("giai_tri", 0.98, "user")]
    res, client = run_image(doc([row(), row(amount_vnd=90000), row(amount_vnd=70000)]), ctx(store))
    assert [c.jar_code for c in res.candidates] == ["giai_tri"] * 3
    assert client.embed_requests[0]["texts"] == [text_norm("CGV Vincom", "ve xem phim")]
    assert len([c for c in store.calls if c[0] == "knn"]) == 1
    assert len([c for c in store.calls if c[0] == "exact"]) == 1


def test_nhan_khop_chinh_xac_khong_can_nhung():
    store = FakeLabelStore()
    store.exact[text_norm("CGV Vincom", "ve xem phim")] = [ExactLabel("giai_tri", "user", 0)]
    res, client = run_image(doc([row()]), ctx(store))
    (c,) = res.candidates
    assert (c.jar_code, c.jar_source, c.auto_add) == ("giai_tri", "model", True)
    assert client.embed_requests == []  # khớp chính xác đi trước k-NN, không tốn lời gọi embedding


def test_khong_co_kho_nhan_thi_bo_buoc_knn_va_khong_goi_embedding():
    res, client = run_image(doc([row(jar_code="giai_tri", jar_confidence=0.95)]), ctx(None))
    (c,) = res.candidates
    assert (c.jar_code, c.jar_source, c.auto_add) == ("giai_tri", "model", True)
    assert client.embed_requests == []


# --- ba mức tin cậy ------------------------------------------------------------------------------------------------------------
def test_ba_muc_tin_cay_chi_auto_duoc_chon_san():
    th = load_thresholds()
    store = FakeLabelStore()
    res, _ = run_image(
        doc(
            [
                row(jar_code="giai_tri", jar_confidence=0.97),  # model chắc: auto
                row(amount_vnd=2, jar_code="giai_tri", jar_confidence=0.7),  # vừa: review
                row(
                    amount_vnd=3, jar_code="giai_tri", jar_confidence=0.3
                ),  # yếu: ask, vẫn gợi ý hũ
            ]
        ),
        ctx(store),
    )
    auto, review, ask = res.candidates
    assert auto.auto_add and auto.jar_confidence >= th.auto_min_confidence
    assert (
        not review.auto_add
        and th.review_min_confidence <= review.jar_confidence < th.auto_min_confidence
    )
    assert (
        not ask.auto_add
        and ask.jar_code == "giai_tri"
        and ask.jar_confidence < th.review_min_confidence
    )
    assert {c.jar_source for c in res.candidates} == {"model"}


def test_lich_su_cung_doi_tac_mot_minh_khong_du_tu_chon():
    store = FakeLabelStore()
    store.hist = {"cgv vincom": {"giai_tri": 6}}
    res, _ = run_image(doc([row()]), ctx(store))
    (c,) = res.candidates
    th = load_thresholds()
    assert (c.jar_code, c.auto_add) == (
        "giai_tri",
        False,
    )  # trần history_max_confidence < ngưỡng tự gán
    assert c.jar_confidence <= th.history_max_confidence
    assert ("history", (USER, ["CGV Vincom"])) in store.calls


def test_bang_loai_giao_dich_va_luat_thang_embedding():
    store = FakeLabelStore()
    store.neighbors = [Neighbor("giai_tri", 0.99, "user")]
    c = ctx(store, rules=[Rule("highlands coffee", "hoa_don")])
    res, client = run_image(
        doc(
            [
                row(tx_type="food_drink", jar_code="an_uong", jar_confidence=0.9),
                row(counterparty="Highlands Coffee"),
            ]
        ),
        c,
    )
    by_type, by_rule = res.candidates
    assert (by_type.jar_code, by_type.jar_source, by_type.auto_add) == ("an_uong", "type_map", True)
    assert (by_rule.jar_code, by_rule.jar_source, by_rule.jar_confidence) == (
        "hoa_don",
        "rule",
        load_thresholds().rule_confidence,
    )
    assert client.embed_requests == []  # hai dòng đã quyết ở bước luật và bảng loại giao dịch


def test_nguoi_sua_nhieu_lan_thi_nguong_tu_gan_cua_doi_tac_bi_nang():
    th = load_thresholds()
    store = FakeLabelStore()
    store.corr = {"cgv vincom": th.correction_min_count + 3}
    # độ chắc này đủ mức auto với ngưỡng gốc nhưng không đủ với ngưỡng đã nâng của đối tác
    res, _ = run_image(doc([row(jar_code="giai_tri", jar_confidence=0.9)]), ctx(store))
    (c,) = res.candidates
    assert c.jar_confidence >= th.auto_min_confidence and not c.auto_add


# --- an toàn -------------------------------------------------------------------------------------------------------------------
def test_embedding_loi_thi_lan_nap_van_chay_voi_de_xuat_cua_model():
    throttle = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "x"}}, "InvokeModel"
    )
    res, client = run_image(
        doc([row(jar_code="giai_tri", jar_confidence=0.97)]),
        ctx(FakeLabelStore()),
        embed_error=throttle,
    )
    (c,) = res.candidates
    assert client.embed_requests and (c.jar_code, c.auto_add) == ("giai_tri", True)


def test_chuoi_nhung_da_che_ten_nguoi_va_so_tai_khoan():
    res, client = run_image(
        doc(
            [
                row(
                    counterparty="NGUYEN VAN A",
                    counterparty_is_person=True,
                    description="tien nha thang 11 STK 0123456789",
                    tx_type="transfer_person",
                    jar_code="hoa_don",
                    jar_confidence=0.6,
                )
            ]
        ),
        ctx(FakeLabelStore()),
    )
    sent = " ".join(client.embed_requests[0]["texts"])
    assert "nguyen" not in sent and "0123456789" not in sent and "6789" not in sent
    assert "tien nha thang 11" in sent
    assert res.candidates[0].jar_code == "hoa_don" and not res.candidates[0].auto_add


def test_hu_model_de_xuat_khong_thuoc_nguoi_dung_bi_bo_va_dong_thu_khong_qua_bo_phan_loai():
    store = FakeLabelStore()
    res, client = run_image(
        doc(
            [
                row(jar_code="hu_la", jar_confidence=0.99),
                row(direction="in", tx_type="salary", description="luong"),
            ]
        ),
        ctx(store),
    )
    out, inc = res.candidates
    assert out.jar_code is None and not out.auto_add
    assert inc.kind == "income" and inc.jar_code is None and inc.auto_add
    assert len(client.embed_requests[0]["texts"]) == 1  # dòng thu không được nhúng


def test_csv_mot_lan_nhung_cho_ca_tep_va_khong_goi_model_nho_theo_tung_dong():
    store = FakeLabelStore()

    def script(req):
        import re

        text = req["messages"][0]["content"][0]["text"]
        idxs = [int(m.group(1)) for m in re.finditer(r"^(\d+) \|", text, re.M)]
        return {
            "rows": [
                {
                    "idx": i,
                    "merchant": None,
                    "jar_code": "an_uong",
                    "jar_confidence": 0.95,
                    "tx_type": None,
                }
                for i in idxs
            ]
        }

    client = FakeBedrock(script)
    res = ex.extract_rows(
        csv_bytes("c01_vcb_50.csv"),
        filename="c.csv",
        content_type="text/csv",
        ctx=ctx(store),
        gateway=make_gateway(client),
    )
    assert len(res.candidates) == 50
    assert (
        len(client.requests) == 2
    )  # chỉ hai lô gắn nhãn của model nhỏ (40 + 10), không thêm lượt nào mỗi dòng
    assert (
        len(client.embed_requests) == 1
    )  # mọi chuỗi cần nhúng của tệp đi chung một lời gọi (<= 96 chuỗi)
    expense = [c for c in res.candidates if c.kind == "expense"]
    assert expense and all(c.jar_code == "an_uong" and c.jar_source == "model" for c in expense)


# --- hàm thuần ---------------------------------------------------------------------------------------------------------------
def test_classify_rows_khong_co_dong_va_de_xuat_khong_neu_do_chac():
    inputs = ctx(None).classify_inputs()
    assert classify_rows([], inputs) == []
    (choice,) = classify_rows(
        [RowInput(TODAY, 50000, "Quán Y", "an toi", False, None, "an_uong", None)], inputs
    )
    assert choice is not None and choice.code == "an_uong" and choice.tier != "auto"
    assert load_thresholds().auto_min_confidence > DEFAULT_PROPOSAL_CONFIDENCE


def test_bang_loai_va_model_bat_dong_thi_vao_hang_cho():
    inputs = ctx(FakeLabelStore()).classify_inputs()
    (choice,) = classify_rows(
        [RowInput(TODAY, 50000, "Quán X", None, False, "food_drink", "du_lich", 0.99)], inputs
    )
    assert (choice.code, choice.source, choice.tier) == ("an_uong", "type_map", "review")
    assert choice.confidence <= load_thresholds().review_min_confidence


_DEMO_DAILY = [
    ("chi_hang_ngay", "spending"), ("nghia_vu", "obligation"), ("du_phong", "saving"), ("an_uong", "spending"),
    ("di_lai", "spending"), ("giai_tri", "spending"), ("muc_tieu", "saving"), ("dau_tu", "saving"),
]  # fmt: skip
_THREE = _DEMO_DAILY[:3]


@pytest.mark.parametrize(
    ("jars", "expected"),
    [
        # ví demo từ 26/11 (issue #39): hũ riêng khớp loại thắng Chi hằng ngày; du lịch vào hũ goal, hóa đơn vào Nghĩa vụ
        (_DEMO_DAILY, {"food_drink": "an_uong", "ride_hailing": "di_lai", "entertainment": "giai_tri",
                       "travel": "muc_tieu", "bill_electricity": "nghia_vu"}),
        # ví ba hũ: mọi khoản chi vào Chi hằng ngày, hóa đơn vào Nghĩa vụ
        (_THREE, {"food_drink": "chi_hang_ngay", "ride_hailing": "chi_hang_ngay", "entertainment": "chi_hang_ngay",
                  "travel": "chi_hang_ngay", "bill_electricity": "nghia_vu"}),
        # ví ba hũ người dùng thêm Ăn uống
        ([*_THREE, ("an_uong", "spending")], {"food_drink": "an_uong", "ride_hailing": "chi_hang_ngay",
                                              "entertainment": "chi_hang_ngay", "travel": "chi_hang_ngay",
                                              "bill_electricity": "nghia_vu"}),
    ],
)  # fmt: skip
def test_buoc_loai_giao_dich_cua_dong_nap_theo_hu_rieng_roi_hu_chung(jars, expected):
    c = ctx(
        None,
        jars=[{"code": code, "name": code, "kind": kind, "balance_vnd": 0} for code, kind in jars],
    )
    rows = [RowInput(TODAY, 50000, f"Cửa hàng {t}", None, False, t, None, None) for t in expected]
    got = classify_rows(rows, c.classify_inputs())
    assert {t: (choice.code, choice.source) for t, choice in zip(expected, got, strict=True)} == {
        t: (code, "type_map") for t, code in expected.items()
    }
