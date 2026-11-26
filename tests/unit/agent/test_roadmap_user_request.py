"""Lời người dùng tới được người lập lộ trình (C4 của báo cáo rà soát #39): trước đây yêu cầu lộ trình bị rút còn ba ô (số tiền, hũ, hạn) và
mọi ràng buộc khác bị bỏ mà không báo. Nay `build_roadmap` nhận câu của người dùng (tham số tùy chọn `user_request`, mặc định None giữ hành
vi cũ), che PII bằng bộ che sẵn có rồi đưa vào ngữ cảnh planner như DỮ LIỆU, kèm hướng dẫn theo nguyên tắc. Số tiền trong câu đọc bằng mã
(`textutil.extract_amounts`) thành tham chiếu `user_amount` mà bước chuyển tiền hay giảm chi dùng được, vẫn qua mọi trần của bước. Hũ người
dùng dặn giữ (model trích vào `protect_jars` của bản phác thảo) mà bước nào lấy tiền hay giảm phần chia của hũ đó thì bước vào vòng sửa sẵn
có. Không gọi model thật (model giả theo kịch bản)."""

from __future__ import annotations

from agent_helpers import fixture
from test_roadmap_agent import (
    args_for,
    build,
    goal_balances,
    later_phase,
    outline,
    prompt,
    review,
    roadmap_events,
    scripted_tools,
    step,
)
from yofina_agent.roadmap_agent import ROADMAP_REQUEST_GUIDE, ROADMAP_SYSTEM

#: câu người dùng của các ca (tự viết cho test, không chép câu eval): có số điện thoại để kiểm bộ che PII
MOVE_NOW = "Lên lộ trình giúp mình, mình muốn chuyển ngay 500 nghìn từ Dự phòng qua Du lịch, có gì gọi 0912345678"
KEEP_FUN = "Lập kế hoạch tiết kiệm nhưng giữ nguyên hũ Giải trí cho mình nhé"


def user_step(index=0, **changes):
    """Bước chuyển ngay từ Dự phòng sang Du lịch, số tiền là số thứ `index` trong lời người dùng."""
    base = {
        "jar_code": "du_phong",
        "to_jar_code": "du_lich",
        "amount_ref": {"jar_code": "du_lich", "field": "user_amount", "index": index},
    }
    return step("chuyen_ngay", **{**base, **changes})


def test_khong_co_loi_nguoi_dung_thi_ngu_canh_va_loi_nhac_nhu_cu():
    tools = scripted_tools()
    result, client, _ = build(tools, outline(review()))
    assert result.outcome.ok
    sent = prompt(client)
    assert "user_request" not in sent and "user_amounts" not in sent["context"]
    assert client.calls[0]["system"][0]["text"] == ROADMAP_SYSTEM


def test_loi_nguoi_dung_vao_ngu_canh_nhu_du_lieu_da_che_pii():
    tools = scripted_tools()
    result, client, _ = build(tools, outline(review()), user_request=MOVE_NOW)
    assert result.outcome.ok
    sent = prompt(client)
    text = sent["user_request"]["text"]
    assert "0912345678" not in text and "500 nghìn" in text and "Du lịch" in text
    # số tiền trong câu đọc bằng mã (số điện thoại đã che nên không thành số tiền); là căn cứ cho chữ của bước
    assert sent["context"]["user_amounts"] == [{"amount_text": "500.000 ₫"}]
    assert "500.000 ₫" in sent["reason_numbers"]
    # lời người dùng nằm NGOÀI bản gọn làm căn cứ số: số người dùng gõ chỉ vào căn cứ qua `user_amounts`
    assert "user_request" not in sent["context"]
    system = client.calls[0]["system"][0]["text"]
    assert system == ROADMAP_SYSTEM + ROADMAP_REQUEST_GUIDE
    assert "protect_jars" in ROADMAP_REQUEST_GUIDE and "user_amount" in ROADMAP_REQUEST_GUIDE
    # lời người dùng không đổi được luật an toàn: không lấy quỹ dự phòng cho chi tiêu không thiết yếu, không bỏ bước kiểm tra
    assert "quỹ dự phòng cho chi tiêu không thiết yếu" in ROADMAP_REQUEST_GUIDE and "không bỏ bước kiểm tra" in ROADMAP_REQUEST_GUIDE


