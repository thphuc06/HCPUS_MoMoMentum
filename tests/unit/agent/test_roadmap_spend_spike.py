"""Lập lộ trình với dữ kiện đợt chi tăng và luật giữ quỹ dự phòng (issue #39, chủ dự án chốt 26/11 tối). Không gọi model thật.

- Sàn của bộ tối ưu tính từ mức nền bền; một đợt chi tăng là DỮ KIỆN có cấu trúc trên dòng phân bổ của hũ (`recent_spend`: mức nền, mức gần
  đây, từ ngày nào, đã xác nhận đổi hành vi chưa, ngày dự báo hũ cạn nếu giữ nhịp). Planner thấy các trường đó (số và ngày dạng chữ, có
  trong `reason_numbers` để lý do chép được) và tự quyết nói gì, đề xuất gì; mã không chép câu.
- Luật giữ quỹ dự phòng cho việc gấp (`emergency_not_for_discretionary`, BR-42) mở rộng cho bước lộ trình chuyển tiền: bước lấy tiền quỹ dự
  phòng (cùng định nghĩa của luật: hũ `buffer`, hoặc hũ tiết kiệm cũ không mục tiêu khi ví chưa có hũ `buffer`) sang một hũ chi không thiết
  yếu (theo dòng phân bổ) vào vòng sửa sẵn có, trừ khi lời của chính người dùng (`user_request`) nói rõ muốn vậy và model ghi hũ nhận vào
  `buffer_to_jars` của bản phác thảo."""

from __future__ import annotations

from agent_helpers import fixture, mcp_ok
from test_roadmap_agent import (
    allocation_with,
    args_for,
    build,
    later_phase,
    outline,
    prompt,
    review,
    roadmap_events,
    scripted_tools,
    step,
)
from yofina_agent.roadmap_agent import ROADMAP_REQUEST_GUIDE, ROADMAP_SYSTEM
from yofina_agent.tools import classify_result

SPIKE_AN_UONG = {
    "an_uong": {
        "recent_spend": {
            "recent_monthly_vnd": 7_309_000, "keep_floor_vnd": 1_800_000, "baseline_monthly_vnd": 3_827_143, "unusually_high": True,
            "high_since": "2026-11-07", "change_confirmed": True, "runout_date": "2026-11-23",
        },
    },
    "giai_tri": {"recent_spend": {"recent_monthly_vnd": 409_000, "keep_floor_vnd": 195_000, "baseline_monthly_vnd": 390_000}},
}  # fmt: skip


def test_dot_chi_tang_vao_ngu_canh_planner_thanh_du_kien_co_cau_truc():
    tools = scripted_tools(allocation=allocation_with(SPIKE_AN_UONG))
    result, client, _ = build(tools, outline(review()))
    assert result.outcome.ok
    sent = prompt(client)
    eat = sent["context"]["allocation"]["lines"]["an_uong"]
    assert (eat["recent_spend_text"], eat["baseline_spend_text"]) == ("7.309.000 ₫", "3.827.143 ₫")
    assert eat["recent_spend_unusually_high"] is True and eat["behavior_change_confirmed"] is True
    assert (eat["high_since_text"], eat["runout_date_text"]) == ("07/11/2026", "23/11/2026")
    # số và ngày của dữ kiện là căn cứ cho chữ của bước (chép nguyên văn được)
    assert {"7.309.000 ₫", "3.827.143 ₫", "07/11/2026", "23/11/2026"} <= set(sent["reason_numbers"])
    # hũ chi đều: chỉ mức chi, không có khóa của đợt tăng
    fun = sent["context"]["allocation"]["lines"]["giai_tri"]
    assert "recent_spend_unusually_high" not in fun and "high_since_text" not in fun and "behavior_change_confirmed" not in fun
    # lời nhắc nói nghĩa của các trường mới, theo nguyên tắc
    for key in ("high_since_text", "behavior_change_confirmed", "runout_date_text"):
        assert key in ROADMAP_SYSTEM


def test_dot_chi_tang_chua_xac_nhan_khong_co_co_xac_nhan_va_ngay_vang_thi_khong_co_khoa():
    lines = {"an_uong": {"recent_spend": {**SPIKE_AN_UONG["an_uong"]["recent_spend"], "change_confirmed": False}}}
    del lines["an_uong"]["recent_spend"]["runout_date"]
    tools = scripted_tools(allocation=allocation_with(lines))
    _, client, _ = build(tools, outline(review()))
    eat = prompt(client)["context"]["allocation"]["lines"]["an_uong"]
    assert eat["recent_spend_unusually_high"] is True and "behavior_change_confirmed" not in eat
    assert "runout_date_text" not in eat and eat["high_since_text"] == "07/11/2026"


# --- giữ quỹ dự phòng cho việc gấp: bước chuyển tiền -----------------------------------------------------------------------------------
def from_buffer(to_jar="giai_tri", **changes):
    """Bước chuyển ngay từ Dự phòng (hũ tiết kiệm cũ không mục tiêu của fixture: quỹ dự phòng) sang `to_jar`, số tiền là phần tăng của
    Dự phòng trong phương án (600.000 ₫, vừa số dư 2.700.000 ₫)."""
    base = {"jar_code": "du_phong", "to_jar_code": to_jar, "amount_ref": {"jar_code": "du_phong", "field": "proposed_increase"}}
    return step("lay_du_phong", **{**base, **changes})


