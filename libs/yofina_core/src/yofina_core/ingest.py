"""Hợp đồng dùng chung của luồng nạp dữ liệu từ ảnh và CSV (phase 5, F6): hằng số, cấu hình, khóa khử trùng, độ phủ dữ liệu,
model kết quả tool `ingest___*` và hàm dựng hai khối `ingest_review`, `coverage_change`.

Nguồn sự thật: `contracts/blocks/{ingest_review,coverage_change}.schema.json`, `contracts/tools/ingest.json`,
`contracts/tools/ingest.results.schema.json`, `db/migrations/0050_ingest.sql`; quy ước ở contracts/README.md mục
"Phase 5 (F6): nạp dữ liệu". Model khối nằm ở `yofina_core.blocks` (cùng hợp `Block`); module này chỉ thêm, không đổi hành vi cũ.

Không có đồng hồ hệ thống ở đây: người gọi truyền `as_of` và `app_date`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import Field

from yofina_core.blocks import (
    SCHEMA_VERSION,
    ConfirmActionData,
    CoverageChangeBlock,
    CoverageChangeData,
    CoverageJar,
    IngestCounts,
    IngestJar,
    IngestJobStatus,
    IngestReviewBlock,
    IngestReviewData,
    IngestRow,
    IsoDate,
    IsoDateTime,
    ReceiptActionData,
    Uuid,
    _clip,
    _date_text,
    _source,
    _Strict,
)
from yofina_core.config import Config
from yofina_core.money import format_vnd, to_vnd
from yofina_core.params import fold_text
from yofina_core.wallet import CONFIRM_ROWS

# --- tập giá trị (khớp CHECK của 0050 và enum của contracts/; test chống lệch ở tests/unit/test_contracts_ingest.py) ------
TARGET = "ingest"
#: tool của target `ingest` (đúng thứ tự trong contracts/tools/ingest.json); tên đầy đủ qua Gateway `ingest___<tool>`
INGEST_TOOLS = ("start_job", "get_job_status", CONFIRM_ROWS)
INGEST_WRITE_TOOLS = (CONFIRM_ROWS,)
SOURCE_KINDS = ("image", "csv")
JOB_STATUSES = ("awaiting_upload", "queued", "processing", "review", "done", "failed", "rejected")
JOB_FINAL_STATUSES = ("done", "failed", "rejected")
ROW_KINDS = ("expense", "income")
ROW_STATUSES = ("auto_added", "pending", "approved", "rejected", "duplicate")
#: dòng còn chốt được bằng confirm_rows
ROW_OPEN_STATUSES = ("auto_added", "pending")
JAR_SOURCES = ("type_map", "rule", "model", "user")
CONSENT_SOURCES = ("image_upload", "csv_upload")
CONSENT_SOURCE_OF = {"image": "image_upload", "csv": "csv_upload"}
FORECAST_REFRESH = ("queued", "done", "skipped")
#: giá trị `transactions.source` của dòng do confirm_rows ghi (cột tự do của 0001, tối đa 32 ký tự)
LEDGER_SOURCE = "ingest"

ROW_LIMIT_IN_BLOCK = 200


# --- cấu hình (MỘT nơi cho tên khóa và giá trị mặc định; ghi lại ở contracts/README.md) ---------------------------------------
@dataclass(frozen=True)
class IngestSettings:
    """Giới hạn và ngưỡng của luồng nạp. Khóa cấu hình là tên trường (biến `YOFINA_<TÊN>` hoặc SSM `<prefix>/<tên>`)."""

    #: ảnh tối đa (byte). 3.750.000 = giới hạn 3,75 MB mỗi ảnh của Bedrock Converse (ImageBlock)
    ingest_image_max_bytes: int = 3_750_000
    #: CSV tối đa (byte)
    ingest_csv_max_bytes: int = 2_000_000
    #: số dòng tối đa đọc từ một CSV (thừa thì từ chối, không cắt im lặng)
    ingest_csv_max_rows: int = 500
    #: MIME cho phép (dấu phẩy); ảnh là png, jpeg, webp (định dạng Converse nhận)
    ingest_image_mime_types: tuple[str, ...] = ("image/png", "image/jpeg", "image/webp")
    ingest_csv_mime_types: tuple[str, ...] = ("text/csv", "application/vnd.ms-excel")
    #: hạn của presigned POST (giây)
    ingest_upload_url_ttl_seconds: int = 300
    #: cửa sổ khử trùng với sổ cái: lệch ngày tối đa (ngày) khi so cùng số tiền, cùng kind
    ingest_dedupe_window_days: int = 3
    #: dòng tự chọn sẵn (auto_added) khi CẢ HAI ngưỡng đạt; dòng chi còn cần có hũ đề xuất
    ingest_auto_extract_min_confidence: Decimal = Decimal("0.90")
    ingest_auto_jar_min_confidence: Decimal = Decimal("0.80")
    #: phiên bản văn bản đồng ý đang hiển thị (ghi vào consents.version)
    ingest_consent_version: str = "2026-12"

    @property
    def mime_types(self) -> dict[str, tuple[str, ...]]:
        return {"image": self.ingest_image_mime_types, "csv": self.ingest_csv_mime_types}

    def max_bytes(self, source_kind: str) -> int:
        return self.ingest_image_max_bytes if source_kind == "image" else self.ingest_csv_max_bytes

    @classmethod
    def from_config(cls, cfg: Config | None = None) -> IngestSettings:
        """Đọc từ cấu hình; khóa vắng thì dùng mặc định ở trên (giá trị nghiệp vụ, không gắn tài khoản AWS)."""
        cfg = cfg or Config()
        d = cls()

        def mimes(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
            raw = cfg.get(name, default=None)
            if raw is None:
                return default
            return tuple(m.strip().lower() for m in str(raw).split(",") if m.strip())

        out = cls(
            ingest_image_max_bytes=cfg.get_int(
                "ingest_image_max_bytes", default=d.ingest_image_max_bytes
            ),
            ingest_csv_max_bytes=cfg.get_int(
                "ingest_csv_max_bytes", default=d.ingest_csv_max_bytes
            ),
            ingest_csv_max_rows=cfg.get_int("ingest_csv_max_rows", default=d.ingest_csv_max_rows),
            ingest_image_mime_types=mimes("ingest_image_mime_types", d.ingest_image_mime_types),
            ingest_csv_mime_types=mimes("ingest_csv_mime_types", d.ingest_csv_mime_types),
            ingest_upload_url_ttl_seconds=cfg.get_int(
                "ingest_upload_url_ttl_seconds", default=d.ingest_upload_url_ttl_seconds
            ),
            ingest_dedupe_window_days=cfg.get_int(
                "ingest_dedupe_window_days", default=d.ingest_dedupe_window_days
            ),
            ingest_auto_extract_min_confidence=cfg.get_decimal(
                "ingest_auto_extract_min_confidence", default=d.ingest_auto_extract_min_confidence
            ),
            ingest_auto_jar_min_confidence=cfg.get_decimal(
                "ingest_auto_jar_min_confidence", default=d.ingest_auto_jar_min_confidence
            ),
            ingest_consent_version=cfg.get(
                "ingest_consent_version", default=d.ingest_consent_version
            ),
        )
        out.validate()
        return out

    def validate(self) -> None:
        if not (self.ingest_image_max_bytes > 0 and self.ingest_csv_max_bytes > 0):
            raise ValueError("giới hạn kích thước phải dương")
        if not 1 <= self.ingest_csv_max_rows <= 500:
            raise ValueError("ingest_csv_max_rows trong 1..500 (trần của app_insert_ingest_rows)")
        if not 0 <= self.ingest_dedupe_window_days <= 30:
            raise ValueError("ingest_dedupe_window_days trong 0..30 (hàm DB kẹp cùng khoảng)")
        if not 60 <= self.ingest_upload_url_ttl_seconds <= 3600:
            raise ValueError("ingest_upload_url_ttl_seconds trong 60..3600")
        for v in (self.ingest_auto_extract_min_confidence, self.ingest_auto_jar_min_confidence):
            if not Decimal(0) <= v <= Decimal(1):
                raise ValueError("ngưỡng tin cậy trong 0..1")
        if not self.ingest_image_mime_types or not self.ingest_csv_mime_types:
            raise ValueError("cần ít nhất một MIME cho mỗi loại tệp")


def should_auto_add(
    *, kind: str, extract_confidence: float | Decimal, jar_code: str | None,
    jar_confidence: float | Decimal | None, settings: IngestSettings,
) -> bool:  # fmt: skip
    """Dòng được CHỌN SẴN (auto_added) trong khối duyệt khi đủ tin cậy. Vẫn chỉ vào sổ cái khi người dùng chốt confirm_rows."""
    if Decimal(str(extract_confidence)) < settings.ingest_auto_extract_min_confidence:
        return False
    if kind == "income":
        return True
    return (
        jar_code is not None
        and jar_confidence is not None
        and Decimal(str(jar_confidence)) >= settings.ingest_auto_jar_min_confidence
    )


# --- khóa khử trùng (cùng công thức với transactions.dedupe_key, contracts/README.md "Khử trùng") ----------------------------
def row_dedupe_key(
    *,
    app_date: date | str,
    amount_vnd: int,
    counterparty: str | None,
    content_sha256: str,
    seq: int,
) -> str:
    """`sha256("{app_date}|{abs(amount)}|{đối tác chuẩn hóa}|{client_ref}")` với `client_ref = ingest:{sha256 tệp[:16]}:{seq}`.

    Cùng tệp (cùng nội dung) nạp lại thì cùng khóa từng dòng, nên `ingest_rows_dedupe_uidx` và `transactions_dedupe_uidx` chặn dòng
    thứ hai. Dòng ghi vào sổ cái dùng ĐÚNG khóa này làm `transactions.dedupe_key`."""
    day = app_date.isoformat() if isinstance(app_date, date) else str(app_date)
    ref = f"ingest:{content_sha256[:16]}:{int(seq)}"
    raw = f"{day}|{abs(int(amount_vnd))}|{fold_text(counterparty or '')}|{ref}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def content_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- độ phủ dữ liệu: CÙNG công thức với yofina_ml.quality.data_coverage ---------------------------------------------------------
COVERAGE_FORMULA = "clamp((spend + balance_end - balance_start) / income, 0, 1)"


def coverage_ratio(facts: Mapping[str, Any] | None) -> float | None:
    """Độ phủ từ một dòng `app_get_data_coverage` (hoặc `meta.coverage` của `app_get_forecast_context`). Thu nhập 0 thì None.

    Viết lại ở đây để `yofina_core` không phụ thuộc `yofina_ml`; test khóa nó bằng đúng `quality.data_coverage`."""
    if not facts:
        return None
    income = to_vnd(facts["income_vnd"])
    if income <= 0:
        return None
    raw = (
        to_vnd(facts["spend_vnd"])
        + to_vnd(facts["balance_end_vnd"])
        - to_vnd(facts["balance_start_vnd"])
    ) / income
    return round(min(max(raw, 0.0), 1.0), 3)


# --- dựng khối ------------------------------------------------------------------------------------------------------------------
def _jar(j: Mapping[str, Any]) -> IngestJar:
    return IngestJar(
        code=j["code"], name=j["name"], color_key=j["color_key"], icon_key=j["icon_key"]
    )


def _ratio(v: Any) -> float | None:
    return None if v is None else float(Decimal(str(v)))


def build_ingest_review(
    *,
    job: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    jars: Sequence[Mapping[str, Any]],
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
) -> IngestReviewBlock:
    """Khối duyệt từ kết quả `app_get_ingest_job` (payload `job` và các payload `row`) và hũ người dùng.

    `jars`: hũ người dùng theo thứ tự hiển thị (hũ hệ thống bị bỏ); hũ đề xuất của dòng không còn trong danh sách thì vắng.
    Đếm `counts` trên MỌI dòng truyền vào; khối chỉ mang tối đa 200 dòng đầu (theo seq)."""
    user_jars = [j for j in jars if j.get("kind") != "system"][:20]
    by_code = {j["code"]: _jar(j) for j in user_jars}
    ordered = sorted(rows, key=lambda r: int(r["seq"]))
    counts = {s: 0 for s in ROW_STATUSES}
    for r in ordered:
        counts[str(r["review_status"])] += 1
    out_rows: list[IngestRow] = []
    for r in ordered[:ROW_LIMIT_IN_BLOCK]:
        code = r.get("suggested_jar_code")
        sj = by_code.get(code) if code and r["kind"] == "expense" else None
        dup = r.get("duplicate_of_transaction_id")
        out_rows.append(
            IngestRow(
                row_id=str(r["id"]),
                seq=int(r["seq"]),
                kind=r["kind"],
                app_date=_date_text(r["app_date"])[:10],
                amount_vnd=to_vnd(r["amount_vnd"]),
                counterparty=r.get("counterparty") or None,
                description=r.get("description") or None,
                extract_confidence=float(Decimal(str(r["extract_confidence"]))),
                suggested_jar=sj,
                jar_confidence=_ratio(r.get("jar_confidence")) if sj else None,
                jar_source=r.get("jar_source") if sj else None,
                review_status=r["review_status"],
                duplicate_of=str(dup) if dup and r["review_status"] == "duplicate" else None,
            )
        )
    job_id = str(job["id"])
    total = len(ordered)
    open_n = counts["auto_added"] + counts["pending"]
    if job["status"] == "review":
        text = f"Đã đọc {total} dòng ngoài ví; {open_n} dòng chờ bạn duyệt, {counts['duplicate']} dòng trùng."
    elif job["status"] == "done":
        text = (
            f"Đã thêm {counts['approved']} dòng ngoài ví vào lịch sử chi tiêu; số dư hũ không đổi."
        )
    elif job["status"] in ("failed", "rejected"):
        text = "Không đọc được tệp này. Hãy thử ảnh rõ hơn hoặc tệp CSV khác."
    else:
        text = "Đang đọc tệp của bạn."
    return IngestReviewBlock(
        v=SCHEMA_VERSION,
        id=f"ingest_review:{job_id}",
        type="ingest_review",
        trace_id=trace_id,
        fallback_text=_clip(text, 280),
        source=_source(source_tool, as_of, app_date),
        data=IngestReviewData(
            job_id=job_id,
            status=job["status"],
            source_kind=job["source_kind"],
            rows=out_rows,
            rows_total=total,
            counts=IngestCounts(**counts),
            jars=list(by_code.values()),
        ),
    )


def build_coverage_change(
    *,
    job_id: str,
    before: float | None,
    after: float | None,
    rows_added: int,
    external_spend_added_vnd: int | Decimal | str,
    jars_affected: Iterable[Mapping[str, Any]],
    forecast_refresh: str,
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    external_income_added_vnd: int | Decimal | str | None = None,
) -> CoverageChangeBlock:
    """Khối độ phủ trước và sau. `before`/`after` lấy bằng `coverage_ratio` (cùng công thức với dự báo)."""
    if forecast_refresh not in FORECAST_REFRESH:
        raise ValueError(f"forecast_refresh không hợp lệ: {forecast_refresh!r}")
    spend = to_vnd(external_spend_added_vnd)
    income = to_vnd(external_income_added_vnd) if external_income_added_vnd is not None else 0
    jars = [CoverageJar(code=j["code"], name=j["name"]) for j in jars_affected][:20]

    def pct(x: float) -> str:
        return f"{round(x * 100)}%"

    if before is not None and after is not None:
        text = f"Độ phủ dữ liệu từ {pct(before)} lên {pct(after)} sau khi thêm {rows_added} dòng ngoài ví."
    elif after is not None:
        text = f"Độ phủ dữ liệu là {pct(after)} sau khi thêm {rows_added} dòng ngoài ví."
    else:
        text = f"Đã thêm {rows_added} dòng ngoài ví ({format_vnd(spend)} chi tiêu)."
    return CoverageChangeBlock(
        v=SCHEMA_VERSION,
        id=f"coverage_change:{job_id}",
        type="coverage_change",
        trace_id=trace_id,
        fallback_text=_clip(text, 280),
        source=_source(source_tool, as_of, app_date),
        data=CoverageChangeData(
            job_id=job_id,
            before=before,
            after=after,
            rows_added=int(rows_added),
            external_spend_added_vnd=spend,
            external_income_added_vnd=income or None,
            jars_affected=jars,
            forecast_refresh=forecast_refresh,  # type: ignore[arg-type]
        ),
    )


# --- kết quả tool `ingest___*` (khớp contracts/tools/ingest.results.schema.json) --------------------------------------------
class UploadLimit(_Strict):
    source_kind: Literal["image", "csv"]
    max_bytes: Annotated[int, Field(ge=1)]
    mime_types: Annotated[
        list[Annotated[str, Field(min_length=3, max_length=100)]],
        Field(min_length=1, max_length=10),
    ]


class StartJobData(_Strict):
    """`start_job` của agent KHÔNG tạo job và không ghi gì: tệp chỉ tải lên được từ màn hình (người dùng chọn tệp và đồng ý),
    nên tool trả đường dẫn màn Nạp dữ liệu, giới hạn tệp, việc đã đồng ý chưa và job gần nhất (nếu có)."""

    upload_path: Annotated[str, Field(min_length=1, max_length=40, pattern=r"^/[a-z0-9/_-]*$")]
    limits: Annotated[list[UploadLimit], Field(min_length=1, max_length=2)]
    consent_required: bool
    latest_job_id: Uuid | None = None
    latest_job_status: IngestJobStatus | None = None


class StartJobOk(_Strict):
    status: Literal["OK"]
    as_of: IsoDateTime
    app_date: IsoDate
    data: StartJobData


class JobStatusData(_Strict):
    job_id: Uuid
    status: IngestJobStatus
    source_kind: Literal["image", "csv"]
    progress: Annotated[int, Field(ge=0, le=100)]
    rows_total: Annotated[int, Field(ge=0)]
    error_code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]*$")] | None = None
    review: IngestReviewData | None = None
    coverage_change: CoverageChangeData | None = None


class GetJobStatusOk(_Strict):
    status: Literal["OK"]
    as_of: IsoDateTime
    app_date: IsoDate
    data: JobStatusData


class ConfirmRowsNeedsConfirmation(_Strict):
    status: Literal["NEEDS_CONFIRMATION"]
    as_of: IsoDateTime
    app_date: IsoDate
    data: ConfirmActionData


class ConfirmRowsOk(_Strict):
    status: Literal["OK"]
    as_of: IsoDateTime
    app_date: IsoDate
    data: ReceiptActionData


RESULT_MODELS: dict[str, tuple[type[_Strict], ...]] = {
    "start_job": (StartJobOk,),
    "get_job_status": (GetJobStatusOk,),
    CONFIRM_ROWS: (ConfirmRowsNeedsConfirmation, ConfirmRowsOk),
}

__all__ = [
    "CONSENT_SOURCES",
    "COVERAGE_FORMULA",
    "INGEST_TOOLS",
    "JAR_SOURCES",
    "JOB_STATUSES",
    "ROW_STATUSES",
    "SOURCE_KINDS",
    "IngestSettings",
    "build_coverage_change",
    "build_ingest_review",
    "content_sha256",
    "coverage_ratio",
    "row_dedupe_key",
    "should_auto_add",
]
