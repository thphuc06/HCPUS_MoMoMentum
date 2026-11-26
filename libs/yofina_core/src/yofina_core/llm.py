"""Mọi lời gọi Bedrock đi qua module này (agent, Lambda, pipeline, evals).

Việc module làm (docs/plan/master-plan.md, mục "Model và giới hạn"):

1. **Vai -> chuỗi model dự phòng.** Cấu hình vai (`planner`, `small`, `embedding`) và danh sách model
   theo thứ tự dự phòng nằm ở `llm_defaults.json` (đóng gói cùng module) và được ghi đè bằng
   biến môi trường `YOFINA_LLM_<TÊN>` hoặc SSM `/yofina/llm/<tên>` (xem `load_settings`). Không có
   model id nào nằm trong logic.
2. **Giới hạn tốc độ mỗi model** (cửa sổ trượt 60 giây, mặc định 8 request/phút cho Claude 4.x).
   Chờ tối đa `rate_limit_max_wait_seconds`; quá thì coi model này là "đang nghẽn" và chuyển sang
   model kế tiếp. Bộ đếm này là **theo tiến trình** (mỗi microVM của Runtime một bộ); trần theo
   ngày mới là bộ đếm dùng chung.
3. **Trần lượt gọi mỗi ngày theo model**, đếm nguyên tử ở DynamoDB `yofina-usage` bằng `UpdateItem`
   có điều kiện (khóa `day` + `model`, thuộc tính `count`, TTL `ttl`). Chạm trần thì ném
   `ModelBudgetExceeded` (ứng với `ErrorCode.MODEL_BUDGET_EXCEEDED`) và **không** rơi sang model
   dự phòng: trần là chốt chi phí của cả vai. Không đọc/ghi được bộ đếm cũng coi là chạm trần
   (đóng cửa an toàn, vì đây là chốt chi phí). Lượt gọi được đếm *trước* khi gửi, nên lời gọi
   bị Bedrock throttle vẫn tính vào trần **ngày** của model đó (thiên về an toàn, có chủ ý: `UpdateItem` có điều
   kiện là chỗ giữ trước giúp trần đúng giữa mọi microVM/Lambda; bộ đếm theo từng model nên lần Sonnet bị throttle
   không lấy chỗ của Kimi). Lần bộ giới hạn tốc độ bỏ qua thì không đụng bộ đếm ngày.
   **Trần mỗi lượt hội thoại** (`TurnScope`) thì chỉ đếm lời gọi thật sự tới model: lần bị bộ giới hạn bỏ qua
   hoặc bị Bedrock từ chối trước khi chạy (`REFUSED_OUTCOMES`) được trả chỗ, để model dự phòng còn chỗ.
4. **Chuỗi dự phòng** bắt `ThrottlingException` **và** `AccessDeniedException` (Claude 5.x bị chặn
   theo kiểu này, xem docs/research/spike-bedrock-models.md §1) cùng vài lỗi tạm thời khác.
5. **Ghi log** mỗi lời gọi: vai, model, token vào/ra (token vào là tổng, gồm cả phần đọc/ghi cache), token đọc/ghi cache,
   thời lượng, kết quả (JSON một dòng, logger `yofina.llm`).
6. **JSON có cấu trúc bằng ép tool** (Nova không hỗ trợ `outputConfig`): `structured_json`, có
   giới hạn số lần thử; mỗi lần thử là một lượt gọi model và được đếm.
7. **Embedding** (`embed`, vai `embedding` = Cohere Embed v3, `InvokeModel`): gom lô tối đa 96 chuỗi, mỗi lô là một lời gọi được
   đếm và giới hạn như mọi lời gọi khác; mọi lô của một lần gọi dùng cùng một model.
8. **Prompt caching** theo cờ `prompt_cache` của từng model trong `llm_defaults.json` (mặc định tắt): bật thì `Converse` có
   `cachePoint` sau tool schema và sau system prompt (nguồn và giới hạn ở `PROMPT_CACHE_POINT`). Cờ theo MODEL chứ không theo vai,
   vì model dự phòng của cùng vai (Kimi K3) không nhận `cachePoint`.

Strands dùng chung các lớp kiểm này qua `LlmGateway.chain/reserve*/record`; lớp bọc `Model` của
Strands nằm ở `yofina_agent.metered_model` (để `yofina_core` không phụ thuộc Strands).

Client giả chỉ dùng trong unit test (truyền `client=`/`usage=`); mã sản phẩm không import chúng.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from importlib import resources
from typing import Any, Protocol, TypeVar
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError

from yofina_core.config import SSM_PREFIX_ENV, Config, ConfigError
from yofina_core.errors import ErrorCode

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger("yofina.llm")

DEFAULTS_FILE = "llm_defaults.json"
ENV_PREFIX = "YOFINA_LLM_"
_MISSING: Any = object()

#: Mã lỗi Bedrock làm chuỗi dự phòng rẽ sang model kế tiếp. `AccessDeniedException` nằm trong đó vì
#: quota 0 của Claude 5.x biểu hiện như vậy (không phải Throttling).
FALLBACK_ERROR_CODES = frozenset(
    {
        "ThrottlingException",
        "AccessDeniedException",
        "ServiceUnavailableException",
        "ModelNotReadyException",
        "ModelTimeoutException",
        "InternalServerException",
        "ResourceNotFoundException",
    }
)
_FALLBACK_EXC_NAMES = frozenset(
    {
        "ModelThrottledException",  # strands.types.exceptions
        "ReadTimeoutError",
        "ConnectTimeoutError",
        "EndpointConnectionError",
    }
)
#: Kết quả của lần thử mà Bedrock từ chối **trước khi** model chạy (throttle, quota 0, model/dịch vụ chưa nhận việc):
#: không có token, không mất tiền, nên không tính vào trần lượt hội thoại (`TurnScope`). Lần thử hết giờ, lỗi 5xx hay lỗi
#: khác vẫn tính, vì model có thể đã chạy. `ModelThrottledException` là tên Strands đặt cho `ThrottlingException`.
REFUSED_OUTCOMES = frozenset(
    {
        "ThrottlingException",
        "ModelThrottledException",
        "AccessDeniedException",
        "ServiceUnavailableException",
        "ModelNotReadyException",
    }
)

#: Điểm cache của Converse (`CachePointBlock`, TTL mặc định 5 phút; không đặt `ttl`).
#: Theo tài liệu Bedrock (truy cập 2026-11-26):
#: - https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html : Claude Sonnet 4.6 nhận `cachePoint` trong `system`,
#:   `messages` và `tools`, tối đa 4 điểm mỗi request, tối thiểu 1.024 token CỘNG DỒN cho cả tiền tố trước mỗi điểm (thứ tự xử lý
#:   `tools` -> `system` -> `messages`); tiền tố chưa đủ thì request vẫn chạy, chỉ không được cache. Dùng được cùng suy luận liên
#:   vùng (inference profile `global.`), nhưng request đi máy khác thì ghi cache mới thay vì đọc. Có cache thì `usage.inputTokens`
#:   CHỈ còn token không qua cache: tổng token vào = `inputTokens + cacheReadInputTokens + cacheWriteInputTokens`.
#: - https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-4-6.html : Explicit Prompt Caching có,
#:   1.024 token, 4 điểm, TTL 5 phút hoặc 1 giờ; ID suy luận toàn cầu `global.anthropic.claude-sonnet-4-6`.
#: - https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-moonshot-ai-kimi-k3.html : Converse KHÔNG nhận cache tường minh
#:   với Kimi K3 (spike 21/11: `ValidationException`, docs/research/spike-bedrock-models.md §4).
#: - https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_TokenUsage.html : `cacheReadInputTokens`, `cacheWriteInputTokens`.
PROMPT_CACHE_POINT: Mapping[str, Any] = {"cachePoint": {"type": "default"}}


# --- lỗi có kiểu ----------------------------------------------------------------------------
class LlmError(RuntimeError):
    """Gốc của lỗi do lớp bọc này ném."""


class ModelBudgetExceeded(LlmError):
    """Chạm trần lượt gọi (theo ngày hoặc theo lượt hội thoại), hoặc không đọc được bộ đếm.

    Luồng gọi phải rẽ sang thẻ số liệu tất định (không trả luồng rỗng).
    """

    code = ErrorCode.MODEL_BUDGET_EXCEEDED

    def __init__(
        self,
        message: str,
        *,
        role: str,
        model: str | None = None,
        cap: int | None = None,
        reason: str = "daily_cap",
    ) -> None:
        super().__init__(message)
        self.role, self.model, self.cap, self.reason = role, model, cap, reason


class AllModelsFailed(LlmError):
    """Mọi model trong chuỗi của vai đều lỗi tạm thời (throttle, bị chặn, nghẽn)."""

    def __init__(self, role: str, attempts: Sequence[tuple[str, str]]) -> None:
        detail = "; ".join(f"{m}: {c}" for m, c in attempts) or "chuỗi rỗng"
        super().__init__(f"Vai '{role}': mọi model đều lỗi ({detail})")
        self.role, self.attempts = role, tuple(attempts)


class RateLimitWaitTooLong(LlmError):
    """Phải chờ quá `rate_limit_max_wait_seconds` mới có chỗ; nội bộ, kích hoạt dự phòng."""

    def __init__(self, model: str, wait_seconds: float) -> None:
        super().__init__(f"{model}: phải chờ {wait_seconds:.1f}s để qua giới hạn tốc độ")
        self.model, self.wait_seconds = model, wait_seconds


class StructuredOutputError(LlmError):
    """Hết số lần thử mà model vẫn không trả JSON hợp lệ theo schema."""

    def __init__(self, role: str, attempts: int, last_error: str) -> None:
        super().__init__(
            f"Vai '{role}': sau {attempts} lần thử vẫn không có JSON hợp lệ: {last_error}"
        )
        self.role, self.attempts, self.last_error = role, attempts, last_error


# --- cấu hình -------------------------------------------------------------------------------
@dataclass(frozen=True)
class ModelSpec:
    id: str
    rpm: int  # 0 = không giới hạn
    daily_cap: int
    temperature: bool = True  # False: model không nhận `temperature` (Kimi K3)
    # True: gắn `cachePoint` sau system và sau tool schema (xem `PROMPT_CACHE_POINT`). Chỉ bật cho model mà tài liệu Bedrock xác
    # nhận có nhận `cachePoint` ở cả `system` lẫn `tools` của Converse; Kimi K3 trả `ValidationException` nên luôn tắt.
    prompt_cache: bool = False


@dataclass(frozen=True)
class LlmSettings:
    roles: Mapping[str, tuple[ModelSpec, ...]]
    rate_limit_max_wait_seconds: float = 20.0
    budget_timezone: str = "Asia/Ho_Chi_Minh"
    usage_ttl_days: int = 3
    read_timeout_seconds: float = 60.0


def load_defaults() -> dict[str, Any]:
    text = resources.files("yofina_core").joinpath(DEFAULTS_FILE).read_text(encoding="utf-8")
    return json.loads(text)


def _param(cfg: Config, env: Mapping[str, str], name: str) -> str | None:
    """Tra `YOFINA_LLM_<NAME>` rồi SSM `<prefix>/llm/<name>`; không có thì None."""
    key = ENV_PREFIX + name.upper()
    if key in env:
        return env[key]
    return cfg.get("llm/" + name, default=None)


def load_settings(
    config: Config | None = None, env: Mapping[str, str] | None = None
) -> LlmSettings:
    """Đọc cấu hình: mặc định đóng gói, rồi ghi đè bằng env/SSM.

    - `roles` (JSON): thay nguyên cấu hình của từng vai được nêu (vai khác giữ mặc định).
    - `daily_cap_<vai>` (số nguyên): ghi đè trần ngày của **mọi** model trong vai đó
      (ví dụ `YOFINA_LLM_DAILY_CAP_PLANNER=0` để thử đường suy giảm).
    - `rate_limit_max_wait_seconds`, `budget_timezone`, `usage_ttl_days`, `read_timeout_seconds`.
    """
    env = os.environ if env is None else env
    cfg = config or Config(env=env)
    defaults = load_defaults()

    roles_raw: dict[str, Any] = dict(defaults["roles"])
    override = _param(cfg, env, "roles")
    if override:
        try:
            parsed = json.loads(override)
            if not isinstance(parsed, dict):
                raise ValueError("phải là object")
            roles_raw.update(parsed)
        except ValueError as exc:
            raise ConfigError(f"Cấu hình llm/roles không phải JSON hợp lệ: {exc}") from exc

    roles: dict[str, tuple[ModelSpec, ...]] = {}
    for role, body in roles_raw.items():
        cap_override = _param(cfg, env, f"daily_cap_{role}")
        try:
            role_cap = int(body.get("daily_cap", 0))
            if cap_override is not None:
                cap_override_int: int | None = int(cap_override)
            else:
                cap_override_int = None
            specs = []
            for m in body["models"]:
                cap = (
                    cap_override_int
                    if cap_override_int is not None
                    else m.get("daily_cap", role_cap)
                )
                specs.append(
                    ModelSpec(
                        id=str(m["id"]),
                        rpm=int(m.get("rpm", body.get("rpm", 0))),
                        daily_cap=int(cap),
                        temperature=bool(m.get("temperature", True)),
                        prompt_cache=bool(m.get("prompt_cache", False)),
                    )
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"Cấu hình vai '{role}' sai định dạng: {exc!r}") from exc
        roles[role] = tuple(specs)

    def num(name: str, cast: Callable[[str], Any]) -> Any:
        raw = _param(cfg, env, name)
        try:
            return cast(raw) if raw is not None else defaults[name]
        except ValueError as exc:
            raise ConfigError(f"Cấu hình llm/{name} sai định dạng: {raw!r}") from exc

    return LlmSettings(
        roles=roles,
        rate_limit_max_wait_seconds=float(num("rate_limit_max_wait_seconds", float)),
        budget_timezone=str(_param(cfg, env, "budget_timezone") or defaults["budget_timezone"]),
        usage_ttl_days=int(num("usage_ttl_days", int)),
        read_timeout_seconds=float(num("read_timeout_seconds", float)),
    )


class BulkSsm:
    """Nguồn SSM cho `Config`: đọc cả nhánh `<prefix>/llm` bằng **một** lời gọi `GetParametersByPath`.

    `load_settings` tra khoảng chục khóa tùy chọn; hầu hết vắng. Mỗi khóa vắng qua `GetParameter` là một vòng
    mạng (cả giây ở phiên lạnh), nên gom lại. Khóa ngoài nhánh llm (ví dụ `dynamodb/usage-table`) đi thẳng
    `GetParameter`. Không đọc được nhánh llm (thiếu quyền, mạng) thì ghi log lỗi và dùng mặc định đóng gói
    (trần mặc định vẫn có hiệu lực), không làm sập lượt hội thoại.
    """

    class ParameterNotFound(Exception):  # Config nhận biết "vắng" qua tên lớp này
        pass

    def __init__(self, prefix: str, region: str, client: Any | None = None) -> None:
        self._path = prefix.rstrip("/") + "/llm"
        self._region, self._client = region, client
        self._params: dict[str, str] | None = None
        self._lock = threading.Lock()

    def _ssm(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("ssm", region_name=self._region)
        return self._client

    def _load(self) -> dict[str, str]:
        with self._lock:
            if self._params is None:
                found: dict[str, str] = {}
                try:
                    kw: dict[str, Any] = {
                        "Path": self._path,
                        "Recursive": True,
                        "WithDecryption": True,
                    }
                    while True:
                        page = self._ssm().get_parameters_by_path(**kw)
                        found.update({p["Name"]: str(p["Value"]) for p in page["Parameters"]})
                        if not page.get("NextToken"):
                            break
                        kw["NextToken"] = page["NextToken"]
                except Exception as exc:
                    logger.error(
                        json.dumps(
                            {
                                "event": "llm_ssm_unreadable",
                                "path": self._path,
                                "error": repr(exc)[:200],
                            }
                        )
                    )
                self._params = found
            return self._params

    def get_parameter(self, *, Name: str, WithDecryption: bool) -> Mapping[str, Any]:
        if Name.startswith(self._path + "/"):
            params = self._load()
            if Name in params:
                return {"Parameter": {"Value": params[Name]}}
            raise self.ParameterNotFound(Name)
        return self._ssm().get_parameter(Name=Name, WithDecryption=WithDecryption)


def default_config(env: Mapping[str, str] | None = None) -> Config:
    """`Config` cho tiến trình thật: nhánh SSM `<prefix>/llm` được đọc gộp một lần (xem `BulkSsm`)."""
    env = os.environ if env is None else env
    prefix = env.get(SSM_PREFIX_ENV)
    if not prefix:
        return Config(env)
    cfg = Config(env)
    return Config(env, BulkSsm(prefix, cfg.region()))


# --- bộ đếm theo ngày -----------------------------------------------------------------------
class BudgetCapReached(Exception):
    """Bộ đếm báo đã đủ trần (nội bộ; gateway đổi thành `ModelBudgetExceeded`)."""


class UsageStore(Protocol):
    def consume(self, *, day: str, model: str, cap: int, ttl_epoch: int) -> int:
        """Tăng bộ đếm nguyên tử và trả giá trị mới; ném `BudgetCapReached` nếu đã đủ `cap`."""
        ...


class DynamoUsageStore:
    """Bộ đếm ở DynamoDB `yofina-usage`: `UpdateItem` có điều kiện, nguyên tử giữa mọi tiến trình."""

    def __init__(self, table_name: str, client: Any) -> None:
        self._table, self._client = table_name, client

    def consume(self, *, day: str, model: str, cap: int, ttl_epoch: int) -> int:
        try:
            resp = self._client.update_item(
                TableName=self._table,
                Key={"day": {"S": day}, "model": {"S": model}},
                # `count` và `ttl` là từ khóa dành riêng của DynamoDB: phải đi qua tên giả.
                UpdateExpression="ADD #c :one SET #t = if_not_exists(#t, :ttl)",
                ConditionExpression="attribute_not_exists(#c) OR #c < :cap",
                ExpressionAttributeNames={"#c": "count", "#t": "ttl"},
                ExpressionAttributeValues={
                    ":one": {"N": "1"},
                    ":cap": {"N": str(cap)},
                    ":ttl": {"N": str(ttl_epoch)},
                },
                ReturnValues="UPDATED_NEW",
            )
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code == "ConditionalCheckFailedException":
                raise BudgetCapReached(model) from exc
            raise
        return int(resp["Attributes"]["count"]["N"])


# --- giới hạn tốc độ ------------------------------------------------------------------------
class RateLimiter:
    """Cửa sổ trượt theo khóa (model). An toàn đa luồng; chỉ giữ khóa rất ngắn."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, window: float = 60.0) -> None:
        self._clock, self._window = clock, window
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}

    def try_acquire(self, key: str, limit: int) -> float:
        """Lấy một chỗ. Trả 0.0 nếu lấy được, ngược lại là số giây phải chờ để có chỗ."""
        if limit <= 0:
            return 0.0
        with self._lock:
            now = self._clock()
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] >= self._window:
                q.popleft()
            if len(q) < limit:
                q.append(now)
                return 0.0
            return max(q[0] + self._window - now, 0.001)


