"""Người tư vấn (luồng K của phase 6): kiểm và phát lập luận có cấu trúc kèm một câu kết luận (khối `reasoning`).

Lập luận nằm trong CHÍNH lời gọi model đã có, không thêm lượt gọi nào: Analyst của what-if trả `Analysis.reasoning` và
`Analysis.conclusion`; planner lộ trình trả `AdvisedSketch.reasoning` và `.conclusion` (`roadmap_agent.py`). Model trả lập luận như DỮ
LIỆU (ba câu ngắn và mã căn cứ cho mỗi bước), không phải chuỗi suy nghĩ nội bộ; agent không bao giờ phát suy nghĩ thô của model.

Mã kiểm trước khi phát (mã quyết định, không tin model):

- Số: từng câu qua đúng bộ kiểm số của luồng (`NumericGrounding` với tập số của lượt ở what-if; bộ kiểm chặt `_grounding` của lộ
  trình). Bước có số không căn cứ bị BỎ (không trả lại cho model sửa, không tốn lượt gọi).
- Căn cứ: `tool:<tên>` chỉ hợp lệ khi tool đó trả OK trong lượt; `rule:<id>` chỉ khi luật đó đã được `check_suitability` xét (không
  phải `skipped`) cho phương án hoặc bước đã kiểm. Bước không còn căn cứ hợp lệ nào bị bỏ. Nhãn căn cứ do mã dựng.
- Kết luận: số có căn cứ; trỏ đúng phương án được gợi ý (what-if) hoặc một bước của bản đã lưu (lộ trình); nguồn cá nhân hóa khai
  trong `personal` phải có thật trong lượt (khối bộ nhớ khác rỗng, hồ sơ hành vi sẵn sàng), không thì bỏ cả câu.
- Nhất quán với kết quả đã lưu (#7, chạy sau các kiểm trên; `SavedResult`): hũ nhận bằng tên/mã hũ thật của lượt, luật bằng mã căn
  cứ bước đã khai, không đọc ý câu chữ. Bước trích một luật đã loại hũ nó nhắc (`rule_conflict`) hoặc nhắc hũ không có trong kết quả
  (`jar_mismatch`) bị bỏ; kết luận nhắc hũ ngoài kết quả, hoặc còn ít hơn số bước tối thiểu sau khi bỏ bước mâu thuẫn, thì bỏ cả khối
  (`settle`).

Không có lập luận (model không trả, hoặc mọi bước và kết luận bị bỏ) thì lượt chạy như cũ và không có khối `reasoning`. Công tắc
`AgentSettings.reasoning_switch` (SSM `agent/reasoning_enabled`) tắt thì không xin model lập luận và không có khối này.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from yofina_agent.tools import ToolKind, ToolOutcome
from yofina_core import blocks as B
from yofina_core.suitability import SuitabilityVerdict

if TYPE_CHECKING:
    from yofina_agent.schemas import ReasoningStepIn
    from yofina_agent.turn import Turn

log = logging.getLogger("yofina.agent.advisor")

#: Nhãn căn cứ của các tool đọc mà lập luận được dựa vào (tên ngắn -> nhãn người dùng thấy). Tool ghi và tool hạ tầng không ở đây.
TOOL_BASIS_LABELS: dict[str, str] = {
    "run_scenario": "Kết quả mô phỏng",
    "get_obligations": "Các khoản đến hạn",
    "get_forecast": "Dự báo của hũ",
    "get_fee_schedule": "Biểu phí Trả sau",
    "get_jar_balances": "Số dư các hũ",
    "get_behavior_profile": "Thói quen chi tiêu",
    "get_exchange_rate": "Tỷ giá",
    "list_scenarios": "Các khoản đang cân nhắc",
    "get_resilience_score": "Điểm chống chịu",
    "optimize_allocation": "Phương án phân bổ",
    "get_roadmap": "Lộ trình trước đó",
}

#: Tên các luật phù hợp (`gateway/tools/planner/rules/*.yaml`, trường `title`; test giữ khớp) để model chọn mã căn cứ `rule:<id>`
#: trước khi Verifier chạy `check_suitability`. Nhãn trong khối lấy từ kết quả `check_suitability` của chính lượt.
RULE_TITLES: dict[str, str] = {
    "obligations_first": "Nghĩa vụ trước",
    "emergency_before_investing": "Dự phòng trước đầu tư",
    "risk_within_tolerance": "Không vượt khẩu vị rủi ro",
    "no_borrow_to_spend": "Không khuyên vay để tiêu",
    "obligation_to_income": "Nghĩa vụ trên thu nhập",
    "source_jar_covers": "Hũ nguồn đủ tiền",
    "emergency_not_for_discretionary": "Giữ quỹ dự phòng cho việc gấp",
}

#: Số thói quen tối đa của hồ sơ hành vi đưa cho model (bản gọn, đầu danh sách là quan trọng nhất).
MAX_HABITS = 3

Context = Literal["what_if", "roadmap"]


@dataclass(frozen=True)
class Advice:
    """Lập luận ĐÃ KIỂM của một lượt: các bước và câu kết luận (có thể vắng một trong hai)."""

    context: Context
    steps: tuple[B.ReasoningStep, ...] = ()
    conclusion: B.ReasoningConclusion | None = None

    @property
    def empty(self) -> bool:
        return not self.steps and self.conclusion is None

    def texts(self) -> list[str]:
        """Chữ model viết trong lập luận (để lọc Guardrail đầu ra cùng phần chữ khác của lượt)."""
        out = [t for s in self.steps for t in (s.seen, s.why, s.effect)]
        return [*out, self.conclusion.text] if self.conclusion is not None else out


def tools_ok(outcomes: Iterable[ToolOutcome]) -> list[str]:
    """Tên ngắn của các tool đọc trả OK trong lượt, theo thứ tự gọi (căn cứ dùng được của lập luận)."""
    names = [o.name.split("___", 1)[-1] for o in outcomes if o.kind is ToolKind.OK]
    return [n for n in dict.fromkeys(names) if n in TOOL_BASIS_LABELS]


def basis_catalog(tool_names: Iterable[str]) -> list[dict[str, str]]:
    """Danh sách `<can_cu>` cho prompt: tool đã có kết quả trong lượt và các luật phù hợp, mỗi mục một mã và một tên."""
    out = [
        {"ma": f"tool:{t}", "ten": TOOL_BASIS_LABELS[t]}
        for t in dict.fromkeys(tool_names)
        if t in TOOL_BASIS_LABELS
    ]
    return out + [{"ma": f"rule:{rule}", "ten": title} for rule, title in RULE_TITLES.items()]


def checked_rules(verdicts: Iterable[SuitabilityVerdict]) -> dict[str, str]:
    """Luật đã được xét thật (pass, warn hoặc fail; không tính `skipped`) trong các phán quyết của lượt: rule_id -> nhãn của tool."""
    out: dict[str, str] = {}
    for v in verdicts:
        for c in v.checked:
            if c.outcome != "skipped":
                out.setdefault(c.rule_id, c.label)
    return out


def behavior_view(payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Bản gọn hồ sơ hành vi cho model (nhóm hành vi và vài câu thói quen do batch dựng, số trong câu đã kiểm lúc tính). Hồ sơ chưa
    sẵn sàng hoặc sai dạng thì None (lượt không có thói quen nào để cá nhân hóa)."""
    data = (payload or {}).get("data")
    if not isinstance(data, Mapping) or not data.get("ready"):
        return None
    habits = [
        {"kind": str(i["kind"]), "text": str(i["headline"])}
        for i in data.get("insights") or []
        if isinstance(i, Mapping) and i.get("headline") and i.get("kind")
    ][:MAX_HABITS]
    if not habits:
        return None
    segment = data.get("segment")
    out: dict[str, Any] = {"habits": habits}
    if isinstance(segment, Mapping) and segment.get("label"):
        out["segment"] = str(segment["label"])
    return out


