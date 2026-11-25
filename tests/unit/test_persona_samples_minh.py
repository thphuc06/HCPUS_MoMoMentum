"""Ảnh chứng từ mẫu cảnh 5 cho persona `minh` (issue #16): `make_samples.minh_receipts` (phần dữ liệu, không vẽ ảnh).

Giám khảo dùng `giamkhao1`–`giamkhao3`, cả ba là persona `minh`. Biên lai mẫu phải có họ tên, số điện thoại, số tài khoản HƯ CẤU nhìn
rõ, số tiền và ngày ra từ spec qua bộ sinh như mẫu của `vy`, và không trùng giao dịch đã seed (khỏi bị khử trùng loại).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date

import pytest
from conftest import REPO

from personas import generate
from yofina_core.ingest import IngestSettings
from yofina_core.pii import PiiPolicy, mask_counterparty, mask_row_text

ANCHOR = date(2026, 11, 21)  # ngày neo của demo (YOFINA_DEMO_ANCHOR_DATE)
SAMPLES = REPO / "data" / "personas" / "samples"
SPEC = json.loads((SAMPLES / "minh_receipts.json").read_text("utf-8"))
MINH = json.loads((REPO / "data" / "personas" / "specs" / "minh.json").read_text("utf-8"))
MERCHANTS = [m for g in SPEC["out_of_wallet"]["sources"][0]["groups"] for m in g["merchants"]]


@pytest.fixture(scope="module")
def ms():
    spec = importlib.util.spec_from_file_location("make_samples", SAMPLES / "make_samples.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass cần module có trong sys.modules lúc định nghĩa
    try:
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.modules.pop(spec.name, None)


@pytest.fixture(scope="module")
def receipts(ms):
    return ms.minh_receipts(ANCHOR)


def values(r) -> list[str]:
    return [v for _, v in r.rows]


def test_hai_bien_lai_theo_thu_tu_spec_moi_anh_mot_khoan(receipts):
    assert [r.file_name for r in receipts] == ["minh_bien_lai_1.png", "minh_bien_lai_2.png"]
    assert [r.title for r in receipts] == [
        "Chuyển khoản thành công",
        "Thanh toán hóa đơn thành công",
    ]
    assert [r.jar_code for r in receipts] == ["an_uong", "hoa_don"]


def test_ho_ten_sdt_so_tai_khoan_hu_cau_hien_nguyen_van_tren_bien_lai(receipts):
    transfer, bill = receipts
    src = SPEC["source_account"]
    t, b = MERCHANTS[0]["receipt"], MERCHANTS[1]["receipt"]
    assert (transfer.names, transfer.phones, transfer.accounts) == (
        (MERCHANTS[0]["name"],),
        (t["phone"],),
        (src, t["account"]),
    )
    assert (bill.names, bill.phones, bill.accounts) == ((b["customer"],), (b["phone"],), (src,))
    for r in receipts:
        for pii in (*r.names, *r.phones, *r.accounts):
            assert pii in values(r), (r.file_name, pii)  # nhìn rõ: nguyên văn, chưa che
    # tên hư cấu không trùng payee đã seed hay tên hiển thị của minh: worker giữ nguyên các tên đó khi che PII
    seeded = {p["name"] for p in MINH["payees"]} | {MINH["display_name"]}
    assert not {n for r in receipts for n in r.names} & seeded


def test_so_tien_va_ngay_ra_tu_spec_va_ngay_mo_phong_cua_minh(receipts):
    totals = {g["jar"]: g["total_vnd"] for g in SPEC["out_of_wallet"]["sources"][0]["groups"]}
    assert {r.jar_code: r.amount_vnd for r in receipts} == totals
    assert [r.amount_text for r in receipts] == ["345.000 VND", "126.000 VND"]
    # from_days_ago = to_days_ago = 1: hôm qua theo ngày neo, giờ do bộ sinh chọn
    assert [r.app_date for r in receipts] == [date(2026, 11, 20)] * 2
    for r in receipts:
        when = dict(r.rows)["Thời gian giao dịch"]
        assert when.startswith("20/11/2026 ") and len(when) == len("20/11/2026 07:05")


def test_khong_trung_so_tien_voi_giao_dich_da_seed_trong_cua_so_khu_trung(receipts):
    window = IngestSettings().ingest_dedupe_window_days
    seeded = generate("minh", anchor=ANCHOR).transactions
    for r in receipts:
        days_ago = (ANCHOR - r.app_date).days
        clash = [
            t
            for t in seeded
            if t.kind == "expense"
            and -t.amount_vnd == r.amount_vnd
            and abs(t.days_ago - days_ago) <= window
        ]
        assert not clash, (r.file_name, clash)


def test_tat_dinh(ms, receipts):
    assert ms.minh_receipts(ANCHOR) == receipts


# --- che PII: bộ che thật của dự án trên chữ của biên lai (tất định, không OCR, không gọi model) -----------------------------
def policy_cua_minh() -> PiiPolicy:
    """Như `Worker.build_context` (pipelines/ingest/yofina_ingest/worker.py): giữ tên payee đã lưu và tên hiển thị của người dùng."""
    return PiiPolicy.build(
        keep=[p["name"] for p in MINH["payees"]], self_names=[MINH["display_name"]]
    )


#: quy tắc che của contracts/README.md (Phase 5, "Che PII"): tên người -> chữ cái đầu + `***`; số -> `****` + 4 số cuối
MASKED = {
    "BÙI QUỐC KHÁNH": "B***",
    "VÕ THỊ NGỌC TRÂM": "V***",
    "0901 234 567": "****4567",
    "0938 765 432": "****5432",
    "1027356824": "****6824",
    "19038642097531": "****7531",
}


def test_bo_che_pii_che_ten_sdt_so_tai_khoan_va_giu_nguyen_phan_giao_dich(receipts):
    policy = policy_cua_minh()
    pii = {p for r in receipts for p in (*r.names, *r.phones, *r.accounts)}
    assert pii == set(MASKED)
    for r in receipts:
        # từng dòng chữ như vẽ trên ảnh, và từng cặp nhãn + giá trị như model có thể chép vào nội dung; dòng không có PII (số tiền,
        # nhà cung cấp, ngân hàng, nội dung, mã tham chiếu) phải còn nguyên để thành dòng giao dịch. Bỏ dòng ngày giờ: model trả ngày ở
        # trường `date` riêng (extract.parse_date), không qua mask_row_text (hàm này hiện đọc "2026 07" của "dd/mm/yyyy HH:MM" là số)
        when = dict(r.rows)["Thời gian giao dịch"]
        drawn = {line: MASKED.get(line, line) for line in r.lines if line != when}
        joined = {f"{k}: {v}": f"{k}: {MASKED.get(v, v)}" for k, v in r.rows if v != when}
        for line, expected in {**drawn, **joined}.items():
            assert mask_row_text(line, policy) == expected, line


def test_doi_tac_la_nguoi_bi_che_doi_tac_doanh_nghiep_giu_nguyen(receipts):
    policy = policy_cua_minh()
    transfer, bill = receipts
    assert mask_counterparty(dict(transfer.rows)["Tên người hưởng"], policy=policy) == "B***"
    provider = dict(bill.rows)["Nhà cung cấp"]
    assert mask_counterparty(provider, policy=policy) == provider