# --- phạm vi một lượt hội thoại -------------------------------------------------------------
@dataclass
class CallRecord:
    role: str
    model: str
    input_tokens: int  # tổng token vào, GỒM cả token đọc và ghi cache (xem `PROMPT_CACHE_POINT`)
    output_tokens: int
    latency_ms: int
    outcome: str
    cache_read_tokens: int = 0  # phần của `input_tokens` đọc từ cache (`cacheReadInputTokens`)
    cache_write_tokens: int = 0  # phần của `input_tokens` ghi vào cache (`cacheWriteInputTokens`)

    @property
    def counted(self) -> bool:
        """Lần thử này có tính vào trần lượt không (False nếu Bedrock từ chối trước khi model chạy)."""
        return self.outcome not in REFUSED_OUTCOMES


class TurnScope:
    """Gom các lượt gọi của **một lượt hội thoại**: đếm, đặt trần (`max_calls`), cộng token.

    Trần chỉ đếm lời gọi thật sự tới model: `begin_call` giữ một chỗ trước khi gửi (để các lời gọi song song không vượt
    trần), rồi chỗ đó được trả lại nếu lần thử không tới model: bộ giới hạn tốc độ bỏ qua, chạm trần ngày (`cancel_call`)
    hoặc Bedrock từ chối trước khi chạy (`add` với kết quả thuộc `REFUSED_OUTCOMES`). Nhờ vậy khi Sonnet bị throttle,
    model dự phòng vẫn còn chỗ trong trần.

    Truyền tường minh (không dùng contextvar) để chạy đúng qua generator bất đồng bộ và luồng.
    """

    def __init__(self, max_calls: int | None = None) -> None:
        self.max_calls = max_calls
        self.records: list[CallRecord] = []
        self._held = 0  # lời gọi đã tính + lời gọi đang giữ chỗ chưa có kết quả
        self._lock = threading.Lock()

    def begin_call(self, role: str) -> None:
        with self._lock:
            if self.max_calls is not None and self._held >= self.max_calls:
                raise ModelBudgetExceeded(
                    f"Đã dùng hết {self.max_calls} lượt gọi model cho một lượt hội thoại",
                    role=role,
                    cap=self.max_calls,
                    reason="turn_limit",
                )
            self._held += 1

    def cancel_call(self) -> None:
        """Trả chỗ đã giữ bằng `begin_call` khi lần thử dừng trước lúc gửi tới model."""
        with self._lock:
            self._held = max(self._held - 1, 0)

    def add(self, record: CallRecord) -> None:
        with self._lock:
            self.records.append(record)
            if not record.counted:
                self._held = max(self._held - 1, 0)

    @property
    def calls(self) -> int:
        """Số lời gọi đã tới model và có kết quả (con số trần lượt đếm); lần bị từ chối vẫn nằm trong `records`."""
        with self._lock:
            return sum(1 for r in self.records if r.counted)

    def usage_by_model(self) -> list[dict[str, Any]]:
        """Dạng `usage` của AG-UI (`TokenUsage`): provider, model, inputTokens, outputTokens.

        `inputTokens` là tổng token vào (gồm cả phần qua cache), đúng nghĩa của AG-UI; model có token qua cache thì thêm
        `cachedInputTokens` (đọc) và `cacheWriteInputTokens` (ghi), là PHẦN của `inputTokens` chứ không cộng thêm. Không có cache
        thì dạng giữ như cũ (không có hai khóa đó)."""
        agg: dict[str, list[int]] = {}
        with self._lock:
            for r in self.records:
                a = agg.setdefault(r.model, [0, 0, 0, 0])
                a[0] += r.input_tokens
                a[1] += r.output_tokens
                a[2] += r.cache_read_tokens
                a[3] += r.cache_write_tokens
        out: list[dict[str, Any]] = []
        for m, a in agg.items():
            row: dict[str, Any] = {
                "provider": "bedrock",
                "model": m,
                "inputTokens": a[0],
                "outputTokens": a[1],
                "totalTokens": a[0] + a[1],
            }
            if a[2] or a[3]:
                row["cachedInputTokens"], row["cacheWriteInputTokens"] = a[2], a[3]
            out.append(row)
        return out


