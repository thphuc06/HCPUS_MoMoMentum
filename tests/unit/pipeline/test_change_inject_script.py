"""scripts/inject_behavior_shift.py: kế hoạch lấy số từ dữ liệu của tài khoản, sao kê CSV đọc được, luồng REST đúng thứ tự (đối tượng giả),
và kế hoạch của script khiến PELT xác nhận (hai tuần lệch) hoặc không (một khoản lớn đơn lẻ)."""

from __future__ import annotations

import csv
import importlib.util
import io
import sys
from datetime import date, timedelta

import numpy as np
import pytest
from conftest import REPO

from yofina_ml import change as ml

APP_DATE = date(2026, 11, 21)
P = ml.load_params()


@pytest.fixture(scope="module")
def sc():
    scripts = str(REPO / "scripts")
    sys.path.insert(0, scripts)
    try:
        spec = importlib.util.spec_from_file_location(
            "inject_behavior_shift", REPO / "scripts" / "inject_behavior_shift.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod  # dataclass cần tra module theo tên
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.modules.pop("inject_behavior_shift", None)
        sys.path.remove(scripts)


def history(sc, weeks=12, level=500_000, per_week=6, seed=0):
    """Lịch sử ổn định `weeks` tuần đầy đủ (cắt lùi từ hôm qua), mỗi tuần `per_week` khoản."""
    rng = np.random.default_rng(seed)
    out = []
    last = APP_DATE - timedelta(days=1)
    for k in range(weeks):
        end = last - timedelta(days=7 * k)
        total = level * (1 + 0.1 * rng.standard_normal())
        w = np.exp(rng.normal(0, 0.4, per_week))  # khoản chi trong tuần không đều nhau như thật
        for i in range(per_week):
            out.append(
                sc.Spend(
                    end - timedelta(days=i), int(total * w[i] / w.sum() // 1000 * 1000), "Cơm tấm"
                )
            )
    return out


def daily_of(spends, extra=()):
    first = min(s.day for s in spends)
    n = (APP_DATE - first).days
    arr = np.zeros(n)
    for s in spends:
        arr[(s.day - first).days] += s.amount_vnd
    for r in extra:
        arr[(r.day - first).days] += r.amount_vnd
    return arr


def test_spend_of_chi_lay_chi_tru_tien_hu_khong_gan_nghia_vu(sc):
    base = {
        "kind": "expense",
        "jar": "an_uong",
        "app_date": "2026-11-20",
        "amount_vnd": -50_000,
        "merchant": "A",
    }
    assert sc.spend_of(base, "an_uong") == sc.Spend(date(2026, 11, 20), 50_000, "A")
    assert sc.spend_of({**base, "obligation_id": "x"}, "an_uong") is None
    assert sc.spend_of({**base, "funding_source": "credit"}, "an_uong") is None
    assert sc.spend_of({**base, "kind": "income"}, "an_uong") is None
    assert sc.spend_of({**base, "jar": "di_lai"}, "an_uong") is None


def test_weekly_va_baseline_lay_tu_du_lieu(sc):
    h = history(sc, weeks=10, level=500_000)
    w = sc.weekly_totals(h, APP_DATE, 10)
    assert len(w) == 10 and all(x > 0 for x in w)
    base = sc.baseline_weekly(h, APP_DATE, 2)
    assert base == pytest.approx(500_000, rel=0.1)
    with pytest.raises(sc.ShiftError, match="chưa có khoản chi"):
        sc.baseline_weekly([], APP_DATE, 2)
    with pytest.raises(sc.ShiftError, match="Chưa đủ lịch sử"):
        sc.baseline_weekly(history(sc, weeks=3), APP_DATE, 2)


def test_ke_hoach_dua_hai_tuan_cuoi_toi_dung_boi_so_va_tat_dinh(sc):
    h = history(sc)
    plan = sc.plan_shift(h, APP_DATE, factor=2.0, shift_weeks=2)
    assert plan == sc.plan_shift(
        h, APP_DATE, factor=2.0, shift_weeks=2
    )  # cùng đầu vào, cùng kế hoạch
    base = sc.baseline_weekly(h, APP_DATE, 2)
    last = APP_DATE - timedelta(days=1)
    assert all(last - timedelta(days=13) <= r.day <= last for r in plan)  # chỉ trong hai tuần cuối
    assert all(r.amount_vnd % 1000 == 0 and r.amount_vnd > 0 for r in plan)
    assert {r.description for r in plan} == {"Cơm tấm"}  # nơi chi lấy từ lịch sử của hũ
    now = sc.weekly_totals(h + [sc.Spend(r.day, r.amount_vnd, None) for r in plan], APP_DATE, 2)
    assert all(x == pytest.approx(2.0 * base, rel=0.001) for x in now)
    with pytest.raises(sc.ShiftError, match="lớn hơn 1"):
        sc.plan_shift(h, APP_DATE, factor=1.0)


def test_ke_hoach_khong_them_gi_khi_tuan_cuoi_da_dat_muc(sc):
    h = history(sc)
    big = [sc.Spend(APP_DATE - timedelta(days=d), 400_000, "x") for d in range(1, 15)]
    with pytest.raises(sc.ShiftError, match="không có gì để thêm"):
        sc.plan_shift([*h, *big], APP_DATE, factor=2.0)


def test_hai_tuan_lech_duoc_pelt_xac_nhan_con_mot_khoan_lon_don_le_thi_khong(sc):
    h = history(sc, weeks=12)
    shift = sc.plan_shift(h, APP_DATE, factor=2.4, shift_weeks=2)
    s = ml.prepare_weekly(daily_of(h, shift), P)
    hit = ml.detect_confirmed(s, P)
    assert hit is not None and hit.direction == "up" and hit.weeks_held == 2
    one = sc.plan_one_off(h, APP_DATE, multiple=10, shift_weeks=2)
    assert len(one) == 1 and one[0].amount_vnd == pytest.approx(10 * 500_000, rel=0.1)
    s1 = ml.prepare_weekly(daily_of(h, one), P)
    assert ml.detect_confirmed(s1, P) is None and ml.detect_suspect(s1, P) is None
    assert one[0].day in [APP_DATE - timedelta(days=d) for d in range(1, 8)]  # nằm trong tuần cuối


def test_csv_doc_duoc_dung_dinh_dang_vcb_va_khong_trung_noi_dung_giua_hai_lan(sc):
    plan = [
        sc.PlannedRow(date(2026, 11, 10), 1_234_000, "Cơm tấm"),
        sc.PlannedRow(date(2026, 11, 12), 99_000, "Phở"),
    ]
    data = sc.build_csv(plan, run_id="a" * 32)
    assert data.startswith("﻿".encode())
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    assert rows[0] == sc.CSV_HEADER and len(rows) == 3
    assert rows[1][1] == "10/11/2026" and rows[1][3] == "1,234,000" and rows[1][4] == ""
    assert "CƠM TẤM" in rows[1][5]
    assert data != sc.build_csv(plan, run_id="b" * 32)
    # đọc được bằng bộ đọc CSV thật của pipeline nạp: tiêu đề nhận ra, ánh xạ cột dùng được, hai dòng chi đúng số tiền
    sys.path.insert(0, str(REPO / "pipelines" / "ingest"))
    try:
        from yofina_ingest import csvparse

        table = csvparse.read_table(data, max_rows=100)
        mapping = csvparse.map_header(table.header)
        assert table.header_found and mapping.usable and len(table.rows) == 2
        parsed = csvparse.parse_rows(table, mapping, today=APP_DATE)
        assert [(r.amount_vnd, r.direction, r.date) for r in parsed] == [
            (1_234_000, "out", date(2026, 11, 10)),
            (99_000, "out", date(2026, 11, 12)),
        ]
    finally:
        sys.path.remove(str(REPO / "pipelines" / "ingest"))


class FakeApi:
    """REST giả mô phỏng worker nạp: ghi lại thứ tự các lời gọi."""

    def __init__(self, rows, *, final="review", dup=0):
        self.calls: list[tuple[str, str, object]] = []
        self.rows, self.final, self.dup = rows, final, dup
        self.polls = 0

    def post(self, path, body):
        self.calls.append(("POST", path, body))
        if path == "/ingest/uploads":
            return {"job_id": "job-1", "url": "https://s3.invalid", "fields": {"key": "k"}}
        if path == "/ingest/confirmations":
            return {"confirm_token": "tok", "params": body["params"]}
        if path == "/ingest/actions":
            return {"type": "receipt_action"}
        return {}

    def get(self, path):
        self.calls.append(("GET", path, None))
        self.polls += 1
        if self.polls < 2:
            return {"status": "processing", "progress": 40}
        rows = [
            {"row_id": f"r{i}", "kind": "expense", "review_status": "pending", "amount_vnd": a}
            for i, a in enumerate(self.rows)
        ] + [
            {"row_id": f"d{i}", "kind": "expense", "review_status": "duplicate", "amount_vnd": 1}
            for i in range(self.dup)
        ]
        return {
            "status": self.final,
            "error_code": "INGEST_NOT_FINANCIAL",
            "review": {"data": {"rows": rows, "jars": [{"code": "an_uong"}, {"code": "di_lai"}]}},
        }

    def upload(self, up, data, mime):
        self.calls.append(("UPLOAD", up["url"], len(data)))


def test_luong_rest_dung_thu_tu_va_chot_kem_token(sc, monkeypatch):
    monkeypatch.setattr(sc.time, "sleep", lambda s: None)
    api = FakeApi([100_000, 250_000], dup=1)
    plan = [
        sc.PlannedRow(date(2026, 11, 10), 100_000, "A"),
        sc.PlannedRow(date(2026, 11, 11), 250_000, "B"),
    ]
    out = sc.apply_plan(api, plan, "an_uong", consent=True, timeout=10)
    paths = [(m, p) for m, p, _ in api.calls if m != "GET"]
    assert paths[0] == ("POST", "/ingest/uploads") and paths[1][0] == "UPLOAD"
    assert [p for _, p in paths[2:]] == [
        "/ingest/rows/r0/jar",
        "/ingest/rows/r1/jar",
        "/ingest/confirmations",
        "/ingest/actions",
    ]
    upload_body = api.calls[0][2]
    assert upload_body["consent"] is True and upload_body["source_kind"] == "csv"
    actions = api.calls[-1][2]
    assert actions["tool"] == "confirm_rows" and actions["confirm_token"] == "tok"
    assert [r["jar"] for r in actions["params"]["rows"]] == ["an_uong", "an_uong"]
    assert out["rows_written"] == 2 and out["rows_duplicate"] == 1 and out["amount_vnd"] == 350_000


def test_luong_rest_khong_gui_consent_khi_khong_co_co_va_bao_loi_ro(sc, monkeypatch):
    monkeypatch.setattr(sc.time, "sleep", lambda s: None)
    api = FakeApi([100_000])
    sc.apply_plan(
        api, [sc.PlannedRow(date(2026, 11, 10), 100_000, "A")], "an_uong", consent=False, timeout=10
    )
    assert "consent" not in api.calls[0][2]
    with pytest.raises(sc.ShiftError, match="rejected"):
        sc.apply_plan(
            FakeApi([1], final="rejected"),
            [sc.PlannedRow(date(2026, 11, 10), 1000, "A")],
            "an_uong",
            consent=True,
            timeout=10,
        )
    with pytest.raises(sc.ShiftError, match="không có trong danh sách hũ"):
        sc.apply_plan(
            FakeApi([1]),
            [sc.PlannedRow(date(2026, 11, 10), 1000, "A")],
            "du_lich",
            consent=True,
            timeout=10,
        )


def test_next_steps_noi_ro_ky_vong_cua_tung_che_do(sc):
    assert "confirmed" in sc.next_steps("sub-x", "shift", "an_uong")
    assert "KHÔNG có dòng confirmed" in sc.next_steps("sub-x", "one-off", "an_uong")
    assert "yofina-forecast-batch" in sc.next_steps("sub-x", "shift", "an_uong")
