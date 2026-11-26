"""Script đo ví 3 hũ (`scripts/measure_three_jars.py`, issue #39): ánh xạ hũ theo quy tắc sản phẩm, bộ dữ liệu nhãn đổi đáp án, mô phỏng
phân loại không gọi model, hũ gộp của bộ sinh dự báo và chuỗi gộp của PELT. Chạy offline, không AWS."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
THREE = ("chi_hang_ngay", "nghia_vu", "du_phong")


@pytest.fixture(scope="module")
def m3():
    """Script nạp từ đường dẫn; trả `sys.path` và các module script nạp kèm về như cũ khi xong (như `test_scene4_statement`)."""
    saved_path, before = list(sys.path), set(sys.modules)
    spec = importlib.util.spec_from_file_location(
        "measure_three_jars", REPO / "scripts" / "measure_three_jars.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.path[:] = saved_path
        for name in (
            "measure_three_jars",
            "measure_scene4_pelt",
            "inject_behavior_shift",
            "sim",
            "run_eval",
            "build_dataset",
            "build_seed_labels",
        ):
            if name not in before:
                sys.modules.pop(name, None)


def test_vi_ba_hu_doc_tu_migration_0059(m3):
    assert m3.onboarding_layout() == [
        ("chi_hang_ngay", "Chi hằng ngày", "spending"),
        ("nghia_vu", "Nghĩa vụ", "obligation"),
        ("du_phong", "Dự phòng", "saving"),
    ]


def test_anh_xa_hu_cu_sang_vi_ba_hu_theo_transaction_jar(m3):
    for code in ("an_uong", "di_lai", "giai_tri", "du_lich"):
        assert m3.to_layout(code, THREE) == "chi_hang_ngay"
    assert m3.to_layout("hoa_don", THREE) == "nghia_vu"
    assert m3.to_layout("giai_tri", THREE, "subscription") == "nghia_vu"
    assert m3.to_layout("du_phong", THREE) == "du_phong"
    assert m3.to_layout(None, THREE) is None


def test_buoc_0_tren_vi_ba_hu_chi_bon_loai_khong_co_hu(m3):
    import sim

    routes = m3.type_routes(sim.load_type_map(), {"ba_hu": list(THREE)})
    unrouted = {r["tx_type"] for r in routes if r["ba_hu"] is None}
    assert unrouted == {"bnpl_purchase", "transfer_person", "qr_other", "other_expense"}
    assert all(r["ba_hu"] in THREE for r in routes if r["ba_hu"] is not None)


def test_bo_du_lieu_doi_dap_an_sang_ba_hu_va_chi_doi_co_nhat_quan_cua_chuyen_khoan_ten_rieng(m3):
    import sim

    rows = sim.load_dataset()
    new = m3.three_jar_rows(rows, THREE)
    assert {r["truth_jar"] for r in new} <= set(THREE)
    assert all(r["truth_jar_7"] == o["truth_jar"] for r, o in zip(new, rows, strict=True))
    changed = [r for r, o in zip(new, rows, strict=True) if r["consistent"] != o["consistent"]]
    assert changed and all(r["category"] == "person_no_note" and r["consistent"] for r in changed)
    kept = m3.three_jar_rows(rows, THREE, recompute_consistent=False)
    assert all(r["consistent"] == o["consistent"] for r, o in zip(kept, rows, strict=True))


def test_nhan_seed_doi_ma_va_bang_alias_cua_san_pham(m3):
    mapped = m3.seed_labels("minh", THREE, "mapped")
    persona = m3.seed_labels("minh", THREE, "persona")
    assert len(mapped) == len(persona) and {j for _, j in mapped} <= set(THREE)
    alias = m3.seed_labels(
        "minh", THREE, "alias"
    )  # apply_seed_labels(jar_aliases=LEGACY_JAR_ALIASES) bỏ nhãn Ăn uống, Đi lại...
    assert 0 < len(alias) < len(persona) and {j for _, j in alias} <= {"nghia_vu", "du_phong"}
    assert m3.seed_labels("minh", THREE, "none") == []


def test_judge_doi_ma_doi_hu_cua_phan_quyet_bo_bay_va_bo_runner_trung(m3):
    from yofina_core.llm import ModelBudgetExceeded

    jars = dict.fromkeys(THREE)
    judge = m3.RemappedJudge(
        {"k1": {"jar": "an_uong", "conf": 0.7, "runner": "giai_tri"}}, {"r1": "k1"}
    )
    judge.row = {"id": "r1", "tx_type": "qr_other"}
    v = judge("bất kỳ", jars)
    assert (v.jar_code, v.confidence, v.runner_up) == ("chi_hang_ngay", 0.7, None)
    judge.row = {"id": "r2", "tx_type": "qr_other"}
    with pytest.raises(ModelBudgetExceeded):
        judge("bất kỳ", jars)
    with pytest.raises(ModelBudgetExceeded):
        m3.NoModelJudge()("bất kỳ", jars)


def test_mo_phong_ba_hu_khong_goi_model_va_chi_gan_hu_cua_vi(m3):
    import run_eval
    import sim

    from yofina_ledger import classify_config

    rows = [r for r in sim.load_dataset() if r["seq"] < 24]
    rows3 = m3.three_jar_rows(rows, THREE)
    caches = run_eval.load_caches("cache")
    wallet = m3.three_jar_wallet()
    th = classify_config.load_thresholds()

    def run():
        judge = m3.NoModelJudge()
        res = m3.simulate(
            rows3,
            th,
            m3.OfflineEmbedder(caches.embeddings, "đệm"),
            judge,
            wallet=lambda p: dict(wallet),
            seeds=lambda p, codes: m3.seed_labels(p, codes, "mapped"),
        )
        return res, judge

    res, judge = run()
    assert len(res) == len(rows3)
    assert all(r.decision.jar in THREE for r in res if r.decision.assigned)
    assert all(r.decision.stage != "llm" for r in res)
    assert judge.calls > 0  # bước model có được gọi tới, nhưng không có model trả lời
    again, _ = run()
    assert [(r.decision.jar, r.decision.tier) for r in again] == [
        (r.decision.jar, r.decision.tier) for r in res
    ]


def test_hu_gop_cua_bo_sinh_cong_chi_va_so_du_giu_hu_khac(m3):
    from yofina_ml.synth import generate

    p = generate("hurdle_lognormal", "office", 201)
    members = m3.MERGES["gop3"]
    q = m3.merge_persona(p, members)
    merged = q.jar(m3.MERGED_CODE)
    assert np.array_equal(merged.spend, sum(p.jar(c).spend for c in members))
    assert merged.split_percent == sum(p.jar(c).split_percent for c in members)
    assert np.array_equal(q.balances[m3.MERGED_CODE], sum(p.balances[c] for c in members))
    assert [j.code for j in q.jars] == [
        "chi_hang_ngay",
        "mua_sam",
        "du_lich",
        "du_phong",
        "nghia_vu",
    ]
    for j in ("mua_sam", "du_lich", "du_phong", "nghia_vu"):
        assert np.array_equal(q.balances[j], p.balances[j])


def test_gop_hu_khong_doi_du_bao_cua_hu_khong_gop(m3):
    """Hạt Monte Carlo theo mã hũ, độ phủ dữ liệu tính trên tổng ví: hũ không nằm trong nhóm gộp có đúng dự báo như ví hũ riêng."""
    job = ("hurdle_lognormal", "office", 201, "rieng", (120,), 200, 400, True)
    bands_a, scen_a = m3._forecast_job(job)
    bands_b, scen_b = m3._forecast_job((*job[:3], "gop3", *job[4:]))

    def pick(rows, jar):
        return [{k: v for k, v in r.items() if k != "variant"} for r in rows if r["jar"] == jar]

    for jar in ("mua_sam", "du_lich", "du_phong", "nghia_vu"):
        assert pick(bands_a, jar) == pick(bands_b, jar)
    assert pick(scen_a, "mua_sam") == pick(scen_b, "mua_sam")
    assert pick(bands_b, m3.MERGED_CODE) and not pick(bands_a, m3.MERGED_CODE)


def test_chuoi_gop_cua_minh_la_tong_ba_hu_chi_va_tep_canh_4_doc_du(m3):
    msp = m3._load_script("measure_scene4_pelt")
    own, merged = m3.merged_history()
    parts = [msp.persona_history(jar=j, layout="demo").daily for j in m3.DEMO_SPEND_JARS]
    assert np.array_equal(merged.daily, np.sum(parts, axis=0))
    assert np.array_equal(own.daily, parts[0]) and merged.spends == own.spends
    rows = m3.scene4_rows()
    assert len(rows) == 32 and sum(r.amount_vnd for r in rows) == 3_416_000
