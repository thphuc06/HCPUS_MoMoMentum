"""Chuẩn hóa `params` của từng tool ghi (phần hợp đồng, contracts/README.md mục "Chuẩn hóa tham số").

`params_hash = sha256(canonical_json({"tool", "params"}))` tính trên bản ĐÃ chuẩn hóa (`yofina_core.confirm`), nên
thứ người dùng thấy ở khối xác nhận cũng là thứ được ký. Hai tính chất bắt buộc:

- **Tất định**: cùng đầu vào, cùng trạng thái (`NormContext`) thì cùng kết quả.
- **Idempotent**: `normalize(normalize(x, ctx)) == normalize(x, ctx)`, và chuẩn hóa lại bản ĐÃ chuẩn hóa mà KHÔNG có
  ngữ cảnh cũng không đổi gì (nên `ConfirmService.issue/verify` chuẩn hóa lại không cần trạng thái server).

Quy tắc chung: bỏ `user_id`, `confirm_token`, `conversation_id`, `confirm_block_id`, `params_hash` và khóa lạ; bỏ
khóa có giá trị null; chuỗi cắt khoảng trắng đầu cuối, chuỗi rỗng là vắng; mã hũ chữ thường; uuid chữ thường; tiền là
số nguyên; ngày `YYYY-MM-DD` hợp lệ; mảng giữ thứ tự. Phần điền mặc định phụ thuộc trạng thái server (hũ suy từ
`tx_type`, hũ trả của nghĩa vụ, ngày đến hạn suy từ `due_day`, mã hũ mới) chỉ chạy khi có `NormContext`.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from yofina_core.money import to_vnd
from yofina_core.schedule import first_due_from_day, midpoint
from yofina_core.wallet import (
    ASSIGN_JAR,
    CONFIRM_ROWS,
    CONFIRM_SALARY,
    DATA_DELETION_SCOPES,
    DECLARABLE_OBLIGATION_KINDS,
    DELETE_MY_DATA,
    JAR_PURPOSES,
    MOVE_BETWEEN_JARS,
    NUDGE_KINDS,
    NUDGE_OPS,
    OBLIGATION_CYCLES,
    OTHER_INCOME_JAR_CODE,
    RECORD_TRANSACTION,
    RECORDABLE_FUNDING_SOURCES,
    RULE_SCOPES,
    SALARY_DECISIONS,
    SAVE_JARS,
    SCHEDULE_NUDGE,
    SYSTEM_JAR_CODES,
    UNCLASSIFIED_JAR_CODE,
    UPDATE_PROFILE,
    USER_JAR_KINDS,
    transaction_jar,
)

JAR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
TX_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
CLIENT_REF_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
MAX_VND = 99_999_999_999_999  # numeric(14,0)
RISK_LEVELS = ("low", "medium", "high")
TRANSACTION_KINDS_WRITABLE = ("expense", "income")
FUNDING_CHOICES = RECORDABLE_FUNDING_SOURCES  # external chỉ vào sổ cái qua confirm_rows
CONFIRM_ROWS_MAX = 500  # trần số dòng của một lần chốt (khớp app_insert_ingest_rows)
JAR_CODE_MAX = 32


class ParamsError(ValueError):
    """Tham số tool không hợp lệ (ứng với `ErrorCode.PARAMS_INVALID`)."""


@dataclass(frozen=True)
class TxTypeInfo:
    """Một dòng của bảng tra `tx_type_map` (bước 0 của phân loại)."""

    tx_type: str
    direction: str  # in | out | internal
    default_jar_code: str | None = None
    system_role: str | None = None
    label: str = ""
    is_selectable: bool = True
    #: loại "chuyển tiền cho người khác" (cờ của bảng tra, giao diện không đoán theo tên)
    is_person_transfer: bool = False


@dataclass(frozen=True)
class NormContext:
    """Trạng thái server dùng để điền mặc định: người gọi (ledger) dựng từ DB và bảng tra, hàm chuẩn hóa vẫn thuần."""

    today: date
    tx_types: Mapping[str, TxTypeInfo] = field(default_factory=dict)
    #: mọi mã hũ của người dùng, kể cả hai hũ hệ thống
    jar_codes: frozenset[str] = frozenset()
    #: hũ mặc định do ledger tra theo cấu hình hũ của người dùng
    obligation_jar: str | None = None


# --- tiện ích kiểu --------------------------------------------------------------------------------------
def _jar_code(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ParamsError(f"{name} phải là chuỗi mã hũ")
    code = value.strip().lower()
    if not JAR_CODE_RE.fullmatch(code):
        raise ParamsError(f"{name} không phải mã hũ hợp lệ: {value!r}")
    return code


def _clean(value: Any) -> Any:
    """Chuỗi cắt khoảng trắng, chuỗi rỗng và None thành vắng (None)."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return value


