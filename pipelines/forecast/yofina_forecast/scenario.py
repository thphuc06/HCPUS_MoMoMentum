"""`forecast___run_scenario`: áp một `ScenarioSpec` (sáu loại của FR5) lên dự báo đã tính và so SAU với TRƯỚC.

Cách làm (spike-ml-forecasting §6 và §10, "common random numbers"):

1. Dựng `ForecastInputs` của người dùng (cùng hàm `build_inputs` của pipeline) với `scenario_n_paths` (5.000) đường.
2. `apply_scenario` biến đầu vào đó thành đầu vào SAU: đổi số dư hôm nay, thêm khoản chi hoặc thu theo ngày, đổi lịch lương. Mọi
   đổi đều là đổi dữ liệu tất định; không đụng phân phối chi tiêu.
3. Cả hai chạy `update_forecast` trên cùng phân phối chi tiêu ĐÃ fit của lần chạy mới nhất (`jar_state`) và cùng `config.seed`, nên
   cùng một dãy số ngẫu nhiên (ml/montecarlo.py: mỗi dòng ngẫu nhiên của một hũ chỉ phụ thuộc (seed, ngày gốc, mã hũ)). Chênh lệch
   SAU - TRƯỚC vì thế không bị nhiễu mẫu. TRƯỚC ở đây là lần chạy cùng 5.000 đường, nên có thể lệch rất nhỏ so với bản 10.000
   đường ở Chi tiết hũ (nhiễu Monte Carlo); `compare.n_paths` ghi rõ số đường.
4. Dựng `timelines` (hũ bị tác động nhiều nhất trước, tối đa ba), `effects`, `obligation_impact` (kịch bản Trả sau) và `basis`;
   ghi một dòng `scenarios` (dữ liệu dẫn xuất) rồi trả kết quả theo `contracts/tools/forecast.results.schema.json`.

Gộp kịch bản trong một cuộc chat: `with_scenarios` là các kịch bản người dùng VẪN GIỮ từ trước (mua một lần, khoản chi định kỳ,
mua Trả sau; tối đa bốn, tối đa MỘT Trả sau cho cả bó). `apply_bundle` áp chúng nối tiếp rồi mới áp `scenario`; TRƯỚC vẫn là thực
tế hiện tại, SAU là thực tế cộng mọi kịch bản của bó. Mỗi lần chạy lưu `conversation_id` và `bundle` (migration 0051) để tool
`list_scenarios` cho agent biết cuộc chat này đã chạy những gì.

Không có số ngẫu nhiên nào do LLM chọn; mọi số trong kết quả đi từ DB qua engine.
"""

from __future__ import annotations

import logging
import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from yofina_core.blocks import (
    ForecastBasis,
    ForecastTimelineData,
    ObligationImpactData,
    format_instant,
)
from yofina_core.clock import app_today
from yofina_core.errors import PAY_JAR_FIELD, ErrorCode, YofinaError
from yofina_core.money import format_vnd_short
from yofina_core.scenario import parse_scenario, scenario_hash, scenario_to_wire
from yofina_core.schedule import advance_due, bnpl_due_date, obligation_window
from yofina_core.suitability import Proposal
from yofina_core.wallet import (
    BNPL_PRODUCT_CODE,
    DEFAULT_OBLIGATION_JAR,
    resolve_obligation_pay_jar,
    split_amount,
)
from yofina_forecast import repo as forecast_repo
from yofina_forecast.common import (
    STATUS_RANK,
    clip,
    dm,
    int_of,
    min_band,
    to_date,
)
from yofina_forecast.credit import compute_credit_cost, jar_at_due, obligation_impact
from yofina_forecast.inputs import build_inputs
from yofina_forecast.runner import Pipeline
from yofina_forecast.settings import ForecastSettings
from yofina_ml.api import runout_date_shown, update_forecast
from yofina_ml.contract import check_inputs, check_result
from yofina_ml.types import (
    ForecastInputs,
    ForecastResult,
    JarForecast,
    ScheduledFlow,
)
from yofina_planner.engine import evaluate, obligation_ratio_figures
from yofina_planner.facts import facts_from_rows
from yofina_planner.rules import cached_rules

log = logging.getLogger("yofina.forecast.scenario")

MAX_TIMELINES = 3
MAX_RESULT_CHARS = (
    55_000  # bảng `scenarios.result` giới hạn 60.000 ký tự (Data API ~64 KB mỗi dòng)
)
CYCLE_WORD = {"weekly": "mỗi tuần", "monthly": "mỗi tháng", "yearly": "mỗi năm"}

#: `with_scenarios`: tối đa bốn kịch bản đã giữ từ trước, chỉ ba loại này; cả bó có tối đa MỘT `bnpl_purchase`
MAX_PRIOR_SCENARIOS = 4
BUNDLE_PRIOR_KINDS = ("one_time_purchase", "recurring_expense", "bnpl_purchase")
KIND_VN = {
    "one_time_purchase": "mua một lần",
    "bnpl_purchase": "mua Trả sau",
    "income_change": "đổi lương",
    "recurring_expense": "khoản chi định kỳ",
    "jar_transfer": "chuyển hũ",
    "goal_delay": "lùi mục tiêu",
}
#: loại có `amount_vnd` mà tổng của bó (`bundle_total_vnd`) cộng vào: tiền thật sự bỏ ra một lần
BUNDLE_TOTAL_KINDS = ("one_time_purchase", "bnpl_purchase")
CONVERSATION_ID_MAX = 256
LIST_LIMIT_DEFAULT, LIST_LIMIT_MAX = 5, 10


@dataclass(frozen=True)
class JarMeta:
    code: str
    name: str
    color_key: str
    icon_key: str
    kind: str
    balance_vnd: int
    goal_vnd: int | None = None
    goal_date: date | None = None
    purpose: str | None = None

    @classmethod
    def from_row(cls, r: Mapping[str, Any]) -> JarMeta:
        return cls(
            code=r["code"],
            name=r["name"],
            color_key=r["color_key"],
            icon_key=r["icon_key"],
            kind=r["kind"],
            balance_vnd=int_of(r["balance_vnd"]),
            goal_vnd=int_of(r["goal_vnd"]) if r.get("goal_vnd") is not None else None,
            goal_date=to_date(r.get("goal_date")),
            purpose=r.get("purpose"),
        )

    def ref(self) -> dict[str, str]:
        return {
            **({"purpose": self.purpose} if self.purpose is not None else {}),
            "code": self.code,
            "name": self.name,
            "color_key": self.color_key,
            "icon_key": self.icon_key,
        }


