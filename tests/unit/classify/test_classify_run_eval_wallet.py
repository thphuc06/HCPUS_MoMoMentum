"""Bộ kiểm phân hũ chọn ví (`evals/classification/run_eval.py --wallet multi|three`, issue #39): ví 3 hũ đưa đúng 3 hũ vào lời nhắn,
nhãn ánh xạ qua quy tắc sản phẩm (`scripts/measure_three_jars.py`), đệm model riêng theo ví, ước tính số lời gọi và chi phí trước khi
chạy, chạy tiếp được khi đứt, `--limit`. Model và embedding GIẢ; không AWS, không Bedrock, không ghi vào `results/` của repo."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import classify_helpers  # noqa: F401  (đặt đường nhập cho pipelines/classify, evals/classification)
import pytest
from yofina_classify.model import Verdict

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "evals" / "classification"))

import fakes  # noqa: E402
import run_eval  # noqa: E402
import sim  # noqa: E402

THREE = [
    "chi_hang_ngay",
    "nghia_vu",
    "du_phong",
]  # bộ hũ mặc định của tài khoản mới (migration 0059)


class FakeJudge:
    """Model nhỏ GIẢ: chọn hũ chi tiêu đầu tiên của danh sách trong lời nhắn; ghi lại lời nhắn đã nhận. `fail_after`: lời gọi thứ
    `fail_after + 1` ném lỗi như mạng đứt giữa chừng."""

    def __init__(self, fail_after: int | None = None) -> None:
        self.prompts: list[str] = []
        self.fail_after = fail_after

    def __call__(self, prompt: str, jars) -> Verdict:
        if self.fail_after is not None and len(self.prompts) >= self.fail_after:
            raise ConnectionError("mạng đứt (giả)")
        self.prompts.append(prompt)
        spending = [h["ma"] for h in json.loads(prompt)["hu"] if h["loai"] == "spending"]
        return Verdict(spending[0] if spending and spending[0] in jars else None, 0.7)


@pytest.fixture
def results(tmp_path, monkeypatch):
    """Đệm và báo cáo ghi vào thư mục tạm (đệm đã commit của repo không bị chạm); cổng Bedrock thay bằng bản giả."""
    monkeypatch.setattr(run_eval, "RESULTS", tmp_path)
    monkeypatch.setattr(run_eval, "EMB_CACHE", tmp_path / "embedding_cache.json")
    monkeypatch.setattr(run_eval, "LLM_CACHE", tmp_path / "llm_cache.json")
    judge = FakeJudge()

    def live():
        return fakes.HashingEmbedder(), judge, fakes.MODEL_ID

    monkeypatch.setattr(run_eval, "live_backends", live)
    return tmp_path, judge


def main(monkeypatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["run_eval.py", *argv])
    return run_eval.main()


def prompt_jars(prompt: str) -> list[str]:
    return [h["ma"] for h in json.loads(prompt)["hu"]]


def test_vi_ba_hu_dung_bo_hu_va_quy_tac_anh_xa_cua_san_pham():
    from yofina_core.wallet import transaction_jar

    three = run_eval.wallet_setup("three")
    rows7 = [r for r in sim.load_dataset() if r["seq"] < 10]
    rows3 = three.rows(rows7)
    assert list(three.jars("minh")) == THREE
    for r7, r3 in zip(rows7, rows3, strict=True):
        assert r3["truth_jar"] == transaction_jar(r7["truth_jar"], THREE, tx_type=r7["tx_type"])
    # nhãn seed đổi mã theo cùng quy tắc; chế độ none là tài khoản mới không có nhãn seed
    seeds = three.seeds("minh", THREE)
    assert seeds and {j for _, j in seeds} <= set(THREE)
    assert run_eval.wallet_setup("three", seed_labels="none").seeds("minh", THREE) == []
    multi = run_eval.wallet_setup("multi")
    assert multi.rows(rows7) == rows7 and multi.seeds is None
    assert list(multi.jars("minh")) == list(sim.persona_jars("minh"))


def test_loi_nhan_model_chi_chua_hu_cua_vi_dang_do():
    from yofina_ledger import classify_config

    th = classify_config.load_thresholds()
    rows = [r for r in sim.load_dataset() if r["seq"] < 6]
    emb = sim.CachedEmbedder(sim.Caches(), "x", fakes.HashingEmbedder())
    three = run_eval.wallet_setup("three")
    prompts3 = sim.warm_prompts(three.rows(rows), th, emb, jars_of=three.jars)
    assert prompts3 and all(prompt_jars(p) == THREE for p in prompts3)
    prompts7 = sim.warm_prompts(rows, th, emb)
    persona_wallets = [list(sim.persona_jars(p)) for p in ("minh", "lan", "khoa")]
    assert prompts7 and all(prompt_jars(p) in persona_wallets for p in prompts7)
    assert {sim.prompt_key(p) for p in prompts3}.isdisjoint(
        sim.prompt_key(p) for p in prompts7
    )  # khóa đệm khác nhau


def test_chi_dong_buoc_0_khong_xep_duoc_moi_can_model_tren_moi_vi():
    """Như `Classifier.classify` bước 0: loại giao dịch có hũ qua `transaction_jar` (kể cả hũ chung của ví 3 hũ) thì không tới model,
    nên không nằm trong bộ thông điệp cần gọi (ước tính và `warm` không gọi thừa)."""
    from yofina_core.wallet import transaction_jar
    from yofina_ledger import classify_config

    th = classify_config.load_thresholds()
    types = sim.load_type_map()
    emb = sim.CachedEmbedder(sim.Caches(), "x", fakes.HashingEmbedder())
    rows = sim.load_dataset()
    for name in ("multi", "three"):
        setup = run_eval.wallet_setup(name)
        rs = setup.rows(rows)

        def routed(r, setup=setup):
            info = types.get(r["tx_type"])
            jars = setup.jars(r["persona"], ())
            return (
                info is not None
                and info.direction == "out"
                and transaction_jar(info.default_jar_code, jars, tx_type=r["tx_type"])
            )

        want = sum(1 for r in rs if not routed(r))
        assert len(sim.warm_prompts(rs, th, emb, jars_of=setup.jars)) == want, name
        assert 0 < want < len(rs), name


def test_dem_model_rieng_theo_vi():
    assert run_eval.llm_cache_path("multi") == run_eval.LLM_CACHE
    three = run_eval.llm_cache_path("three")
    assert three != run_eval.LLM_CACHE and three.parent == run_eval.LLM_CACHE.parent


def test_uoc_tinh_so_loi_goi_va_chi_phi():
    est = run_eval.estimate(["x" * 300, "y" * 600], embed_texts=["a"] * 100)
    assert est["llm_calls"] == 2 and est["llm_calls_max_with_retry"] == 4
    assert est["embed_calls"] == 2  # gom lô 96
    assert est["input_tokens"] == pytest.approx(
        (2 * len(run_eval.JUDGE_SYSTEM) + 900) / run_eval.CHARS_PER_TOKEN, abs=1
    )
    assert est["output_tokens_max"] == 2 * run_eval.JUDGE_MAX_OUTPUT_TOKENS
    assert est["cost_usd_max"] > 0 and est["minutes"] > 0
    assert run_eval.estimate([], embed_texts=[])["cost_usd_max"] == 0


def test_che_do_dem_vi_ba_hu_in_uoc_tinh_roi_dung_khong_goi_model(results, monkeypatch, capsys):
    tmp, judge = results
    assert main(monkeypatch, "run", "--mode", "cache", "--wallet", "three", "--limit", "4") == 3
    out = capsys.readouterr().out
    assert "ước tính" in out and "lời gọi model nhỏ" in out
    assert judge.prompts == []
    assert not (tmp / "llm_cache_three.json").exists()


def test_warm_vi_ba_hu_dut_giua_chung_roi_chay_tiep_khong_goi_lai(results, monkeypatch, capsys):
    tmp, judge = results
    monkeypatch.setattr(run_eval, "SAVE_EVERY", 1)
    judge.fail_after = 3
    with pytest.raises(ConnectionError):
        main(monkeypatch, "warm", "--wallet", "three", "--limit", "5")
    out = capsys.readouterr().out
    assert "ước tính" in out  # in trước khi gọi
    saved = json.loads((tmp / "llm_cache_three.json").read_text(encoding="utf-8"))["verdicts"]
    assert (
        len(saved) == 3 and not (tmp / "llm_cache.json").exists()
    )  # đệm của ví nhiều hũ không bị chạm
    first = list(judge.prompts)
    judge.fail_after = None
    assert main(monkeypatch, "warm", "--wallet", "three", "--limit", "5") == 0
    again = judge.prompts[len(first) :]
    assert again and set(again).isdisjoint(first)  # không gọi lại thông điệp đã có đệm
    total = json.loads((tmp / "llm_cache_three.json").read_text(encoding="utf-8"))["verdicts"]
    assert len(total) == len(first) + len(again)
    assert all(prompt_jars(p) == THREE for p in judge.prompts)
    judge.prompts.clear()
    assert (
        main(monkeypatch, "warm", "--wallet", "three", "--limit", "5") == 0 and judge.prompts == []
    )


def test_limit_lay_n_dong_dau_moi_persona(results, monkeypatch):
    tmp, judge = results
    assert main(monkeypatch, "warm", "--wallet", "three", "--limit", "2") == 0
    small = len(judge.prompts)
    judge.prompts.clear()
    (tmp / "llm_cache_three.json").unlink()
    assert main(monkeypatch, "warm", "--wallet", "three", "--limit", "6") == 0
    assert 0 < small < len(judge.prompts)


def test_run_live_vi_ba_hu_bao_cao_chi_hu_cua_vi(results, monkeypatch):
    tmp, judge = results
    out = tmp / "rep.json"
    assert (
        main(
            monkeypatch,
            "run",
            "--mode",
            "live",
            "--wallet",
            "three",
            "--limit",
            "8",
            "--out",
            str(out),
        )
        == 0
    )
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert (
        rep["wallet"] == "three"
        and rep["seed_labels"] == "mapped"
        and rep["llm_cache"] == "llm_cache_three.json"
    )
    assert set(rep["confusion_test"]) <= set(THREE)
    assert {k for row in rep["confusion_test"].values() for k in row} <= {*THREE, "HOI"}
    assert rep["llm_errors"] == {} and rep["llm_calls_this_run"] > 0
    assert rep["wallet_jars"] and [j["code"] for j in rep["wallet_jars"]] == THREE
    # lấp nốt đệm bằng warm (bộ thông điệp đủ, kể cả dòng mà lượt run không cần model) rồi chấm ở chế độ chỉ đệm: cùng số, không gọi gì
    assert main(monkeypatch, "warm", "--wallet", "three", "--limit", "8") == 0
    judge.prompts.clear()
    again = tmp / "rep2.json"
    assert (
        main(
            monkeypatch,
            "run",
            "--mode",
            "cache",
            "--wallet",
            "three",
            "--limit",
            "8",
            "--out",
            str(again),
        )
        == 0
    )
    rep2 = json.loads(again.read_text(encoding="utf-8"))
    assert rep2["test_split"] == rep["test_split"] and judge.prompts == []


def test_vi_ba_hu_khong_hieu_chinh_nguong(results, monkeypatch):
    before = run_eval.DEFAULTS.read_text(encoding="utf-8")
    assert main(monkeypatch, "calibrate", "--mode", "dry", "--wallet", "three", "--limit", "4") == 2
    assert run_eval.DEFAULTS.read_text(encoding="utf-8") == before
