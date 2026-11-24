"""`GET /nudges/today` tôn trọng giờ im lặng người dùng dặn trong bộ nhớ dài hạn: `nudges_rest.MemoryNudgePreferences` (nguồn
`proactive.NudgePreferenceSource` đọc `memory_store.quiet_hours`) gắn vào `LedgerService.nudge_preferences`. Memory hỏng thì bản tin vẫn
hiện và có log. Client AgentCore Memory là đồ giả (`FakeMemoryApi`); đồng hồ cố định 03:00 UTC (10 giờ sáng giờ Việt Nam)."""

from __future__ import annotations

import logging

import pytest
from ledger_fakes import make_service
from test_ledger_memory import MEMORY_ID, FakeMemoryApi
from test_ledger_nudges import NID, TODAY, TRACE, FakeNudgesDb, gate_decision, get_today

from yofina_ledger import proactive as P
from yofina_ledger.memory_store import MemoryStore
from yofina_ledger.nudges_rest import MemoryNudgePreferences, split_windows

USER = "3f2a9c10-1b2c-4d5e-8f90-a1b2c3d4e5f6"
OTHER = "9e8d7c6b-5a49-4382-9170-6f5e4d3c2b1a"


@pytest.fixture()
def world():
    svc, repo, clock = make_service(users=(USER, OTHER))
    repo.db = FakeNudgesDb()
    api = FakeMemoryApi()
    svc.nudge_preferences = MemoryNudgePreferences(MemoryStore(MEMORY_ID, client=api))
    for uid in (USER, OTHER):
        P.insert_gate_nudge(
            repo.db, uid, nudge_id=NID if uid == USER else NID.replace("2d", "4d"), app_date=TODAY,
            decision=gate_decision(), trace_id=TRACE,
        )  # fmt: skip
    return svc, api, clock


def test_tach_khung_vat_qua_nua_dem():
    assert split_windows([(22, 5), (5, 11), (3, 3), (22, 24)]) == ((0, 5), (5, 11), (22, 24))
    assert split_windows([(0, 9)]) == ((0, 9),)


def test_lo_dat_lien_service_mac_dinh_khong_co_so_thich():
    svc, _, _ = make_service()
    assert svc.nudge_preferences is None


def test_gio_im_lang_trong_bo_nho_an_ban_tin_dung_nguoi(world):
    svc, api, clock = world
    api.add(1, "preference", USER, '{"context":"c","preference":"Đừng nhắc mình buổi sáng","categories":["nhắc"]}')
    api.add(2, "fact", OTHER, "Đừng nhắc mình buổi sáng")  # người khác, lại là sự thật: không ảnh hưởng ai
    body = get_today(svc, USER)  # 10 giờ sáng
    assert "nudge" not in body and "card" not in body
    assert body["suppressed"][0] == {"kind": "roadmap_proposed", "reason": "quiet_hours"}
    assert get_today(svc, OTHER)["nudge"]["kind"] == "roadmap_proposed"
    clock.advance(4 * 3600)  # 14 giờ: hết buổi sáng
    assert get_today(svc, USER)["nudge"]["nudge_id"] == NID


def test_gio_im_lang_vat_qua_nua_dem(world):
    svc, api, clock = world
    api.add(1, "preference", USER, "đừng gửi gì từ 22 giờ đến 7 giờ")
    assert get_today(svc, USER)["nudge"]["nudge_id"] == NID  # 10 giờ
    clock.advance(13 * 3600)  # 23 giờ cùng ngày
    assert "nudge" not in get_today(svc, USER)


def test_khong_co_so_thich_nhac_thi_van_hien(world):
    svc, api, _ = world
    api.add(1, "preference", USER, "Ưu tiên hũ Du lịch")
    assert get_today(svc, USER)["nudge"]["nudge_id"] == NID


def test_memory_hong_thi_van_hien_ban_tin_va_co_log(world, caplog):
    svc, api, _ = world
    api.add(1, "preference", USER, "Đừng nhắc mình buổi sáng")
    api.error = "ThrottledException"
    with caplog.at_level(logging.INFO):
        body = get_today(svc, USER)
    assert body["nudge"]["nudge_id"] == NID
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "quiet_hours_unavailable" in msgs and "nudge_preferences_unavailable" in msgs


def test_memory_chua_cau_hinh_thi_khong_co_so_thich(caplog):
    with caplog.at_level(logging.INFO):
        prefs = MemoryNudgePreferences(MemoryStore(None, client=FakeMemoryApi())).nudge_preferences(USER)
    assert prefs == P.NO_PREFERENCES
    assert "nudge_preferences_unavailable" in " ".join(r.getMessage() for r in caplog.records)


def test_nguon_loi_bat_ngo_khong_nem_ra_ngoai():
    class Broken:
        def memory_id(self):
            raise RuntimeError("boom")

    assert MemoryNudgePreferences(Broken()).nudge_preferences(USER) == P.NO_PREFERENCES
