"""Chi tiêu NGOÀI ví của persona (F6): thứ người dùng sẽ nạp từ sao kê ngân hàng khác hoặc ảnh biên lai.

Spec khai khối `out_of_wallet` (tùy chọn). Khối này KHÔNG vào sổ cái seed (`generate` không biết tới nó): sổ cái chỉ có thu nhập
ngoài ví (`external_income_monthly_vnd`), còn khoản chi ngoài ví thì để trống cho tới khi người dùng nạp tệp trong cảnh 5 của demo.
Module này dựng đúng các khoản chi đó, tất định theo seed, để:

- `samples/make_samples.py` sinh tệp mẫu để tải lên (CSV sao kê kiểu VCB, ảnh biên lai);
- test tính độ phủ dữ liệu TRƯỚC và SAU khi nạp bằng đúng công thức (`tests/unit/test_persona_external.py`,
  `tests/local_pg/test_persona_external.py`).

Mọi số tiền ra từ spec (tổng chi mỗi nhóm hũ, số khoản, nhịp) qua cùng các hàm chia tiền và chọn ngày với bộ sinh persona
(lognormal, trọng số cuối tuần). Số độ phủ KHÔNG nằm ở đâu cả: nó là kết quả của công thức trên dữ liệu đã sinh.

Khử trùng (F6): worker ghép dòng nạp với giao dịch ĐÃ CÓ cùng loại, cùng số tiền tuyệt đối, lệch ngày trong cửa sổ
`ingest_dedupe_window_days` (mặc định 3). Nên bộ sinh tránh để một khoản chi ngoài ví trùng số tiền với khoản chi nào trong ví (hay khoản
đã dựng trước đó) trong `dedupe_margin_days` ngày (mặc định 7, rộng hơn cửa sổ); khoản trùng được nhích 1.000 đ và phần chênh
chuyển sang khoản lớn nhất của cùng nguồn, nên tổng mỗi nguồn không đổi. Ngược lại các dòng TIỀN VÀO trong sao kê (lương freelance) cố ý
trùng số tiền và ngày với dòng thu nhập ngoài ví đã seed: đó là phép thử khử trùng của cảnh 5 (chúng bị loại, không cộng đôi thu nhập).
"""

from __future__ import annotations

import csv
import io
import random
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, time, timedelta
from pathlib import Path
from typing import Any

from personas.generator import (
    _ROUND,
    SPECS_DIR,
    PersonaData,
    PersonaError,
    _day_weights,
    _pick_days,
    _rhythm,
    _split_total,
    generate,
    load_spec,
)

#: cột sao kê kiểu Vietcombank, đúng như `evals/ingest/synthetic/csv/c01_vcb_50.csv`
VCB_HEADER = (
    "STT",
    "Ngày giao dịch",
    "Số tham chiếu",
    "Số tiền ghi nợ",
    "Số tiền ghi có",
    "Số dư",
    "Nội dung chi tiết",
)


@dataclass(frozen=True)
class OutOfWalletTx:
    """Một giao dịch ở tài khoản ngân hàng khác. `amount_vnd` luôn dương, hướng nằm ở `kind`."""

    key: str
    source_id: str
    days_ago: int
    local_time: time
    kind: str  # expense | income
    amount_vnd: int
    jar_code: str | None  # None với tiền vào
    merchant: str
    tx_type: str
    bank_text: str  # nội dung dòng sao kê hoặc lời nhắn biên lai
    receipt_style: str | None = None
    recipient_label: str | None = None

    def app_date(self, anchor: date) -> date:
        return anchor - timedelta(days=self.days_ago)


@dataclass(frozen=True)
class OutOfWalletSource:
    id: str
    channel: str  # csv | image
    from_days_ago: int
    to_days_ago: int
    rows: tuple[OutOfWalletTx, ...]  # theo thứ tự thời gian

    @property
    def expenses(self) -> tuple[OutOfWalletTx, ...]:
        return tuple(r for r in self.rows if r.kind == "expense")

    @property
    def incomes(self) -> tuple[OutOfWalletTx, ...]:
        return tuple(r for r in self.rows if r.kind == "income")


