"""Trần theo tài khoản mỗi ngày (#13, B4) qua API công khai của `yofina_core.quota`, với bộ đếm giả cùng giao kèo `UsageStore`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.llm import BudgetCapReached
from yofina_core.quota import CHAT, UPLOAD, AccountQuota, CapSource, DailyQuotaExceeded

NOW = datetime(2026, 12, 3, 3, 0, tzinfo=UTC)  # 10:00 giờ Việt Nam


class CountingUsage:
    """Bộ đếm giả cùng giao kèo với `DynamoUsageStore.consume`: tăng nguyên tử, đủ trần thì ném `BudgetCapReached`."""

    def __init__(self) -> None:
        self.counts: dict[tuple[str, str], int] = {}

    def consume(self, *, day: str, model: str, cap: int, ttl_epoch: int) -> int:
        n = self.counts.get((day, model), 0)
        if n >= cap:
            raise BudgetCapReached(model)
        self.counts[(day, model)] = n + 1
        return n + 1


class BrokenUsage:
    def consume(self, **kw: Any) -> int:
        raise ConnectionError("dynamodb không trả lời")


class FakeSsm:
    """SSM giả: chỉ có những tham số trong `params`; khóa khác là `ParameterNotFound` (Config nhận biết theo tên lớp)."""

    class ParameterNotFound(Exception):
        pass

    def __init__(self, params: dict[str, str]) -> None:
        self.params, self.calls = params, 0

    def get_parameter(self, *, Name: str, WithDecryption: bool) -> dict[str, Any]:
        self.calls += 1
        if Name in self.params:
            return {"Parameter": {"Value": self.params[Name]}}
        raise self.ParameterNotFound(Name)


def quota(kind: str = CHAT, **kw: Any) -> AccountQuota:
    kw.setdefault("store", CountingUsage())
    kw.setdefault("cap", CapSource(kind, env={}))
    kw.setdefault("now", lambda: NOW)
    return AccountQuota(kind, **kw)


def test_mac_dinh_luot_chat_100_qua_luot_101_bi_chan():
    q = quota()
    assert [q.take("sub-minh") for _ in range(100)] == list(range(1, 101))
    with pytest.raises(DailyQuotaExceeded) as caught:
        q.take("sub-minh")
    err = caught.value
    assert isinstance(err, YofinaError)
    assert err.code == ErrorCode.DAILY_QUOTA_EXCEEDED and err.http_status == 429
    assert "100 lượt" in err.message and "vẫn xem" in err.message


def test_mac_dinh_nap_tep_20_lan_va_tai_khoan_khac_dem_rieng():
    q = quota(UPLOAD)
    for _ in range(20):
        q.take("sub-minh")
    with pytest.raises(DailyQuotaExceeded) as caught:
        q.take("sub-minh")
    assert "20" in caught.value.message and "vẫn xem" in caught.value.message
    assert q.take("sub-lan") == 1  # một tài khoản chạm trần không chặn tài khoản khác


def test_tran_0_thi_chan_ngay():
    with pytest.raises(DailyQuotaExceeded):
        quota(cap=0).take("sub-minh")


def test_nguon_tran_env_truoc_ssm_truoc_mac_dinh():
    ssm = FakeSsm({"/yofina/quota/chat_turns_per_day": "7", "/yofina/quota/uploads_per_day": "3"})
    prefix = {"YOFINA_SSM_PREFIX": "/yofina"}
    assert CapSource(CHAT, {**prefix, "YOFINA_QUOTA_CHAT_TURNS_PER_DAY": "2"}, ssm)() == 2
    assert ssm.calls == 0  # có biến môi trường thì không đọc SSM
    assert CapSource(CHAT, prefix, ssm)() == 7
    assert CapSource(UPLOAD, prefix, ssm)() == 3
    assert CapSource(CHAT, prefix, FakeSsm({}))() == 100  # SSM vắng khóa: mặc định
    assert CapSource(UPLOAD, {}, ssm)() == 20  # không có tiền tố SSM: mặc định


def test_doi_tran_tren_ssm_co_hieu_luc_sau_thoi_gian_nho_khong_can_deploy():
    t = [0.0]
    ssm = FakeSsm({"/yofina/quota/chat_turns_per_day": "2"})
    cap = CapSource(CHAT, {"YOFINA_SSM_PREFIX": "/yofina"}, ssm, ttl=300, clock=lambda: t[0])
    q = quota(cap=cap)
    q.take("sub-minh")
    q.take("sub-minh")
    with pytest.raises(DailyQuotaExceeded):
        q.take("sub-minh")
    ssm.params["/yofina/quota/chat_turns_per_day"] = "5"
    t[0] = 299.0
    # còn trong thời gian nhớ: vẫn trần cũ, không gọi SSM mỗi lượt
    with pytest.raises(DailyQuotaExceeded):
        q.take("sub-minh")
    assert ssm.calls == 1
    t[0] = 300.0
    assert q.take("sub-minh") == 3


def test_lam_nong_doc_tran_truoc_nen_luot_dau_khong_doc_ssm():
    ssm = FakeSsm({"/yofina/quota/chat_turns_per_day": "7"})
    store = CountingUsage()
    q = quota(store=store, cap=CapSource(CHAT, {"YOFINA_SSM_PREFIX": "/yofina"}, ssm))
    assert q.warm() == 7 and ssm.calls == 1
    assert store.counts == {}  # làm nóng không tính lượt nào
    assert q.take("sub-minh") == 1 and ssm.calls == 1


def test_lam_nong_bo_dem_tat_thi_khong_doc_tran():
    ssm = FakeSsm({"/yofina/quota/chat_turns_per_day": "7"})
    q = quota(store=None, cap=CapSource(CHAT, {"YOFINA_SSM_PREFIX": "/yofina"}, ssm))
    assert q.warm() is None and ssm.calls == 0


def test_ssm_loi_hoac_sai_dinh_dang_thi_dung_mac_dinh_va_ghi_log(caplog):
    class Denied(FakeSsm):
        def get_parameter(self, **kw: Any) -> dict[str, Any]:
            raise PermissionError("AccessDenied")

    prefix = {"YOFINA_SSM_PREFIX": "/yofina"}
    with caplog.at_level("ERROR", logger="yofina.quota"):
        assert CapSource(CHAT, prefix, Denied({}))() == 100
        assert (
            CapSource(CHAT, prefix, FakeSsm({"/yofina/quota/chat_turns_per_day": "nhiều"}))() == 100
        )
    assert sum("quota_cap_unreadable" in r.message for r in caplog.records) == 2


def test_bo_dem_loi_thi_cho_qua_va_ghi_log(caplog):
    q = quota(store=BrokenUsage())
    with caplog.at_level("ERROR", logger="yofina.quota"):
        assert q.take("sub-minh") is None
    assert any("quota_store_error" in r.message for r in caplog.records)


def test_ngay_doi_theo_dong_ho_that_o_mui_gio_viet_nam():
    clock = [datetime(2026, 12, 2, 16, 58, tzinfo=UTC)]  # 23:58 ngày 2/12 giờ Việt Nam
    store = CountingUsage()
    q = quota(store=store, cap=1, now=lambda: clock[0])
    q.take("sub-minh")
    clock[0] = datetime(2026, 12, 2, 16, 59, 59, tzinfo=UTC)
    with pytest.raises(DailyQuotaExceeded):
        q.take("sub-minh")
    # 00:00:01 ngày 3/12 giờ Việt Nam, ngày UTC chưa đổi
    clock[0] = datetime(2026, 12, 2, 17, 0, 1, tzinfo=UTC)
    assert q.take("sub-minh") == 1
    # phân vùng riêng: không lẫn vào `day = YYYY-MM-DD` mà bảng vận hành (`/ops/summary`) cộng lượt gọi model
    assert not {day for day, _ in store.counts} & {"2026-12-02", "2026-12-03"}


def test_khong_luu_sub_tho_va_cung_sub_cung_mot_bo_dem():
    store = CountingUsage()
    sub = "a1b2c3d4-0000-4000-8000-minh"
    q = quota(store=store)
    q.take(sub)
    q.take(sub)
    q.take("sub-lan")
    keys = [part for key in store.counts for part in key]
    assert not any(sub in k or "minh" in k or "sub-lan" in k for k in keys)
    assert sorted(store.counts.values()) == [1, 2]


def test_from_env_khong_co_bang_dem_thi_tat_va_ghi_log(caplog):
    with caplog.at_level("WARNING", logger="yofina.quota"):
        q = AccountQuota.from_env(CHAT, {})
    assert q.take("sub-minh") is None
    assert any("quota_disabled" in r.message for r in caplog.records)


def test_from_env_dem_o_bang_usage_bang_update_item_co_dieu_kien():
    class Ddb:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def update_item(self, **kw: Any) -> dict[str, Any]:
            self.calls.append(kw)
            return {"Attributes": {"count": {"N": "1"}}}

    ddb = Ddb()
    env = {"YOFINA_USAGE_TABLE": "yofina-usage", "YOFINA_QUOTA_UPLOADS_PER_DAY": "4"}
    assert AccountQuota.from_env(UPLOAD, env, client=ddb).take("sub-minh") == 1
    [call] = ddb.calls
    assert call["TableName"] == "yofina-usage" and call["ExpressionAttributeValues"][":cap"] == {
        "N": "4"
    }
