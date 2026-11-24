"""REST quyền riêng tư (phase 5, luồng B, proposal §7): bộ nhớ của tôi (`/memory*`) và "Xóa dữ liệu của tôi" (`/me/delete-data*`).

Nối vào `rest_api._dispatch` bằng MỘT khối chuyển tiếp cho tiền tố `/memory` và `/me/delete-data`. Danh tính CHỈ là `sub` do
`rest_api` lấy từ claim của JWT authorizer; không endpoint nào đọc người dùng từ thân yêu cầu hay đường dẫn.

- `GET /memory?kind&limit&cursor`, `DELETE /memory/{record_id}`, `DELETE /memory`: `memory_store.MemoryStore` (namespace theo `sub`,
  kiểm lại namespace mọi bản ghi). Không qua token (không đổi số dư; giao diện hỏi lại trước khi gọi).
- `POST /me/delete-data/confirmations`: cấp token cho `delete_my_data` (cùng khóa HMAC, bảng `jti` với mọi thao tác ghi, ADR-0002),
  kèm bản xem trước những gì sẽ bị xóa. Không ghi gì.
- `POST /me/delete-data`: kiểm và tiêu token, rồi xóa theo thứ tự S3 (mọi object dưới `<tiền tố nạp><sub>/` của bucket nạp), Memory
  (như `DELETE /memory`), Aurora (`app_delete_user_data`, một transaction, cùng transaction với việc chốt dòng nhật ký). Trạng thái
  từng bước ghi vào `data_deletions` sau MỖI bước, nên Lambda chết giữa chừng thì lần gọi sau (token mới) nhận lại dòng `running` đã
  quá hạn thuê (`privacy_deletion_lease_seconds`) và làm tiếp bước chưa xong. Đang có lần `running` còn hạn thì trả lần đó (không chạy
  song song). Mọi bước idempotent: chạy lại sau `partial` hay `failed` vẫn xong.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from yofina_core.blocks import format_instant
from yofina_core.confirm import ConfirmService, hash_normalized_params
from yofina_core.db import DataApi, Row
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.memory import ACTOR_ID_RE
from yofina_core.params import ParamsError, normalize_params
from yofina_core.privacy import DATA_DELETION_STEPS, DataDeletion
from yofina_core.wallet import DELETE_MY_DATA
from yofina_ledger.memory_store import MemoryStore, load_defaults

log = logging.getLogger("yofina.ledger.privacy")

ROUTE_PREFIXES = ("GET /memory", "DELETE /memory", "POST /me/delete-data")


# --- nhật ký data_deletions --------------------------------------------------------------------------
_COLS = "id::text AS id, status, steps, requested_at, finished_at, updated_at"


class DeletionRepo:
    """Đọc và ghi `data_deletions` (RLS theo `app.user_id`; mọi câu lệnh vẫn có `user_id = :uid`)."""

    def __init__(self, db: DataApi) -> None:
        self.db = db

    def running(self, uid: str) -> Row | None:
        with self.db.transaction(uid) as tx:
            rows = tx.execute(
                f"SELECT {_COLS} FROM data_deletions WHERE user_id = :uid AND status = 'running' LIMIT 1",
                {"uid": uid},
            )
        return rows[0] if rows else None

    def create(self, uid: str, steps: dict[str, Any], trace_id: str) -> Row:
        with self.db.transaction(uid) as tx:
            rows = tx.execute(
                "INSERT INTO data_deletions (user_id, scope, status, steps, trace_id) "
                f"VALUES (:uid, 'all', 'running', CAST(:steps AS jsonb), :trace) RETURNING {_COLS}",
                {"uid": uid, "steps": steps, "trace": trace_id[:64] or None},
            )
        return rows[0]

    def save(
        self,
        uid: str,
        deletion_id: str,
        steps: dict[str, Any],
        status: str,
        finished_at: datetime | None,
    ) -> Row:
        with self.db.transaction(uid) as tx:
            return self._save(tx, uid, deletion_id, steps, status, finished_at)

    @staticmethod
    def _save(
        tx: Any,
        uid: str,
        did: str,
        steps: dict[str, Any],
        status: str,
        finished_at: datetime | None,
    ) -> Row:
        # Data API gửi mọi `stringValue` không có `typeHint` dưới dạng text (datetime của `yofina_core.db` cũng vậy): cột không phải
        # text phải CAST tường minh, nếu không Postgres báo 42804 ("finished_at is of type timestamp with time zone but expression is
        # of type text") và cả lần xóa lùi ở bước Aurora.
        rows = tx.execute(
            "UPDATE data_deletions SET steps = CAST(:steps AS jsonb), status = :status, "
            "finished_at = CAST(:fin AS timestamptz), updated_at = now() "
            f"WHERE id = CAST(:id AS uuid) AND user_id = :uid RETURNING {_COLS}",
            {"steps": steps, "status": status, "fin": finished_at, "id": did, "uid": uid},
        )
        if not rows:
            raise YofinaError(ErrorCode.INTERNAL_ERROR, "Không cập nhật được nhật ký xóa dữ liệu.")
        return rows[0]

    def delete_aurora_and_finish(
        self,
        uid: str,
        deletion_id: str,
        finish: Callable[[int], tuple[dict[str, Any], str, datetime]],
    ) -> Row:
        """Xóa mọi dòng của người dùng (`app_delete_user_data`) VÀ chốt dòng nhật ký trong CÙNG một transaction: hoặc cả hai, hoặc không."""
        with self.db.transaction(uid) as tx:
            rows = tx.execute(
                "SELECT relname, deleted FROM app_delete_user_data(:uid, CAST(:did AS uuid))",
                {"uid": uid, "did": deletion_id},
            )
            total = sum(int(r["deleted"]) for r in rows)
            steps, status, fin = finish(total)
            return self._save(tx, uid, deletion_id, steps, status, fin)


# --- S3 ------------------------------------------------------------------------------------------------
class S3Deleter:
    """Xóa mọi object dưới một tiền tố của bucket nạp (bucket không bật versioning nên DeleteObjects là xóa hẳn)."""

    def __init__(
        self,
        bucket: str | None,
        upload_prefix: str,
        client: Any = None,
        *,
        batch_size: int = 1000,
        region: str | None = None,
    ):
        self.bucket = bucket or None
        self.upload_prefix = upload_prefix
        self._client = client
        self.batch_size = min(max(batch_size, 1), 1000)
        self._region = region

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("s3", region_name=self._region)
        return self._client

    def prefix_of(self, sub: str) -> str:
        if not ACTOR_ID_RE.fullmatch(sub or ""):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Người dùng không hợp lệ cho tiền tố tệp.")
        return f"{self.upload_prefix}{sub}/"

    def delete_user_objects(self, sub: str) -> int:
        prefix = self.prefix_of(sub)
        deleted = 0
        token: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "Bucket": self.bucket,
                "Prefix": prefix,
                "MaxKeys": self.batch_size,
            }
            if token:
                kwargs["ContinuationToken"] = token
            resp = self.client.list_objects_v2(**kwargs)
            keys = [
                o["Key"]
                for o in resp.get("Contents") or []
                if str(o.get("Key", "")).startswith(prefix)
            ]
            if keys:
                out = self.client.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": [{"Key": k} for k in keys], "Quiet": True},
                )
                errors = out.get("Errors") or []
                if errors:
                    raise RuntimeError(f"S3 không xóa được {len(errors)} object")
                deleted += len(keys)
            if not resp.get("IsTruncated"):
                return deleted
            token = resp.get("NextContinuationToken")


# --- xóa dữ liệu của tôi ----------------------------------------------------------------------------
def _pending_steps() -> dict[str, Any]:
    return {k: {"status": "pending"} for k in DATA_DELETION_STEPS}


def _step_ok(n: int) -> dict[str, Any]:
    return {"status": "done", "deleted": int(n)}


def _step_failed(code: str) -> dict[str, Any]:
    return {"status": "failed", "error_code": code[:40]}


def _final_status(steps: Mapping[str, Any]) -> str:
    st = {k: steps[k]["status"] for k in DATA_DELETION_STEPS}
    if st["aurora"] == "failed":
        return "failed"
    if "failed" in st.values():
        return "partial"
    return "done"


def _error_code_of(exc: BaseException, default: str) -> str:
    if isinstance(exc, YofinaError):
        return str(exc.code)
    return default


def to_wire(row: Row) -> dict[str, Any]:
    """Dòng `data_deletions` -> `DataDeletion` (kiểm bằng Pydantic của hợp đồng)."""
    steps = row["steps"] if isinstance(row["steps"], dict) else json.loads(row["steps"])
    model = DataDeletion.model_validate(
        {
            "deletion_id": row["id"],
            "status": row["status"],
            "scope": "all",
            "requested_at": format_instant(row["requested_at"]),
            **(
                {"finished_at": format_instant(row["finished_at"])}
                if row.get("finished_at")
                else {}
            ),
            "steps": {k: steps[k] for k in DATA_DELETION_STEPS},
        }
    )
    return model.model_dump(exclude_none=True)


class PrivacyService:
    def __init__(
        self,
        *,
        repo: DeletionRepo,
        confirm: ConfirmService,
        memory: MemoryStore,
        s3: S3Deleter,
        lease_seconds: int,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repo, self.confirm, self.memory, self.s3 = repo, confirm, memory, s3
        self.lease_seconds = lease_seconds
        self.now = now

    @classmethod
    def from_ledger(cls, service: Any, env: Mapping[str, str] | None = None) -> PrivacyService:
        env = os.environ if env is None else env
        d = load_defaults()

        def setting(name: str) -> int:
            raw = env.get(f"YOFINA_{name.upper()}")
            return int(raw) if raw not in (None, "") else int(d[name])

        region = env.get("YOFINA_REGION") or None
        return cls(
            repo=DeletionRepo(service.repo.db),
            confirm=service.confirm,
            memory=MemoryStore.from_env(env),
            s3=S3Deleter(
                env.get("YOFINA_INGEST_BUCKET") or None,
                env.get("YOFINA_INGEST_UPLOAD_PREFIX") or "",
                batch_size=setting("privacy_s3_delete_batch_size"),
                region=region,
            ),
            lease_seconds=setting("privacy_deletion_lease_seconds"),
        )

    # --- token --------------------------------------------------------------------------------------
    @staticmethod
    def _normalize(tool: Any, params: Any) -> dict[str, Any]:
        if tool != DELETE_MY_DATA:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Tool không được hỗ trợ ở đường dẫn này.")
        if not isinstance(params, Mapping):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Thiếu params.")
        try:
            return normalize_params(DELETE_MY_DATA, params)
        except ParamsError as exc:
            raise YofinaError(ErrorCode.PARAMS_INVALID, str(exc)) from exc

    def issue_confirmation(
        self, sub: str, *, tool: Any, params: Any, client_params_hash: Any
    ) -> dict[str, Any]:
        """`POST /me/delete-data/confirmations`: token + bản xem trước. Không ghi gì."""
        norm = self._normalize(tool, params)
        digest = hash_normalized_params(DELETE_MY_DATA, norm)
        if client_params_hash and client_params_hash != digest:
            raise YofinaError(
                ErrorCode.PARAMS_MISMATCH, "Tham số khác với yêu cầu bạn đang xem; hãy mở lại."
            )
        issued = self.confirm.issue(sub, DELETE_MY_DATA, norm)
        return {
            "confirm_token": issued.token,
            "expires_at": format_instant(issued.expires_at),
            "ttl_seconds": issued.ttl_seconds,
            "tool": issued.tool,
            "params": issued.params,
            "params_hash": issued.params_hash,
            "preview": {
                "summary": "Xóa vĩnh viễn toàn bộ dữ liệu của bạn ở Yofina",
                "changes": [
                    {"label": "Hồ sơ, hũ, sổ cái, lộ trình", "after": "Xóa vĩnh viễn"},
                    {"label": "Hội thoại và bản ghi lượt", "after": "Xóa vĩnh viễn"},
                    {"label": "Tệp đã nạp (ảnh, CSV)", "after": "Xóa vĩnh viễn"},
                    {"label": "Bộ nhớ của trợ lý", "after": "Xóa vĩnh viễn"},
                    {
                        "label": "Tài khoản đăng nhập",
                        "before": "Giữ",
                        "after": "Giữ, đăng nhập lại là tài khoản trắng",
                    },
                ],
                "warnings": ["Không hoàn tác được: dữ liệu đã xóa không khôi phục lại được."],
            },
        }

    # --- xóa --------------------------------------------------------------------------------------------
    def delete_my_data(
        self, sub: str, *, tool: Any, params: Any, confirm_token: Any, trace_id: str
    ) -> dict[str, Any]:
        """`POST /me/delete-data`: kiểm và tiêu token rồi chạy (hoặc làm tiếp) lần xóa. Trả `DataDeletion`."""
        norm = self._normalize(tool, params)
        if confirm_token in (None, ""):
            raise YofinaError(
                ErrorCode.NEEDS_CONFIRMATION, "Thao tác này cần bạn xác nhận trước khi thực hiện."
            )
        if not isinstance(confirm_token, str):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "confirm_token phải là chuỗi.")
        self.confirm.verify_and_consume(confirm_token, sub=sub, tool=DELETE_MY_DATA, params=norm)

        row = self.repo.running(sub)
        if row is not None:
            age = (self.now() - row["updated_at"]).total_seconds()
            if age < self.lease_seconds:
                log.info(json.dumps({"msg": "data_deletion_in_progress", "trace_id": trace_id}))
                return to_wire(row)
            log.warning(
                json.dumps(
                    {"msg": "data_deletion_resumed", "trace_id": trace_id, "age_s": int(age)}
                )
            )
        else:
            try:
                row = self.repo.create(sub, _pending_steps(), trace_id)
            except YofinaError:
                again = self.repo.running(
                    sub
                )  # lần gọi song song vừa tạo dòng running (chỉ mục duy nhất một phần)
                if again is None:
                    raise
                return to_wire(again)
        return self._run(sub, row, trace_id)

    def _run(self, sub: str, row: Row, trace_id: str) -> dict[str, Any]:
        did = str(row["id"])
        steps = dict(row["steps"] if isinstance(row["steps"], dict) else json.loads(row["steps"]))
        for name in ("s3", "memory"):
            if steps.get(name, {}).get("status") in ("done", "skipped"):
                continue
            steps[name] = self._s3_step(sub) if name == "s3" else self._memory_step(sub)
            row = self.repo.save(
                sub, did, steps, "running", None
            )  # ghi tiến độ: chết giữa chừng thì lần sau làm tiếp
        try:

            def finish(total: int) -> tuple[dict[str, Any], str, datetime]:
                done = {**steps, "aurora": _step_ok(total)}
                return done, _final_status(done), self.now()

            row = self.repo.delete_aurora_and_finish(sub, did, finish)
        except Exception as exc:
            log.error(
                json.dumps(
                    {
                        "msg": "data_deletion_aurora_failed",
                        "trace_id": trace_id,
                        "error": type(exc).__name__,
                    }
                )
            )
            steps["aurora"] = _step_failed(_error_code_of(exc, "INTERNAL_ERROR"))
            row = self.repo.save(sub, did, steps, "failed", self.now())
        out = to_wire(row)
        log.info(
            json.dumps(
                {
                    "msg": "data_deletion_finished",
                    "trace_id": trace_id,
                    "status": out["status"],
                    "steps": {k: out["steps"][k]["status"] for k in DATA_DELETION_STEPS},
                }
            )
        )
        return out

    def _s3_step(self, sub: str) -> dict[str, Any]:
        if not self.s3.bucket:
            return {"status": "skipped"}
        try:
            return _step_ok(self.s3.delete_user_objects(sub))
        except Exception as exc:
            log.warning(json.dumps({"msg": "data_deletion_s3_failed", "error": type(exc).__name__}))
            return _step_failed(_error_code_of(exc, "STORAGE_UNAVAILABLE"))

    def _memory_step(self, sub: str) -> dict[str, Any]:
        try:
            if not self.memory.memory_id():
                return {"status": "skipped"}  # chưa có Memory resource: không có gì để xóa
            res = self.memory.clear(sub)
        except Exception as exc:
            log.warning(
                json.dumps({"msg": "data_deletion_memory_failed", "error": type(exc).__name__})
            )
            return _step_failed(_error_code_of(exc, "MEMORY_UNAVAILABLE"))
        if res.failed:
            return _step_failed(ErrorCode.MEMORY_UNAVAILABLE.value)
        return _step_ok(res.deleted_records + res.deleted_events)


# --- định tuyến ------------------------------------------------------------------------------------
_SERVICE: PrivacyService | None = None


def _privacy(service: Any) -> PrivacyService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = PrivacyService.from_ledger(service)
    return _SERVICE


def _body(event: Mapping[str, Any]) -> dict[str, Any]:
    from yofina_ledger.rest_api import _body as parse

    return parse(event)


def handles(route: str) -> bool:
    return route.startswith(ROUTE_PREFIXES)


def dispatch(
    route: str,
    event: Mapping[str, Any],
    sub: str,
    trace_id: str,
    service: Any,
    *,
    privacy: PrivacyService | None = None,
) -> tuple[int, dict[str, Any]]:
    p = privacy or _privacy(service)
    if route == "GET /memory":
        q = event.get("queryStringParameters") or {}
        return 200, p.memory.list_records(
            sub, kind=q.get("kind"), limit=q.get("limit"), cursor=q.get("cursor")
        ).model_dump(exclude_none=True)
    if route == "DELETE /memory":
        return 200, p.memory.clear(sub).model_dump()
    if route.startswith("DELETE /memory/"):
        record_id = (event.get("pathParameters") or {}).get("record_id") or route.removeprefix(
            "DELETE /memory/"
        )
        return 200, p.memory.delete_record(sub, str(record_id)).model_dump()
    if route == "POST /me/delete-data/confirmations":
        body = _body(event)
        return 200, p.issue_confirmation(
            sub,
            tool=body.get("tool"),
            params=body.get("params"),
            client_params_hash=body.get("params_hash"),
        )
    if route == "POST /me/delete-data":
        body = _body(event)
        return 200, p.delete_my_data(
            sub,
            tool=body.get("tool"),
            params=body.get("params"),
            confirm_token=body.get("confirm_token"),
            trace_id=trace_id,
        )
    raise YofinaError(ErrorCode.PARAMS_INVALID, "Đường dẫn không tồn tại.")