def test_buoc_lay_quy_du_phong_cho_hu_chi_khong_thiet_yeu_vao_vong_sua(caplog):
    caplog.set_level("WARNING", logger="yofina.agent.roadmap")
    tools = scripted_tools(checks=("ok", "ok"))
    result, client, scope = build(tools, outline(from_buffer(), review()), outline(review()))
    assert result.outcome.ok and scope.calls == 2
    (feedback,) = prompt(client, 1)["feedback"]
    assert feedback["rule_id"] == "emergency_not_for_discretionary" and feedback["step_id"] == "lay_du_phong"
    assert "Dự phòng" in feedback["message"] and "Giải trí" in feedback["message"]
    (rejected,) = roadmap_events(caplog, "roadmap_step_rejected")
    assert rejected["rule_id"] == "emergency_not_for_discretionary"
    # vòng sửa bằng mã, không tốn lượt check_suitability cho bước đó
    assert all(a["proposal"].get("jar_code") != "du_phong" for a in args_for(tools, "check_suitability"))
    saved = [s["step_id"] for p in args_for(tools, "save_roadmap")[0]["phases"] for s in p["steps"]]
    assert saved == ["giu_muc_tieu"]


def test_buoc_o_giai_doan_sau_va_buoc_tra_nghia_vu_cung_bi_chan():
    tools = scripted_tools(checks=("ok", "ok"))
    pay = from_buffer(kind="pay_obligation")
    _, client, _ = build(tools, later_phase(pay), outline(review()))
    (feedback,) = prompt(client, 1)["feedback"]
    assert feedback["rule_id"] == "emergency_not_for_discretionary"


def test_quy_du_phong_sang_hu_chi_thiet_yeu_hu_nghia_vu_hu_muc_tieu_thi_duoc():
    # Ăn uống là hũ chi THIẾT YẾU theo dòng phân bổ; Nghĩa vụ là hũ nghĩa vụ; Du lịch là hũ để dành: không thuộc luật này
    for target in ("an_uong", "nghia_vu", "du_lich"):
        tools = scripted_tools(checks=("ok", "ok"))
        result, client, scope = build(tools, outline(from_buffer(target)))
        assert result.outcome.ok and scope.calls == 1, target
        assert "feedback" not in prompt(client)


def test_hu_tiet_kiem_khac_khong_phai_quy_du_phong():
    # Du lịch có mục tiêu trong phương án: không phải quỹ dự phòng, chuyển sang Giải trí không thuộc luật này
    tools = scripted_tools(checks=("ok", "ok"))
    moved = from_buffer(jar_code="du_lich", amount_ref={"jar_code": "du_lich", "field": "proposed_increase"})
    result, client, scope = build(tools, outline(moved))
    assert result.outcome.ok and scope.calls == 1
    assert "feedback" not in prompt(client)


REQUEST = "Tháng này cho mình lấy bớt tiền quỹ dự phòng sang hũ Giải trí để đi chơi nhé"


def test_nguoi_dung_noi_ro_va_model_ghi_buffer_to_jars_thi_buoc_duoc_giu():
    tools = scripted_tools(checks=("ok",))
    draft = outline(from_buffer())
    draft["buffer_to_jars"] = ["giai_tri", "khong_co"]
    result, _, scope = build(tools, draft, user_request=REQUEST)
    assert result.outcome.ok and scope.calls == 1
    (saved,) = args_for(tools, "save_roadmap")[0]["phases"][0]["steps"]
    assert (saved["jar_code"], saved["to_jar_code"]) == ("du_phong", "giai_tri")
    # bước vẫn qua check_suitability như mọi bước
    assert any(a["proposal"].get("jar_code") == "du_phong" for a in args_for(tools, "check_suitability"))
    assert "buffer_to_jars" in ROADMAP_REQUEST_GUIDE


def test_khong_co_loi_nguoi_dung_hay_khong_ghi_hu_thi_van_chan():
    # model ghi buffer_to_jars mà không có lời người dùng (job sinh lại): bỏ qua; có lời người dùng mà không ghi hũ: vẫn chặn
    for request, listed in ((None, ["giai_tri"]), (REQUEST, []), (REQUEST, ["an_uong"])):
        tools = scripted_tools(checks=("ok", "ok"))
        draft = outline(from_buffer(), review())
        draft["buffer_to_jars"] = listed
        _, client, _ = build(tools, draft, outline(review()), user_request=request)
        (feedback,) = prompt(client, 1)["feedback"]
        assert feedback["rule_id"] == "emergency_not_for_discretionary", (request, listed)


def test_vi_co_hu_buffer_thi_hu_tiet_kiem_cu_khong_muc_tieu_khong_phai_quy_du_phong():
    balances = fixture("get_jar_balances.ok.json")
    for jar in balances["data"]["jars"]:
        jar["kind"] = {"du_lich": "saving", "du_phong": "saving", "nghia_vu": "obligation", "hoa_don": "obligation"}.get(
            jar["code"], "spending"
        )
    balances["data"]["jars"].append(
        {"code": "quy_gap", "name": "Quỹ gấp", "color_key": "blue", "icon_key": "shield", "balance_vnd": 500_000,
         "split_percent": 0, "kind": "saving", "purpose": "buffer"}
    )  # fmt: skip
    tools = scripted_tools(
        checks=("ok", "ok"), get_jar_balances=lambda _args: classify_result("get_jar_balances", mcp_ok(balances))
    )
    result, client, scope = build(tools, outline(from_buffer()))
    assert result.outcome.ok and scope.calls == 1 and "feedback" not in prompt(client)