def test_buoc_chuyen_ngay_dung_so_tien_nguoi_dung_neu_khi_so_du_du():
    tools = scripted_tools()
    result, _, scope = build(tools, outline(user_step()), user_request=MOVE_NOW)
    assert result.outcome.ok and scope.calls == 1
    (saved,) = args_for(tools, "save_roadmap")[0]["phases"][0]["steps"]
    assert (saved["jar_code"], saved["to_jar_code"], saved["amount_vnd"]) == ("du_phong", "du_lich", 500_000)
    assert saved["action"]["params"]["amount_vnd"] == 500_000
    assert saved["metrics"][0] == {"label": "Hũ Dự phòng", "before": "2.700.000 ₫", "after": "2.200.000 ₫"}


def test_so_tien_nguoi_dung_neu_van_qua_tran_cua_buoc(caplog):
    # Giải trí chỉ có 760.000 ₫: chuyển ngay 3 triệu theo lời người dùng vượt phần chuyển được nên vào vòng sửa, phản hồi nêu trần
    caplog.set_level("WARNING", logger="yofina.agent.roadmap")
    tools = scripted_tools()
    big = user_step(jar_code="giai_tri")
    result, client, scope = build(
        tools, outline(big, review()), outline(review()), user_request="Chuyển ngay 3 triệu từ Giải trí sang Du lịch"
    )
    assert result.outcome.ok and scope.calls == 2
    (feedback,) = prompt(client, 1)["feedback"]
    assert feedback["rule_id"] == "step_invalid" and "760.000 ₫" in feedback["message"]
    (rejected,) = roadmap_events(caplog, "roadmap_step_rejected")
    assert rejected["detail"] == "amount_over_available"


def test_tham_chieu_so_tien_nguoi_dung_sai_cho_thi_vao_vong_sua(caplog):
    caplog.set_level("WARNING", logger="yofina.agent.roadmap")
    # không có lời người dùng, vị trí ngoài danh sách, hay bước đổi tỷ lệ chia (không rõ tăng hay giảm): không dựng được số tiền
    split = review(
        step_id="doi_ti_le", kind="adjust_split", jar_code="du_lich", action=None,
        amount_ref={"jar_code": "du_lich", "field": "user_amount", "index": 0},
    )  # fmt: skip
    cases = [(outline(user_step()), None), (outline(user_step(1)), MOVE_NOW), (later_phase(split), MOVE_NOW)]
    for draft, request in cases:
        caplog.clear()
        tools = scripted_tools(checks=("ok", "ok"))
        result, client, _ = build(tools, draft, outline(review()), user_request=request)
        assert result.outcome.ok
        (feedback,) = prompt(client, 1)["feedback"]
        assert feedback["rule_id"] == "step_invalid"
        (rejected,) = roadmap_events(caplog, "roadmap_step_rejected")
        assert rejected["detail"] == "user_amount", (request, rejected)


def test_giam_chi_theo_so_tien_nguoi_dung_neu_o_giai_doan_sau():
    cut = review(
        step_id="giam_giai_tri", kind="cut_spending", jar_code="giai_tri", action=None,
        amount_ref={"jar_code": "giai_tri", "field": "user_amount", "index": 0},
    )  # fmt: skip
    tools = scripted_tools(checks=("ok", "ok"))
    result, _, scope = build(tools, later_phase(cut), user_request="Mỗi tháng bớt 200 nghìn ở Giải trí giúp mình")
    assert result.outcome.ok and scope.calls == 1
    assert args_for(tools, "save_roadmap")[0]["phases"][1]["steps"][0]["amount_vnd"] == 200_000


