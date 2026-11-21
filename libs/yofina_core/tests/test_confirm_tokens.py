"""Token xác nhận dùng một lần (ADR-0002). 13 ca của spike Gateway §5 (step5_confirm.py), cộng các ca
tấn công bổ sung. Dùng kho `jti` giả trong bộ nhớ và đồng hồ giả; kho DynamoDB thật được thử ở
tests/integration (kể cả hai request đua cùng `jti`)."""

from __future__ import annotations

import base64
import json
import threading
from datetime import UTC, datetime, timedelta

import pytest

from yofina_core.confirm import (
    MOVE_BETWEEN_JARS,
    ConfirmService,
    DynamoJtiStore,
    SecretKeyProvider,
    decode_token,
    issue_token,
    params_hash,
)
from yofina_core.errors import ErrorCode, YofinaError

KEY = b"khoa-thu-nghiem-cua-unit-test"
OTHER_KEY = b"khoa-khac-hoan-toan"
A, B = "sub-nguoi-dung-a", "sub-nguoi-dung-b"
P = {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100_000}
TOOL = MOVE_BETWEEN_JARS
NOW = datetime(2026, 11, 21, 3, 0, tzinfo=UTC)


class MemoryJtiStore:
    def __init__(self) -> None:
        self.used: set[str] = set()
        self.lock = threading.Lock()

    def consume(self, jti: str, exp: int) -> None:
        with self.lock:
            if jti in self.used:
                raise YofinaError(ErrorCode.TOKEN_REUSED, "đã dùng")
            self.used.add(jti)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def make(ttl: int = 120, max_ttl: int = 120) -> tuple[ConfirmService, Clock, MemoryJtiStore]:
    clock, store = Clock(), MemoryJtiStore()
    return (
        ConfirmService(lambda: KEY, store, ttl_seconds=ttl, max_ttl_seconds=max_ttl, clock=clock),
        clock,
        store,
    )


def code_of(fn) -> ErrorCode:
    with pytest.raises(YofinaError) as ei:
        fn()
    return ei.value.code


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


# --- 13 ca của spike ------------------------------------------------------------------------
def test_ca01_khong_token_thi_can_xac_nhan_du_tu_dien_co():
    svc, _, store = make()
    assert code_of(lambda: svc.verify_and_consume(None, sub=A, tool=TOOL, params=P)) == (
        ErrorCode.NEEDS_CONFIRMATION
    )
    assert code_of(lambda: svc.verify_and_consume("", sub=A, tool=TOOL, params=P)) == (
        ErrorCode.NEEDS_CONFIRMATION
    )
    assert not store.used


def test_ca02_bia_token_abc_def():
    svc, _, _ = make()
    assert code_of(lambda: svc.verify_and_consume("abc.def", sub=A, tool=TOOL, params=P)) == (
        ErrorCode.TOKEN_INVALID
    )


def test_ca03_token_gia_dung_dinh_dang_ky_sai_khoa():
    svc, clock, _ = make()
    forged, _ = issue_token(
        OTHER_KEY,
        sub=A,
        tool=TOOL,
        params_hash=params_hash(TOOL, P),
        now_epoch=clock.now.timestamp(),
        ttl_seconds=100,
    )
    assert code_of(lambda: svc.verify_and_consume(forged, sub=A, tool=TOOL, params=P)) == (
        ErrorCode.TOKEN_INVALID
    )


def test_ca04_cap_token_ghim_sub_tu_nguoi_goi_khong_tin_client():
    # `issue` chỉ nhận `sub` do tầng REST lấy từ JWT; tham số client (kể cả user_id) bị chuẩn hóa bỏ đi.
    svc, clock, _ = make()
    issued = svc.issue(A, TOOL, {**P, "user_id": B})
    payload = decode_token(
        issued.token, key=KEY, now_epoch=clock.now.timestamp(), max_ttl_seconds=120
    )
    assert payload.sub == A
    assert issued.params == P
    assert issued.ttl_seconds == 120


def test_ca05_ca06_tham_so_khac_bi_tu_choi_va_khong_lam_mat_token():
    svc, _, store = make()
    tok = svc.issue(A, TOOL, P).token
    big = {**P, "amount_vnd": 3_000_000}
    other_jar = {**P, "to_jar": "vui_choi"}
    assert code_of(lambda: svc.verify_and_consume(tok, sub=A, tool=TOOL, params=big)) == (
        ErrorCode.PARAMS_MISMATCH
    )
    assert code_of(lambda: svc.verify_and_consume(tok, sub=A, tool=TOOL, params=other_jar)) == (
        ErrorCode.PARAMS_MISMATCH
    )
    assert not store.used  # chưa tiêu jti
    # ca 7: đúng tham số thì vẫn dùng được token đó
    assert svc.verify_and_consume(tok, sub=A, tool=TOOL, params=P).sub == A


