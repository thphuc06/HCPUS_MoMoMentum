"""Thẻ chủ động của Tổng quan (phase 2): chọn MỘT việc bằng luật tất định, không LLM.

Thứ tự ưu tiên (contracts/rest/openapi.yaml, mô tả `GET /overview`): lương về chờ xác nhận, hũ hụt có ngày cạn sớm nhất,
hũ sát, nghĩa vụ đến hạn trong N ngày (`proactive_obligation_days`, cấu hình), giao dịch cần xem lại, dữ liệu ít (ước lượng
ban đầu). Mọi chữ trên thẻ do code dựng từ số liệu thật. `snooze` và `mute_kind` chỉ lưu phía giao diện ở phase 2.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from yofina_core.blocks import ProactiveCardBlock, build_proactive_card
from yofina_core.money import format_vnd
from yofina_ledger.convert import percent, to_date, vnd

_SNOOZE = {"kind": "snooze", "label": "Để sau"}
_MUTE = {"kind": "mute_kind", "label": "Ít nhắc loại này"}


def _dm(value: date) -> str:
    return f"{value.day:02d}/{value.month:02d}"


def choose_proactive_card(
    *,
    today: date,
    jars: Sequence[Mapping[str, Any]],
    forecasts: Mapping[str, Mapping[str, Any]],
    salary_event: Mapping[str, Any] | None,
    obligations_due: Sequence[Mapping[str, Any]],
    review_count: int,
    obligation_days: int,
    trace_id: str,
    as_of: datetime,
    source_tool: str,
) -> ProactiveCardBlock | None:
    """`jars`: hũ người dùng (không gồm hũ hệ thống); `forecasts`: tóm tắt dự báo mới nhất theo mã hũ."""

    def make(
        kind: str,
        status: str,
        title: str,
        reason: str,
        actions: list[dict[str, Any]],
        jar: str | None = None,
    ):
        return build_proactive_card(
            kind=kind,
            status=status,
            title=title,
            reason=reason,
            actions=actions,
            trace_id=trace_id,
            source_tool=source_tool,
            as_of=as_of,
            app_date=today,
            jar_code=jar,
        )

    if salary_event is not None and salary_event.get("status") == "pending":
        received = to_date(salary_event["received_on"])
        dev = percent(salary_event["deviation_percent"])
        reason = f"Nhận {format_vnd(vnd(salary_event['amount_vnd']))} ngày {_dm(received)}"  # type: ignore[arg-type]
        reason += f", lệch {dev}% so với lương đã khai." if dev else ", đúng số đã khai."
        return make(
            "salary_pending",
            "ok",
            "Lương đã về, chờ bạn xác nhận chia vào các hũ",
            reason,
            [{"kind": "confirm_salary", "label": "Xác nhận chia lương"}, _SNOOZE, _MUTE],
        )

    by_status: dict[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = {
        "short": [],
        "tight": [],
    }
    for jar in jars:
        f = forecasts.get(jar["code"])
        if f is not None and f.get("status") in by_status:
            by_status[f["status"]].append((jar, f))

    def runout_key(item: tuple[Mapping[str, Any], Mapping[str, Any]]) -> tuple[int, str]:
        runout = item[1].get("runout_date")
        return (0 if runout else 1, str(to_date(runout)) if runout else "9999-12-31")

    for status in ("short", "tight"):
        if not by_status[status]:
            continue
        jar, f = min(by_status[status], key=runout_key)
        name, code = jar["name"], jar["code"]
        payday = to_date(f["payday_date"])
        days = int(f["days_to_payday"])
        runout = to_date(f.get("runout_date"))
        balance = format_vnd(vnd(jar["balance_vnd"]))
        if status == "short":
            title = (
                f"Hũ {name} dự kiến cạn ngày {_dm(runout)}"  # type: ignore[arg-type]
                if runout
                else f"Hũ {name} dự kiến hụt trước kỳ lương"
            )
            if runout:
                # Khoảng từ ngày cạn tới lương (cùng số với khối forecast_timeline trong chat), không phải từ hôm nay.
                gap = (payday - runout).days  # type: ignore[operator]
                reason = (
                    f"Còn {balance}, cạn xong còn {gap} ngày nữa mới tới kỳ lương {_dm(payday)}."  # type: ignore[arg-type]
                )
            else:
                reason = f"Còn {balance}, còn {days} ngày tới kỳ lương {_dm(payday)}."  # type: ignore[arg-type]
            if f.get("show_probability") and f.get("p_shortfall") is not None:
                reason += f" Xác suất hụt khoảng {round(float(f['p_shortfall']) * 100)}%."
        else:
            title = f"Hũ {name} đang sát số dư"
            reason = f"Còn {balance}, dự kiến còn rất ít trước kỳ lương {_dm(payday)}."  # type: ignore[arg-type]
        return make(
            "runout_warning",
            status,
            title,
            reason,
            [
                {"kind": "open_forecast", "label": "Xem dự báo", "jar_code": code},
                {
                    "kind": "ask_why",
                    "label": "Hỏi vì sao",
                    "jar_code": code,
                    "prompt": f"Vì sao hũ {name} {'sắp cạn' if status == 'short' else 'đang sát số dư'}?",
                },
                _SNOOZE,
                _MUTE,
            ],
            jar=code,
        )

    soon = [
        o
        for o in obligations_due
        if o.get("status", "active") == "active"
        and 0 <= (to_date(o["due_date"]) - today).days <= obligation_days  # type: ignore[operator]
    ]
    if soon:
        ob = min(soon, key=lambda o: (str(to_date(o["due_date"])), str(o["id"])))
        due = to_date(ob["due_date"])
        pay_jar = ob.get("pay_jar_code")
        pay_name = next((j["name"] for j in jars if j["code"] == pay_jar), None)
        reason = f"Cần {format_vnd(vnd(ob['amount_vnd']))}"
        reason += f", trả từ hũ {pay_name}." if pay_name else "."
        return make(
            "obligation_due",
            "tight",
            f"{ob['name']} đến hạn ngày {_dm(due)}",  # type: ignore[arg-type]
            reason,
            [{"kind": "open_obligations", "label": "Xem nghĩa vụ"}, _SNOOZE, _MUTE],
            jar=pay_jar,
        )

    if review_count > 0:
        return make(
            "review_needed",
            "ok",
            f"{review_count} giao dịch cần bạn xem lại",
            "Có khoản chi chưa xếp được vào hũ nào.",
            [{"kind": "review_unclassified", "label": "Xem lại ngay"}, _SNOOZE, _MUTE],
        )

    initial = [f for f in forecasts.values() if f.get("is_initial_estimate")]
    if initial:
        days = int(max(int(f["history_days"]) for f in initial))
        return make(
            "low_data",
            "ok",
            "Dự báo mới là ước lượng ban đầu",
            f"Mới có {days} ngày dữ liệu. Khai thêm nghĩa vụ hoặc nhập thêm giao dịch để dự báo chính xác hơn.",
            [{"kind": "open_obligations", "label": "Khai nghĩa vụ"}, _SNOOZE, _MUTE],
        )
    return None