@dataclass(frozen=True)
class SavedResult:
    """Kết quả ĐÃ LƯU (đã phát) của lượt mà lập luận phải khớp. Mọi trường là dữ liệu có cấu trúc do mã dựng từ kết quả tool, không
    đọc chữ của model.

    - `jar_names`: mã -> tên các hũ thật của lượt (`jar_rows`), để nhận ra hũ nào được nhắc trong chữ (`mentioned_jars`).
    - `step_jars`: các hũ một bước lập luận được nhắc tới (hũ có mặt trong kết quả).
    - `conclusion_jars`: các hũ câu kết luận được nhắc tới (what-if: hũ của kịch bản và của mọi phương án đã phát, cộng hũ mà nguồn cá
      nhân hóa có nói tới; lộ trình: như `step_jars`).
    - `rejected`: rule_id -> các hũ nguồn mà luật đó đã loại trong lượt (`rule_rejections`).
    """

    jar_names: Mapping[str, str]
    step_jars: frozenset[str]
    conclusion_jars: frozenset[str]
    rejected: Mapping[str, frozenset[str]] = field(default_factory=dict)


#: lý do bỏ một bước vì mâu thuẫn với kết quả đã lưu (mã ổn định để ghi log)
CONFLICT_REASONS: tuple[str, ...] = ("rule_conflict", "jar_mismatch")


