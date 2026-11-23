"""Phần ĐỌC của danh sách "Xem lại" và hỏi gộp (F2): dùng chung giữa `GET /review` (khối `review_list`) và tool `get_unclassified`.

Quy ước:
- Danh sách lấy từ hàm `app_get_review_list` (mức `review`: đã được tự gán và đánh dấu cần xem lại; mức `ask`, chế độ `daily_ask`: đang ở
  hũ Chưa phân loại) và `app_get_review_ask` (câu hỏi gộp của một ngày), migration 0052.
- **Lý do của gợi ý do code dựng, không do model viết** và dựng LÚC ĐỌC từ dữ kiện sổ cái (cột `transactions.suggested_jars` chỉ lưu mã
  hũ): giống N giao dịch trước gửi cho cùng người, loại giao dịch thường vào hũ này, lời nhắn, hoặc số tiền và thời điểm. Độ tin cậy
  chỉ có ở gợi ý đầu (cột `classification_confidence`).
- Không ghi gì (việc "đã hỏi hôm nay" do pipeline phân loại ghi).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from yofina_core.db import DataApi, Row
from yofina_core.wallet import REVIEW_MODES
from yofina_ledger import convert

REASON_MAX = 80
LIST_LIMIT_DEFAULT = 20
LIST_LIMIT_MAX = 50

SQL_REVIEW_LIST = "SELECT * FROM app_get_review_list(CAST(:uid AS text), CAST(:mode AS text), CAST(:lim AS integer))"
SQL_REVIEW_ASK = "SELECT * FROM app_get_review_ask(CAST(:uid AS text), CAST(:d AS date))"
# Với mỗi (giao dịch, hũ gợi ý): số giao dịch TRƯỚC (khác chính nó, không phải chuyển hũ) của cùng người nhận (hoặc cùng đối tác khi
# không có người nhận đã lưu) đang ở hũ đó. Cần set_config nên chạy trong transaction.
SQL_HISTORY_COUNTS = (
    "SELECT s.tx_id, s.jar_code, s.by_payee, "
    "(SELECT count(*) FROM transactions h WHERE h.user_id = :uid AND h.id <> s.tx_id AND h.kind <> 'transfer' "
    "AND h.jar_code = s.jar_code AND ((s.payee_id IS NOT NULL AND h.payee_id = s.payee_id) "
    "OR (s.payee_id IS NULL AND s.merchant IS NOT NULL AND lower(h.merchant) = lower(s.merchant)))) AS n "
    "FROM jsonb_to_recordset(CAST(:items AS jsonb)) AS s(tx_id uuid, jar_code text, payee_id uuid, merchant text, by_payee boolean) "
    "LIMIT 200"
)


def parse_limit(raw: Any) -> int:
    from yofina_core.errors import ErrorCode, YofinaError

    if raw in (None, ""):
        return LIST_LIMIT_DEFAULT
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise YofinaError(ErrorCode.PARAMS_INVALID, "limit phải là số nguyên.") from None
    return max(1, min(n, LIST_LIMIT_MAX))


def parse_mode(raw: Any) -> str:
    from yofina_core.errors import ErrorCode, YofinaError

    if raw in (None, ""):
        return "review"
    if raw not in REVIEW_MODES:
        raise YofinaError(
            ErrorCode.PARAMS_INVALID, f"mode phải là một trong {', '.join(REVIEW_MODES)}."
        )
    return str(raw)


def reason_text(*, n_same: int, by_payee: bool, type_default: bool, has_note: bool) -> str:
    """Lý do của MỘT gợi ý, dựng từ tín hiệu đã dùng (xem docstring module). Luôn dưới `REASON_MAX` ký tự."""
    if n_same > 0:
        text = (
            f"Giống {n_same} giao dịch trước gửi cho cùng người"
            if by_payee
            else f"Giống {n_same} giao dịch trước ở cùng nơi"
        )
    elif type_default:
        text = "Loại giao dịch này thường vào hũ này"
    elif has_note:
        text = "Gợi ý từ lời nhắn của giao dịch"
    else:
        text = "Gợi ý từ số tiền và thời điểm giao dịch"
    return text[:REASON_MAX]


def history_counts(
    db: DataApi,
    user_id: str,
    entries: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], int]:
    """(id giao dịch, mã hũ) -> số giao dịch trước cùng người nhận (hoặc cùng đối tác) ở hũ đó. `entries`: tx_id, jar_code, payee_id,
    merchant. Rỗng thì không gọi DB."""
    rows = [
        {
            "tx_id": str(e["tx_id"]),
            "jar_code": e["jar_code"],
            "payee_id": str(e["payee_id"]) if e.get("payee_id") else None,
            "merchant": e.get("merchant") or None,
            "by_payee": bool(e.get("payee_id")),
        }
        for e in entries
    ]
    if not rows:
        return {}
    with db.transaction(user_id) as t:
        out = t.execute(SQL_HISTORY_COUNTS, {"uid": user_id, "items": rows})
    return {(str(r["tx_id"]), r["jar_code"]): int(r["n"]) for r in out}


def suggestion_entries(
    tx_id: str,
    suggested: Sequence[str],
    *,
    jar_names: Mapping[str, Any],
    payee_id: Any,
    merchant: str | None,
    tx_type: str | None,
    note: str | None,
    type_defaults: Mapping[str, str | None],
    counts: Mapping[tuple[str, str], int],
    confidence: Any,
) -> list[dict[str, Any]]:
    """Gợi ý (tối đa 2, chỉ hũ còn tồn tại) kèm lý do do code dựng; `confidence` chỉ gắn cho gợi ý đầu."""
    out: list[dict[str, Any]] = []
    for rank, code in enumerate(suggested[:2]):
        if code not in jar_names:
            continue
        reason = reason_text(
            n_same=counts.get((tx_id, code), 0),
            by_payee=bool(payee_id),
            type_default=bool(tx_type and type_defaults.get(tx_type) == code),
            has_note=bool(note),
        )
        entry: dict[str, Any] = {"code": code, "reason": reason}
        if rank == 0 and confidence is not None:
            entry["confidence"] = round(float(confidence), 3)
        out.append(entry)
    return out


def list_rows(db: DataApi, user_id: str, mode: str, limit: int) -> list[Row]:
    return db.query(
        SQL_REVIEW_LIST, {"uid": user_id, "mode": mode, "lim": limit}, max_rows=LIST_LIMIT_MAX
    )


def ask_row(db: DataApi, user_id: str, ask_date: date) -> Row | None:
    rows = db.query(SQL_REVIEW_ASK, {"uid": user_id, "d": ask_date}, max_rows=1)
    return rows[0] if rows else None


def counterparty_of(row: Mapping[str, Any]) -> str | None:
    name = row.get("payee_name") or row.get("merchant")
    return str(name)[:120] if name else None


def can_remember(row: Mapping[str, Any]) -> bool:
    """Có người nhận đã lưu hoặc đối tác để nhớ thành luật 'luôn luôn cho người này' (khớp điều kiện của `assign_jar`)."""
    return bool(row.get("payee_id") or row.get("merchant"))


def amount_positive(row: Mapping[str, Any]) -> int:
    return abs(convert.vnd(row["amount_vnd"]))