@dataclass(frozen=True)
class CreditEnv:
    """Dữ liệu Trả sau để tính chi phí: hạn mức, phí đang hiệu lực, nhãn sản phẩm."""

    line: Mapping[str, Any] | None
    fee: Any | None
    late_fee: Any | None
    label: str


@dataclass
class Applied:
    """Kết quả áp kịch bản: đầu vào SAU, hũ bị tác động, mốc phát sinh thêm và dữ kiện phụ."""

    inputs: ForecastInputs
    targets: list[str]
    label: str
    spec: dict[str, Any]
    kind: str
    extra_events: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    cost: dict[str, Any] | None = None
    pay_jar: str | None = None
    #: tổng các khoản nghĩa vụ ĐÃ có của hũ trả vào ngày đến hạn (cho `due_vnd` của `JarAtDue`)
    existing_due_on_pay_jar: int = 0
    added_obligation_vnd: int = 0
    #: kết quả áp từng kịch bản của bó theo thứ tự (with_scenarios rồi scenario); rỗng khi không gộp (chỉ một kịch bản)
    parts: tuple[Applied, ...] = ()


def _short(n: int) -> str:
    return format_vnd_short(n)


def _name_of(metas: Mapping[str, JarMeta], code: str) -> str:
    return metas[code].name if code in metas else code


def _flow(d: date, label: str, amount: int, kind: str) -> ScheduledFlow:
    return ScheduledFlow(date=d, kind=kind, label=clip(label, 60), amount_vnd=amount)  # type: ignore[arg-type]


def _jar_index(inputs: ForecastInputs, code: str) -> int:
    for i, j in enumerate(inputs.jars):
        if j.code == code:
            return i
    raise KeyError(code)


def _with_jar(inputs: ForecastInputs, code: str, **changes: Any) -> ForecastInputs:
    i = _jar_index(inputs, code)
    jars = list(inputs.jars)
    jars[i] = replace(jars[i], **changes)
    return replace(inputs, jars=tuple(jars))


def _add_outflow(inputs: ForecastInputs, code: str, flow: ScheduledFlow) -> ForecastInputs:
    jar = inputs.jars[_jar_index(inputs, code)]
    outs = sorted((*jar.outflows, flow), key=lambda f: (f.date, f.label))
    return _with_jar(inputs, code, outflows=tuple(outs))


def _with_bnpl_due(
    inputs: ForecastInputs, code: str, due: date, label: str, total: int,
    existing: Mapping[str, Any] | None,
) -> ForecastInputs:
    jar = inputs.jars[_jar_index(inputs, code)]
    ref = str(existing["id"]) if existing else None
    flows = tuple(flow for flow in jar.outflows if not ref or flow.ref_id != ref or flow.date != due)
    out = _with_jar(inputs, code, outflows=flows)
    return _add_outflow(out, code, _flow(due, label, total, "obligation"))


def _add_inflow(inputs: ForecastInputs, code: str, flow: ScheduledFlow) -> ForecastInputs:
    jar = inputs.jars[_jar_index(inputs, code)]
    ins = sorted((*jar.inflows, flow), key=lambda f: (f.date, f.label))
    return _with_jar(inputs, code, inflows=tuple(ins))


def _shift_balance(inputs: ForecastInputs, code: str, delta: int) -> ForecastInputs:
    jar = inputs.jars[_jar_index(inputs, code)]
    return _with_jar(inputs, code, balance_vnd=jar.balance_vnd + delta)


def _check_date(d: date, today: date, horizon: int, *, what: str, allow_today: bool = True) -> None:
    last = today + timedelta(days=horizon)
    if d < today or (d == today and not allow_today):
        raise YofinaError(ErrorCode.SCENARIO_INVALID, f"{what} không được ở quá khứ.")
    if d > last:
        raise YofinaError(
            ErrorCode.SCENARIO_INVALID,
            f"{what} ({dm(d)}) nằm ngoài khoảng dự báo {horizon} ngày (tới {dm(last)}).",
        )


def _forecastable(
    metas: Mapping[str, JarMeta], inputs: ForecastInputs, code: str, *, allow_system: bool = False
) -> bool:
    """True nếu hũ có dự báo. Hũ không tồn tại thì JAR_NOT_FOUND; hũ hệ thống thì FORECAST_NOT_APPLICABLE (trừ khi cho phép,
    như hũ nguồn hay hũ nhận của chuyển hũ, nơi hũ hệ thống chỉ bị bỏ qua)."""
    meta = metas.get(code)
    if meta is None:
        raise YofinaError(ErrorCode.JAR_NOT_FOUND, f"Không tìm thấy hũ {code}.")
    if meta.kind == "system" or all(j.code != code for j in inputs.jars):
        if allow_system:
            return False
        raise YofinaError(
            ErrorCode.FORECAST_NOT_APPLICABLE, f"Hũ {meta.name} là hũ hệ thống, không có dự báo."
        )
    return True


def _label(spec: Any, text: str) -> str:
    return clip(text, 80)


def item_name(label: str | None) -> str | None:
    """Tên món để ghép sau chữ "mua": bỏ chữ "mua"/"Mua" đứng đầu mà model hay để sẵn trong `label` ("Mua dép"),
    tránh nhãn "mua Mua dép"."""
    if not label:
        return None
    name = label.strip()
    if name.lower() == "mua" or name.lower().startswith("mua "):
        name = name[3:].strip()
    return name or None