def _text(name: str, value: Any, *, max_len: int) -> str | None:
    value = _clean(value)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ParamsError(f"{name} phải là chuỗi")
    if len(value) > max_len:
        raise ParamsError(f"{name} dài tối đa {max_len} ký tự")
    return value


def _amount(name: str, value: Any, *, minimum: int = 1) -> int:
    if isinstance(value, bool):
        raise ParamsError(f"{name} không hợp lệ")
    try:
        amount = to_vnd(value)
    except (TypeError, ValueError) as exc:
        raise ParamsError(f"{name} không hợp lệ: {exc}") from exc
    if not minimum <= amount <= MAX_VND:
        raise ParamsError(f"{name} phải trong khoảng {minimum}..{MAX_VND}")
    return amount


def _int_range(name: str, value: Any, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str, Decimal)):
        raise ParamsError(f"{name} phải là số nguyên")
    try:
        n = to_vnd(value)
    except (TypeError, ValueError):
        raise ParamsError(f"{name} phải là số nguyên") from None
    if not low <= n <= high:
        raise ParamsError(f"{name} phải trong khoảng {low}..{high}")
    return n


def _uuid(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ParamsError(f"{name} phải là chuỗi UUID")
    text = value.strip().lower()
    if not UUID_RE.fullmatch(text):
        raise ParamsError(f"{name} không phải UUID hợp lệ")
    return text


def _iso_date(name: str, value: Any) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value.strip()):
        raise ParamsError(f"{name} phải có dạng YYYY-MM-DD")
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ParamsError(f"{name} không phải ngày hợp lệ") from None


def _choice(name: str, value: Any, allowed: Sequence[str]) -> str:
    if not isinstance(value, str):
        raise ParamsError(f"{name} phải là một trong: {', '.join(allowed)}")
    text = value.strip().lower()
    if text not in allowed:
        raise ParamsError(f"{name} phải là một trong: {', '.join(allowed)}")
    return text


