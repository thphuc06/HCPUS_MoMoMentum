"""Quyết định thuần: k-NN, trộn bằng chứng, mức tin cậy, ngưỡng đọc từ cấu hình (phase 4 luồng B)."""

from __future__ import annotations

import classify_helpers  # noqa: F401  (đặt đường nhập cho pipelines/classify, evals/classification)
import pytest
from yofina_classify import decide
from yofina_classify.model import Evidence, ExactLabel, Neighbor, Verdict

from yofina_ledger.classify_config import ClassifyConfigError, load_thresholds

TH = load_thresholds({})


def test_cau_hinh_mac_dinh_hop_le_va_moi_so_co_nguon():
    from yofina_ledger.classify_config import load_raw

    raw = load_raw()
    assert TH.review_min_confidence <= TH.auto_min_confidence
    for name, entry in raw["thresholds"].items():
        assert {"value", "unit", "note", "source"} <= set(entry), name
    assert "0,97" in raw["note"]  # nhắc rõ ngưỡng của proposal đã bị bác


def test_env_ghi_de_va_kiem_mien():
    t = load_thresholds(
        {"YOFINA_CLASSIFY_AUTO_MIN_CONFIDENCE": "0.95", "YOFINA_CLASSIFY_KNN_K": "7"}
    )
    assert t.auto_min_confidence == 0.95 and t.knn_k == 7
    with pytest.raises(ClassifyConfigError):
        load_thresholds({"YOFINA_CLASSIFY_REVIEW_MIN_CONFIDENCE": "0.99"})  # lớn hơn auto
    with pytest.raises(ClassifyConfigError):
        load_thresholds({"YOFINA_CLASSIFY_KNN_K": "abc"})
    with pytest.raises(ClassifyConfigError):
        load_thresholds({"YOFINA_CLASSIFY_SUGGESTIONS_MAX": "3"})  # CHECK cardinality <= 2


def test_nguong_rieng_cua_nguoi_nhan_khong_bao_gio_thap_hon_nguong_chung():
    assert TH.auto_threshold_for(None) == TH.auto_min_confidence
    assert TH.auto_threshold_for(0.5) == TH.auto_min_confidence
    assert TH.auto_threshold_for(0.97) == 0.97


def test_tier_of_ba_muc():
    assert decide.tier_of(0.95, 0.9, 0.6) == "auto"
    assert decide.tier_of(0.9, 0.9, 0.6) == "auto"
    assert decide.tier_of(0.7, 0.9, 0.6) == "review"
    assert decide.tier_of(0.59, 0.9, 0.6) == "ask"


def test_knn_chi_nhan_nhan_tu_do_giong_toi_thieu_va_tinh_bien():
    nb = [
        Neighbor("an_uong", 0.95),
        Neighbor("an_uong", 0.90),
        Neighbor("hoa_don", 0.80),
        Neighbor("di_lai", 0.5),
    ]
    feats = decide.knn_features(nb, TH)
    assert [f[0] for f in feats] == ["an_uong", "hoa_don"]  # di_lai dưới ngưỡng giống
    assert feats[0][1] == pytest.approx(0.95) and feats[0][2] == pytest.approx(0.15)
    assert feats[1][2] == pytest.approx(-0.15)  # biên của hũ thứ hai là âm
    only = decide.knn_features([Neighbor("an_uong", 0.9)], TH)
    assert only[0][2] == pytest.approx(0.9 - TH.knn_min_similarity)
    assert decide.knn_features([Neighbor("an_uong", TH.knn_min_similarity - 0.01)], TH) == []


def test_knn_xac_suat_tang_theo_do_giong_va_bien():
    lo = decide.knn_evidence([Neighbor("a", 0.75)], TH)[0].p
    hi = decide.knn_evidence([Neighbor("a", 0.95)], TH)[0].p
    assert 0 < lo < hi < 1
    narrow = decide.knn_evidence([Neighbor("a", 0.9), Neighbor("b", 0.89)], TH)[0].p
    wide = decide.knn_evidence([Neighbor("a", 0.9), Neighbor("b", 0.72)], TH)[0].p
    assert narrow < wide


def test_exact_nhan_moi_nhat_thang_nhan_cu_hu_khac_chi_la_bang_chung_yeu():
    ev = decide.exact_evidence(
        [ExactLabel("an_uong", "user", 0), ExactLabel("giai_tri", "seed", 1)], TH
    )
    assert ev[0].jar == "an_uong" and ev[0].p == pytest.approx(
        TH.exact_match_confidence + TH.exact_match_user_bonus
    )
    assert ev[1].jar == "giai_tri" and ev[1].p < ev[0].p / 1.5
    ranked = decide.fuse(ev, TH)
    assert ranked[0][0] == "an_uong" and ranked[0][1] < ev[0].p  # có mâu thuẫn thì độ tin cậy tụt


def test_fuse_cong_dong_bang_chung_cung_hu_va_tru_khi_mau_thuan():
    agree = decide.fuse([Evidence("a", 0.6, "embedding"), Evidence("a", 0.6, "llm")], TH)
    assert agree[0][1] == pytest.approx(1 - 0.4 * 0.4)
    clash = decide.fuse([Evidence("a", 0.6, "embedding"), Evidence("b", 0.6, "llm")], TH)
    assert clash[0][1] == pytest.approx(0.6 * (1 - TH.conflict_weight * 0.6))
    assert decide.fuse([], TH) == []


def test_history_can_toi_thieu_va_co_tran():
    assert decide.history_evidence({"an_uong": 2}, TH) == []  # dưới history_min_count
    ev = decide.history_evidence({"an_uong": 30, "giai_tri": 1}, TH)
    assert ev[0].jar == "an_uong" and ev[0].p == pytest.approx(
        TH.history_max_confidence
    )  # trần: không tự gán một mình
    assert ev[0].p < TH.auto_min_confidence


def test_llm_evidence_hieu_chinh_khong_tin_thang_do_chac_cua_model():
    ev = decide.llm_evidence(Verdict("an_uong", 1.0, "giai_tri"), TH)
    assert ev[0].jar == "an_uong" and ev[0].p < 1.0
    assert ev[1].jar == "giai_tri" and ev[1].p < ev[0].p
    assert decide.llm_evidence(Verdict(None, 0.0), TH) == [] and decide.llm_evidence(None, TH) == []


def test_classified_by_history_tinh_vao_buoc_model_nho():
    ev = [Evidence("a", 0.5, "history"), Evidence("a", 0.4, "llm")]
    assert decide.dominant_source(ev, "a") == "llm"
    assert decide.dominant_source([Evidence("a", 0.9, "embedding")], "a") == "embedding"
