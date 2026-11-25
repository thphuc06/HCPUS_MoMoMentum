"""Trần theo tài khoản mỗi ngày (#13, phase 6 B4, Q6): lượt chat và lượt nạp tệp của một tài khoản.

Trần chung theo model (`yofina_core.llm`) giữ chi phí cả hệ thống; trần này giữ để một tài khoản không dùng hết trần chung của
mọi người. Đếm ở cùng bảng DynamoDB `yofina-usage` bằng `DynamoUsageStore` (`UpdateItem` có điều kiện, nguyên tử giữa mọi
tiến trình), nhưng ở phân vùng riêng để bảng vận hành (`/ops/summary`, `Query` theo `day = YYYY-MM-DD`) không lẫn số:

- `day` = `quota#<YYYY-MM-DD>`, `model` = `<kind>#<băm sub>`; băm SHA-256 có tiền tố cố định, không bao giờ lưu `sub` hay email.
- Ngày theo **đồng hồ thật** ở múi giờ trần model (`budget_timezone` của `llm_defaults.json`, mặc định `Asia/Ho_Chi_Minh`), như
  trần ngày của `llm.py`: trần giữ chi phí thật mỗi ngày thật, không theo ngày mô phỏng (`app_today`) của từng tài khoản demo.

Số trần đọc theo thứ tự: biến `YOFINA_QUOTA_<TÊN>`, SSM `<prefix>/quota/<tên>`, mặc định trong mã. Giá trị SSM được nhớ
`CAP_CACHE_SECONDS` giây rồi đọc lại, nên đổi trần không cần deploy. Bộ đếm lỗi (mạng, quyền) thì cho qua và ghi log: trần chung
theo model vẫn chặn chi phí, còn chặn người dùng vì bảng đếm trục trặc thì thiệt hơn.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from yofina_core.config import SSM_PREFIX_ENV, Config
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.llm import BudgetCapReached, DynamoUsageStore, UsageStore, load_defaults

logger = logging.getLogger("yofina.quota")

CHAT = "chat"
UPLOAD = "upload"
#: tên khóa cấu hình (biến `YOFINA_QUOTA_<TÊN HOA>`, SSM `<prefix>/quota/<tên>`) và trần mặc định của từng loại
CAP_NAMES: dict[str, str] = {CHAT: "chat_turns_per_day", UPLOAD: "uploads_per_day"}
DEFAULT_CAPS: dict[str, int] = {CHAT: 100, UPLOAD: 20}
CAP_CACHE_SECONDS = 300.0
TTL_DAYS = 3
_KEY_SALT = "yofina-quota:"


#: tiêu đề khối `notice` của lượt chat bị chặn (khối giới hạn 80 ký tự)
EXCEEDED_TITLE = "Hôm nay đã hết lượt"
#: việc bị chặn, theo loại trần; câu đầy đủ ở `DailyQuotaExceeded.message` (khối `notice` giới hạn 280 ký tự)
_USED_UP: dict[str, str] = {
    CHAT: "Hôm nay tài khoản đã dùng đủ {cap} lượt trò chuyện với trợ lý.",
    UPLOAD: "Hôm nay tài khoản đã nạp đủ {cap} tệp.",
}
_STILL_OK = " Bạn vẫn xem số liệu ở các màn khác bình thường; lượt mới mở lại từ 0 giờ ngày mai."


class DailyQuotaExceeded(YofinaError):
    """Tài khoản đã dùng đủ trần của loại `kind` trong ngày: mã `DAILY_QUOTA_EXCEEDED` (HTTP 429), câu tiếng Việt hiển thị được."""

    def __init__(self, kind: str, cap: int) -> None:
        super().__init__(
            ErrorCode.DAILY_QUOTA_EXCEEDED, _USED_UP[kind].format(cap=max(cap, 0)) + _STILL_OK
        )
        self.kind, self.cap = kind, cap


def account_key(sub: str) -> str:
    """Khóa ẩn danh của tài khoản: SHA-256 (có tiền tố cố định) của `sub`, cắt 32 ký tự hex."""
    return hashlib.sha256((_KEY_SALT + sub).encode("utf-8")).hexdigest()[:32]


class CapSource:
    """Trần hiện hành của một loại: env, rồi SSM (nhớ `ttl` giây), rồi mặc định. Lỗi đọc SSM thì dùng mặc định."""

    def __init__(
        self,
        kind: str,
        env: Mapping[str, str] | None = None,
        ssm: Any = None,
        *,
        ttl: float = CAP_CACHE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.kind, self.name, self.default = kind, CAP_NAMES[kind], DEFAULT_CAPS[kind]
        self._env = os.environ if env is None else env
        self._ssm, self._ttl, self._clock = ssm, ttl, clock
        self._value: int | None = None
        self._read_at = 0.0
        self._lock = threading.Lock()

    def _ssm_client(self) -> Any:
        if self._ssm is None:
            import boto3  # chỉ import khi thật sự đọc SSM

            self._ssm = boto3.client("ssm", region_name=Config(self._env).region())
        return self._ssm

    def _read(self) -> int:
        env_key = f"YOFINA_QUOTA_{self.name.upper()}"
        try:
            if env_key in self._env:
                return int(self._env[env_key])
            prefix = self._env.get(SSM_PREFIX_ENV)
            if not prefix:
                return self.default
            path = f"{prefix.rstrip('/')}/quota/{self.name}"
            try:
                resp = self._ssm_client().get_parameter(Name=path, WithDecryption=False)
            except Exception as exc:
                # như `Config`: khóa vắng (`ParameterNotFound`) thì dùng mặc định
                if type(exc).__name__ == "ParameterNotFound":
                    return self.default
                raise
            return int(resp["Parameter"]["Value"])
        except Exception as exc:
            logger.error(
                json.dumps(
                    {"event": "quota_cap_unreadable", "name": self.name, "error": repr(exc)[:200]}
                )
            )
            return self.default

    def __call__(self) -> int:
        with self._lock:
            now = self._clock()
            if self._value is None or now - self._read_at >= self._ttl:
                self._value, self._read_at = self._read(), now
            return self._value


class AccountQuota:
    """Bộ đếm một loại trần (`chat` hoặc `upload`) của mọi tài khoản. `store=None` là tắt (chưa cấu hình bảng)."""

    def __init__(
        self,
        kind: str,
        *,
        store: UsageStore | None,
        cap: int | Callable[[], int],
        now: Callable[[], datetime] | None = None,
        timezone: str | None = None,
        ttl_days: int = TTL_DAYS,
    ) -> None:
        if kind not in CAP_NAMES:
            raise ValueError(f"loại trần lạ: {kind}")
        self.kind, self._store, self._ttl_days = kind, store, ttl_days
        self._cap: Callable[[], int] = cap if callable(cap) else (lambda: cap)
        self._tz = ZoneInfo(timezone or str(load_defaults()["budget_timezone"]))
        self._now = now or (lambda: datetime.now(self._tz))

    @classmethod
    def from_env(
        cls, kind: str, env: Mapping[str, str] | None = None, *, client: Any = None, ssm: Any = None
    ) -> AccountQuota:
        """Cấu hình tiến trình thật: bảng ở `YOFINA_USAGE_TABLE` (vắng thì tắt và ghi log), trần ở env/SSM (`CapSource`)."""
        env = os.environ if env is None else env
        table = env.get("YOFINA_USAGE_TABLE", "")
        store: UsageStore | None = None
        if table:
            if client is None:
                import boto3

                client = boto3.client("dynamodb", region_name=Config(env).region())
            store = DynamoUsageStore(table, client)
        else:
            logger.warning(
                json.dumps({"event": "quota_disabled", "kind": kind, "reason": "no_usage_table"})
            )
        return cls(kind, store=store, cap=CapSource(kind, env, ssm))

    def take(self, sub: str) -> int | None:
        """Tính một lượt cho tài khoản `sub`. Đủ trần thì ném `DailyQuotaExceeded`; trả số lượt đã dùng (None nếu không đếm được)."""
        if self._store is None:
            return None
        cap = self._cap()
        if cap <= 0:
            raise DailyQuotaExceeded(self.kind, cap)
        now = self._now().astimezone(self._tz)
        ttl = int((now + timedelta(days=self._ttl_days)).timestamp())
        try:
            return self._store.consume(
                day=f"quota#{now.date().isoformat()}",
                model=f"{self.kind}#{account_key(sub)}",
                cap=cap,
                ttl_epoch=ttl,
            )
        except BudgetCapReached as exc:
            logger.info(json.dumps({"event": "quota_exceeded", "kind": self.kind, "cap": cap}))
            raise DailyQuotaExceeded(self.kind, cap) from exc
        except Exception as exc:
            logger.error(
                json.dumps(
                    {"event": "quota_store_error", "kind": self.kind, "error": repr(exc)[:300]}
                )
            )
            return None