def test_hu_nguoi_dung_dan_giu_ma_buoc_lay_tien_thi_vao_vong_sua(caplog):
    caplog.set_level("WARNING", logger="yofina.agent.roadmap")
    tools = scripted_tools(checks=("ok", "ok"))
    draft = outline(step(), review())  # chuyển từ Giải trí sang Dự phòng
    draft["protect_jars"] = ["giai_tri", "khong_co"]  # mã lạ bị bỏ
    fixed = outline(step(jar_code="du_phong", to_jar_code="du_lich", amount_ref={"jar_code": "du_lich", "field": "proposed_increase"}))
    result, client, scope = build(tools, draft, fixed, user_request=KEEP_FUN)
    assert result.outcome.ok and scope.calls == 2
    (feedback,) = prompt(client, 1)["feedback"]
    assert feedback["rule_id"] == "user_constraint" and feedback["step_id"] == "bu_du_phong"
    assert "Giải trí" in feedback["message"]
    (rejected,) = roadmap_events(caplog, "roadmap_step_rejected")
    assert rejected["rule_id"] == "user_constraint"
    # bước lấy tiền hũ bị giữ không tốn lượt check_suitability
    assert all(a["proposal"].get("jar_code") != "giai_tri" for a in args_for(tools, "check_suitability"))
    (saved,) = args_for(tools, "save_roadmap")[0]["phases"][0]["steps"]
    assert saved["jar_code"] == "du_phong"


def test_giu_hu_ap_cho_giam_chi_giam_phan_chia_va_ti_le_chia_moi():
    cut = review(
        step_id="giam_giai_tri", kind="cut_spending", jar_code="giai_tri", action=None,
        amount_ref={"jar_code": "giai_tri", "field": "proposed_decrease"},
    )  # fmt: skip
    lower = review(
        step_id="giam_chia", kind="adjust_split", jar_code="giai_tri", action=None,
        amount_ref={"jar_code": "giai_tri", "field": "proposed_decrease"},
    )  # fmt: skip
    apply_all = review(step_id="ap_ti_le", kind="adjust_split", action="save_jars")  # tỷ lệ đề xuất cắt Giải trí 1.200.000 -> 600.000 ₫
    for bad in (cut, lower, apply_all):
        tools = scripted_tools(get_jar_balances=goal_balances(), checks=("ok", "ok"))
        draft = later_phase(bad)
        draft["protect_jars"] = ["giai_tri"]
        result, client, _ = build(tools, draft, later_phase(review(step_id="nhac_lai")), user_request=KEEP_FUN)
        assert result.outcome.ok
        (feedback,) = prompt(client, 1)["feedback"]
        assert feedback["rule_id"] == "user_constraint", bad["step_id"]


def test_giu_hu_khong_co_loi_nguoi_dung_thi_bo_qua():
    """Không có lời người dùng (job sinh lại không ghi chú) thì không có căn cứ cho `protect_jars`: bước vẫn được xét như cũ."""
    tools = scripted_tools()
    draft = outline(step())
    draft["protect_jars"] = ["giai_tri"]
    result, _, scope = build(tools, draft)
    assert result.outcome.ok and scope.calls == 1
    assert args_for(tools, "save_roadmap")[0]["phases"][0]["steps"][0]["jar_code"] == "giai_tri"


def test_loi_nguoi_dung_rong_hay_chi_khoang_trang_nhu_khong_co():
    for blank in ("", "   "):
        tools = scripted_tools()
        result, client, _ = build(tools, outline(review()), user_request=blank)
        assert result.outcome.ok and "user_request" not in prompt(client)


def test_fixture_khong_doi():
    # các ca trên dựa vào fixture: Dự phòng 2.700.000 ₫, Giải trí 760.000 ₫, Du lịch còn thiếu tới đích hơn 500.000 ₫
    jars = {j["code"]: j["balance_vnd"] for j in fixture("get_jar_balances.ok.json")["data"]["jars"]}
    assert (jars["du_phong"], jars["giai_tri"], jars["du_lich"]) == (2_700_000, 760_000, 1_800_000)
