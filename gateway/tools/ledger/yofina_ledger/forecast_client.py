"""Gọi Lambda `yofina-forecast-batch` từ ledger (không nhúng engine vào zip ledger).

Vì sao gọi Lambda khác thay vì nhúng lõi pipeline vào ledger: engine cần numpy và scipy (zip khoảng 45 MB nén, 150 MB giải nén,
nhập thư viện vài trăm ms lúc nguội) trong khi ledger là zip 3 MB phục vụ MỌI route đọc và ghi, nên nhúng sẽ làm chậm mọi lần
khởi động nguội của ledger và phình zip. Tách ra thì ledger chỉ trả giá một lần gọi `Invoke` khi thật sự cần tính.

- `compute`: đồng bộ (`RequestResponse`) cho `POST /demo/reset` (mở app là có số) và `GET /forecasts/{jar}` khi dự báo cũ.
- `request`: bắn rồi quên (`Event`) cho `GET /overview` khi dự báo cũ (Tổng quan không được chờ).
Lỗi KHÔNG BAO GIỜ làm hỏng thao tác của người dùng: ghi log và trả False.
"""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger("yofina.ledger.forecast")


class ForecastClient:
    def __init__(
        self,
        function_name: str,
        client: Any = None,
        *,
        region: str | None = None,
        sync_timeout_seconds: float = 22.0,
    ) -> None:
        self.function_name = function_name
        self._client = client
        self._region = region
        self._sync_timeout = sync_timeout_seconds

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3
            from botocore.config import Config as BotoConfig

            self._client = boto3.client(
                "lambda",
                region_name=self._region,
                config=BotoConfig(
                    connect_timeout=3,
                    read_timeout=int(self._sync_timeout),
                    retries={"max_attempts": 1, "mode": "standard"},
                ),
            )
        return self._client

    @staticmethod
    def _payload(user_id: str, trigger: str) -> bytes:
        return json.dumps({"op": "run_user", "user_id": user_id, "trigger": trigger}).encode()

    def compute(self, user_id: str, trigger: str) -> bool:
        """Tính đồng bộ cho một người dùng. True khi lần tính thành công hoặc được bỏ qua vì vừa có bản mới."""
        try:
            resp = self.client.invoke(
                FunctionName=self.function_name,
                InvocationType="RequestResponse",
                Payload=self._payload(user_id, trigger),
            )
            if resp.get("FunctionError"):
                log.warning(json.dumps({"msg": "forecast_compute_failed", "trigger": trigger}))
                return False
            body = json.loads(resp["Payload"].read() or b"{}")
            return body.get("status") in ("ok", "skipped")
        except Exception as exc:
            log.warning(json.dumps({"msg": "forecast_compute_error", "error": type(exc).__name__}))
            return False

    def request(self, user_id: str, trigger: str = "read") -> bool:
        """Kích hoạt tính nền (không chờ). True nếu Lambda nhận yêu cầu."""
        try:
            resp = self.client.invoke(
                FunctionName=self.function_name,
                InvocationType="Event",
                Payload=self._payload(user_id, trigger),
            )
            return int(resp.get("StatusCode", 0)) == 202
        except Exception as exc:
            log.warning(json.dumps({"msg": "forecast_request_error", "error": type(exc).__name__}))
            return False