def test_ca07_dung_tham_so_dung_token():
    svc, _, store = make()
    payload = svc.verify_and_consume(svc.issue(A, TOOL, P).token, sub=A, tool=TOOL, params=P)
    assert payload.tool == TOOL and payload.sub == A
    assert payload.jti in store.used


def test_ca08_replay_cung_token():
    svc, _, _ = make()
    tok = svc.issue(A, TOOL, P).token
    svc.verify_and_consume(tok, sub=A, tool=TOOL, params=P)
    assert code_of(lambda: svc.verify_and_consume(tok, sub=A, tool=TOOL, params=P)) == (
        ErrorCode.TOKEN_REUSED
    )


def test_ca09_a_dung_token_cua_b():
    svc, _, store = make()
    tok_b = svc.issue(B, TOOL, P).token
    assert code_of(lambda: svc.verify_and_consume(tok_b, sub=A, tool=TOOL, params=P)) == (
        ErrorCode.TOKEN_INVALID
    )
    assert not store.used  # token của B vẫn còn nguyên cho B
    assert svc.verify_and_consume(tok_b, sub=B, tool=TOOL, params=P).sub == B


def test_ca10_token_bi_danh_cap_nhung_sub_do_tang_tin_cay_ghim():
    """Ghi lại GIỚI HẠN đã biết (spike ca 10): nếu kẻ trộm có token của B và tầng trên cho phép
    nó đặt sub=B thì token hợp lệ. Vì vậy `sub` luôn đến từ JWT (REST) hoặc interceptor (Gateway),
    không bao giờ từ thân yêu cầu; token hạn 2 phút và dùng một lần."""
    svc, _, _ = make()
    tok_b = svc.issue(B, TOOL, P).token
    assert svc.verify_and_consume(tok_b, sub=B, tool=TOOL, params=P).sub == B


def test_ca11_dang_nhap_gia_khong_toi_duoc_ham_cap_token():
    # Ở REST, JWT authorizer chặn trước (401) và handler thiếu claim sub thì UNAUTHENTICATED:
    # kiểm ở tests/unit/test_ledger_rest.py::test_thieu_claim_sub. Ở tầng này, `issue` yêu cầu sub.
    svc, _, _ = make()
    with pytest.raises(ValueError):
        svc.issue("", TOOL, P)


def test_ca12_token_het_han():
    svc, clock, store = make(ttl=1, max_ttl=120)
    tok = svc.issue(A, TOOL, P).token
    clock.advance(3)
    assert code_of(lambda: svc.verify_and_consume(tok, sub=A, tool=TOOL, params=P)) == (
        ErrorCode.TOKEN_EXPIRED
    )
    assert not store.used


def test_ca13_hop_le_sau_khi_cap_lai_token_moi():
    svc, clock, _ = make(ttl=1, max_ttl=120)
    old = svc.issue(A, TOOL, P).token
    clock.advance(3)
    svc2 = ConfirmService(lambda: KEY, MemoryJtiStore(), ttl_seconds=120, clock=clock)
    assert (
        svc2.verify_and_consume(svc2.issue(A, TOOL, P).token, sub=A, tool=TOOL, params=P).sub == A
    )
    assert code_of(lambda: svc.verify_and_consume(old, sub=A, tool=TOOL, params=P)) == (
        ErrorCode.TOKEN_EXPIRED
    )


# --- tấn công bổ sung ----------------------------------------------------------------------
def test_sua_payload_giu_nguyen_chu_ky():
    svc, _, _ = make()
    tok = svc.issue(A, TOOL, P).token
    body, sig = tok.split(".")
    payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    payload["sub"] = B
    forged = b64(json.dumps(payload, separators=(",", ":")).encode()) + "." + sig
    assert code_of(lambda: svc.verify_and_consume(forged, sub=B, tool=TOOL, params=P)) == (
        ErrorCode.TOKEN_INVALID
    )


def test_token_het_han_ky_sai_van_la_invalid_khong_phai_expired():
    clock = Clock()
    forged, _ = issue_token(
        OTHER_KEY,
        sub=A,
        tool=TOOL,
        params_hash=params_hash(TOOL, P),
        now_epoch=clock.now.timestamp() - 1000,
        ttl_seconds=5,
    )
    svc, _, _ = make()
    assert (
        code_of(lambda: svc.verify(forged, sub=A, tool=TOOL, params=P)) == ErrorCode.TOKEN_INVALID
    )


def test_token_cho_tool_khac():
    svc, clock, _ = make()
    tok, _ = issue_token(
        KEY,
        sub=A,
        tool="record_transaction",
        params_hash=params_hash(TOOL, P),
        now_epoch=clock.now.timestamp(),
        ttl_seconds=60,
    )
    assert code_of(lambda: svc.verify(tok, sub=A, tool=TOOL, params=P)) == ErrorCode.TOKEN_INVALID


