"""Nạp lộ trình seed của persona khi đặt lại demo (`POST /demo/reset`, phase 4 N4): `data/personas/roadmaps/<persona>.json`.

Với `minh`: v1 `superseded`, v2 `active` (sửa một bước), để màn So với bản cũ có hai bản. Seed KHÔNG có dấu hiệu đổi hành vi hay bản đề
xuất (issue #22): bản `behavior_changed` của cảnh 4 do bộ phát hiện thật tạo sau khi người dùng nạp sao kê; một dấu hiệu `confirmed`
cài sẵn sẽ làm batch đêm bỏ qua hũ đó. Phiên bản seed có lý do `behavior_changed` bị từ chối (`ROADMAP_INVALID`, thiếu dấu hiệu).

Không có đường ghi tắt: mỗi phiên bản đi qua đúng các bước của đường thật (chạy luật suitability cho TỪNG bước bằng `yofina_planner`,
`app_save_roadmap` để tính phiên bản và trạng thái, quyết định từng bước bằng `app_set_roadmap_step_state`, sửa một bước bằng cùng hàm
`apply_step_edit` của REST). Lộ trình seed vi phạm luật suitability (vì persona đổi) thì đặt lại demo báo `ROADMAP_INVALID` thay vì lưu.

Số trong seed: số của persona (mục tiêu và hạn của hũ từ spec, số dư hũ từ sổ cái vừa nạp, chiếu mục tiêu theo mức dành mỗi tháng) hoặc dữ liệu
seed ghi rõ trong file (`nguon`). Mọi ngày trong file là số ngày kể từ ngày neo (ngày mô phỏng lúc đặt lại), nên không gắn với một ngày cụ thể.

Chạy TRONG transaction đặt lại (`LedgerRepo.reset_user`): ghi hỏng thì cả lần đặt lại rollback.

Ví demo (bộ hũ demo, issue #39) dùng cùng file seed của persona, mã hũ đổi theo `personas.six_jars.JAR_ALIASES` (`jar_aliases`).
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import fields
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.roadmap import status_for_new_version
from yofina_ledger import roadmap_logic as rl
from yofina_ledger.repo import SQL_JAR_VIEW
from yofina_ledger.roadmap_repo import SQL_GET_ROADMAP, save_in_tx, set_step_in_tx
from yofina_ledger.settings import LedgerSettings
from yofina_planner.facts import facts_from_rows
from yofina_planner.rules import cached_rules, rules_version

SQL_BALANCES = "SELECT code, balance_vnd FROM jars WHERE user_id = :uid"
#: số ngày kỳ tính tổng nghĩa vụ của luật `obligation_to_income` (mặc định của cấu hình ledger): bước lộ trình không thêm nghĩa vụ nên
#: luật đó bị bỏ qua và con số này không ảnh hưởng kết quả; lấy từ mặc định của cấu hình để không đặt thêm một số.
_WINDOW_DAYS = next(
    int(f.default) for f in fields(LedgerSettings) if f.name == "suitability_window_days"
)
DAYS_PER_MONTH = 30


def seed_path(persona: str) -> Path:
    import personas

    return Path(personas.__file__).resolve().parent / "roadmaps" / f"{persona}.json"


#: khóa mang mã hũ trong bước và tham số hành động của file seed
_JAR_KEYS = ("jar_code", "to_jar_code", "from_jar", "to_jar")


def _map_jars(node: Any, aliases: Mapping[str, str]) -> Any:
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k in _JAR_KEYS and isinstance(v, str):
                out[k] = aliases.get(v, v)
            elif k == "goal_monthly_plan_vnd":
                out[k] = {aliases.get(code, code): amount for code, amount in v.items()}
            else:
                out[k] = _map_jars(v, aliases)
        return out
    if isinstance(node, list):
        return [_map_jars(v, aliases) for v in node]
    return node


def load_seed(
    persona: str | None, *, jar_aliases: Mapping[str, str] | None = None
) -> dict[str, Any] | None:
    """Nội dung file seed của persona, hoặc None nếu persona không có lộ trình seed. `jar_aliases` (mã hũ của persona -> mã hũ của ví
    đã nạp, như bộ hũ demo `personas.six_jars.JAR_ALIASES`) đổi mã hũ trong mọi bước, hành động và mức dành cho mục tiêu: một file seed
    dùng cho cả ví persona lẫn ví demo, không có bản thứ hai để lệch."""
    if not persona or not persona.isidentifier():
        return None
    path = seed_path(persona)
    if not path.is_file():
        return None
    seed = json.loads(path.read_text(encoding="utf-8"))
    return _map_jars(seed, jar_aliases) if jar_aliases else seed


def project_goal(
    jar: dict[str, Any], balance_vnd: int, monthly_plan_vnd: int, today: date
) -> dict[str, Any]:
    """Chiếu một mục tiêu (hũ có `goal_vnd`) theo mức dành mỗi tháng của seed: ngày đạt dự kiến, kịp hạn hay không, thiếu bao nhiêu và mỗi
    tháng cần bao nhiêu để kịp. Tháng là 30 ngày. Đây là phép chiếu đơn giản chỉ để seed có số nhất quán (lộ trình thật lấy `goals` từ
    `optimize_allocation`, không tính ở đây)."""
    target = int(jar["goal_vnd"])
    goal_date = jar.get("goal_date")
    remaining = max(target - balance_vnd, 0)
    projected = today + timedelta(
        days=math.ceil(remaining * DAYS_PER_MONTH / monthly_plan_vnd) if remaining else 0
    )
    months_left = max(
        ((goal_date - today).days / DAYS_PER_MONTH) if goal_date else 1, 1 / DAYS_PER_MONTH
    )
    on_track = goal_date is None or projected <= goal_date
    out: dict[str, Any] = {
        "jar": {k: jar[k] for k in ("code", "name", "color_key", "icon_key")},
        "target_vnd": target,
        "projected_date": projected.isoformat(),
        "on_track": on_track,
        "shortfall_vnd": 0
        if on_track
        else max(math.ceil(remaining - monthly_plan_vnd * months_left), 1),
        "monthly_needed_vnd": math.ceil(remaining / months_left),
    }
    if goal_date is not None:
        out["target_date"] = goal_date.isoformat()
    return out


def _resolve_phases(raw: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    """Giai đoạn của file seed (ngày là số ngày từ ngày neo) -> dạng bản nháp (ngày ISO, `fire_on_day` thành `fire_on`)."""

    def iso(days: int) -> str:
        return (today + timedelta(days=int(days))).isoformat()

    phases = []
    for ph in raw:
        steps = []
        for st in ph["steps"]:
            s = {k: v for k, v in st.items() if k != "due_day"}
            if "due_day" in st:
                s["due_date"] = iso(st["due_day"])
            if s.get("action"):
                params = dict(s["action"]["params"])
                if "fire_on_day" in params:
                    params["fire_on"] = iso(params.pop("fire_on_day"))
                s["action"] = {"tool": s["action"]["tool"], "params": params}
            steps.append(s)
        phases.append(
            {
                **{k: v for k, v in ph.items() if k not in ("start_day", "end_day", "steps")},
                "start_date": iso(ph["start_day"]),
                "end_date": iso(ph["end_day"]),
                "steps": steps,
            }
        )
    return phases


def seed_roadmaps(
    tx: Any,
    user_id: str,
    *,
    persona: str | None,
    app_date: date,
    jars: list[dict[str, Any]],
    jar_aliases: Mapping[str, str] | None = None,
) -> int:
    """Nạp lộ trình seed của `persona` trong transaction `tx` (sau khi sổ cái và số dư hũ đã nạp). Trả số phiên bản đã nạp (0 nếu persona
    không có file seed). `jars` là danh sách hũ đã nạp (mã, tên, màu, biểu tượng, loại, mục tiêu); `jar_aliases` như `load_seed`."""
    seed = load_seed(persona, jar_aliases=jar_aliases)
    if seed is None:
        return 0
    meta = {j["code"]: j for j in jars}
    balances = {
        r["code"]: int(r["balance_vnd"]) for r in tx.execute(SQL_BALANCES, {"uid": user_id})
    }
    jar_kinds = {code: j["kind"] for code, j in meta.items()}
    rules = cached_rules()
    facts = facts_from_rows(
        today=app_date,
        user=tx.execute("SELECT * FROM app_get_user(:uid)", {"uid": user_id})[0],
        jars=[
            r
            # hũ kèm `purpose` (cùng hàm với `LedgerRepo.jar_view`): chỉ hũ `buffer` (hoặc hũ cũ `purpose` NULL theo quy tắc tương
            # thích) là quỹ dự phòng, hũ Đầu tư `long_term` thì không
            for r in tx.execute(SQL_JAR_VIEW, {"uid": user_id})
            if r["code"] is not None
        ],
        obligations=tx.execute(
            "SELECT * FROM app_list_obligations(CAST(:uid AS text), 'active', CAST(NULL AS date), 100)",
            {"uid": user_id},
        ),
        window_days=_WINDOW_DAYS,
    )
    basis = {**seed["basis"], "computed_at": _now_text(tx)}

    prev: dict[str, Any] | None = None  # bản vừa lưu: {version, plan, states, feasibility}
    saved_count = 0
    for v in seed["versions"]:
        has_active = prev is not None
        if "edit" in v:
            assert prev is not None
            e = v["edit"]
            plan, step, changes = rl.apply_step_edit(
                prev["plan"], e["step_id"], amount_vnd=e.get("amount_vnd"), due_date=None
            )
            violations, checked = rl.check_steps(
                plan["phases"], facts, rules, only_step=e["step_id"]
            )
            if violations:
                raise rl.violation_error(violations)
            step["checked_rules"] = checked[e["step_id"]] or step.get("checked_rules", [])
            if not step["checked_rules"]:
                step.pop("checked_rules")
            text, detail = rl.reason_for("step_edited", step_title=step["title"], changes=changes)
            states = {k: dict(s) for k, s in prev["states"].items()}
            states[e["step_id"]] = {
                "status": "accepted",
                "decided_at": _now_text(tx),
                "edited": True,
            }
            feasibility, flag_ref, based_on = prev["feasibility"], None, prev["version"]
        else:
            goals = [
                project_goal(meta[code], balances[code], int(plan_vnd), app_date)
                for code, plan_vnd in v.get("goal_monthly_plan_vnd", {}).items()
            ]
            # seed không có dấu hiệu đổi hành vi: bản `behavior_changed` thiếu `behavior_flag_id` nên `parse_draft` từ chối
            draft = rl.parse_draft(
                {
                    "reason_code": v["reason_code"],
                    "based_on_version": prev["version"] if prev else None,
                    "behavior_flag_id": None,
                    "feasibility": v["feasibility"],
                    "goals": goals,
                    "phases": _resolve_phases(v["phases"], app_date),
                    "alternatives": [],
                }
            )
            phases = rl.draft_phases(draft)
            goals = [g.model_dump(mode="json", exclude_none=True) for g in draft.goals]
            rl.validate_jar_refs(phases, goals, [], jar_kinds)
            violations, checked = rl.check_steps(phases, facts, rules)
            if violations:
                raise rl.violation_error(violations)
            plan = rl.build_plan(
                feasibility=draft.feasibility,
                goals=goals,
                phases=phases,
                alternatives=[],
                checked=checked,
                basis=basis,
            )
            text, detail = rl.reason_for(v["reason_code"])
            states = {}
            feasibility, flag_ref, based_on = (
                draft.feasibility,
                draft.behavior_flag_id,
                draft.based_on_version,
            )
        saved = save_in_tx(
            tx,
            user_id,
            reason_code=v["reason_code"],
            reason_text=text,
            reason_detail=detail,
            behavior_flag_id=flag_ref,
            based_on_version=based_on,
            feasibility=feasibility,
            app_date=app_date,
            plan=plan,
            rules_version=rules_version(rules),
            status=status_for_new_version(v["reason_code"], has_active),
            trace_id=None,
            step_states=states or None,
        )
        if int(saved["version"]) != int(v["version"]):
            raise YofinaError(
                ErrorCode.INTERNAL_ERROR,
                f"Lộ trình seed lệch số phiên bản (file {v['version']}, DB {saved['version']}).",
            )
        for step_id, decision in v.get("decisions", {}).items():
            set_step_in_tx(
                tx,
                user_id,
                version=int(saved["version"]),
                step_id=step_id,
                status=decision,
                edited=None,
            )
        row = tx.execute(
            SQL_GET_ROADMAP, {"uid": user_id, "version": int(saved["version"]), "which": "active"}
        )[0]
        prev = {
            "version": int(saved["version"]),
            "plan": row["plan"],
            "states": row["step_states"] or {},
            "feasibility": feasibility,
        }
        saved_count += 1
    return saved_count


def _now_text(tx: Any) -> str:
    """Giờ của DB (cùng nguồn với `now()` của hàm ghi) dạng RFC 3339 UTC."""
    row = tx.execute("SELECT now() AS ts")[0]
    return rl.iso_instant(row["ts"])