def apply_scenario(
    spec: Any,
    inputs: ForecastInputs,
    metas: Mapping[str, JarMeta],
    *,
    today: date,
    horizon: int,
    shares: Sequence[tuple[str, Any]],
    salary_vnd: int,
    obligations: Sequence[Mapping[str, Any]],
    credit: CreditEnv | None,
) -> Applied:
    """Áp `spec` (đã qua `parse_scenario`) lên `inputs`. Hàm thuần: không I/O, không đồng hồ."""
    kind = spec.kind
    wire = scenario_to_wire(spec)
    item = item_name(getattr(spec, "label", None))

    if kind == "one_time_purchase":
        d = to_date(spec.date) or today
        _check_date(d, today, horizon, what="Ngày mua")
        code = spec.jar_code
        _forecastable(metas, inputs, code)
        wire["date"] = d.isoformat()
        label = _label(spec, f"mua {item + ' ' if item else ''}{_short(spec.amount_vnd)}")
        events: dict[str, list[dict[str, Any]]] = {}
        if d == today:
            out = _shift_balance(inputs, code, -spec.amount_vnd)
        else:
            out = _add_outflow(
                inputs, code, _flow(d, item or "Mua sắm", spec.amount_vnd, "obligation")
            )
            events[code] = [_event(d, item or "Mua sắm", spec.amount_vnd)]
        return Applied(out, [code], label, wire, kind, events)

    if kind == "bnpl_purchase":
        if credit is None:
            raise YofinaError(ErrorCode.CREDIT_LIMIT_EXCEEDED, "Bạn chưa có hạn mức Trả sau.")
        d = to_date(spec.date) or today
        _check_date(d, today, horizon, what="Ngày mua")
        wire["date"] = d.isoformat()
        line = credit.line
        due_day = int(line["due_day"]) if line else 5
        due = bnpl_due_date(due_day, d)
        existing = next(
            (
                o
                for o in obligations
                if o.get("kind") == "bnpl" and to_date(o.get("due_date")) == due
            ),
            None,
        )
        cost = compute_credit_cost(
            principal_vnd=spec.amount_vnd,
            due_date=due,
            existing_due_vnd=int_of(existing["amount_vnd"]) if existing else None,
            product_label=credit.label,
            line=line,
            fee=credit.fee,
            late_fee=credit.late_fee,
        )
        pay = resolve_obligation_pay_jar(
            ((j.code, j.kind) for j in inputs.jars),
            saved=existing.get("pay_jar_code") if existing else None,
            selected=spec.pay_jar,
        )
        if pay is None:
            raise YofinaError(ErrorCode.SCENARIO_INVALID, "Chọn hũ để trả khoản Trả sau này.", field=PAY_JAR_FIELD)
        label = _label(
            spec,
            f"mua {item + ' ' if item else ''}{_short(spec.amount_vnd)} bằng {credit.label}",
        )
        out = inputs
        events = {}
        charge = cost["principal_vnd"] + cost["fee_added_vnd"]
        if today < due <= today + timedelta(days=horizon):
            out = _with_bnpl_due(out, pay, due, credit.label, cost["total_due_vnd"], existing)
            events[pay] = [_event(due, credit.label, charge)]
        existing_on_jar = sum(
            flow.amount_vnd
            for flow in inputs.jars[_jar_index(inputs, pay)].outflows
            if flow.date == due and (not existing or flow.ref_id != str(existing["id"]))
        ) + (cost.get("existing_due_vnd") or 0)
        return Applied(
            out,
            [pay],
            label,
            wire,
            kind,
            events,
            cost=cost,
            pay_jar=pay,
            existing_due_on_pay_jar=existing_on_jar,
            added_obligation_vnd=cost["item_cost_vnd"],
        )

    if kind == "income_change":
        pay_dates = list(inputs.payday_dates)
        if not pay_dates:
            raise YofinaError(
                ErrorCode.SCENARIO_INVALID, "Chưa có ngày lương nào trong khoảng dự báo."
            )
        d = to_date(spec.date) or pay_dates[0]
        _check_date(d, today, horizon, what="Ngày hiệu lực")
        wire["date"] = d.isoformat()
        try:
            parts = split_amount(spec.new_monthly_salary_vnd, list(shares))
        except ValueError as exc:
            raise YofinaError(
                ErrorCode.SCENARIO_INVALID, f"Không chia được lương mới: {exc}"
            ) from exc
        out = inputs
        targets: list[str] = []
        for j in inputs.jars:
            new_part = parts.get(j.code, 0)
            ins = []
            changed = False
            for f in j.inflows:
                if f.date >= d and f.amount_vnd != new_part:
                    changed = True
                    if new_part > 0:
                        ins.append(replace(f, amount_vnd=new_part))
                else:
                    ins.append(f)
            if changed:
                out = _with_jar(out, j.code, inflows=tuple(ins))
                targets.append(j.code)
        if not targets:
            raise YofinaError(
                ErrorCode.SCENARIO_INVALID,
                "Lương mới không làm đổi khoản nào trong khoảng dự báo (cùng mức lương hiện tại, hoặc hiệu lực sau ngày lương cuối).",
            )
        label = _label(spec, f"lương mới {_short(spec.new_monthly_salary_vnd)}")
        return Applied(out, targets, label, wire, kind)

    if kind == "recurring_expense":
        start = to_date(spec.date)
        assert start is not None
        _check_date(start, today, horizon, what="Ngày bắt đầu")
        end = to_date(spec.end_date)
        code = resolve_obligation_pay_jar(
            ((j.code, j.kind) for j in inputs.jars), selected=spec.jar_code
        )
        if code is None:
            if spec.jar_code is not None:
                _forecastable(metas, inputs, spec.jar_code)
            raise YofinaError(ErrorCode.SCENARIO_INVALID, "Chọn hũ để trả khoản định kỳ này.", field="jar_code")
        wire["jar_code"] = code
        _forecastable(metas, inputs, code)
        out = inputs
        events = {code: []}
        through = today + timedelta(days=horizon)
        cursor: date | None = start
        n = 0
        while (
            cursor is not None and cursor <= through and (end is None or cursor <= end) and n < 400
        ):
            n += 1
            if cursor == today:
                out = _shift_balance(out, code, -spec.amount_vnd)
            else:
                out = _add_outflow(
                    out,
                    code,
                    _flow(cursor, item or "Khoản chi định kỳ", spec.amount_vnd, "obligation"),
                )
                events[code].append(_event(cursor, item or "Khoản chi định kỳ", spec.amount_vnd))
            cursor = advance_due(cursor, spec.cycle, start.day if spec.cycle == "monthly" else None)
        label = _label(
            spec,
            f"thêm {item + ' ' if item else 'khoản chi '}{_short(spec.amount_vnd)} {CYCLE_WORD[spec.cycle]}",
        )
        return Applied(
            out,
            [code],
            label,
            wire,
            kind,
            events,
            added_obligation_vnd=spec.amount_vnd,
        )

    if kind == "jar_transfer":
        d = to_date(spec.date) or today
        _check_date(d, today, horizon, what="Ngày chuyển")
        wire["date"] = d.isoformat()
        src_ok = _forecastable(metas, inputs, spec.from_jar, allow_system=True)
        dst_ok = _forecastable(metas, inputs, spec.to_jar, allow_system=True)
        if not (src_ok or dst_ok):
            raise YofinaError(
                ErrorCode.FORECAST_NOT_APPLICABLE, "Cả hai hũ đều là hũ hệ thống, không có dự báo."
            )
        out = inputs
        events = {}
        targets = []
        src_name, dst_name = _name_of(metas, spec.from_jar), _name_of(metas, spec.to_jar)
        if src_ok:
            targets.append(spec.from_jar)
            if d == today:
                out = _shift_balance(out, spec.from_jar, -spec.amount_vnd)
            else:
                out = _add_outflow(
                    out,
                    spec.from_jar,
                    _flow(d, f"Chuyển sang {dst_name}", spec.amount_vnd, "obligation"),
                )
                events[spec.from_jar] = [_event(d, f"Chuyển sang {dst_name}", spec.amount_vnd)]
        if dst_ok:
            targets.append(spec.to_jar)
            if d == today:
                out = _shift_balance(out, spec.to_jar, spec.amount_vnd)
            else:
                out = _add_inflow(
                    out, spec.to_jar, _flow(d, f"Nhận từ {src_name}", spec.amount_vnd, "salary")
                )
        label = _label(spec, f"chuyển {_short(spec.amount_vnd)} từ {src_name} sang {dst_name}")
        return Applied(out, targets, label, wire, kind, events)

    # goal_delay
    code = spec.jar_code
    _forecastable(metas, inputs, code)
    meta = metas[code]
    if meta.purpose not in (None, "goal") or meta.goal_vnd is None or meta.goal_date is None:
        raise YofinaError(ErrorCode.SCENARIO_INVALID, f"Hũ {meta.name} chưa có mục tiêu để lùi.")
    remaining = max(meta.goal_vnd - meta.balance_vnd, 0)
    days_left = max((meta.goal_date - today).days, 0)
    months_before = max(math.ceil(days_left / 30), 1)
    months_after = months_before + spec.delay_months
    need_before = math.ceil(remaining / months_before)
    need_after = math.ceil(remaining / months_after)
    label = _label(
        spec,
        f"lùi mục tiêu {meta.name} {spec.delay_months} tháng: cần {_short(need_after)}/tháng thay vì {_short(need_before)}",
    )
    return Applied(inputs, [code], label, wire, kind)