@dataclass(frozen=True)
class OutOfWallet:
    persona: str
    anchor: date
    bank: str
    opening_balance_vnd: int
    sources: tuple[OutOfWalletSource, ...]

    def source(self, source_id: str) -> OutOfWalletSource:
        for s in self.sources:
            if s.id == source_id:
                return s
        raise PersonaError(f"Persona {self.persona}: không có nguồn nạp {source_id!r}")


def _fold(text: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def _collides(row_days: int, amount: int, avoid: list[tuple[int, int]], margin: int) -> bool:
    return any(a == amount and abs(d - row_days) <= margin for d, a in avoid)


def _dedupe_clear(rows: list[dict[str, Any]], avoid: list[tuple[int, int]], margin: int) -> None:
    """Nhích số tiền của dòng chi trùng (số tiền, ngày) với `avoid` đi một bội của 1.000, bù vào khoản lớn nhất còn lại."""
    for _ in range(10_000):
        bad = next(
            (r for r in rows if _collides(r["days_ago"], r["amount_vnd"], avoid, margin)), None
        )
        if bad is None:
            return
        donor = max((r for r in rows if r is not bad), key=lambda r: r["amount_vnd"], default=None)
        if donor is None:
            raise PersonaError("Nguồn chỉ có một khoản chi mà trùng số tiền với giao dịch trong ví")
        for step in range(1, 40):
            for delta in (step * _ROUND, -step * _ROUND):
                new_bad, new_donor = bad["amount_vnd"] + delta, donor["amount_vnd"] - delta
                if new_bad < _ROUND or new_donor < _ROUND:
                    continue
                if _collides(bad["days_ago"], new_bad, avoid, margin) or _collides(
                    donor["days_ago"], new_donor, avoid, margin
                ):
                    continue
                bad["amount_vnd"], donor["amount_vnd"] = new_bad, new_donor
                break
            else:
                continue
            break
        else:
            raise PersonaError("Không nhích được số tiền để tránh trùng giao dịch trong ví")
    raise PersonaError("Khử trùng số tiền không hội tụ")


def generate_out_of_wallet(
    persona: str,
    *,
    anchor: date,
    seed: int | None = None,
    specs_dir: Path = SPECS_DIR,
    spec: Mapping[str, Any] | None = None,
    data: PersonaData | None = None,
) -> OutOfWallet:
    """Dựng các nguồn nạp (sao kê CSV, ảnh biên lai) của `persona`. Tất định: cùng (persona, seed, anchor) -> cùng kết quả.

    Persona không khai `out_of_wallet` thì `PersonaError`."""
    spec = spec if spec is not None else load_spec(persona, specs_dir)
    cfg = spec.get("out_of_wallet")
    if not cfg:
        raise PersonaError(f"Persona {persona} không khai out_of_wallet")
    seed = spec["seed"] if seed is None else seed
    data = data or generate(persona, anchor=anchor, seed=seed, specs_dir=specs_dir, spec=spec)
    margin = int(cfg.get("dedupe_margin_days", 7))
    jar_codes = {j["code"] for j in spec["jars"]}
    payday_day = int(spec["payday_day"])

    # giao dịch đã có trong ví: tránh trùng số tiền (xem docstring module)
    avoid: list[tuple[int, int]] = [
        (t.days_ago, -t.amount_vnd) for t in data.transactions if t.kind == "expense"
    ]
    ext_income = [
        t for t in data.transactions if t.kind == "income" and t.funding_source == "external"
    ]
    income_text = str(spec.get("external_income", {}).get("statement_text", ""))

    sources: list[OutOfWalletSource] = []
    for src in cfg["sources"]:
        sid = src["id"]
        first, last = int(src["from_days_ago"]), int(src["to_days_ago"])
        if not (1 <= last <= first <= data.history_days):
            raise PersonaError(f"Nguồn {sid}: khoảng ngày {first}..{last} nằm ngoài lịch sử")
        rng = random.Random(f"{seed}:{persona}:oow:{sid}")
        rhythm = _rhythm(spec, {"rhythm": src.get("rhythm", {})})
        span = list(range(first, last - 1, -1))
        weights = _day_weights(span, anchor, payday_day, rhythm)

        spend: list[dict[str, Any]] = []
        for gi, group in enumerate(src["groups"]):
            if group["jar"] not in jar_codes:
                raise PersonaError(f"Nguồn {sid}: hũ {group['jar']} không có trong spec")
            merchants = group["merchants"]
            amounts = _split_total(
                rng, int(group["total_vnd"]), int(group["count"]), float(rhythm["amount_sigma"])
            )
            agos = _pick_days(rng, span, weights, len(amounts), int(rhythm["max_per_day"]))
            if len(agos) < len(amounts):
                raise PersonaError(f"Nguồn {sid}: max_per_day quá thấp cho {len(amounts)} khoản")
            rng.shuffle(amounts)
            for k, (amount, ago) in enumerate(zip(amounts, agos, strict=True)):
                m = rng.choices(
                    merchants, weights=[float(x.get("weight", 1.0)) for x in merchants], k=1
                )[0]
                spend.append(
                    {
                        "key": f"{sid}:{gi}:{k}",
                        "days_ago": ago,
                        "local_time": time(rng.randint(7, 21), rng.randint(0, 59)),
                        "amount_vnd": amount,
                        "jar_code": group["jar"],
                        "merchant": m["name"],
                        "tx_type": m["tx_type"],
                        "bank_text": m["bank_text"],
                        "receipt_style": m.get("receipt_style"),
                        "recipient_label": m.get("recipient_label"),
                    }
                )
        _dedupe_clear(spend, avoid, margin)
        avoid.extend((r["days_ago"], r["amount_vnd"]) for r in spend)

        rows = [
            OutOfWalletTx(
                kind="expense",
                source_id=sid,
                **{
                    **r,
                    "bank_text": r["bank_text"].replace(
                        "{ref}", f"FT26{rng.randrange(10**7, 10**8)}"
                    ),
                },
            )
            for r in spend
        ]
        if src.get("include_external_income"):
            for t in ext_income:
                if first >= t.days_ago >= last:
                    rows.append(
                        OutOfWalletTx(
                            key=f"{sid}:{t.key}", source_id=sid, days_ago=t.days_ago,
                            local_time=t.local_time, kind="income", amount_vnd=t.amount_vnd,
                            jar_code=None, merchant=t.merchant or "Thu nhập",
                            tx_type=t.tx_type, bank_text=income_text or _fold(t.merchant or "").upper(),
                        )
                    )  # fmt: skip
        rows.sort(key=lambda r: (-r.days_ago, r.local_time, r.key))
        sources.append(OutOfWalletSource(sid, src["channel"], first, last, tuple(rows)))
    return OutOfWallet(
        persona=persona,
        anchor=anchor,
        bank=str(cfg.get("bank", "")),
        opening_balance_vnd=int(cfg.get("opening_balance_vnd", 0)),
        sources=tuple(sources),
    )


# --- tệp mẫu ---------------------------------------------------------------------------------------------------------------
def statement_balances(oow: OutOfWallet, source_id: str) -> list[int]:
    """Số dư sau từng dòng của sao kê, từ `opening_balance_vnd` của tài khoản ngân hàng khác."""
    bal, out = oow.opening_balance_vnd, []
    for r in oow.source(source_id).rows:
        bal += r.amount_vnd if r.kind == "income" else -r.amount_vnd
        out.append(bal)
    return out


def _commas(v: int) -> str:
    return f"{v:,}"


def statement_csv(oow: OutOfWallet, source_id: str = "statement", *, seed: str = "") -> bytes:
    """Sao kê CSV kiểu Vietcombank (UTF-8 có BOM, xuống dòng CRLF, số có dấu phẩy, ngày dd/mm/yyyy), cùng cột và cùng cách ghi
    với `evals/ingest/synthetic/csv/c01_vcb_50.csv`. Số tham chiếu lấy từ `random.Random` theo seed (tất định)."""
    src = oow.source(source_id)
    rng = random.Random(f"{oow.persona}:{seed}:ref:{source_id}")
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(VCB_HEADER)
    for i, (r, bal) in enumerate(zip(src.rows, statement_balances(oow, source_id), strict=True), 1):
        d = r.app_date(oow.anchor)
        w.writerow(
            [
                i,
                d.strftime("%d/%m/%Y"),
                f"{rng.randrange(1000, 9999)} - {rng.randrange(10000, 99999)}",
                _commas(r.amount_vnd) if r.kind == "expense" else "",
                _commas(r.amount_vnd) if r.kind == "income" else "",
                _commas(bal),
                r.bank_text,
            ]
        )
    return buf.getvalue().encode("utf-8-sig")