def _jar_pattern(token: str) -> re.Pattern[str] | None:
    words = unicodedata.normalize("NFC", token).split()
    if not words:
        return None
    return re.compile(r"(?<!\w)" + r"\s+".join(map(re.escape, words)) + r"(?!\w)")


def mentioned_jars(text: str, jar_names: Mapping[str, str]) -> frozenset[str]:
    """Mã các hũ mà chữ nhắc tới, nhận bằng tên (hoặc mã) hũ THẬT của lượt: mẫu dựng từ dữ liệu hũ, không có danh sách từ khóa.

    So nguyên cụm từ và đúng chữ hoa như tên trong dữ liệu (model chép tên hũ từ danh sách hũ, "hũ Giải trí"): tên hũ tiếng Việt là danh
    từ chung, nên chữ thường ("dùng hũ khác", "khoản nghĩa vụ", "quỹ dự phòng") không tính là nhắc tới hũ "Khác", "Nghĩa vụ", "Dự
    phòng". Tên dài khớp trước, đoạn đã khớp không khớp lần hai ("Du lịch Đà Lạt" không bị tính thêm là "Du lịch")."""
    t = unicodedata.normalize("NFC", text or "")
    tokens = [(name, code) for code, name in jar_names.items()] + [
        (code, code) for code in jar_names
    ]
    taken: list[tuple[int, int]] = []
    found: set[str] = set()
    for token, code in sorted(tokens, key=lambda tc: -len(tc[0])):
        if (pattern := _jar_pattern(token)) is None:
            continue
        for m in pattern.finditer(t):
            if not any(m.start() < end and start < m.end() for start, end in taken):
                taken.append(m.span())
                found.add(code)
    return frozenset(found)


#: Trường mang mã hũ dạng chuỗi trong kết quả tool, phương án và bước lộ trình (`to_jar_code`: hũ nhận của bước lộ trình, có cả khi
#: bước không gắn hành động `move_between_jars`).
_JAR_KEYS = frozenset({"jar_code", "to_jar_code", "from_jar", "to_jar"})


def jar_codes(node: Any) -> set[str]:
    """Mọi mã hũ trong một kết quả có cấu trúc (đệ quy): `jar.code` và các trường `jar_code`, `to_jar_code`, `from_jar`, `to_jar`.
    Danh sách hũ trong tham số `save_jars` (khóa `code` trần) không tính: bước đổi tỷ lệ chia không phải bước "nói về" mọi hũ."""
    out: set[str] = set()
    if isinstance(node, Mapping):
        jar = node.get("jar")
        if isinstance(jar, Mapping) and isinstance(jar.get("code"), str):
            out.add(jar["code"])
        for key, value in node.items():
            if key in _JAR_KEYS and isinstance(value, str) and value:
                out.add(value)
            else:
                out |= jar_codes(value)
    elif isinstance(node, list):
        for item in node:
            out |= jar_codes(item)
    return out


def rule_rejections(
    judged: Iterable[tuple[str | None, SuitabilityVerdict]],
) -> dict[str, frozenset[str]]:
    """rule_id -> hũ nguồn của các đề xuất mà luật đó đã LOẠI (`fail`, mức block) trong lượt, mọi vòng kiểm. `judged` là các cặp (hũ
    nguồn của đề xuất, phán quyết `check_suitability`); đề xuất không lấy tiền từ hũ nào không gắn được với hũ nên bỏ qua. Luật chỉ
    cảnh báo (`warn`) không loại phương án nên không tính."""
    out: dict[str, set[str]] = {}
    for jar, v in judged:
        if not jar:
            continue
        for c in v.checked:
            if c.outcome == "fail":
                out.setdefault(c.rule_id, set()).add(jar)
    return {rule: frozenset(jars) for rule, jars in out.items()}