def apply_bundle(
    specs: Sequence[Any],
    inputs: ForecastInputs,
    metas: Mapping[str, JarMeta],
    *,
    today: date,
    horizon: int,
    shares: Sequence[tuple[str, Any]],
    salary_vnd: int,
    obligations: Sequence[Mapping[str, Any]],
    credit: CreditEnv | None,
) -> Applied:
    """Áp một bó kịch bản (phần tử cuối là kịch bản chính) lên `inputs`, nối tiếp. Hàm thuần.

    Một kịch bản thì trả đúng `apply_scenario`. Nhiều kịch bản: đầu vào SAU cộng dồn mọi thay đổi; `targets` là hợp các hũ bị tác
    động (hũ của kịch bản chính đứng đầu); sự kiện gộp theo hũ; chi phí và nghĩa vụ lấy từ khoản Trả sau duy nhất (nếu có), còn
    `added_obligation_vnd` cộng dồn; nhãn gộp bằng " + ". Khoản Trả sau được áp SAU CÙNG (kết quả không phụ thuộc thứ tự áp, chỉ
    `existing_due_on_pay_jar` cần thấy các khoản chi cùng ngày đến hạn của bó)."""
    n = len(specs)
    if n == 0:
        raise YofinaError(ErrorCode.PARAMS_INVALID, "Thiếu kịch bản.")
    common: dict[str, Any] = {
        "today": today,
        "horizon": horizon,
        "shares": shares,
        "salary_vnd": salary_vnd,
        "obligations": obligations,
        "credit": credit,
    }
    if n == 1:
        return apply_scenario(specs[0], inputs, metas, **common)
    results: list[Applied | None] = [None] * n
    current = inputs
    for i in sorted(range(n), key=lambda k: specs[k].kind == "bnpl_purchase"):
        try:
            applied = apply_scenario(specs[i], current, metas, **common)
        except YofinaError as exc:
            if i == n - 1:
                raise
            raise YofinaError(
                exc.code,
                f"Khoản đã giữ từ trước ({KIND_VN.get(specs[i].kind, specs[i].kind)}): {exc.message}",
            ) from exc
        results[i] = applied
        current = applied.inputs
    parts = tuple(a for a in results if a is not None)
    main = parts[-1]
    targets: list[str] = []
    for a in (main, *parts[:-1]):
        targets.extend(t for t in a.targets if t not in targets)
    events: dict[str, list[dict[str, Any]]] = {}
    for a in parts:
        for code, evs in a.extra_events.items():
            events.setdefault(code, []).extend(evs)
    for evs in events.values():
        evs.sort(key=lambda e: (e["date"], e["label"]))
    credit_part = next((a for a in parts if a.cost is not None), None)
    return Applied(
        inputs=current,
        targets=targets,
        label=_label(None, " + ".join(a.label for a in parts)),
        spec=main.spec,
        kind=main.kind,
        extra_events=events,
        cost=credit_part.cost if credit_part else None,
        pay_jar=credit_part.pay_jar if credit_part else None,
        existing_due_on_pay_jar=credit_part.existing_due_on_pay_jar if credit_part else 0,
        added_obligation_vnd=sum(a.added_obligation_vnd for a in parts),
        parts=parts,
    )


def bundle_items(applied: Applied) -> list[dict[str, Any]]:
    """Tóm tắt từng khoản của bó theo thứ tự áp (kể cả khi chỉ có một): `kind`, `label` riêng, `amount_vnd` và `jar_code` nếu có,
    `spec` dạng wire đã chuẩn hóa."""
    items: list[dict[str, Any]] = []
    for part in applied.parts or (applied,):
        item: dict[str, Any] = {"kind": part.kind, "label": part.label}
        amount = part.spec.get("amount_vnd")
        if isinstance(amount, int) and not isinstance(amount, bool):
            item["amount_vnd"] = amount
        if part.spec.get("jar_code"):
            item["jar_code"] = part.spec["jar_code"]
        item["spec"] = part.spec
        items.append(item)
    return items


