"""Nạp sẵn trước snapshot của Runtime V2 (#39, lỗi 4 của báo cáo NN).

Ca thật (Runtime v32, 26/11): "Chào bạn" ở hội thoại mới chờ khoảng 15 giây (đúng trần chờ làm nóng `WARMUP_WAIT_MS` của frontend). Log
của phiên `b05ddc85…` có lượt làm nóng lúc 09:31:18.69 rồi tới 09:31:35.88 mới có lượt chat; lượt chat đó còn mất 1,1 giây trước bước
router (phiên nhanh: 30 ms), tức việc làm nóng chưa xong sau 17 giây. Runtime V2 khởi động mỗi phiên bằng cách khôi phục snapshot chụp
ngay sau khi `/ping` đạt; tệp trong snapshot đọc lần đầu ở mỗi phiên thì chậm (tài liệu AWS "Optimize your agent for AgentCore Runtime
V2"). Agent lại import Strands, MCP, boto3 và nạp mô hình dịch vụ của botocore trong lượt làm nóng của từng phiên (sau khi khôi phục),
nên phiên nào cũng đọc lại hàng trăm tệp đó. Việc này phải làm MỘT lần lúc tiến trình khởi động, trước khi nghe cổng 8080 (trước
snapshot), không gọi mạng và không đọc dữ liệu có thể đổi.
"""

from __future__ import annotations

import json
import logging
import runpy
import sys
from pathlib import Path

import pytest
from test_app import SpyQuota, warm_runtime
from yofina_agent import app as app_module

MAIN = Path(__file__).resolve().parents[3] / "agent" / "main.py"


def test_preload_nap_thu_vien_va_mo_hinh_dich_vu_khong_goi_mang(monkeypatch):
    monkeypatch.setenv("YOFINA_REGION", "ap-southeast-1")
    calls: list[str] = []
    import botocore.endpoint

    monkeypatch.setattr(botocore.endpoint.Endpoint, "make_request", lambda *a, **k: calls.append("network"))
    info = app_module.preload()
    assert set(info["services"]) == set(app_module.PRELOAD_SERVICES)
    assert {"bedrock-runtime", "dynamodb", "ssm", "bedrock-agentcore"} <= set(app_module.PRELOAD_SERVICES)
    assert "strands" in sys.modules and "strands.tools.mcp" in sys.modules
    assert isinstance(info["ms"], int) and calls == []
    # mô hình dịch vụ nằm trong bộ nạp của phiên boto3 mặc định (phiên mà mọi `boto3.client(...)` của agent dùng)
    import boto3

    loader = boto3.DEFAULT_SESSION._session.get_component("data_loader")
    for name in app_module.PRELOAD_SERVICES:
        assert loader.load_service_model(name, "service-2") is not None


def test_preload_khong_co_region_thi_van_import_va_ghi_log(monkeypatch, caplog):
    monkeypatch.delenv("YOFINA_REGION", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    with caplog.at_level(logging.INFO, logger="yofina.agent.app"):
        info = app_module.preload()
    assert info["services"] == [] and "strands" in sys.modules
    assert any('"event": "preload"' in r.getMessage() for r in caplog.records)


def test_main_nap_san_truoc_khi_nghe_cong(monkeypatch):
    order: list[str] = []
    monkeypatch.setattr(app_module, "preload", lambda: order.append("preload") or {"services": [], "ms": 0})
    monkeypatch.setattr(logging, "basicConfig", lambda **_k: None)  # không thay handler của pytest
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: order.append("listen"))
    runpy.run_path(str(MAIN), run_name="__main__")
    assert order == ["preload", "listen"]


def test_warm_ghi_log_thoi_gian(caplog):
    with caplog.at_level(logging.INFO, logger="yofina.agent.app"):
        info = warm_runtime(lambda: SpyQuota()).warm()
    events = [json.loads(r.getMessage()) for r in caplog.records if r.getMessage().startswith("{")]
    done = [e for e in events if e.get("event") == "warm_done"]
    assert len(done) == 1 and done[0]["ms"] == info["ms"] and done[0]["quota"] is True


@pytest.fixture(autouse=True)
def _restore_logging():
    # runpy chạy `configure_logging` của main.py (đặt mức log cho vài logger): trả lại như cũ cho các test sau
    names = ("strands", "botocore", "urllib3", "httpx", "httpcore", "mcp")
    levels = {n: logging.getLogger(n).level for n in names}
    yield
    for n, level in levels.items():
        logging.getLogger(n).setLevel(level)
