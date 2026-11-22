"""F6 trên PostgreSQL thật: persona `vy` (thu nhập ngoài ví) cho kịch bản demo "độ phủ dữ liệu tăng sau khi nạp sao kê ngân hàng khác".

Nạp `vy` bằng chính đường của `POST /demo/reset` (`LedgerService.reset_demo`: bộ sinh -> `reset_user`), rồi:

1. thu nhập ngoài ví nằm trong sổ cái đúng dạng (external, không hũ), số dư mỗi hũ = tổng dòng trả bằng hũ;
2. độ phủ TRƯỚC khi nạp (`app_get_data_coverage`, cùng số với `app_get_forecast_context`) nằm trong dải mục tiêu;
3. khử trùng của luồng nạp (`app_find_ingest_matches`, cửa sổ mặc định 3 ngày) bỏ đúng hai dòng tiền vào của sao kê và giữ mọi
   dòng chi; ghi các dòng chi còn lại như `confirm_rows` ghi (external, có hũ);
4. độ phủ SAU khi nạp nằm trong dải mục tiêu, bằng số dựng từ dữ liệu bộ sinh, số dư hũ không đổi;
5. đặt lại demo đưa độ phủ về như cũ; minh vẫn phủ trọn (ví đóng).

Chạy cùng bộ local_pg (lệnh ở docstring của conftest.py).
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

import pytest
from conftest import ANCHOR
from persona_coverage import AFTER_RANGE, BEFORE_RANGE, coverage_facts

from personas import generate, generate_out_of_wallet
from yofina_core import ingest
from yofina_ml import quality
from yofina_ml.types import CoverageInputs

VY, MINH = "sub-vy", "sub-minh"
TZ = "Asia/Ho_Chi_Minh"
WIN = 330  # forecast_history_window_days
DEDUPE_WINDOW = 3  # ingest_dedupe_window_days mặc định

SQL_COVERAGE = (
    "SELECT * FROM app_get_data_coverage(CAST(:uid AS text), CAST(:now AS timestamptz), CAST(:tz AS text), "
    "CAST(:win AS integer))"
)
SQL_MATCH = (
    "SELECT * FROM app_find_ingest_matches(:uid, CAST(:rows AS jsonb), CAST(:win AS integer))"
)


def reset_vy(env):
    return env.svc.reset_demo(VY, "vy", trace_id="t" * 8)


def coverage_row(env, user):
    return env.db.query(
        SQL_COVERAGE, {"uid": user, "now": env.clock.now, "tz": TZ, "win": WIN}, max_rows=1
    )[0]


def facts_of(row) -> dict[str, int]:
    return {
        k: int(row[k]) for k in ("income_vnd", "spend_vnd", "balance_start_vnd", "balance_end_vnd")
    }


def balances(env, user) -> dict[str, int]:
    return {j["code"]: int(j["balance_vnd"]) for j in env.repo.jar_view(user).jars}


def matches(env, user, rows, win=DEDUPE_WINDOW):
    return env.db.query(
        SQL_MATCH, {"uid": user, "rows": json.dumps(rows), "win": win}, max_rows=2000
    )


def candidates(rows, anchor: date):
    return [
        {
            "idx": i,
            "app_date": r.app_date(anchor).isoformat(),
            "amount_vnd": r.amount_vnd,
            "counterparty": r.merchant,
            "kind": r.kind,
        }
        for i, r in enumerate(rows)
    ]


def write_external_expense(env, user, row, anchor: date) -> None:
    """Ghi một dòng chi ngoài ví như `confirm_rows`: funding external, có hũ, nguồn ingest, không đổi số dư hũ."""
    with env.master() as m:
        m.execute(
            "INSERT INTO transactions (id, user_id, occurred_at, app_date, kind, jar_code, amount_vnd, merchant, source, "
            "tx_type, funding_source) VALUES (%s, %s, %s, %s, 'expense', %s, %s, %s, 'ingest', %s, 'external')",
            [str(uuid.uuid4()), user, env.clock.now, row.app_date(anchor), row.jar_code,
             -row.amount_vnd, row.merchant, row.tx_type],
        )  # fmt: skip


def test_vy_thu_nhap_ngoai_vi_trong_so_cai_va_so_du_hu_dung_bat_bien(env):
    reset_vy(env)
    data = generate("vy", anchor=ANCHOR)
    with env.master() as m:
        ext = m.execute(
            "SELECT kind, jar_code, amount_vnd, funding_source, tx_type, app_date, transfer_id, obligation_id "
            "FROM transactions WHERE user_id = %s AND funding_source = 'external' ORDER BY app_date",
            [VY],
        ).fetchall()
        by_jar = dict(
            m.execute(
                "SELECT j.code, coalesce((SELECT sum(t.amount_vnd) FROM transactions t WHERE t.user_id = j.user_id "
                "AND t.jar_code = j.code AND t.funding_source = 'jar'), 0) FROM jars j WHERE j.user_id = %s",
                [VY],
            ).fetchall()
        )
    assert [(r[0], r[1], int(r[2]), r[3], r[4], r[5], r[6], r[7]) for r in ext] == [
        ("income", None, 4_800_000, "external", "income_other", date(2026, 10, 18), None, None),
        ("income", None, 4_800_000, "external", "income_other", date(2026, 11, 18), None, None),
    ]
    bal = balances(env, VY)
    assert {c: int(v) for c, v in by_jar.items()} == bal  # số dư mỗi hũ = tổng dòng trả bằng hũ
    assert {j.code: j.balance_vnd for j in data.jars} == {
        c: bal[c] for c in (j.code for j in data.jars)
    }


def test_vy_do_phu_truoc_nap_trong_dai(env):
    reset_vy(env)
    row = coverage_row(env, VY)
    facts = facts_of(row)
    before = ingest.coverage_ratio(row)
    assert before == quality.data_coverage(CoverageInputs(**facts))
    assert BEFORE_RANGE[0] <= before <= BEFORE_RANGE[1], before
    # DB và bộ sinh cho cùng thành phần (công thức dựng lại trong test đơn vị khớp SQL)
    assert facts == coverage_facts(generate("vy", anchor=ANCHOR))
    assert int(row["external_spend_vnd"]) == 0 and int(row["external_income_vnd"]) == 9_600_000


def test_vy_nap_sao_ke_do_phu_len_dai_sau_va_khu_trung_dung(env):
    reset_vy(env)
    data = generate("vy", anchor=ANCHOR)
    oow = generate_out_of_wallet("vy", anchor=ANCHOR, data=data)
    stmt = oow.source("statement")
    before_row = coverage_row(env, VY)
    before = ingest.coverage_ratio(before_row)
    bal_before = balances(env, VY)

    # khử trùng với sổ cái đã có: đúng hai dòng tiền vào trùng thu nhập ngoài ví, không dòng chi nào
    got = matches(env, VY, candidates(stmt.rows, ANCHOR))
    matched = {int(r["idx"]) for r in got}
    assert matched == {i for i, r in enumerate(stmt.rows) if r.kind == "income"}
    assert all(r["funding_source"] == "external" for r in got)
    new_rows = [r for i, r in enumerate(stmt.rows) if i not in matched]
    assert len(new_rows) == len(stmt.expenses) and all(r.kind == "expense" for r in new_rows)

    for r in new_rows:
        write_external_expense(env, VY, r, ANCHOR)

    after_row = coverage_row(env, VY)
    after = ingest.coverage_ratio(after_row)
    spent = sum(r.amount_vnd for r in stmt.expenses)
    assert int(after_row["external_spend_vnd"]) == spent
    assert int(after_row["income_vnd"]) == int(
        before_row["income_vnd"]
    )  # tiền vào đã khử trùng: không cộng đôi
    assert AFTER_RANGE[0] <= after <= AFTER_RANGE[1], after
    assert after > before
    assert after == quality.data_coverage(CoverageInputs(**facts_of(after_row)))
    assert facts_of(after_row) == coverage_facts(data, extra_expenses=spent)
    assert balances(env, VY) == bal_before  # dòng external không đổi số dư hũ nào

    # nạp tiếp ảnh biên lai (hôm qua): không trùng sao kê đã nạp; độ phủ tăng nhưng chưa tới 100%
    receipts = oow.source("receipts")
    assert matches(env, VY, candidates(receipts.rows, ANCHOR)) == []
    for r in receipts.expenses:
        write_external_expense(env, VY, r, ANCHOR)
    both = ingest.coverage_ratio(coverage_row(env, VY))
    assert after < both < 1.0


def test_vy_dat_lai_xoa_dong_ngoai_vi_da_nap_va_minh_van_phu_tron(env):
    reset_vy(env)
    before = ingest.coverage_ratio(coverage_row(env, VY))
    oow = generate_out_of_wallet("vy", anchor=ANCHOR)
    for r in oow.source("statement").expenses:
        write_external_expense(env, VY, r, ANCHOR)
    assert ingest.coverage_ratio(coverage_row(env, VY)) > before
    reset_vy(env)  # POST /demo/reset: xóa sạch (cả dòng external đã nạp), sinh lại
    assert ingest.coverage_ratio(coverage_row(env, VY)) == before
    with env.master() as m:
        n = m.execute(
            "SELECT count(*) FROM transactions WHERE user_id = %s AND funding_source = 'external' AND kind = 'expense'",
            [VY],
        ).fetchone()[0]
    assert n == 0
    # ví đóng của minh: phủ trọn, nên câu chuyện nạp dữ liệu chỉ kể được trên vy
    env.reset(MINH)
    assert ingest.coverage_ratio(coverage_row(env, MINH)) == 1.0


def test_vy_so_ngay_khong_vuot_cua_so_du_bao():
    data = generate("vy", anchor=ANCHOR)
    assert data.history_days <= WIN
    oow = generate_out_of_wallet("vy", anchor=ANCHOR, data=data)
    assert max(r.days_ago for s in oow.sources for r in s.rows) <= data.history_days
    assert min(r.app_date(ANCHOR) for s in oow.sources for r in s.rows) >= ANCHOR - timedelta(
        days=data.history_days
    )


@pytest.mark.parametrize("name", ["minh", "lan", "khoa"])
def test_ba_persona_cu_phu_tron_theo_cong_thuc_0050(env, name):
    """Ví đóng: mọi thu nhập là lương vào ví nên độ phủ 100% (không có dòng external)."""
    env.reset(f"sub-{name}")
    row = coverage_row(env, f"sub-{name}")
    assert int(row["external_income_vnd"]) == 0 and int(row["external_spend_vnd"]) == 0
    assert ingest.coverage_ratio(row) == 1.0