# --- kết quả --------------------------------------------------------------------------------
@dataclass
class ConverseResult:
    role: str
    model_id: str
    response: dict[str, Any]
    latency_ms: int
    input_tokens: int  # tổng token vào, gồm cả phần đọc/ghi cache
    output_tokens: int
    attempts: list[tuple[str, str]] = field(default_factory=list)  # (model, lý do bỏ qua)
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def content(self) -> list[dict[str, Any]]:
        return list(self.response.get("output", {}).get("message", {}).get("content", []))

    @property
    def text(self) -> str:
        return "".join(b["text"] for b in self.content if "text" in b)

    @property
    def tool_uses(self) -> list[dict[str, Any]]:
        return [b["toolUse"] for b in self.content if "toolUse" in b]


@dataclass
class StructuredResult[T: BaseModel]:
    value: T
    role: str
    model_id: str
    attempts: int  # số lần gọi model đã dùng (>= 1)


#: Giới hạn của Cohere Embed v3 trên Bedrock (https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-embed-v3.html):
#: tối đa 96 chuỗi mỗi lời gọi, mỗi chuỗi tối đa 2.048 ký tự.
EMBED_MAX_BATCH = 96
EMBED_MAX_CHARS = 2048
EMBED_INPUT_DOCUMENT = "search_document"
EMBED_INPUT_QUERY = "search_query"
EMBED_INPUT_TYPES = (EMBED_INPUT_DOCUMENT, EMBED_INPUT_QUERY)


