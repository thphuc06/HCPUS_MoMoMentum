"""Hợp đồng ML <-> pipeline: kiểu dữ liệu `yofina_ml.types`, JSON Schema `contracts/ml/forecast_io.schema.json`,
fixture dùng chung, bộ kiểm bất biến `yofina_ml.contract`, và khớp với DB và khối `forecast_timeline`."""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import replace
from datetime import date, timedelta

import pytest
from conftest import BASE, CONTRACTS, REPO, load_json
from jsonschema import Draft202012Validator

from yofina_ml import contract, serde
from yofina_ml.api import forecast_user, update_forecast
from yofina_ml.types import (
    DayQuantiles,
    ForecastConfig,
    ForecastInputs,
    ForecastResult,
    JarForecast,
    JarSummary,
    RunMeta,
)

FIX = CONTRACTS / "fixtures" / "ml"
INPUT_FILES = sorted(FIX.glob("forecast_inputs.*.json"))
RESULT_FILES = sorted(FIX.glob("forecast_result.*.json"))
MIGRATION_0006 = (REPO / "db" / "migrations" / "0006_forecast.sql").read_text(encoding="utf-8")


def validator(registry, name):
    return Draft202012Validator(
        {"$ref": f"{BASE}/ml/forecast_io.schema.json#/$defs/{name}"}, registry=registry
    )


def pair(case: str):
    inputs = serde.forecast_inputs_from_dict(load_json(FIX / f"forecast_inputs.{case}.json"))
    result = serde.forecast_result_from_dict(load_json(FIX / f"forecast_result.{case}.json"))
    return inputs, result


# --- JSON Schema và fixture ------------------------------------------------------------------
@pytest.mark.parametrize("path", INPUT_FILES, ids=lambda p: p.name)
def test_fixture_dau_vao_hop_le_va_khu_hoi_khong_doi(registry, path):
    obj = load_json(path)
    assert list(validator(registry, "ForecastInputs").iter_errors(obj)) == []
    assert serde.forecast_inputs_to_dict(serde.forecast_inputs_from_dict(obj)) == obj


@pytest.mark.parametrize("path", RESULT_FILES, ids=lambda p: p.name)
def test_fixture_dau_ra_hop_le_va_khu_hoi_khong_doi(registry, path):
    obj = load_json(path)
    assert list(validator(registry, "ForecastResult").iter_errors(obj)) == []
    assert serde.forecast_result_to_dict(serde.forecast_result_from_dict(obj)) == obj


@pytest.mark.parametrize("path", sorted((FIX / "invalid").glob("*.json")), ids=lambda p: p.name)
def test_fixture_sai_bi_tu_choi(registry, path):
    name = "ForecastInputs" if path.name.startswith("forecast_inputs") else "ForecastResult"
    assert not validator(registry, name).is_valid(load_json(path))


@pytest.mark.parametrize("case", ["default", "cold_start"])
def test_fixture_cap_vao_ra_thoa_bo_kiem_hop_dong(case):
    inputs, result = pair(case)
    assert contract.check_inputs(inputs) == []
    assert contract.check_result(inputs, result) == []


def test_ca_khoi_dau_lanh_la_uoc_luong_ban_dau_khong_phat_xac_suat():
    inputs, result = pair("cold_start")
    assert inputs.config.cold_start_min_days > max(j.history_days for j in inputs.jars)
    assert result.run.is_initial_estimate and result.run.confidence_label == "low"
    assert result.run.data_coverage is None  # lương đã nhận bằng 0: không tính được độ phủ
    for jf in result.jars:
        assert jf.summary.p_shortfall is None and not jf.summary.show_probability
        assert jf.summary.series_kind == "cold_start"


# --- ánh xạ sang bảng DB (không lệch cột) -----------------------------------------------------
def table_columns(table: str) -> set[str]:
    m = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", MIGRATION_0006, re.S)
    assert m, table
    cols = set()
    for line in m.group(1).splitlines():
        mm = re.match(
            r"\s{2}([a-z_0-9]+)\s+(uuid|text|date|smallint|integer|bigint|numeric|boolean|timestamptz|jsonb)",
            line,
        )
        if mm:
            cols.add(mm.group(1))
    return cols


