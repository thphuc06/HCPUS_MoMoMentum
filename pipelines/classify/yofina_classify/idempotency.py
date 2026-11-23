"""Idempotency theo id sự kiện bằng DynamoDB (EventBridge và SQS giao ÍT NHẤT MỘT LẦN), đặt quanh bước tốn tiền (embedding, model nhỏ).

Cùng ngữ nghĩa với `yofina_forecast.idempotency` (claim có khóa thuê, `done`, `release`) nhưng là bảng RIÊNG của Lambda phân loại, và khóa có tiền tố
`classify:` nên dùng chung bảng với thứ khác cũng không đè nhau (id sự kiện `transaction.recorded` là id giao dịch, mà dự báo cũng dùng).
Lớp thứ hai là trạng thái nghiệp vụ: giao dịch đã ra khỏi Chưa phân loại thì lần giao lại bị bỏ qua (`service.ClassifyService.run`).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any

log = logging.getLogger("yofina.classify.idempotency")
KEY_PREFIX = "classify:"


class Claim(StrEnum):
    CLAIMED = "claimed"
    DUPLICATE = "duplicate"
    BUSY = "busy"


class IdempotencyStore:
    def __init__(
        self,
        table: str,
        client: Any = None,
        *,
        ttl_seconds: int,
        lease_seconds: int,
        region: str | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.table, self._client, self._region = table, client, region
        self.ttl_seconds, self.lease_seconds, self._clock = ttl_seconds, lease_seconds, clock

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("dynamodb", region_name=self._region)
        return self._client

    @staticmethod
    def _failed_condition(exc: Exception) -> bool:
        return (
            getattr(exc, "response", {}).get("Error", {}).get("Code")
            == "ConditionalCheckFailedException"
        )

    def _key(self, event_id: str) -> dict[str, Any]:
        return {"event_id": {"S": KEY_PREFIX + event_id}}

    def claim(self, event_id: str, *, user_id: str | None = None) -> Claim:
        now = int(self._clock())
        item: dict[str, Any] = {
            **self._key(event_id),
            "status": {"S": "in_progress"},
            "lease_until": {"N": str(now + self.lease_seconds)},
            "ttl": {"N": str(now + self.ttl_seconds)},
        }
        if user_id:
            item["user_id"] = {"S": user_id}
        try:
            self.client.put_item(
                TableName=self.table,
                Item=item,
                ConditionExpression="attribute_not_exists(event_id) OR (#s = :ip AND lease_until < :now)",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":ip": {"S": "in_progress"}, ":now": {"N": str(now)}},
            )
            return Claim.CLAIMED
        except Exception as exc:
            if not self._failed_condition(exc):
                raise
        got = self.client.get_item(
            TableName=self.table, Key=self._key(event_id), ConsistentRead=True
        ).get("Item")
        if got and got.get("status", {}).get("S") == "done":
            return Claim.DUPLICATE
        if not got:  # bị nhả giữa hai lệnh: thử giành lại một lần
            return self.claim(event_id, user_id=user_id)
        return Claim.BUSY

    def complete(self, event_id: str) -> None:
        now = int(self._clock())
        self.client.update_item(
            TableName=self.table,
            Key=self._key(event_id),
            UpdateExpression="SET #s = :done, #t = :ttl REMOVE lease_until",
            ExpressionAttributeNames={"#s": "status", "#t": "ttl"},
            ExpressionAttributeValues={
                ":done": {"S": "done"},
                ":ttl": {"N": str(now + self.ttl_seconds)},
            },
        )

    def release(self, event_id: str) -> None:
        """Nhả khóa của lần xử lý thất bại để lần giao lại được xử lý; không bao giờ xóa mục đã `done`."""
        try:
            self.client.delete_item(
                TableName=self.table,
                Key=self._key(event_id),
                ConditionExpression="#s = :ip",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":ip": {"S": "in_progress"}},
            )
        except Exception as exc:
            if not self._failed_condition(exc):
                log.warning("release idempotency thất bại: %r", exc)