def _percent(value: Any) -> int | float:
    """Tỷ lệ 0..100 làm tròn 2 chữ số; số nguyên giữ dạng int (hash ổn định, khớp `blocks._percent`)."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ParamsError("split_percent phải là số")
    try:
        p = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        raise ParamsError("split_percent phải là số") from None
    if not Decimal(0) <= p <= Decimal(100):
        raise ParamsError("split_percent phải trong khoảng 0..100")
    return int(p) if p == p.to_integral_value() else float(p)


def fold_text(value: str) -> str:
    """Chữ thường, bỏ dấu, gộp khoảng trắng (dùng cho khóa khử trùng và khóa luật theo đối tác)."""
    text = value.replace("đ", "d").replace("Đ", "d")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return " ".join(text.split())


def compute_dedupe_key(
    *,
    app_date: date | str,
    amount_vnd: int,
    payee_id: str | None,
    counterparty: str | None,
    client_ref: str,
) -> str:
    """Khóa khử trùng của sổ cái (contracts/README.md): `sha256("{app_date}|{abs(amount)}|{payee_id hoặc đối tác
    chuẩn hóa}|{client_ref}")`. Chỉ đặt khi có `client_ref`."""
    day = app_date.isoformat() if isinstance(app_date, date) else str(app_date)
    who = payee_id or fold_text(counterparty or "")
    raw = f"{day}|{abs(int(amount_vnd))}|{who}|{client_ref}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def slugify_jar_code(name: str) -> str:
    """Mã hũ từ tên: chữ thường, bỏ dấu, ký tự khác chữ số thành `_`, bắt đầu bằng chữ cái, tối đa 32 ký tự."""
    text = name.replace("đ", "d").replace("Đ", "d")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if not text or not text[0].isalpha():
        text = "hu_" + text if text else "hu"
    return text[:JAR_CODE_MAX].rstrip("_") or "hu"


def unique_jar_code(name: str, taken: set[str]) -> str:
    """Mã hũ mới từ tên, thêm `_2`, `_3`... nếu trùng (kể cả khi phải cắt để vừa 32 ký tự)."""
    base = slugify_jar_code(name)
    code, n = base, 1
    while code in taken:
        n += 1
        suffix = f"_{n}"
        code = base[: JAR_CODE_MAX - len(suffix)].rstrip("_") + suffix
    return code


# --- move_between_jars (phase 1, không đổi) -------------------------------------------------------------
_MOVE_KEYS = ("from_jar", "to_jar", "amount_vnd")


def normalize_move_params(params: Mapping[str, Any]) -> dict[str, Any]:
    """Chỉ giữ `from_jar`, `to_jar`, `amount_vnd`; mã hũ hạ chữ thường; tiền là số nguyên trong [1, MAX_VND].

    Hũ nguồn có thể là `tien_vao_khac` (cách gán "Tiền vào khác" vào hũ)."""
    missing = [k for k in _MOVE_KEYS if k not in params]
    if missing:
        raise ParamsError(f"Thiếu tham số: {', '.join(missing)}")
    from_jar = _jar_code("from_jar", params["from_jar"])
    to_jar = _jar_code("to_jar", params["to_jar"])
    if from_jar == to_jar:
        raise ParamsError("Hũ nguồn và hũ đích phải khác nhau")
    return {
        "from_jar": from_jar,
        "to_jar": to_jar,
        "amount_vnd": _amount("amount_vnd", params["amount_vnd"]),
    }


# --- record_transaction ---------------------------------------------------------------------------------
def normalize_record_transaction(
    params: Mapping[str, Any], ctx: NormContext | None
) -> dict[str, Any]:
    if _clean(params.get("kind")) is None or params.get("amount_vnd") is None:
        raise ParamsError("Thiếu tham số: kind, amount_vnd")
    kind = _choice("kind", params["kind"], TRANSACTION_KINDS_WRITABLE)
    out: dict[str, Any] = {"kind": kind, "amount_vnd": _amount("amount_vnd", params["amount_vnd"])}
    funding = _clean(params.get("funding"))
    funding = _choice("funding", funding, FUNDING_CHOICES) if funding is not None else "jar"
    obligation_id = _clean(params.get("obligation_id"))
    if kind == "income" and (funding == "credit" or obligation_id is not None):
        raise ParamsError("Tiền vào không dùng được hạn mức Trả sau hay trả nghĩa vụ")
    if funding == "credit" and obligation_id is not None:
        raise ParamsError("Không trả nghĩa vụ bằng hạn mức Trả sau")
    out["funding"] = funding
    if (pay_jar := _clean(params.get("pay_jar"))) is not None:
        if funding != "credit":
            raise ParamsError("pay_jar chỉ dành cho giao dịch Trả sau")
        out["pay_jar"] = _jar_code("pay_jar", pay_jar)
    if obligation_id is not None:
        out["obligation_id"] = _uuid("obligation_id", obligation_id)
    tx_type = _clean(params.get("tx_type"))
    if tx_type is not None:
        if not isinstance(tx_type, str):
            raise ParamsError("tx_type phải là chuỗi")
        tx_type = tx_type.strip().lower()
        if not TX_TYPE_RE.fullmatch(tx_type):
            raise ParamsError("tx_type không hợp lệ")
    else:
        tx_type = (
            "income_other"
            if kind == "income"
            else ("obligation_payment" if obligation_id is not None else "other_expense")
        )
    if ctx is not None and ctx.tx_types:
        info = ctx.tx_types.get(tx_type)
        if info is None or info.direction == "internal":
            raise ParamsError(f"Loại giao dịch không hợp lệ: {tx_type}")
        if info.direction != ("in" if kind == "income" else "out"):
            raise ParamsError(f"Loại giao dịch {tx_type} không hợp với {kind}")
    out["tx_type"] = tx_type
    if kind == "income":
        out["jar"] = (
            OTHER_INCOME_JAR_CODE  # tiền vào luôn nằm ở Tiền vào khác cho tới khi xác nhận/gán
        )
    else:
        jar = _clean(params.get("jar"))
        if jar is not None:
            out["jar"] = _jar_code("jar", jar)
        elif ctx is not None:
            info = ctx.tx_types.get(tx_type)
            is_bill = info is not None and info.default_jar_code == "hoa_don"
            if (
                funding == "jar" and obligation_id is None
                and (is_bill or tx_type == "obligation_payment")
            ):
                if ctx.obligation_jar is None:
                    raise ParamsError("Chọn hũ để trả khoản nghĩa vụ này.")
                out["jar"] = ctx.obligation_jar
            else:
                out["jar"] = _default_expense_jar(tx_type, ctx)
    for key, limit in (("counterparty", 120), ("note", 200)):
        text = _text(key, params.get(key), max_len=limit)
        if text is not None:
            out[key] = text
    if _clean(params.get("payee_id")) is not None:
        out["payee_id"] = _uuid("payee_id", params["payee_id"])
    ref = _clean(params.get("client_ref"))
    if ref is not None:
        if not isinstance(ref, str) or not CLIENT_REF_RE.fullmatch(ref):
            raise ParamsError("client_ref chỉ gồm chữ, số, _ . : - và tối đa 64 ký tự")
        out["client_ref"] = ref
    return out


def _default_expense_jar(tx_type: str, ctx: NormContext) -> str:
    """Bước 0 của phân loại: `default_jar_code` nếu người dùng có hũ đó, `system_role` thì hũ hệ thống, không thì
    Chưa phân loại."""
    info = ctx.tx_types.get(tx_type)
    if info is not None:
        if jar := transaction_jar(info.default_jar_code, ctx.jar_codes, tx_type=tx_type):
            return jar
        if info.system_role:
            return SYSTEM_JAR_CODES[info.system_role]
    return UNCLASSIFIED_JAR_CODE


# --- assign_jar -----------------------------------------------------------------------------------------
def normalize_assign_jar(params: Mapping[str, Any]) -> dict[str, Any]:
    if _clean(params.get("transaction_id")) is None or _clean(params.get("jar")) is None:
        raise ParamsError("Thiếu tham số: transaction_id, jar")
    remember = _clean(params.get("remember"))
    return {
        "transaction_id": _uuid("transaction_id", params["transaction_id"]),
        "jar": _jar_code("jar", params["jar"]),
        "remember": _choice("remember", remember, RULE_SCOPES) if remember is not None else "once",
    }


# --- update_profile -------------------------------------------------------------------------------------
_OBLIGATION_FIELDS = (
    "kind", "name", "amount_vnd", "amount_min_vnd", "amount_max_vnd", "fee_vnd",
    "due_date", "due_day", "cycle", "pay_jar", "is_essential",
)  # fmt: skip


def normalize_obligation_change(raw: Any, ctx: NormContext | None) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ParamsError("obligation phải là một đối tượng")
    op = _choice("obligation.op", _clean(raw.get("op")), ("upsert", "delete"))
    oid = _clean(raw.get("obligation_id"))
    out: dict[str, Any] = {"op": op}
    if oid is not None:
        out["obligation_id"] = _uuid("obligation_id", oid)
    if op == "delete":
        if oid is None:
            raise ParamsError("Xóa nghĩa vụ cần obligation_id")
        return out
    creating = oid is None
    kind = _clean(raw.get("kind"))
    if kind is not None:
        kind = _choice("obligation.kind", kind, DECLARABLE_OBLIGATION_KINDS)
        out["kind"] = kind
    elif creating:
        raise ParamsError(f"Khoản nghĩa vụ mới cần kind ({', '.join(DECLARABLE_OBLIGATION_KINDS)})")
    name = _text("obligation.name", raw.get("name"), max_len=80)
    if name is not None:
        out["name"] = name
    elif creating:
        raise ParamsError("Khoản nghĩa vụ mới cần name")
    low = raw.get("amount_min_vnd")
    high = raw.get("amount_max_vnd")
    if (low is None) != (high is None):
        raise ParamsError("amount_min_vnd và amount_max_vnd phải đi cùng nhau")
    amount = raw.get("amount_vnd")
    if low is not None and high is not None:
        lo, hi = _amount("amount_min_vnd", low), _amount("amount_max_vnd", high)
        if lo > hi:
            raise ParamsError("amount_min_vnd không được lớn hơn amount_max_vnd")
        am = midpoint(lo, hi) if amount is None else _amount("amount_vnd", amount)
        if not lo <= am <= hi:
            raise ParamsError("amount_vnd phải nằm trong khoảng min..max")
        out.update(amount_min_vnd=lo, amount_max_vnd=hi, amount_vnd=am)
    elif amount is not None:
        out["amount_vnd"] = _amount("amount_vnd", amount)
    elif creating:
        raise ParamsError(
            "Khoản nghĩa vụ mới cần amount_vnd (hoặc amount_min_vnd và amount_max_vnd)"
        )
    fee = raw.get("fee_vnd")
    if fee is not None:
        out["fee_vnd"] = _amount("fee_vnd", fee, minimum=0)
    elif creating:
        out["fee_vnd"] = 0
    cycle = _clean(raw.get("cycle"))
    if cycle is not None:
        out["cycle"] = _choice("obligation.cycle", cycle, OBLIGATION_CYCLES)
    elif creating:
        out["cycle"] = "monthly"
    if raw.get("due_day") is not None:
        out["due_day"] = _int_range("due_day", raw["due_day"], 1, 31)
    due = _clean(raw.get("due_date"))
    if due is not None:
        out["due_date"] = _iso_date("due_date", due).isoformat()
    ess = raw.get("is_essential")
    if ess is not None:
        if not isinstance(ess, bool):
            raise ParamsError("is_essential phải là true hoặc false")
        out["is_essential"] = ess
    elif creating:
        out["is_essential"] = False
    pay_jar = _clean(raw.get("pay_jar"))
    if pay_jar is not None:
        out["pay_jar"] = _jar_code("pay_jar", pay_jar)
    elif creating and ctx is not None and ctx.obligation_jar:
        out["pay_jar"] = ctx.obligation_jar
    if creating:
        if "due_date" not in out and "due_day" not in out:
            raise ParamsError("Khoản nghĩa vụ mới cần due_date hoặc due_day")
        if "due_date" not in out and out["cycle"] == "once":
            raise ParamsError("Khoản một lần cần due_date")
        if "due_date" not in out and ctx is not None:
            out["due_date"] = first_due_from_day(out["due_day"], ctx.today).isoformat()
        if out.get("cycle") == "monthly" and "due_day" not in out and "due_date" in out:
            out["due_day"] = date.fromisoformat(out["due_date"]).day
    return out


def normalize_update_profile(params: Mapping[str, Any], ctx: NormContext | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    name = _text("display_name", params.get("display_name"), max_len=80)
    if name is not None:
        out["display_name"] = name
    if params.get("monthly_salary_vnd") is not None:
        out["monthly_salary_vnd"] = _amount("monthly_salary_vnd", params["monthly_salary_vnd"])
    if params.get("payday_day") is not None:
        out["payday_day"] = _int_range("payday_day", params["payday_day"], 1, 31)
    risk = _clean(params.get("risk_tolerance"))
    if risk is not None:
        out["risk_tolerance"] = _choice("risk_tolerance", risk, RISK_LEVELS)
    if params.get("obligation") is not None:
        out["obligation"] = normalize_obligation_change(params["obligation"], ctx)
    if not out:
        raise ParamsError("Cần ít nhất một thay đổi")
    return out


def jar_commitments(jar: Mapping[str, Any], old: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve and validate saving metadata against the current jar at preview and write."""
    purpose = jar.get("purpose", old.get("purpose")) if jar["kind"] == "saving" else None
    same_purpose = purpose is not None and purpose == old.get("purpose")
    old_date = str(old["goal_date"]) if same_purpose and old.get("goal_date") is not None else None
    old_amount = old.get("goal_vnd") if same_purpose else None
    goal_date = jar.get("goal_date", old_date)
    goal_vnd = jar.get("goal_vnd", int(old_amount) if old_amount is not None else None)
    if goal_date is not None and goal_vnd is None and purpose not in ("sinking", "long_term"):
        raise ParamsError("goal_date cần goal_vnd")
    if purpose == "goal" and (goal_vnd is None or goal_date is None):
        raise ParamsError("Hũ Mục tiêu cần số tiền và ngày mục tiêu")
    if purpose == "sinking" and old_date is not None and goal_date != old_date:
        raise ParamsError("Ngày đã cam kết của Quỹ dồn được giữ nguyên")
    previous_items = (old.get("sinking_items") or []) if same_purpose else []
    items = jar.get("sinking_items", previous_items)
    if items and purpose != "sinking":
        raise ParamsError("sinking_items chỉ dành cho Quỹ dồn")
    old_dates = {item["name"].casefold(): item["needed_date"] for item in previous_items}
    if any(
        old_dates.get(item["name"].casefold(), item["needed_date"]) != item["needed_date"]
        for item in items
    ):
        raise ParamsError("Ngày đã cam kết của Quỹ dồn được giữ nguyên")
    return {"purpose": purpose, "goal_vnd": goal_vnd, "goal_date": goal_date, "sinking_items": items}


