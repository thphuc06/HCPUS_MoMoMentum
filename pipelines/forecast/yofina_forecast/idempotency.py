"""Idempotency theo `event_id` bằng DynamoDB (contracts/README.md, mục "Sự kiện": EventBridge và SQS giao ÍT NHẤT MỘT LẦN).

Mỗi sự kiện đi qua ba trạng thái trong bảng `yofina-idempotency` (khóa `event_id`, TTL `ttl`):

    (chưa có) --claim--> in_progress (khóa thuê `lease_until`) --complete--> done
                                   \\--release (xử lý lỗi)--> (xóa, để lần giao lại xử lý)

- `claim`: `PutItem` có điều kiện (chưa có, hoặc đang `in_progress` mà khóa thuê đã hết hạn do tiến trình trước chết giữa chừng).
- Đã `done` thì lần giao trùng bị bỏ qua (`DUPLICATE`): "không tính hai lần".
- Đang `in_progress` còn hạn (một tiến trình khác đang xử lý) thì `BUSY`: người gọi báo lỗi từng mục để SQS giao lại sau.
- `complete` đặt `done` kèm TTL; `release` chỉ xóa khi vẫn là `in_progress` của mình (không xóa kết quả `done`).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any

log = logging.getLogger("yofina.forecast.idempotency")


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
        self.table = table
        self._client = client
        self._region = region
        self.ttl_seconds = ttl_seconds
        self.lease_seconds = lease_seconds
        self._clock = clock

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("dynamodb", region_name=self._region)
        return self._client

    @staticmethod
    def _is_conditional_failure(exc: Exception) -> bool:
        return (
            getattr(exc, "response", {}).get("Error", {}).get("Code")
            == "ConditionalCheckFailedException"
        )

    def claim(self, event_id: str, *, user_id: str | None = None) -> Claim:
        now = int(self._clock())
        item: dict[str, Any] = {
            "event_id": {"S": event_id},
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
            if not self._is_conditional_failure(exc):
                raise
        got = self.client.get_item(
            TableName=self.table, Key={"event_id": {"S": event_id}}, ConsistentRead=True
        ).get("Item")
        if got and got.get("status", {}).get("S") == "done":
            return Claim.DUPLICATE
        if not got:  # bị xóa (release) giữa hai lệnh: thử giành lại một lần
            return self.claim(event_id, user_id=user_id)
        return Claim.BUSY

    def complete(self, event_id: str, *, run_id: str | None = None) -> None:
        now = int(self._clock())
        values: dict[str, Any] = {
            ":done": {"S": "done"},
            ":ttl": {"N": str(now + self.ttl_seconds)},
        }
        expr = "SET #s = :done, #t = :ttl REMOVE lease_until"
        if run_id:
            expr = "SET #s = :done, #t = :ttl, run_id = :run REMOVE lease_until"
            values[":run"] = {"S": run_id}
        self.client.update_item(
            TableName=self.table,
            Key={"event_id": {"S": event_id}},
            UpdateExpression=expr,
            ExpressionAttributeNames={"#s": "status", "#t": "ttl"},
            ExpressionAttributeValues=values,
        )

    def release(self, event_id: str) -> None:
        """Bỏ khóa của một lần xử lý thất bại để lần giao lại được xử lý; không bao giờ xóa mục đã `done`."""
        try:
            self.client.delete_item(
                TableName=self.table,
                Key={"event_id": {"S": event_id}},
                ConditionExpression="#s = :ip",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":ip": {"S": "in_progress"}},
            )
        except Exception as exc:
            if not self._is_conditional_failure(exc):
                log.warning("release idempotency thất bại: %r", exc)
