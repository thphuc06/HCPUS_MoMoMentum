"""Lý do gợi ý, câu mở đầu, nhãn seed, bộ dữ liệu và bộ kiểm chạy chế độ khô (phase 4 luồng B)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import classify_helpers  # noqa: F401  (đặt đường nhập cho pipelines/classify, evals/classification)
import numpy as np
import pytest

from yofina_core.wallet import EMBEDDING_DIMENSIONS
from yofina_ledger import classify_seed, review_reads, review_rest
from yofina_ledger.classify_write import AssignContext, is_confirm_same_jar, is_correction, pg_array

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "evals" / "classification"))


def test_ly_do_goi_y_do_code_dung_ngan_hon_80_ky_tu():
    t1 = review_reads.reason_text(n_same=4, by_payee=True, type_default=False, has_note=False)
    assert t1 == "Giống 4 giao dịch trước gửi cho cùng người"
    assert review_reads.reason_text(
        n_same=2, by_payee=False, type_default=False, has_note=False
    ).endswith("cùng nơi")
    assert "thường vào hũ này" in review_reads.reason_text(
        n_same=0, by_payee=True, type_default=True, has_note=True
    )
    assert "lời nhắn" in review_reads.reason_text(
        n_same=0, by_payee=False, type_default=False, has_note=True
    )
    assert "số tiền" in review_reads.reason_text(
        n_same=0, by_payee=False, type_default=False, has_note=False
    )
    assert (
        len(
            review_reads.reason_text(
                n_same=10**9, by_payee=True, type_default=False, has_note=False
            )
        )
        <= 80
    )


def test_goi_y_chi_gan_do_tin_cay_cho_goi_y_dau_va_bo_hu_da_xoa():
    out = review_reads.suggestion_entries(
        "tx",
        ["an_uong", "da_xoa", "giai_tri"],
        jar_names={"an_uong": "Ăn uống", "giai_tri": "Giải trí"},
        payee_id="p",
        merchant=None,
        tx_type=None,
        note=None,
        type_defaults={},
        counts={("tx", "an_uong"): 3},
        confidence=0.4123,
    )
    assert out[0] == {
        "code": "an_uong",
        "reason": "Giống 3 giao dịch trước gửi cho cùng người",
        "confidence": 0.412,
    }
    assert len(out) == 1  # hũ đã xóa và gợi ý thứ hai ngoài danh sách bị bỏ


def test_tham_so_mode_limit_nghiem_ngat():
    from yofina_core.errors import YofinaError

    assert (
        review_reads.parse_mode(None) == "review"
        and review_reads.parse_mode("daily_ask") == "daily_ask"
    )
    with pytest.raises(YofinaError):
        review_reads.parse_mode("khac")
    assert (
        review_reads.parse_limit(None) == 20
        and review_reads.parse_limit("999") == 50
        and review_reads.parse_limit("0") == 1
    )
    with pytest.raises(YofinaError):
        review_reads.parse_limit("abc")


def test_cau_mo_dau_do_code_dung():
    assert (
        review_rest.headline("daily_ask", 2, 180_000)
        == "Hôm nay mình chưa xếp được hũ cho 2 giao dịch, tổng 180.000 ₫."
    )
    assert review_rest.headline("daily_ask", 0, 0) == "Không có giao dịch nào cần hỏi."
    assert "xem lại" in review_rest.headline("review", 3, 90_000)
    assert review_rest.headline("review", 0, 0) == "Không có giao dịch nào cần xem lại."


def test_xac_nhan_cung_hu_chi_hop_le_khi_dang_cho_xem_lai():
    assert is_confirm_same_jar({"needs_review": True, "jar_code": "an_uong"}, {"jar": "an_uong"})
    assert not is_confirm_same_jar(
        {"needs_review": False, "jar_code": "an_uong"}, {"jar": "an_uong"}
    )
    assert not is_confirm_same_jar({"needs_review": True, "jar_code": "an_uong"}, {"jar": "di_lai"})


def test_la_sua_chi_khi_doi_hu_cua_mot_lan_gan_tu_dong():
    auto = AssignContext("llm", "an_uong", None, "p", "x")
    assert is_correction(auto, "giai_tri") and not is_correction(auto, "an_uong")
    assert not is_correction(AssignContext("user", "an_uong", None, "p", "x"), "giai_tri")
    assert not is_correction(
        AssignContext("llm", "chua_phan_loai", "unclassified", "p", "x"), "giai_tri"
    )
    assert not is_correction(None, "giai_tri")


def test_pg_array_chi_nhan_ma_hu_hop_le_toi_da_hai():
    assert pg_array(["a_b", "c1", "d"]) == "{a_b,c1}" and pg_array([]) is None
    assert pg_array(['x"; DROP']) is None


def test_vector_seed_khu_hoi_float16_va_sai_chieu_bi_tu_choi():
    rng = np.random.default_rng(1)
    v = rng.normal(size=EMBEDDING_DIMENSIONS).tolist()
    out = classify_seed.decode_vector(classify_seed.encode_vector(v))
    assert np.allclose(v, out, atol=5e-3)
    assert len(classify_seed.encode_vector(v)) < 3000  # ~2,7 KB thay vì ~10 KB chữ
    with pytest.raises(ValueError):
        classify_seed.encode_vector([0.1, 0.2])


def test_bo_du_lieu_du_300_dong_co_chuyen_khoan_ten_rieng_khong_loi_nhan_va_khop_bo_sinh():
    import build_dataset

    rows = build_dataset.build()
    assert build_dataset.check(rows) == []
    assert len(rows) >= 300
    assert {r["persona"] for r in rows} == {"minh", "lan", "khoa"}
    no_note = [r for r in rows if r["category"] == "person_no_note"]
    assert no_note and all(r["note"] is None and r["is_person"] for r in no_note)
    on_disk = (REPO / "evals" / "classification" / "dataset.jsonl").read_text(encoding="utf-8")
    assert on_disk == build_dataset.dumps(rows), (
        "dataset.jsonl lệch bộ sinh: chạy lại build_dataset.py"
    )


def test_cua_hang_chua_thay_khong_trung_voi_nhan_seed():
    """Chống rò rỉ: nhóm `unseen_qr` không được nằm trong nhãn seed (nếu không độ đúng bị thổi phồng)."""
    import build_dataset
    import build_seed_labels
    from yofina_classify.text import normalize_text

    seeds = {t for p in ("minh", "lan", "khoa") for t, _ in build_seed_labels.normalized_labels(p)}
    leaks = []
    for items in build_dataset.UNSEEN.values():
        for name, _ in items:
            if normalize_text(name) in seeds:
                leaks.append(name)
    assert leaks == []


def test_mo_phong_che_do_kho_chay_tu_dau_den_cuoi_va_chi_so_nhat_quan():
    import fakes
    import sim

    rows = sim.load_dataset()
    caches = sim.Caches()
    texts = sim.prefetch_texts(rows)
    caches.embeddings = dict(zip(texts, fakes.HashingEmbedder().embed_many(texts)[1], strict=True))
    emb = sim.CachedEmbedder(caches, fakes.MODEL_ID)
    judge = sim.CachedJudge(caches, fakes.KeywordJudge())
    from yofina_ledger.classify_config import load_thresholds

    res = sim.run_sim(rows, load_thresholds({}), caches, emb, judge)
    assert len(res) == len(rows)
    m = sim.metrics(res)
    assert m["assigned"] + m["ask"] == m["n"] and m["auto"] + m["review"] == m["assigned"]
    assert 0 <= m["accuracy_assigned"] <= 1
    # mục `mapped_type` là bước 0: đúng theo bảng tra
    assert m["by_category"]["mapped_type"]["accuracy_assigned"] == 1.0
    # cùng đầu vào, cùng kết quả (tất định)
    res2 = sim.run_sim(rows, load_thresholds({}), caches, emb, judge)
    assert [(r.decision.jar, r.decision.tier) for r in res] == [
        (r.decision.jar, r.decision.tier) for r in res2
    ]
    assert set(sim.split_of(rows).values()) == {"calibration", "test"}


def test_hoi_quy_logistic_khoi_phuc_he_so_va_bang_dau_hieu():
    import run_eval

    rng = np.random.default_rng(0)
    x = rng.uniform(0.7, 1.0, size=(4000, 1))
    p = 1 / (1 + np.exp(-(-20 + 25 * x[:, 0])))
    y = (rng.uniform(size=4000) < p).astype(float)
    w = run_eval.fit_logistic(x, y)
    assert w[1] == pytest.approx(25, rel=0.25) and w[0] == pytest.approx(-20, rel=0.25)


def test_che_do_kho_khong_ghi_cau_hinh(tmp_path, monkeypatch):
    import run_eval

    monkeypatch.setattr(
        sys,
        "argv",
        ["run_eval.py", "calibrate", "--mode", "dry", "--write-config", "--limit", "12"],
    )
    monkeypatch.setattr(run_eval, "RESULTS", tmp_path)
    before = run_eval.DEFAULTS.read_text(encoding="utf-8")
    assert run_eval.main() == 2
    assert run_eval.DEFAULTS.read_text(encoding="utf-8") == before
    assert (
        json.loads(next(tmp_path.glob("classification-dry-*.json")).read_text(encoding="utf-8"))[
            "representative"
        ]
        is False
    )
