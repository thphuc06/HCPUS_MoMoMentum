"""Client Data API với client boto3 giả: kiểu dữ liệu, retry resume, thứ tự transaction, rollback."""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from yofina_core.config import Config
from yofina_core.db import DataApi, DataApiSettings, parse_records, to_parameter
from yofina_core.errors import ErrorCode, YofinaError


class AwsError(Exception):
    def __init__(self, code: str, msg: str = "") -> None:
        super().__init__(f"{code}: {msg}")
        self.response = {"Error": {"Code": code, "Message": msg}}


class FakeRds:
    """Ghi lại mọi lệnh gọi; `script` là hàng đợi kết quả hoặc ngoại lệ cho execute_statement."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.script: list = []
        self.fail_commit: Exception | None = None
        self.fail_begin: list[Exception] = []

    def _rec(self, op: str, kw: dict) -> None:
        self.calls.append((op, kw))

    def execute_statement(self, **kw):
        self._rec("execute", kw)
        item = self.script.pop(0) if self.script else {"records": [], "columnMetadata": []}
        if isinstance(item, Exception):
            raise item
        return item

    def batch_execute_statement(self, **kw):
        self._rec("batch", kw)
        return {"updateResults": []}

    def begin_transaction(self, **kw):
        self._rec("begin", kw)
        if self.fail_begin:
            raise self.fail_begin.pop(0)
        return {"transactionId": "tx-1"}

    def commit_transaction(self, **kw):
        self._rec("commit", kw)
        if self.fail_commit:
            raise self.fail_commit
        return {"transactionStatus": "Transaction Committed"}

    def rollback_transaction(self, **kw):
        self._rec("rollback", kw)
        return {}

    def ops(self) -> list[str]:
        return [c[0] for c in self.calls]


SETTINGS = DataApiSettings(
    cluster_arn="arn:cluster",
    secret_arn="arn:secret-app",
    database="db",
    resume_max_wait_seconds=10,
    resume_sleep_seconds=2,
)


def api(fake: FakeRds, clock: list[float] | None = None) -> tuple[DataApi, list[float]]:
    t = clock if clock is not None else [0.0]
    sleeps: list[float] = []

    def sleep(s: float) -> None:
        sleeps.append(s)
        t[0] += s

    return DataApi(SETTINGS, fake, sleep=sleep, monotonic=lambda: t[0]), sleeps


# --- tham số -------------------------------------------------------------------------------
def test_tham_so_kieu_co_ban():
    assert to_parameter("a", None)["value"] == {"isNull": True}
    assert to_parameter("a", True)["value"] == {"booleanValue": True}
    assert to_parameter("a", 5)["value"] == {"longValue": 5}
    assert to_parameter("a", "x")["value"] == {"stringValue": "x"}
    d = to_parameter("a", Decimal("12.50"))
    assert d["value"] == {"stringValue": "12.50"} and d["typeHint"] == "DECIMAL"
    assert to_parameter("a", date(2026, 11, 21))["value"] == {"stringValue": "2026-11-21"}
    assert to_parameter("a", {"k": "ế"})["value"] == {"stringValue": '{"k": "ế"}'}


def test_datetime_doi_sang_utc_va_bat_buoc_co_mui_gio():
    tz7 = timezone(timedelta(hours=7))
    v = to_parameter("t", datetime(2026, 11, 21, 10, 0, tzinfo=tz7))["value"]["stringValue"]
    assert v.startswith("2026-11-21T03:00:00") and v.endswith("+00:00")
    with pytest.raises(ValueError):
        to_parameter("t", datetime(2026, 11, 21, 10, 0))


def test_float_bi_tu_choi():
    with pytest.raises(TypeError):
        to_parameter("amount", 1.5)


# --- kết quả -------------------------------------------------------------------------------
def test_parse_records_chuyen_kieu_theo_metadata():
    resp = {
        "columnMetadata": [
            {"label": "balance", "typeName": "numeric"},
            {"label": "at", "typeName": "timestamptz"},
            {"label": "d", "typeName": "date"},
            {"label": "j", "typeName": "jsonb"},
            {"label": "n", "typeName": "int4"},
            {"label": "s", "typeName": "text"},
            {"label": "z", "typeName": "text"},
        ],
        "records": [
            [
                {"stringValue": "380000"},
                {"stringValue": "2026-11-21 02:13:37.658608"},
                {"stringValue": "2026-11-21"},
                {"stringValue": '{"a": [1, 2]}'},
                {"longValue": 3},
                {"stringValue": "Ăn uống"},
                {"isNull": True},
            ]
        ],
    }
    (row,) = parse_records(resp)
    assert row["balance"] == Decimal("380000") and isinstance(row["balance"], Decimal)
    assert row["at"] == datetime(2026, 11, 21, 2, 13, 37, 658608, tzinfo=UTC)
    assert row["d"] == date(2026, 11, 21)
    assert row["j"] == {"a": [1, 2]}
    assert row["n"] == 3 and row["s"] == "Ăn uống" and row["z"] is None


# --- retry ---------------------------------------------------------------------------------
def test_retry_database_resuming_roi_thanh_cong():
    fake = FakeRds()
    fake.script = [AwsError("DatabaseResumingException"), AwsError("DatabaseResumingException"), {}]
    db, sleeps = api(fake)
    assert db.query("SELECT 1") == []
    assert fake.ops() == ["execute"] * 3
    assert sleeps == [2, 2]


def test_het_ngan_sach_resume_thi_database_unavailable():
    fake = FakeRds()
    fake.script = [AwsError("DatabaseResumingException")] * 50
    db, sleeps = api(fake)
    with pytest.raises(YofinaError) as ei:
        db.query("SELECT 1")
    assert ei.value.code == ErrorCode.DATABASE_UNAVAILABLE
    assert sum(sleeps) <= SETTINGS.resume_max_wait_seconds


def test_loi_khac_khong_retry_va_khong_ro_chi_tiet_sql():
    fake = FakeRds()
    fake.script = [AwsError("BadRequestException", "syntax error at or near SELECT secret_table")]
    db, sleeps = api(fake)
    with pytest.raises(YofinaError) as ei:
        db.query("SELECT 1")
    assert ei.value.code == ErrorCode.INTERNAL_ERROR
    assert "secret_table" not in ei.value.message
    assert sleeps == [] and fake.ops() == ["execute"]


# --- mức log của lỗi Data API (#39) -------------------------------------------------------------------------------------------
def _db_records(caplog, fake: FakeRds) -> list[logging.LogRecord]:
    db, _ = api(fake)
    with caplog.at_level(logging.INFO, logger="yofina_core.db"), pytest.raises(YofinaError) as ei:
        db.query("SELECT 1")
    assert ei.value.code == ErrorCode.INTERNAL_ERROR  # mã nghiệp vụ do tầng gọi đổi (roadmap_logic.db_business_error), không đổi ở đây
    return [r for r in caplog.records if r.name == "yofina_core.db"]


@pytest.mark.parametrize(
    "message",
    [
        # đúng dạng Data API trả trên Aurora thật: chữ có dấu của thông điệp RAISE đã bị thay bằng U+FFFD trước khi tới Lambda
        "ERROR: ROADMAP_VERSION_CONFLICT: b\ufffd\ufffd\ufffdn n\ufffd\ufffdy kh\ufffd\ufffdng c\ufffd\ufffdn; SQLState: P0001",
        "ERROR: ROADMAP_NOT_FOUND: không có phiên bản này\n  Where: PL/pgSQL function app_decide_roadmap_version; SQLState: P0001",
        "ERROR: PARAMS_INVALID: khoảng thời gian không hợp lệ; SQLState: P0001",
    ],
    ids=["conflict_hong_dau", "not_found", "params_invalid"],
)
def test_loi_nghiep_vu_4xx_cua_ham_sql_ghi_warning_khong_phai_error(caplog, message):
    """Lỗi nghiệp vụ dự kiến (`RAISE EXCEPTION 'MÃ: ...'` với MÃ là `ErrorCode` nhóm 4xx) ghi WARNING, không có dòng ERROR (ERROR dành
    cho lỗi hệ thống). Dòng log là JSON giữ nguyên chữ tiếng Việt (không `\\uXXXX`)."""
    fake = FakeRds()
    fake.script = [AwsError("BadRequestException", message)]
    records = _db_records(caplog, fake)
    assert [r.levelno for r in records] == [logging.WARNING]
    line = json.loads(records[0].getMessage())
    code = message.split(": ")[1]
    assert line["msg"] == "data_api_business_error" and line["code"] == code and line["aws_code"] == "BadRequestException"
    assert message.split("; SQLState")[0].split(f"{code}: ")[1].split("\n")[0] in records[0].getMessage()  # chữ gốc, không thoát mã
    assert "\\u" not in records[0].getMessage()


@pytest.mark.parametrize(
    "message",
    [
        "syntax error at or near SELECT secret_table",
        "ERROR: INTERNAL_ERROR: còn dữ liệu của người dùng sau khi xóa; SQLState: P0001",  # mã 5xx do hàm SQL ném: vẫn là lỗi hệ thống
        "ERROR: FOO_BAR: không phải mã của ErrorCode; SQLState: P0001",
        'ERROR: duplicate key value violates unique constraint "x"; SQLState: 23505',
    ],
    ids=["cu_phap", "internal_error", "ma_la", "trung_khoa"],
)
def test_loi_he_thong_cua_data_api_van_ghi_error(caplog, message):
    fake = FakeRds()
    fake.script = [AwsError("BadRequestException", message)]
    records = _db_records(caplog, fake)
    assert [r.levelno for r in records] == [logging.ERROR]
    assert records[0].getMessage().startswith("data_api_error code=BadRequestException")


def test_query_max_rows_bao_loi_khi_thieu_limit():
    fake = FakeRds()
    fake.script = [
        {
            "columnMetadata": [{"label": "a", "typeName": "int4"}],
            "records": [[{"longValue": i}] for i in range(5)],
        }
    ]
    db, _ = api(fake)
    with pytest.raises(YofinaError):
        db.query("SELECT a FROM t", max_rows=3)


def test_execute_gui_dung_tham_so_secret_va_database():
    fake = FakeRds()
    db, _ = api(fake)
    db.query("SELECT * FROM app_get_jar_view(:uid)", {"uid": "u1"})
    kw = fake.calls[0][1]
    assert kw["resourceArn"] == "arn:cluster" and kw["secretArn"] == "arn:secret-app"
    assert kw["database"] == "db" and kw["includeResultMetadata"] is True
    assert kw["parameters"] == [{"name": "uid", "value": {"stringValue": "u1"}}]
    assert "transactionId" not in kw


# --- transaction ---------------------------------------------------------------------------
def test_transaction_thu_tu_begin_set_config_cau_lenh_commit():
    fake = FakeRds()
    db, _ = api(fake)
    with db.transaction("user-a") as tx:
        tx.execute("UPDATE jars SET balance_vnd = 1 WHERE user_id = :uid", {"uid": "user-a"})
        tx.batch("INSERT INTO t VALUES (:a)", [{"a": 1}, {"a": 2}])
    assert fake.ops() == ["begin", "execute", "execute", "batch", "commit"]
    set_cfg = fake.calls[1][1]
    assert "set_config('app.user_id', :uid, true)" in set_cfg["sql"]
    assert set_cfg["parameters"][0]["value"] == {"stringValue": "user-a"}
    assert set_cfg["transactionId"] == "tx-1"
    assert fake.calls[3][1]["transactionId"] == "tx-1"
    assert "rollback" not in fake.ops()


def test_loi_trong_transaction_thi_rollback_va_khong_commit():
    fake = FakeRds()
    db, _ = api(fake)
    with pytest.raises(RuntimeError), db.transaction("user-a"):
        raise RuntimeError("boom")
    assert fake.ops() == ["begin", "execute", "rollback"]


def test_commit_that_bai_van_rollback_trong_finally():
    fake = FakeRds()
    fake.fail_commit = AwsError("InternalServerErrorException")
    db, _ = api(fake)
    with pytest.raises(YofinaError), db.transaction("user-a"):
        pass
    assert fake.ops()[-1] == "rollback"


def test_lenh_trong_transaction_loi_thi_rollback():
    fake = FakeRds()
    fake.script = [{}, AwsError("BadRequestException", "violates check constraint")]
    db, _ = api(fake)
    with pytest.raises(YofinaError), db.transaction("u") as tx:
        tx.execute("UPDATE jars SET x = 1")
    assert fake.ops() == ["begin", "execute", "execute", "rollback"]


def test_begin_transaction_cung_retry_resume():
    fake = FakeRds()
    fake.fail_begin = [AwsError("DatabaseResumingException")]
    db, sleeps = api(fake)
    with db.transaction("u"):
        pass
    assert sleeps == [2] and fake.ops().count("begin") == 2


def test_transaction_yeu_cau_user_id():
    db, _ = api(FakeRds())
    with pytest.raises(ValueError), db.transaction(""):
        pass


# --- cấu hình ------------------------------------------------------------------------------
def test_settings_tu_bien_moi_truong_va_thieu_thi_bao_loi():
    env = {
        "YOFINA_DB_CLUSTER_ARN": "arn:c",
        "YOFINA_DB_APP_SECRET_ARN": "arn:s",
        "YOFINA_DB_NAME": "yofina",
        "YOFINA_DB_RESUME_MAX_WAIT_SECONDS": "12",
    }
    s = DataApiSettings.from_config(Config(env=env))
    assert (s.cluster_arn, s.secret_arn, s.database) == ("arn:c", "arn:s", "yofina")
    assert s.resume_max_wait_seconds == 12.0
    with pytest.raises(Exception, match="db_cluster_arn"):
        DataApiSettings.from_config(Config(env={}))