def step_conflict(step: ReasoningStepIn, saved: SavedResult) -> str | None:
    """Lý do bước mâu thuẫn với kết quả đã lưu, hoặc None:

    - `rule_conflict`: bước khai căn cứ `rule:<id>` mà luật đó đã loại đề xuất lấy tiền từ một hũ bước nhắc tới (ví dụ trích "Hũ nguồn
      đủ tiền" khi nói hũ mà chính luật đó bác là đủ). Mã không đọc được bước khen hay chê hũ đó, nên bước nhắc hũ bị luật mình trích
      loại đều bị bỏ.
    - `jar_mismatch`: bước nhắc một hũ không có trong kết quả (`step_jars`)."""
    jars: set[str] = set()
    for text in (step.seen, step.why, step.effect):
        jars |= mentioned_jars(text, saved.jar_names)
    cited = {key.split(":", 1)[1] for key in step.basis if key.startswith("rule:")}
    if any(jars & saved.rejected.get(rule, frozenset()) for rule in cited):
        return "rule_conflict"
    if jars - saved.step_jars:
        return "jar_mismatch"
    return None


def verify_steps(
    steps: Sequence[ReasoningStepIn],
    *,
    grounded: Callable[[str], bool],
    tools: Iterable[str],
    rules: Mapping[str, str],
    saved: SavedResult | None = None,
) -> tuple[list[B.ReasoningStep], dict[str, int]]:
    """Các bước giữ được (đánh lại `s1`, `s2`...) và số bước bị bỏ theo lý do (`grounding`, `basis`, rồi `rule_conflict`,
    `jar_mismatch` khi có `saved`: kiểm nhất quán với kết quả đã lưu chạy SAU kiểm số và căn cứ)."""
    usable_tools = set(tools)
    kept: list[B.ReasoningStep] = []
    dropped = {"grounding": 0, "basis": 0, **dict.fromkeys(CONFLICT_REASONS, 0)}
    seen_texts: set[str] = set()
    for s in steps:
        if len(kept) >= B.REASONING_MAX_STEPS:
            break
        texts = (s.seen.strip(), s.why.strip(), s.effect.strip())
        if not all(texts) or not all(grounded(t) for t in texts):
            dropped["grounding"] += 1
            continue
        basis: list[B.ReasoningBasis] = []
        for key in dict.fromkeys(s.basis):
            kind, ref = key.split(":", 1)
            if kind == "tool" and ref in usable_tools and ref in TOOL_BASIS_LABELS:
                basis.append(B.ReasoningBasis(kind="tool", ref=ref, label=TOOL_BASIS_LABELS[ref]))
            elif kind == "rule" and ref in rules:
                basis.append(B.ReasoningBasis(kind="rule", ref=ref, label=rules[ref][:60]))
        if not basis:
            dropped["basis"] += 1
            continue
        if saved is not None and (conflict := step_conflict(s, saved)) is not None:
            dropped[conflict] += 1
            continue
        if texts[0] in seen_texts:  # cùng một điều nói hai lần
            continue
        seen_texts.add(texts[0])
        kept.append(
            B.ReasoningStep(
                step_id=f"s{len(kept) + 1}",
                seen=texts[0],
                why=texts[1],
                effect=texts[2],
                basis=basis[:4],
            )
        )
    return kept, dropped