def field_names(cls) -> set[str]:
    return {f.name for f in dataclasses.fields(cls)}


def test_cot_cua_forecasts_la_day_quantiles_cong_khoa():
    cols = table_columns("forecasts")
    assert cols == {"run_id", "user_id", "jar_code", "day"} | (field_names(DayQuantiles) - {"date"})


def test_cot_cua_forecast_jar_summaries_la_jar_summary_cong_khoa_chay():
    cols = table_columns("forecast_jar_summaries")
    assert cols == {"run_id", "user_id"} | field_names(JarSummary)


def test_cot_cua_forecast_runs_phan_ml_quyet_dinh_la_run_meta():
    cols = table_columns("forecast_runs")
    pipeline_adds = {"id", "user_id", "computed_at", "trigger", "parent_run_id", "source_event_id"}
    assert cols == pipeline_adds | field_names(RunMeta)


def test_khop_khoi_forecast_timeline_o_truong_dung_chung():
    block = load_json(CONTRACTS / "fixtures/blocks/valid/forecast_timeline.short.json")["data"]
    summary = {"status", "confidence_band", "runout_date", "p_shortfall", "p_shortfall_se"}
    assert summary <= set(block)  # cùng tên với JarSummary
    assert summary <= field_names(JarSummary)
    assert {"model", "history_days", "is_initial_estimate"} <= set(block)
    assert {"model", "history_days", "is_initial_estimate"} <= field_names(RunMeta)
    day = block["days"][0]
    assert set(day) == {
        "date",
        "p10_vnd",
        "p50_vnd",
        "p90_vnd",
    }  # số dư P10/P50/P90 của DayQuantiles


# --- giao diện hàm ---------------------------------------------------------------------------
def test_ham_cong_khai_chay_va_dat_bo_kiem_hop_dong():
    """Từ phase 2 luồng B hai hàm đã cài: đầu ra qua bộ kiểm bất biến (kiểm kỹ ở tests/unit/ml/)."""
    inputs, _ = pair("default")
    result = forecast_user(inputs)
    assert contract.check_result(inputs, result) == []
    updated = update_forecast(inputs, result, ["an_uong"])
    assert contract.check_result(inputs, updated, subset=True) == []


def test_goi_ml_chi_phu_thuoc_thu_vien_chuan_trong_types_va_serde():
    for name in ("types.py", "serde.py", "contract.py"):
        text = (REPO / "ml" / "yofina_ml" / name).read_text(encoding="utf-8")
        assert not re.search(
            r"^\s*(import|from)\s+(numpy|scipy|boto3|pydantic|yofina_core)", text, re.M
        ), name
        assert "date.today(" not in text and "datetime.now(" not in text  # ADR-0003


# --- bộ kiểm có bắt được vi phạm (kiểm chính bộ kiểm) -----------------------------------------
def _mutate_first_jar(result: ForecastResult, **summary_changes) -> ForecastResult:
    first = result.jars[0]
    return replace(
        result,
        jars=(JarForecast(replace(first.summary, **summary_changes), first.days), *result.jars[1:]),
    )


def test_bo_kiem_bat_xac_suat_khi_chua_du_tin_cay():
    inputs, result = pair("default")
    bad = _mutate_first_jar(result, p_shortfall=0.4, show_probability=True)
    errs = contract.check_result(inputs, bad)
    assert any("probability_enabled" in e for e in errs)
    ok_cfg = replace(inputs, config=replace(inputs.config, probability_enabled=True))
    assert (
        contract.check_result(
            ok_cfg,
            _mutate_first_jar(result, p_shortfall=0.3, show_probability=True, status="tight"),
        )
        == []
    )