def bundle_total_vnd(items: Sequence[Mapping[str, Any]]) -> int:
    """Tổng `amount_vnd` các khoản mua một lần và mua Trả sau của bó."""
    return sum(int(i["amount_vnd"]) for i in items if i["kind"] in BUNDLE_TOTAL_KINDS)


def _event(d: date, label: str, amount: int) -> dict[str, Any]:
    return {
        "date": d.isoformat(),
        "kind": "obligation",
        "label": clip(label, 60),
        "amount_vnd": amount,
    }


# =====================================================================================
# Dựng kết quả
# =====================================================================================
def _days_payload(jf: JarForecast) -> list[dict[str, Any]]:
    return [
        {
            "date": d.date.isoformat(),
            "p10_vnd": d.balance_p10_vnd,
            "p50_vnd": d.balance_p50_vnd,
            "p90_vnd": d.balance_p90_vnd,
        }
        for d in jf.days
    ]


def _events_payload(jar: Any, *, include_original_dates: bool = False) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in (*jar.outflows, *jar.inflows):
        item: dict[str, Any] = {
            "date": f.date.isoformat(),
            "kind": f.kind,
            "label": f.label,
            "amount_vnd": f.amount_vnd,
        }
        if include_original_dates and f.original_due_date is not None:
            item["original_due_date"] = f.original_due_date.isoformat()
        if f.amount_max_vnd is not None and f.amount_max_vnd > f.amount_vnd:
            item["amount_max_vnd"] = f.amount_max_vnd
        out.append(item)
    out.sort(key=lambda e: (e["date"], 0 if e["kind"] == "obligation" else 1, e["label"]))
    return out


def _min_p50(jf: JarForecast) -> int:
    return min(d.balance_p50_vnd for d in jf.days)


def _runout_shift(
    before: date | None, after: date | None, origin: date, horizon: int
) -> int | None:
    """Ngày cạn SAU trừ TRƯỚC (âm là cạn sớm hơn). Bên không cạn trong horizon được coi như cạn ở ngày ngay sau horizon."""
    if before is None and after is None:
        return None
    beyond = origin + timedelta(days=horizon + 1)
    return ((after or beyond) - (before or beyond)).days


def _runs_out_by_payday(jf: JarForecast) -> bool:
    """Số dư P50 chạm ngưỡng cạn TRƯỚC hoặc ĐÚNG ngày lương kế.

    Xác suất hụt của engine ML (và trạng thái suy từ nó) chỉ xét các ngày TRƯỚC ngày lương (`window` = số ngày tới lương - 1). Một
    khoản đến hạn đúng ngày lương (Trả sau của `minh` đến hạn 05/12, lương cũng ngày 5) lớn hơn số dư cộng phần lương về hũ thì hũ
    cạn ngay ngày đó mà xác suất "trước kỳ lương" vẫn là 0, nên trạng thái "đủ" mâu thuẫn với số dư thấp nhất âm và ngày cạn."""
    s = jf.summary
    return s.runout_date is not None and s.runout_date <= s.payday_date


def _status(jf: JarForecast) -> str:
    """Trạng thái hiển thị trên thẻ what-if: trạng thái của engine, trừ khi hũ cạn trước hoặc đúng ngày lương thì là hụt (cùng
    nghĩa "hụt trước kỳ lương" mà người dùng đọc cạnh ngày cạn và số dư thấp nhất của chính thẻ)."""
    return "short" if _runs_out_by_payday(jf) else jf.summary.status


def _p(jf: JarForecast) -> float | None:
    """Xác suất hụt để hiển thị. Bỏ khi hũ cạn ngay ngày lương: xác suất của engine không xét ngày đó nên con số (thường 0%)
    sẽ nói ngược với trạng thái hụt và ngày cạn; khi đó thẻ chỉ nói ngày cạn."""
    s = jf.summary
    if not s.show_probability or s.p_shortfall is None:
        return None
    if _runs_out_by_payday(jf) and s.status != "short":
        return None
    return round(float(s.p_shortfall), 4)


def _p_se(jf: JarForecast) -> float | None:
    s = jf.summary
    return (
        round(float(s.p_shortfall_se), 5)
        if _p(jf) is not None and s.p_shortfall_se is not None
        else None
    )


def _impact_key(b: JarForecast, a: JarForecast) -> tuple[int, int, int]:
    """Hũ bị tác động nhiều hơn xếp trước: trạng thái xấu đi nhiều, rồi số dư thấp nhất giảm nhiều, rồi trạng thái SAU nặng hơn."""
    worsen = STATUS_RANK[_status(a)] - STATUS_RANK[_status(b)]
    return (-worsen, _min_p50(a) - _min_p50(b), -STATUS_RANK[_status(a)])