# --- save_jars ------------------------------------------------------------------------------------------
def normalize_save_jars(params: Mapping[str, Any], ctx: NormContext | None) -> dict[str, Any]:
    raw = params.get("jars")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or not 1 <= len(raw) <= 20:
        raise ParamsError("jars phải là danh sách từ 1 đến 20 hũ")
    system_codes = set(SYSTEM_JAR_CODES.values())
    jars: list[dict[str, Any]] = []
    given: list[str | None] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ParamsError("Mỗi hũ phải là một đối tượng")
        name = _text("name", item.get("name"), max_len=40)
        if name is None:
            raise ParamsError("Mỗi hũ cần name")
        jar: dict[str, Any] = {"name": name}
        for key in ("color_key", "icon_key"):
            value = _clean(item.get(key))
            if not isinstance(value, str) or not KEY_RE.fullmatch(value.strip().lower()):
                raise ParamsError(f"{key} không hợp lệ")
            jar[key] = value.strip().lower()
        jar["kind"] = _choice("kind", _clean(item.get("kind")), USER_JAR_KINDS)
        purpose = _clean(item.get("purpose"))
        if purpose is not None:
            if jar["kind"] != "saving":
                raise ParamsError("purpose chỉ dành cho hũ để dành")
            jar["purpose"] = _choice("purpose", purpose, JAR_PURPOSES)
        if item.get("split_percent") is None:
            raise ParamsError("Mỗi hũ cần split_percent")
        jar["split_percent"] = _percent(item["split_percent"])
        code = _clean(item.get("code"))
        given_code = _jar_code("code", code) if code is not None else None
        if given_code in system_codes:
            raise ParamsError("Mã hũ này dành cho hũ hệ thống")
        if item.get("goal_vnd") is not None:
            jar["goal_vnd"] = _amount("goal_vnd", item["goal_vnd"])
        gdate = _clean(item.get("goal_date"))
        if gdate is not None:
            jar["goal_date"] = _iso_date("goal_date", gdate).isoformat()
        if "sinking_items" in item:
            raw_items = item["sinking_items"]
            if not isinstance(raw_items, list) or len(raw_items) > 40:
                raise ParamsError("sinking_items phải là danh sách tối đa 40 khoản")
            entries = []
            names: set[str] = set()
            for entry in raw_items:
                if not isinstance(entry, Mapping) or set(entry) != {
                    "name", "amount_vnd", "needed_date"
                }:
                    raise ParamsError("Khoản Quỹ dồn cần tên, số tiền và ngày cần")
                title = _text("sinking_items.name", entry["name"], max_len=80)
                if title is None or title.casefold() in names:
                    raise ParamsError("Tên khoản Quỹ dồn phải có và không được trùng")
                names.add(title.casefold())
                entries.append({
                    "name": title,
                    "amount_vnd": _amount("sinking_items.amount_vnd", entry["amount_vnd"]),
                    "needed_date": _iso_date("sinking_items.needed_date", entry["needed_date"]).isoformat(),
                })
            jar["sinking_items"] = entries
        if given_code is None or (ctx is not None and given_code not in ctx.jar_codes):
            jar_commitments(jar, {})
        jars.append(jar)
        given.append(given_code)
    dup = {c for c in given if c is not None and given.count(c) > 1}
    if dup:
        raise ParamsError(f"Mã hũ trùng: {', '.join(sorted(dup))}")
    total = sum(Decimal(str(j["split_percent"])) for j in jars)
    if total != Decimal(100):
        raise ParamsError(f"Tổng tỷ lệ chia phải bằng 100 (hiện là {total})")
    taken = {c for c in given if c is not None} | system_codes
    if ctx is not None:
        taken |= set(ctx.jar_codes)
    for jar, code in zip(jars, given, strict=True):
        if code is not None:
            jar["code"] = code
        elif ctx is not None:
            jar["code"] = unique_jar_code(jar["name"], taken)
            taken.add(jar["code"])
    return {"jars": jars}


