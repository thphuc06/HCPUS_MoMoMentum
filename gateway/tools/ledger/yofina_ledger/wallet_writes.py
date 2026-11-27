"""Phía GHI của ví mô phỏng (phase 2): chuẩn hóa, kiểm nghiệp vụ, xem trước (`confirm_action`), ghi, biên nhận, sự kiện.

Mixin của `LedgerService` cho năm tool ghi ngoài chuyển hũ: `record_transaction`, `assign_jar`, `update_profile`,
`save_jars`, `confirm_salary`. Cùng cơ chế ADR-0002 với chuyển hũ: không token thì chỉ xem trước (không ghi), có token hợp lệ
(dùng một lần, gắn người + tool + hash tham số) thì mỗi thao tác MỘT transaction rồi phát sự kiện SAU commit.

Luồng của một thao tác: `_normalize` (tham số + trạng thái -> bản chuẩn hóa đầy đủ) -> `_validate` (nghiệp vụ + xem trước)
-> [cấp token] -> `apply_action` (kiểm token, ghi, biên nhận, sự kiện).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from yofina_core.blocks import (
    ConfirmActionBlock,
    ReceiptActionBlock,
    block_to_wire,
    build_confirm_action,
    build_receipt_action,
)
from yofina_core.clock import latest_payday, next_payday
from yofina_core.confirm import ParamsError
from yofina_core.errors import PAY_JAR_FIELD, ErrorCode, YofinaError
from yofina_core.money import format_vnd
from yofina_core.params import NormContext, compute_dedupe_key, jar_commitments, normalize_params
from yofina_core.schedule import advance_due, bnpl_due_date
from yofina_core.wallet import (
    ASSIGN_JAR,
    BNPL_PRODUCT_CODE,
    CONFIRM_SALARY,
    OTHER_INCOME_JAR_CODE,
    RECORD_TRANSACTION,
    SAVE_JARS,
    SCHEDULE_NUDGE,
    UNCLASSIFIED_JAR_CODE,
    UPDATE_PROFILE,
    resolve_obligation_pay_jar,
    split_amount,
    transaction_jar,
)
from yofina_ledger import classify_write, convert, events, split_proposal
from yofina_ledger.classify_config import load_thresholds as classify_thresholds
from yofina_ledger.repo_wallet import ClaimSpec, WriteResult

log = logging.getLogger("yofina.ledger.writes")

TX_TYPE_SALARY = "salary"
SOURCE_APP = "app"
#: nhãn hiển thị của loại nhắc (phase 3)
NUDGE_KIND_LABELS = {
    "runout_warning": "Cảnh báo sắp cạn hũ",
    "obligation_due": "Nghĩa vụ sắp đến hạn",
    "salary_pending": "Lương chờ xác nhận",
    "review_needed": "Giao dịch cần xem lại",
    "low_data": "Cần thêm dữ liệu",
    "purchase_review": "Xem lại khoản định mua",
}
JAR_KIND_LABELS = {"spending": "Chi tiêu", "obligation": "Nghĩa vụ", "saving": "Để dành"}
JAR_PURPOSE_LABELS = {
    None: "chưa đặt",
    "buffer": "Dự phòng",
    "goal": "Mục tiêu",
    "sinking": "Quỹ dồn",
    "long_term": "Dài hạn",
}


def _dm(value: date) -> str:
    return f"{value.day:02d}/{value.month:02d}"


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _change(label: str, after: str, before: str | None = None) -> dict[str, str]:
    item = {"label": _clip(label, 60), "after": _clip(after, 120)}
    if before is not None:
        item["before"] = _clip(before, 80)
    return item


def _sinking_item_changes(
    jar_name: str, before: list[dict[str, Any]], after: list[dict[str, Any]]
) -> list[dict[str, str]]:
    old = {item["name"].casefold(): item for item in before}
    new = {item["name"].casefold(): item for item in after}
    changes = []
    for key, item in new.items():
        previous = old.get(key)
        if item == previous:
            continue
        amount = format_vnd(item["amount_vnd"])
        needed = _dm(date.fromisoformat(item["needed_date"]))
        label = f"Khoản {item['name']}"
        if previous is None:
            changes.append(_change(f"Khoản mới: {item['name']}", f"{amount}, cần trước {needed}"))
        else:
            old_amount = format_vnd(previous["amount_vnd"])
            if previous["name"] != item["name"]:
                label = f"Khoản {previous['name']} → {item['name']}"
            changes.append(_change(label, f"{amount}, cần trước {needed}", old_amount))
    for key, item in old.items():
        if key not in new:
            amount = format_vnd(item["amount_vnd"])
            needed = _dm(date.fromisoformat(item["needed_date"]))
            changes.append(
                _change(f"Bỏ khoản {item['name']}", "không còn", f"{amount}, cần trước {needed}")
            )
    if [key for key in old if key in new] != [key for key in new if key in old]:
        changes.append(
            _change(f"Thứ tự khoản hũ {jar_name}", ", ".join(item["name"] for item in after))
        )
    return changes


def _jar_setting_changes(
    cur: Mapping[str, Any], jar: Mapping[str, Any], sort_order: int
) -> list[dict[str, str]]:
    name = jar["name"]
    changes = []
    if cur["name"] != name:
        changes.append(_change("Tên hũ", name, cur["name"]))
    if cur["kind"] != jar["kind"]:
        changes.append(
            _change(f"Loại hũ {name}", JAR_KIND_LABELS[jar["kind"]], JAR_KIND_LABELS[cur["kind"]])
        )
    if cur.get("purpose") != jar["purpose"]:
        changes.append(
            _change(
                f"Mục đích hũ {name}",
                JAR_PURPOSE_LABELS[jar["purpose"]],
                JAR_PURPOSE_LABELS[cur.get("purpose")],
            )
        )
    display = []
    for key, label in (("color_key", "màu"), ("icon_key", "biểu tượng")):
        if cur[key] != jar[key]:
            display.append(f"{label} {cur[key]} → {jar[key]}")
    old_order = cur["sort_order"]
    if old_order != sort_order:
        display.append(f"vị trí {old_order + 1} → {sort_order + 1}")
    if display:
        changes.append(_change(f"Hiển thị hũ {name}", ", ".join(display)))
    return changes


def _jar_goal_change(cur: Mapping[str, Any], jar: Mapping[str, Any]) -> dict[str, str] | None:
    old_amount, amount = cur.get("goal_vnd"), jar["goal_vnd"]
    if old_amount is not None:
        old_amount = convert.vnd(old_amount)
    old_date, goal_date = cur.get("goal_date"), jar["goal_date"]
    parts = []
    if old_amount != amount:
        before = format_vnd(old_amount) if old_amount is not None else "chưa đặt"
        after = format_vnd(amount) if amount is not None else "bỏ"
        parts.append(f"mục tiêu {before} → {after}")
    if (str(old_date) if old_date is not None else None) != goal_date:
        before = _dm(date.fromisoformat(str(old_date))) if old_date is not None else "chưa đặt"
        after = _dm(date.fromisoformat(goal_date)) if goal_date is not None else "bỏ"
        parts.append(f"hạn {before} → {after}")
    return _change(jar["name"], ", ".join(parts)) if parts else None


@dataclass
class UserState:
    """Trạng thái người dùng đọc một lần cho một thao tác: độ lệch đồng hồ và mọi hũ (kể cả hũ hệ thống)."""

    offset: int | None
    jars: dict[str, dict[str, Any]]
    today: date
    now: datetime

    @property
    def exists(self) -> bool:
        return self.offset is not None

    def user_jars(self) -> list[dict[str, Any]]:
        return sorted(
            (j for j in self.jars.values() if j.get("kind") != "system"),
            key=lambda j: (j.get("sort_order") or 0, j["code"]),
        )


@dataclass
class Prepared:
    tool: str
    norm: dict[str, Any]
    summary: str
    changes: list[dict[str, str]]
    warnings: list[str] = field(default_factory=list)
    state: UserState | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class WalletWrites:
    """Mixin: ghi. Thuộc tính dùng: repo, confirm, settings, ref, events, now(), _app_date()."""

    events: events.EventPublisher | None

    # --- trạng thái và chuẩn hóa -----------------------------------------------------------------------------
    def _load_state(self, user_id: str) -> UserState:
        now = self.now()
        view = self.repo.jar_view(user_id)
        return UserState(
            offset=view.clock_offset_days,
            jars={j["code"]: j for j in view.jars},
            today=self._app_date(view.clock_offset_days, now),
            now=now,
        )

    def _norm_ctx(self, st: UserState) -> NormContext:
        user_jars = st.user_jars()
        return NormContext(
            today=st.today,
            tx_types=self.ref.tx_types(),
            jar_codes=frozenset(st.jars),
            obligation_jar=resolve_obligation_pay_jar((j["code"], j["kind"]) for j in user_jars),
        )

    def _normalize(
        self, user_id: str, tool: str, params: Mapping[str, Any]
    ) -> tuple[dict[str, Any], UserState]:
        st = self._load_state(user_id)
        try:
            ctx = self._norm_ctx(st)
            version = params.get("base_version") if tool == SAVE_JARS else None
            if version is not None:
                if not isinstance(version, str) or not split_proposal.JAR_LIST_VERSION_RE.fullmatch(
                    version
                ):
                    raise ParamsError("base_version không hợp lệ")
                jars = params.get("jars")
                if isinstance(jars, Sequence) and all(
                    isinstance(jar, Mapping) and jar.get("code") for jar in jars
                ):
                    # Mọi mã hũ trong thẻ đã chuẩn hóa. Giữ nguyên cách kiểm hash khi hũ đã bị xóa.
                    ctx = None
            norm = normalize_params(tool, params, ctx)
            if version is not None:
                norm["base_version"] = version
            if tool == RECORD_TRANSACTION and "obligation_id" in norm and not params.get("jar"):
                ob = self._find_obligation(user_id, norm["obligation_id"])
                pay = resolve_obligation_pay_jar(
                    ((j["code"], j["kind"]) for j in st.user_jars()), saved=ob.get("pay_jar_code")
                )
                if pay is None:
                    raise ParamsError("Chọn hũ để trả khoản nghĩa vụ này.")
                norm["jar"] = pay
        except ParamsError as exc:
            raise YofinaError(ErrorCode.PARAMS_INVALID, str(exc)) from exc
        return norm, st

    # --- kiểm nghiệp vụ và xem trước ---------------------------------------------------------------------------
    def _validate(
        self, user_id: str, tool: str, norm: dict[str, Any], st: UserState, *, name_hint: str | None
    ) -> Prepared:
        if tool == RECORD_TRANSACTION:
            return self._prep_record(user_id, norm, st)
        if tool == ASSIGN_JAR:
            return self._prep_assign(user_id, norm, st)
        if tool == UPDATE_PROFILE:
            return self._prep_profile(user_id, norm, st, name_hint)
        if tool == SAVE_JARS:
            return self._prep_save_jars(user_id, norm, st)
        if tool == CONFIRM_SALARY:
            return self._prep_salary(user_id, norm, st)
        if tool == SCHEDULE_NUDGE:
            return self._prep_nudge(user_id, norm, st)
        raise YofinaError(ErrorCode.PARAMS_INVALID, "Tool không hỗ trợ xác nhận.")

    def _jar_name(self, st: UserState, code: str) -> str:
        j = st.jars.get(code)
        return j["name"] if j else code

    def _check_amount_limit(self, amount: int) -> None:
        cap = self.settings.transaction_max_amount_vnd
        if cap and amount > cap:
            raise YofinaError(
                ErrorCode.AMOUNT_LIMIT_EXCEEDED, "Số tiền vượt hạn mức cho một giao dịch."
            )

    def _prep_record(self, user_id: str, norm: dict[str, Any], st: UserState) -> Prepared:
        kind, amount = norm["kind"], norm["amount_vnd"]
        self._check_amount_limit(amount)
        if not st.exists:
            raise YofinaError(
                ErrorCode.PROFILE_INCOMPLETE, "Bạn chưa khai lương và ngày nhận lương."
            )
        jar = st.jars.get(norm["jar"])
        if jar is None:
            code = ErrorCode.PROFILE_INCOMPLETE if kind == "income" else ErrorCode.JAR_NOT_FOUND
            raise YofinaError(code, "Không tìm thấy hũ bạn chọn.")
        tx_types = self.ref.tx_types()
        type_label = (
            tx_types[norm["tx_type"]].label if norm["tx_type"] in tx_types else norm["tx_type"]
        )
        extra: dict[str, Any] = {"tx_type_label": type_label}
        warnings: list[str] = []
        changes: list[dict[str, str]] = []
        payee = None
        if "payee_id" in norm:
            payee = next(
                (p for p in self.repo.list_payees(user_id) if str(p["id"]) == norm["payee_id"]),
                None,
            )
            if payee is None:
                raise YofinaError(ErrorCode.PAYEE_NOT_FOUND, "Không tìm thấy người nhận này.")
            extra["payee_name"] = payee["name"]
        who = norm.get("counterparty") or (payee["name"] if payee else None)
        balance = convert.vnd(jar["balance_vnd"])

        if kind == "income":
            is_salary = norm["tx_type"] == TX_TYPE_SALARY
            changes.append(
                _change(f"Hũ {jar['name']}", format_vnd(balance + amount), format_vnd(balance))
            )
            changes.append(_change("Loại", type_label))
            if who:
                changes.append(_change("Người gửi", who))
            summary = f"Nhận {format_vnd(amount)} vào hũ {jar['name']}" + (
                " (lương)" if is_salary else ""
            )
            if is_salary:
                info = self._salary_info(user_id, amount, st)
                extra["salary"] = info
                if info["expected_vnd"]:
                    dev = info["deviation_percent"]
                    changes.append(
                        _change(
                            "So với lương đã khai",
                            f"{dev:+.2f}%".replace(".00%", "%").replace(".", ","),
                        )
                    )
                if info["ask_update_salary"]:
                    warnings.append(
                        "Số nhận lệch nhiều so với lương đã khai; bạn sẽ được hỏi có cập nhật lương không."
                    )
            else:
                warnings.append("Tiền này nằm ở Tiền vào khác và không được tính là thu nhập.")
            return Prepared(RECORD_TRANSACTION, norm, summary, changes, warnings, st, extra)

        if norm["funding"] == "credit":
            return self._prep_credit(user_id, norm, st, jar, who, extra, changes, warnings)

        if jar.get("system_role") != "unclassified" and balance < amount:
            raise YofinaError(ErrorCode.INSUFFICIENT_FUNDS, f"Hũ {jar['name']} không đủ số dư.")
        after = balance - amount
        if jar.get("system_role") == "unclassified":
            changes.append(
                _change("Đã chi, chưa xếp hũ", format_vnd(abs(after)), format_vnd(abs(balance)))
            )
            warnings.append("Khoản chi sẽ nằm ở Chưa phân loại cho tới khi bạn xếp vào một hũ.")
        else:
            changes.append(_change(f"Hũ {jar['name']}", format_vnd(after), format_vnd(balance)))
        if "obligation_id" in norm:
            ob = self._find_obligation(user_id, norm["obligation_id"])
            extra["obligation"] = ob
            expected = convert.vnd(ob["amount_vnd"])
            nxt = advance_due(ob["due_date"], ob["cycle"], ob.get("due_day"))
            changes.append(
                _change(
                    f"Khoản {ob['name']}",
                    f"hạn kế tiếp {_dm(nxt)}" if nxt else "hoàn tất",
                    f"đến hạn {_dm(ob['due_date'])}",
                )
            )
            if amount != expected and ob["kind"] == "bnpl":
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID, f"Trả sau cần thanh toán đủ {format_vnd(expected)}."
                )
            if amount != expected:
                warnings.append(f"Số tiền khác số phải trả dự kiến ({format_vnd(expected)}).")
            summary = f"Trả {ob['name']} {format_vnd(amount)} từ hũ {jar['name']}"
        elif who:
            changes.append(_change("Người nhận" if payee else "Đối tác", who))
            summary = f"Chi {format_vnd(amount)} cho {who} từ hũ {jar['name']}"
        else:
            summary = f"Chi {format_vnd(amount)} từ hũ {jar['name']}"
        changes.append(_change("Loại", type_label))
        if norm.get("note"):
            changes.append(_change("Lời nhắn", norm["note"]))
        return Prepared(RECORD_TRANSACTION, norm, summary, changes, warnings, st, extra)

    def _find_obligation(self, user_id: str, obligation_id: str) -> dict[str, Any]:
        rows = self.repo.list_obligations(user_id, status="all", limit=100)
        ob = next((o for o in rows if str(o["id"]) == obligation_id), None)
        if ob is None:
            raise YofinaError(ErrorCode.OBLIGATION_NOT_FOUND, "Không tìm thấy khoản nghĩa vụ.")
        if ob["status"] != "active":
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Khoản nghĩa vụ này không còn hoạt động.")
        return ob

    def _salary_info(self, user_id: str, amount: int, st: UserState) -> dict[str, Any]:
        """Số nhận so với lương đã khai: `deviation_percent = round((nhận - khai) / khai * 100, 2)`; hỏi cập nhật lương khi
        lệch tuyệt đối vượt ngưỡng cấu hình `salary_deviation_ask_percent`; kỳ lương là ngày lương gần nhất với ngày nhận."""
        row = self.repo.user_row(user_id)
        expected = (
            convert.vnd(row["monthly_salary_vnd"])
            if row and row["monthly_salary_vnd"] is not None
            else None
        )
        payday = int(row["payday_day"]) if row and row["payday_day"] is not None else None
        deviation = Decimal(0)
        if expected:
            deviation = ((Decimal(amount) - expected) / expected * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        period = st.today
        if payday:
            before, after = latest_payday(payday, st.today), next_payday(payday, st.today)
            period = before if (st.today - before) <= (after - st.today) else after
        return {
            "expected_vnd": expected,
            "deviation_percent": deviation,
            "ask_update_salary": abs(deviation) > self.settings.salary_deviation_ask_percent,
            "period_date": period,
        }

    def _prep_credit(
        self,
        user_id: str,
        norm: dict[str, Any],
        st: UserState,
        jar: dict[str, Any],
        who: str | None,
        extra: dict[str, Any],
        changes: list[dict[str, str]],
        warnings: list[str],
    ) -> Prepared:
        amount = norm["amount_vnd"]
        line = self.repo.credit_line(user_id)
        if line is None or line["status"] != "active":
            raise YofinaError(
                ErrorCode.CREDIT_LIMIT_EXCEEDED,
                "Bạn chưa có hạn mức Trả sau (mô phỏng) đang hoạt động.",
            )
        limit, outstanding = convert.vnd(line["limit_vnd"]), convert.vnd(line["outstanding_vnd"])
        label = self.ref.product_label(line["product_code"], st.today)
        if outstanding + amount > limit:
            raise YofinaError(
                ErrorCode.CREDIT_LIMIT_EXCEEDED,
                f"Vượt hạn mức {label}: còn {format_vnd(limit - outstanding)}.",
            )
        due = bnpl_due_date(int(line["due_day"]), st.today)
        fee_row = self.ref.bnpl_monthly_fee(st.today)
        fee = fee_row.amount_vnd or 0 if fee_row else 0
        existing = next(
            (
                o
                for o in self.repo.list_obligations(user_id, status="active", limit=100)
                if o["kind"] == "bnpl" and o["due_date"] == due
            ),
            None,
        )
        pay_jar = resolve_obligation_pay_jar(
            ((j["code"], j["kind"]) for j in st.user_jars()),
            saved=existing.get("pay_jar_code") if existing else None,
            selected=norm.get("pay_jar"),
        )
        if pay_jar is None:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Chọn hũ để trả khoản Trả sau này.", field=PAY_JAR_FIELD)
        before_total = convert.vnd(existing["amount_vnd"]) if existing else 0
        after_total = before_total + amount + (0 if existing else fee)
        extra.update(
            credit_line=line,
            credit_label=label,
            due_date=due,
            fee=fee,
            fee_row=fee_row,
            existing_bnpl=existing,
            pay_jar=pay_jar,
            after_total=after_total,
        )
        changes.append(_change("Nguồn trả", label))
        changes.append(
            _change(
                f"Phải trả ngày {_dm(due)}",
                format_vnd(after_total),
                format_vnd(before_total) if existing else "chưa có",
            )
        )
        changes.append(
            _change(
                "Hạn mức còn lại",
                format_vnd(limit - outstanding - amount),
                format_vnd(limit - outstanding),
            )
        )
        changes.append(_change("Hũ trả khi đến hạn", self._jar_name(st, pay_jar)))
        changes.append(_change("Tính chi tiêu vào hũ", jar["name"]))
        if who:
            changes.append(_change("Đối tác", who))
        if not existing and fee:
            warnings.append(
                f"Phí dịch vụ {format_vnd(fee)} tính một lần cho tháng có giao dịch (theo biểu phí đã công bố)."
            )
        summary = f"Mua {format_vnd(amount)} bằng {label}, trả ngày {_dm(due)}"
        return Prepared(RECORD_TRANSACTION, norm, summary, changes, warnings, st, extra)

    def _prep_nudge(self, user_id: str, norm: dict[str, Any], st: UserState) -> Prepared:
        """Lời nhắc (phase 3): đặt hoặc hủy. Chỉ LƯU và hủy; việc gửi nhắc theo ngày là phase 4 và 5."""
        if norm["op"] == "cancel":
            row = self.repo.get_nudge(user_id, norm["nudge_id"])
            if row is None:
                raise YofinaError(ErrorCode.NUDGE_NOT_FOUND, "Không còn lời nhắc nào để hủy.")
            label = NUDGE_KIND_LABELS.get(row["kind"], row["kind"])
            changes = [
                _change(
                    "Lời nhắc", "đã hủy", f"{label} ngày {_dm(convert.to_date(row['fire_on']))}"
                )
            ]
            return Prepared(
                SCHEDULE_NUDGE, norm, "Hủy lời nhắc đã đặt", changes, [], st, {"nudge": row}
            )
        if norm["fire_on"] <= st.today.isoformat():
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Ngày nhắc phải sau hôm nay.")
        fire = date.fromisoformat(norm["fire_on"])
        jar_code = norm.get("jar_code")
        if jar_code is not None and (
            jar_code not in st.jars or st.jars[jar_code].get("kind") == "system"
        ):
            raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ bạn chọn.")
        changes = [
            _change("Ngày nhắc", _dm(fire)),
            _change("Loại", NUDGE_KIND_LABELS.get(norm["kind"], norm["kind"])),
        ]
        if jar_code:
            changes.append(_change("Hũ", self._jar_name(st, jar_code)))
        if norm.get("note"):
            changes.append(_change("Ghi chú", norm["note"]))
        summary = _clip(
            f"Nhắc bạn ngày {_dm(fire)}" + (f": {norm['note']}" if norm.get("note") else ""), 120
        )
        return Prepared(SCHEDULE_NUDGE, norm, summary, changes, [], st, {})

    def _prep_salary(self, user_id: str, norm: dict[str, Any], st: UserState) -> Prepared:
        row = next(
            (
                e
                for e in self.repo.salary_events(user_id, "all")
                if str(e["id"]) == norm["salary_event_id"]
            ),
            None,
        )
        if row is None:
            raise YofinaError(ErrorCode.SALARY_EVENT_NOT_FOUND, "Không tìm thấy lương này.")
        if row["status"] != "pending":
            raise YofinaError(ErrorCode.ALREADY_APPLIED, "Khoản lương này đã được xử lý rồi.")
        amount = convert.vnd(row["amount_vnd"])
        warnings: list[str] = []
        changes: list[dict[str, str]] = []
        if norm["decision"] == "keep_as_other":
            summary = f"Giữ {format_vnd(amount)} ở Tiền vào khác"
            changes.append(_change("Tiền vào khác", f"giữ {format_vnd(amount)}"))
            warnings.append("Tiền này không được chia vào hũ và không tính là thu nhập.")
            return Prepared(CONFIRM_SALARY, norm, summary, changes, warnings, st, {"event": row})
        parts = self._salary_parts(st.user_jars(), amount)
        for code, part in parts.items():
            if part > 0:
                j = st.jars[code]
                bal = convert.vnd(j["balance_vnd"])
                changes.append(_change(f"Hũ {j['name']}", format_vnd(bal + part), format_vnd(bal)))
        other = st.jars.get(OTHER_INCOME_JAR_CODE)
        if other is None or convert.vnd(other["balance_vnd"]) < amount:
            raise YofinaError(
                ErrorCode.INSUFFICIENT_FUNDS, "Hũ Tiền vào khác không còn đủ số tiền lương để chia."
            )
        if norm.get("update_declared_salary"):
            changes.append(_change("Lương đã khai", format_vnd(amount)))
        elif row["ask_update_salary"]:
            warnings.append(
                f"Số nhận lệch {convert.percent(row['deviation_percent'])}% so với lương đã khai; "
                "bạn có thể chọn cập nhật lương."
            )
        summary = (
            f"Chia {format_vnd(amount)} lương vào {sum(1 for p in parts.values() if p > 0)} hũ"
        )
        return Prepared(
            CONFIRM_SALARY,
            norm,
            summary,
            changes[:20],
            warnings,
            st,
            {"event": row, "parts": parts},
        )

    @staticmethod
    def _salary_parts(user_jars: Sequence[Mapping[str, Any]], amount: int) -> dict[str, int]:
        """Phần lương của từng hũ người dùng theo `split_percent` bằng `split_amount` (cùng quy tắc với dự báo)."""
        if not user_jars:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Bạn chưa có hũ nào để chia lương.")
        try:
            return split_amount(amount, [(j["code"], j["split_percent"]) for j in user_jars])
        except ValueError as exc:
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, "Tổng tỷ lệ chia lương của các hũ chưa bằng 100."
            ) from exc

    def _prep_assign(self, user_id: str, norm: dict[str, Any], st: UserState) -> Prepared:
        tx = self.repo.transaction_by_id(user_id, norm["transaction_id"])
        if tx is None:
            raise YofinaError(ErrorCode.TRANSACTION_NOT_FOUND, "Không tìm thấy giao dịch.")
        if tx["kind"] == "transfer":
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Dòng chuyển hũ không gán lại được.")
        if tx["kind"] == "income" and tx["tx_type"] == TX_TYPE_SALARY:
            raise YofinaError(
                ErrorCode.PARAMS_INVALID,
                "Tiền lương được chia bằng bước xác nhận lương, không gán vào một hũ.",
            )
        dst = st.jars.get(norm["jar"])
        if dst is None:
            raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ bạn chọn.")
        if dst["kind"] == "system":
            raise YofinaError(ErrorCode.JAR_PROTECTED, "Không gán vào hũ hệ thống.")
        source = st.jars.get(tx["jar_code"]) if tx["jar_code"] else None
        # "Đúng rồi" với mục "Xem lại": gán CHÍNH hũ hiện tại (xóa cờ cần xem lại, không chuyển tiền). Gán cùng hũ một dòng
        # không chờ xem lại vẫn là không làm gì nên vẫn bị từ chối.
        confirm_same = classify_write.is_confirm_same_jar(tx, norm)
        if tx["jar_code"] == norm["jar"] and not confirm_same:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Giao dịch đã nằm ở hũ này rồi.")
        signed = convert.vnd(tx["amount_vnd"])
        moves = tx["funding_source"] == "jar" and not confirm_same
        who = tx.get("payee_name") or tx.get("merchant") or "Giao dịch"
        changes = [_change("Giao dịch", f"{who}, {format_vnd(signed)}")]
        if confirm_same:
            changes.append(_change("Xác nhận", f"Đúng, giữ ở hũ {dst['name']}"))
        elif source is not None:
            changes.append(_change("Hũ", dst["name"], source["name"]))
        if moves:
            dst_bal = convert.vnd(dst["balance_vnd"])
            if dst_bal + signed < 0:
                raise YofinaError(ErrorCode.INSUFFICIENT_FUNDS, f"Hũ {dst['name']} không đủ số dư.")
            if source is not None:
                src_bal = convert.vnd(source["balance_vnd"])
                if src_bal - signed < 0 and source.get("system_role") != "unclassified":
                    raise YofinaError(
                        ErrorCode.INSUFFICIENT_FUNDS, f"Hũ {source['name']} không đủ số dư."
                    )
                changes.append(
                    _change(
                        f"Hũ {source['name']}", format_vnd(src_bal - signed), format_vnd(src_bal)
                    )
                )
            changes.append(
                _change(f"Hũ {dst['name']}", format_vnd(dst_bal + signed), format_vnd(dst_bal))
            )
        warnings = []
        if norm["remember"] == "always":
            if not (tx["payee_id"] or tx["merchant"]):
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID,
                    "Giao dịch này không có người nhận hay đối tác để nhớ thành luật.",
                )
            changes.append(_change("Nhớ cho lần sau", f"luôn xếp {who} vào hũ {dst['name']}"))
        if confirm_same:
            summary = f"Xác nhận {who} ({format_vnd(abs(signed))}) ở hũ {dst['name']}"
        else:
            summary = f"Xếp {who} ({format_vnd(abs(signed))}) vào hũ {dst['name']}"
        return Prepared(ASSIGN_JAR, norm, summary, changes, warnings, st, {"tx": tx})

    def _prep_profile(
        self, user_id: str, norm: dict[str, Any], st: UserState, name_hint: str | None
    ) -> Prepared:
        row = self.repo.user_row(user_id) if st.exists else None
        changes: list[dict[str, str]] = []
        warnings: list[str] = []
        extra: dict[str, Any] = {"existing": row, "name_hint": name_hint}
        if row is None and (
            norm.get("monthly_salary_vnd") is None or norm.get("payday_day") is None
        ):
            raise YofinaError(
                ErrorCode.PROFILE_INCOMPLETE,
                "Cần khai cả lương mỗi tháng và ngày nhận lương để bắt đầu.",
            )
        if "monthly_salary_vnd" in norm:
            before = (
                format_vnd(convert.vnd(row["monthly_salary_vnd"]))
                if row and row["monthly_salary_vnd"] is not None
                else None
            )
            changes.append(
                _change("Lương mỗi tháng", format_vnd(norm["monthly_salary_vnd"]), before)
            )
        if "payday_day" in norm:
            before = f"ngày {row['payday_day']}" if row and row["payday_day"] is not None else None
            changes.append(_change("Ngày nhận lương", f"ngày {norm['payday_day']}", before))
        if "risk_tolerance" in norm:
            labels = {"low": "thấp", "medium": "vừa", "high": "cao"}
            before = labels.get(row["risk_tolerance"]) if row and row["risk_tolerance"] else None
            changes.append(_change("Mức chấp nhận rủi ro", labels[norm["risk_tolerance"]], before))
        if "display_name" in norm:
            changes.append(
                _change("Tên hiển thị", norm["display_name"], row["display_name"] if row else None)
            )
        if row is None:
            summary = (
                "Tạo hồ sơ: lương "
                + format_vnd(norm["monthly_salary_vnd"])
                + f", nhận ngày {norm['payday_day']}"
            )
            templates = [t for t in self.ref.templates() if t.is_default]
            if templates:
                changes.append(_change("Hũ mặc định", f"{len(templates)} hũ, bạn sửa được sau"))
            warnings.append(
                "Hệ thống tạo sẵn các hũ mặc định và hai hũ Tiền vào khác, Chưa phân loại."
            )
        else:
            parts = [c["label"].lower() for c in changes]
            summary = "Cập nhật " + ", ".join(parts) if parts else "Cập nhật hồ sơ"
        if "obligation" in norm:
            had_other = bool(changes)
            ob_summary, ob_values = self._prep_obligation(
                user_id, norm["obligation"], st, changes, extra, row is None
            )
            extra["obligation_values"] = ob_values
            summary = (
                f"{summary}; {ob_summary[0].lower()}{ob_summary[1:]}" if had_other else ob_summary
            )
        return Prepared(UPDATE_PROFILE, norm, summary, changes[:20], warnings, st, extra)

    def _prep_obligation(
        self,
        user_id: str,
        ob: dict[str, Any],
        st: UserState,
        changes: list[dict[str, str]],
        extra: dict[str, Any],
        onboarding: bool,
    ) -> tuple[str, dict[str, Any]]:
        pay = ob.get("pay_jar")
        if pay is not None:
            j = st.jars.get(pay)
            if j is None and not onboarding:
                raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ trả cho khoản này.")
            if j is not None and j["kind"] == "system":
                raise YofinaError(
                    ErrorCode.JAR_PROTECTED, "Không dùng hũ hệ thống để trả nghĩa vụ."
                )
        if ob["op"] == "delete":
            cur = self._find_obligation(user_id, ob["obligation_id"])
            if cur["kind"] == "bnpl":
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID, "Khoản Trả sau tự sinh khi mua, không xóa được."
                )
            changes.append(
                _change(
                    f"Hủy khoản {cur['name']}",
                    "không còn trong lịch",
                    format_vnd(convert.vnd(cur["amount_vnd"])),
                )
            )
            extra["obligation_current"] = cur
            return f"Hủy khoản {cur['name']}", {
                "op": "delete",
                "obligation_id": ob["obligation_id"],
            }
        if "obligation_id" in ob:
            cur = self._find_obligation(user_id, ob["obligation_id"])
            if cur["kind"] == "bnpl":
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID, "Khoản Trả sau tự sinh khi mua, không sửa được."
                )
            extra["obligation_current"] = cur
            if pay is None:
                pay = resolve_obligation_pay_jar(
                    ((j["code"], j["kind"]) for j in st.user_jars()),
                    saved=cur.get("pay_jar_code"),
                )
            if pay is None:
                raise YofinaError(ErrorCode.PARAMS_INVALID, "Chọn hũ để trả khoản nghĩa vụ này.", field=PAY_JAR_FIELD)
            values = {**ob, "op": "update", "pay_jar": pay}
            if "amount_vnd" in ob:
                changes.append(
                    _change(
                        f"Khoản {cur['name']}",
                        format_vnd(ob["amount_vnd"]),
                        format_vnd(convert.vnd(cur["amount_vnd"])),
                    )
                )
            if "due_date" in ob:
                changes.append(
                    _change(
                        "Ngày đến hạn",
                        _dm(date.fromisoformat(ob["due_date"])),
                        _dm(cur["due_date"]),
                    )
                )
            if "name" in ob:
                changes.append(_change("Tên khoản", ob["name"], cur["name"]))
            return f"Sửa khoản {ob.get('name') or cur['name']}", values
        available = (
            ((t.code, t.kind) for t in self.ref.templates() if t.is_default)
            if onboarding else ((j["code"], j["kind"]) for j in st.user_jars())
        )
        pay = resolve_obligation_pay_jar(available, selected=pay)
        if pay is None:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Chọn hũ để trả khoản nghĩa vụ này.", field=PAY_JAR_FIELD)
        values = {**ob, "op": "create", "pay_jar": pay}
        if "due_date" not in values:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Khoản nghĩa vụ mới cần ngày đến hạn.")
        amount_text = format_vnd(ob["amount_vnd"])
        if "amount_min_vnd" in ob:
            amount_text = (
                f"{format_vnd(ob['amount_min_vnd'])} đến {format_vnd(ob['amount_max_vnd'])}"
            )
        cycle = {
            "once": "một lần",
            "weekly": "mỗi tuần",
            "monthly": "mỗi tháng",
            "yearly": "mỗi năm",
        }[ob["cycle"]]
        pay_name = self._jar_name(st, pay) if pay else None
        changes.append(
            _change(
                f"Khoản mới: {ob['name']}",
                f"{amount_text} {cycle}, đến hạn {_dm(date.fromisoformat(ob['due_date']))}"
                + (f", trả từ hũ {pay_name}" if pay_name else ""),
            )
        )
        return f"Khai {ob['name']} {amount_text}", values

    def _prep_save_jars(self, user_id: str, norm: dict[str, Any], st: UserState) -> Prepared:
        """Bản xem trước của `save_jars` (BR-47, BR-48): mỗi hũ đổi tỷ lệ có tỷ lệ và tiền mỗi kỳ lương trước và sau cùng
        phần chênh (theo `split_amount` trên lương đã khai, cùng quy tắc `confirm_salary`), lý do bằng số đo khi tỷ lệ Nghĩa
        vụ hoặc khoản Quỹ dồn đổi, kỳ áp dụng và việc dự báo tính lại. Tỷ lệ mới chỉ áp từ lần chia lương đầu tiên sau khi
        lưu (BR-45); có lương đang chờ chia thì người dùng chọn chia lương đó trước (từ kỳ sau) hay sau khi lưu (kỳ này)."""
        if not st.exists:
            raise YofinaError(
                ErrorCode.PROFILE_INCOMPLETE, "Bạn chưa khai lương và ngày nhận lương."
            )
        current_jars = st.user_jars()
        split_proposal.check_jar_list_version(norm.get("base_version"), current_jars)
        existing = {j["code"]: j for j in current_jars}
        wanted = [j["code"] for j in norm["jars"]]
        usage = {u["code"]: u for u in self.repo.jars_usage(user_id)}
        structural_changes: list[dict[str, str]] = []
        changes: list[dict[str, str]] = []
        after_jars = []
        row = self.repo.user_row(user_id)
        salary = (
            convert.vnd(row["monthly_salary_vnd"])
            if row and row.get("monthly_salary_vnd") is not None
            else None
        )
        before_amt = split_proposal.jar_amounts(
            salary, [(c, j["split_percent"]) for c, j in existing.items()]
        )
        after_amt = split_proposal.jar_amounts(
            salary, [(j["code"], j["split_percent"]) for j in norm["jars"]]
        )
        amounts = before_amt is not None and after_amt is not None
        share_changed = False
        changed_codes: set[str] = set()
        for i, j in enumerate(norm["jars"]):
            cur = existing.get(j["code"])
            try:
                metadata = jar_commitments(j, cur or {})
            except ParamsError as exc:
                raise YofinaError(ErrorCode.PARAMS_INVALID, str(exc)) from exc
            after_jar = {**j, **metadata, "balance_vnd": cur["balance_vnd"] if cur else 0}
            after_jars.append(after_jar)
            goal_change = _jar_goal_change(cur or {}, after_jar)
            item_changes = _sinking_item_changes(
                j["name"], (cur or {}).get("sinking_items") or [], metadata["sinking_items"]
            )
            if goal_change:
                changes.append(goal_change)
            if item_changes:
                changes.extend(item_changes)
            if goal_change or item_changes or (cur and cur.get("purpose") != metadata["purpose"]):
                changed_codes.add(j["code"])
            pct = Decimal(str(j["split_percent"]))
            if cur is None:
                share_changed = share_changed or pct > 0
                changed_codes.add(j["code"])
                new_vnd = after_amt.get(j["code"]) if after_amt is not None else None
                _, after = split_proposal.share_line(None, pct, None, new_vnd)
                text = after if amounts else f"{convert.percent(pct)}% lương"
                structural_changes.append(_change(f"Hũ mới: {j['name']}", text))
                continue
            old = Decimal(str(cur["split_percent"]))
            if old != pct:
                share_changed = True
                changed_codes.add(j["code"])
                before, after = split_proposal.share_line(
                    old,
                    pct,
                    before_amt.get(j["code"]) if before_amt is not None and amounts else None,
                    after_amt.get(j["code"]) if after_amt is not None and amounts else None,
                )
                changes.append(_change(f"Hũ {j['name']}", after, before))
            changes.extend(_jar_setting_changes(cur, after_jar, i))
        for code, cur in existing.items():
            if code in wanted:
                continue
            u = usage.get(code)
            if convert.vnd(cur["balance_vnd"]) != 0 or (
                u and (int(u["active_obligations"]) or int(u["tx_count"]))
            ):
                reason = (
                    "còn tiền"
                    if convert.vnd(cur["balance_vnd"]) != 0
                    else "còn nghĩa vụ trả bằng hũ này"
                    if u and int(u["active_obligations"])
                    else "đã có lịch sử giao dịch"
                )
                raise YofinaError(
                    ErrorCode.JAR_PROTECTED, f"Hũ {cur['name']} {reason} nên chưa bỏ được."
                )
            share_changed = share_changed or Decimal(str(cur["split_percent"])) > 0
            structural_changes.append(_change(f"Bỏ hũ {cur['name']}", "không còn"))
        reasons = self._save_jars_reasons(user_id, after_jars, st, salary, changed_codes)
        if not structural_changes and not changes:
            changes.append(_change("Danh sách hũ", "không đổi"))
        warnings: list[str] = []
        extra: dict[str, Any] = {}
        if share_changed:
            pending = self.repo.salary_events(user_id, "pending")
            if pending:
                ev = pending[0]
                extra["pending_salary_event_id"] = str(ev["id"])
                warnings.append(
                    f"Lương {format_vnd(convert.vnd(ev['amount_vnd']))} đang chờ chia: "
                    "chọn áp tỷ lệ mới cho kỳ này hay từ kỳ sau."
                )
            warnings.append(
                "Tỷ lệ mới áp từ lần chia lương đầu tiên sau khi lưu. Dự báo tính lại ngay sau khi lưu."
            )
        return Prepared(
            SAVE_JARS,
            norm,
            f"Lưu {len(norm['jars'])} hũ và tỷ lệ chia lương",
            (structural_changes + changes + reasons)[:20],
            warnings,
            st,
            extra,
        )

    def _save_jars_reasons(
        self,
        user_id: str,
        after_jars: list[dict[str, Any]],
        st: UserState,
        salary: int | None,
        changed_codes: set[str],
    ) -> list[dict[str, str]]:
        """Lý do bằng số đo khi tỷ lệ hoặc cam kết đổi: nghĩa vụ quy về tháng so với lương và số cần trích mỗi kỳ cho Quỹ dồn."""
        if not salary or not changed_codes:
            return []
        row = self.repo.user_row(user_id)
        payday = int(row["payday_day"]) if row and row.get("payday_day") is not None else None
        out: list[dict[str, str]] = []
        ob_jar = resolve_obligation_pay_jar((j["code"], j["kind"]) for j in after_jars)
        if ob_jar is not None and ob_jar in changed_codes:
            obligations = self.repo.list_obligations(user_id, status="active", limit=100)
            declared, monthly = split_proposal.declared_need(obligations, after_jars, ob_jar)
            name = self._jar_name(st, ob_jar)
            text = (
                split_proposal.obligation_reason(monthly, salary)
                if declared
                else "chưa có số khai"
            )
            out.append(_change(f"Lý do: hũ {name}", text))
        for j in after_jars:
            code = j["code"]
            if code not in changed_codes or j.get("purpose") != "sinking":
                continue
            label = f"Lý do: hũ {j['name']}"
            if not j["sinking_items"]:
                if st.jars.get(code, {}).get("sinking_items"):
                    out.append(_change(label, "không còn khoản cần trích mỗi kỳ"))
                continue
            if payday is None:
                continue
            plan = split_proposal.sinking_plan(
                split_proposal.stored_items(j),
                today=st.today,
                payday_day=payday,
                saved_vnd=convert.vnd(j.get("balance_vnd") or 0),
            )
            out.append(_change(label, split_proposal.sinking_reason(plan, salary)))
        return out

    # --- xem trước (không ghi) ---------------------------------------------------------------------------------
    def _confirm_block(
        self, prep: Prepared, *, trace_id: str, source_tool: str
    ) -> ConfirmActionBlock:
        st = prep.state
        assert st is not None
        return build_confirm_action(
            tool=prep.tool,
            params=prep.norm,
            summary=prep.summary,
            changes=prep.changes or [_change("Thay đổi", "xem chi tiết")],
            warnings=prep.warnings[:5],
            trace_id=trace_id,
            source_tool=source_tool,
            as_of=st.now,
            app_date=st.today,
            expires_at=st.now + timedelta(seconds=self.settings.offer_ttl_seconds),
        )

    def prepare_action(
        self,
        user_id: str,
        tool: str,
        params: Mapping[str, Any],
        *,
        trace_id: str,
        source_tool: str,
        name_hint: str | None = None,
    ) -> tuple[Prepared, ConfirmActionBlock]:
        norm, st = self._normalize(user_id, tool, params)
        if tool == SAVE_JARS and "base_version" not in norm:
            norm["base_version"] = split_proposal.jar_list_version(st.user_jars())
        prep = self._validate(user_id, tool, norm, st, name_hint=name_hint)
        return prep, self._confirm_block(prep, trace_id=trace_id, source_tool=source_tool)

    # --- ghi -----------------------------------------------------------------------------------------------------
    def _publish(self, user_id: str, trace_id: str, evs: list[events.Event]) -> None:
        """Phát sau commit; thất bại không làm hỏng thao tác đã ghi (log + metric trong publisher, audit `error` ở đây)."""
        if not evs or self.events is None:
            return
        try:
            ok = self.events.publish(evs, trace_id=trace_id)
        except Exception:  # publisher không được ném, nhưng đây là lưới cuối
            log.exception("publish_unexpected trace_id=%s", trace_id)
            ok = False
        if ok:
            return
        try:
            self.repo.audit(
                user_id,
                trace_id=trace_id,
                event_type="event_publish",
                tool=None,
                outcome="error",
                code="EVENT_PUBLISH_FAILED",
                params=None,
                details={"detail_types": [e.detail_type for e in evs]},
            )
        except Exception:
            log.warning("không ghi được audit lỗi phát sự kiện", exc_info=True)

    def _audit(
        self, prep: Prepared, trace_id: str, channel: str, jti: str | None
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "event_type": prep.tool,
            "params": prep.norm,
            "details": {"channel": channel, "jti": jti},
        }

    def apply_generic(
        self,
        user_id: str,
        prep: Prepared,
        jti: str | None,
        *,
        trace_id: str,
        channel: str,
        source_tool: str,
        claim_ref: tuple[str, str] | None,
    ) -> ReceiptActionBlock:
        """Ghi một thao tác (không phải chuyển hũ) rồi dựng biên nhận và phát sự kiện. Token đã được kiểm và tiêu."""
        st = prep.state
        assert st is not None
        now = self.now()
        app_date = self._app_date(st.offset, now)
        audit = self._audit(prep, trace_id, channel, jti)

        def receipt_of(res: WriteResult) -> ReceiptActionBlock:
            return self._receipt(prep, res, trace_id=trace_id, source_tool=source_tool)

        claim = (
            ClaimSpec(claim_ref[0], claim_ref[1], lambda res: _wire(receipt_of(res)))
            if claim_ref
            else None
        )
        tool, norm = prep.tool, prep.norm
        if tool == RECORD_TRANSACTION:
            result = self._write_record(user_id, prep, now, app_date, audit, claim)
        elif tool == ASSIGN_JAR:
            tx_before = prep.extra.get("tx") or {}
            before = classify_write.assign_context(self.repo.db, user_id, norm["transaction_id"])
            if classify_write.is_confirm_same_jar(tx_before, norm):
                result = classify_write.write_confirm_same_jar(
                    self.repo,
                    user_id,
                    norm=norm,
                    now=now,
                    app_date=app_date,
                    audit=audit,
                    claim=claim,
                    tool=tool,
                )
            else:
                result = self.repo.write_assign_jar(
                    user_id,
                    norm=norm,
                    now=now,
                    app_date=app_date,
                    audit=audit,
                    claim=claim,
                    tool=tool,
                )
            # nhãn k-NN, đếm lần sửa, ngưỡng riêng của người nhận, đóng câu hỏi gộp (không bao giờ làm hỏng thao tác đã commit)
            classify_write.record_assignment_feedback(
                self.repo.db,
                user_id,
                transaction_id=norm["transaction_id"],
                target_jar=norm["jar"],
                before=before,
                thresholds=classify_thresholds(),
            )
        elif tool == CONFIRM_SALARY:
            result = self.repo.write_confirm_salary(
                user_id,
                norm=norm,
                now=now,
                app_date=app_date,
                shares_for=lambda jars, amount: self._salary_parts(jars, amount),
                audit=audit,
                claim=claim,
                tool=tool,
            )
        elif tool == SAVE_JARS:
            result = self.repo.write_save_jars(
                user_id, norm=norm, now=now, app_date=app_date, audit=audit, claim=claim, tool=tool
            )
        elif tool == UPDATE_PROFILE:
            result = self._write_profile(user_id, prep, now, app_date, audit, claim)
        elif tool == SCHEDULE_NUDGE:
            result = self.repo.write_nudge(
                user_id,
                norm=norm,
                now=now,
                app_date=app_date,
                trace_id=trace_id,
                audit=audit,
                claim=claim,
                tool=tool,
            )
        else:  # pragma: no cover - ACTION_TOOLS đã được kiểm ở service
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Tool không hỗ trợ xác nhận.")
        self._publish(user_id, trace_id, self._events_of(user_id, prep, result, trace_id))
        return receipt_of(result)

    def _write_profile(
        self,
        user_id: str,
        prep: Prepared,
        now: datetime,
        app_date: date,
        audit: dict[str, Any],
        claim: ClaimSpec | None,
    ) -> WriteResult:
        return self.repo.write_update_profile(
            user_id,
            norm=prep.norm,
            display_name_default=prep.extra.get("name_hint") or self.settings.default_display_name,
            credit_limit_default=self.settings.default_credit_limit_vnd,
            credit_product_code=BNPL_PRODUCT_CODE,
            obligation_values=prep.extra.get("obligation_values"),
            now=now,
            app_date=app_date,
            audit=audit,
            claim=claim,
            tool=UPDATE_PROFILE,
        )

    def _write_record(
        self,
        user_id: str,
        prep: Prepared,
        now: datetime,
        app_date: date,
        audit: dict[str, Any],
        claim: ClaimSpec | None,
    ) -> WriteResult:
        norm, extra = prep.norm, prep.extra
        amount, kind = norm["amount_vnd"], norm["kind"]
        signed = amount if kind == "income" else -amount
        merchant = norm.get("counterparty") or extra.get("payee_name")
        jar = prep.state.jars[norm["jar"]] if prep.state else {}
        tx_type = norm["tx_type"]
        info = self.ref.tx_types().get(tx_type)
        unclassified = jar.get("system_role") == "unclassified"
        if unclassified:
            classified_by = None
        elif info is not None and transaction_jar(
            info.default_jar_code, prep.state.jars if prep.state else (), tx_type=tx_type
        ) == norm["jar"]:
            classified_by = "type_map"
        else:
            classified_by = "user"
        tx = {
            "tx_id": str(uuid.uuid4()),
            "occurred_at": now,
            "app_date": app_date,
            "kind": kind,
            "jar": norm["jar"],
            "signed": signed,
            "merchant": merchant,
            "note": norm.get("note"),
            "source": SOURCE_APP,
            "tx_type": tx_type,
            "funding": norm["funding"],
            "payee_id": norm.get("payee_id"),
            "obligation_id": norm.get("obligation_id"),
            "dedupe_key": (
                compute_dedupe_key(
                    app_date=app_date,
                    amount_vnd=amount,
                    payee_id=norm.get("payee_id"),
                    counterparty=norm.get("counterparty") or merchant,
                    client_ref=norm["client_ref"],
                )
                if "client_ref" in norm
                else None
            ),
            "classified_by": classified_by,
            "needs_review": unclassified and kind == "expense",
        }
        tool = RECORD_TRANSACTION
        if kind == "income":
            salary = None
            if tx_type == TX_TYPE_SALARY:
                info_s = extra["salary"]
                salary = {
                    "id": str(uuid.uuid4()),
                    "period_date": info_s["period_date"],
                    "expected_vnd": info_s["expected_vnd"],
                    "deviation_percent": info_s["deviation_percent"],
                    "ask_update_salary": info_s["ask_update_salary"],
                }
            return self.repo.write_jar_transaction(
                user_id, tx=tx, salary=salary, audit=audit, claim=claim, tool=tool
            )
        if norm["funding"] == "credit":
            fee_row = extra.get("fee_row")
            fee = {
                "amount_vnd": extra["fee"],
                "id": fee_row.id if fee_row else None,
                "name": extra["credit_label"],
            }
            def limit_check(line: Mapping[str, Any]) -> None:
                if not line or line.get("status") != "active":
                    raise YofinaError(
                        ErrorCode.CREDIT_LIMIT_EXCEEDED,
                        "Bạn chưa có hạn mức Trả sau (mô phỏng) đang hoạt động.",
                    )
                if convert.vnd(line["outstanding_vnd"]) + amount > convert.vnd(line["limit_vnd"]):
                    raise YofinaError(
                        ErrorCode.CREDIT_LIMIT_EXCEEDED, "Vượt hạn mức Trả sau (mô phỏng) còn lại."
                    )

            return self.repo.write_credit_purchase(
                user_id,
                tx=tx,
                fee=fee,
                pay_jar=extra["pay_jar"],
                audit=audit,
                claim=claim,
                tool=tool,
                due_date_for=lambda due_day: bnpl_due_date(due_day, app_date),
                limit_check=limit_check,
            )
        if "obligation_id" in norm:
            return self.repo.write_obligation_payment(
                user_id,
                tx=tx,
                audit=audit,
                claim=claim,
                tool=tool,
                next_due_for=lambda ob: advance_due(ob["due_date"], ob["cycle"], ob.get("due_day")),
            )
        return self.repo.write_jar_transaction(
            user_id, tx=tx, salary=None, audit=audit, claim=claim, tool=tool
        )

    # --- biên nhận ------------------------------------------------------------------------------------------------
    def _receipt(
        self, prep: Prepared, res: WriteResult, *, trace_id: str, source_tool: str
    ) -> ReceiptActionBlock:
        tool, norm, f = prep.tool, prep.norm, res.facts
        details: list[dict[str, str]] = []
        follow_up: dict[str, Any] | None = None
        amount: int | None = None
        jars_after = res.jars_after
        if tool == RECORD_TRANSACTION:
            amount = norm["amount_vnd"]
            jar_name = self._jar_name(prep.state, norm["jar"]) if prep.state else norm["jar"]
            label = prep.extra.get("tx_type_label", norm["tx_type"])
            who = norm.get("counterparty") or prep.extra.get("payee_name")
            details.append({"label": "Loại", "value": label})
            if who:
                details.append({"label": "Đối tác", "value": _clip(who, 120)})
            if norm["kind"] == "income":
                summary = f"Đã ghi tiền vào {format_vnd(amount)} vào {jar_name}"
                if f.get("salary_event_id"):
                    s = prep.extra["salary"]
                    follow_up = {
                        "kind": "confirm_salary",
                        "label": "Xác nhận chia lương vào các hũ",
                        "salary_event_id": f["salary_event_id"],
                        "received_vnd": amount,
                        "deviation_percent": float(s["deviation_percent"]),
                        "ask_update_salary": bool(s["ask_update_salary"]),
                    }
                    if s["expected_vnd"]:
                        follow_up["expected_vnd"] = s["expected_vnd"]
            elif norm["funding"] == "credit":
                label_credit = prep.extra.get("credit_label", "Trả sau (mô phỏng)")
                summary = f"Đã mua {format_vnd(amount)} bằng {label_credit}"
                due = f["due_date"]
                details.append(
                    {"label": f"Phải trả ngày {_dm(due)}", "value": format_vnd(f["amount_vnd"])}
                )
                if f.get("fee_vnd"):
                    details.append(
                        {"label": "Trong đó phí dịch vụ", "value": format_vnd(f["fee_vnd"])}
                    )
                details.append(
                    {
                        "label": "Hạn mức còn lại",
                        "value": format_vnd(f["limit_vnd"] - f["outstanding_vnd"]),
                    }
                )
            elif "obligation_id" in norm:
                summary = f"Đã trả {f.get('obligation_name', 'khoản nghĩa vụ')} {format_vnd(amount)} từ hũ {jar_name}"
                if f.get("obligation_status") == "paid":
                    details.append({"label": "Khoản này", "value": "đã hoàn tất"})
                elif f.get("obligation_due"):
                    details.append({"label": "Hạn kế tiếp", "value": _dm(f["obligation_due"])})
            else:
                summary = f"Đã chi {format_vnd(amount)} từ hũ {jar_name}"
                if prep.state and prep.state.jars[norm["jar"]].get("system_role") == "unclassified":
                    follow_up = {
                        "kind": "review_unclassified",
                        "label": "Xếp khoản chi này vào một hũ",
                    }
        elif tool == ASSIGN_JAR:
            amount = f["amount_vnd"]
            if f.get("confirmed_same_jar"):
                summary = f"Đã xác nhận giao dịch ở hũ {f['to_jar_name']}"
                details.append({"label": "Hũ", "value": f["to_jar_name"]})
            else:
                summary = f"Đã xếp giao dịch vào hũ {f['to_jar_name']}"
                details.append({"label": "Từ hũ", "value": f["from_jar_name"]})
                details.append({"label": "Sang hũ", "value": f["to_jar_name"]})
            if f.get("rule_saved"):
                details.append({"label": "Luật đã nhớ", "value": "luôn xếp vào hũ này"})
        elif tool == CONFIRM_SALARY:
            amount = f["amount_vnd"]
            if f["decision"] == "keep_as_other":
                summary = f"Đã giữ {format_vnd(amount)} ở Tiền vào khác"
            else:
                n = len(f["split"])
                summary = f"Đã chia {format_vnd(amount)} lương vào {n} hũ"
                names = {j["code"]: j["name"] for j in res.jars_after}
                for part in f["split"][:20]:
                    details.append(
                        {
                            "label": f"Hũ {names.get(part['jar'], part['jar'])}",
                            "value": f"+{format_vnd(part['amount_vnd'])}",
                        }
                    )
                if f.get("salary_updated"):
                    details.append({"label": "Lương đã khai", "value": format_vnd(amount)})
        elif tool == UPDATE_PROFILE:
            ob = f.get("obligation")
            if f.get("created"):
                summary = f"Đã tạo hồ sơ: lương {format_vnd(f['monthly_salary_vnd'])}, nhận ngày {f['payday_day']}"
            elif ob and len(prep.changes) == 1:
                verb = {"created": "Đã khai", "updated": "Đã sửa", "cancelled": "Đã hủy"}[ob["op"]]
                summary = f"{verb} khoản {ob['name']}"
            else:
                summary = "Đã cập nhật hồ sơ"
            details.extend({"label": c["label"], "value": c["after"]} for c in prep.changes)
        elif tool == SCHEDULE_NUDGE:
            fire = convert.to_date(f["fire_on"])
            label = NUDGE_KIND_LABELS.get(f["kind"], f["kind"])
            if f["op"] == "cancel":
                summary = "Đã hủy lời nhắc"
            else:
                summary = f"Đã đặt nhắc ngày {_dm(fire)}" if fire else "Đã đặt lời nhắc"
            details.append({"label": "Loại", "value": label})
            if fire:
                details.append({"label": "Ngày nhắc", "value": _dm(fire)})
            if f.get("note"):
                details.append({"label": "Ghi chú", "value": _clip(f["note"], 120)})
        else:  # SAVE_JARS
            summary = f"Đã lưu {f['count']} hũ và tỷ lệ chia lương"
            if f.get("removed"):
                details.append({"label": "Đã bỏ", "value": f"{len(f['removed'])} hũ"})
            jars_after = []
        return build_receipt_action(
            tool=tool,
            occurred_at=res.occurred_at,
            app_date=res.app_date,
            summary=summary,
            trace_id=trace_id,
            source_tool=source_tool,
            reference_id=res.reference_id,
            amount_vnd=amount,
            jars_after=jars_after,
            details=details[:20],
            follow_up=follow_up,
        )

    # --- sự kiện ---------------------------------------------------------------------------------------------------
    def _events_of(
        self, user_id: str, prep: Prepared, res: WriteResult, trace_id: str
    ) -> list[events.Event]:
        tool, norm, f = prep.tool, prep.norm, res.facts
        balances = {j["code"]: j["balance_vnd"] for j in res.jars_after}
        out: list[events.Event] = []
        if tool == RECORD_TRANSACTION:
            jar = norm["jar"]
            deltas = dict(res.deltas)
            ob_id = f.get("obligation_id") if norm["funding"] != "credit" else None
            out.append(
                events.transaction_recorded(
                    user_id=user_id,
                    trace_id=trace_id,
                    transaction_id=str(res.reference_id),
                    occurred_at=res.occurred_at,
                    app_date=res.app_date,
                    kind=norm["kind"],
                    tx_type=norm["tx_type"],
                    funding_source=norm["funding"],
                    amount_vnd=norm["amount_vnd"],
                    jar_codes=[jar],
                    deltas=deltas,
                    balances=balances,
                    payee_id=norm.get("payee_id"),
                    obligation_id=ob_id,
                    needs_classification=(
                        norm["kind"] == "expense" and jar == UNCLASSIFIED_JAR_CODE
                    ),
                )
            )
            if norm["funding"] == "credit":
                out.append(
                    events.obligation_changed(
                        user_id=user_id,
                        trace_id=trace_id,
                        obligation_id=f["obligation_id"],
                        occurred_at=res.occurred_at,
                        app_date=res.app_date,
                        change="created" if f.get("obligation_created") else "updated",
                        kind="bnpl",
                        pay_jar=f.get("pay_jar"),
                        due_date=f.get("due_date"),
                    )
                )
            elif "obligation_id" in norm:
                out.append(
                    events.obligation_changed(
                        user_id=user_id,
                        trace_id=trace_id,
                        obligation_id=norm["obligation_id"],
                        occurred_at=res.occurred_at,
                        app_date=res.app_date,
                        change="paid",
                        kind=f.get("obligation_kind", "bill"),
                        pay_jar=f.get("pay_jar"),
                        due_date=f.get("obligation_due"),
                    )
                )
        elif tool == ASSIGN_JAR:
            codes = [f["from_jar"], f["to_jar"]]
            out.append(
                events.transaction_recorded(
                    user_id=user_id,
                    trace_id=trace_id,
                    transaction_id=norm["transaction_id"],
                    event_id=str(uuid.uuid4()),
                    occurred_at=res.occurred_at,
                    app_date=res.app_date,
                    kind=f["kind"],
                    tx_type="jar_assign",
                    # nguồn trả thật của dòng (jar, credit, hoặc external của phase 5); bản cũ suy từ moves_money
                    funding_source=f.get("funding_source")
                    or ("jar" if f["moves_money"] else "credit"),
                    amount_vnd=f["amount_vnd"],
                    jar_codes=codes,
                    deltas=res.deltas,
                    balances=balances,
                )
            )
        elif tool == CONFIRM_SALARY:
            out.append(
                events.salary_confirmed(
                    user_id=user_id,
                    trace_id=trace_id,
                    salary_event_id=norm["salary_event_id"],
                    occurred_at=res.occurred_at,
                    app_date=res.app_date,
                    period_date=convert.to_date(f["period_date"]),  # type: ignore[arg-type]
                    decision=f["decision"],
                    amount_vnd=f["amount_vnd"],
                    salary_updated=bool(f.get("salary_updated")),
                    deltas=res.deltas,
                    balances=balances,
                )
            )
            if f["decision"] == "split" and res.deltas:
                out.append(
                    events.transaction_recorded(
                        user_id=user_id,
                        trace_id=trace_id,
                        transaction_id=str(res.reference_id),
                        occurred_at=res.occurred_at,
                        app_date=res.app_date,
                        kind="transfer",
                        tx_type="salary_split",
                        funding_source="jar",
                        amount_vnd=f["amount_vnd"],
                        jar_codes=list(res.deltas),
                        deltas=res.deltas,
                        balances=balances,
                    )
                )
        elif tool == UPDATE_PROFILE:
            fields = []
            if f.get("created"):
                fields.append("onboarding")
            if "monthly_salary_vnd" in norm:
                fields.append("salary")
            if "payday_day" in norm:
                fields.append("payday")
            if "risk_tolerance" in norm:
                fields.append("risk")
            if "display_name" in norm:
                fields.append("display_name")
            if fields:
                out.append(
                    events.profile_updated(
                        user_id=user_id,
                        trace_id=trace_id,
                        occurred_at=res.occurred_at,
                        app_date=res.app_date,
                        fields=fields,
                    )
                )
            ob = f.get("obligation")
            if ob:
                out.append(
                    events.obligation_changed(
                        user_id=user_id,
                        trace_id=trace_id,
                        obligation_id=str(ob["id"]),
                        occurred_at=res.occurred_at,
                        app_date=res.app_date,
                        change=ob["op"],
                        kind=ob["kind"],
                        pay_jar=ob.get("pay_jar_code"),
                        due_date=convert.to_date(ob.get("due_date")),
                    )
                )
        elif tool == SAVE_JARS:
            out.append(
                events.profile_updated(
                    user_id=user_id,
                    trace_id=trace_id,
                    occurred_at=res.occurred_at,
                    app_date=res.app_date,
                    fields=["jars"],
                )
            )
        return out


def _wire(block: ReceiptActionBlock) -> dict[str, Any]:
    return block_to_wire(block)