@dataclass
class EmbedResult:
    role: str
    model_id: str
    vectors: list[list[float]]
    latency_ms: int
    input_tokens: int
    calls: int  # số lời gọi InvokeModel đã gửi (mỗi lô tối đa 96 chuỗi là một lời gọi)
    attempts: list[tuple[str, str]] = field(default_factory=list)  # (model, lý do bỏ qua)


def user_message(text: str) -> dict[str, Any]:
    return {"role": "user", "content": [{"text": text}]}


# --- schema cho ép tool ---------------------------------------------------------------------
def bedrock_json_schema(model: type[BaseModel], *, require_all: bool = True) -> dict[str, Any]:
    """JSON Schema phẳng cho `toolSpec.inputSchema`: giải `$ref`, bỏ `title`/`default`, `X | None`
    thành `type: [X, "null"]`, mọi thuộc tính đều `required`, `additionalProperties: false`.

    Dạng này đã chạy 14/14 với Nova 2 Lite, Haiku 4.5, Sonnet 4.6 và Kimi K3
    (spikes/bedrock-models/03_tooluse.py).

    `require_all=False`: `required` giữ đúng như Pydantic (chỉ trường không có giá trị mặc
    định), trường tùy chọn được bỏ. Cho schema nhiều trường tùy chọn mà mỗi lượt chỉ dùng vài
    trường (router): khi mọi trường là bắt buộc, Claude Haiku 4.5 chép đủ mọi trường kể cả null
    và vượt trần token đầu ra của router (đo ở #39).
    """
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(x) for x in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            return walk(copy.deepcopy(defs[name]))
        if "anyOf" in node:
            options = [o for o in node["anyOf"] if o.get("type") != "null"]
            nullable = len(options) != len(node["anyOf"])
            if len(options) == 1:
                merged = walk(options[0])
                if nullable:
                    if isinstance(merged.get("type"), str):
                        merged["type"] = [merged["type"], "null"]
                    if "enum" in merged:
                        merged["enum"] = [*merged["enum"], None]
                if "description" in node:
                    merged.setdefault("description", node["description"])
                return merged
        # `title`/`default` là khóa mô tả pydantic thêm vào, bỏ đi; nhưng trong `properties` thì khóa là TÊN FIELD (vd. field
        # `title` của dàn ý lộ trình) nên phải giữ nguyên.
        out = {
            k: ({name: walk(sub) for name, sub in v.items()} if k == "properties" else walk(v))
            for k, v in node.items()
            if k not in {"title", "default"}
        }
        if out.get("type") == "object" and "properties" in out:
            if require_all:
                out["required"] = list(out["properties"])
            out["additionalProperties"] = False
        return out

    return walk(schema)


