"""Xóa dữ liệu của tôi (phase 5, proposal §7): kiểu của `POST /me/delete-data` và nhật ký `data_deletions` (migration 0053).

Luồng (ADR-0002, cùng khóa HMAC và bảng `jti` với mọi thao tác ghi): `POST /me/delete-data/confirmations` với
`{tool: "delete_my_data", params: {scope: "all"}}` cấp token dùng một lần sau khi người dùng bấm xác nhận; `POST /me/delete-data`
kèm token thì Lambda (1) ghi một dòng `data_deletions` trạng thái `running`, (2) xóa S3 (mọi object dưới tiền tố `{sub}/` của
bucket nạp), (3) xóa AgentCore Memory (liệt kê theo gốc namespace của người dùng rồi xóa từng bản ghi, và sự kiện ngắn hạn theo
`actorId`), (4) gọi `app_delete_user_data` (xóa MỌI dòng của người dùng ở Aurora, kể cả `audit_events` và `users`, trong một
transaction), (5) cập nhật dòng nhật ký: `done` khi cả ba bước xong, `partial` khi có bước lỗi (gọi lại thì làm tiếp các bước
chưa xong), `failed` khi bước Aurora lỗi. Nhật ký KHÔNG chứa dữ liệu đã xóa, chỉ số lượng theo bước. Sau khi xóa, đăng nhập lại
với cùng tài khoản Cognito là một tài khoản trắng (onboarding lại).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yofina_core import wallet
from yofina_core.blocks import IsoDateTime, Uuid

#: Trạng thái của một lần xóa (cột `data_deletions.status`).
DATA_DELETION_STATUSES = ("running", "done", "partial", "failed")
#: Ba nơi giữ dữ liệu người dùng, theo thứ tự Lambda xóa (Aurora cuối cùng vì nhật ký nằm ngoài các bảng bị xóa và vì sau
#: Aurora không còn hồ sơ để đọc tiền tố hay namespace).
DATA_DELETION_STEPS = ("s3", "memory", "aurora")
DELETION_STEP_STATUSES = ("pending", "done", "failed", "skipped")
#: Phạm vi xóa: chỉ có "tất cả" (không xóa từng phần ở hợp đồng này; xóa bộ nhớ riêng thì dùng `DELETE /memory`).
DATA_DELETION_SCOPES = wallet.DATA_DELETION_SCOPES

DeletionStatus = Literal["running", "done", "partial", "failed"]
DeletionStepStatus = Literal["pending", "done", "failed", "skipped"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DeletionStep(_Strict):
    status: DeletionStepStatus
    deleted: Annotated[int, Field(ge=0)] | None = None
    error_code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]*$", max_length=40)] | None = None

    @model_validator(mode="after")
    def _error_iff_failed(self) -> DeletionStep:
        if (self.status == "failed") != (self.error_code is not None):
            raise ValueError("error_code có khi và chỉ khi bước failed")
        if self.status == "done" and self.deleted is None:
            raise ValueError("bước done phải có số đã xóa")
        return self


class DeletionSteps(_Strict):
    s3: DeletionStep
    memory: DeletionStep
    aurora: DeletionStep


class DataDeletion(_Strict):
    """Một lần "Xóa dữ liệu của tôi" (dòng `data_deletions`, phản hồi của `POST /me/delete-data`)."""

    deletion_id: Uuid
    status: DeletionStatus
    scope: Literal["all"]
    requested_at: IsoDateTime
    finished_at: IsoDateTime | None = None
    steps: DeletionSteps

    @model_validator(mode="after")
    def _status_matches_steps(self) -> DataDeletion:
        """`done`: cả ba bước done hoặc skipped; `failed`: bước Aurora failed; `partial`: Aurora xong nhưng có bước khác failed;
        `running`: còn bước pending và chưa có `finished_at`. Kết thúc (khác running) thì có `finished_at`."""
        st = {k: getattr(self.steps, k).status for k in DATA_DELETION_STEPS}
        finished = self.status != "running"
        if finished != (self.finished_at is not None):
            raise ValueError("finished_at có khi và chỉ khi lần xóa đã kết thúc")
        if self.status == "running" and "pending" not in st.values():
            raise ValueError("running thì còn ít nhất một bước pending")
        if finished and "pending" in st.values():
            raise ValueError("đã kết thúc thì không còn bước pending")
        if self.status == "done" and not set(st.values()) <= {"done", "skipped"}:
            raise ValueError("done thì mọi bước done hoặc skipped")
        if self.status == "failed" and st["aurora"] != "failed":
            raise ValueError("failed nghĩa là bước Aurora lỗi")
        if self.status == "partial" and not (st["aurora"] == "done" and "failed" in st.values()):
            raise ValueError("partial nghĩa là Aurora đã xóa và có bước khác lỗi")
        return self
