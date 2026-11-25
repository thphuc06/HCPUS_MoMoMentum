"""Thẻ chủ động của Tổng quan (phase 2): chọn MỘT việc bằng luật tất định, không LLM.

Thứ tự ưu tiên (contracts/rest/openapi.yaml, mô tả `GET /overview`): lương về chờ xác nhận, hũ hụt có ngày cạn sớm nhất,
hũ sát, nghĩa vụ đến hạn trong N ngày (`proactive_obligation_days`, cấu hình), giao dịch cần xem lại, dữ liệu ít (ước lượng
ban đầu). Mọi chữ trên thẻ do code dựng từ số liệu thật. `snooze` và `mute_kind` chỉ lưu phía giao diện ở phase 2.

Phase 5 (FR13, luồng B): CỔNG GIÁ TRỊ của bản tin chủ động (phần "cổng bản tin" ở cuối file). Batch đêm (Lambda forecast-batch,
`yofina_forecast.behavior.run_nudge_gate`) gom ứng viên, `select_nudge` chọn tối đa MỘT việc mỗi ngày khi vượt ngưỡng theo
`wallet.NUDGE_GATE_ORDER` (loại bị "Ít nhắc loại này" hạ một bậc), rồi ghi một dòng `nudges` `source = system`. `GET /nudges/today`
(`nudges_rest`) dựng thẻ `proactive_card` có `nudge_id` từ dòng đó và tôn trọng giờ im lặng trong sở thích của người dùng
(`NudgePreferences`, điểm móc `NudgePreferenceSource` cho bộ nhớ dài hạn của luồng p5-memory).
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol

from yofina_core.blocks import ProactiveCardBlock, block_to_wire, build_proactive_card
from yofina_core.money import format_vnd
from yofina_core.pii import fold
from yofina_core.wallet import NUDGE_GATE_ORDER
from yofina_ledger.convert import percent, to_date, vnd

_SNOOZE = {"kind": "snooze", "label": "Để sau"}
_MUTE = {"kind": "mute_kind", "label": "Ít nhắc loại này"}


def _dm(value: date) -> str:
    return f"{value.day:02d}/{value.month:02d}"


def shortfall_chance_text(p: float) -> str:
    """Khả năng hụt (0..1) thành chữ, CÙNG LUẬT với `formatShortfallChance` của frontend (`frontend/src/lib/format.ts`): làm tròn
    bước 5% (backtest phase 2 mục 2.5: xác suất hũ dày lệch 2 đến 8 điểm %), tròn lên 100% thì "Gần như chắc chắn", tròn về 0% thì
    "Dưới 5%" (mô hình không chắc tuyệt đối). Làm tròn nửa lên như `Math.round`, không theo kiểu ngân hàng của `round`."""
    step = math.floor(float(p) * 20 + 0.5)
    if step >= 20:
        return "Gần như chắc chắn"
    if step <= 0:
        return "Dưới 5%"
    return f"{step * 5}%"


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
    # Tài khoản chưa có đồng nào trong hũ (mới onboarding, hoặc vừa "Xóa dữ liệu của tôi"): chưa có gì để cạn, không cảnh báo hũ.
    funded = _has_money(jars)
    for jar in jars if funded else ():
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
        if status == "short" and vnd(jar["balance_vnd"]) <= 0:
            # Hũ đã hết tiền: "dự kiến cạn … Còn 0 ₫" sai nghĩa, nói thẳng là đã hết và còn bao lâu tới lương.
            title = f"Hũ {name} đã hết tiền"
            reason = f"Còn {days} ngày nữa mới tới kỳ lương {_dm(payday)}."  # type: ignore[arg-type]
        elif status == "short":
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
                reason += f" Khả năng hụt: {shortfall_chance_text(float(f['p_shortfall'])).lower()}."
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
            (
                f"Mới có {days} ngày dữ liệu. Khai thêm nghĩa vụ hoặc nhập thêm giao dịch để dự báo chính xác hơn."
                if days > 0
                else "Chưa có giao dịch nào. Khai nghĩa vụ hoặc nhập giao dịch để có dự báo."
            ),
            [{"kind": "open_obligations", "label": "Khai nghĩa vụ"}, _SNOOZE, _MUTE],
        )
    return None


def _has_money(jars: Iterable[Mapping[str, Any]]) -> bool:
    """Có ít nhất một hũ người dùng còn tiền (tài khoản 0 ₫ thì không cảnh báo cạn: lỗi P12-08)."""
    return any(vnd(j["balance_vnd"]) > 0 for j in jars)


# =====================================================================================================
# Phase 5 (FR13): cổng giá trị của bản tin chủ động
# =====================================================================================================
#: Phần trong ngày theo giờ địa phương [bắt đầu, kết thúc) dùng cho "đừng nhắc buổi ...". Buổi đêm vắt qua nửa đêm.
DAY_PARTS: dict[str, tuple[tuple[int, int], ...]] = {
    "sang": ((5, 11),),
    "trua": ((11, 13),),
    "chieu": ((13, 18),),
    "toi": ((18, 22),),
    "dem": ((22, 24), (0, 5)),
}
_NEGATED_REMIND_RE = re.compile(
    r"\b(?:dung|khong|tranh|ngung)\s+(?:\w+\s+){0,2}(?:nhac|bao|thong bao|gui|lam phien)\b"
)
#: buổi có dấu ("tối" khác "tôi"), hoặc không dấu nhưng phải có chữ "buoi" đứng trước cho khỏi nhầm
_PART_ACCENTED_RE = re.compile(r"\b(sáng|trưa|chiều|tối|đêm|khuya)\b")
_PART_FOLDED_RE = re.compile(r"\bbuoi (sang|trua|chieu|toi|dem)\b")
_PART_KEY = {"sáng": "sang", "trưa": "trua", "chiều": "chieu", "tối": "toi", "đêm": "dem", "khuya": "dem"}


@dataclass(frozen=True)
class NudgePreferences:
    """Sở thích về bản tin của MỘT người dùng (đã chuẩn hóa thành dữ liệu, không phải câu chữ). `quiet_hours`: các khoảng giờ địa
    phương [bắt đầu, kết thúc) không hiện bản tin."""

    quiet_hours: tuple[tuple[int, int], ...] = ()

    def is_quiet(self, hour: int) -> bool:
        return any(start <= hour < end for start, end in self.quiet_hours)


NO_PREFERENCES = NudgePreferences()


class NudgePreferenceSource(Protocol):
    """ĐIỂM MÓC cho bộ nhớ dài hạn (luồng p5-memory): nhận `user_id` (`sub`), trả sở thích bản tin của người đó. Cài bằng cách
    gắn một đối tượng có phương thức này vào thuộc tính `nudge_preferences` của `LedgerService` (`GET /nudges/today` đọc nó; vắng thì
    không có sở thích nào). Cách dựng gợi ý: đọc các bản ghi `preference` của người dùng rồi `preferences_from_texts`. Lỗi hay chậm
    khi đọc bộ nhớ thì nguồn nên trả `NO_PREFERENCES` (`read_preferences` cũng tự nuốt lỗi): bản tin vẫn chạy."""

    def nudge_preferences(self, user_id: str) -> NudgePreferences: ...


def preferences_from_texts(texts: Iterable[str]) -> NudgePreferences:
    """Dựng `NudgePreferences` từ các câu sở thích người dùng đã nói (ví dụ bản ghi `preference` của AgentCore Memory): câu có lời phủ
    định ("đừng", "không", "tránh") cộng từ nhắc ("nhắc", "báo", "thông báo") cộng một buổi (sáng, trưa, chiều, tối, đêm) thì thêm
    giờ im lặng của buổi đó. Nội dung bộ nhớ là dữ liệu không tin cậy: kết quả chỉ có thể BỚT bản tin, không thêm hay đổi việc gì."""
    windows: list[tuple[int, int]] = []
    for raw in texts:
        original = unicodedata.normalize("NFC", str(raw)).lower()[:500]
        t = fold(original)
        if _NEGATED_REMIND_RE.search(t) is None:
            continue
        parts = [_PART_KEY[p] for p in _PART_ACCENTED_RE.findall(original)] + _PART_FOLDED_RE.findall(t)
        for part in parts:
            for w in DAY_PARTS[part]:
                if w not in windows:
                    windows.append(w)
    return NudgePreferences(quiet_hours=tuple(sorted(windows)))


def read_preferences(source: NudgePreferenceSource | None, user_id: str) -> NudgePreferences:
    """Đọc sở thích qua điểm móc; không có nguồn hoặc nguồn lỗi thì không có sở thích nào."""
    if source is None:
        return NO_PREFERENCES
    try:
        prefs = source.nudge_preferences(user_id)
    except Exception:
        return NO_PREFERENCES
    return prefs if isinstance(prefs, NudgePreferences) else NO_PREFERENCES


@dataclass(frozen=True)
class GateConfig:
    """Ngưỡng của cổng giá trị (điểm cùng đơn vị với `threshold`, mặc định 1). Giá trị do dự án chọn, chưa hiệu chỉnh trên người
    dùng thật. Điểm từng loại (`gather_candidates`): hũ thiết yếu hụt 1 + số ngày từ lúc cạn tới kỳ lương / 7 (sát chỉ 0,5); nghĩa vụ
    1 + phần thiếu / số phải trả (đủ tiền thì 0); lộ trình đề xuất mới 1,5; hỏi gộp 1 + 0,1 cho mỗi giao dịch thêm; điểm chống chịu
    số nhóm bị tụt; nhận xét hành vi 1 khi chưa nhắc trong `behavior_repeat_days` ngày."""

    thresholds: Mapping[str, float] = field(default_factory=lambda: dict.fromkeys(NUDGE_GATE_ORDER, 1.0))
    obligation_days: int = 3
    roadmap_max_age_days: int = 7
    behavior_repeat_days: int = 7
    #: "Ít nhắc loại này" trong từng này ngày gần nhất thì loại đó bị hạ một bậc
    demote_window_days: int = 30

    def threshold(self, kind: str) -> float:
        return float(self.thresholds.get(kind, 1.0))


DEFAULT_GATE_CONFIG = GateConfig()


@dataclass(frozen=True)
class GateCandidate:
    """Một việc có thể nhắc hôm nay. `title`, `body` do code dựng từ số liệu thật (không LLM)."""

    kind: str
    score: float
    title: str
    body: str
    status: str = "ok"  # trạng thái của thẻ: ok | tight | short
    jar_code: str | None = None
    value_vnd: int | None = None


@dataclass(frozen=True)
class GateDecision:
    chosen: GateCandidate | None
    #: `NudgeGate` của hợp đồng (rank, score, threshold, candidates, demoted) khi có bản tin
    gate: dict[str, Any] | None
    suppressed: list[dict[str, str]]


def effective_order(demoted: Iterable[str], order: Sequence[str] = NUDGE_GATE_ORDER) -> list[str]:
    """Thứ tự ưu tiên sau khi hạ bậc: mỗi loại bị hạ đổi chỗ với loại ngay sau nó (hạ ĐÚNG một bậc)."""
    out = list(order)
    for kind in [k for k in order if k in set(demoted)][::-1]:
        i = out.index(kind)
        if i + 1 < len(out):
            out[i], out[i + 1] = out[i + 1], out[i]
    return out


def select_nudge(
    candidates: Sequence[GateCandidate],
    *,
    demoted: Iterable[str] = (),
    config: GateConfig = DEFAULT_GATE_CONFIG,
) -> GateDecision:
    """Chọn tối đa MỘT việc: đi theo thứ tự ưu tiên đã hạ bậc, lấy ứng viên đầu tiên có điểm không dưới ngưỡng của loại đó (cùng
    loại nhiều ứng viên thì điểm cao hơn trước). Các ứng viên còn lại vào `suppressed` kèm lý do: `below_threshold` (chưa tới ngưỡng),
    `demoted` (vượt ngưỡng, xếp trước việc được chọn theo thứ tự gốc nhưng bị hạ bậc nên thua), `lower_rank` (có việc ưu tiên hơn)."""
    demoted_set = set(demoted)
    order = effective_order(demoted_set)
    rank_of = {k: i for i, k in enumerate(order)}
    base_rank = {k: i for i, k in enumerate(NUDGE_GATE_ORDER)}
    pool = sorted(
        (c for c in candidates if c.kind in rank_of),
        key=lambda c: (rank_of[c.kind], -c.score),
    )
    chosen = next((c for c in pool if c.score >= config.threshold(c.kind)), None)
    suppressed: list[dict[str, str]] = []
    seen: set[str] = set()
    for c in pool:
        if c is chosen or c.kind in seen:
            continue
        if c.score < config.threshold(c.kind):
            reason = "below_threshold"
        elif chosen is not None and c.kind in demoted_set and base_rank[c.kind] < base_rank[chosen.kind]:
            reason = "demoted"
        else:
            reason = "lower_rank"
        if chosen is not None and c.kind == chosen.kind:
            continue  # ứng viên cùng loại với việc được chọn: không phải một loại bị bỏ
        seen.add(c.kind)
        suppressed.append({"kind": c.kind, "reason": reason})
    gate = None
    if chosen is not None:
        gate = {
            "rank": rank_of[chosen.kind] + 1,
            "score": round(float(chosen.score), 3),
            "threshold": config.threshold(chosen.kind),
            "candidates": max(1, min(len(pool), 20)),
        }
        if chosen.kind in demoted_set:
            gate["demoted"] = True
    return GateDecision(chosen=chosen, gate=gate, suppressed=suppressed[:10])


# --- ứng viên: dựng từ số liệu đã đọc (thuần, không DB) -----------------------------------------------------------
_BAND_ORDER = ("weak", "fair", "strong")
_BAND_LABEL = {"weak": "Yếu", "fair": "Vừa", "strong": "Tốt"}


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def gather_candidates(
    *,
    today: date,
    jars: Sequence[Mapping[str, Any]],
    forecasts: Mapping[str, Mapping[str, Any]],
    essential_jar_codes: Iterable[str],
    avg_daily_spend: Mapping[str, int],
    obligations: Sequence[Mapping[str, Any]],
    roadmap: Mapping[str, Any] | None,
    review_ask: Mapping[str, Any] | None,
    resilience_today: Mapping[str, Any] | None,
    resilience_before: Mapping[str, Any] | None,
    behavior: Mapping[str, Any] | None,
    recent_kinds: Mapping[str, int],
    config: GateConfig = DEFAULT_GATE_CONFIG,
) -> list[GateCandidate]:
    """Ứng viên của cổng, mỗi loại theo đúng thứ tự `NUDGE_GATE_ORDER`:

    1. `runout_warning`: hũ THIẾT YẾU (mã trong `essential_jar_codes`) mà dự báo mới nhất hụt (cạn trước kỳ lương) hoặc sát;
       `value_vnd` ước tính phần hụt = chi trung bình mỗi ngày của hũ x số ngày từ lúc cạn tới kỳ lương.
    2. `obligation_due`: nghĩa vụ đang hoạt động đến hạn trong `obligation_days` ngày mà hũ trả không đủ; `value_vnd` là phần thiếu.
    3. `roadmap_proposed`: có phiên bản lộ trình `proposed` lập trong `roadmap_max_age_days` ngày gần nhất.
    4. `review_needed`: câu hỏi gộp hôm nay còn `open` và có giao dịch; `value_vnd` là tổng chờ chọn hũ.
    5. `resilience_drop`: nhóm điểm chống chịu hôm nay thấp hơn hôm qua.
    6. `behavior_insight`: hồ sơ hành vi sẵn sàng và loại này chưa được nhắc trong `behavior_repeat_days` ngày (`recent_kinds`).
    """
    out: list[GateCandidate] = []
    essential = set(essential_jar_codes)
    by_code = {j["code"]: j for j in jars}
    funded = _has_money(jars)

    for code, f in forecasts.items():
        jar = by_code.get(code)
        if not funded or jar is None or code not in essential or f.get("status") not in ("short", "tight"):
            continue
        payday = to_date(f.get("payday_date"))
        runout = to_date(f.get("runout_date"))
        name, balance = jar["name"], format_vnd(vnd(jar["balance_vnd"]))
        if f["status"] == "short" and runout is not None and payday is not None and runout < payday:
            gap = (payday - runout).days
            value = int(avg_daily_spend.get(code, 0)) * gap
            empty = vnd(jar["balance_vnd"]) <= 0
            out.append(
                GateCandidate(
                    kind="runout_warning",
                    score=1.0 + min(gap, 28) / 7,
                    title=_clip(f"Hũ {name} đã hết tiền" if empty else f"Hũ {name} dự kiến cạn ngày {_dm(runout)}", 80),
                    body=_clip(
                        f"Còn {(payday - today).days} ngày nữa mới tới kỳ lương {_dm(payday)}."
                        if empty
                        else f"Còn {balance}, cạn xong còn {gap} ngày nữa mới tới kỳ lương {_dm(payday)}.",
                        200,
                    ),
                    status="short",
                    jar_code=code,
                    value_vnd=value or None,
                )
            )
        elif payday is not None:
            out.append(
                GateCandidate(
                    kind="runout_warning",
                    score=0.5,
                    title=_clip(f"Hũ {name} đang sát số dư", 80),
                    body=_clip(f"Còn {balance}, dự kiến còn rất ít trước kỳ lương {_dm(payday)}.", 200),
                    status="tight",
                    jar_code=code,
                )
            )

    for ob in obligations:
        if ob.get("status", "active") != "active":
            continue
        due = to_date(ob.get("due_date"))
        if due is None or not 0 <= (due - today).days <= config.obligation_days:
            continue
        amount = vnd(ob["amount_vnd"])
        pay = by_code.get(ob.get("pay_jar_code") or "")
        balance = vnd(pay["balance_vnd"]) if pay else 0
        short = max(amount - max(balance, 0), 0)
        if amount <= 0:
            continue
        where = f", hũ {pay['name']} còn {format_vnd(balance)}" if pay else ""
        out.append(
            GateCandidate(
                kind="obligation_due",
                score=(1.0 + short / amount) if short > 0 else 0.0,
                title=_clip(f"{ob['name']} đến hạn ngày {_dm(due)}", 80),
                body=_clip(
                    f"Cần {format_vnd(amount)}{where}"
                    + (f", còn thiếu {format_vnd(short)}." if short > 0 else ", đủ để trả."),
                    200,
                ),
                status="short" if short > 0 else "ok",
                jar_code=pay["code"] if pay else None,
                value_vnd=short or None,
            )
        )

    if roadmap is not None and roadmap.get("status") == "proposed":
        made = to_date(roadmap.get("app_date"))
        if made is not None and 0 <= (today - made).days <= config.roadmap_max_age_days:
            version = int(roadmap["version"])
            reason = str(roadmap.get("reason_text") or "").strip()
            body = f"Bản đề xuất phiên bản {version}: {reason}" if reason else f"Bản đề xuất phiên bản {version} đã sẵn sàng để bạn so sánh."
            out.append(
                GateCandidate(
                    kind="roadmap_proposed",
                    score=1.5,
                    title="Lộ trình mới chờ bạn chọn",
                    body=_clip(body, 200),
                    status="tight",
                )
            )

    if review_ask is not None and review_ask.get("status") == "open" and int(review_ask.get("item_count") or 0) > 0:
        n = int(review_ask["item_count"])
        total = vnd(review_ask.get("pending_total_vnd") or 0)
        out.append(
            GateCandidate(
                kind="review_needed",
                score=1.0 + 0.1 * min(n - 1, 9),
                title=_clip(f"{n} giao dịch chờ bạn chọn hũ", 80),
                body=_clip(f"Tổng {format_vnd(total)}; trả lời một lần là xong cho hôm nay.", 200),
                status="ok",
                value_vnd=total or None,
            )
        )

    if resilience_today is not None and resilience_before is not None:
        now_band, before_band = resilience_today.get("band"), resilience_before.get("band")
        if now_band in _BAND_ORDER and before_band in _BAND_ORDER:
            drop = _BAND_ORDER.index(before_band) - _BAND_ORDER.index(now_band)
            if drop > 0:
                out.append(
                    GateCandidate(
                        kind="resilience_drop",
                        score=float(drop),
                        title=_clip(f"Điểm chống chịu tụt xuống nhóm {_BAND_LABEL[now_band]}", 80),
                        body=_clip(
                            f"Từ {int(resilience_before['score'])} xuống {int(resilience_today['score'])} điểm so với hôm qua.",
                            200,
                        ),
                        status="tight",
                    )
                )

    if behavior is not None and behavior.get("ready") and behavior.get("insights"):
        top = behavior["insights"][0]
        repeat = int(recent_kinds.get("behavior_insight", 0)) > 0
        out.append(
            GateCandidate(
                kind="behavior_insight",
                score=0.0 if repeat else 1.0,
                title="Nhận xét mới về thói quen chi tiêu",
                body=_clip(str(top["headline"]), 200),
                status="ok",
                jar_code=top.get("jar_code"),
            )
        )
    return out


# --- thẻ của bản tin ---------------------------------------------------------------------------------
_GATE_ACTIONS: dict[str, Callable[[str | None], list[dict[str, Any]]]] = {
    "runout_warning": lambda jar: [
        {"kind": "open_forecast", "label": "Xem dự báo", **({"jar_code": jar} if jar else {})},
        _SNOOZE,
        _MUTE,
    ],
    "obligation_due": lambda jar: [{"kind": "open_obligations", "label": "Xem nghĩa vụ"}, _SNOOZE, _MUTE],
    "roadmap_proposed": lambda jar: [{"kind": "open_roadmap", "label": "Xem lộ trình mới"}, _SNOOZE, _MUTE],
    "review_needed": lambda jar: [{"kind": "review_unclassified", "label": "Trả lời ngay"}, _SNOOZE, _MUTE],
    "resilience_drop": lambda jar: [{"kind": "open_resilience", "label": "Xem điểm chống chịu"}, _SNOOZE, _MUTE],
    "behavior_insight": lambda jar: [{"kind": "open_profile", "label": "Xem hồ sơ chi tiêu"}, _SNOOZE, _MUTE],
}
#: trạng thái của thẻ theo loại khi dòng `nudges` không giữ trạng thái (cột không có); hũ hụt lấy từ `gate_reason.status`
_GATE_STATUS = {
    "runout_warning": "tight",
    "obligation_due": "tight",
    "roadmap_proposed": "tight",
    "review_needed": "ok",
    "resilience_drop": "tight",
    "behavior_insight": "ok",
}
GATE_REASON_KEYS = ("rank", "score", "threshold", "candidates", "demoted")


def gate_card(
    nudge: Mapping[str, Any], *, as_of: datetime, app_date: date, source_tool: str = "rest:GET /nudges/today"
) -> ProactiveCardBlock:
    """Khối `proactive_card` của MỘT bản tin của cổng (dòng `nudges` đọc bằng `app_get_today_nudge`): cùng `kind`, `title`, `reason`
    với dòng, có `nudge_id` để "Để sau" và "Ít nhắc loại này" gửi phản hồi. `trace_id` là của lần chạy cổng (id thẻ ổn định qua các
    lần đọc, nên phản hồi ghi đúng một dòng `feedback`)."""
    kind = str(nudge["kind"])
    reason_json = nudge.get("gate_reason") or {}
    status = str(reason_json.get("status") or _GATE_STATUS.get(kind, "ok"))
    jar = nudge.get("jar_code")
    block = build_proactive_card(
        kind=kind,
        status=status,
        title=str(nudge["title"]),
        reason=str(nudge["body"]),
        actions=_GATE_ACTIONS[kind](jar),
        trace_id=str(nudge["trace_id"]),
        source_tool=source_tool,
        as_of=as_of,
        app_date=app_date,
        jar_code=jar,
    )
    wire = block_to_wire(block)
    wire["data"]["nudge_id"] = str(nudge["id"])  # `build_proactive_card` (phase 2) chưa nhận nudge_id: thêm rồi kiểm lại cả khối
    return ProactiveCardBlock.model_validate(wire)


def gate_reason_json(decision: GateDecision, *, status: str) -> dict[str, Any]:
    """Cột `nudges.gate_reason`: `NudgeGate` của hợp đồng, cộng trạng thái thẻ và danh sách loại bị bỏ (để `GET /nudges/today` trả
    `suppressed` mà không chạy lại cổng)."""
    assert decision.gate is not None
    return {**decision.gate, "status": status, "suppressed": list(decision.suppressed)}


SQL_TODAY_NUDGE = "SELECT * FROM app_get_today_nudge(CAST(:uid AS text), CAST(:d AS date))"
SQL_NUDGE_STATS = "SELECT * FROM app_nudge_outcome_stats(CAST(:uid AS text), CAST(:since AS date))"
SQL_INSERT_GATE_NUDGE = (
    "INSERT INTO nudges (id, user_id, kind, fire_on, created_app_date, jar_code, status, source, trace_id, value_vnd, gate_reason, "
    "title, body) VALUES (CAST(:id AS uuid), :uid, :kind, CAST(:d AS date), CAST(:d AS date), :jar_code, 'scheduled', 'system', "
    ":trace_id, CAST(:value AS numeric), CAST(:gate AS jsonb), :title, :body) "
    "ON CONFLICT (user_id, fire_on) WHERE source = 'system' AND status <> 'cancelled' DO NOTHING RETURNING id"
)


def insert_gate_nudge(
    db: Any,
    user_id: str,
    *,
    nudge_id: str,
    app_date: date,
    decision: GateDecision,
    trace_id: str,
) -> bool:
    """Ghi bản tin được chọn (tối đa một mỗi ngày: đã có bản tin của cổng hôm nay thì không ghi, trả False)."""
    c = decision.chosen
    assert c is not None and decision.gate is not None
    from decimal import Decimal

    with db.transaction(user_id) as tx:
        rows = tx.execute(
            SQL_INSERT_GATE_NUDGE,
            {
                "id": nudge_id,
                "uid": user_id,
                "kind": c.kind,
                "d": app_date,
                "jar_code": c.jar_code,
                "trace_id": trace_id,
                "value": Decimal(c.value_vnd) if c.value_vnd is not None else None,
                "gate": json.dumps(gate_reason_json(decision, status=c.status), ensure_ascii=False),
                "title": c.title,
                "body": c.body,
            },
        )
    return bool(rows)
