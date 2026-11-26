"""Planner lộ trình gọi tool tính ngày `knowledge___resolve_date` cho ngày nhắc theo mốc (#39, việc nối 4 của đợt gộp).

Bước có `schedule_nudge` mà model điền `nudge_on_spec` (cùng định nghĩa với đầu vào tool, `schemas.date_spec_field`) thì mã gọi tool qua
hàm gọi tool sẵn có của lần lập và dùng đúng ngày tool trả làm ngày nhắc; mã không tự tính ngày. Ngày ngoài giai đoạn của bước, tool trả
lỗi hay đặc tả sai dạng thì bước vào vòng sửa sẵn có. Không có đặc tả thì như cũ: nhắc vào ngày cuối giai đoạn, không gọi tool. Model giả,
tool giả.
"""

from __future__ import annotations

from agent_helpers import FakeTools, fixture, mcp_ok
from test_roadmap_agent import args_for, build, outline, prompt, review, scripted_tools, step
from yofina_agent.roadmap_agent import StepOutline
from yofina_agent.tools import classify_result

TET_SPEC = {"anchor": "lunar_new_year", "before": True}


def _ok_check(_args):
    return classify_result("check_suitability", mcp_ok(fixture("check_suitability.ok.json")))


def _tools(**results):
    return scripted_tools(checks=_ok_check, **results)


def _resolve(name: str):
    return lambda _args: classify_result("resolve_date", mcp_ok(fixture(f"resolve_date.{name}.json")))


class _Targets(FakeTools):
    """FakeTools ghi thêm tên đủ của tool (có target) để thấy lời gọi đi qua target `knowledge`."""

    def __init__(self, inner: FakeTools) -> None:
        super().__init__()
        self.results, self.calls, self.full_names = inner.results, inner.calls, []

    async def call(self, name, arguments):
        self.full_names.append(name)
        return await super().call(name, arguments)


def _nudge(**changes):
    return review(step_id="nhac_truoc_tet", kind="remind", **changes)


def _saved_nudge(tools):
    (stored,) = args_for(tools, "save_roadmap")
    return next(s for phase in stored["phases"] for s in phase["steps"] if s["step_id"] == "nhac_truoc_tet")


def test_model_dien_dac_ta_ngay_nhac_thi_ma_goi_tool_va_dung_ngay_cua_tool():
    tools = _Targets(_tools(resolve_date=_resolve("ok")))
    result, client, _ = build(tools, outline(step(), _nudge(nudge_on_spec=TET_SPEC)))
    assert result.outcome.ok
    # đúng một lời gọi tool tính ngày, qua target knowledge, tham số là đặc tả model điền
    assert args_for(tools, "resolve_date") == [TET_SPEC]
    assert "knowledge___resolve_date" in tools.full_names
    nudge = _saved_nudge(tools)
    assert nudge["action"]["params"]["fire_on"] == nudge["due_date"] == "2027-02-05"
    # schema đầu ra của planner có trường đặc tả (cùng định nghĩa với đầu vào tool)
    schema = StepOutline.model_json_schema()["properties"]["nudge_on_spec"]
    assert "knowledge___resolve_date" in schema["anyOf"][0]["description"]
    assert prompt(client)["max_steps"] >= 2


def test_khong_co_dac_ta_thi_nhac_vao_ngay_cuoi_giai_doan_khong_goi_tool():
    tools = _tools()
    result, _, _ = build(tools, outline(step(), _nudge()))
    assert result.outcome.ok and not args_for(tools, "resolve_date")
    (stored,) = args_for(tools, "save_roadmap")
    (phase,) = stored["phases"]
    assert _saved_nudge(tools)["action"]["params"]["fire_on"] == phase["end_date"]


def test_ngay_ngoai_giai_doan_vao_vong_sua_va_ban_sua_khong_goi_lai_tool():
    """Tool trả 01/07/2028, sau ngày cuối kỳ: bước vào vòng sửa với lời nói rõ ngày và giai đoạn; bản sửa bỏ đặc tả thì nhắc vào ngày
    cuối giai đoạn, không gọi thêm tool."""
    tools = _tools(resolve_date=_resolve("ok_quarter"))
    spec = {"anchor": "start_of", "period": "quarter", "period_offset": 7}
    result, client, scope = build(tools, outline(step(), _nudge(nudge_on_spec=spec)), outline(step(), _nudge()))
    assert result.outcome.ok and scope.calls == 2
    feedback = prompt(client, 1)["feedback"]
    (issue,) = [f for f in feedback if f.get("step_id") == "nhac_truoc_tet"]
    assert issue["rule_id"] == "step_invalid" and "01/07/2028" in issue["message"] and "nudge_on_spec" in issue["message"]
    assert len(args_for(tools, "resolve_date")) == 1
    (stored,) = args_for(tools, "save_roadmap")
    (phase,) = stored["phases"]
    assert _saved_nudge(tools)["action"]["params"]["fire_on"] == phase["end_date"]


def test_tool_loi_thi_vao_vong_sua_theo_loi_cua_tool_va_cung_dac_ta_chi_goi_mot_lan():
    """Ngày đã qua (DATE_IN_PAST): lời của tool vào phản hồi sửa; bản sửa giữ nguyên đặc tả thì dùng lại kết quả đã có (không gọi lại),
    bước vẫn bị loại, các bước khác vẫn được lưu."""
    tools = _tools(resolve_date=_resolve("error_in_past"))
    draft = outline(step(), _nudge(nudge_on_spec=TET_SPEC))
    result, client, _ = build(tools, draft, draft, draft)
    assert result.outcome.ok
    assert len(args_for(tools, "resolve_date")) == 1
    message = fixture("resolve_date.error_in_past.json")["message"]
    (issue,) = [f for f in prompt(client, 1)["feedback"] if f.get("step_id") == "nhac_truoc_tet"]
    assert message in issue["message"]
    (stored,) = args_for(tools, "save_roadmap")
    assert all(s["step_id"] != "nhac_truoc_tet" for phase in stored["phases"] for s in phase["steps"])


def test_dac_ta_sai_dang_vao_vong_sua_khong_goi_tool():
    tools = _tools(resolve_date=_resolve("ok"))
    result, client, _ = build(
        tools, outline(step(), _nudge(nudge_on_spec={"anchor": "hom_qua"})), outline(step(), _nudge())
    )
    assert result.outcome.ok and not args_for(tools, "resolve_date")
    (issue,) = [f for f in prompt(client, 1)["feedback"] if f.get("step_id") == "nhac_truoc_tet"]
    assert "nudge_on_spec" in issue["message"]


def test_dac_ta_chi_dung_cho_buoc_co_schedule_nudge():
    """Bước chuyển tiền có đặc tả ngày nhắc (không có nghĩa với bước đó): bỏ qua, không gọi tool."""
    tools = _tools(resolve_date=_resolve("ok"))
    result, _, _ = build(tools, outline(step(nudge_on_spec=TET_SPEC), _nudge()))
    assert result.outcome.ok and not args_for(tools, "resolve_date")