class ScenarioEngine:
    """Điều phối `run_scenario`. Đọc dữ liệu qua `ledger_repo` (cùng giao diện `LedgerRepo`) và `pipeline` (đầu vào dự báo,
    trạng thái đã fit); ghi một dòng `scenarios`."""

    def __init__(
        self,
        pipeline: Pipeline,
        ledger_repo: Any,
        ref: Any,
        settings: ForecastSettings,
        *,
        rules: Any = None,
    ) -> None:
        self.pipeline = pipeline
        self.repo = ledger_repo
        self.ref = ref
        self.settings = settings
        self._rules = rules

    @property
    def rules(self):  # type: ignore[no-untyped-def]
        return self._rules or cached_rules()

    # ----------------------------------------------------------------------------------------------
    def run(
        self,
        user_id: str,
        scenario: Any,
        *,
        trace_id: str,
        conversation_id: Any = None,
        with_scenarios: Any = None,
    ) -> dict[str, Any]:
        spec = self._parse(scenario)
        conversation = self._conversation_id(conversation_id)
        prior = self._parse_prior(with_scenarios, spec)
        bundle_specs = [*prior, spec]
        s = self.settings
        now = self.pipeline.now()
        ctx = self.pipeline.load_context(user_id, now)
        today = ctx.app_date
        built = build_inputs(ctx, s, user_id, n_paths=s.scenario_n_paths)
        view = self.repo.jar_view(user_id)
        metas = {r["code"]: JarMeta.from_row(r) for r in view.jars}
        profile = ctx.meta.get("profile") or {}
        user_jars = [j for j in ctx.jars if j["kind"] != "system"]
        credit = (
            self._credit_env(user_id, today)
            if any(sp.kind == "bnpl_purchase" for sp in bundle_specs)
            else None
        )

        applied = apply_bundle(
            bundle_specs,
            built.inputs,
            metas,
            today=today,
            horizon=s.horizon_days,
            shares=[(j["code"], j["split_percent"]) for j in user_jars],
            salary_vnd=int_of(profile.get("monthly_salary_vnd")),
            obligations=ctx.obligations,
            credit=credit,
        )
        errors = check_inputs(applied.inputs)
        if errors:
            raise YofinaError(
                ErrorCode.SCENARIO_INVALID,
                "Kịch bản tạo đầu vào không hợp lệ: " + "; ".join(errors[:2]),
            )

        ob_rows = (
            self.repo.list_obligations(user_id, status="active", limit=100)
            if applied.added_obligation_vnd
            else []
        )
        previous, parent_run_id, _rows = self._previous(user_id, built.inputs, applied.targets)
        before = update_forecast(built.inputs, previous, applied.targets)
        after = update_forecast(applied.inputs, previous, applied.targets)
        for res, inp in ((before, built.inputs), (after, applied.inputs)):
            bad = check_result(inp, res, subset=True)
            if bad:
                raise YofinaError(
                    ErrorCode.INTERNAL_ERROR, "Kết quả kịch bản sai hợp đồng: " + "; ".join(bad[:2])
                )

        scenario_id = str(uuid.uuid4())
        data = self._build_data(
            scenario_id=scenario_id,
            applied=applied,
            built_inputs=built.inputs,
            before=before,
            after=after,
            metas=metas,
            now=now,
            today=today,
            ctx_profile=profile,
            facts_inputs=(view, ob_rows),
        )
        result_for_db = self._db_result(data)
        forecast_repo.save_scenario(
            self.pipeline.repo,
            user_id,
            scenario_id=scenario_id,
            trace_id=trace_id,
            kind=applied.kind,
            spec=applied.spec,
            spec_hash=scenario_hash(applied.spec),
            app_date=today,
            baseline_run_id=parent_run_id,
            n_paths=int(before.run.n_paths or s.scenario_n_paths),
            seed=before.run.seed,
            result=result_for_db,
            keep=s.scenario_keep,
            conversation_id=conversation,
            bundle=[part.spec for part in applied.parts or (applied,)],
        )
        return {
            "status": "OK",
            "as_of": format_instant(now),
            "app_date": today.isoformat(),
            "data": data,
        }

    # ----------------------------------------------------------------------------------------------
    def list_scenarios(
        self, user_id: str, *, conversation_id: Any, limit: Any = None
    ) -> dict[str, Any]:
        """`forecast___list_scenarios`: các kịch bản đã chạy trong MỘT cuộc chat của chính người dùng, mới nhất trước (đọc, không ghi).
        Dòng cũ không có `bundle` thì `bundle` là [spec chính]."""
        cid = self._conversation_id(conversation_id, required=True)
        if limit is None:
            n = LIST_LIMIT_DEFAULT
        elif isinstance(limit, int) and not isinstance(limit, bool):
            n = min(max(limit, 1), LIST_LIMIT_MAX)
        else:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "limit phải là số nguyên từ 1 đến 10.")
        now = self.pipeline.now()
        view = self.repo.jar_view(user_id)
        if view.clock_offset_days is None:
            raise YofinaError(ErrorCode.PROFILE_INCOMPLETE, "Người dùng chưa có hồ sơ.")
        today = app_today(view.clock_offset_days, now, self.settings.tz)
        rows = forecast_repo.list_conversation_scenarios(self.pipeline.repo, user_id, cid, n)
        return {
            "status": "OK",
            "as_of": format_instant(now),
            "app_date": today.isoformat(),
            "data": {"scenarios": [self._scenario_item(r) for r in rows[:n]]},
        }

    @staticmethod
    def _scenario_item(row: Mapping[str, Any]) -> dict[str, Any]:
        spec = dict(row["spec"])
        label = row.get("result_label") or KIND_VN.get(row["kind"], row["kind"])
        summary = row.get("result_bundle")
        if isinstance(summary, list) and summary:
            bundle = list(summary)
        else:  # dòng cũ (trước migration 0051) hoặc kết quả không có tóm tắt: bó chỉ có spec chính
            single: dict[str, Any] = {"kind": row["kind"], "label": label}
            amount = spec.get("amount_vnd")
            if isinstance(amount, int) and not isinstance(amount, bool):
                single["amount_vnd"] = amount
            if spec.get("jar_code"):
                single["jar_code"] = spec["jar_code"]
            single["spec"] = spec
            bundle = [single]
        return {
            "scenario_id": str(row["id"]),
            "created_at": format_instant(row["created_at"]),
            "kind": row["kind"],
            "label": label,
            "spec": spec,
            "bundle": bundle,
        }

    # ----------------------------------------------------------------------------------------------
    @staticmethod
    def _parse(scenario: Any, what: str = "scenario") -> Any:
        if not isinstance(scenario, Mapping):
            raise YofinaError(ErrorCode.PARAMS_INVALID, f"{what} phải là một đối tượng.")
        clean = {k: v for k, v in scenario.items() if v is not None and v != ""}
        try:
            return parse_scenario(clean)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(p) for p in first.get("loc", ()) if p != "")
            msg = str(first.get("msg", ""))
            if first.get("type") in ("union_tag_invalid", "union_tag_not_found") or "kind" in where:
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID,
                    "kind phải là một trong sáu loại kịch bản đã nêu trong mô tả tool."
                    if what == "scenario"
                    else f"kind của {what} phải là một trong sáu loại kịch bản đã nêu trong mô tả tool.",
                ) from None
            if first.get("type") == "value_error":
                raise YofinaError(
                    ErrorCode.SCENARIO_INVALID, msg.removeprefix("Value error, ")
                ) from None
            raise YofinaError(
                ErrorCode.PARAMS_INVALID,
                f"{what} không hợp lệ ({where or what}): thiếu hoặc sai trường theo loại.",
            ) from None

    @staticmethod
    def _conversation_id(value: Any, *, required: bool = False) -> str | None:
        """`conversation_id` (session id của cuộc chat): chuỗi 1 tới 256 ký tự. Vắng hoặc rỗng thì None (trừ khi `required`)."""
        if value is None or value == "":
            if required:
                raise YofinaError(ErrorCode.PARAMS_INVALID, "Thiếu conversation_id.")
            return None
        if not isinstance(value, str) or len(value) > CONVERSATION_ID_MAX:
            raise YofinaError(
                ErrorCode.PARAMS_INVALID,
                f"conversation_id phải là chuỗi tối đa {CONVERSATION_ID_MAX} ký tự.",
            )
        return value

    def _parse_prior(self, with_scenarios: Any, main: Any) -> list[Any]:
        """Kiểm và parse `with_scenarios` (các kịch bản đã giữ từ trước). Luật của bó: tối đa bốn khoản trước đó, chỉ mua một lần,
        khoản chi định kỳ và mua Trả sau, tối đa MỘT khoản Trả sau cho cả bó (tính cả kịch bản chính)."""
        if with_scenarios is None:
            return []
        if not isinstance(with_scenarios, Sequence) or isinstance(
            with_scenarios, str | bytes | Mapping
        ):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "with_scenarios phải là một danh sách.")
        if len(with_scenarios) > MAX_PRIOR_SCENARIOS:
            raise YofinaError(
                ErrorCode.SCENARIO_INVALID,
                f"Chỉ gộp được tối đa {MAX_PRIOR_SCENARIOS} kịch bản đã giữ từ trước vào một mô phỏng.",
            )
        prior = [self._parse(item, f"with_scenarios[{i}]") for i, item in enumerate(with_scenarios)]
        for item in prior:
            if item.kind not in BUNDLE_PRIOR_KINDS:
                raise YofinaError(
                    ErrorCode.SCENARIO_INVALID,
                    f"Chưa gộp được kịch bản {KIND_VN[item.kind]} vào mô phỏng chung; chỉ gộp được "
                    "mua một lần, khoản chi định kỳ và mua Trả sau.",
                )
        if sum(1 for sp in (*prior, main) if sp.kind == "bnpl_purchase") > 1:
            raise YofinaError(
                ErrorCode.SCENARIO_INVALID,
                "Chưa gộp được hai khoản Trả sau trong một mô phỏng.",
            )
        return prior

    def _credit_env(self, user_id: str, today: date) -> CreditEnv:
        line = self.repo.credit_line(user_id)
        code = (line or {}).get("product_code") or BNPL_PRODUCT_CODE
        fees = self.ref.active_fees(code, today)
        fee = self.ref.bnpl_monthly_fee(today)
        late = next((f for f in fees if f.condition_code == "overdue" and f.amount_vnd), None)
        return CreditEnv(
            line=line, fee=fee, late_fee=late, label=self.ref.product_label(code, today)
        )

    def _previous(self, user_id: str, inputs: ForecastInputs, targets: Sequence[str]):  # type: ignore[no-untyped-def]
        now = self.pipeline.now()
        prev, _reason, rows = self.pipeline.previous_state(user_id, inputs, targets, now)
        if prev is None:  # chưa có nền hoặc quá cũ: tính đầy đủ một lần rồi thử lại
            self.pipeline.run_user(user_id, trigger="manual")
            prev, _reason, rows = self.pipeline.previous_state(
                user_id, inputs, targets, self.pipeline.now()
            )
        if prev is None:
            raise YofinaError(
                ErrorCode.FORECAST_UNAVAILABLE,
                "Chưa có nền dự báo để chạy kịch bản, thử lại sau ít phút.",
            )
        previous, parent_run_id = prev
        return previous, parent_run_id, rows

    # ----------------------------------------------------------------------------------------------
    def _thresholds(self) -> tuple[int, int]:
        return (
            self.settings.affordability_short_p50_floor_vnd,
            self.settings.affordability_tight_p10_floor_vnd,
        )

    def _basis(
        self, before: ForecastResult, after: ForecastResult, now: datetime
    ) -> dict[str, Any]:
        run = before.run
        bands = [jf.summary.confidence_band for jf in (*before.jars, *after.jars)]
        basis: dict[str, Any] = {
            "computed_at": format_instant(now),
            "stale": False,
            "confidence_band": min_band(bands),
            "is_initial_estimate": bool(run.is_initial_estimate),
            "history_days": int(run.history_days),
        }
        if run.data_coverage is not None:
            basis["coverage"] = round(float(run.data_coverage), 3)
        return basis

    def _build_data(
        self,
        *,
        scenario_id: str,
        applied: Applied,
        built_inputs: ForecastInputs,
        before: ForecastResult,
        after: ForecastResult,
        metas: Mapping[str, JarMeta],
        now: datetime,
        today: date,
        ctx_profile: Mapping[str, Any],
        facts_inputs: tuple[Any, Any],
    ) -> dict[str, Any]:
        s = self.settings
        pairs = list(zip(before.jars, after.jars, strict=True))
        pairs.sort(key=lambda p: _impact_key(p[0], p[1]))
        basis = self._basis(before, after, now)
        run = before.run
        horizon = s.horizon_days

        effects: list[dict[str, Any]] = []
        timelines: list[dict[str, Any]] = []
        for b, a in pairs:
            meta = metas[b.summary.jar_code]
            sb, sa = b.summary, a.summary
            # hũ thưa (#25): ngày cạn sai trung bình hơn 6 ngày nên không nêu ngày trước, sau, hay độ dời ngày cạn
            date_shown = runout_date_shown(before, sb.jar_code) and runout_date_shown(
                after, sb.jar_code
            )
            runout_b = sb.runout_date if date_shown else None
            runout_a = sa.runout_date if date_shown else None
            effect: dict[str, Any] = {
                "jar": meta.ref(),
                "status_before": _status(b),
                "status_after": _status(a),
                "min_balance_delta_vnd": _min_p50(a) - _min_p50(b),
            }
            if runout_b:
                effect["runout_date_before"] = runout_b.isoformat()
            if runout_a:
                effect["runout_date_after"] = runout_a.isoformat()
            if _p(b) is not None:
                effect["p_shortfall_before"] = _p(b)
            if _p(a) is not None:
                effect["p_shortfall_after"] = _p(a)
            effects.append(effect)
            if len(timelines) >= MAX_TIMELINES:
                continue
            code = sb.jar_code
            jar_in = built_inputs.jars[_jar_index(built_inputs, code)]
            p_b, p_a = _p(b), _p(a)
            path: dict[str, Any] = {
                "status": _status(a),
                "min_balance_p50_vnd": _min_p50(a),
                "days": _days_payload(a),
            }
            if runout_a:
                path["runout_date"] = runout_a.isoformat()
            if p_a is not None:
                path["p_shortfall"] = p_a
                if _p_se(a) is not None:
                    path["p_shortfall_se"] = _p_se(a)
            extra = applied.extra_events.get(code)
            if extra:
                path["events"] = extra[:60]
            delta: dict[str, Any] = {"min_balance_delta_vnd": _min_p50(a) - _min_p50(b)}
            shift = _runout_shift(runout_b, runout_a, today, horizon) if date_shown else None
            if shift is not None:
                delta["runout_shift_days"] = shift
            if p_a is not None and p_b is not None:
                delta["p_shortfall_delta"] = round(p_a - p_b, 4)
            tl: dict[str, Any] = {
                "jar": meta.ref(),
                "status": _status(b),
                "origin_date": today.isoformat(),
                "start_balance_vnd": sb.start_balance_vnd,
                "horizon_days": horizon,
                "payday": {"date": sb.payday_date.isoformat(), "days_until": sb.days_to_payday},
                "confidence_band": sb.confidence_band,
                "history_days": int(run.history_days),
                "is_initial_estimate": bool(run.is_initial_estimate),
                "model": run.model,
                "computed_at": basis["computed_at"],
                "stale": False,
                "days": _days_payload(b),
                "events": _events_payload(jar_in)[:60],
                "compare": {
                    "label": applied.label,
                    "kind": applied.kind,
                    "scenario_id": scenario_id,
                    "after": path,
                    "delta": delta,
                    "n_paths": int(run.n_paths or s.scenario_n_paths),
                    "common_random_numbers": True,
                },
            }
            if code == DEFAULT_OBLIGATION_JAR and meta.kind == "obligation":
                jar_after = applied.inputs.jars[_jar_index(applied.inputs, code)]
                for target, source, forecast in ((tl, jar_in, b), (path, jar_after, a)):
                    target["obligations_before_payday"] = obligation_window(
                        _events_payload(source, include_original_dates=True),
                        forecast.summary.payday_date.isoformat(),
                        {d.date.isoformat(): d.balance_p50_vnd for d in forecast.days},
                        opening_balance_vnd=source.balance_vnd,
                    )
            if runout_b:
                tl["runout_date"] = runout_b.isoformat()
            if not date_shown:
                tl["runout_date_shown"] = False
            if p_b is not None:
                tl["p_shortfall"] = p_b
                if _p_se(b) is not None:
                    tl["p_shortfall_se"] = _p_se(b)
            if run.data_coverage is not None:
                tl["coverage"] = round(float(run.data_coverage), 3)
            timelines.append(
                ForecastTimelineData.model_validate(tl).model_dump(mode="json", exclude_none=True)
            )

        data: dict[str, Any] = {
            "scenario_id": scenario_id,
            "spec": applied.spec,
            "n_paths": int(run.n_paths or s.scenario_n_paths),
            "common_random_numbers": True,
            "effects": effects[:8],
            "timelines": timelines,
            "basis": ForecastBasis.model_validate(basis).model_dump(mode="json", exclude_none=True),
        }
        items = bundle_items(applied)
        data["bundle"] = items
        if len(items) >= 2:
            data["bundle_total_vnd"] = bundle_total_vnd(items)
        if applied.cost is not None and applied.pay_jar is not None:
            data["obligation_impact"] = self._obligation_impact(
                applied, after, metas, basis, now, today, facts_inputs, ctx_profile
            )
        return data

    def _obligation_impact(
        self,
        applied: Applied,
        after: ForecastResult,
        metas: Mapping[str, JarMeta],
        basis: Mapping[str, Any],
        now: datetime,
        today: date,
        facts_inputs: tuple[Any, Any],
        profile: Mapping[str, Any],
    ) -> dict[str, Any]:
        cost = applied.cost
        assert cost is not None and applied.pay_jar is not None
        short_floor, tight_floor = self._thresholds()
        due = date.fromisoformat(cost["due_date"])
        jf = next(j for j in after.jars if j.summary.jar_code == applied.pay_jar)
        series = [
            (d.date, d.balance_p10_vnd, d.balance_p50_vnd, d.balance_p90_vnd) for d in jf.days
        ]
        due_vnd = applied.existing_due_on_pay_jar + cost["principal_vnd"] + cost["fee_added_vnd"]
        entry = jar_at_due(
            jar=metas[applied.pay_jar].ref(),
            days=series,
            due_date=due,
            due_vnd=due_vnd,
            short_floor_vnd=short_floor,
            tight_floor_vnd=tight_floor,
        )
        view, ob_rows = facts_inputs
        facts = facts_from_rows(
            today=today,
            user={
                "monthly_salary_vnd": profile.get("monthly_salary_vnd"),
                "payday_day": profile.get("payday_day"),
                "risk_tolerance": None,
            },
            jars=view.jars,
            obligations=ob_rows,
            window_days=self.settings.horizon_days,
        )
        ratio = obligation_ratio_figures(facts, cost["item_cost_vnd"], self.rules)
        verdict = evaluate(
            Proposal(
                kind="bnpl_purchase",
                amount_vnd=cost["principal_vnd"],
                funding_source="credit",
                origin="user_request",
            ),
            facts,
            self.rules,
            added_obligation_vnd=cost["item_cost_vnd"],
        )
        cautions = [{"rule_id": v.rule_id, "text": v.message[:140]} for v in verdict.violations][:3]
        impact = obligation_impact(
            cost=cost, at_due=[entry], ratio=ratio, cautions=cautions, basis=basis
        )
        return ObligationImpactData.model_validate(impact).model_dump(
            mode="json", exclude_none=True
        )

    @staticmethod
    def _db_result(data: Mapping[str, Any]) -> dict[str, Any]:
        """Kết quả gọn để lưu (không có `spec`, đã ở cột riêng). Quá lớn thì giảm số khối trước-sau cho vừa giới hạn bảng."""
        out = {k: v for k, v in data.items() if k not in ("spec", "scenario_id")}
        import json

        while (
            len(json.dumps(out, ensure_ascii=False)) > MAX_RESULT_CHARS
            and len(out["timelines"]) > 1
        ):
            out["timelines"] = out["timelines"][:-1]
        return out


__all__ = [
    "Applied",
    "CreditEnv",
    "JarMeta",
    "ScenarioEngine",
    "apply_bundle",
    "apply_scenario",
    "bundle_items",
    "bundle_total_vnd",
]
