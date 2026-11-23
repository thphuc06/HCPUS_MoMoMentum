"""Logic THUẦN của lộ trình (phase 4, F5): không DB, không đồng hồ hệ thống, không model. Dùng chung cho tool Gateway
(`planner___save_roadmap`, `planner___get_roadmap`), REST `/roadmap*` và seed persona.

- Dựng JSON `plan` của bảng `roadmaps` từ bản nháp (`RoadmapDraft`), đọc lại `RoadmapData` từ một dòng bảng (gộp trạng thái từng bước
  `step_states` phủ lên `plan`), so hai phiên bản (`RoadmapDiffData`), sửa một bước (không gọi model: đổi số, đổi chữ có số trong tiêu đề).
- Luật suitability cho TỪNG bước: bước nào vi phạm mức block thì không lưu (`ROADMAP_INVALID`). Cách đổi bước thành `Proposal` ở
  `proposal_for_step`. Bước lộ trình không biểu diễn được việc đầu tư (loại bước cố định ở hợp đồng) nên hai luật đầu tư (dự phòng trước
  đầu tư, khẩu vị rủi ro) luôn bị bỏ qua; thứ có hiệu lực thật là `obligations_first` (rút tiền khỏi hũ đang gánh nghĩa vụ thiết yếu).
- Lỗi nghiệp vụ trong hàm SQL `app_*` là `RAISE EXCEPTION 'MÃ: ...'`; `db_business_error` đổi chúng về `YofinaError`.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from typing import Any

from pydantic import ValidationError

from yofina_core.blocks import RoadmapData, RoadmapDiffData, format_instant
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.money import format_vnd
from yofina_core.roadmap import RoadmapDraft, RoadmapDraftStep, RoadmapJob, RoadmapVersionSummary
from yofina_core.suitability import Proposal, SuitabilityRule
from yofina_planner.engine import evaluate
from yofina_planner.facts import SuitabilityFacts

HEADLINE_MAX = 160
HEADLINE_TAIL_MAX = 120
REASON_TEXT_MAX = 160
#: lỗi nghiệp vụ mà hàm SQL của migration 0052 ném ra (tiền tố mã trước dấu hai chấm)
DB_ERROR_RE = re.compile(
    r"(ROADMAP_NOT_FOUND|ROADMAP_INVALID|ROADMAP_VERSION_CONFLICT|PROFILE_INCOMPLETE): ([^\r\n]*)"
)
#: câu tiếng Việt thay cho thông điệp DB khi Data API làm hỏng dấu (ký tự thay thế U+FFFD thay từng byte của chữ có dấu); chỉ dùng khi
#: thông điệp gốc không đọc được, nên nói chung cho cả mã
DB_ERROR_FALLBACK = {
    "ROADMAP_NOT_FOUND": "Không tìm thấy lộ trình hoặc phiên bản này.",
    "ROADMAP_INVALID": "Yêu cầu về lộ trình không hợp lệ.",
    "ROADMAP_VERSION_CONFLICT": "Lộ trình đã thay đổi hoặc bản này không còn ở trạng thái chờ chọn. Hãy đọc lại lộ trình rồi thử lại.",
    "PROFILE_INCOMPLETE": "Bạn chưa có hồ sơ để lập lộ trình.",
}
#: các loại bước kéo tiền khỏi `jar_code` sang `to_jar_code` (đối tượng của luật nghĩa vụ trước)
MONEY_MOVING_KINDS = ("set_aside", "pay_obligation")
STEP_CATEGORY = {
    "set_aside": "saving",
    "pay_obligation": "debt_payment",
    "cut_spending": "spending",
}
MAX_DIFF_CHANGES = 30


# --- lỗi từ DB -------------------------------------------------------------------------------------------------
def db_business_error(exc: BaseException) -> YofinaError | None:
    """`YofinaError` tương ứng nếu `exc` (hoặc nguyên nhân của nó) là lỗi nghiệp vụ do hàm SQL `app_*` ném; không thì None.

    `DataApi` đổi lỗi lạ của boto3 thành `INTERNAL_ERROR` và giữ nguyên nhân ở `__cause__`; thông điệp gốc có dạng
    `ERROR: ROADMAP_NOT_FOUND: không có phiên bản này`."""
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        m = DB_ERROR_RE.search(str(cur))
        if m:
            code, text = m.group(1), m.group(2).strip()
            if "�" in text:  # Data API trả thông điệp có dấu bị hỏng mã hóa từng byte: dùng câu chuẩn của mã
                text = DB_ERROR_FALLBACK[code]
            return YofinaError(ErrorCode(code), text)
        cur = cur.__cause__ or cur.__context__
    return None


# --- định dạng -------------------------------------------------------------------------------------------------
def iso_instant(value: Any) -> str:
    """Thời điểm (datetime hoặc chuỗi ISO từ jsonb) -> RFC 3339 UTC hậu tố Z."""
    if isinstance(value, datetime):
        return format_instant(value)
    return format_instant(datetime.fromisoformat(str(value).replace("Z", "+00:00")))


def iso_date(value: Any) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)[:10]


def fmt_date(iso: str) -> str:
    """'2026-12-05' -> '05/12/2026'."""
    y, m, d = iso[:10].split("-")
    return f"{d}/{m}/{y}"


def _short_date(iso: str) -> str:
    return fmt_date(iso)[:5]


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# --- lý do của phiên bản (do code dựng từ sự kiện, không do LLM viết) ---------------------------------------------
def reason_for(
    code: str,
    *,
    flag: Mapping[str, Any] | None = None,
    jar_name: str | None = None,
    step_title: str | None = None,
    changes: Sequence[Mapping[str, str]] | None = None,
) -> tuple[str, list[dict[str, str]] | None]:
    """(`reason.text`, `reason.detail`) của một phiên bản. `flag` là dòng `behavior_flags` (cho `behavior_changed`), `step_title` và
    `changes` là bước và thay đổi của người dùng (cho `step_edited`)."""
    if code == "initial":
        return "Lộ trình đầu tiên của bạn.", None
    if code == "behavior_changed":
        if flag is None:
            raise YofinaError(ErrorCode.ROADMAP_INVALID, "Thiếu dấu hiệu đổi hành vi.")
        old, new = int(flag["old_weekly_vnd"]), int(flag["new_weekly_vnd"])
        name = jar_name or str(flag["jar_code"])
        weeks = flag.get("weeks_held")
        held = f" và giữ mức đó {int(weeks)} tuần" if weeks else ""
        verb = "tăng" if new > old else "giảm"
        to = "lên" if new > old else "xuống"
        label = _clip(f"Chi {name} mỗi tuần", 60)
        text = f"Chi {name} mỗi tuần {verb} từ {format_vnd(old)} {to} {format_vnd(new)}{held}."
        detail = [{"label": label, "before": format_vnd(old), "after": format_vnd(new)}]
        return _clip(text, REASON_TEXT_MAX), detail
    if code == "goal_changed":
        return "Mục tiêu của bạn đã thay đổi nên lộ trình được tính lại.", None
    if code == "income_changed":
        return "Thu nhập của bạn đã thay đổi nên lộ trình được tính lại.", None
    if code == "forecast_drift":
        return "Dự báo đã lệch so với lúc lập lộ trình nên lộ trình được tính lại.", None
    if code == "user_request":
        return "Bạn yêu cầu lập lại lộ trình.", None
    if code == "step_edited":
        title = _clip(step_title or "", 60)
        parts = ", ".join(f"{c['label'].lower()} {c['after']}" for c in (changes or ()))
        shown = f" ({parts})" if parts else ""
        text = f"Bạn đã sửa bước '{title}'{shown} và lưu thành phiên bản mới."
        return _clip(text, REASON_TEXT_MAX), [dict(c) for c in (changes or ())][:3] or None
    raise YofinaError(ErrorCode.ROADMAP_INVALID, "Lý do sinh lộ trình không hợp lệ.")


# --- bản nháp -> kiểm -> plan ----------------------------------------------------------------------------------
def parse_draft(args: Mapping[str, Any]) -> RoadmapDraft:
    """`RoadmapDraft` từ tham số tool (JSON). Sai kiểu hay thiếu trường: PARAMS_INVALID; vi phạm bất biến của hợp đồng (vd. `infeasible`
    mà không có đúng hai lựa chọn): ROADMAP_INVALID, kèm câu giải thích của bất biến đó."""
    clean = {k: v for k, v in args.items() if v is not None and v != ""}
    try:
        return RoadmapDraft.model_validate(clean, strict=False)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first.get("loc", ()))
        if first.get("type") == "value_error" and not first.get("loc"):
            msg = str(first.get("msg", "")).removeprefix("Value error, ")
            raise YofinaError(ErrorCode.ROADMAP_INVALID, f"Lộ trình không hợp lệ: {msg}.") from None
        raise YofinaError(
            ErrorCode.PARAMS_INVALID, f"Lộ trình không hợp lệ ({where or 'lộ trình'})."
        ) from None


def draft_phases(draft: RoadmapDraft) -> list[dict[str, Any]]:
    """Các giai đoạn của bản nháp dạng dict JSON (bỏ trường vắng)."""
    return [p.model_dump(mode="json", exclude_none=True) for p in draft.phases]


def iter_steps(
    phases: Iterable[Mapping[str, Any]],
) -> Iterable[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    for ph in phases:
        for st in ph["steps"]:
            yield ph, st


def validate_jar_refs(
    phases: Sequence[Mapping[str, Any]],
    goals: Sequence[Mapping[str, Any]],
    alternatives: Sequence[Mapping[str, Any]],
    jar_codes: Iterable[str],
) -> None:
    """Mọi mã hũ nhắc tới phải là hũ của người dùng (không phải hũ hệ thống), và `action` chuyển hũ phải khớp bước: nếu không,
    luật suitability kiểm một số tiền còn hành động thực hiện một số khác."""
    jars = set(jar_codes)

    def bad(msg: str) -> YofinaError:
        return YofinaError(ErrorCode.ROADMAP_INVALID, msg)

    for _ph, st in iter_steps(phases):
        sid = st["step_id"]
        for field in ("jar_code", "to_jar_code"):
            code = st.get(field)
            if code is not None and code not in jars:
                raise bad(f"Bước '{sid}' nhắc tới hũ '{code}' mà bạn không có.")
        action = st.get("action")
        if not action:
            continue
        params = action.get("params") or {}
        for key in ("from_jar", "to_jar", "jar_code"):
            code = params.get(key)
            if isinstance(code, str) and code not in jars:
                raise bad(f"Hành động của bước '{sid}' nhắc tới hũ '{code}' mà bạn không có.")
        if action.get("tool") == "move_between_jars":
            for key, field in (
                ("from_jar", "jar_code"),
                ("to_jar", "to_jar_code"),
                ("amount_vnd", "amount_vnd"),
            ):
                if key in params and st.get(field) is not None and params[key] != st[field]:
                    raise bad(
                        f"Hành động chuyển hũ của bước '{sid}' không khớp với bước ({key} khác {field})."
                    )
    for g in goals:
        code = (g.get("jar") or {}).get("code")
        if code not in jars:
            raise bad(f"Mục tiêu nhắc tới hũ '{code}' mà bạn không có.")
    for a in alternatives:
        code = a.get("jar_code")
        if code is not None and code not in jars:
            raise bad(f"Lựa chọn nhắc tới hũ '{code}' mà bạn không có.")


def proposal_for_step(step: Mapping[str, Any], start_date: str | None = None) -> Proposal:
    """Đổi một bước thành đề xuất cho `check_suitability`. Mọi bước là phương án do hệ thống đề xuất (`origin recommendation`, nên
    luật có thể nghiêm hơn lời người dùng tự nói). Chỉ bước kéo tiền khỏi một hũ (`set_aside`, `pay_obligation` có cả hũ nguồn
    `jar_code` và hũ nhận `to_jar_code`) mới có nguồn tiền là hũ đó; bước trả nghĩa vụ là khoản thiết yếu, bước `set_aside` thì không.

    `start_date` là ngày bắt đầu giai đoạn của bước, gắn vào đề xuất của bước kéo tiền: số tiền của bước là mức hằng tháng, nên bộ
    đánh giá chỉ so nó với số dư HIỆN CÓ của hũ nguồn khi giai đoạn bắt đầu trước kỳ lương kế; giai đoạn từ kỳ lương kế trở đi
    lấy tiền từ lương các kỳ sau. Ngày không có thật thì bỏ (đề xuất coi là làm ngay, kiểm chặt hơn)."""
    kind = str(step["kind"])
    moves = (
        kind in MONEY_MOVING_KINDS
        and step.get("jar_code")
        and step.get("to_jar_code")
        and step.get("amount_vnd")
    )
    fields: dict[str, Any] = {
        "kind": f"roadmap_{kind}",
        "amount_vnd": step.get("amount_vnd"),
        "funding_source": "jar" if moves else None,
        "jar_code": step.get("jar_code") if moves else None,
        "is_essential": True
        if kind == "pay_obligation"
        else (False if kind == "set_aside" else None),
        "category": STEP_CATEGORY.get(kind),
        "origin": "recommendation",
        "start_date": _real_date(start_date) if moves else None,
    }
    return Proposal.model_validate({k: v for k, v in fields.items() if v is not None}, strict=False)


def _real_date(value: Any) -> str | None:
    """Chuỗi `YYYY-MM-DD` nếu là một ngày có thật, không thì None."""
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value).isoformat() if len(value) == 10 else None
    except ValueError:
        return None


def check_steps(
    phases: Sequence[Mapping[str, Any]],
    facts: SuitabilityFacts,
    rules: tuple[SuitabilityRule, ...],
    *,
    only_step: str | None = None,
) -> tuple[list[tuple[str, str, str]], dict[str, list[str]]]:
    """Chạy bộ đánh giá suitability cho từng bước (hoặc riêng `only_step`), với ngày bắt đầu giai đoạn của bước. Trả (vi phạm mức
    block `(step_id, rule_id, message)`, luật đã thực sự kiểm theo từng bước: mọi luật không `skipped`)."""
    violations: list[tuple[str, str, str]] = []
    checked: dict[str, list[str]] = {}
    for ph, st in iter_steps(phases):
        if only_step is not None and st["step_id"] != only_step:
            continue
        verdict = evaluate(proposal_for_step(st, ph.get("start_date")), facts, rules)
        checked[st["step_id"]] = [c.rule_id for c in verdict.checked if c.outcome != "skipped"]
        violations.extend(
            (st["step_id"], v.rule_id, v.message)
            for v in verdict.violations
            if v.severity == "block"
        )
    return violations, checked


def violation_error(violations: Sequence[tuple[str, str, str]]) -> YofinaError:
    """`ROADMAP_INVALID` nêu bước đầu tiên vi phạm, mã luật và cách sửa (số bước khác nếu có)."""
    step_id, rule_id, message = violations[0]
    more = len({v[0] for v in violations}) - 1
    tail = f" (và {more} bước khác)" if more > 0 else ""
    return YofinaError(
        ErrorCode.ROADMAP_INVALID,
        f"Bước '{step_id}' vi phạm luật {rule_id}: {message} Hãy bỏ hoặc đổi bước này.{tail}",
    )


def plan_headline(
    feasibility: str,
    phases: Sequence[Mapping[str, Any]],
    goals: Sequence[Mapping[str, Any]],
) -> str:
    """Phần sau 'Lộ trình phiên bản N: ' (số phiên bản chỉ biết sau khi lưu nên ghép lúc đọc, xem `compose_headline`)."""
    steps = sum(len(p["steps"]) for p in phases)
    head = f"{len(phases)} giai đoạn, {steps} bước"
    if feasibility == "infeasible":
        names = [
            str((g["jar"] or {}).get("name") or g["jar"]["code"])
            for g in goals
            if not g["on_track"]
        ]
        who = f"mục tiêu {', '.join(names)}" if names else "mục tiêu"
        return _clip(f"{who} chưa khả thi, có 2 lựa chọn.", HEADLINE_TAIL_MAX)
    if feasibility == "relaxed":
        return _clip(f"{head}, kịp hạn sau khi điều chỉnh các hũ.", HEADLINE_TAIL_MAX)
    return _clip(f"{head}, kịp hạn." if goals else f"{head}.", HEADLINE_TAIL_MAX)


def compose_headline(version: int, tail: str) -> str:
    return _clip(f"Lộ trình phiên bản {version}: {tail}", HEADLINE_MAX)


def build_plan(
    *,
    feasibility: str,
    goals: Sequence[Mapping[str, Any]],
    phases: Sequence[Mapping[str, Any]],
    alternatives: Sequence[Mapping[str, Any]],
    checked: Mapping[str, Sequence[str]],
    basis: Mapping[str, Any],
) -> dict[str, Any]:
    """Cột `plan` (jsonb) của một phiên bản mới: bước ở `pending` (trạng thái thật nằm ở `step_states`), `checked_rules` là luật đã kiểm
    thật (thay giá trị agent tự khai), horizon là từ ngày bắt đầu sớm nhất tới ngày kết thúc muộn nhất."""
    out_phases: list[dict[str, Any]] = []
    for ph in phases:
        steps = []
        for st in ph["steps"]:
            s = {k: v for k, v in st.items() if k not in ("status", "decided_at", "edited")}
            rules = list(checked.get(s["step_id"], ()))
            if rules:
                s["checked_rules"] = rules
            else:
                s.pop("checked_rules", None)
            s["status"] = "pending"
            steps.append(s)
        out_phases.append({**{k: v for k, v in ph.items() if k != "steps"}, "steps": steps})
    return {
        "headline": plan_headline(feasibility, out_phases, goals),
        "horizon": {
            "start_date": min(p["start_date"] for p in out_phases),
            "end_date": max(p["end_date"] for p in out_phases),
        },
        "goals": copy.deepcopy(list(goals)),
        "phases": out_phases,
        "alternatives": copy.deepcopy(list(alternatives)),
        "basis": dict(basis),
    }


# --- đọc lại: dòng bảng -> RoadmapData ---------------------------------------------------------------------------
def counts_of(phases: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    steps = [s for _p, s in iter_steps(phases)]
    return {
        "pending": sum(s["status"] == "pending" for s in steps),
        "accepted": sum(s["status"] == "accepted" for s in steps),
        "rejected": sum(s["status"] == "rejected" for s in steps),
    }


def merged_phases(
    plan: Mapping[str, Any], step_states: Mapping[str, Any] | None
) -> list[dict[str, Any]]:
    """Giai đoạn của `plan` với trạng thái từng bước phủ lên: bước vắng trong `step_states` là `pending`."""
    states = step_states or {}
    phases: list[dict[str, Any]] = []
    for ph in plan["phases"]:
        steps = []
        for st in ph["steps"]:
            s = {k: v for k, v in st.items() if k not in ("status", "decided_at", "edited")}
            state = states.get(s["step_id"]) or {}
            status = state.get("status", "pending")
            s["status"] = status
            if status != "pending":
                s["decided_at"] = iso_instant(state["decided_at"])
                if state.get("edited"):
                    s["edited"] = True
            steps.append(s)
        phases.append({**{k: v for k, v in ph.items() if k != "steps"}, "steps": steps})
    return phases


def roadmap_data(row: Mapping[str, Any]) -> dict[str, Any]:
    """`RoadmapData` (dict JSON đã kiểm bằng Pydantic) của một dòng `app_get_roadmap`."""
    plan = row["plan"]
    phases = merged_phases(plan, row.get("step_states"))
    reason: dict[str, Any] = {"code": row["reason_code"], "text": row["reason_text"]}
    if row.get("reason_detail"):
        reason["detail"] = row["reason_detail"]
    if row.get("behavior_flag_id"):
        reason["behavior_flag_id"] = str(row["behavior_flag_id"])
    data: dict[str, Any] = {
        "roadmap_id": str(row["id"]),
        "version": int(row["version"]),
        "status": row["status"],
        "reason": reason,
        "created_at": iso_instant(row["created_at"]),
        "app_date": iso_date(row["app_date"]),
        "headline": compose_headline(int(row["version"]), str(plan["headline"])),
        "feasibility": row["feasibility"],
        "horizon": plan["horizon"],
        "goals": plan.get("goals", []),
        "phases": phases,
        "alternatives": plan.get("alternatives", []),
        "counts": counts_of(phases),
        "rules_version": row["rules_version"],
        "basis": plan["basis"],
    }
    if row.get("based_on_version") is not None:
        data["based_on_version"] = int(row["based_on_version"])
    return RoadmapData.model_validate(data).model_dump(mode="json", exclude_none=True)


def version_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    """Một dòng của `GET /roadmap/versions` (từ `app_list_roadmap_versions`)."""
    total, accepted, rejected = (
        int(row["steps_total"]),
        int(row["accepted_count"]),
        int(row["rejected_count"]),
    )
    data: dict[str, Any] = {
        "roadmap_id": str(row["id"]),
        "version": int(row["version"]),
        "status": row["status"],
        "reason_code": row["reason_code"],
        "reason_text": row["reason_text"],
        "created_at": iso_instant(row["created_at"]),
        "app_date": iso_date(row["app_date"]),
        "feasibility": row["feasibility"],
        "counts": {
            "pending": max(total - accepted - rejected, 0),
            "accepted": accepted,
            "rejected": rejected,
        },
    }
    if row.get("based_on_version") is not None:
        data["based_on_version"] = int(row["based_on_version"])
    return RoadmapVersionSummary.model_validate(data).model_dump(mode="json", exclude_none=True)


def job_data(row: Mapping[str, Any]) -> dict[str, Any]:
    """`RoadmapJob` (dict JSON) của một dòng `app_get_roadmap_job`."""
    data: dict[str, Any] = {
        "job_id": str(row["id"]),
        "status": row["status"],
        "trigger": row["trigger"],
        "progress": int(row["progress"]),
        "requested_at": iso_instant(row["requested_at"]),
    }
    if row.get("stage"):
        data["stage"] = row["stage"]
    if row.get("finished_at"):
        data["finished_at"] = iso_instant(row["finished_at"])
    if row.get("version") is not None:
        data["version"] = int(row["version"])
    if row.get("roadmap_id"):
        data["roadmap_id"] = str(row["roadmap_id"])
    if row.get("error_code"):
        data["error_code"] = row["error_code"]
    if row.get("error_message"):
        data["error_message"] = row["error_message"]
    return RoadmapJob.model_validate(data).model_dump(mode="json", exclude_none=True)


# --- sửa một bước (không gọi model) ------------------------------------------------------------------------------
def apply_step_edit(
    plan: Mapping[str, Any],
    step_id: str,
    *,
    amount_vnd: int | None,
    due_date: str | None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    """Bản sao của `plan` với MỘT bước đã sửa số tiền và/hoặc ngày; trả (plan mới, bước đã sửa, các thay đổi `{label, before, after}`).

    Số tiền (hoặc ngày) cũ trong TIÊU ĐỀ bước được thay bằng số mới (tiêu đề bước hay có chữ như 'Bù 150.000 ₫ mỗi tuần'); `reason`
    không đụng tới vì nó có thể nhắc cùng con số cho việc khác. Hành động gắn vào bước (`action.params.amount_vnd`, `fire_on`) đổi theo
    để thứ người dùng sẽ xác nhận khớp thứ họ vừa sửa. Bước không có số tiền (hoặc ngày) thì không sửa số tiền (hoặc ngày) được."""
    new_plan = copy.deepcopy(dict(plan))
    target: dict[str, Any] | None = None
    for ph in new_plan["phases"]:
        for st in ph["steps"]:
            if st["step_id"] == step_id:
                target = st
    if target is None:
        raise YofinaError(ErrorCode.ROADMAP_NOT_FOUND, "Không có bước này trong phiên bản.")
    changes: list[dict[str, str]] = []
    if amount_vnd is not None:
        old = target.get("amount_vnd")
        if old is None:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Bước này không có số tiền để sửa.")
        if old != amount_vnd:
            target["amount_vnd"] = amount_vnd
            target["title"] = target["title"].replace(format_vnd(old), format_vnd(amount_vnd))
            params = (target.get("action") or {}).get("params")
            if isinstance(params, dict) and "amount_vnd" in params:
                params["amount_vnd"] = amount_vnd
            changes.append(
                {"label": "Số tiền", "before": format_vnd(old), "after": format_vnd(amount_vnd)}
            )
    if due_date is not None:
        old_date = target.get("due_date")
        if old_date is None:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Bước này không có ngày để sửa.")
        if old_date != due_date:
            target["due_date"] = due_date
            title = target["title"].replace(fmt_date(old_date), fmt_date(due_date))
            target["title"] = title.replace(_short_date(old_date), _short_date(due_date))
            params = (target.get("action") or {}).get("params")
            if isinstance(params, dict) and "fire_on" in params:
                params["fire_on"] = due_date
            changes.append(
                {"label": "Ngày", "before": fmt_date(old_date), "after": fmt_date(due_date)}
            )
    if not changes:
        raise YofinaError(ErrorCode.PARAMS_INVALID, "Giá trị mới trùng giá trị hiện tại của bước.")
    try:
        RoadmapDraftStep.model_validate(
            {k: v for k, v in target.items() if k not in ("status", "decided_at", "edited")},
            strict=False,
        )
    except ValidationError:
        raise YofinaError(ErrorCode.PARAMS_INVALID, "Giá trị mới không hợp lệ.") from None
    return new_plan, target, changes


# --- so hai phiên bản --------------------------------------------------------------------------------------------
def diff_roadmaps(
    old: Mapping[str, Any], new: Mapping[str, Any], jar_names: Mapping[str, str]
) -> dict[str, Any]:
    """`RoadmapDiffData` (dict JSON) giữa hai `RoadmapData`: so theo `step_id`. Bước đổi nếu khác số tiền, ngày, hũ nguồn, hũ nhận,
    loại, giai đoạn, tên (chỉ khi không có khác biệt nào khác) hoặc lý do ("Vì sao")."""

    def index(data: Mapping[str, Any]) -> dict[str, tuple[str, Mapping[str, Any]]]:
        return {s["step_id"]: (p["phase_id"], s) for p in data["phases"] for s in p["steps"]}

    def jar(code: str | None) -> str:
        return jar_names.get(code or "", code or "")

    old_idx, new_idx = index(old), index(new)
    changed: list[dict[str, Any]] = []
    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    unchanged = 0
    for sid, (phase, step) in new_idx.items():
        if sid not in old_idx:
            added.append(
                {
                    "kind": "added",
                    "step_id": sid,
                    "phase_id": phase,
                    "title": step["title"],
                    "reason_after": step["reason"],
                }
            )
            continue
        old_phase, ostep = old_idx[sid]
        fields: list[dict[str, str]] = []

        def add(
            label: str, before: str | None, after: str | None, _f: list[dict[str, str]] = fields
        ) -> None:
            if before != after:
                _f.append(
                    {"label": label, "before": before or "(chưa có)", "after": after or "(bỏ)"}
                )

        add(
            "Số tiền",
            format_vnd(ostep["amount_vnd"]) if ostep.get("amount_vnd") else None,
            format_vnd(step["amount_vnd"]) if step.get("amount_vnd") else None,
        )
        add(
            "Ngày",
            fmt_date(ostep["due_date"]) if ostep.get("due_date") else None,
            fmt_date(step["due_date"]) if step.get("due_date") else None,
        )
        add(
            "Hũ nguồn",
            jar(ostep.get("jar_code")) or None,
            jar(step.get("jar_code")) or None,
        )
        add(
            "Hũ nhận",
            jar(ostep.get("to_jar_code")) or None,
            jar(step.get("to_jar_code")) or None,
        )
        add("Loại bước", ostep["kind"], step["kind"])
        add("Giai đoạn", old_phase, phase)
        if not fields:
            add("Tên bước", ostep["title"], step["title"])
        reason_changed = ostep["reason"] != step["reason"]
        if fields or reason_changed:
            item: dict[str, Any] = {
                "kind": "changed",
                "step_id": sid,
                "phase_id": phase,
                "title": step["title"],
            }
            if fields:
                item["fields"] = fields[:6]
            if reason_changed:
                item["reason_after"] = step["reason"]
            changed.append(item)
        else:
            unchanged += 1
    for sid, (phase, step) in old_idx.items():
        if sid not in new_idx:
            removed.append(
                {"kind": "removed", "step_id": sid, "phase_id": phase, "title": step["title"]}
            )
    changes = (changed + added + removed)[:MAX_DIFF_CHANGES]
    counts = {k: sum(c["kind"] == k for c in changes) for k in ("added", "removed", "changed")}
    counts["unchanged"] = unchanged
    n = len(changes)
    if n:
        headline = (
            f"Phiên bản {new['version']} khác phiên bản {old['version']} ở {n} bước: "
            f"thêm {counts['added']}, bỏ {counts['removed']}, đổi {counts['changed']}."
        )
    else:
        headline = f"Phiên bản {new['version']} không khác phiên bản {old['version']} ở bước nào."
    data = {
        "from_version": int(old["version"]),
        "to_version": int(new["version"]),
        "from_roadmap_id": old["roadmap_id"],
        "to_roadmap_id": new["roadmap_id"],
        "to_status": new["status"],
        "reason": new["reason"],
        "headline": headline,
        "changes": changes,
        "counts": counts,
        "can_adopt": new["status"] == "proposed",
    }
    return RoadmapDiffData.model_validate(data).model_dump(mode="json", exclude_none=True)
