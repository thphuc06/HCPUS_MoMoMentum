"""Lời kết của lộ trình chọn theo dữ kiện có cấu trúc, không chỉ theo `feasibility` (V5 của báo cáo rà soát #39).

Trước đây `relaxed` luôn thành câu "chỉ kịp sau khi nới hạn hoặc mức" kể cả khi phương án chỉ giảm chi ở hũ không thiết yếu và mục tiêu vẫn
đúng hạn, còn ví không có mục tiêu nào vẫn nghe "mục tiêu kịp hạn". Bản đã lưu không có `relaxations` của bộ tối ưu, nhưng mỗi mục tiêu có
`on_track` theo hạn gốc: mục tiêu phải lùi hạn (`goal_delayed`) đúng là mục tiêu `on_track` false, nên `relaxed` với mọi mục tiêu đúng hạn
là chỉ giảm chi. Mục tiêu không có hạn (V2) không "kịp" hay "trễ": lời kết nói chưa có hạn để người dùng cho biết hạn.

- `notices.roadmap_outlook(data)`: các câu thay cho câu theo `feasibility` trong lời kết dựng bằng mã của lượt lập (nối ở `turn.py`);
- các câu cũ theo `feasibility` (`ROADMAP_CLOSING_FEASIBILITY`) nay đúng với mọi trường hợp của trạng thái đó, để lời kết chưa nối hàm mới
  cũng không nói sai;
- writer (lượt xem lộ trình) nhận `goals` có cấu trúc trong bản gọn và nhiệm vụ nói nghĩa của chúng.
"""

from __future__ import annotations

from agent_helpers import fixture
from yofina_agent import notices, writer
from yofina_agent.compact import compact_roadmap

from yofina_core import blocks as B


def data(feasibility: str, *goals: dict) -> B.RoadmapData:
    payload = fixture("save_roadmap.ok.json")["data"]
    # "chưa khả thi" đi với đúng hai lựa chọn: lấy hai lựa chọn của phương án chưa khả thi trong fixture
    alternatives = fixture("optimize_allocation.ok_infeasible.json")["data"]["alternatives"]
    payload.update(feasibility=feasibility, goals=list(goals), alternatives=alternatives if feasibility == "infeasible" else [])
    return B.RoadmapData.model_validate(payload)


def goal(*, on_track: bool = True, dated: bool = True, name: str = "Du lịch") -> dict:
    out = {
        "jar": {"code": "du_lich", "name": name, "color_key": "teal", "icon_key": "plane"},
        "target_vnd": 6_000_000,
        "on_track": on_track,
        "shortfall_vnd": 0 if on_track else 300_000,
        "monthly_needed_vnd": 1_150_000 if dated else 0,
    }
    if dated:
        out["target_date"] = "2027-03-31"
    return out


def test_relaxed_chi_vi_giam_chi_ma_muc_tieu_dung_han_thi_khong_noi_noi_han():
    (line,) = notices.roadmap_outlook(data("relaxed", goal()))
    assert line == notices.ROADMAP_OUTLOOK_CUT_ONLY
    assert "nới hạn" not in line and "kịp hạn" in line


def test_relaxed_co_muc_tieu_phai_lui_han():
    assert notices.roadmap_outlook(data("relaxed", goal(on_track=False))) == [notices.ROADMAP_OUTLOOK_DELAYED]


def test_vi_khong_co_muc_tieu_thi_khong_noi_muc_tieu_kip_han():
    for feasibility in ("on_track", "relaxed"):
        (line,) = notices.roadmap_outlook(data(feasibility))
        assert "mục tiêu" not in line.lower(), (feasibility, line)
    assert notices.roadmap_outlook(data("on_track", goal())) == [notices.ROADMAP_OUTLOOK_ON_TRACK]


def test_muc_tieu_chua_co_han_noi_ro_chua_co_han():
    lines = notices.roadmap_outlook(data("on_track", goal(dated=False, name="Quỹ cưới")))
    assert lines[0] == notices.ROADMAP_OUTLOOK_NO_GOAL
    assert "Quỹ cưới" in lines[1] and "chưa có hạn" in lines[1] and "kịp hạn" not in lines[1]


def test_chua_kha_thi_giu_cau_cu():
    assert notices.roadmap_outlook(data("infeasible", goal(on_track=False))) == [
        notices.ROADMAP_CLOSING_FEASIBILITY["infeasible"]
    ]


def test_cau_theo_feasibility_dung_voi_moi_truong_hop_cua_trang_thai():
    """Lời kết chưa nối `roadmap_outlook` vẫn dùng câu theo `feasibility`: câu `relaxed` không khẳng định phải nới hạn, câu `on_track`
    không khẳng định có mục tiêu."""
    relaxed, on_track = notices.ROADMAP_CLOSING_FEASIBILITY["relaxed"], notices.ROADMAP_CLOSING_FEASIBILITY["on_track"]
    assert "chỉ kịp sau khi nới" not in relaxed and "giảm chi" in relaxed and "lùi hạn" in relaxed
    assert "mục tiêu kịp hạn" not in on_track


def test_writer_xem_lo_trinh_nhan_muc_tieu_co_cau_truc():
    payload = {"data": data("relaxed", goal(), goal(dated=False, name="Quỹ cưới")).model_dump(mode="json", exclude_none=True)}
    view = compact_roadmap(payload)
    assert view["goals"] == [
        {"jar": "Du lịch", "target_text": "6.000.000 ₫", "target_date_text": "31/03/2027", "on_track": True},
        {"jar": "Quỹ cưới", "target_text": "6.000.000 ₫", "no_deadline": True, "on_track": True},
    ]
    late = compact_roadmap({"data": data("relaxed", goal(on_track=False)).model_dump(mode="json", exclude_none=True)})
    assert late["goals"][0]["shortfall_text"] == "300.000 ₫"
    task = writer.TASKS["roadmap"]
    assert all(key in task for key in ("goals", "no_deadline", "on_track", "relaxed"))
    assert "kịp sau khi nới hạn hoặc mức" not in task
