"""Khử trùng dòng nạp với sổ cái (`yofina_ingest.worker.pick_matches`) trên đúng các ca của lần kiểm lại 24/11 trên `giamkhao3`.

Dữ liệu dựng lại, không gọi AWS: sổ cái ví của persona `vy` từ `data/personas` (ngày neo 21/11/2026), dòng tiền phòng của ảnh `s02` đã
chốt (nhãn trong `evals/ingest/manifest.json`), 50 dòng của sao kê `c01` (nhãn manifest). `fake_find_matches` làm đúng việc của
`app_find_ingest_matches` (migration 0050): cùng chiều, cùng số tiền tuyệt đối, lệch ngày trong cửa sổ, đối tác khớp khi hai bên có từ
3 ký tự và bên này chứa bên kia.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import pytest
from ingest_helpers import REPO
from yofina_ingest.extract import Candidate
from yofina_ingest.worker import is_duplicate_match, pick_matches, text_tokens, texts_similar

from personas import generate
from yofina_core.ingest import IngestSettings
from yofina_core.params import fold_text

ANCHOR = date(2026, 11, 21)
WINDOW = IngestSettings().ingest_dedupe_window_days
MANIFEST = json.loads((REPO / "evals" / "ingest" / "manifest.json").read_text(encoding="utf-8"))
#: đối tác bộ đọc CSV lấy cho dòng 15 của `c01` ở lần kiểm lại 24/11 (manifest để null: nội dung không có tên đối tác)
C01_ROW15_READ_COUNTERPARTY = "TIEN PHONG"


def item(item_id: str) -> dict[str, Any]:
    return next(i for i in MANIFEST["items"] if i["id"] == item_id)


def vy_ledger() -> list[dict[str, Any]]:
    data = generate("vy", anchor=ANCHOR)
    return [
        {
            "id": t.key,
            "kind": t.kind,
            "app_date": ANCHOR - timedelta(days=t.days_ago),
            "amount_vnd": t.amount_vnd,
            "merchant": t.payee or t.merchant,
            "note": t.note,
            "funding_source": t.funding_source,
        }
        for t in data.transactions
    ]


def s02_ledger_row() -> dict[str, Any]:
    """Dòng của ảnh `s02` sau khi chốt: `funding_source external`, đối tác và nội dung như dòng nạp đã che."""
    (tx,) = item("s02")["expected"]["transactions"]
    return {
        "id": "s02",
        "kind": "expense",
        "app_date": date.fromisoformat(tx["date"]),
        "amount_vnd": -tx["amount_vnd"],
        "merchant": tx["counterparty"],
        "note": tx["description"],
        "funding_source": "external",
    }


def c01_candidates() -> dict[int, Candidate]:
    out = {}
    for tx in item("c01")["expected"]["transactions"]:
        seq = tx["source_row"]
        cp = tx["counterparty"] if seq != 15 else C01_ROW15_READ_COUNTERPARTY
        out[seq] = Candidate(
            seq=seq, kind="expense" if tx["direction"] == "out" else "income", app_date=date.fromisoformat(tx["date"]),
            amount_vnd=tx["amount_vnd"], counterparty=cp, description=tx["description"], extract_confidence=0.95,
        )  # fmt: skip
    return out


def fake_find_matches(
    ledger: list[dict[str, Any]], cands: dict[int, Candidate], window: int
) -> list[dict[str, Any]]:
    out = []
    for c in cands.values():
        cp = fold_text(c.counterparty or "")
        for t in ledger:
            if (
                t["kind"] != c.kind
                or t["kind"] == "transfer"
                or abs(t["amount_vnd"]) != c.amount_vnd
            ):
                continue
            dd = (t["app_date"] - c.app_date).days
            if abs(dd) > window:
                continue
            who = fold_text(t["merchant"] or "")
            hit = len(cp) >= 3 and len(who) >= 3 and (cp in who or who in cp)
            out.append({"idx": c.seq, "transaction_id": t["id"], "funding_source": t["funding_source"],
                        "app_date": t["app_date"], "day_diff": dd, "counterparty_match": hit})  # fmt: skip
    return sorted(out, key=lambda m: (m["idx"], abs(m["day_diff"]), not m["counterparty_match"]))


def details_of(ledger: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {t["id"]: {"merchant": t["merchant"], "note": t["note"]} for t in ledger}


def dedupe(ledger: list[dict[str, Any]], cands: dict[int, Candidate]) -> dict[int, Any]:
    return pick_matches(fake_find_matches(ledger, cands, WINDOW), cands, WINDOW, details_of(ledger))


# --- ca thật trên giamkhao3 -----------------------------------------------------------------------------------------------------
def test_du_lieu_dung_lai_co_du_sau_dong_trung_gia_cua_nghiem_thu():
    """Bộ dựng lại phải còn đủ 6 dòng `c01` từng bị đánh trùng giả với ví `vy` (Circle K, Grab, Highlands, Phúc Long, Be), không thì
    các test bên dưới không kiểm gì."""
    ledger, cands = vy_ledger(), c01_candidates()
    wallet = {
        m["idx"] for m in fake_find_matches(ledger, cands, WINDOW) if m["funding_source"] == "jar"
    }
    assert wallet == {7, 8, 12, 26, 30, 35}
    assert {cands[i].counterparty for i in wallet} == {
        "Circle K",
        "Grab",
        "Highlands Coffee",
        "Phuc Long",
        "Be",
    }


def test_c01_sau_anh_s02_chi_dong_tien_phong_la_trung():
    ledger = [*vy_ledger(), s02_ledger_row()]
    best = dedupe(ledger, c01_candidates())
    assert set(best) == {15}
    assert best[15]["transaction_id"] == "s02"


def test_c01_tren_vy_vua_dat_lai_khong_dong_nao_trung():
    assert dedupe(vy_ledger(), c01_candidates()) == {}


def test_highlands_45000_la_hai_lan_mua_khong_phai_dong_trung():
    """Highlands Coffee 45.000 ₫ ngày 31/10 của `c01` khớp đối tác với Highlands Coffee 45.000 ₫ ngày 29/10 trong ví `vy`, nhưng giao dịch
    ví trả từ hũ (`funding_source jar`) còn dòng sao kê là một lần thanh toán QR khác từ tài khoản ngân hàng (mã FT riêng); `c01` dựng
    độc lập với persona (`scripts/make_ingest_synthetic.py`)."""
    ledger, cands = vy_ledger(), c01_candidates()
    (m,) = [m for m in fake_find_matches(ledger, cands, WINDOW) if m["idx"] == 12]
    wallet_tx = next(t for t in ledger if t["id"] == m["transaction_id"])
    assert (wallet_tx["merchant"], wallet_tx["funding_source"], m["counterparty_match"], m["day_diff"]) == (
        "Highlands Coffee", "jar", True, -2,
    )  # fmt: skip
    assert not is_duplicate_match(m, cands[12], details_of(ledger)[m["transaction_id"]], WINDOW)


def test_anh_s02_nap_sau_c01_cung_bi_danh_trung():
    """Thứ tự ngược lại: dòng 15 của `c01` đã chốt (đối tác "TIEN PHONG"), rồi ảnh `s02` (đối tác đã che "N***")."""
    c15 = c01_candidates()[15]
    ledger = [
        *vy_ledger(),
        {"id": "c01-15", "kind": "expense", "app_date": c15.app_date, "amount_vnd": -c15.amount_vnd,
         "merchant": c15.counterparty, "note": c15.description, "funding_source": "external"},
    ]  # fmt: skip
    s02 = s02_ledger_row()
    cand = Candidate(seq=1, kind="expense", app_date=s02["app_date"], amount_vnd=1_500_000, counterparty=s02["merchant"],
                     description=s02["note"], extract_confidence=0.98)  # fmt: skip
    best = dedupe(ledger, {1: cand})
    assert best[1]["transaction_id"] == "c01-15"


# --- từng luật ---------------------------------------------------------------------------------------------------------------------
def cand(cp: str | None, desc: str | None, amount: int) -> Candidate:
    return Candidate(seq=1, kind="expense", app_date=date(2026, 11, 1), amount_vnd=amount, counterparty=cp,
                     description=desc, extract_confidence=0.95)  # fmt: skip


def match(day_diff: int, funding: str = "external", hit: bool = False) -> dict[str, Any]:
    return {
        "idx": 1,
        "transaction_id": "t",
        "funding_source": funding,
        "day_diff": day_diff,
        "counterparty_match": hit,
    }


def test_hai_doi_tac_da_che_khac_noi_dung_so_tien_nho_khong_trung():
    # hai lần chuyển 200.000 ₫ cho hai người khác nhau cùng chữ cái đầu: hàm DB thấy "n***" bằng nhau nhưng đó không phải bằng chứng
    existing = {"merchant": "N***", "note": "tra tien sach"}
    assert not is_duplicate_match(
        match(0, hit=True), cand("N***", "tien an trua", 200_000), existing, WINDOW
    )


@pytest.mark.parametrize(
    ("day_diff", "funding", "expected"),
    [(0, "external", True), (1, "external", True), (2, "external", False), (0, "jar", False)],
)
def test_khong_biet_doi_tac_so_tien_lon_ngoai_vi_trung_khi_lech_toi_da_mot_ngay(
    day_diff, funding, expected
):
    existing = {"merchant": None, "note": "hoc phi"}
    got = is_duplicate_match(
        match(day_diff, funding), cand("N***", "CK thang 11", 2_000_000), existing, WINDOW
    )
    assert got is expected


def test_khong_biet_doi_tac_so_tien_nho_noi_dung_khac_khong_trung():
    existing = {"merchant": None, "note": "GRABFOOD ORDER"}
    assert not is_duplicate_match(
        match(0), cand(None, "THANH TOAN QR PHUC LONG", 59_000), existing, WINDOW
    )


def test_khong_doi_tac_noi_dung_chua_ten_cua_hang_trung_giao_dich_vi_cung_ngay():
    existing = {"merchant": "Highlands Coffee", "note": None}
    c = cand(None, "THANH TOAN QR HIGHLANDS COFFEE FT2636235975", 45_000)
    assert is_duplicate_match(match(0, "jar"), c, existing, WINDOW)
    assert not is_duplicate_match(match(2, "jar"), c, existing, WINDOW)


def test_giao_dich_vi_cung_doi_tac_chi_trung_khi_lech_toi_da_mot_ngay():
    existing = {"merchant": "Highlands Coffee", "note": None}
    c = cand("Highlands Coffee", "ca phe", 45_000)
    assert is_duplicate_match(match(1, "jar", hit=True), c, existing, WINDOW)
    assert not is_duplicate_match(match(2, "credit", hit=True), c, existing, WINDOW)
    assert is_duplicate_match(match(3, "external", hit=True), c, existing, WINDOW)


def test_tu_chung_cua_noi_dung_ngan_hang_khong_tinh_la_gan_giong():
    a = text_tokens(None, "MBVCB.FT2611.THANH TOAN QR CK chuyen tien")
    assert a == frozenset()
    assert not texts_similar(
        text_tokens("X", "THANH TOAN QR HIGHLANDS"), text_tokens("Y", "THANH TOAN QR PHUC LONG")
    )
    assert texts_similar(
        text_tokens(C01_ROW15_READ_COUNTERPARTY, "MBVCB.3765569.CK tien phong T11"),
        text_tokens("N***", "MINH CK tien phong thang 11"),
    )
