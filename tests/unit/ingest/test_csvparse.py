"""Bộ đọc CSV tất định trên các tệp sao kê dựng sẵn (evals/ingest/synthetic/csv)."""

from __future__ import annotations

import unicodedata
from datetime import date

import pytest
from ingest_helpers import csv_bytes
from yofina_ingest import csvparse as c

TODAY = date(2026, 11, 21)


def _enc_cp1258(ch: str) -> bytes:
    """Mã hóa một ký tự sang cp1258 (bảng mã này chỉ có vài chữ ghép sẵn, dấu thanh là ký tự ghép riêng)."""
    try:
        return ch.encode("cp1258")
    except UnicodeEncodeError:
        pass
    d = unicodedata.normalize("NFD", ch)
    base, rest = d[0], []
    for mark in d[1:]:
        comp = unicodedata.normalize("NFC", base + mark)
        try:
            comp.encode("cp1258")
            base = comp
        except UnicodeEncodeError:
            rest.append(mark)
    return (base + "".join(rest)).encode("cp1258")


def parsed(name: str):
    table = c.read_table(csv_bytes(name), max_rows=500)
    mapping = c.map_header(table.header)
    return table, mapping, c.parse_rows(table, mapping, today=TODAY)


def test_c01_utf8_bom_dau_phay_hai_cot_no_co():
    table, mapping, rows = parsed("c01_vcb_50.csv")
    assert table.encoding == "utf-8-sig" and table.delimiter == "," and table.header_found
    assert mapping.usable and mapping.debit is not None and mapping.credit is not None
    assert len(rows) == 50 and all(r.problem is None for r in rows)
    first = rows[0]
    assert (first.date, first.amount_vnd, first.direction) == (date(2026, 10, 22), 48000, "out")
    salary = rows[5]
    assert (salary.amount_vnd, salary.direction) == (9_000_000, "in")


def test_c02_so_tien_co_dau():
    _, mapping, rows = parsed("c02_bidv_en_signed.csv")
    assert mapping.amount is not None and mapping.debit is None
    assert rows[0].direction == "in" and rows[0].amount_vnd == 9_000_000
    assert rows[1].direction == "out" and rows[1].amount_vnd == 372_000
    assert all(r.confidence == 0.99 for r in rows)


def test_c03_dau_cham_phay_khong_dau_so_cham_ngan_cach():
    table, _, rows = parsed("c03_khongdau_semicolon.csv")
    assert table.delimiter == ";"
    assert rows[0].amount_vnd == 9_000_000 and rows[0].direction == "in"
    assert rows[1].amount_vnd == 1_500_000 and rows[1].direction == "out"


def test_c05_cong_thuc_trung_hoa_va_dong_so_tien_cong_thuc_bi_loai():
    _, _, rows = parsed("c05_formula_injection.csv")
    by = {r.source_row: r for r in rows}
    assert by[6].problem == "formula_amount" and by[6].amount_vnd is None
    for n in (1, 2, 3, 4):
        assert by[n].problem is None
        assert by[n].description is not None and by[n].description.startswith("'")
    assert by[5].description == "THANH TOAN QR PHUC LONG FT2611331122"


def test_c04_noi_dung_tan_cong_chi_la_du_lieu():
    _, _, rows = parsed("c04_attack_injection.csv")
    assert len(rows) == 6 and all(r.problem is None for r in rows)
    assert rows[3].direction == "in" and rows[3].amount_vnd == 1000


def test_giai_ma_cp1258_khi_khong_phai_utf8():
    text = (
        "Ngày giao dịch,Số tiền ghi nợ,Số tiền ghi có,Nội dung\n"
        '01/11/2026,"50,000",,Cà phê\n02/11/2026,,"1,000,000",Lương\n'
    )
    data = b"".join(_enc_cp1258(ch) for ch in text)
    assert c.decode_bytes(data)[1] == "cp1258"
    table = c.read_table(data, max_rows=10)
    rows = c.parse_rows(table, c.map_header(table.header), today=TODAY)
    assert [r.amount_vnd for r in rows] == [50000, 1000000]
    assert rows[0].description == "Cà phê"


def test_tab_va_dong_dau_thua_truoc_tieu_de():
    text = (
        "Sao ke tai khoan\nChu tai khoan\tX\nNgay\tSo tien\tNoi dung\n01/11/2026\t-50000\tca phe\n"
    )
    table = c.read_table(text.encode(), max_rows=10)
    assert table.delimiter == "\t" and table.header == ("Ngay", "So tien", "Noi dung")
    assert len(table.rows) == 1


def test_qua_nhieu_dong_bi_tu_choi_khong_cat_im_lang():
    body = "Ngay,So tien,Noi dung\n" + "\n".join(f"01/11/2026,-{1000 + i},x" for i in range(11))
    with pytest.raises(c.CsvError) as e:
        c.read_table(body.encode(), max_rows=10)
    assert e.value.code == "too_many_rows"


def test_tep_rong_hoac_khong_co_dong_du_lieu():
    for data in (b"", b"   \n", b"Ngay,So tien\n"):
        with pytest.raises(c.CsvError):
            c.read_table(data, max_rows=10)


def test_cot_la_khong_anh_xa_duoc_va_ghep_anh_xa_cua_model():
    text = "Col A,Col B,Col C\n01/11/2026,-50000,ca phe\n"
    table = c.read_table(text.encode(), max_rows=10)
    assert not table.header_found
    auto = c.map_header(table.header)
    assert not auto.usable
    extra = c.mapping_from_names(
        table.header,
        {"date": "Col A", "amount": "Col B", "description": "Col C", "debit": "Cột bịa"},
        "dmy",
    )
    assert extra.debit is None  # model không được bịa tên cột
    merged = c.merge_mapping(auto, extra)
    assert merged.usable
    rows = c.parse_rows(table, merged, today=TODAY)
    assert rows[0].amount_vnd == 50000 and rows[0].direction == "out"


def test_so_tien_khong_dau_thi_do_tin_cay_thap():
    text = "Ngay,So tien,Noi dung\n01/11/2026,50000,x\n"
    table = c.read_table(text.encode(), max_rows=10)
    row = c.parse_rows(table, c.map_header(table.header), today=TODAY)[0]
    assert row.direction == "out" and row.confidence < 0.9 and "unsigned_amount" in row.notes


def test_dong_tong_khong_co_ngay_bi_loai():
    text = "Ngay,So tien ghi no,So tien ghi co\n01/11/2026,50000,\nTong cong,50000,\n"
    table = c.read_table(text.encode(), max_rows=10)
    rows = c.parse_rows(table, c.map_header(table.header), today=TODAY)
    assert [r.problem for r in rows] == [None, "no_date"]
