"""N2 (phase 4): batch đêm và đặt lại chạy thêm điểm chống chịu rồi phát hiện đổi hành vi sau dự báo; mỗi bước bọc lỗi riêng."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from yofina_core.errors import ErrorCode, YofinaError
from yofina_forecast import batch, change, resilience

NOW = datetime(2026, 11, 21, 2, 0, tzinfo=UTC)


@dataclass
class _Outcome:
    status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return {"trigger": "x"}


@dataclass
class _Pipeline:
    status: str = "ok"
    calls: list[str] = field(default_factory=list)

    def run_user(self, user_id: str, *, trigger: str) -> _Outcome:
        self.calls.append(f"forecast:{trigger}")
        return _Outcome(self.status)

    def now(self) -> datetime:
        return NOW


@dataclass
class _Score:
    score: int = 33


@dataclass
class _Report:
    confirmed: list[str] = field(default_factory=lambda: ["an_uong"])

    def to_dict(self) -> dict[str, Any]:
        return {"user_id": "u", "confirmed": self.confirmed, "suspected": [], "published": ["f1"]}


def _patch(monkeypatch, pipe: _Pipeline, *, res_exc: Exception | None = None, chg_exc: Exception | None = None):
    def fake_res(p, uid, now, *, source="nightly"):
        pipe.calls.append(f"resilience:{source}")
        if res_exc:
            raise res_exc
        return _Score()

    def fake_chg(p, uid, now, **kw):
        pipe.calls.append("change")
        if chg_exc:
            raise chg_exc
        return _Report()

    monkeypatch.setattr(resilience, "compute_and_store", fake_res)
    monkeypatch.setattr(change, "detect_and_store", fake_chg)


@pytest.mark.parametrize(("trigger", "source"), [("nightly", "nightly"), ("reset", "reset"), ("manual", "nightly")])
def test_du_bao_roi_diem_chong_chiu_roi_doi_hanh_vi(monkeypatch, trigger, source):
    pipe = _Pipeline()
    _patch(monkeypatch, pipe)
    out = batch.run_one(pipe, "u", trigger, raise_errors=True)
    assert pipe.calls == [f"forecast:{trigger}", f"resilience:{source}", "change"]
    assert out["phase4"]["resilience"] == {"status": "ok", "score": 33}
    assert out["phase4"]["change"]["confirmed"] == ["an_uong"] and out["phase4"]["change"]["published"] == ["f1"]


@pytest.mark.parametrize("trigger", ["read", "event"])
def test_duong_nhanh_chi_tinh_du_bao(monkeypatch, trigger):
    pipe = _Pipeline()
    _patch(monkeypatch, pipe)
    out = batch.run_one(pipe, "u", trigger, raise_errors=True)
    assert pipe.calls == [f"forecast:{trigger}"] and "phase4" not in out


def test_du_bao_bi_bo_qua_thi_khong_chay_buoc_sau(monkeypatch):
    pipe = _Pipeline(status="skipped")
    _patch(monkeypatch, pipe)
    out = batch.run_one(pipe, "u", "nightly", raise_errors=True)
    assert pipe.calls == ["forecast:nightly"] and "phase4" not in out


def test_mot_buoc_loi_khong_lam_hong_buoc_kia_va_khong_nem(monkeypatch):
    pipe = _Pipeline()
    _patch(monkeypatch, pipe, res_exc=RuntimeError("boom"))
    out = batch.run_one(pipe, "u", "nightly", raise_errors=True)
    assert out["status"] == "ok"
    assert out["phase4"]["resilience"] == {"status": "failed", "error": "RuntimeError"}
    assert out["phase4"]["change"]["status"] == "ok"


def test_loi_nghiep_vu_thi_bo_qua_buoc(monkeypatch):
    pipe = _Pipeline()
    _patch(monkeypatch, pipe, chg_exc=YofinaError(ErrorCode.PROFILE_INCOMPLETE, "chưa đủ hồ sơ"))
    out = batch.run_one(pipe, "u", "reset", raise_errors=True)
    assert out["phase4"]["change"] == {"status": "skipped", "code": str(ErrorCode.PROFILE_INCOMPLETE)}
    assert out["phase4"]["resilience"]["status"] == "ok"