def verify_conclusion(
    text: str | None,
    personal: Iterable[str],
    *,
    grounded: Callable[[str], bool],
    target_ok: bool,
    has_memory: bool,
    has_behavior: bool,
    option_id: str | None = None,
    step_id: str | None = None,
    saved: SavedResult | None = None,
) -> tuple[B.ReasoningConclusion | None, str]:
    """(kết luận đã kiểm hoặc None, lý do để ghi log: `kept`, `none`, `grounding`, `target`, `personal`, `jar_mismatch`).

    `jar_mismatch` (chỉ khi có `saved`, kiểm sau cùng): câu nhắc một hũ ngoài `saved.conclusion_jars`, tức mâu thuẫn với kết quả đã
    lưu; người gọi bỏ cả khối (`settle`)."""
    if text is None or not text.strip():
        return None, "none"
    clean = text.strip()
    if not grounded(clean):
        return None, "grounding"
    if not target_ok:
        return None, "target"
    sources = list(dict.fromkeys(personal))
    if ("memory" in sources and not has_memory) or ("behavior" in sources and not has_behavior):
        return None, "personal"
    if saved is not None and mentioned_jars(clean, saved.jar_names) - saved.conclusion_jars:
        return None, "jar_mismatch"
    return (
        B.ReasoningConclusion(
            text=clean[:240],
            option_id=option_id,
            step_id=step_id,
            personal=sources or None,  # type: ignore[arg-type]
        ),
        "kept",
    )


def settle(
    context: Context,
    steps: Sequence[B.ReasoningStep],
    conclusion: B.ReasoningConclusion | None,
    dropped: Mapping[str, int],
    conclusion_reason: str,
    *,
    min_steps: int,
) -> tuple[Advice, str]:
    """Khối cuối sau kiểm nhất quán, và mã của khối để ghi log (`kept`, `conclusion_conflict`, `too_few_steps`).

    Bỏ CẢ khối khi câu kết luận mâu thuẫn với kết quả đã lưu, hoặc khi đã bỏ bước vì mâu thuẫn mà còn ít hơn `min_steps` bước (số
    bước tối thiểu của khối): phần còn lại không đủ để thành một lập luận đáng tin. Không bước nào bị bỏ vì mâu thuẫn thì giữ như cũ."""
    if conclusion_reason == "jar_mismatch":
        return Advice(context=context), "conclusion_conflict"
    if any(dropped.get(reason, 0) for reason in CONFLICT_REASONS) and len(steps) < min_steps:
        return Advice(context=context), "too_few_steps"
    return Advice(context=context, steps=tuple(steps), conclusion=conclusion), "kept"


def log_advice(
    context: Context,
    steps_in: int,
    kept: int,
    dropped: Mapping[str, int],
    conclusion: str,
    block: str = "kept",
) -> None:
    """Một dòng JSON mỗi lượt có lập luận (chỉ số đếm và mã lý do, không chữ, không tiền) để đo trên Runtime. `block` là mã của khối
    sau kiểm nhất quán (`settle`): `kept`, `conclusion_conflict`, `too_few_steps`."""
    log.info(
        json.dumps(
            {
                "event": "advisor_reasoning",
                "context": context,
                "steps_in": steps_in,
                "steps_kept": kept,
                "dropped_grounding": dropped.get("grounding", 0),
                "dropped_basis": dropped.get("basis", 0),
                "dropped_rule_conflict": dropped.get("rule_conflict", 0),
                "dropped_jar_mismatch": dropped.get("jar_mismatch", 0),
                "conclusion": conclusion,
                "block": block,
            }
        )
    )


def emit(turn: Turn, advice: Advice | None) -> None:
    """Phát dần khối `reasoning`: mỗi bước thêm một bản `complete: false` (cùng id, bản sau thay bản trước), bản cuối `complete:
    true` có đủ bước và kết luận. Không có gì để phát thì không phát khối nào."""
    if advice is None or advice.empty:
        return
    steps = list(advice.steps)

    def one(upto: int, *, complete: bool) -> None:
        data = B.ReasoningData(
            context=advice.context,
            complete=complete,
            steps=steps[:upto],
            conclusion=advice.conclusion if complete else None,
        )
        turn.emit_block(
            B.build_reasoning(
                data=data,
                trace_id=turn.trace_id,
                source_tool="agent",
                as_of=turn.d.now(),
                app_date=turn.block_app_date(),
            )
        )

    for upto in range(1, len(steps)):
        one(upto, complete=False)
    one(len(steps), complete=True)


__all__ = [
    "CONFLICT_REASONS",
    "RULE_TITLES",
    "TOOL_BASIS_LABELS",
    "Advice",
    "SavedResult",
    "basis_catalog",
    "behavior_view",
    "checked_rules",
    "emit",
    "jar_codes",
    "log_advice",
    "mentioned_jars",
    "rule_rejections",
    "settle",
    "step_conflict",
    "tools_ok",
    "verify_conclusion",
    "verify_steps",
]