# --- confirm_salary -------------------------------------------------------------------------------------
def normalize_confirm_salary(params: Mapping[str, Any]) -> dict[str, Any]:
    if _clean(params.get("salary_event_id")) is None or _clean(params.get("decision")) is None:
        raise ParamsError("Thiếu tham số: salary_event_id, decision")
    decision = _choice("decision", params["decision"], SALARY_DECISIONS)
    update = params.get("update_declared_salary")
    if update is not None and not isinstance(update, bool):
        raise ParamsError("update_declared_salary phải là true hoặc false")
    return {
        "salary_event_id": _uuid("salary_event_id", params["salary_event_id"]),
        "decision": decision,
        "update_declared_salary": bool(update) and decision == "split",
    }


# --- schedule_nudge (phase 3) ---------------------------------------------------------------------------
def normalize_schedule_nudge(params: Mapping[str, Any], ctx: NormContext | None) -> dict[str, Any]:
    """`op` mặc định `create`. `create`: bắt buộc `kind` và `fire_on` (ngày mô phỏng, SAU hôm nay khi có ngữ cảnh), tùy chọn
    `jar_code`, `note` (tối đa 120 ký tự), `scenario_id`. `cancel`: chỉ `nudge_id`. Idempotent như mọi bộ chuẩn hóa."""
    op_raw = _clean(params.get("op"))
    op = _choice("op", op_raw, NUDGE_OPS) if op_raw is not None else "create"
    if op == "cancel":
        if _clean(params.get("nudge_id")) is None:
            raise ParamsError("Hủy lời nhắc cần nudge_id")
        return {"op": "cancel", "nudge_id": _uuid("nudge_id", params["nudge_id"])}
    if _clean(params.get("kind")) is None or _clean(params.get("fire_on")) is None:
        raise ParamsError("Thiếu tham số: kind, fire_on")
    out: dict[str, Any] = {
        "op": "create",
        "kind": _choice("kind", params["kind"], NUDGE_KINDS),
    }
    fire_on = _iso_date("fire_on", params["fire_on"])
    if ctx is not None and fire_on <= ctx.today:
        raise ParamsError("fire_on phải sau hôm nay (ngày mô phỏng)")
    out["fire_on"] = fire_on.isoformat()
    jar = _clean(params.get("jar_code"))
    if jar is not None:
        out["jar_code"] = _jar_code("jar_code", jar)
    note = _text("note", params.get("note"), max_len=120)
    if note is not None:
        out["note"] = note
    if _clean(params.get("scenario_id")) is not None:
        out["scenario_id"] = _uuid("scenario_id", params["scenario_id"])
    return out


