"""Trích dòng giao dịch từ MỘT tệp (ảnh hoặc CSV), che PII, loại dòng không phải chi tiêu thật, gán hũ đề xuất. KHÔNG chạm DB.

`extract(data, *, filename, content_type, mode="eval")` là điểm vào của `scripts/eval_ingest.py` (và của op `eval_extract` của
Lambda worker); worker dùng `extract_rows` với ngữ cảnh thật của người dùng.

Luồng một tệp:

1. **Ảnh**: kiểm kích thước và chữ ký tệp, gửi cho model vai `ingest` (Sonnet 4.6, dự phòng Kimi K3) kèm danh sách hũ và loại giao dịch của
   người dùng; model BẮT BUỘC trả JSON theo schema (`yofina_core.llm.structured_json`, ép tool `report`, không có công cụ ghi nào).
   **CSV**: bộ đọc tất định (`csvparse`); model nhỏ (vai `ingest_columns`) chỉ được hỏi khi cột lạ (tên cột + vài ô ĐÃ che PII) và để gắn
   nhãn đối tác/hũ cho các dòng (nội dung ĐÃ che PII; lỗi hay hết hạn mức thì dòng vẫn được nạp, chỉ không có hũ đề xuất).
2. **Che PII ngay sau khi đọc** (`yofina_core.pii`) TRƯỚC khi lưu, ghi log hay gửi văn bản cho lời gọi model thứ hai.
3. **Loại**: thất bại, chưa thực hiện, nạp tiền giữa tài khoản của chính mình, dòng không đọc được số tiền. Không dòng nào của màn xác
   nhận/OTP/biểu mẫu trống hay bảng phí đi qua được bước này thành `auto_add`.
4. **Gán hũ**: bộ phân loại phase 4 (`yofina_ingest.classify`): luật người dùng, bảng `tx_type_map`, embedding k-NN, model nhỏ (đề xuất
   hũ của chính lượt đọc tệp); ba mức tin cậy, chỉ mức `auto` được chọn sẵn.
5. **Tự chọn sẵn** (`should_auto_add`): chỉ khi đủ tin cậy và tệp không chứa văn bản giống chỉ dẫn; dòng chứa câu giống chỉ dẫn và mọi dòng
   của tệp bị gắn cờ luôn vào hàng chờ duyệt.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from yofina_core.clock import app_today
from yofina_core.config import Config
from yofina_core.ingest import IngestSettings, should_auto_add
from yofina_core.llm import (
    AllModelsFailed,
    LlmGateway,
    ModelBudgetExceeded,
    StructuredOutputError,
    get_gateway,
)
from yofina_core.params import MAX_VND
from yofina_core.pii import PiiPolicy, mask_counterparty, mask_row_text
from yofina_ingest import csvparse, prompts
from yofina_ingest.classify import RowInput, classify_rows
from yofina_ingest.context import ExtractContext, eval_context
from yofina_ingest.normalize import (
    clean_text,
    looks_failed,
    looks_like_instruction,
    looks_like_self_topup,
    neutralize,
    parse_date,
)
from yofina_ingest.schemas import ColumnMap, CsvLabels, ImageExtraction

log = logging.getLogger("yofina.ingest.extract")

IMAGE_ROLE = "ingest"
COLUMNS_ROLE = "ingest_columns"
IMAGE_MAX_TOKENS = 8192  # Kimi K3 luôn suy nghĩ và phần đó tính vào maxTokens
LABEL_BATCH = 40
CP_LIMIT = 120
DESC_LIMIT = 200

#: mã lỗi của `extract` (chữ thường, đúng quy ước của eval_ingest) -> mã `ErrorCode` của job
ERROR_CODE_OF = {
    "not_financial": "INGEST_NOT_FINANCIAL",
    "no_transactions": "INGEST_NOT_FINANCIAL",
    "unsupported_type": "INGEST_UNSUPPORTED_TYPE",
    "unreadable": "INGEST_UNSUPPORTED_TYPE",
    "too_large": "INGEST_TOO_LARGE",
    "too_many_rows": "INGEST_TOO_LARGE",
    "budget_exceeded": "MODEL_BUDGET_EXCEEDED",
    "model_failed": "INTERNAL_ERROR",
}
ERROR_MESSAGES = {
    "not_financial": "Ảnh này không giống biên lai, tin nhắn hay lịch sử giao dịch nên mình không đọc được khoản nào.",
    "no_transactions": "Mình không thấy giao dịch nào đã hoàn tất trong tệp này (có thể là màn xác nhận, giao dịch không thành công hoặc chỉ là nạp tiền giữa tài khoản của bạn).",
    "unsupported_type": "Mình chưa đọc được loại tệp này. Hãy dùng ảnh PNG, JPEG, WebP hoặc tệp CSV.",
    "unreadable": "Mình không đọc được nội dung tệp này. Hãy thử ảnh rõ hơn hoặc tệp CSV khác.",
    "too_large": "Tệp lớn hơn giới hạn cho phép.",
    "too_many_rows": "Tệp có quá nhiều dòng cho một lần nạp.",
    "budget_exceeded": "Hôm nay đã hết lượt đọc tệp bằng AI. Hãy thử lại vào ngày mai.",
    "model_failed": "Không đọc được tệp lúc này. Hãy thử lại sau.",
}


class ExtractError(Exception):
    """Tệp bị từ chối hay không đọc được. `code` là mã chữ thường của `ERROR_CODE_OF`."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.message = message or ERROR_MESSAGES.get(code, ERROR_MESSAGES["unreadable"])