# --- cổng gọi model -------------------------------------------------------------------------
class LlmGateway:
    """Điểm vào duy nhất để gọi Bedrock. Tạo một lần mỗi tiến trình (giữ bộ giới hạn tốc độ)."""

    def __init__(
        self,
        settings: LlmSettings | None = None,
        *,
        config: Config | None = None,
        client: Any | None = None,
        usage: UsageStore | None = None,
        limiter: RateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config or default_config()
        self.settings = settings or load_settings(self._config)
        self._client = client
        self._usage = usage
        self.limiter = limiter or RateLimiter()
        self._sleep = sleep
        self._now = now or (lambda: datetime.now(ZoneInfo(self.settings.budget_timezone)))
        self._init_lock = threading.Lock()

    # -- cấu hình ---------------------------------------------------------------------------
    def chain(self, role: str) -> tuple[ModelSpec, ...]:
        try:
            chain = self.settings.roles[role]
        except KeyError as exc:
            raise ConfigError(f"Không có vai model '{role}' trong cấu hình") from exc
        if not chain:
            raise ConfigError(f"Vai model '{role}' không có model nào")
        return chain

    # -- client và bộ đếm (tạo lười) --------------------------------------------------------
    @property
    def client(self) -> Any:
        if self._client is None:
            with self._init_lock:
                if self._client is None:
                    import boto3
                    from botocore.config import Config as BotoConfig

                    self._client = boto3.client(
                        "bedrock-runtime",
                        region_name=self._config.region(),
                        # Không retry ngầm của boto3: chuỗi dự phòng và bộ đếm tự quyết định.
                        config=BotoConfig(
                            retries={"max_attempts": 1},
                            read_timeout=self.settings.read_timeout_seconds,
                            connect_timeout=5,
                        ),
                    )
        return self._client

    @property
    def usage(self) -> UsageStore:
        if self._usage is None:
            with self._init_lock:
                if self._usage is None:
                    import boto3

                    table = os.environ.get("YOFINA_USAGE_TABLE") or self._config.get(
                        "dynamodb/usage-table"
                    )
                    self._usage = DynamoUsageStore(
                        table, boto3.client("dynamodb", region_name=self._config.region())
                    )
        return self._usage

    # -- giữ chỗ trước mỗi lời gọi ----------------------------------------------------------
    def _consume_budget(self, role: str, spec: ModelSpec) -> None:
        if spec.daily_cap <= 0:
            raise ModelBudgetExceeded(
                f"Trần ngày của {spec.id} bằng {spec.daily_cap}: không gọi model",
                role=role,
                model=spec.id,
                cap=spec.daily_cap,
            )
        now = self._now().astimezone(ZoneInfo(self.settings.budget_timezone))
        ttl = int((now + timedelta(days=self.settings.usage_ttl_days)).timestamp())
        try:
            self.usage.consume(
                day=now.date().isoformat(), model=spec.id, cap=spec.daily_cap, ttl_epoch=ttl
            )
        except BudgetCapReached as exc:
            raise ModelBudgetExceeded(
                f"Đã chạm trần {spec.daily_cap} lượt/ngày của {spec.id}",
                role=role,
                model=spec.id,
                cap=spec.daily_cap,
            ) from exc
        except Exception as exc:
            logger.error(
                json.dumps(
                    {"event": "usage_store_error", "model": spec.id, "error": repr(exc)[:300]}
                )
            )
            raise ModelBudgetExceeded(
                "Không đọc/ghi được bộ đếm lượt gọi model; từ chối gọi để giữ trần chi phí",
                role=role,
                model=spec.id,
                cap=spec.daily_cap,
                reason="usage_store_unavailable",
            ) from exc

    def reserve(self, role: str, spec: ModelSpec, scope: TurnScope | None = None) -> None:
        """Giữ chỗ cho một lời gọi (đồng bộ): trần lượt hội thoại -> tốc độ -> trần ngày.

        Dừng ở bước tốc độ hoặc trần ngày thì trả lại chỗ trong trần lượt (lời gọi chưa tới model)."""
        if scope is not None:
            scope.begin_call(role)
        try:
            waited = 0.0
            while (wait := self.limiter.try_acquire(spec.id, spec.rpm)) > 0:
                if waited + wait > self.settings.rate_limit_max_wait_seconds:
                    raise RateLimitWaitTooLong(spec.id, wait)
                self._sleep(wait)
                waited += wait
            self._consume_budget(role, spec)
        except BaseException:
            if scope is not None:
                scope.cancel_call()
            raise

    async def reserve_async(
        self, role: str, spec: ModelSpec, scope: TurnScope | None = None
    ) -> None:
        """Như `reserve` nhưng không chặn event loop (chờ bằng `asyncio.sleep`, DynamoDB trong luồng)."""
        if scope is not None:
            scope.begin_call(role)
        try:
            waited = 0.0
            while (wait := self.limiter.try_acquire(spec.id, spec.rpm)) > 0:
                if waited + wait > self.settings.rate_limit_max_wait_seconds:
                    raise RateLimitWaitTooLong(spec.id, wait)
                await asyncio.sleep(wait)
                waited += wait
            await asyncio.to_thread(self._consume_budget, role, spec)
        except BaseException:  # gồm cả CancelledError khi đang chờ
            if scope is not None:
                scope.cancel_call()
            raise

    # -- phân loại lỗi và ghi log -----------------------------------------------------------
    @staticmethod
    def error_code(exc: BaseException) -> str | None:
        """Mã lỗi AWS (nếu có) của một ngoại lệ botocore."""
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            return response.get("Error", {}).get("Code")
        return None

    @classmethod
    def is_fallback_error(cls, exc: BaseException) -> bool:
        """Lỗi tạm thời/quyền: chuỗi dự phòng rẽ sang model kế tiếp."""
        code = cls.error_code(exc)
        if code is not None:
            return code in FALLBACK_ERROR_CODES
        return type(exc).__name__ in _FALLBACK_EXC_NAMES

    @staticmethod
    def record(
        role: str,
        model: str,
        *,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        outcome: str,
        scope: TurnScope | None = None,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> None:
        """Ghi một lần thử. `input_tokens` là tổng token vào; `cache_*_tokens` là phần của nó qua cache (0 nếu không có)."""
        if scope is not None:
            scope.add(
                CallRecord(
                    role,
                    model,
                    input_tokens,
                    output_tokens,
                    latency_ms,
                    outcome,
                    cache_read_tokens,
                    cache_write_tokens,
                )
            )
        logger.info(
            json.dumps(
                {
                    "event": "llm_call",
                    "role": role,
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cache_read_tokens": cache_read_tokens,
                    "cache_write_tokens": cache_write_tokens,
                    "latency_ms": latency_ms,
                    "outcome": outcome,
                }
            )
        )

    # -- Converse ---------------------------------------------------------------------------
    def converse(
        self,
        role: str,
        *,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tool_config: dict[str, Any] | None = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
        scope: TurnScope | None = None,
    ) -> ConverseResult:
        """Gọi `Converse` theo chuỗi dự phòng của `role` (đồng bộ)."""
        skipped: list[tuple[str, str]] = []
        for spec in self.chain(role):
            try:
                self.reserve(role, spec, scope)
            except RateLimitWaitTooLong as exc:
                skipped.append((spec.id, "RateLimitWaitTooLong"))
                logger.warning(json.dumps({"event": "llm_skip", "model": spec.id, "why": str(exc)}))
                continue
            started = time.perf_counter()
            try:
                response = self.client.converse(
                    **self._request(spec, messages, system, tool_config, max_tokens, temperature)
                )
            except Exception as exc:
                latency = int((time.perf_counter() - started) * 1000)
                code = self.error_code(exc) or type(exc).__name__
                self.record(
                    role,
                    spec.id,
                    input_tokens=0,
                    output_tokens=0,
                    latency_ms=latency,
                    outcome=code,
                    scope=scope,
                )
                if self.is_fallback_error(exc):
                    skipped.append((spec.id, code))
                    continue
                raise
            return self._result(role, spec, response, started, skipped, scope)
        raise AllModelsFailed(role, skipped)

    async def aconverse(self, role: str, **kwargs: Any) -> ConverseResult:
        """`converse` chạy trong luồng nền (không chặn event loop)."""
        return await asyncio.to_thread(self.converse, role, **kwargs)

    @staticmethod
    def _request(
        spec: ModelSpec,
        messages: list[dict[str, Any]],
        system: str | None,
        tool_config: dict[str, Any] | None,
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        inference: dict[str, Any] = {"maxTokens": max_tokens}
        if spec.temperature:
            inference["temperature"] = temperature
        req: dict[str, Any] = {
            "modelId": spec.id,
            "messages": messages,
            "inferenceConfig": inference,
        }
        # Có cache: điểm cache sau tool schema và sau system (phần tĩnh), không đặt trong `messages` (đổi theo lượt). Tạo bản mới,
        # không sửa `tool_config` của người gọi: model dự phòng (Kimi K3) dùng lại đúng `tool_config` đó và không được có điểm cache.
        if system:
            req["system"] = [{"text": system}]
            if spec.prompt_cache:
                req["system"].append(copy.deepcopy(dict(PROMPT_CACHE_POINT)))
        if tool_config:
            tools = tool_config.get("tools")
            if spec.prompt_cache and isinstance(tools, list) and tools:
                tool_config = {
                    **tool_config,
                    "tools": [*tools, copy.deepcopy(dict(PROMPT_CACHE_POINT))],
                }
            req["toolConfig"] = tool_config
        return req

    def _result(
        self,
        role: str,
        spec: ModelSpec,
        response: dict[str, Any],
        started: float,
        skipped: list[tuple[str, str]],
        scope: TurnScope | None,
    ) -> ConverseResult:
        latency = int((time.perf_counter() - started) * 1000)
        usage = response.get("usage", {})
        # Có cache thì Bedrock chỉ để token KHÔNG qua cache ở `inputTokens`: cộng lại để `input_tokens` vẫn là tổng token vào
        # (cùng nghĩa với lúc chưa có cache, nên log và ước tính chi phí cũ không bị đếm thấp).
        read = int(usage.get("cacheReadInputTokens", 0) or 0)
        write = int(usage.get("cacheWriteInputTokens", 0) or 0)
        tin = int(usage.get("inputTokens", 0)) + read + write
        tout = int(usage.get("outputTokens", 0))
        self.record(
            role,
            spec.id,
            input_tokens=tin,
            output_tokens=tout,
            latency_ms=latency,
            outcome="ok",
            scope=scope,
            cache_read_tokens=read,
            cache_write_tokens=write,
        )
        return ConverseResult(
            role, spec.id, response, latency, tin, tout, list(skipped), read, write
        )

    # -- JSON có cấu trúc bằng ép tool ------------------------------------------------------
    def structured_json(
        self,
        role: str,
        *,
        output_model: type[T],
        messages: list[dict[str, Any]],
        system: str | None = None,
        tool_name: str = "report",
        description: str = "Trả kết quả theo đúng schema.",
        max_attempts: int = 3,
        max_tokens: int = 512,
        scope: TurnScope | None = None,
        require_all_fields: bool = True,
    ) -> StructuredResult[T]:
        """Ép model gọi một tool có schema của `output_model` và kiểm bằng Pydantic.

        Không dùng `outputConfig` (Nova không hỗ trợ). Lỗi kiểm schema hoặc model không gọi tool thì
        gửi lại lỗi cho model và thử lại, tối đa `max_attempts` lần gọi model (mỗi lần được đếm và
        giới hạn như mọi lời gọi khác). Lỗi `ModelBudgetExceeded`/`AllModelsFailed` đi thẳng ra ngoài.
        `require_all_fields`: như `require_all` của `bedrock_json_schema`.
        """
        if max_attempts < 1:
            raise ValueError("max_attempts phải >= 1")
        tool_config = {
            "tools": [
                {
                    "toolSpec": {
                        "name": tool_name,
                        "description": description,
                        "inputSchema": {
                            "json": bedrock_json_schema(output_model, require_all=require_all_fields)
                        },
                    }
                }
            ],
            "toolChoice": {"tool": {"name": tool_name}},
        }
        convo = list(messages)
        last_error = "model không gọi tool"
        for attempt in range(1, max_attempts + 1):
            res = self.converse(
                role,
                messages=convo,
                system=system,
                tool_config=tool_config,
                max_tokens=max_tokens,
                scope=scope,
            )
            use = next((u for u in res.tool_uses if u.get("name") == tool_name), None)
            if use is None:
                last_error = "model không gọi tool"
                convo = [
                    *convo,
                    res.response["output"]["message"],
                    user_message(
                        f"Bạn phải trả kết quả bằng cách gọi tool `{tool_name}` theo đúng schema."
                    ),
                ]
                continue
            try:
                return StructuredResult(
                    output_model.model_validate(use.get("input") or {}), role, res.model_id, attempt
                )
            except ValidationError as exc:
                last_error = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
                )[:400]
                convo = [
                    *convo,
                    res.response["output"]["message"],
                    {
                        "role": "user",
                        "content": [
                            {
                                "toolResult": {
                                    "toolUseId": use["toolUseId"],
                                    "status": "error",
                                    "content": [
                                        {
                                            "text": f"JSON sai schema: {last_error}. Gọi lại tool với giá trị đúng."
                                        }
                                    ],
                                }
                            }
                        ],
                    },
                ]
        raise StructuredOutputError(role, max_attempts, last_error)

    async def astructured_json(self, role: str, **kwargs: Any) -> StructuredResult[Any]:
        return await asyncio.to_thread(self.structured_json, role, **kwargs)

    # -- embedding (Cohere Embed v3 qua InvokeModel) -----------------------------------------
    def embed(
        self,
        role: str,
        texts: Sequence[str],
        *,
        input_type: str = EMBED_INPUT_DOCUMENT,
        scope: TurnScope | None = None,
    ) -> EmbedResult:
        """Nhúng danh sách chuỗi bằng `InvokeModel` theo chuỗi dự phòng của `role` (đồng bộ).

        Theo tài liệu Bedrock (Cohere Embed v3): tối đa `EMBED_MAX_BATCH` (96) chuỗi mỗi lời gọi nên danh sách dài được cắt thành nhiều
        lô; mỗi chuỗi tối đa `EMBED_MAX_CHARS` ký tự (dài hơn thì bị cắt đuôi ở phía client, để không phụ thuộc `truncate`).
        `input_type` là `search_document` (nhãn lưu vào kho) hoặc `search_query` (chuỗi cần tra). Mỗi LÔ là MỘT lời gọi: được giữ chỗ,
        đếm vào trần ngày và vào `scope` như mọi lời gọi khác, nên gom lô là cách giữ trần. Một lô lỗi tạm thời thì thử model kế
        tiếp của vai (mỗi lô tự chọn model, nhưng mọi lô của MỘT lần gọi phải cùng model để vector so sánh được: lô sau đi lại
        đúng model của lô đầu, không dự phòng sang model khác). Thứ tự vector khớp thứ tự `texts`.
        """
        if input_type not in EMBED_INPUT_TYPES:
            raise ValueError(f"input_type phải thuộc {EMBED_INPUT_TYPES}")
        clipped = [str(t)[:EMBED_MAX_CHARS] for t in texts]
        if not clipped:
            return EmbedResult(role, "", [], 0, 0, 0, [])
        batches = [clipped[i : i + EMBED_MAX_BATCH] for i in range(0, len(clipped), EMBED_MAX_BATCH)]
        skipped: list[tuple[str, str]] = []
        chain = self.chain(role)
        vectors: list[list[float]] = []
        used: ModelSpec | None = None
        tin_total, latency_total, calls = 0, 0, 0
        for batch in batches:
            candidates = (used,) if used is not None else chain
            done = False
            for spec in candidates:
                try:
                    self.reserve(role, spec, scope)
                except RateLimitWaitTooLong as exc:
                    skipped.append((spec.id, "RateLimitWaitTooLong"))
                    logger.warning(json.dumps({"event": "llm_skip", "model": spec.id, "why": str(exc)}))
                    continue
                started = time.perf_counter()
                try:
                    response = self.client.invoke_model(
                        modelId=spec.id,
                        body=json.dumps({"texts": batch, "input_type": input_type, "truncate": "END"}),
                        contentType="application/json",
                        accept="application/json",
                    )
                    payload = json.loads(response["body"].read())
                    vecs = payload["embeddings"]
                    if len(vecs) != len(batch) or any(len(v) != len(vecs[0]) for v in vecs):
                        raise LlmError(
                            f"{spec.id}: trả {len(vecs)} vector cho {len(batch)} chuỗi hoặc vector lệch chiều"
                        )
                except Exception as exc:
                    latency = int((time.perf_counter() - started) * 1000)
                    code = self.error_code(exc) or type(exc).__name__
                    self.record(
                        role, spec.id, input_tokens=0, output_tokens=0, latency_ms=latency, outcome=code, scope=scope
                    )
                    if used is None and self.is_fallback_error(exc):
                        skipped.append((spec.id, code))
                        continue
                    raise
                latency = int((time.perf_counter() - started) * 1000)
                headers = response.get("ResponseMetadata", {}).get("HTTPHeaders", {})
                tin = int(headers.get("x-amzn-bedrock-input-token-count", 0) or 0)
                self.record(
                    role, spec.id, input_tokens=tin, output_tokens=0, latency_ms=latency, outcome="ok", scope=scope
                )
                used = spec
                vectors.extend([float(x) for x in v] for v in vecs)
                tin_total += tin
                latency_total += latency
                calls += 1
                done = True
                break
            if not done:
                raise AllModelsFailed(role, skipped)
        assert used is not None
        return EmbedResult(role, used.id, vectors, latency_total, tin_total, calls, skipped)

    async def aembed(self, role: str, texts: Sequence[str], **kwargs: Any) -> EmbedResult:
        return await asyncio.to_thread(self.embed, role, texts, **kwargs)


_gateway: LlmGateway | None = None
_gateway_lock = threading.Lock()


def get_gateway() -> LlmGateway:
    """Cổng dùng chung của tiến trình (tạo lần đầu từ cấu hình env/SSM)."""
    global _gateway
    if _gateway is None:
        with _gateway_lock:
            if _gateway is None:
                _gateway = LlmGateway()
    return _gateway
