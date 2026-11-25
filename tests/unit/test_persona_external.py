"""F6: thu nhập ngoài ví và chi ngoài ví của persona (`vy`), ba persona cũ không đổi một byte, độ phủ dữ liệu trước và sau khi nạp.

Độ phủ KHÔNG gắn cứng ở đâu: test dựng lại các thành phần của `app_coverage_facts` (migration 0050) từ dữ liệu bộ sinh đã sinh rồi
đưa qua `quality.data_coverage` và `ingest.coverage_ratio`; test chỉ khẳng định số rơi vào dải mục tiêu của kịch bản demo. Bản
cùng việc trên PostgreSQL thật nằm ở tests/local_pg/test_persona_external.py.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from conftest import REPO
from persona_coverage import AFTER_RANGE, BEFORE_RANGE, coverage_facts
from persona_digest import persona_digest

from personas import (
    OutOfWallet,
    PersonaError,
    generate,
    generate_out_of_wallet,
    load_accounts,
    materialize,
    statement_balances,
    statement_csv,
)
from yofina_core import ingest
from yofina_ml import quality
from yofina_ml.types import CoverageInputs

ANCHOR = date(2026, 11, 21)
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime(2026, 12, 10, 3, 0, tzinfo=UTC)
SAMPLES = REPO / "data" / "personas" / "samples"

#: băm đầu ra bộ sinh của ba persona cũ ĐO TRƯỚC khi thêm thu nhập ngoài ví (`uv run python tests/unit/persona_digest.py` ở bản
#: bộ sinh chưa có tính năng). Đổi spec của chúng một cách có chủ đích thì tính lại băm và sửa ở đây.
OLD_DIGESTS = {
    "minh": "69b43593fde86faed5d7956e6c9b58b2b82dba2dfbe1dcf963005eb0c40eb826",
    "lan": "63f427e0ce42acdfa95c80ec3dff9d0cf656faf6ebc0ed89f62a4716fde0f6c2",
    "khoa": "3454c1e28c115e852f7889aaf4e97a7ccc532014a7b85d6797c0cea001c2a8d5",
}


# --- ba persona cũ không đổi -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(OLD_DIGESTS))
def test_ba_persona_cu_khong_doi_mot_byte(name):
    assert persona_digest(name) == OLD_DIGESTS[name]


@pytest.mark.parametrize("name", sorted(OLD_DIGESTS))
def test_ba_persona_cu_khong_co_dong_ngoai_vi(name):
    d = generate(name, anchor=ANCHOR)
    assert d.external_income_monthly_vnd is None
    assert all(t.funding_source in ("jar", "credit") for t in d.transactions)
    assert all(t.jar_code is not None for t in d.transactions)


# --- tham số spec `external_income_monthly_vnd` ---------------------------------------------------------------------------
def _spec(name: str, mutate):
    spec = json.loads((REPO / "data" / "personas" / "specs" / f"{name}.json").read_text("utf-8"))
    mutate(spec)
    return spec


def test_spec_khong_khai_thu_nhap_ngoai_vi_thi_khong_co_dong_nao():
    spec = _spec("minh", lambda s: s.update(external_income_monthly_vnd=0))
    assert (
        generate("minh", anchor=ANCHOR, spec=spec).transactions
        == generate("minh", anchor=ANCHOR).transactions
    )


def test_thu_nhap_ngoai_vi_moi_thang_mot_dong_khong_hu_va_khong_doi_so_du():
    def add(s):
        s["external_income_monthly_vnd"] = 3_000_000
        s["external_income"] = {"day": 31, "merchant": "Khách hàng", "tx_type": "refund"}

    base = generate("minh", anchor=ANCHOR)
    d = generate(
        "minh", anchor=ANCHOR, spec=_spec("minh", add)
    )  # cùng tên persona: cùng hạt ngẫu nhiên
    ext = [t for t in d.transactions if t.funding_source == "external"]
    assert d.external_income_monthly_vnd == 3_000_000
    # ngày 31: 31/10 nằm trong lịch sử (5/10 đến 20/11); ngày 31 của tháng 11 lấy ngày cuối tháng là 30/11, sau ngày neo
    assert [(ANCHOR - timedelta(days=t.days_ago)) for t in ext] == [date(2026, 10, 31)]
    assert all(
        t.kind == "income"
        and t.jar_code is None
        and t.amount_vnd == 3_000_000
        and t.tx_type == "refund"
        for t in ext
    )
    # số dư mọi hũ và mọi dòng khác y như persona gốc
    assert {j.code: j.balance_vnd for j in d.jars} == {j.code: j.balance_vnd for j in base.jars}
    assert [t for t in d.transactions if t.funding_source != "external"] == list(base.transactions)
    assert d.system_balances == base.system_balances


def test_thu_nhap_ngoai_vi_ngay_mac_dinh_va_tx_type_mac_dinh():
    d = generate(
        "minh",
        anchor=ANCHOR,
        spec=_spec("minh", lambda s: s.update(external_income_monthly_vnd=1_000_000)),
    )
    ext = [t for t in d.transactions if t.funding_source == "external"]
    assert sorted(ANCHOR - timedelta(days=t.days_ago) for t in ext) == [
        date(2026, 10, 15),
        date(2026, 11, 15),
    ]
    assert {t.tx_type for t in ext} == {"income_other"}


@pytest.mark.parametrize(
    ("patch", "match"),
    [
        ({"external_income_monthly_vnd": -5}, "dương"),
        ({"external_income_monthly_vnd": 1_000_000, "external_income": {"day": 32}}, "từ 1 đến 31"),
        (
            {"external_income_monthly_vnd": 1_000_000, "external_income": {"merchant": ""}},
            "merchant",
        ),
    ],
)
def test_spec_thu_nhap_ngoai_vi_sai_thi_bao_loi(patch, match):
    with pytest.raises(PersonaError, match=match):
        generate("x", anchor=ANCHOR, spec=_spec("minh", lambda s: s.update(patch)))


# --- persona vy: sổ cái ---------------------------------------------------------------------------------------------------
def test_vy_la_persona_co_thu_nhap_ngoai_vi():
    d = generate("vy", anchor=ANCHOR)
    assert d.monthly_salary_vnd == 8_000_000 and d.external_income_monthly_vnd == 4_800_000
    ext = [t for t in d.transactions if t.funding_source == "external"]
    assert len(ext) == 2 and all(t.kind == "income" and t.jar_code is None for t in ext)
    assert sorted(ANCHOR - timedelta(days=t.days_ago) for t in ext) == [
        date(2026, 10, 18),
        date(2026, 11, 18),
    ]
    # thu nhập ngoài ví không đụng hũ nào: số dư mỗi hũ = tổng dòng trả bằng hũ
    by_jar: dict[str, int] = defaultdict(int)
    for t in d.transactions:
        if t.funding_source == "jar":
            by_jar[t.jar_code] += t.amount_vnd
    assert {j.code: j.balance_vnd for j in d.jars} == {j.code: by_jar[j.code] for j in d.jars}
    assert d.system_balances == {"tien_vao_khac": 0, "chua_phan_loai": 0}


def test_vy_materialize_dong_ngoai_vi_khong_hu_funding_external():
    m = materialize(generate("vy", anchor=ANCHOR), anchor=ANCHOR, now=NOW, tz=TZ, user_id="u1")
    rows = [r for r in m.transaction_rows if r["funding_source"] == "external"]
    assert len(rows) == 2
    assert all(
        r["jar_code"] is None and r["kind"] == "income" and r["transfer_id"] is None
        and r["obligation_id"] is None and r["amount"] > 0 and r["merchant"]
        for r in rows
    )  # fmt: skip
    assert all(
        r["jar_code"] is not None for r in m.transaction_rows if r["funding_source"] != "external"
    )


# --- độ phủ dữ liệu: dựng lại thành phần của app_coverage_facts (migration 0050) ----------------------------------------------
def coverage(facts: dict[str, int]) -> float | None:
    a = quality.data_coverage(CoverageInputs(**facts))
    assert ingest.coverage_ratio(facts) == a  # hai bản của công thức cho cùng số
    return a


@pytest.fixture(scope="module")
def vy():
    data = generate("vy", anchor=ANCHOR)
    return data, generate_out_of_wallet("vy", anchor=ANCHOR, data=data)


def test_vy_do_phu_truoc_khi_nap_nam_trong_dai_muc_tieu(vy):
    data, _ = vy
    before = coverage(coverage_facts(data))
    assert BEFORE_RANGE[0] <= before <= BEFORE_RANGE[1], before


def test_vy_do_phu_sau_khi_nap_sao_ke_nam_trong_dai_muc_tieu(vy):
    data, oow = vy
    stmt = oow.source("statement")
    # tiền vào của sao kê trùng thu nhập ngoài ví đã seed (cùng ngày, cùng số tiền): khử trùng loại, không cộng đôi thu nhập
    seeded = {
        (ANCHOR - timedelta(days=t.days_ago), t.amount_vnd)
        for t in data.transactions
        if t.funding_source == "external"
    }
    assert {(r.app_date(ANCHOR), r.amount_vnd) for r in stmt.incomes} == seeded
    added = sum(r.amount_vnd for r in stmt.expenses)
    before = coverage(coverage_facts(data))
    after = coverage(coverage_facts(data, extra_expenses=added))
    assert AFTER_RANGE[0] <= after <= AFTER_RANGE[1], after
    assert after > before
    # nạp thêm cả ảnh biên lai (ngày gần nhất): độ phủ tăng nữa nhưng chưa đủ 100%
    receipts = sum(r.amount_vnd for r in oow.source("receipts").expenses)
    both = coverage(coverage_facts(data, extra_expenses=added + receipts))
    assert after < both < 1.0


def test_vy_nap_ca_tien_vao_cua_sao_ke_neu_khu_trung_hong_thi_do_phu_tut(vy):
    """Phản chứng: nếu khử trùng hỏng và hai dòng tiền vào bị cộng đôi thì độ phủ giảm, nên khử trùng là điều kiện của kịch bản."""
    data, oow = vy
    stmt = oow.source("statement")
    added = sum(r.amount_vnd for r in stmt.expenses)
    doubled = sum(r.amount_vnd for r in stmt.incomes)
    good = coverage(coverage_facts(data, extra_expenses=added))
    bad = coverage(coverage_facts(data, extra_expenses=added, extra_income=doubled))
    assert bad < good and not (AFTER_RANGE[0] <= bad <= AFTER_RANGE[1])


# --- persona vy: chi ngoài ví -------------------------------------------------------------------------------------------
def test_chi_ngoai_vi_tat_dinh_va_tong_dung_spec(vy):
    data, oow = vy
    again = generate_out_of_wallet("vy", anchor=ANCHOR)
    assert again == oow
    assert generate_out_of_wallet("vy", anchor=ANCHOR, seed=1) != oow
    spec = json.loads((REPO / "data" / "personas" / "specs" / "vy.json").read_text("utf-8"))
    for src in spec["out_of_wallet"]["sources"]:
        planned = sum(g["total_vnd"] for g in src["groups"])
        assert (
            sum(r.amount_vnd for r in oow.source(src["id"]).expenses) == planned
        )  # nhích chống trùng giữ nguyên tổng nguồn
        assert len(oow.source(src["id"]).expenses) == sum(g["count"] for g in src["groups"])
    # sổ cái seed KHÔNG có khoản chi ngoài ví: đó là thứ người dùng sẽ nạp
    assert not [
        t for t in data.transactions if t.funding_source == "external" and t.kind == "expense"
    ]


def test_chi_ngoai_vi_nam_trong_lich_su_va_hu_co_trong_spec(vy):
    data, oow = vy
    jar_codes = {j.code for j in data.jars}
    for src in oow.sources:
        for r in src.rows:
            assert (
                1 <= r.days_ago <= data.history_days
                and src.to_days_ago <= r.days_ago <= src.from_days_ago
            )
            assert r.app_date(ANCHOR) < ANCHOR and r.amount_vnd > 0
            assert r.kind == "income" or r.jar_code in jar_codes


def test_chi_ngoai_vi_khong_trung_so_tien_voi_giao_dich_trong_vi_trong_cua_so_khu_trung(vy):
    """Cửa sổ khử trùng mặc định 3 ngày: không khoản chi ngoài ví nào cùng số tiền với một khoản chi đã có (ví hoặc nguồn khác)."""
    data, oow = vy
    existing = [(t.days_ago, -t.amount_vnd) for t in data.transactions if t.kind == "expense"]
    seen: list[tuple[str, int, int]] = []
    for src in oow.sources:
        for r in src.expenses:
            assert not [1 for d, a in existing if a == r.amount_vnd and abs(d - r.days_ago) <= 3], r
            assert not [
                1
                for sid, d, a in seen
                if a == r.amount_vnd and abs(d - r.days_ago) <= 3 and sid != src.id
            ], r
        seen.extend((src.id, r.days_ago, r.amount_vnd) for r in src.expenses)


def test_chi_ngoai_vi_hu_doan_duoc_tu_loai_giao_dich(vy):
    """Mỗi khoản chi có tx_type mà bảng tx_type_map (db/seed) đã gán hũ mặc định: bước 0 của phân loại tự đoán đúng hũ."""
    _, oow = vy
    seed_sql = (REPO / "db" / "seed" / "tx_type_map.sql").read_text("utf-8")
    default_jar = dict(re.findall(r"\('([a-z_]+)',\s*'[^']*',\s*'out',\s*'([a-z_]+)'", seed_sql))
    for src in oow.sources:
        for r in src.expenses:
            assert default_jar.get(r.tx_type) == r.jar_code, (r.tx_type, r.jar_code)


def test_sao_ke_so_du_khong_am_va_khop_cach_cong_tru(vy):
    _, oow = vy
    bal = statement_balances(oow, "statement")
    assert min(bal) >= 0
    rows = oow.source("statement").rows
    assert bal[-1] == oow.opening_balance_vnd + sum(
        r.amount_vnd if r.kind == "income" else -r.amount_vnd for r in rows
    )


# --- tệp mẫu --------------------------------------------------------------------------------------------------------------
def parse_statement(raw: bytes) -> list[dict[str, str]]:
    assert (
        raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw
    )  # UTF-8 có BOM, CRLF như sao kê mẫu của eval
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")))


def test_csv_mau_dung_cot_vcb_va_khop_du_lieu_bo_sinh(vy):
    _, oow = vy
    raw = statement_csv(oow)
    ref = (REPO / "evals" / "ingest" / "synthetic" / "csv" / "c01_vcb_50.csv").read_bytes()
    assert (
        raw.decode("utf-8-sig").splitlines()[0] == ref.decode("utf-8-sig").splitlines()[0]
    )  # cùng hàng tiêu đề
    rows = parse_statement(raw)
    src = oow.source("statement")
    assert len(rows) == len(src.rows) and [r["STT"] for r in rows] == [
        str(i) for i in range(1, len(rows) + 1)
    ]
    debit = sum(int(r["Số tiền ghi nợ"].replace(",", "")) for r in rows if r["Số tiền ghi nợ"])
    credit = sum(int(r["Số tiền ghi có"].replace(",", "")) for r in rows if r["Số tiền ghi có"])
    assert debit == sum(r.amount_vnd for r in src.expenses) and credit == sum(
        r.amount_vnd for r in src.incomes
    )
    assert all(
        bool(r["Số tiền ghi nợ"]) != bool(r["Số tiền ghi có"]) for r in rows
    )  # mỗi dòng một chiều
    dates = [datetime.strptime(r["Ngày giao dịch"], "%d/%m/%Y").date() for r in rows]
    assert (
        dates == sorted(dates)
        and dates[0] >= ANCHOR - timedelta(days=45)
        and dates[-1] <= ANCHOR - timedelta(days=2)
    )
    assert statement_csv(oow) == raw  # tất định


def test_tep_csv_da_commit_khop_bo_sinh(vy):
    """Tệp trong data/personas/samples là đúng đầu ra của bộ sinh (chạy lại make_samples.py nếu test này đỏ)."""
    _, oow = vy
    committed = SAMPLES / "vy_sao_ke_vcb.csv"
    assert committed.is_file(), (
        "chưa có tệp mẫu: uv run --with pillow python data/personas/samples/make_samples.py"
    )
    assert committed.read_bytes() == statement_csv(oow)


def test_anh_bien_lai_da_commit_la_png_hop_le_va_dong_nhat_voi_nguon_receipts(vy):
    pil = pytest.importorskip("PIL.Image")
    _, oow = vy
    files = sorted(SAMPLES.glob("vy_bien_lai_*.png"))
    assert len(files) == len(oow.source("receipts").expenses) >= 1
    for f in files:
        with pil.open(f) as im:
            im.verify()


def test_ba_tai_khoan_giam_khao_deu_la_minh_vy_khong_gan_tai_khoan_nao():
    # issue #8: giamkhao3 thôi là vy; vy vẫn nạp được bằng `scripts/seed_persona.py <tài khoản> --persona vy`
    m = load_accounts()["demo_accounts"]
    assert m["giamkhao1"] == m["giamkhao2"] == m["giamkhao3"] == "minh"
    assert "vy" not in m.values()


def test_out_of_wallet_chi_cho_persona_khai_khoi_nay():
    with pytest.raises(PersonaError, match="out_of_wallet"):
        generate_out_of_wallet("minh", anchor=ANCHOR)
    assert isinstance(generate_out_of_wallet("vy", anchor=ANCHOR), OutOfWallet)
