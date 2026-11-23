"""Phân hũ tự động (phase 4 luồng B) trên PostgreSQL thật cục bộ: SQL thật (migration 0052: pgvector, RLS), `LedgerService` thật,
`ClassifyService` thật nối `PgLabelIndex` thật. Chỉ embedding và model nhỏ là cổng giả (không có AWS trong test).

Chạy cùng bộ local_pg (lệnh ở docstring của conftest.py): `pytest tests/local_pg/test_classify_flow.py`.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import pytest
from conftest import REPO

for _p in ("pipelines/classify", "tests/unit"):
    if str(REPO / _p) not in sys.path:
        sys.path.insert(0, str(REPO / _p))

from jsonschema import Draft202012Validator  # noqa: E402
from ledger_fakes import gateway_context, http_event  # noqa: E402
from yofina_classify.consumer import process_records  # noqa: E402
from yofina_classify.model import Verdict  # noqa: E402
from yofina_classify.pipeline import Classifier  # noqa: E402
from yofina_classify.repo import ClassifyRepo, PgLabelIndex  # noqa: E402
from yofina_classify.service import ClassifyService  # noqa: E402

from yofina_core.blocks import parse_block  # noqa: E402
from yofina_core.wallet import EMBEDDING_DIMENSIONS  # noqa: E402
from yofina_ledger.classify_config import load_thresholds  # noqa: E402
from yofina_ledger.gateway_api import handle_gateway  # noqa: E402
from yofina_ledger.rest_api import handle_http  # noqa: E402

MINH = "sub-minh"
VEC = [1.0] * EMBEDDING_DIMENSIONS
TH = load_thresholds({})


def vec_text(vec):
    return "[" + ",".join(f"{x:g}" for x in vec) + "]"


class FakeEmbedder:
    """Cổng embedding giả (chỉ test): mọi chuỗi cùng một vector, hoặc vector theo từ điển."""

    def __init__(self, orthogonal: bool = False) -> None:
        self.orthogonal, self.calls, self.seen = orthogonal, [], {}

    def embed(self, text_norm):
        self.calls.append(text_norm)
        if not self.orthogonal:
            return "cohere.embed-multilingual-v3", VEC
        if text_norm not in self.seen:  # mỗi chuỗi một trục riêng: hai chuỗi khác nhau có cosine 0
            vec = [0.0] * EMBEDDING_DIMENSIONS
            vec[len(self.seen)] = 1.0
            self.seen[text_norm] = vec
        return "cohere.embed-multilingual-v3", self.seen[text_norm]


class FakeJudge:
    def __init__(self, verdict: Verdict | None = None) -> None:
        self.verdict, self.prompts = verdict or Verdict(None, 0.0), []

    def __call__(self, prompt, jars):
        self.prompts.append(prompt)
        return self.verdict


@pytest.fixture(scope="session")
def schema():
    import importlib.util

    spec = importlib.util.spec_from_file_location("unit_conftest", REPO / "tests/unit/conftest.py")
    uc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(uc)
    reg = uc.build_registry()

    def check(ref: str, instance):
        v = Draft202012Validator({"$ref": f"{uc.BASE}/{ref}"}, registry=reg)
        errors = [f"{list(e.path)}: {e.message}" for e in v.iter_errors(instance)]
        assert not errors, errors

    return check


def make(env, *, th=TH, emb=None, judge=None):
    from zoneinfo import ZoneInfo

    emb, judge = emb or FakeEmbedder(), judge or FakeJudge()
    repo = ClassifyRepo(env.db, ZoneInfo("Asia/Ho_Chi_Minh"))
    clf = Classifier(th, PgLabelIndex(env.db), emb, judge)
    return ClassifyService(repo, clf, env.events, clock=env.clock), emb, judge


def record(env, **p) -> str:
    """Ghi một khoản chi vào Chưa phân loại (đường ghi thật) và trả id giao dịch lấy từ sự kiện `needs_classification`."""
    before = len(env.events.sent)
    env.act(
        MINH,
        "record_transaction",
        {"kind": "expense", "jar": "chua_phan_loai", **p},
    )
    evs = [e for e in env.events.sent[before:] if e.detail_type == "transaction.recorded"]
    assert evs and evs[0].detail.get("needs_classification") is True
    return evs[0].detail["transaction_id"]


def row(env, tx_id: str) -> dict[str, Any]:
    with env.master() as c:
        cur = c.execute(
            "select jar_code, classified_by, classification_confidence, needs_review, suggested_jars from transactions where id = %s",
            (tx_id,),
        )
        v = cur.fetchone()
    return dict(zip(("jar", "by", "conf", "needs_review", "suggested"), v, strict=True))


def jar_bal(env) -> dict[str, int]:
    ov = env.svc.overview_response(MINH)
    return {j["code"]: j["balance_vnd"] for j in [*ov["jars"], *ov["system_jars"]]}


def add_label(env, text_norm: str, jar: str, vec=VEC, source: str = "seed") -> None:
    with env.master() as c:
        c.execute(
            "insert into tx_embeddings_labeled (user_id, text_norm, jar_code, source, model, embedding) "
            "values (%s, %s, %s, %s, 'cohere.embed-multilingual-v3', %s::vector)",
            (MINH, text_norm, jar, source, vec_text(vec)),
        )


def rest(env, method, path, body=None, query=None):
    out = handle_http(http_event(method, path, sub=MINH, body=body, query=query), env.svc)
    return out["statusCode"], json.loads(out["body"])


# --- bước 0 và bảo toàn số dư ------------------------------------------------------------------------------
def test_bang_tra_tu_gan_doi_so_du_bang_duong_ghi_san_co_va_phat_su_kien(env):
    env.reset(MINH)
    svc, emb, judge = make(env)
    before = jar_bal(env)
    tx = record(env, amount_vnd=50_000, tx_type="food_drink", counterparty="Quán Cơm Hai")
    out = svc.run(MINH, tx, trace_id="a" * 32)
    assert (out.status, out.jar, out.stage, out.tier) == ("assigned", "an_uong", "type_map", "auto")
    r = row(env, tx)
    assert (r["jar"], r["by"], r["needs_review"], r["suggested"]) == (
        "an_uong",
        "type_map",
        False,
        None,
    )
    after = jar_bal(env)
    assert after["an_uong"] == before["an_uong"] - 50_000
    assert (
        after["chua_phan_loai"] == before["chua_phan_loai"]
    )  # khoản chi ghi vào Chưa phân loại (-50k) rồi được kéo ra (+50k)
    assert emb.calls == [] and judge.prompts == []
    sent = [e for e in env.events.sent if e.detail.get("tx_type") == "jar_assign"]
    assert sent and sent[-1].detail["jar_codes"] == ["chua_phan_loai", "an_uong"]
    assert "needs_classification" not in sent[-1].detail  # không vòng lặp phân loại
    with env.master() as c:
        aud = c.execute(
            "select tool, params from audit_events where user_id = %s and event_type = 'auto_classify'",
            (MINH,),
        ).fetchall()
    assert len(aud) == 1 and aud[0][0] == "classify"
    assert "Quán" not in json.dumps(aud[0][1], ensure_ascii=False)  # audit không có tên đối tác


def test_nguoi_dung_da_tu_chon_hu_thi_bo_qua_va_chay_lai_khong_lam_hai_lan(env):
    env.reset(MINH)
    svc, _, _ = make(env)
    env.act(MINH, "record_transaction", {"kind": "expense", "amount_vnd": 40_000, "jar": "an_uong"})
    with env.master() as c:
        tx = str(
            c.execute(
                "select id from transactions where user_id = %s order by created_at desc limit 1",
                (MINH,),
            ).fetchone()[0]
        )
    assert svc.run(MINH, tx).reason == "already_has_jar"
    tx2 = record(env, amount_vnd=50_000, tx_type="food_drink")
    assert svc.run(MINH, tx2).status == "assigned"
    bal = jar_bal(env)
    assert svc.run(MINH, tx2).reason == "already_has_jar"  # lần giao lại: không cộng trừ lần hai
    assert jar_bal(env) == bal


def test_hu_dich_khong_du_so_du_thi_o_lai_hoi_gop(env):
    env.reset(MINH)
    svc, *_ = make(env)
    tx = record(env, amount_vnd=400_000, tx_type="food_drink")  # an_uong chỉ có 380.000
    out = svc.run(MINH, tx)
    assert (out.status, out.tier) == ("asked", "ask")
    r = row(env, tx)
    assert r["jar"] == "chua_phan_loai" and r["suggested"] == ["an_uong"]


# --- embedding: khớp chính xác, k-NN, ghi tx_embeddings -------------------------------------------------------
def test_knn_pgvector_that_gan_hu_va_ghi_embedding_roi_khop_chinh_xac_thi_khong_goi_lai(env):
    env.reset(MINH)
    add_label(
        env, "quan ca phe khac", "an_uong"
    )  # chuỗi khác: không khớp chính xác, chỉ gần theo vector
    svc, emb, judge = make(env)
    tx = record(env, amount_vnd=45_000, tx_type="qr_other", counterparty="Cà phê Nhà Riêng")
    out = svc.run(MINH, tx)
    # vector trùng nhãn: cùng cosine 1 -> k-NN chắc, dừng ở bước embedding (không gọi model nhỏ)
    assert (out.status, out.jar, out.stage, out.classified_by) == (
        "assigned",
        "an_uong",
        "embedding",
        "embedding",
    )
    assert judge.prompts == [] and len(emb.calls) == 1 and emb.calls[0] == "ca phe nha rieng"
    with env.master() as c:
        n = c.execute(
            "select count(*), min(text_norm) from tx_embeddings where transaction_id = %s", (tx,)
        ).fetchone()
    assert n == (1, "ca phe nha rieng")
    add_label(env, "ca phe nha rieng", "an_uong", source="user")  # người dùng đã xác nhận chuỗi này
    tx2 = record(env, amount_vnd=46_000, tx_type="qr_other", counterparty="CÀ PHÊ NHÀ RIÊNG")
    out2 = svc.run(MINH, tx2)
    assert (
        out2.jar == "an_uong" and len(emb.calls) == 1
    )  # khớp chuỗi chính xác sau chuẩn hóa: không nhúng lại


def test_nhan_cua_nguoi_dung_khac_khong_bi_thay_rls(env):
    env.reset(MINH)
    env.reset("sub-lan", "lan")
    with env.master() as c:
        c.execute(
            "insert into tx_embeddings_labeled (user_id, text_norm, jar_code, source, model, embedding) "
            "values ('sub-lan', 'cua hang bi mat', 'giai_tri', 'user', 'm', %s::vector)",
            (vec_text(VEC),),
        )
    idx = PgLabelIndex(env.db)
    assert idx.find_exact(MINH, "cua hang bi mat") == []
    assert idx.knn(MINH, VEC, 5) == []
    assert [x.jar_code for x in idx.knn("sub-lan", VEC, 5)] == ["giai_tri"]


# --- ba mức, hỏi gộp, REST ---------------------------------------------------------------------------------------
def test_muc_ask_giu_o_chua_phan_loai_mo_cau_hoi_gop_va_rest_tra_khoi_dung_hop_dong(env, schema):
    env.reset(MINH)
    svc, *_ = make(env, judge=FakeJudge(Verdict(None, 0.0)))
    tx = record(env, amount_vnd=70_000, tx_type="qr_other", counterparty="Quán Không Tên")
    out = svc.run(MINH, tx)
    assert out.status == "asked"
    with env.master() as c:
        ask = c.execute(
            "select status, item_count, pending_total_vnd from review_asks where user_id = %s",
            (MINH,),
        ).fetchall()
    assert ask == [("open", 3, 250_000)]  # hai khoản seed (180.000) cộng khoản này
    status, body = rest(env, "GET", "/review", query={"mode": "daily_ask"})
    assert status == 200
    schema("blocks/review_list.schema.json", body)
    block = parse_block(body)
    d = block.data
    assert (d.mode, d.count, d.pending_total_vnd) == ("daily_ask", 3, 250_000)
    assert d.ask is not None and d.ask.status == "open" and all(i.tier == "ask" for i in d.items)
    assert d.headline == "Hôm nay mình chưa xếp được hũ cho 3 giao dịch, tổng 250.000 ₫."
    assert {j.code for j in d.jars} >= {"an_uong", "di_lai"} and all(
        j.code not in ("chua_phan_loai", "tien_vao_khac") for j in d.jars
    )
    new = next(i for i in d.items if i.transaction_id == tx)
    assert (
        new.counterparty == "Quán Không Tên"
        and new.can_remember
        and new.current_jar.code == "chua_phan_loai"
    )
    # gợi ý do code dựng, lý do ngắn
    assert all(len(s.reason) <= 80 for i in d.items for s in i.suggestions)


def test_skip_cau_hoi_gop_idempotent_va_ngay_khong_co_cau_hoi_thi_400(env):
    env.reset(MINH)
    svc, *_ = make(env, judge=FakeJudge(Verdict(None, 0.0)))
    svc.run(MINH, record(env, amount_vnd=70_000, tx_type="qr_other", counterparty="Quán Không Tên"))
    ask_date = "2026-11-21"
    s1 = rest(env, "POST", "/review/daily-ask/skip", {"ask_date": ask_date})
    assert s1 == (200, {"ask_date": ask_date, "status": "skipped"})
    assert rest(env, "POST", "/review/daily-ask/skip", {"ask_date": ask_date}) == s1  # idempotent
    _, body = rest(env, "GET", "/review", query={"mode": "daily_ask"})
    assert (
        body["data"]["ask"]["status"] == "skipped" and body["data"]["count"] == 3
    )  # vẫn ở Chưa phân loại
    assert rest(env, "POST", "/review/daily-ask/skip", {"ask_date": "2026-01-01"})[0] == 400
    assert rest(env, "POST", "/review/daily-ask/skip", {"ask_date": "khong-phai-ngay"})[0] == 400
    assert rest(env, "GET", "/review", query={"mode": "linh_tinh"})[0] == 400
    # khoản ask mới cùng ngày KHÔNG mở lại câu hỏi đã để sau (hỏi một lần mỗi ngày)
    svc.run(MINH, record(env, amount_vnd=30_000, tx_type="qr_other", counterparty="Tiệm Lạ"))
    assert (
        rest(env, "GET", "/review", query={"mode": "daily_ask"})[1]["data"]["ask"]["status"]
        == "skipped"
    )


def test_skip_hom_nay_chua_co_dong_review_asks_thi_tao_dong_skipped(env):
    """Sau đặt lại chỉ có khoản seed ở Chưa phân loại, chưa qua pipeline: GET báo `open`, skip tạo dòng `skipped` (không 400)."""
    env.reset(MINH)
    ask_date = "2026-11-21"  # ngày mô phỏng của đồng hồ cố định (offset -19)
    _, body = rest(env, "GET", "/review", query={"mode": "daily_ask"})
    assert body["data"]["ask"] == {"ask_date": ask_date, "status": "open"}
    s1 = rest(env, "POST", "/review/daily-ask/skip", {"ask_date": ask_date})
    assert s1 == (200, {"ask_date": ask_date, "status": "skipped"})
    assert rest(env, "POST", "/review/daily-ask/skip", {"ask_date": ask_date}) == s1
    with env.master() as c:
        ask = c.execute(
            "select status, item_count, pending_total_vnd, resolved_at is not null from review_asks where user_id = %s",
            (MINH,),
        ).fetchall()
    assert ask == [("skipped", 2, 180_000, True)]  # hai khoản seed
    _, body = rest(env, "GET", "/review", query={"mode": "daily_ask"})
    assert body["data"]["ask"]["status"] == "skipped" and body["data"]["count"] == 2
    svc, *_ = make(env, judge=FakeJudge(Verdict(None, 0.0)))
    svc.run(MINH, record(env, amount_vnd=30_000, tx_type="qr_other", counterparty="Tiệm Lạ"))
    with env.master() as c:
        assert c.execute(
            "select status, item_count from review_asks where user_id = %s", (MINH,)
        ).fetchall() == [("skipped", 3)]  # pipeline giữ nguyên `skipped`, chỉ cập nhật số mục


def test_review_ba_muc_tu_gan_vao_xem_lai_roi_dung_roi_xoa_co_khong_chuyen_tien(env, schema):
    env.reset(MINH)
    strict = load_thresholds(
        {
            "YOFINA_CLASSIFY_AUTO_MIN_CONFIDENCE": "0.99",
            "YOFINA_CLASSIFY_REVIEW_MIN_CONFIDENCE": "0.1",
        }
    )
    svc, *_ = make(env, th=strict, judge=FakeJudge(Verdict("giai_tri", 0.9, "an_uong")))
    tx = record(env, amount_vnd=60_000, tx_type="qr_other", counterparty="Quán Cô Hà")
    out = svc.run(MINH, tx)
    assert (out.status, out.tier, out.jar, out.classified_by) == (
        "assigned",
        "review",
        "giai_tri",
        "llm",
    )
    r = row(env, tx)
    assert r["jar"] == "giai_tri" and r["needs_review"] is True and r["suggested"] == ["an_uong"]
    bal = jar_bal(env)
    status, body = rest(env, "GET", "/review")
    assert status == 200
    schema("blocks/review_list.schema.json", body)
    item = next(i for i in parse_block(body).data.items if i.transaction_id == tx)
    assert (item.tier, item.classified_by, item.current_jar.code) == ("review", "llm", "giai_tri")
    assert item.suggestions[0].jar.code == "an_uong"
    # tool get_unclassified: tương thích ngược và có phần mở rộng
    res = handle_gateway({"user_id": MINH}, gateway_context("ledger___get_unclassified"), env.svc)
    schema("tools/ledger.results.schema.json#/$defs/GetUnclassifiedResult", res)
    it = next(i for i in res["data"]["items"] if i["transaction"]["id"] == tx)
    assert it["tier"] == "review" and it["classified_by"] == "llm" and "confidence" in it
    # "đúng rồi": assign_jar với CHÍNH hũ hiện tại
    receipt = env.act(MINH, "assign_jar", {"transaction_id": tx, "jar": "giai_tri"})
    assert receipt["data"]["summary"].startswith("Đã xác nhận giao dịch ở hũ")
    r2 = row(env, tx)
    assert (r2["by"], r2["needs_review"], r2["suggested"], r2["conf"]) == (
        "user",
        False,
        None,
        None,
    )
    assert jar_bal(env) == bal  # không chuyển tiền
    with env.master() as c:
        lab = c.execute(
            "select jar_code, source from tx_embeddings_labeled where user_id = %s and transaction_id = %s",
            (MINH, tx),
        ).fetchall()
    assert lab == [("giai_tri", "user")]  # nhãn k-NN từ embedding đã lưu lúc phân loại
    # xác nhận lần hai khi đã hết cờ cần xem lại thì bị từ chối (không phải thao tác thật)
    from yofina_core.errors import YofinaError

    with pytest.raises(YofinaError):
        env.act(MINH, "assign_jar", {"transaction_id": tx, "jar": "giai_tri"})


def test_xac_nhan_cung_hu_voi_luon_luon_luu_luat(env):
    env.reset(MINH)
    strict = load_thresholds(
        {
            "YOFINA_CLASSIFY_AUTO_MIN_CONFIDENCE": "0.99",
            "YOFINA_CLASSIFY_REVIEW_MIN_CONFIDENCE": "0.1",
        }
    )
    svc, *_ = make(env, th=strict, judge=FakeJudge(Verdict("giai_tri", 0.9)))
    tx = record(env, amount_vnd=60_000, tx_type="qr_other", counterparty="Rạp Mới")
    svc.run(MINH, tx)
    env.act(MINH, "assign_jar", {"transaction_id": tx, "jar": "giai_tri", "remember": "always"})
    with env.master() as c:
        rules = c.execute(
            "select match_type, scope, jar_code from category_rules where user_id = %s", (MINH,)
        ).fetchall()
    assert rules == [("merchant", "always", "giai_tri")]
    # giao dịch kế tiếp cùng đối tác: luật thắng, tự gán mà không gọi model
    svc2, emb2, judge2 = make(env, th=strict, judge=FakeJudge(Verdict("an_uong", 1.0)))
    tx2 = record(env, amount_vnd=60_000, tx_type="qr_other", counterparty="Rạp Mới")
    out = svc2.run(MINH, tx2)
    assert (out.jar, out.stage, out.classified_by) == ("giai_tri", "rule", "rule")
    assert judge2.prompts == [] and emb2.calls == []
    with env.master() as c:
        assert (
            c.execute(
                "select hit_count from category_rules where user_id = %s", (MINH,)
            ).fetchone()[0]
            == 1
        )


# --- sửa nhiều lần nâng ngưỡng, đóng câu hỏi gộp -------------------------------------------------------------------
def test_sua_lan_gan_tu_dong_dem_va_nang_nguong_rieng_cua_nguoi_nhan(env):
    env.reset(MINH)
    loose = load_thresholds(
        {
            "YOFINA_CLASSIFY_AUTO_MIN_CONFIDENCE": "0.5",
            "YOFINA_CLASSIFY_REVIEW_MIN_CONFIDENCE": "0.1",
            "YOFINA_CLASSIFY_HISTORY_MIN_COUNT": "1000",  # cô lập khỏi lịch sử giao dịch seed của người nhận
        }
    )
    svc, *_ = make(
        env, th=loose, emb=FakeEmbedder(orthogonal=True), judge=FakeJudge(Verdict("giai_tri", 1.0))
    )
    payee = env.svc.payees_response(MINH)["payees"][0]
    for i in range(3):
        tx = record(
            env,
            amount_vnd=50_000,
            tx_type="transfer_person",
            payee_id=payee["id"],
            note=("tien com", "tien xang", "tien nuoc")[i],
        )
        out = svc.run(MINH, tx)
        assert out.status == "assigned" and out.jar == "giai_tri" and out.classified_by == "llm", (
            i,
            out,
        )
        env.act(
            MINH, "assign_jar", {"transaction_id": tx, "jar": "an_uong"}
        )  # người dùng sửa sang hũ khác
        with env.master() as c:
            cnt, amc = c.execute(
                "select correction_count, auto_min_confidence from payees where id = %s",
                (payee["id"],),
            ).fetchone()
        assert cnt == i + 1
        if i == 0:
            assert amc is None  # mới sửa một lần: chưa nâng (correction_min_count)
    assert float(amc) == pytest.approx(
        TH.auto_min_confidence + 2 * TH.auto_min_confidence_step, abs=1e-3
    )


def test_tra_loi_het_cau_hoi_gop_thi_dong_cau_hoi_va_khong_tinh_la_sua(env):
    env.reset(MINH)
    svc, *_ = make(env, judge=FakeJudge(Verdict(None, 0.0)))
    tx = record(env, amount_vnd=70_000, tx_type="qr_other", counterparty="Tiệm Lạ Hoắc")
    svc.run(MINH, tx)
    with env.master() as c:
        assert (
            c.execute(
                "select count(*) from tx_embeddings where transaction_id = %s", (tx,)
            ).fetchone()[0]
            == 1
        )
    items = env.svc.unclassified_result(MINH)["data"]["items"]
    assert len(items) == 3
    for it in items:
        env.act(MINH, "assign_jar", {"transaction_id": it["transaction"]["id"], "jar": "an_uong"})
        if it is not items[-1]:
            assert (
                rest(env, "GET", "/review", query={"mode": "daily_ask"})[1]["data"]["ask"]["status"]
                == "open"
            )
    with env.master() as c:
        assert c.execute(
            "select status, resolved_at is not null from review_asks where user_id = %s", (MINH,)
        ).fetchall() == [("answered", True)]
        assert (
            c.execute(
                "select sum(correction_count) from payees where user_id = %s", (MINH,)
            ).fetchone()[0]
            == 0
        )
    body = rest(env, "GET", "/review", query={"mode": "daily_ask"})[1]
    assert (
        body["data"]["count"] == 0 and body["data"]["headline"] == "Không có giao dịch nào cần hỏi."
    )
    # câu trả lời của người dùng đã thành nhãn k-NN (giao dịch có embedding)
    with env.master() as c:
        labels = c.execute(
            "select count(*) from tx_embeddings_labeled where user_id = %s and source = 'user'",
            (MINH,),
        ).fetchone()[0]
    assert labels == 1


def test_mot_ask_moi_sau_khi_da_tra_loi_xong_mo_lai_cau_hoi_cua_ngay(env):
    env.reset(MINH)
    svc, *_ = make(env, judge=FakeJudge(Verdict(None, 0.0)))
    for it in env.svc.unclassified_result(MINH)["data"]["items"]:
        env.act(MINH, "assign_jar", {"transaction_id": it["transaction"]["id"], "jar": "an_uong"})
    svc.run(MINH, record(env, amount_vnd=30_000, tx_type="qr_other", counterparty="Tiệm A"))
    assert (
        rest(env, "GET", "/review", query={"mode": "daily_ask"})[1]["data"]["ask"]["status"]
        == "open"
    )


# --- consumer SQS trên DB thật ------------------------------------------------------------------------------------
def test_consumer_sqs_idempotent_voi_idempotency_trong_bo_nho(env):
    env.reset(MINH)
    svc, *_ = make(env)
    tx = record(env, amount_vnd=50_000, tx_type="food_drink")
    ev = next(e for e in env.events.sent if e.detail.get("transaction_id") == tx)
    body = json.dumps(
        {"source": "yofina.ledger", "detail-type": ev.detail_type, "detail": ev.detail}
    )

    class Idem:
        def __init__(self):
            self.done = set()

        def claim(self, event_id, *, user_id=None):
            from yofina_classify.idempotency import Claim

            return Claim.DUPLICATE if event_id in self.done else Claim.CLAIMED

        def complete(self, event_id):
            self.done.add(event_id)

        def release(self, event_id):
            pass

    idem = Idem()
    recs = [{"messageId": "m1", "body": body}]
    r1 = process_records(recs, svc, idem, max_receive_count=3)
    r2 = process_records(recs, svc, idem, max_receive_count=3)
    assert (r1.assigned, r2.duplicates, r1.failures, r2.failures) == (1, 1, [], [])


def test_dat_lai_xoa_nhan_nguoi_dung_va_seed_nap_lai_khi_co_file(env):
    """Bảng nhãn có khóa ngoại tới hũ nên đặt lại xóa cả nhãn; `apply_seed_labels` nạp lại nhãn seed (không có file thì 0)."""
    from yofina_ledger import classify_seed

    env.reset(MINH)
    add_label(env, "ca phe nha rieng", "an_uong", source="user")
    env.reset(MINH)
    with env.master() as c:
        assert (
            c.execute(
                "select count(*) from tx_embeddings_labeled where user_id = %s", (MINH,)
            ).fetchone()[0]
            == 0
        )
    # persona không có file nhãn thì không nạp gì, không lỗi
    assert classify_seed.apply_seed_labels(env.db, MINH, "persona_khong_co") == 0
