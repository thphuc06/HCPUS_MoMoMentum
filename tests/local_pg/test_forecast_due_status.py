"""Trạng thái dự báo không tự mâu thuẫn với danh sách khoản đến hạn trước lương (#39, việc nối 3; KK "điểm còn nghi"), engine thật trên
PostgreSQL cục bộ.

Ví demo của `minh` (ngày mô phỏng 21/11/2026, lương ngày 5): hũ Nghĩa vụ trả Tiền điện 26/11 và Trả sau đúng ngày lương 05/12; trước khi
lương về hũ chỉ dư khoảng 31.608 ₫. Chuyển bớt 100.000 ₫ sang hũ Dự phòng thì khoản Trả sau 05/12 thiếu tiền (trả bằng số dư trước khi
lương về, BR-22) trong khi xác suất hụt của engine (chỉ xét các ngày trước ngày lương) vẫn thấy "đủ". Lần dự báo thường ghi trạng thái hụt
(`yofina_forecast.due_status`), nên khối dự báo, Tổng quan (chip trạng thái của hũ đọc ở đây) và bản gọn cho agent (đọc khối dự báo) cùng
nói hụt, không hiện xác suất của engine. Không gọi AWS, không gọi model.

    uv run --python 3.12 --no-project --with pgserver --with "psycopg[binary]" --with pydantic --with pytest --with jsonschema \
        --with pyyaml --with referencing --with numpy --with boto3 --with scipy --with ruptures \
        pytest tests/local_pg/test_forecast_due_status.py -p no:cacheprovider -s
"""

from __future__ import annotations

from datetime import timedelta

from test_demo_scenes import USER, _pipeline, _reset_demo

PAY_JAR = "nghia_vu"
PAYDAY = "2026-12-05"


def _nghia_vu(env) -> tuple[dict, dict, dict]:
    """(tóm tắt đã ghi, khối dự báo, hũ trên Tổng quan) của hũ Nghĩa vụ."""
    (summary,) = [r for r in env.repo.forecast_summaries(USER) if r["jar_code"] == PAY_JAR]
    block = env.svc.forecast_block_or_none(USER, PAY_JAR, trace_id="tt-due", source_tool="test")
    assert block is not None
    (jar,) = [j for j in env.svc.overview_response(USER)["jars"] if j["code"] == PAY_JAR]
    return summary, block.model_dump(mode="json", exclude_none=True), jar


def test_khoan_dung_ngay_luong_thieu_tien_thi_moi_noi_hien_hut(env):
    p = _pipeline(env)
    _reset_demo(env, p)
    summary, block, jar = _nghia_vu(env)
    window = block["data"]["obligations_before_payday"]
    print("\n[trước] trạng thái", summary["status"], "| Tổng quan", jar.get("status"), "| danh sách", window)
    assert summary["status"] == "ok" and "first_shortfall" not in window

    env.act(USER, "move_between_jars", {"from_jar": PAY_JAR, "to_jar": "du_phong", "amount_vnd": 100_000})
    # đồng hồ test đứng yên: hai lần chạy cùng computed_at thì "mới nhất" (computed_at DESC, id DESC) rơi vào run_id uuid4 ngẫu nhiên,
    # nửa số lần đọc lại lần chạy lúc đặt lại; đẩy đồng hồ thêm một giây để lần chạy sau khi chuyển chắc chắn là lần mới nhất
    env.clock.now += timedelta(seconds=1)
    run = p.run_user(USER, trigger="manual")
    assert run.status == "ok"
    summary, block, jar = _nghia_vu(env)
    assert str(summary["run_id"]) == run.run_id
    data = block["data"]
    window = data["obligations_before_payday"]
    print("[sau khi chuyển 100.000 ₫] trạng thái", summary["status"], "| Tổng quan", jar.get("status"), "| danh sách", window)
    print("  câu thay thế:", block["fallback_text"])
    short = window["first_shortfall"]
    assert short["date"] == PAYDAY and short["shortfall_vnd"] > 0
    # cùng một trạng thái ở tóm tắt đã ghi, khối dự báo và Tổng quan; không hiện xác suất "trước kỳ lương" của engine
    assert summary["status"] == data["status"] == jar["status"] == "short"
    assert not summary["show_probability"] and "p_shortfall" not in data and "p_shortfall" not in jar
    assert "đủ tới kỳ lương" not in block["fallback_text"] and "thiếu" in block["fallback_text"]