def test_bo_kiem_bat_phan_tram_thay_vi_ty_le_va_status_lech_nguong():
    inputs, result = pair("default")
    cfg = replace(inputs, config=replace(inputs.config, probability_enabled=True))
    errs = contract.check_result(
        cfg, _mutate_first_jar(result, p_shortfall=71.0, show_probability=True)
    )
    assert any("tỷ lệ 0..1" in e for e in errs)
    errs = contract.check_result(
        cfg, _mutate_first_jar(result, p_shortfall=0.8, show_probability=True, status="ok")
    )
    assert any("không khớp ngưỡng" in e for e in errs)


def test_bo_kiem_bat_thieu_ngay_va_phan_vi_dao_nguoc():
    inputs, result = pair("default")
    first = result.jars[0]
    short = replace(result, jars=(JarForecast(first.summary, first.days[:-1]), *result.jars[1:]))
    assert any("horizon_days dòng" in e for e in contract.check_result(inputs, short))
    d0 = first.days[0]
    swapped = replace(d0, balance_p10_vnd=d0.balance_p90_vnd + 1)
    bad = replace(
        result, jars=(JarForecast(first.summary, (swapped, *first.days[1:])), *result.jars[1:])
    )
    assert any("phân vị số dư" in e for e in contract.check_result(inputs, bad))
    skipped = replace(first.days[1], date=first.days[1].date + timedelta(days=1))
    bad2 = replace(
        result,
        jars=(
            JarForecast(first.summary, (first.days[0], skipped, *first.days[2:])),
            *result.jars[1:],
        ),
    )
    assert any("ngày thứ 2" in e for e in contract.check_result(inputs, bad2))


def test_bo_kiem_bat_sai_thu_tu_hu_va_uoc_luong_ban_dau():
    inputs, result = pair("default")
    reordered = replace(result, jars=tuple(reversed(result.jars)))
    assert any("cùng thứ tự" in e for e in contract.check_result(inputs, reordered))
    assert (
        contract.check_result(inputs, reordered, subset=True) == []
    )  # kết quả cục bộ thì thứ tự tùy ý
    cold_in, cold_res = pair("cold_start")
    wrong = replace(cold_res, run=replace(cold_res.run, is_initial_estimate=False))
    assert any("is_initial_estimate" in e for e in contract.check_result(cold_in, wrong))


def test_bo_kiem_dau_vao_bat_lich_su_thung_va_moc_ngoai_horizon():
    inputs, _ = pair("default")
    jar = inputs.jars[0]
    short_history = replace(jar, daily_spend_vnd=jar.daily_spend_vnd[:-1])
    errs = contract.check_inputs(replace(inputs, jars=(short_history, *inputs.jars[1:])))
    assert any("app_date - 1" in e for e in errs)
    far = replace(jar.inflows[0], date=inputs.app_date + timedelta(days=60))
    errs = contract.check_inputs(
        replace(inputs, jars=(replace(jar, inflows=(far,)), *inputs.jars[1:]))
    )
    assert any("ngoài horizon" in e for e in errs)
    assert any(
        "payday_dates" in e
        for e in contract.check_inputs(replace(inputs, payday_dates=(date(2027, 1, 5),)))
    )
    assert any(
        "tăng dần" in e or "hũ" in e
        for e in contract.check_inputs(replace(inputs, jars=(jar, jar)))
    )


def test_config_mac_dinh_khop_schema_va_serde_tu_choi_truong_la():
    assert set(dataclasses.asdict(ForecastConfig())) == set(
        load_json(CONTRACTS / "ml/forecast_io.schema.json")["$defs"]["ForecastConfig"]["properties"]
    )
    with pytest.raises(KeyError):
        serde.forecast_config_from_dict({"n_paths": 100, "khong_co": 1})


def test_inputs_la_dataclass_bat_bien():
    inputs, _ = pair("default")
    with pytest.raises(dataclasses.FrozenInstanceError):
        inputs.horizon_days = 99  # type: ignore[misc]
    assert isinstance(inputs, ForecastInputs) and json.dumps(serde.forecast_inputs_to_dict(inputs))
