"""Ý định `ingest` (phase 5, F6): "mình vừa nạp ảnh / sao kê" -> trạng thái lần nạp gần nhất và bảng duyệt dòng (khối `ingest_review`).

Luồng (mã điều khiển, KHÔNG có lượt model nào):

    hỏi cách nạp (router: `ingest_action="how_to"`)  -> `ingest___start_job` -> câu hướng dẫn (màn Nạp dữ liệu, loại tệp, giới hạn)
    còn lại                                          -> `ingest___get_job_status` (lần nạp gần nhất)
        đang đọc     -> câu tiến độ
        chờ duyệt    -> khối `ingest_review` + câu đếm dòng (chọn sẵn, cần duyệt, trùng)
        đã chốt      -> khối `ingest_review` + khối `coverage_change` + câu độ phủ trước và sau
        hỏng/từ chối -> câu lý do theo mã lỗi (INGEST_NO_TRANSACTIONS: theo lý do con `error_reason`)
        chưa nạp lần nào (INGEST_JOB_NOT_FOUND) -> như câu hỏi cách nạp

Nội dung tệp chỉ là DỮ LIỆU: đối tác và nội dung của từng dòng (đã che PII ở bước nạp) chỉ đi vào khối để người dùng xem, KHÔNG vào lời nhắc
của model nào, không vào câu trả lời, không vào bản gọn của `TOOL_CALL_RESULT`; câu trả lời dựng bằng mã từ số đếm và trạng thái của tool.
Agent KHÔNG chốt dòng: `confirm_rows` có token chỉ đi từ màn hình (bảng duyệt gửi `POST /ingest/confirmations` rồi `POST /ingest/actions`).

`Turn.call_tool` chỉ biết các target của `AgentSettings.tool` (ledger, forecast, planner, knowledge, audit), nên module này tự phát cùng
chuỗi event AG-UI cho tool của target `ingest` (`call_ingest_tool`).
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Callable, Mapping
from datetime import date
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from yofina_agent import events as ev
from yofina_agent import notices
from yofina_agent.tools import ContractMismatch, ToolKind, ToolOutcome
from yofina_core import blocks as B
from yofina_core.errors import ErrorCode
from yofina_core.ingest import TARGET

if TYPE_CHECKING:
    from yofina_agent.schemas import IntentResult
    from yofina_agent.turn import Turn

log = logging.getLogger("yofina.agent.ingest")

_TRANSIENT = {
    ErrorCode.DATABASE_UNAVAILABLE.value,
    ErrorCode.INTERNAL_ERROR.value,
    ErrorCode.RATE_LIMITED.value,
}
_KIND_WORD = {"image": "ảnh", "csv": "tệp sao kê"}
_MIME_LABEL = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/webp": "WebP",
    "text/csv": "CSV",
    "application/vnd.ms-excel": "CSV",
}
#: lý do của lần nạp hỏng hay bị từ chối, theo `error_code` của job (không đọc `error_message` vì tool không trả nó)
_JOB_ERROR_TEXT = {
    ErrorCode.INGEST_NOT_FINANCIAL.value: "tệp không giống biên lai, tin nhắn hay sao kê giao dịch nên mình không đọc được khoản nào",
    ErrorCode.INGEST_DUPLICATE_FILE.value: "tệp này đã được nạp trước đó rồi, mình không ghi trùng",
    ErrorCode.INGEST_TOO_LARGE.value: "tệp lớn hơn giới hạn cho phép hoặc có quá nhiều dòng",
    ErrorCode.INGEST_UNSUPPORTED_TYPE.value: "mình chưa đọc được loại tệp này",
    ErrorCode.MODEL_BUDGET_EXCEEDED.value: "hôm nay đã hết lượt đọc tệp bằng AI",
}
_DEFAULT_JOB_ERROR = "mình chưa xử lý được tệp này"
#: INGEST_NO_TRANSACTIONS: tệp là chứng từ tài chính nhưng không còn giao dịch nào để thêm. Câu báo theo lý do con (`error_reason` của job,
#: enum `IngestErrorReason` của hợp đồng); vắng lý do thì câu chung của mã.
_NO_TX_REASON_TEXT = {
    "unexecuted_form": "đây là màn xác nhận hay biểu mẫu chưa thực hiện nên chưa có giao dịch nào",
    "not_completed": "giao dịch trong tệp chưa thành công hoặc còn đang xử lý",
    "own_account_transfer": "tệp chỉ có tiền chuyển giữa các tài khoản của chính bạn, không có khoản chi hay thu nào",
    "cash_withdrawal": "tệp chỉ có rút tiền mặt, mà Yofina không theo dõi tiền mặt",
    "no_amount": "mình không đọc được số tiền của giao dịch nào trong tệp",
    "no_rows": "mình không thấy khoản tiền đã giao dịch nào trong tệp",
}
_DEFAULT_NO_TX = "tệp là chứng từ tài chính nhưng không còn giao dịch nào sau khi lọc"


def _mb(n: int) -> str:
    text = f"{n / 1_000_000:.2f}".rstrip("0").rstrip(".")
    return f"{text.replace('.', ',')} MB"


def _pct(x: float) -> str:
    return f"{round(float(x) * 100)}%"


# --- gọi tool của target `ingest` ---------------------------------------------------------------------------------------------
async def call_ingest_tool(
    turn: Turn,
    short_name: str,
    args: dict[str, Any],
    *,
    compact: Callable[[ToolOutcome], dict[str, Any]],
    block: Callable[[ToolOutcome, str], list[Any]] | None = None,
) -> tuple[ToolOutcome, list[Any]]:
    """Như `Turn.call_tool_retry` cho tool `ingest___<short_name>`: TOOL_CALL_START/ARGS/END, gọi Gateway, khối UI TRƯỚC
    `TOOL_CALL_RESULT` (bản gọn), ghi vào dấu vết của lượt; thử lại khi lỗi tạm thời."""
    name = f"{TARGET}___{short_name}"
    for attempt in range(turn.s.tool_retry_attempts + 1):
        outcome, built = await _call_once(turn, name, args, compact=compact, block=block)
        transient = outcome.kind is ToolKind.UNAVAILABLE or (
            outcome.kind in (ToolKind.TOOL_ERROR, ToolKind.BAD_RESULT)
            and outcome.code in _TRANSIENT
        )
        if outcome.ok or not transient or turn.tool_calls >= turn.s.max_tool_calls_per_turn:
            break
        log.info(
            json.dumps(
                {"event": "tool_retry", "tool": name, "code": outcome.code, "attempt": attempt + 1}
            )
        )
    return outcome, built


async def _call_once(
    turn: Turn,
    name: str,
    args: dict[str, Any],
    *,
    compact: Callable[[ToolOutcome], dict[str, Any]],
    block: Callable[[ToolOutcome, str], list[Any]] | None,
) -> tuple[ToolOutcome, list[Any]]:
    tcid = ev.new_id("tc-")
    turn.emit(ev.tool_call_start(tcid, name))
    if args:
        turn.emit(ev.tool_call_args(tcid, args))
    turn.emit(ev.tool_call_end(tcid))
    turn.tool_calls += 1
    if turn.tool_calls > turn.s.max_tool_calls_per_turn:
        outcome = ToolOutcome(
            name,
            ToolKind.UNAVAILABLE,
            code=ErrorCode.RATE_LIMITED.value,
            message=notices.GENERIC_ERROR_MESSAGE,
            detail="vượt trần số tool call mỗi lượt",
        )
    else:
        finished = False
        try:
            outcome = await turn.tools.call(name, args)
            finished = True
        finally:
            if not finished:  # bị hủy hay lỗi bất ngờ giữa chừng: vẫn đóng tool call cho hợp lệ
                turn.emit(
                    ev.tool_call_result(
                        tcid,
                        {
                            "status": "ERROR",
                            "code": ErrorCode.INTERNAL_ERROR.value,
                            "message": notices.GENERIC_ERROR_MESSAGE,
                        },
                    )
                )
    built: list[Any] = []
    view: dict[str, Any] | None = None
    if outcome.ok:
        try:
            built = block(outcome, turn.trace_id) if block is not None else []
            view = compact(outcome)
        except (ContractMismatch, KeyError, TypeError, ValueError, ValidationError) as exc:
            outcome = ToolOutcome(
                name,
                ToolKind.BAD_RESULT,
                code=ErrorCode.INTERNAL_ERROR.value,
                message=notices.GENERIC_ERROR_MESSAGE,
                detail=str(exc)[:300],
                args=args,
            )
            built, view = [], None
    if outcome.payload and isinstance(outcome.payload.get("app_date"), str):
        with contextlib.suppress(ValueError):
            turn.app_date = date.fromisoformat(outcome.payload["app_date"])
    turn.tool_log.append(outcome)
    if view is not None:
        turn.compacts[name.split("___", 1)[1]] = view
    for b in built:
        turn.emit_block(b)
    if outcome.ok:
        turn.emit(
            ev.tool_call_result(
                tcid, view if view is not None else {"status": outcome.payload["status"]}
            )
        )
    else:
        turn.emit(
            ev.tool_call_result(
                tcid, {"status": "ERROR", "code": outcome.code, "message": outcome.message}
            )
        )
    return outcome, built


# --- dựng khối và bản gọn từ kết quả tool ---------------------------------------------------------------------------------------
def _source(outcome: ToolOutcome) -> B.Source:
    p = outcome.payload or {}
    return B.Source(tool=outcome.name, as_of=p["as_of"], app_date=p["app_date"])


def status_blocks(outcome: ToolOutcome, trace_id: str) -> list[Any]:
    """`review` của `get_job_status` ĐÃ là `data` của khối `ingest_review` (và `coverage_change` của khối cùng tên): chỉ kiểm hợp
    đồng rồi bọc. Không có `review` (đang đọc, hỏng) thì không có khối."""
    data = (outcome.payload or {})["data"]
    out: list[Any] = []
    if "review" in data:
        review = B.IngestReviewData.model_validate(data["review"])
        out.append(
            B.IngestReviewBlock(
                v=B.SCHEMA_VERSION,
                id=f"ingest_review:{review.job_id}",
                type="ingest_review",
                trace_id=trace_id,
                fallback_text=review_text(data)[:280],
                source=_source(outcome),
                data=review,
            )
        )
    if "coverage_change" in data:
        cov = B.CoverageChangeData.model_validate(data["coverage_change"])
        out.append(
            B.CoverageChangeBlock(
                v=B.SCHEMA_VERSION,
                id=f"coverage_change:{cov.job_id}",
                type="coverage_change",
                trace_id=trace_id,
                fallback_text=coverage_text(cov)[:280],
                source=_source(outcome),
                data=cov,
            )
        )
    return out


def compact_status(outcome: ToolOutcome) -> dict[str, Any]:
    """Bản gọn cho `TOOL_CALL_RESULT`: trạng thái và số đếm, KHÔNG có đối tác hay nội dung dòng (dữ liệu từ tệp)."""
    d = (outcome.payload or {})["data"]
    out: dict[str, Any] = {
        "status": "OK",
        "job_status": d["status"],
        "source_kind": d["source_kind"],
        "progress": d["progress"],
        "rows_total": d["rows_total"],
    }
    if "error_code" in d:
        out["error_code"] = d["error_code"]
    if "error_reason" in d:
        out["error_reason"] = d["error_reason"]
    if "review" in d:
        out["counts"] = dict(d["review"]["counts"])
    if "coverage_change" in d:
        c = d["coverage_change"]
        out["coverage"] = {k: c[k] for k in ("before", "after", "rows_added") if k in c}
    return out


def compact_start(outcome: ToolOutcome) -> dict[str, Any]:
    d = (outcome.payload or {})["data"]
    out = {
        "status": "OK",
        "upload_path": d["upload_path"],
        "consent_required": d["consent_required"],
        "limits": [
            {"source_kind": x["source_kind"], "max_bytes": x["max_bytes"]} for x in d["limits"]
        ],
    }
    if "latest_job_status" in d:
        out["latest_job_status"] = d["latest_job_status"]
    return out


# --- câu trả lời (dựng bằng mã) ---------------------------------------------------------------------------------------------
def review_text(data: Mapping[str, Any]) -> str:
    c = data["review"]["counts"]
    total = data["rows_total"]
    kind = _KIND_WORD.get(data["source_kind"], "tệp")
    if data["status"] == "done":
        return f"Lần nạp {kind} này đã được chốt: {c['approved']} dòng ngoài ví đã vào lịch sử chi tiêu, số dư các hũ không đổi."
    parts = [f"{c['auto_added']} dòng đã chọn sẵn", f"{c['pending']} dòng cần bạn duyệt"]
    if c["duplicate"]:
        parts.append(f"{c['duplicate']} dòng đã có trong ví nên bỏ qua")
    return (
        f"Mình đã đọc xong {kind} bạn vừa nạp: {total} dòng, gồm " + ", ".join(parts) + ". "
        "Bạn xem lại bảng bên dưới, đổi hũ nếu cần rồi bấm chốt trên màn hình; chỉ khi đó các dòng mới vào lịch sử, số dư các hũ không đổi."
    )


def coverage_text(cov: B.CoverageChangeData) -> str:
    if cov.before is not None and cov.after is not None:
        return f"Độ phủ dữ liệu từ {_pct(cov.before)} lên {_pct(cov.after)} sau khi thêm {cov.rows_added} dòng ngoài ví."
    if cov.after is not None:
        return f"Độ phủ dữ liệu là {_pct(cov.after)} sau khi thêm {cov.rows_added} dòng ngoài ví."
    return f"Đã thêm {cov.rows_added} dòng ngoài ví vào lịch sử chi tiêu."


def status_text(data: Mapping[str, Any]) -> str:
    st = data["status"]
    kind = _KIND_WORD.get(data["source_kind"], "tệp")
    if st in ("awaiting_upload", "queued", "processing"):
        return f"Mình đang đọc {kind} bạn vừa nạp ({int(data['progress'])}%). Bạn hỏi lại sau ít phút hoặc mở màn Nạp dữ liệu để xem tiến độ."
    if (
        st in ("failed", "rejected")
        and data.get("error_code") == ErrorCode.INGEST_NO_TRANSACTIONS.value
    ):
        why = _NO_TX_REASON_TEXT.get(str(data.get("error_reason") or ""), _DEFAULT_NO_TX)
        return f"Lần nạp {kind} gần nhất không có giao dịch nào để thêm: {why}. Tệp khác có khoản chi thật thì bạn nạp ở màn Nạp dữ liệu."
    if st in ("failed", "rejected"):
        why = _JOB_ERROR_TEXT.get(str(data.get("error_code") or ""), _DEFAULT_JOB_ERROR)
        return f"Lần nạp {kind} gần nhất không thành công: {why}. Chưa có dòng nào được thêm. Bạn có thể nạp lại ở màn Nạp dữ liệu."
    if st == "done":
        text = review_text(data) if "review" in data else f"Lần nạp {kind} này đã được chốt."
        if "coverage_change" in data:
            text += " " + coverage_text(
                B.CoverageChangeData.model_validate(data["coverage_change"])
            )
        return text
    if "review" in data:  # review
        return review_text(data) + " Độ phủ dữ liệu chỉ đổi sau khi bạn chốt."
    return f"Lần nạp {kind} gần nhất đang ở trạng thái chờ duyệt."


def start_text(data: Mapping[str, Any], *, no_job: bool) -> str:
    lims = []
    for x in data["limits"]:
        mimes = ", ".join(dict.fromkeys(_MIME_LABEL.get(m, m) for m in x["mime_types"]))
        what = "ảnh chụp màn hình giao dịch" if x["source_kind"] == "image" else "tệp sao kê"
        lims.append(f"{what} ({mimes}, tối đa {_mb(int(x['max_bytes']))})")
    head = "Bạn chưa nạp ảnh hay tệp sao kê nào. " if no_job else ""
    text = (
        f"{head}Bạn thêm chi tiêu ở ngân hàng hay thẻ khác bằng {' hoặc '.join(lims)} ở màn Nạp dữ liệu "
        "(Tổng quan, Tiền vào, Nạp ảnh / sao kê ngoài ví). Mình đọc tệp, che thông tin cá nhân rồi đưa các dòng ra bảng duyệt; "
        "dòng chỉ vào lịch sử khi bạn bấm chốt, số dư các hũ không đổi."
    )
    if data["consent_required"]:
        text += " Lần đầu nạp, màn hình sẽ hỏi bạn đồng ý cho Yofina đọc loại tệp đó."
    latest = data.get("latest_job_status")
    if latest == "review":
        text += " Lần nạp gần nhất của bạn đang chờ duyệt."
    elif latest in ("awaiting_upload", "queued", "processing"):
        text += " Lần nạp gần nhất của bạn đang được đọc."
    return text


# --- bộ xử lý ý định ------------------------------------------------------------------------------------------------------------
async def _start(turn: Turn, *, no_job: bool) -> None:
    outcome, _ = await call_ingest_tool(turn, "start_job", {}, compact=compact_start)
    if not outcome.ok:
        turn.tool_failure(outcome)
        return
    await turn.emit_fixed_text(start_text((outcome.payload or {})["data"], no_job=no_job))


async def on_ingest(turn: Turn, r: IntentResult, question: str) -> None:
    if r.params.ingest_action == "how_to":
        await _start(turn, no_job=False)
        return
    outcome, _ = await call_ingest_tool(
        turn, "get_job_status", {}, compact=compact_status, block=status_blocks
    )
    if not outcome.ok:
        if (
            outcome.kind is ToolKind.TOOL_ERROR
            and outcome.code == ErrorCode.INGEST_JOB_NOT_FOUND.value
        ):
            await _start(turn, no_job=True)
            return
        turn.tool_failure(outcome)
        return
    await turn.emit_fixed_text(status_text((outcome.payload or {})["data"]))
