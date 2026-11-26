"""Lời kết của lượt lập lộ trình dùng `notices.roadmap_outlook(data)` (V5, #39): các câu của hàm đứng đúng chỗ câu khả năng kịp. Mục tiêu
có số tiền mà chưa khả thi vẫn nói câu riêng của mục tiêu (không qua hàm). Hạn là ngày liền trước một mốc (đặc tả có `before`) thì câu nói
"trước {mốc}", không nói "trước" ngày liền trước mốc. Hàm giả, không model.
"""

from __future__ import annotations

from agent_helpers import fixture
from yofina_agent import notices
from yofina_agent.turn import _roadmap_closing

from yofina_core import blocks as B


def _data(feasibility: str) -> B.RoadmapData:
    data = fixture("save_roadmap.ok.json")["data"]
    alternatives = [
        {"option_id": "lui_han", "kind": "delay_goal", "label": "Lùi hạn", "summary": "Lùi hạn mục tiêu."},
        {"option_id": "giam_muc", "kind": "reduce_goal", "label": "Giảm mức", "summary": "Giảm số tiền mục tiêu."},
    ]  # hợp đồng: infeasible đi với đúng hai lựa chọn
    data.update(status="active", feasibility=feasibility, alternatives=alternatives if feasibility == "infeasible" else [])
    if feasibility == "infeasible":
        data["goals"][0].update(on_track=False, projected_date="2027-06-30", shortfall_vnd=900_000)
    data["phases"] = data["phases"][:1]
    data["phases"][0]["steps"] = data["phases"][0]["steps"][:1]
    data["counts"] = {"pending": 0, "accepted": 0, "rejected": 0, data["phases"][0]["steps"][0]["status"]: 1}
    return B.RoadmapData.model_validate(data)


def test_co_roadmap_outlook_thi_cac_cau_cua_ham_thay_cau_theo_feasibility(monkeypatch):
    seen: list[B.RoadmapData] = []

    def outlook(data: B.RoadmapData) -> list[str]:
        seen.append(data)
        return ["Câu khả năng kịp.", "Câu chưa có hạn."]

    monkeypatch.setattr(notices, "roadmap_outlook", outlook)
    data = _data("relaxed")
    text = _roadmap_closing(data, None, None)
    assert seen == [data]
    assert notices.ROADMAP_CLOSING_FEASIBILITY["relaxed"] not in text
    head = notices.ROADMAP_CLOSING_ACTIVE.format(version=data.version, phases=1, steps=1)
    assert text == f"{head} Câu khả năng kịp. Câu chưa có hạn. {notices.ROADMAP_CLOSING_NEXT_REVIEW}"


def test_muc_tieu_chua_kha_thi_van_noi_cau_rieng_cua_muc_tieu(monkeypatch):
    monkeypatch.setattr(notices, "roadmap_outlook", lambda _d: ["Không dùng."])
    goal = {"jar": "Du lịch", "target_text": "3.000.000 ₫", "target_date_text": "21/02/2027"}
    text = _roadmap_closing(_data("infeasible"), None, goal)
    assert "Không dùng." not in text
    assert notices.ROADMAP_CLOSING_GOAL_INFEASIBLE.format(goal="3.000.000 ₫ cho hũ Du lịch trước 21/02/2027") in text


def test_han_truoc_moc_thi_loi_ket_noi_truoc_moc_khong_noi_ngay_lien_truoc():
    """Hạn "trước Tết" (Tết Đinh Mùi 06/02/2027) là 05/02/2027: lời kết nói "trước 06/02/2027", không nói "trước 05/02/2027" (đọc ra sớm
    thêm một ngày). Không có mốc thì vẫn nói theo hạn như cũ."""
    goal = {"jar": "Du lịch", "target_text": "20.000.000 ₫", "target_date_text": "05/02/2027", "target_before_text": "06/02/2027"}
    text = _roadmap_closing(_data("infeasible"), None, goal)
    assert notices.ROADMAP_CLOSING_GOAL_INFEASIBLE.format(goal="20.000.000 ₫ cho hũ Du lịch trước 06/02/2027") in text
    assert "05/02/2027" not in text
    note = _roadmap_closing(_data("on_track"), None, goal)
    assert notices.ROADMAP_CLOSING_GOAL_NOTE.format(goal="20.000.000 ₫ cho hũ Du lịch trước 06/02/2027") in note
