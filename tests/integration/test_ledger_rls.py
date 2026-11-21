"""Row Level Security thật trên Aurora, bằng secret của role `yofina_app` (không phải master):
không `set_config` thì không thấy dòng nào; người dùng này không đọc/ghi được dữ liệu người dùng kia."""

from __future__ import annotations

import pytest
from _yofina import REGION, ssm_param

from yofina_core.db import DataApi, DataApiSettings
from yofina_core.errors import YofinaError

pytestmark = pytest.mark.usefixtures("fresh")


@pytest.fixture(scope="module")
def db(sess):
    settings = DataApiSettings(
        cluster_arn=ssm_param("db/cluster-arn", sess=sess),
        secret_arn=ssm_param("db/app-secret-arn", sess=sess),
        database=ssm_param("db/name", sess=sess),
    )
    return DataApi(settings, region=REGION)


def test_chay_bang_role_yofina_app(db):
    (row,) = db.query("SELECT current_user AS who, current_setting('is_superuser') AS su")
    assert row["who"] == "yofina_app" and row["su"] == "off"


def test_khong_set_config_thi_khong_thay_dong_nao(db):
    for table in ("users", "jars", "transactions", "audit_events", "turn_blocks"):
        (row,) = db.query(f"SELECT count(*) AS n FROM {table}")
        assert row["n"] == 0, table


def test_nguoi_dung_nay_khong_doc_duoc_nguoi_dung_kia(db, subs):
    with db.transaction(subs["lan"]) as tx:
        mine = tx.execute("SELECT count(*) AS n FROM jars")[0]["n"]
        theirs = tx.execute(
            "SELECT count(*) AS n FROM jars WHERE user_id = :other", {"other": subs["minh"]}
        )[0]["n"]
        txs = tx.execute(
            "SELECT count(*) AS n FROM transactions WHERE user_id = :other", {"other": subs["minh"]}
        )[0]["n"]
    assert (mine, theirs, txs) == (5, 0, 0)


def test_ham_doc_theo_user_id_chi_tra_du_lieu_cua_user_do(db, subs):
    rows = db.query("SELECT * FROM app_get_jar_view(:u)", {"u": subs["lan"]})
    assert len(rows) == 5
    assert db.query("SELECT * FROM app_get_jar_view(:u)", {"u": "khong-ton-tai"}) == []


def test_khong_ghi_ho_duoc_nguoi_khac_va_khong_sua_duoc_so_cai(db, subs):
    with pytest.raises(YofinaError), db.transaction(subs["lan"]) as tx:
        tx.execute(
            "UPDATE jars SET balance_vnd = 0 WHERE user_id = :other", {"other": subs["minh"]}
        )
        # UPDATE lên dòng không thấy được thì 0 dòng, không lỗi: ép lỗi bằng INSERT hộ người khác
        tx.execute(
            "INSERT INTO audit_events (user_id, event_type, outcome) VALUES (:other, 'x', 'ok')",
            {"other": subs["minh"]},
        )
    with pytest.raises(YofinaError), db.transaction(subs["lan"]) as tx:
        tx.execute(
            "UPDATE transactions SET amount_vnd = 1"
        )  # yofina_app không có quyền UPDATE sổ cái


def test_yofina_app_khong_tat_duoc_rls(db, subs):
    with pytest.raises(YofinaError), db.transaction(subs["lan"]) as tx:
        tx.execute("ALTER TABLE jars DISABLE ROW LEVEL SECURITY")