@dataclass
class Candidate:
    """Một dòng sẵn sàng ghi vào `ingest_rows` (văn bản ĐÃ che PII)."""

    seq: int
    kind: str  # expense | income
    app_date: date
    amount_vnd: int
    counterparty: str | None
    description: str | None
    extract_confidence: float
    tx_type: str | None = None
    jar_code: str | None = None
    jar_confidence: float | None = None
    jar_source: str | None = None
    auto_add: bool = False
    source_row: int | None = None
    flags: list[str] = field(default_factory=list)


@dataclass
class Dropped:
    reason: str
    source_row: int | None = None


@dataclass
class ExtractionResult:
    source_kind: str
    document_type: str | None = None
    candidates: list[Candidate] = field(default_factory=list)
    dropped: list[Dropped] = field(default_factory=list)
    model: str | None = None
    contains_instructions: bool = False
    warnings: list[str] = field(default_factory=list)
    model_calls: int = 0


@dataclass
class RawRow:
    """Dòng thô (chưa che PII) từ ảnh hoặc CSV, đã chuyển về kiểu Python."""

    amount_vnd: int | None
    direction: str | None
    date: date | None = None
    partial_year: bool = False
    counterparty: str | None = None
    is_person: bool | None = None
    description: str | None = None
    status: str = "completed"
    own_account_transfer: bool = False
    tx_type: str | None = None
    jar_code: str | None = None
    jar_confidence: float | None = None
    confidence: float = 0.5
    source_row: int | None = None
    flags: list[str] = field(default_factory=list)


