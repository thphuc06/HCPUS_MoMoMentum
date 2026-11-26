"""Phần nối với nhánh GG (V5, #39): lời kết của lượt lập lộ trình dùng `notices.roadmap_outlook(data)` khi hàm đó có.

Kiểm bằng `hasattr` nên hai nhánh gộp theo thứ tự nào cũng chạy: chưa có hàm thì giữ câu theo `feasibility` như cũ; có hàm thì các câu
của hàm thay đúng chỗ câu đó. Mục tiêu có số tiền mà chưa khả thi vẫn nói câu riêng của mục tiêu (không qua hàm). Hàm giả, không model.
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


def test_chua_co_roadmap_outlook_thi_giu_cau_theo_feasibility(monkeypatch):
    monkeypatch.delattr(notices, "roadmap_outlook", raising=False)
    text = _roadmap_closing(_data("on_track"), None, None)
    assert notices.ROADMAP_CLOSING_FEASIBILITY["on_track"] in text


def test_co_roadmap_outlook_thi_cac_cau_cua_ham_thay_cau_theo_feasibility(monkeypatch):
    seen: list[B.RoadmapData] = []

    def outlook(data: B.RoadmapData) -> list[str]:
        seen.append(data)
        return ["Câu khả năng kịp.", "Câu chưa có hạn."]

    monkeypatch.setattr(notices, "roadmap_outlook", outlook, raising=False)
    data = _data("relaxed")
    text = _roadmap_closing(data, None, None)
    assert seen == [data]
    assert notices.ROADMAP_CLOSING_FEASIBILITY["relaxed"] not in text
    head = notices.ROADMAP_CLOSING_ACTIVE.format(version=data.version, phases=1, steps=1)
    assert text == f"{head} Câu khả năng kịp. Câu chưa có hạn. {notices.ROADMAP_CLOSING_NEXT_REVIEW}"


def test_muc_tieu_chua_kha_thi_van_noi_cau_rieng_cua_muc_tieu(monkeypatch):
    monkeypatch.setattr(notices, "roadmap_outlook", lambda _d: ["Không dùng."], raising=False)
    goal = {"jar": "Du lịch", "target_text": "3.000.000 ₫", "target_date_text": "21/02/2027"}
    text = _roadmap_closing(_data("infeasible"), None, goal)
    assert "Không dùng." not in text
    assert notices.ROADMAP_CLOSING_GOAL_INFEASIBLE.format(goal="3.000.000 ₫ cho hũ Du lịch trước 21/02/2027") in text