# --- confirm_rows (phase 5, F6) -------------------------------------------------------------------------
def _uuid_list(name: str, raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ParamsError(f"{name} phải là danh sách")
    return [_uuid(name, x) for x in raw]


def normalize_confirm_rows(params: Mapping[str, Any]) -> dict[str, Any]:
    """`job_id`; `rows` là các dòng ĐƯỢC GHI vào sổ cái, mỗi dòng `{row_id, jar?, amount_vnd?}` (`jar` là hũ của dòng chi; vắng với
    dòng thu hoặc khi giữ hũ đề xuất đã hiển thị; `amount_vnd` là số VND người dùng nhập cho dòng ngoại tệ, vắng thì giữ số ước tính
    đã hiển thị), sắp theo `row_id`; `reject_row_ids` sắp tăng dần. Không cần trạng thái server nên idempotent không cần ngữ cảnh. Một
    dòng không được vừa ghi vừa bỏ; phải có ít nhất một dòng."""
    if _clean(params.get("job_id")) is None:
        raise ParamsError("Thiếu tham số: job_id")
    raw_rows = params.get("rows")
    if raw_rows is None:
        raw_rows = []
    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes)):
        raise ParamsError("rows phải là danh sách")
    rows: dict[str, dict[str, Any]] = {}
    for item in raw_rows:
        if not isinstance(item, Mapping):
            raise ParamsError("Mỗi dòng trong rows phải là một đối tượng {row_id, jar}")
        rid = _uuid("row_id", item.get("row_id"))
        if rid in rows:
            raise ParamsError(f"row_id lặp lại: {rid}")
        row: dict[str, Any] = {"row_id": rid}
        jar = _clean(item.get("jar"))
        if jar is not None:
            row["jar"] = _jar_code("jar", jar)
        if item.get("amount_vnd") not in (None, ""):
            row["amount_vnd"] = _amount("amount_vnd", item["amount_vnd"])
        rows[rid] = row
    rejects = _uuid_list("reject_row_ids", params.get("reject_row_ids"))
    if len(set(rejects)) != len(rejects):
        raise ParamsError("reject_row_ids có id lặp lại")
    both = set(rows) & set(rejects)
    if both:
        raise ParamsError("Một dòng không thể vừa ghi vừa bỏ")
    if not rows and not rejects:
        raise ParamsError("Cần ít nhất một dòng để ghi hoặc bỏ")
    if len(rows) > CONFIRM_ROWS_MAX or len(rejects) > CONFIRM_ROWS_MAX:
        raise ParamsError(f"Tối đa {CONFIRM_ROWS_MAX} dòng mỗi lần")
    out: dict[str, Any] = {"job_id": _uuid("job_id", params["job_id"])}
    out["rows"] = [rows[k] for k in sorted(rows)]
    out["reject_row_ids"] = sorted(rejects)
    return out