def test_han_xa_hon_tran_ttl_bi_tu_choi_du_ky_dung_khoa():
    svc, clock, _ = make(ttl=120, max_ttl=120)
    tok, _ = issue_token(
        KEY,
        sub=A,
        tool=TOOL,
        params_hash=params_hash(TOOL, P),
        now_epoch=clock.now.timestamp(),
        ttl_seconds=3600,
    )
    assert code_of(lambda: svc.verify(tok, sub=A, tool=TOOL, params=P)) == ErrorCode.TOKEN_INVALID


@pytest.mark.parametrize(
    "token",
    ["a.b.c", ".", "x.", ".y", "không.dấu", "a b.c", "a" * 5000 + "." + "b" * 5000, "e30.e30"],
)
def test_token_rac_deu_invalid(token):
    svc, _, _ = make()
    assert code_of(lambda: svc.verify(token, sub=A, tool=TOOL, params=P)) == ErrorCode.TOKEN_INVALID


def test_tham_so_vo_ly_la_params_invalid_truoc_khi_xet_token():
    svc, _, _ = make()
    assert code_of(lambda: svc.issue(A, TOOL, {**P, "amount_vnd": -5})) == ErrorCode.PARAMS_INVALID
    assert (
        code_of(lambda: svc.verify("x.y", sub=A, tool=TOOL, params={})) == ErrorCode.PARAMS_INVALID
    )


def test_ttl_vuot_tran_bi_chan_khi_dung_dich_vu():
    with pytest.raises(ValueError):
        ConfirmService(lambda: KEY, MemoryJtiStore(), ttl_seconds=300, max_ttl_seconds=120)


def test_moi_token_co_jti_rieng():
    svc, _, _ = make()
    t1, t2 = svc.issue(A, TOOL, P).token, svc.issue(A, TOOL, P).token
    assert t1 != t2


def test_dua_hai_luong_cung_jti_chi_mot_thang():
    svc, _, _ = make()
    tok = svc.issue(A, TOOL, P).token
    results: list[str] = []

    def run() -> None:
        try:
            svc.verify_and_consume(tok, sub=A, tool=TOOL, params=P)
            results.append("ok")
        except YofinaError as exc:
            results.append(str(exc.code))

    threads = [threading.Thread(target=run) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 1
    assert results.count("TOKEN_REUSED") == 7


# --- kho jti DynamoDB và nhà cung cấp khóa --------------------------------------------------
class FakeDdbError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeDdb:
    def __init__(self, fail: str | None = None) -> None:
        self.items: dict[str, dict] = {}
        self.fail = fail
        self.calls: list[dict] = []

    def put_item(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise FakeDdbError(self.fail)
        jti = kw["Item"]["jti"]["S"]
        if jti in self.items:
            raise FakeDdbError("ConditionalCheckFailedException")
        self.items[jti] = kw["Item"]


def test_dynamo_store_put_item_co_dieu_kien_va_ttl():
    ddb = FakeDdb()
    store = DynamoJtiStore("bang-jti", ddb, ttl_grace_seconds=3600)
    store.consume("j1", 1_000)
    call = ddb.calls[0]
    assert call["TableName"] == "bang-jti"
    assert call["ConditionExpression"] == "attribute_not_exists(jti)"
    assert call["Item"]["ttl"]["N"] == "4600"
    with pytest.raises(YofinaError) as ei:
        store.consume("j1", 1_000)
    assert ei.value.code == ErrorCode.TOKEN_REUSED


def test_dynamo_store_loi_khac_thi_tu_choi_khong_ghi():
    store = DynamoJtiStore("bang-jti", FakeDdb(fail="ProvisionedThroughputExceededException"))
    with pytest.raises(YofinaError) as ei:
        store.consume("j1", 1_000)
    assert ei.value.code == ErrorCode.INTERNAL_ERROR


def test_secret_key_provider_cache_va_het_han_cache():
    calls: list[str] = []
    now = [0.0]

    class Sm:
        def get_secret_value(self, SecretId):
            calls.append(SecretId)
            return {"SecretString": f"khoa-{len(calls)}"}

    p = SecretKeyProvider("arn-bi-mat", Sm(), cache_seconds=300, monotonic=lambda: now[0])
    assert p.get() == b"khoa-1" and p.get() == b"khoa-1"
    assert len(calls) == 1
    now[0] = 301
    assert p.get() == b"khoa-2"


def test_secret_rong_thi_loi():
    class Sm:
        def get_secret_value(self, SecretId):
            return {"SecretString": ""}

    with pytest.raises(YofinaError):
        SecretKeyProvider("x", Sm()).get()
