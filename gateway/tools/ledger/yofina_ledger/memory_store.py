"""Bộ nhớ dài hạn phía Lambda ledger (phase 5, luồng B): xem, xóa bản ghi AgentCore Memory của CHÍNH người gọi, xóa hết khi "Xóa dữ
liệu của tôi", và `quiet_hours` (giờ không muốn được nhắc) cho cổng bản tin.

Gọi boto3 `bedrock-agentcore` (data plane) trực tiếp. Thiết kế và nguồn: docs/research/agentcore-memory-design.md.

- Danh tính: `sub` của JWT (rest_api đã lấy từ claim của authorizer). Namespace dựng bằng `yofina_core.memory`, không bao giờ từ dữ liệu
  người dùng gửi. Mọi bản ghi trả về hay bị xóa đều được kiểm lại bằng `kind_of_namespace(ns, sub)`: namespace không thuộc người gọi
  thì bị bỏ, kể cả khi lọc phía dịch vụ sai.
- IAM không ép được namespace theo từng người dùng (một role Lambda dùng chung cho mọi người dùng; condition key
  `bedrock-agentcore:namespace` so với giá trị tĩnh trong policy) nên việc ép nằm ở mã này và có test.
- AgentCore không có API xóa theo người dùng: liệt kê `ListMemoryRecords(namespacePath=/yofina/users/<sub>/)` rồi
  `BatchDeleteMemoryRecords` (tối đa 100 mỗi lần); sự kiện ngắn hạn (nếu có, agent dùng `IngestData` nên thường không có):
  `ListSessions` -> `ListEvents` -> `DeleteEvent`.
- Id của Memory: biến môi trường `YOFINA_MEMORY_ID`, hoặc tham số SSM có tên ở `YOFINA_MEMORY_ID_PARAM` (stack YofinaAgent ghi sau
  khi tạo Memory; YofinaTools deploy trước nên không đọc được lúc deploy). Chưa có tham số thì Memory coi là chưa cấu hình.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from importlib import resources
from typing import Any, Protocol

from yofina_core.blocks import format_instant
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.memory import (
    MEMORY_LIST_LIMIT_DEFAULT,
    MEMORY_LIST_LIMIT_MAX,
    MEMORY_NAMESPACE_TEMPLATES,
    MEMORY_SOURCE_OF_KIND,
    MEMORY_TEXT_MAX_CHARS,
    RECORD_ID_RE,
    MemoryClearResponse,
    MemoryListResponse,
    MemoryRecord,
    MemoryRecordDeleteResponse,
    kind_of_namespace,
    namespace_for,
    user_root,
)
from yofina_core.pii import fold, mask_names, mask_pii

log = logging.getLogger("yofina.ledger.memory")


def load_defaults() -> dict[str, Any]:
    text = (
        resources.files("yofina_ledger")
        .joinpath("memory_defaults.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(text)


def _setting(name: str, env: Mapping[str, str], defaults: Mapping[str, Any]) -> int:
    raw = env.get(f"YOFINA_{name.upper()}")
    return int(raw) if raw not in (None, "") else int(defaults[name])


class MemoryApi(Protocol):
    """Phần của client boto3 `bedrock-agentcore` mà ledger dùng (test thay bằng client giả)."""

    def list_memory_records(self, **kwargs: Any) -> Mapping[str, Any]: ...
    def get_memory_record(self, **kwargs: Any) -> Mapping[str, Any]: ...
    def delete_memory_record(self, **kwargs: Any) -> Mapping[str, Any]: ...
    def batch_delete_memory_records(self, **kwargs: Any) -> Mapping[str, Any]: ...
    def list_sessions(self, **kwargs: Any) -> Mapping[str, Any]: ...
    def list_events(self, **kwargs: Any) -> Mapping[str, Any]: ...
    def delete_event(self, **kwargs: Any) -> Mapping[str, Any]: ...


def _error_code(exc: BaseException) -> str:
    resp = getattr(exc, "response", None)
    if isinstance(resp, Mapping):
        return str(resp.get("Error", {}).get("Code", "")) or type(exc).__name__
    return type(exc).__name__


_NOT_FOUND_CODES = {"ResourceNotFoundException", "ValidationException", "InvalidInputException"}
_TAG_RE = re.compile(r"<topic\s+name=\"([^\"]{0,120})\"\s*>|</?[a-zA-Z][^>]{0,200}>")


def display_text(content: Any) -> str:
    """Chữ hiển thị của một bản ghi, đã che PII và tên người khác: sở thích (JSON `{context, preference, categories}`) lấy
    `preference`; tóm tắt phiên (XML `<topic name="...">`) đổi thành "chủ đề: nội dung"; cắt `MEMORY_TEXT_MAX_CHARS`."""
    raw = content.get("text") if isinstance(content, Mapping) else None
    if not isinstance(raw, str):
        return ""
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            obj = json.loads(raw)
        except ValueError:
            obj = None
        if isinstance(obj, Mapping):
            raw = next(
                (
                    obj[k].strip()
                    for k in ("preference", "fact", "text", "context")
                    if isinstance(obj.get(k), str) and obj[k].strip()
                ),
                raw,
            )
    text = _TAG_RE.sub(lambda m: f" {m.group(1)}: " if m.group(1) else " ", raw)
    text = " ".join(mask_names(mask_pii(text).text).split())
    if len(text) > MEMORY_TEXT_MAX_CHARS:
        text = text[: MEMORY_TEXT_MAX_CHARS - 1].rstrip() + "…"
    return text


class MemoryStore:
    """Thao tác bộ nhớ của MỘT người dùng mỗi lần gọi (luôn nhận `sub` đã xác thực)."""

    def __init__(
        self,
        memory_id: str | Callable[[], str | None] | None,
        client: MemoryApi | None = None,
        *,
        region: str | None = None,
        max_pages: int = 50,
        batch_size: int = 100,
        max_sessions: int = 200,
    ) -> None:
        self._memory_id = memory_id
        self._resolved: str | None = None
        self._client = client
        self._region = region
        self.max_pages = max_pages
        self.batch_size = min(max(batch_size, 1), 100)
        self.max_sessions = max_sessions

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None, *, ssm: Any = None) -> MemoryStore:
        env = os.environ if env is None else env
        d = load_defaults()
        region = env.get("YOFINA_REGION") or env.get("AWS_REGION") or None
        direct = (env.get("YOFINA_MEMORY_ID") or "").strip() or None
        param = (env.get("YOFINA_MEMORY_ID_PARAM") or "").strip() or None

        def resolve() -> str | None:
            if direct:
                return direct
            if not param:
                return None
            client = ssm
            if client is None:
                import boto3

                client = boto3.client("ssm", region_name=region)
            try:
                return str(client.get_parameter(Name=param)["Parameter"]["Value"]).strip() or None
            except Exception as exc:
                if _error_code(exc) == "ParameterNotFound":
                    return None  # YofinaAgent chưa tạo Memory
                log.warning(json.dumps({"msg": "memory_id_unreadable", "code": _error_code(exc)}))
                raise YofinaError(
                    ErrorCode.MEMORY_UNAVAILABLE, "Bộ nhớ tạm thời không truy cập được."
                ) from exc

        return cls(
            resolve,
            region=region,
            max_pages=_setting("memory_list_max_pages", env, d),
            batch_size=_setting("memory_delete_batch_size", env, d),
            max_sessions=_setting("memory_events_max_sessions", env, d),
        )

    # --- hạ tầng ---------------------------------------------------------------------------------
    def memory_id(self) -> str | None:
        """Id của Memory, hoặc None khi chưa cấu hình (stack YofinaAgent chưa tạo). Lỗi đọc SSM: `MEMORY_UNAVAILABLE`."""
        if self._resolved is None:
            mid = self._memory_id() if callable(self._memory_id) else self._memory_id
            self._resolved = mid or None
        return self._resolved

    def _require_id(self) -> str:
        mid = self.memory_id()
        if not mid:
            raise YofinaError(ErrorCode.MEMORY_UNAVAILABLE, "Bộ nhớ chưa được cấu hình.")
        return mid

    @property
    def client(self) -> MemoryApi:
        if self._client is None:
            import boto3
            from botocore.config import Config as BotoConfig

            client = boto3.client(
                "bedrock-agentcore",
                region_name=self._region,
                config=BotoConfig(
                    connect_timeout=3,
                    read_timeout=10,
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
            _check_sdk(client)
            self._client = client
        return self._client

    def _call(self, op: str, **kwargs: Any) -> Mapping[str, Any]:
        try:
            return getattr(self.client, op)(**kwargs)
        except YofinaError:
            raise
        except Exception as exc:
            code = _error_code(exc)
            if code in _NOT_FOUND_CODES:
                raise
            log.warning(json.dumps({"msg": "memory_api_error", "op": op, "code": code}))
            raise YofinaError(
                ErrorCode.MEMORY_UNAVAILABLE, "Bộ nhớ tạm thời không truy cập được, thử lại sau."
            ) from exc

    # --- liệt kê ---------------------------------------------------------------------------------
    def _scope(self, sub: str, kind: str | None) -> dict[str, str]:
        if kind is None:
            return {"namespacePath": user_root(sub)}
        template = MEMORY_NAMESPACE_TEMPLATES[kind]
        if "{sessionId}" in template:
            return {"namespacePath": template.split("{sessionId}", 1)[0].replace("{actorId}", sub)}
        return {"namespace": namespace_for(kind, sub)}

    def _own(
        self, sub: str, summaries: Iterable[Mapping[str, Any]]
    ) -> list[tuple[Mapping[str, Any], str, str]]:
        """(bản ghi, namespace, loại) của các bản ghi THUỘC người gọi; bản ghi khác bị bỏ và ghi log."""
        out = []
        for rec in summaries:
            namespaces = rec.get("namespaces") or []
            ns = str(namespaces[0]) if namespaces else ""
            kind = kind_of_namespace(ns, sub) if ns else None
            rid = str(rec.get("memoryRecordId") or "")
            if kind is None or not RECORD_ID_RE.fullmatch(rid):
                log.warning(json.dumps({"msg": "memory_foreign_record_dropped"}))
                continue
            out.append((rec, ns, kind))
        return out

    def list_records(
        self, sub: str, *, kind: str | None = None, limit: Any = None, cursor: Any = None
    ) -> MemoryListResponse:
        """Một trang bản ghi của người gọi (`GET /memory`), mới nhất trước, chữ đã che PII."""
        if kind is not None and kind not in MEMORY_NAMESPACE_TEMPLATES:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "kind không hợp lệ.")
        try:
            n = MEMORY_LIST_LIMIT_DEFAULT if limit in (None, "") else int(limit)
        except (TypeError, ValueError):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "limit phải là số nguyên.") from None
        if not 1 <= n <= MEMORY_LIST_LIMIT_MAX:
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, f"limit phải trong 1..{MEMORY_LIST_LIMIT_MAX}."
            )
        if cursor is not None and (not isinstance(cursor, str) or not 1 <= len(cursor) <= 2048):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "cursor không hợp lệ.")
        kwargs: dict[str, Any] = {
            "memoryId": self._require_id(),
            "maxResults": n,
            **self._scope(sub, kind),
        }
        if cursor:
            kwargs["nextToken"] = cursor
        try:
            resp = self._call("list_memory_records", **kwargs)
        except YofinaError:
            raise
        except Exception as exc:  # cursor hỏng hoặc hết hạn
            raise YofinaError(ErrorCode.PARAMS_INVALID, "cursor không hợp lệ.") from exc
        records = []
        for rec, _ns, k in self._own(sub, resp.get("memoryRecordSummaries") or []):
            text = display_text(rec.get("content"))
            created = rec.get("createdAt")
            if not text or not isinstance(created, datetime):
                continue
            records.append(
                MemoryRecord(
                    record_id=str(rec["memoryRecordId"]),
                    kind=k,  # type: ignore[arg-type]
                    source=MEMORY_SOURCE_OF_KIND[k],  # type: ignore[arg-type]
                    text=text,
                    created_at=format_instant(created),
                )
            )
        records.sort(key=lambda r: r.created_at, reverse=True)
        token = resp.get("nextToken")
        return MemoryListResponse(
            records=records,
            next_cursor=token if isinstance(token, str) and 1 <= len(token) <= 2048 else None,
        )

    def iter_own(
        self, sub: str, *, kind: str | None = None
    ) -> list[tuple[Mapping[str, Any], str, str]]:
        """Mọi bản ghi của người gọi (tối đa `max_pages` trang 100 bản ghi), đã lọc namespace."""
        mid = self._require_id()
        out: list[tuple[Mapping[str, Any], str, str]] = []
        token: str | None = None
        for _ in range(self.max_pages):
            kwargs: dict[str, Any] = {
                "memoryId": mid,
                "maxResults": MEMORY_LIST_LIMIT_MAX,
                **self._scope(sub, kind),
            }
            if token:
                kwargs["nextToken"] = token
            resp = self._call("list_memory_records", **kwargs)
            out.extend(self._own(sub, resp.get("memoryRecordSummaries") or []))
            token = resp.get("nextToken")
            if not token:
                break
        return out

    # --- xóa -------------------------------------------------------------------------------------
    def delete_record(self, sub: str, record_id: str) -> MemoryRecordDeleteResponse:
        """`DELETE /memory/{record_id}`: đọc bản ghi, kiểm namespace thuộc người gọi rồi mới xóa (kèm namespace)."""
        if not isinstance(record_id, str) or not RECORD_ID_RE.fullmatch(record_id):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "record_id không hợp lệ.")
        mid = self._require_id()
        not_found = YofinaError(
            ErrorCode.MEMORY_RECORD_NOT_FOUND, "Không tìm thấy bản ghi bộ nhớ này."
        )
        try:
            rec = (
                self._call("get_memory_record", memoryId=mid, memoryRecordId=record_id).get(
                    "memoryRecord"
                )
                or {}
            )
        except YofinaError:
            raise
        except Exception:
            raise not_found from None
        namespaces = rec.get("namespaces") or []
        ns = str(namespaces[0]) if namespaces else ""
        if not ns or kind_of_namespace(ns, sub) is None:
            # Của người khác cũng trả như không có (không lộ là bản ghi tồn tại).
            log.warning(json.dumps({"msg": "memory_delete_foreign_denied"}))
            raise not_found
        try:
            self._call("delete_memory_record", memoryId=mid, memoryRecordId=record_id, namespace=ns)
        except YofinaError:
            raise
        except Exception:
            raise not_found from None
        return MemoryRecordDeleteResponse(record_id=record_id, deleted=True)

    def clear(self, sub: str) -> MemoryClearResponse:
        """Xóa MỌI bản ghi dài hạn dưới gốc namespace của người gọi và mọi sự kiện ngắn hạn của `actorId` = `sub`. Idempotent;
        lỗi từng phần tính vào `failed` (gọi lại để xóa nốt). Lỗi liệt kê thì `MEMORY_UNAVAILABLE`."""
        mid = self._require_id()
        own = self.iter_own(sub)
        deleted = failed = 0
        for i in range(0, len(own), self.batch_size):
            chunk = own[i : i + self.batch_size]
            try:
                resp = self._call(
                    "batch_delete_memory_records",
                    memoryId=mid,
                    records=[
                        {"memoryRecordId": str(rec["memoryRecordId"]), "namespace": ns}
                        for rec, ns, _k in chunk
                    ],
                )
            except YofinaError:
                failed += len(chunk)
                continue
            ok = len(resp.get("successfulRecords") or [])
            bad = len(resp.get("failedRecords") or [])
            deleted += ok
            failed += bad if ok + bad else len(chunk) - ok
        events, ev_failed = self._clear_events(mid, sub)
        result = MemoryClearResponse(
            deleted_records=deleted, deleted_events=events, failed=failed + ev_failed
        )
        log.info(json.dumps({"msg": "memory_cleared", **result.model_dump()}))
        return result

    def _clear_events(self, mid: str, sub: str) -> tuple[int, int]:
        deleted = failed = 0
        token: str | None = None
        seen = 0
        while seen < self.max_sessions:
            kwargs: dict[str, Any] = {"memoryId": mid, "actorId": sub, "maxResults": 100}
            if token:
                kwargs["nextToken"] = token
            resp = self._call("list_sessions", **kwargs)
            sessions = list(resp.get("sessionSummaries") or [])
            for s in sessions:
                seen += 1
                if s.get("actorId") not in (None, sub):
                    continue
                d, f = self._clear_session(mid, sub, str(s.get("sessionId") or ""))
                deleted, failed = deleted + d, failed + f
            token = resp.get("nextToken")
            if not token or not sessions:
                break
        return deleted, failed

    def _clear_session(self, mid: str, sub: str, session_id: str) -> tuple[int, int]:
        if not session_id:
            return 0, 0
        deleted = failed = 0
        token: str | None = None
        for _ in range(self.max_pages):
            kwargs: dict[str, Any] = {
                "memoryId": mid,
                "actorId": sub,
                "sessionId": session_id,
                "includePayloads": False,
                "maxResults": 100,
            }
            if token:
                kwargs["nextToken"] = token
            resp = self._call("list_events", **kwargs)
            for e in resp.get("events") or []:
                try:
                    self._call(
                        "delete_event",
                        memoryId=mid,
                        actorId=sub,
                        sessionId=session_id,
                        eventId=str(e["eventId"]),
                    )
                    deleted += 1
                except Exception:
                    failed += 1
            token = resp.get("nextToken")
            if not token:
                break
        return deleted, failed


def _check_sdk(client: Any) -> None:
    """boto3 đi kèm runtime Lambda có thể cũ hơn API Memory hiện hành (namespacePath, IngestData...): báo rõ thay vì lỗi tham số."""
    try:
        members = client.meta.service_model.operation_model("ListMemoryRecords").input_shape.members
    except Exception as exc:
        members = {}
        log.warning(json.dumps({"msg": "memory_sdk_unsupported", "detail": type(exc).__name__}))
    if "namespacePath" not in members:
        import botocore

        log.error(json.dumps({"msg": "memory_sdk_unsupported", "botocore": botocore.__version__}))
        raise YofinaError(ErrorCode.MEMORY_UNAVAILABLE, "Bộ nhớ tạm thời không truy cập được.")


# --- giờ không muốn được nhắc (cho cổng bản tin) ---------------------------------------------------
@dataclass(frozen=True)
class QuietHours:
    """Các khung giờ người dùng không muốn được nhắc, theo giờ địa phương của ứng dụng (`app_timezone`).

    `windows`: các khung `[bắt đầu, kết thúc)` theo giờ 0..24, có thể vắt qua nửa đêm (`(22, 5)` là 22 giờ tới 5 giờ sáng hôm sau).
    `sources`: chữ của các bản ghi sở thích đã cho ra khung giờ (đã che PII), để giải thích vì sao bản tin bị dời.
    `available`: False khi không đọc được bộ nhớ (chưa cấu hình, lỗi): cổng bản tin coi như không có giờ im lặng và có thể ghi lý do.
    """

    windows: tuple[tuple[int, int], ...] = ()
    sources: tuple[str, ...] = ()
    available: bool = True

    def contains(self, hour: int) -> bool:
        """Giờ `hour` (0..23) có rơi vào khung nào không."""
        for start, end in self.windows:
            if start == end:
                continue
            if (start < end and start <= hour < end) or (
                start > end and (hour >= start or hour < end)
            ):
                return True
        return False


_FILLERS = r"(?:\s+(?:can|nen|duoc|hay|muon|thich|minh|toi|em|tao|nua|co|phai|bao gio|gio|nhe|bi|ai|gi|them|lai|nhan|se))*"
_NO_REMIND = re.compile(
    rf"\b(?:dung|khong|ko|tranh|thoi|khong muon|khong thich|ghet|han che){_FILLERS}\s+"
    r"(?:nhac|bao|thong bao|gui|lam phien|nhan tin|ping)\b"
)
_PM_WORDS = ("chieu", "toi", "dem")


def _hour(num: str, part: str | None) -> int | None:
    h = int(num)
    if not 0 <= h <= 24:
        return None
    if part in _PM_WORDS and h < 12 and not (part == "dem" and h < 5):
        h += 12
    return h % 24 if h != 24 else 24


def parse_quiet_hours(texts: Iterable[str], day_parts: Mapping[str, Iterable[int]]) -> QuietHours:
    """Khung giờ im lặng từ các câu sở thích tiếng Việt ("đừng nhắc mình buổi sáng", "không thông báo sau 22h", "đừng gửi gì từ
    22 giờ đến 7 giờ"). Câu không có ý "đừng nhắc" thì bỏ qua. Hàm thuần."""
    parts = {k: tuple(int(x) for x in v) for k, v in day_parts.items()}
    part_re = "|".join(sorted(map(re.escape, parts), key=len, reverse=True))
    pm = "(?:\\s*(sang|trua|chieu|toi|dem))?"
    range_re = re.compile(
        rf"\btu\s+(\d{{1,2}})\s*(?:h|gio)?{pm}\s*(?:den|toi|-)\s*(\d{{1,2}})\s*(?:h|gio){pm}"
    )
    before_re = re.compile(rf"\btruoc\s+(\d{{1,2}})\s*(?:h|gio){pm}")
    after_re = re.compile(rf"\bsau\s+(\d{{1,2}})\s*(?:h|gio){pm}")
    word_re = re.compile(rf"\b({part_re})\b") if part_re else None
    windows: list[tuple[int, int]] = []
    sources: list[str] = []
    for text in texts:
        f = fold(text)
        if not _NO_REMIND.search(f):
            continue
        tail = f  # cụm giờ có thể đứng trước hay sau động từ ("buổi sáng đừng nhắc", "đừng nhắc buổi sáng")
        found: list[tuple[int, int]] = []
        consumed: list[tuple[int, int]] = []
        for r in range_re.finditer(tail):
            a, b = _hour(r.group(1), r.group(2) or r.group(4)), _hour(r.group(3), r.group(4))
            if a is not None and b is not None:
                found.append((a, b))
                consumed.append(r.span())
        for r in before_re.finditer(tail):
            if any(s <= r.start() < e for s, e in consumed):
                continue
            h = _hour(r.group(1), r.group(2))
            if h is not None and h > 0:
                found.append((0, h))
                consumed.append(r.span())
        for r in after_re.finditer(tail):
            if any(s <= r.start() < e for s, e in consumed):
                continue
            h = _hour(r.group(1), r.group(2))
            if h is not None and h < 24:
                found.append((h, 24))
                consumed.append(r.span())
        if word_re is not None:
            for r in word_re.finditer(tail):
                if any(s <= r.start() < e for s, e in consumed):
                    continue
                a, b = parts[r.group(1)]
                found.append((a, b))
        if found:
            sources.append(" ".join(text.split())[:200])
            for w in found:
                if w not in windows:
                    windows.append(w)
    return QuietHours(windows=tuple(windows), sources=tuple(sources))


def quiet_hours(sub: str, *, store: MemoryStore | None = None) -> QuietHours:
    """Giờ người dùng `sub` (sub của Cognito, đã xác thực) không muốn được nhắc, đọc từ các bản ghi SỞ THÍCH trong bộ nhớ dài hạn.

    Dành cho cổng bản tin (FR13): trước khi đặt giờ hiện một bản tin, gọi `quiet_hours(sub).contains(giờ)` và dời sang khung khác nếu
    trùng. Chỉ đọc namespace sở thích của chính `sub` (`ListMemoryRecords`, không semantic search nên không tốn lượt truy xuất),
    không bao giờ ném lỗi: Memory chưa cấu hình hoặc lỗi thì trả `QuietHours(available=False)` (không có khung nào). Test truyền
    `store` dựng từ client giả (`MemoryStore("mem-id", client=...)`).
    """
    d = load_defaults()
    st = store or MemoryStore.from_env()
    try:
        if not st.memory_id():
            return QuietHours(available=False)
        recs = st.iter_own(sub, kind="preference")[: int(d["quiet_hours_max_records"])]
    except Exception as exc:
        log.warning(json.dumps({"msg": "quiet_hours_unavailable", "code": _error_code(exc)}))
        return QuietHours(available=False)
    texts = [display_text(rec.get("content")) for rec, _ns, _k in recs]
    return parse_quiet_hours([t for t in texts if t], d["day_parts"])


__all__ = [
    "MemoryApi",
    "MemoryStore",
    "QuietHours",
    "display_text",
    "load_defaults",
    "parse_quiet_hours",
    "quiet_hours",
]
