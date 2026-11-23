"""Bộ phân loại: bảng tra, luật, embedding, model nhỏ và các ràng buộc cuối (phase 4 luồng B). Cổng giả chỉ có ở đây."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import classify_helpers  # noqa: F401  (đặt đường nhập cho pipelines/classify, evals/classification)
import pytest
from yofina_classify.model import (
    ExactLabel,
    JarInfo,
    Neighbor,
    RuleHit,
    TxFacts,
    TypeInfo,
    UserContext,
    Verdict,
)
from yofina_classify.pipeline import Classifier

from yofina_core.llm import AllModelsFailed, ModelBudgetExceeded
from yofina_core.wallet import EMBEDDING_DIMENSIONS
from yofina_ledger.classify_config import load_thresholds

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
TH = load_thresholds({})
JARS = {
    c: JarInfo(c, n, k, 1_000_000)
    for c, n, k in [
        ("an_uong", "Ăn uống", "spending"),
        ("di_lai", "Đi lại", "spending"),
        ("hoa_don", "Hóa đơn", "spending"),
        ("giai_tri", "Giải trí", "spending"),
    ]
}
TYPES = {
    "food_drink": TypeInfo("food_drink", "Ăn uống", "out", "an_uong"),
    "qr_other": TypeInfo("qr_other", "Quét QR cửa hàng khác", "out", None),
    "transfer_person": TypeInfo("transfer_person", "Chuyển tiền cho người khác", "out", None),
}
VEC = [0.01] * EMBEDDING_DIMENSIONS


class Labels:
    def __init__(self, exact=(), knn=()):
        self.exact, self.nn = list(exact), list(knn)

    def find_exact(self, user_id, text_norm):
        return list(self.exact)

    def knn(self, user_id, vector, k):
        return list(self.nn)


class Emb:
    def __init__(self, fail=None):
        self.calls, self.fail = 0, fail

    def embed(self, text_norm):
        self.calls += 1
        if self.fail:
            raise self.fail
        return "cohere.embed-multilingual-v3", VEC


class Judge:
    def __init__(self, verdict=None, fail=None):
        self.verdict, self.fail, self.prompts = verdict, fail, []

    def __call__(self, prompt, jars):
        self.prompts.append(prompt)
        if self.fail:
            raise self.fail
        return self.verdict


def facts(**kw):
    base = dict(
        transaction_id="t1",
        user_id="u",
        kind="expense",
        amount_vnd=120_000,
        occurred_at=datetime(2026, 11, 20, 5, 30, tzinfo=ZoneInfo("UTC")),
        app_date=datetime(2026, 11, 20).date(),
        tx_type="qr_other",
        funding_source="jar",
        counterparty="QR - Quán Cô Hà",
        note=None,
        payee_id=None,
        is_person=False,
        jar_code="chua_phan_loai",
        in_unclassified=True,
    )
    base.update(kw)
    return TxFacts(**base)


def ctx(**kw):
    base = dict(
        jars=JARS,
        type_map=TYPES,
        rule=None,
        payee_auto_min=None,
        merchant_corrections=0,
        history={},
        tz=TZ,
    )
    base.update(kw)
    return UserContext(**base)


def clf(labels=None, emb=None, judge=None, th=TH):
    return Classifier(th, labels or Labels(), emb or Emb(), judge or Judge(Verdict(None, 0.0)))


def test_buoc_0_bang_tra_tu_gan_khong_goi_embedding_hay_model():
    e, j = Emb(), Judge(Verdict("di_lai", 1.0))
    d = clf(emb=e, judge=j).classify(facts(tx_type="food_drink"), ctx())
    assert (d.jar, d.tier, d.classified_by, d.stage) == ("an_uong", "auto", "type_map", "type_map")
    assert e.calls == 0 and j.prompts == []


def test_luat_cua_nguoi_dung_thang_bang_tra_va_luon_la_auto():
    d = clf().classify(facts(tx_type="food_drink"), ctx(rule=RuleHit("merchant", "k", "giai_tri")))
    assert (d.jar, d.tier, d.classified_by, d.confidence) == (
        "giai_tri",
        "auto",
        "rule",
        TH.rule_confidence,
    )


def test_luat_tro_toi_hu_da_xoa_thi_bi_bo_qua():
    d = clf(judge=Judge(Verdict("an_uong", 0.9))).classify(
        facts(), ctx(rule=RuleHit("merchant", "k", "da_xoa"))
    )
    assert d.classified_by != "rule"


def test_nguong_rieng_cua_nguoi_nhan_ha_bang_tra_xuong_review():
    d = clf().classify(facts(tx_type="food_drink", payee_id="p"), ctx(payee_auto_min=0.99))
    assert (d.jar, d.tier) == ("an_uong", "review")  # 0,95 < 0,99


def test_nguong_rieng_cua_doi_tac_tu_so_luat_once():
    c = clf()
    assert c.auto_threshold(facts(), ctx(merchant_corrections=1)) == TH.auto_min_confidence
    n = TH.correction_min_count
    assert c.auto_threshold(facts(), ctx(merchant_corrections=n)) == pytest.approx(
        TH.auto_min_confidence + TH.auto_min_confidence_step
    )
    assert c.auto_threshold(facts(), ctx(merchant_corrections=999)) == TH.auto_min_confidence_cap


def test_khop_chinh_xac_du_chac_thi_khong_goi_embedding_hay_model():
    e, j = Emb(), Judge(Verdict("di_lai", 1.0))
    labels = Labels(exact=[ExactLabel("giai_tri", "user", 0)])
    d = clf(labels, e, j).classify(facts(counterparty="Cinestar"), ctx())
    assert (d.jar, d.tier, d.classified_by, d.stage) == (
        "giai_tri",
        "auto",
        "embedding",
        "embedding",
    )
    assert e.calls == 0 and j.prompts == [] and d.embedding is None


def test_knn_gan_va_ro_thi_auto_roi_khong_goi_model_va_giu_embedding_de_ghi():
    j = Judge(Verdict("di_lai", 1.0))
    d = clf(Labels(knn=[Neighbor("an_uong", 0.99)]), judge=j).classify(facts(), ctx())
    assert d.stage == "embedding" and d.jar == "an_uong" and d.tier == "auto" and j.prompts == []
    assert d.embedding is not None and d.embedding[1] == "cohere.embed-multilingual-v3"


def test_knn_yeu_thi_chay_tiep_sang_model_va_dong_y_thi_tang_do_tin_cay():
    nb = [Neighbor("an_uong", 0.8)]
    only_knn = clf(Labels(knn=nb), judge=Judge(Verdict(None, 0.0))).classify(facts(), ctx())
    both = clf(Labels(knn=nb), judge=Judge(Verdict("an_uong", 0.8))).classify(facts(), ctx())
    assert both.jar == "an_uong" and both.confidence > only_knn.confidence
    assert both.llm_called and both.stage == "llm"


def test_model_va_embedding_bat_dong_thi_khong_con_tu_gan():
    d = clf(
        Labels(knn=[Neighbor("an_uong", 0.85)]), judge=Judge(Verdict("giai_tri", 0.9))
    ).classify(facts(), ctx())
    assert d.tier != "auto"
    assert {j for j, _ in d.candidates} >= {"an_uong", "giai_tri"}


def test_ma_hu_model_tra_ngoai_danh_sach_bi_bo_khong_theo_chi_dan_tiem():
    from yofina_classify.llm_step import LlmChoice, validate_verdict

    v = validate_verdict(LlmChoice(jar_code="du_phong", confidence=5, runner_up="di_lai"), JARS)
    assert v.jar_code is None and v.confidence == 0.0 and v.runner_up == "di_lai"
    assert (
        validate_verdict(LlmChoice(jar_code="an_uong", confidence=7.0), JARS).confidence == 1.0
    )  # kẹp về [0, 1]


def test_thong_diep_model_khong_chua_ten_nguoi_hay_so_tai_khoan_va_co_tin_hieu_hanh_vi():
    j = Judge(Verdict("an_uong", 0.7))
    clf(judge=j).classify(
        facts(
            counterparty="Trần Quang Huy",
            payee_id="p",
            is_person=True,
            tx_type="transfer_person",
            note="ck 0123456789012 tien com",
            amount_vnd=60_000,
        ),
        ctx(history={"an_uong": 3, "giai_tri": 1}),
    )
    prompt = j.prompts[0]
    assert "Trần" not in prompt and "Huy" not in prompt and "0123456789012" not in prompt
    assert "T***" in prompt and "****9012" in prompt
    assert (
        '"an_uong": 3' in prompt
        and '"gio_dia_phuong": 12' in prompt
        and "so_tien_tron_chuc_nghin" in prompt
    )


def test_chuyen_khoan_ten_rieng_khong_loi_nhan_khong_lich_su_thi_hoi_va_khong_nhung():
    e = Emb()
    d = clf(emb=e).classify(
        facts(counterparty="Lê Minh Châu", payee_id="p", is_person=True, tx_type="transfer_person"),
        ctx(),
    )
    assert d.tier == "ask" and e.calls == 0 and d.embedding is None


def test_lich_su_cung_nguoi_nhan_cho_goi_y_nhung_mot_minh_khong_tu_gan():
    d = clf().classify(
        facts(counterparty="Lê Minh Châu", payee_id="p", is_person=True, tx_type="transfer_person"),
        ctx(history={"giai_tri": 20}),
    )
    assert d.jar == "giai_tri" and d.tier == "review" and d.classified_by == "llm"


def test_model_het_tran_ngay_thi_suy_giam_ve_hoi_gop_khong_nem_loi():
    d = clf(judge=Judge(fail=ModelBudgetExceeded("hết", role="small"))).classify(facts(), ctx())
    assert d.tier == "ask" and d.llm_error == "ModelBudgetExceeded"


def test_model_nghen_thi_thu_lai_cho_toi_lan_giao_cuoi_roi_suy_giam():
    c = clf(judge=Judge(fail=AllModelsFailed("small", [("m", "ThrottlingException")])))
    with pytest.raises(AllModelsFailed):
        c.classify(facts(), ctx(), degrade_on_transient=False)
    d = c.classify(facts(), ctx(), degrade_on_transient=True)
    assert d.tier == "ask" and d.llm_error == "AllModelsFailed"


def test_embedding_het_tran_van_chay_tiep_bang_model():
    d = clf(
        emb=Emb(fail=ModelBudgetExceeded("hết", role="embedding")),
        judge=Judge(Verdict("an_uong", 0.95)),
    ).classify(facts(), ctx())
    assert d.jar == "an_uong" and d.embedding is None and d.llm_called


def test_hu_dich_khong_du_so_du_thi_o_lai_hoi_gop():
    jars = {**JARS, "an_uong": JarInfo("an_uong", "Ăn uống", "spending", 10_000)}
    d = clf().classify(facts(tx_type="food_drink"), ctx(jars=jars))
    assert d.tier == "ask" and d.note == "hu_khong_du_so_du" and d.jar == "an_uong"
    credit = clf().classify(facts(tx_type="food_drink", funding_source="credit"), ctx(jars=jars))
    assert credit.tier == "auto"  # mua bằng hạn mức không đổi số dư hũ


def test_khoan_nho_mot_lan_khong_ro_vao_hu_khac_chi_khi_nguoi_dung_co_hu_do():
    other = {**JARS, "khac": JarInfo("khac", "Khác", "spending", 500_000)}
    small = facts(amount_vnd=TH.small_one_off_max_vnd)
    d = clf().classify(small, ctx(jars=other))
    assert (d.jar, d.tier) == ("khac", "auto") and d.note == "khoan_nho_mot_lan"
    assert clf().classify(small, ctx()).tier == "ask"  # không có hũ Khác
    assert (
        clf().classify(facts(amount_vnd=TH.small_one_off_max_vnd + 1), ctx(jars=other)).tier
        == "ask"
    )
    assert (
        clf().classify(small, ctx(jars=other, history={"an_uong": 1})).tier == "ask"
    )  # không còn là "một lần"


def test_goi_y_hoi_gop_toi_da_hai_khong_trung():
    labels = Labels(
        knn=[Neighbor("an_uong", 0.8), Neighbor("giai_tri", 0.79), Neighbor("hoa_don", 0.78)]
    )
    c = clf(labels, judge=Judge(Verdict(None, 0.0)))
    sug = c.suggestions(c.classify(facts(), ctx()))
    assert len(sug) <= 2 and len(set(sug)) == len(sug)


def test_doi_nguong_cau_hinh_thi_doi_ket_qua_khong_doi_ma():
    strict = load_thresholds(
        {
            "YOFINA_CLASSIFY_AUTO_MIN_CONFIDENCE": "0.999",
            "YOFINA_CLASSIFY_REVIEW_MIN_CONFIDENCE": "0.98",
        }
    )
    d = clf(
        Labels(knn=[Neighbor("an_uong", 0.9)]), th=strict, judge=Judge(Verdict(None, 0.0))
    ).classify(facts(), ctx())
    assert d.tier == "ask"
