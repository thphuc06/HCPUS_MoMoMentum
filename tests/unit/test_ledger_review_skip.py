"""`POST /review/daily-ask/skip` (phase 4 luồng B) với `review_asks` giả trong bộ nhớ: chưa có dòng của hôm nay thì tạo dòng `skipped`,
có dòng `open` thì chuyển `skipped`, idempotent, ngày khác không có câu hỏi thì 400. Ngày "hôm nay" là ngày mô phỏng theo `app_today`
(đồng hồ cố định 10/12/2026, offset -19 ra 21/11/2026). SQL thật chạy ở `tests/local_pg/test_classify_flow.py`."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date
from typing import Any

import pytest
from ledger_fakes import SETTINGS, http_event, make_service

from yofina_core.clock import app_today
from yofina_ledger.rest_api import handle_http

MINH = "sub-minh"


class FakeReviewAsksDb:
    """Chỉ bảng `review_asks` của các câu lệnh trong `review_rest.skip_response`; khóa `(user_id, ask_date)` như UNIQUE thật."""

    def __init__(self, pending: tuple[int, int] = (2, 180_000)) -> None:
        self.rows: dict[tuple[str, date], dict[str, Any]] = {}
        self.pending = pending
        self.sql: list[str] = []

    @contextmanager
    def transaction(self, user_id: str):
        yield self

    def execute(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self.sql.append(sql)
        key = (params["uid"], params["d"])
        row = self.rows.get(key)
        if sql.startswith("SELECT status FROM review_asks"):
            return [{"status": row["status"]}] if row else []
        if sql.startswith("INSERT INTO review_asks"):
            if row is None:
                n, total = self.pending
                row = self.rows[key] = {
                    "status": "skipped",
                    "item_count": n,
                    "pending_total_vnd": total,
                    "resolved": True,
                }
            elif row["status"] == "open":
                row.update(status="skipped", resolved=True)
            return [{"status": row["status"]}]
        if sql.startswith("UPDATE review_asks SET status = 'skipped'"):
            if row and row["status"] == "open":
                row.update(status="skipped", resolved=True)
            return []
        raise AssertionError(f"câu lệnh ngoài dự kiến: {sql}")


@pytest.fixture()
def env():
    svc, repo, clock = make_service()
    repo.db = FakeReviewAsksDb()
    today = app_today(repo.clock_offset(MINH), clock(), SETTINGS.tz)
    return svc, repo.db, today


def skip(svc, ask_date: Any) -> tuple[int, dict[str, Any]]:
    out = handle_http(
        http_event("POST", "/review/daily-ask/skip", sub=MINH, body={"ask_date": ask_date}), svc
    )
    return out["statusCode"], json.loads(out["body"])


def test_ngay_mo_phong_hom_nay_la_21_11(env):
    _, _, today = env
    assert today == date(2026, 11, 21)


def test_chua_co_dong_hom_nay_thi_tao_dong_skipped_va_idempotent(env):
    svc, db, today = env
    assert db.rows == {}
    s1 = skip(svc, today.isoformat())
    assert s1 == (200, {"ask_date": "2026-11-21", "status": "skipped"})
    row = db.rows[(MINH, today)]
    assert (row["status"], row["item_count"], row["pending_total_vnd"], row["resolved"]) == (
        "skipped",
        2,
        180_000,
        True,
    )
    assert skip(svc, today.isoformat()) == s1  # lần hai đọc thấy dòng skipped, không ghi thêm
    assert len(db.rows) == 1
    assert not any(s.startswith("INSERT") for s in db.sql[2:])


def test_co_dong_open_thi_chuyen_skipped(env):
    svc, db, today = env
    db.rows[(MINH, today)] = {
        "status": "open",
        "item_count": 3,
        "pending_total_vnd": 250_000,
        "resolved": False,
    }
    assert skip(svc, "2026-11-21") == (200, {"ask_date": "2026-11-21", "status": "skipped"})
    assert (
        db.rows[(MINH, today)]["status"] == "skipped" and db.rows[(MINH, today)]["item_count"] == 3
    )
    assert skip(svc, "2026-11-21") == (200, {"ask_date": "2026-11-21", "status": "skipped"})


def test_da_answered_thi_tra_answered(env):
    svc, db, today = env
    db.rows[(MINH, today)] = {
        "status": "answered",
        "item_count": 0,
        "pending_total_vnd": 0,
        "resolved": True,
    }
    assert skip(svc, "2026-11-21") == (200, {"ask_date": "2026-11-21", "status": "answered"})
    assert db.rows[(MINH, today)]["status"] == "answered"


def test_ngay_khac_hom_nay_khong_co_cau_hoi_thi_400_va_khong_ghi(env):
    svc, db, _ = env
    status, body = skip(svc, "2026-11-20")
    assert status == 400 and body["error"]["code"] == "PARAMS_INVALID"
    assert db.rows == {}


@pytest.mark.parametrize("bad", ["khong-phai-ngay", "2026-1-21", None, 20261121])
def test_ngay_sai_dinh_dang_thi_400(env, bad):
    svc, db, _ = env
    status, body = skip(svc, bad)
    assert status == 400 and body["error"]["code"] == "PARAMS_INVALID"
    assert db.rows == {}