# --- phát hiện loại tệp -----------------------------------------------------------------------------------------------------------
def sniff_image_format(data: bytes) -> str | None:
    """Định dạng ảnh theo chữ ký tệp (không tin Content-Type do client khai): png, jpeg, webp hoặc None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def source_kind_of(content_type: str, filename: str, settings: IngestSettings) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    name = (filename or "").lower()
    if ct in settings.ingest_image_mime_types or name.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return "image"
    if ct in settings.ingest_csv_mime_types or name.endswith((".csv", ".txt")):
        return "csv"
    raise ExtractError("unsupported_type")


# --- hoàn thiện dòng (dùng chung ảnh và CSV) --------------------------------------------------------------------------------------
def _masked(raw: RawRow, ctx: ExtractContext) -> tuple[str | None, str | None]:
    cp = mask_counterparty(raw.counterparty, is_person=raw.is_person, policy=ctx.policy)
    desc = mask_row_text(raw.description, ctx.policy)
    return clean_text(neutralize(cp), CP_LIMIT), clean_text(neutralize(desc), DESC_LIMIT)


def finalize_rows(
    raws: Sequence[RawRow],
    ctx: ExtractContext,
    *,
    file_flagged: bool,
    gateway: LlmGateway | None = None,
) -> tuple[list[Candidate], list[Dropped]]:
    """Loại, che PII, gán hũ (bộ phân loại phase 4, `yofina_ingest.classify`), quyết định tự chọn sẵn. Thứ tự dòng được giữ; `seq`
    đánh lại từ 1. `gateway` chỉ dùng để nhúng chuỗi cho bước k-NN (khi ngữ cảnh có kho nhãn)."""
    out: list[Candidate] = []
    proposals: list[tuple[str | None, float | None, bool | None]] = []
    dropped: list[Dropped] = []
    cap = ctx.settings.ingest_csv_max_rows
    for raw in raws:
        texts = (raw.counterparty, raw.description)
        if raw.amount_vnd is None or raw.amount_vnd <= 0:
            dropped.append(Dropped("no_amount", raw.source_row))
            continue
        if raw.amount_vnd > MAX_VND:
            dropped.append(Dropped("amount_out_of_range", raw.source_row))
            continue
        if raw.direction not in ("out", "in"):
            dropped.append(Dropped("no_direction", raw.source_row))
            continue
        if raw.status != "completed" or looks_failed(*texts):
            dropped.append(Dropped("not_completed", raw.source_row))
            continue
        if raw.own_account_transfer or looks_like_self_topup(*texts):
            dropped.append(Dropped("own_account_transfer", raw.source_row))
            continue
        if len(out) >= cap:
            dropped.append(Dropped("over_row_cap", raw.source_row))
            continue
        flags = list(raw.flags)
        confidence = float(raw.confidence)
        day = raw.date
        if day is None:
            day, confidence = ctx.today, min(confidence, 0.5)
            flags.append("date_missing")
        elif raw.partial_year:
            confidence = min(confidence, 0.85)
            flags.append("year_assumed")
        injected = looks_like_instruction(*texts)
        if injected:
            flags.append("instruction_like_text")
        cp, desc = _masked(raw, ctx)
        kind = "expense" if raw.direction == "out" else "income"
        info = ctx.type_map.get(raw.tx_type or "")
        tx_type = raw.tx_type if info is not None and info.direction == raw.direction else None
        out.append(
            Candidate(
                seq=len(out) + 1,
                kind=kind,
                app_date=day,
                amount_vnd=int(raw.amount_vnd),
                counterparty=cp,
                description=desc,
                extract_confidence=round(confidence, 3),
                tx_type=tx_type,
                source_row=raw.source_row,
                flags=flags,
            )
        )
        proposals.append((raw.jar_code, raw.jar_confidence, raw.is_person))
    # gán hũ cho MỌI dòng chi một lần (bộ phân loại phase 4; embedding gom lô), rồi mới quyết định chọn sẵn
    expense = [i for i, c in enumerate(out) if c.kind == "expense"]
    choices = classify_rows(
        [
            RowInput(
                app_date=out[i].app_date,
                amount_vnd=out[i].amount_vnd,
                counterparty=out[i].counterparty,
                description=out[i].description,
                is_person=proposals[i][2],
                tx_type=out[i].tx_type,
                proposal_jar=proposals[i][0],
                proposal_confidence=proposals[i][1],
            )
            for i in expense
        ],
        ctx.classify_inputs(gateway),
    )
    chosen = dict(zip(expense, choices, strict=True))
    for i, c in enumerate(out):
        choice = chosen.get(i)
        if choice is not None:
            c.jar_code, c.jar_confidence, c.jar_source = choice.code, choice.confidence, choice.source
        auto = should_auto_add(
            kind=c.kind,
            extract_confidence=c.extract_confidence,
            jar_code=c.jar_code,
            jar_confidence=c.jar_confidence,
            settings=ctx.settings,
        )
        # dòng chi chỉ được chọn sẵn khi bộ phân loại xếp mức `auto`; mức `review`, `ask` vào hàng chờ duyệt
        if c.kind == "expense" and (choice is None or choice.tier != "auto"):
            auto = False
        if file_flagged or "instruction_like_text" in c.flags or "date_missing" in c.flags:
            auto = False
        c.auto_add = auto
    return out, dropped


# --- ảnh --------------------------------------------------------------------------------------------------------------------------
def _call_budget_guard(fn):
    try:
        return fn()
    except ModelBudgetExceeded as exc:
        raise ExtractError("budget_exceeded") from exc
    except (AllModelsFailed, StructuredOutputError) as exc:
        raise ExtractError("model_failed") from exc


def extract_image(data: bytes, ctx: ExtractContext, gateway: LlmGateway) -> ExtractionResult:
    fmt = sniff_image_format(data)
    if fmt is None:
        raise ExtractError("unsupported_type")
    if len(data) > ctx.settings.ingest_image_max_bytes:
        raise ExtractError("too_large")
    system = prompts.image_system(ctx.jars, ctx.type_map, ctx.today)
    messages = prompts.image_messages(data, fmt)
    res = _call_budget_guard(
        lambda: gateway.structured_json(
            IMAGE_ROLE,
            output_model=ImageExtraction,
            messages=messages,
            system=system,
            tool_name="report",
            description="Báo cáo các giao dịch đọc được từ ảnh (và loại ảnh) theo đúng schema.",
            max_attempts=2,
            max_tokens=IMAGE_MAX_TOKENS,
        )
    )
    doc: ImageExtraction = res.value
    result = ExtractionResult(
        source_kind="image",
        document_type=doc.document_type,
        model=res.model_id,
        contains_instructions=doc.contains_instructions,
        model_calls=res.attempts,
    )
    if doc.document_type == "not_financial":
        raise ExtractError("not_financial")
    if not doc.readable and not doc.rows:
        raise ExtractError("unreadable")
    raws: list[RawRow] = []
    for i, r in enumerate(doc.rows, start=1):
        parsed, partial = parse_date(r.date, today=ctx.today, year_hint=doc.year_hint)
        raws.append(
            RawRow(
                amount_vnd=r.amount_vnd,
                direction=r.direction,
                date=parsed,
                partial_year=partial,
                counterparty=r.counterparty,
                is_person=r.counterparty_is_person,
                description=r.description,
                status=r.status,
                own_account_transfer=r.own_account_transfer,
                tx_type=r.tx_type,
                jar_code=r.jar_code,
                jar_confidence=r.jar_confidence,
                confidence=r.confidence * (1.0 if doc.readable else 0.7),
                source_row=i,
            )
        )
    result.candidates, result.dropped = finalize_rows(
        raws, ctx, file_flagged=doc.contains_instructions, gateway=gateway
    )
    return result


# --- CSV --------------------------------------------------------------------------------------------------------------------------
def _map_columns(
    table: csvparse.CsvTable,
    auto: csvparse.Mapping_,
    ctx: ExtractContext,
    gateway: LlmGateway,
    result: ExtractionResult,
) -> csvparse.Mapping_:
    """Bảng tên cột đã biết không đủ (thiếu cột ngày hay số tiền): hỏi model nhỏ CHỈ để ánh xạ tên cột (ô mẫu đã che PII)."""
    sample = [
        [mask_row_text(c, ctx.policy) or "" for c in row]
        for row in csvparse.sample_for_mapping(table)
    ]
    messages = [
        {
            "role": "user",
            "content": [{"text": prompts.columns_user(table.header, sample)}],
        }
    ]
    res = _call_budget_guard(
        lambda: gateway.structured_json(
            COLUMNS_ROLE,
            output_model=ColumnMap,
            messages=messages,
            system=prompts.columns_system(),
            tool_name="report",
            description="Ánh xạ tên cột CSV sang vai của cột.",
            max_attempts=2,
            max_tokens=1024,
        )
    )
    result.model_calls += res.attempts
    result.model = result.model or res.model_id
    cm: ColumnMap = res.value
    extra = csvparse.mapping_from_names(
        table.header,
        {
            "date": cm.date,
            "description": cm.description,
            "amount": cm.amount,
            "debit": cm.debit,
            "credit": cm.credit,
            "counterparty": cm.counterparty,
        },
        cm.date_order,
    )
    return csvparse.merge_mapping(auto, extra)


def _guess_merchant(description: str | None) -> str | None:
    """Đối tác ước lượng từ nội dung sao kê khi không gọi được model: bỏ mã tham chiếu, tiền tố ngân hàng và cụm "thanh toán QR"."""
    if not description:
        return None
    noise = {
        "mbvcb",
        "thanh",
        "toan",
        "qr",
        "ck",
        "chuyen",
        "khoan",
        "nd",
        "ft",
        "ref",
        "gd",
        "internet",
        "banking",
    }
    kept = []
    for tok in description.replace(".", " ").replace("-", " ").split():
        low = tok.lower().strip("'")
        if low in noise or sum(ch.isdigit() for ch in tok) >= 3:
            continue
        kept.append(tok)
    guess = " ".join(kept).strip()
    return guess[:60] or None


def _label_rows(
    rows: list[csvparse.CsvRow], ctx: ExtractContext, gateway: LlmGateway, result: ExtractionResult
) -> dict[int, Any]:
    """Gắn nhãn đối tác, loại và hũ bằng model nhỏ. Văn bản gửi đi ĐÃ che PII. Lỗi hay hết hạn mức thì không có nhãn (dòng vẫn được nạp)."""
    labels: dict[int, Any] = {}
    items = [
        (
            r.source_row,
            r.direction or "out",
            mask_row_text(r.description, ctx.policy) or "",
            mask_row_text(r.counterparty, ctx.policy),
        )
        for r in rows
    ]
    for start in range(0, len(items), LABEL_BATCH):
        batch = items[start : start + LABEL_BATCH]
        messages = [{"role": "user", "content": [{"text": prompts.labels_user(batch)}]}]
        try:
            res = gateway.structured_json(
                COLUMNS_ROLE,
                output_model=CsvLabels,
                messages=messages,
                system=prompts.labels_system(ctx.jars, ctx.type_map),
                tool_name="report",
                description="Gắn nhãn đối tác, loại giao dịch và hũ cho từng dòng.",
                max_attempts=2,
                max_tokens=4096,
            )
        except (ModelBudgetExceeded, AllModelsFailed, StructuredOutputError) as exc:
            result.warnings.append(f"labels_unavailable:{type(exc).__name__}")
            log.warning("csv_labels_unavailable error=%s", type(exc).__name__)
            break
        result.model_calls += res.attempts
        result.model = result.model or res.model_id
        wanted = {i[0] for i in batch}
        for lab in res.value.rows:
            if lab.idx in wanted:
                labels[lab.idx] = lab
    return labels


def extract_csv(data: bytes, ctx: ExtractContext, gateway: LlmGateway) -> ExtractionResult:
    if len(data) > ctx.settings.ingest_csv_max_bytes:
        raise ExtractError("too_large")
    try:
        table = csvparse.read_table(data, max_rows=ctx.settings.ingest_csv_max_rows)
    except csvparse.CsvError as exc:
        code = "too_many_rows" if exc.code == "too_many_rows" else "unreadable"
        raise ExtractError(code, exc.message) from exc
    result = ExtractionResult(source_kind="csv", document_type="bank_statement")
    mapping = csvparse.map_header(table.header) if table.header_found else csvparse.Mapping_()
    if not mapping.usable:
        mapping = _map_columns(table, mapping, ctx, gateway, result)
    if not mapping.usable:
        raise ExtractError("unreadable", "Không nhận ra cột ngày và số tiền trong tệp CSV này.")
    parsed = csvparse.parse_rows(table, mapping, today=ctx.today)
    good = [r for r in parsed if r.problem is None]
    for r in parsed:
        if r.problem is not None:
            result.dropped.append(Dropped(r.problem, r.source_row))
    labels = _label_rows(good, ctx, gateway, result) if good else {}
    raws: list[RawRow] = []
    for r in good:
        lab = labels.get(r.source_row)
        counterparty = (
            r.counterparty or (lab.merchant if lab else None) or _guess_merchant(r.description)
        )
        raws.append(
            RawRow(
                amount_vnd=r.amount_vnd,
                direction=r.direction,
                date=r.date,
                partial_year=r.partial_year,
                counterparty=counterparty,
                is_person=lab.is_person if lab else None,
                description=r.description,
                own_account_transfer=bool(lab and lab.own_account_transfer),
                tx_type=lab.tx_type if lab else None,
                jar_code=lab.jar_code if lab else None,
                jar_confidence=lab.jar_confidence if lab else None,
                confidence=r.confidence,
                source_row=r.source_row,
                flags=list(r.notes),
            )
        )
    result.candidates, finalized_dropped = finalize_rows(
        raws, ctx, file_flagged=False, gateway=gateway
    )
    result.dropped.extend(finalized_dropped)
    return result


# --- điểm vào ---------------------------------------------------------------------------------------------------------------------
def extract_rows(
    data: bytes,
    *,
    filename: str,
    content_type: str,
    ctx: ExtractContext,
    gateway: LlmGateway | None = None,
    source_kind: str | None = None,
) -> ExtractionResult:
    """Trích một tệp với ngữ cảnh đã dựng. Ném `ExtractError` khi tệp bị từ chối. `source_kind` (nếu biết, từ job) thắng cách đoán."""
    kind = source_kind or source_kind_of(content_type, filename, ctx.settings)
    gw = gateway or get_gateway()
    if kind == "image":
        result = extract_image(data, ctx, gw)
    elif kind == "csv":
        result = extract_csv(data, ctx, gw)
    else:
        raise ExtractError("unsupported_type")
    if not result.candidates:
        raise ExtractError("no_transactions")
    return result


# --- chế độ eval (không DB) -------------------------------------------------------------------------------------------------------
class MemoryUsageStore:
    """Bộ đếm lượt gọi trong bộ nhớ (chỉ để chạy eval từ máy dev mà không ghi DynamoDB); cùng giao diện với `UsageStore`."""

    def __init__(self) -> None:
        self.counts: dict[tuple[str, str], int] = {}

    def consume(self, *, day: str, model: str, cap: int, ttl_epoch: int) -> int:
        from yofina_core.llm import BudgetCapReached

        n = self.counts.get((day, model), 0)
        if n >= cap:
            raise BudgetCapReached(model)
        self.counts[(day, model)] = n + 1
        return n + 1


_eval_gateway: LlmGateway | None = None


def eval_gateway() -> LlmGateway:
    """Cổng model cho eval. Có bảng `yofina-usage` cấu hình (biến YOFINA_USAGE_TABLE hay YOFINA_SSM_PREFIX) thì dùng cổng chung của tiến
    trình (trần ngày dùng chung với ứng dụng); không thì bộ đếm trong bộ nhớ, để eval từ máy dev không ghi DynamoDB.
    `YOFINA_INGEST_EVAL_USAGE=memory|shared` ép một trong hai."""
    global _eval_gateway
    mode = os.environ.get("YOFINA_INGEST_EVAL_USAGE", "auto").lower()
    shared = mode == "shared" or (
        mode == "auto"
        and (os.environ.get("YOFINA_USAGE_TABLE") or os.environ.get("YOFINA_SSM_PREFIX"))
    )
    if shared:
        return get_gateway()
    if _eval_gateway is None:
        _eval_gateway = LlmGateway(usage=MemoryUsageStore())
    return _eval_gateway


def _eval_today(now: datetime | None = None) -> date:
    forced = os.environ.get("YOFINA_INGEST_EVAL_TODAY")
    if forced:
        return date.fromisoformat(forced)
    tz = ZoneInfo(Config().get("app_timezone", default="Asia/Ho_Chi_Minh"))
    return app_today(0, now or datetime.now(UTC), tz)


def result_to_eval(res: ExtractionResult, mode: str) -> dict[str, Any]:
    """Dạng `result` mà `scripts/eval_ingest.py` chấm (không có văn bản thô: chỉ trường đã che)."""
    rows = [
        {
            "date": c.app_date.isoformat(),
            "amount_vnd": c.amount_vnd,
            "direction": "out" if c.kind == "expense" else "in",
            "counterparty": c.counterparty,
            "description": c.description,
            "jar_code": c.jar_code,
            "confidence": c.extract_confidence,
            "disposition": "auto_add" if c.auto_add else "review",
            "source_row": c.source_row,
            "tx_type": c.tx_type,
            "jar_source": c.jar_source,
            "jar_confidence": c.jar_confidence,
        }
        for c in res.candidates
    ]
    return {
        "status": "ok",
        "error_code": None,
        "mode": mode,
        "document_type": res.document_type,
        "rows": rows,
        "dropped": [{"reason": d.reason, "source_row": d.source_row} for d in res.dropped],
        "contains_instructions": res.contains_instructions,
        "warnings": res.warnings,
        "model": res.model,
        "model_calls": res.model_calls,
        "tool_calls": [],  # đường trích không có công cụ nào để gọi
    }


def extract(
    data: bytes,
    *,
    filename: str = "",
    content_type: str = "",
    mode: str = "eval",
    ctx: ExtractContext | None = None,
    gateway: LlmGateway | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Điểm vào của eval: chỉ trích và phân loại, không DB, không ghi sổ cái. Trả dict như docstring của `scripts/eval_ingest.py`.

    Tệp bị từ chối thì `status = "error"` với `error_code` chữ thường (`not_financial`, `unreadable`, `unsupported_type`, `too_large`...)."""
    if mode != "eval":
        raise ValueError(
            "extract chỉ hỗ trợ mode='eval'; worker dùng extract_rows với ngữ cảnh thật"
        )
    try:
        context = ctx or eval_context(_eval_today(now))
        res = extract_rows(
            data,
            filename=filename,
            content_type=content_type,
            ctx=context,
            gateway=gateway or eval_gateway(),
        )
    except ExtractError as exc:
        return {
            "status": "error",
            "error_code": exc.code,
            "error_message": exc.message,
            "mode": mode,
            "rows": [],
            "dropped": [],
            "tool_calls": [],
        }
    return result_to_eval(res, mode)


def default_policy(keep: Sequence[str] = (), self_names: Sequence[str] = ()) -> PiiPolicy:
    return PiiPolicy.build(keep, self_names)