# --- delete_my_data (phase 5, quyền riêng tư) -------------------------------------------------------------
def normalize_delete_my_data(params: Mapping[str, Any]) -> dict[str, Any]:
    """`{scope: "all"}`: phạm vi duy nhất là xóa tất cả (vắng thì điền `all` để thứ được ký luôn ghi rõ phạm vi). Không cần
    trạng thái server nên idempotent không cần ngữ cảnh; khóa lạ bị bỏ như mọi tool."""
    scope = _clean(params.get("scope"))
    return {"scope": "all" if scope is None else _choice("scope", scope, DATA_DELETION_SCOPES)}


def normalize_params(
    tool: str, params: Mapping[str, Any], ctx: NormContext | None = None
) -> dict[str, Any]:
    """Chuẩn hóa `params` của một tool ghi. `ctx` (trạng thái server) cho phép điền mặc định phụ thuộc trạng thái."""
    if tool == MOVE_BETWEEN_JARS:
        return normalize_move_params(params)
    if tool == RECORD_TRANSACTION:
        return normalize_record_transaction(params, ctx)
    if tool == ASSIGN_JAR:
        return normalize_assign_jar(params)
    if tool == UPDATE_PROFILE:
        return normalize_update_profile(params, ctx)
    if tool == SAVE_JARS:
        return normalize_save_jars(params, ctx)
    if tool == CONFIRM_SALARY:
        return normalize_confirm_salary(params)
    if tool == SCHEDULE_NUDGE:
        return normalize_schedule_nudge(params, ctx)
    if tool == CONFIRM_ROWS:
        return normalize_confirm_rows(params)
    if tool == DELETE_MY_DATA:
        return normalize_delete_my_data(params)
    raise ParamsError(f"Tool không hỗ trợ xác nhận: {tool!r}")
