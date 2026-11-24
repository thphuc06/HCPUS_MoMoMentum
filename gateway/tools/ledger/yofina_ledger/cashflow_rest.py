"""REST `GET /cashflow`: bản REST của tool `ledger___get_cashflow_summary` cho ba biểu đồ chi tiêu của màn Hoạt động (B1, B5, B7 trong
docs/research/spending-visualization.md). Nối vào `rest_api._dispatch` bằng MỘT dòng. Danh tính chỉ lấy từ claim `sub` do `rest_api`
truyền; mọi hàm SQL tự đặt `app.user_id` nên RLS chỉ cho thấy dòng của người gọi. Không ghi gì, không gọi model.

Một công thức, hai đường vào. Mọi tổng thu, tổng chi, chi theo hũ đều do `LedgerService.cashflow_result` (đúng hàm của tool, SQL
`app_get_cashflow_summary` của migration 0050) tính:

- Kỳ này: kỳ lương hiện tại theo ngày mô phỏng (`app_today` qua `service._app_date`), từ ngày lương gần nhất (`latest_payday`, ngày lương
  trong hồ sơ) tới hôm nay. Chưa khai ngày lương thì như tool: từ mùng 1 của tháng.
- Kỳ trước: từ ngày lương trước đó, TÍNH TỚI CÙNG SỐ NGÀY trong kỳ (ngày thứ n của kỳ này so với ngày thứ n của kỳ trước), không quá
  ngày cuối của kỳ trước. Chưa có giao dịch nào từ ngày đầu kỳ trước trở về trước (kỳ trước chưa trọn dữ liệu, như persona `khoa`)
  thì không có `previous`.
- `daily[]` và `previous_daily[]`: chi từng ngày bằng CÙNG hàm `app_get_cashflow_summary(uid, ngày, ngày)`, gọi cho mọi ngày trong MỘT
  câu SQL (`generate_series`), rồi cộng dồn. Kỳ trước lấy cả kỳ để đường kỳ trước kéo hết kỳ.

Tách nghĩa vụ và Trả sau (`obligation_vnd`, `credit_vnd`): hàm SQL của tool không tách, và đợt này không thêm hàm DB. Phần tách vì vậy
cộng từ `app_list_transactions` (hàm sẵn có, cùng bộ lọc với tool: `kind = expense`, bỏ `funding_source = external`, cùng khoảng
`app_date`), phân trang con trỏ, tối đa `SPLIT_MAX_PAGES` trang mỗi kỳ. Hai điều kiện để trả phần tách: đọc hết các trang, và số dòng
từng hũ đúng bằng `tx_count` của tool, phần tách không vượt `spent_vnd` của hũ. Sai một điều kiện thì bỏ mọi trường tách
(`split_complete` sai, có log) thay vì trả số lệch với tổng.

- `obligation_vnd`: dòng có `obligation_id` (khoản cố định trả theo lịch nghĩa vụ: tiền nhà, hóa đơn, kỳ trả Trả sau).
- `credit_vnd`: dòng `funding_source = credit` không gắn nghĩa vụ (món mua bằng Trả sau).
- `regular_spent_vnd`: chi thường ngày = `spent_vnd − obligation_vnd` (gồm cả món mua Trả sau).

Chênh lệch (`change`, `by_jar[].change_vnd`) và phần còn lại sau chi (`net_vnd` = lương − chi, không tính tiền vào khác) do server trừ,
để giao diện chỉ vẽ.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

from yofina_core.clock import latest_payday, next_payday
from yofina_ledger import convert

log = logging.getLogger("yofina.ledger.cashflow")

ROUTE = "GET /cashflow"
#: Một câu SQL cho mọi ngày của một khoảng: đúng hàm của tool, gọi với from = to = từng ngày. `days` tối đa 31 (một kỳ lương).
SQL_DAILY = (
    "SELECT s.d AS day, app_get_cashflow_summary(:uid, s.d, s.d) AS data "
    "FROM (SELECT CAST(:from_date AS date) + i AS d FROM generate_series(0, CAST(:days AS integer) - 1) AS i) s "
    "ORDER BY s.d"
)
DAILY_MAX = 31
#: Trang của `app_list_transactions` (hàm SQL tự chặn 51 dòng).
SPLIT_PAGE = 51
#: Tối đa số trang mỗi kỳ khi cộng phần tách (khoảng 1.000 dòng chi trong một kỳ lương). Quá thì bỏ phần tách.
SPLIT_MAX_PAGES = 20


def dispatch(
    route: str, event: Mapping[str, Any], sub: str, trace_id: str, service: Any
) -> tuple[int, dict[str, Any]]:
    # Không có tham số: kỳ do server chọn theo ngày mô phỏng và ngày lương.
    del route, event, trace_id
    return 200, cashflow_response(service, sub)


def _iso(value: Any) -> str:
    d = convert.to_date(value)
    if d is None:
        raise ValueError("thiếu ngày")
    return d.isoformat()


# --- kỳ ---------------------------------------------------------------------------------------------------
def _month_end(d: date) -> date:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def periods(payday_day: int | None, today: date) -> dict[str, Any]:
    """Kỳ này (từ đầu kỳ tới hôm nay, cả ngày cuối kỳ) và kỳ trước (cả kỳ, và phần tới cùng số ngày). Thuần, không đọc đồng hồ."""
    if payday_day:
        start = latest_payday(payday_day, today)
        end = next_payday(payday_day, start) - timedelta(days=1)
        prev_start = latest_payday(payday_day, start - timedelta(days=1))
        kind = "pay_period"
    else:  # chưa khai ngày lương: như tool, kỳ là tháng dương lịch
        start = today.replace(day=1)
        end = _month_end(today)
        prev_start = (start - timedelta(days=1)).replace(day=1)
        kind = "calendar_month"
    day_index = (today - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_to = min(prev_start + timedelta(days=day_index - 1), prev_end)
    return {
        "kind": kind,
        "start": start,
        "today": today,
        "end": end,
        "day_index": day_index,
        "days_total": (end - start).days + 1,
        "prev_start": prev_start,
        "prev_to": prev_to,
        "prev_end": prev_end,
    }


# --- đọc --------------------------------------------------------------------------------------------------
def _daily(service: Any, sub: str, start: date, end: date) -> list[dict[str, Any]]:
    """Chi từng ngày trong [start, end] bằng đúng hàm của tool. `spent_vnd` của một ngày = tổng `by_jar` như `cashflow_result`."""
    days = (end - start).days + 1
    if days <= 0:
        return []
    rows = service.repo.db.query(
        SQL_DAILY,
        {"uid": sub, "from_date": start, "days": min(days, DAILY_MAX)},
        max_rows=DAILY_MAX,
    )
    out = []
    for r in rows:
        data = r["data"] or {}
        spent = sum(
            convert.vnd(j["spent_vnd"]) for j in data.get("by_jar", []) if j.get("jar_code")
        )
        out.append({"date": _iso(r["day"]), "spent_vnd": spent})
    return out


def _expense_rows(
    service: Any, sub: str, start: date, end: date
) -> tuple[list[dict[str, Any]], bool]:
    """Mọi dòng chi CỦA VÍ (bỏ external) trong [start, end] qua `app_list_transactions`. Trả (dòng, đã đọc hết chưa)."""
    rows: list[dict[str, Any]] = []
    cursor: tuple[Any, str] | None = None
    for _ in range(SPLIT_MAX_PAGES):
        page = service.repo.list_transactions(
            sub, kind="expense", from_date=start, to_date=end, cursor=cursor, limit=SPLIT_PAGE
        )
        rows.extend(r for r in page if r.get("funding_source") != "external")
        if len(page) < SPLIT_PAGE:
            return rows, True
        last = page[-1]
        cursor = (last["occurred_at"], str(last["id"]))
    return rows, False


def _split(rows: list[dict[str, Any]], start: date, end: date) -> dict[str, Any]:
    """Cộng phần nghĩa vụ và Trả sau theo hũ và theo ngày cho các dòng có `app_date` trong [start, end]."""
    by_jar: dict[str, dict[str, int]] = defaultdict(
        lambda: {"obligation": 0, "credit": 0, "count": 0}
    )
    by_day: dict[str, int] = defaultdict(int)
    for r in rows:
        d = convert.to_date(r["app_date"])
        if d is None or not start <= d <= end:
            continue
        day = d.isoformat()
        jar = r.get("jar_code")
        amount = -convert.vnd(r["amount_vnd"])
        slot = by_jar[jar or ""]
        slot["count"] += 1
        if r.get("obligation_id"):
            slot["obligation"] += amount
            by_day[day] += amount
        elif r.get("funding_source") == "credit":
            slot["credit"] += amount
    return {"by_jar": by_jar, "by_day": by_day}


def _split_matches(split: dict[str, Any], summary: dict[str, Any]) -> bool:
    """Phần tách khớp tool: cùng số dòng từng hũ, phần tách không vượt chi của hũ."""
    tool = {j["jar"]: j for j in summary["by_jar"]}
    mine = {k: v for k, v in split["by_jar"].items() if k}
    if set(tool) != set(mine):
        return False
    for code, j in tool.items():
        s = mine[code]
        if s["count"] != j["tx_count"] or s["obligation"] + s["credit"] > j["spent_vnd"]:
            return False
    return True


# --- dựng phản hồi --------------------------------------------------------------------------------------------
def _totals(summary: dict[str, Any], split: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "from_date": summary["from_date"],
        "to_date": summary["to_date"],
        "salary_income_vnd": summary["salary_income_vnd"],
        "other_income_vnd": summary["other_income_vnd"],
        "spent_vnd": summary["spent_vnd"],
        "net_vnd": summary["salary_income_vnd"] - summary["spent_vnd"],
    }
    if split is not None:
        obligation = sum(v["obligation"] for v in split["by_jar"].values())
        out["obligation_vnd"] = obligation
        out["credit_vnd"] = sum(v["credit"] for v in split["by_jar"].values())
        out["regular_spent_vnd"] = summary["spent_vnd"] - obligation
    return out


def _series(
    daily: list[dict[str, Any]], start: date, split: dict[str, Any] | None
) -> list[dict[str, Any]]:
    out = []
    total = regular = 0
    for d in daily:
        total += d["spent_vnd"]
        item: dict[str, Any] = {
            "date": d["date"],
            "day_index": (date.fromisoformat(d["date"]) - start).days + 1,
            "spent_vnd": d["spent_vnd"],
            "cumulative_vnd": total,
        }
        if split is not None:
            obligation = split["by_day"].get(d["date"], 0)
            regular += d["spent_vnd"] - obligation
            item["obligation_vnd"] = obligation
            item["regular_cumulative_vnd"] = regular
        out.append(item)
    return out


def cashflow_response(service: Any, sub: str) -> dict[str, Any]:
    now = service.now()
    row = service.repo.user_row(sub)
    offset = int(row["clock_offset_days"]) if row else 0
    payday = int(row["payday_day"]) if row and row.get("payday_day") else None
    p = periods(payday, service._app_date(offset, now))
    start, today = p["start"], p["today"]

    cur = service.cashflow_result(sub, from_date=start.isoformat(), to_date=today.isoformat())
    current = cur["data"]
    # Kỳ trước chỉ so được khi có dữ liệu từ ngày đầu kỳ trước trở về trước (không thì phần thiếu bị coi như chi 0 ₫).
    has_prev = bool(service.repo.list_transactions(sub, to_date=p["prev_start"], limit=1))
    previous = (
        service.cashflow_result(
            sub, from_date=p["prev_start"].isoformat(), to_date=p["prev_to"].isoformat()
        )["data"]
        if has_prev
        else None
    )

    # Phần tách nghĩa vụ / Trả sau: chỉ trả khi đọc hết và khớp tool ở cả hai kỳ.
    cur_rows, cur_full = _expense_rows(service, sub, start, today)
    cur_split: dict[str, Any] | None = _split(cur_rows, start, today)
    prev_split_to: dict[str, Any] | None = None
    prev_split_full: dict[str, Any] | None = None
    ok = cur_full and _split_matches(cur_split, current)  # type: ignore[arg-type]
    if ok and previous is not None:
        prev_rows, prev_full = _expense_rows(service, sub, p["prev_start"], p["prev_end"])
        prev_split_to = _split(prev_rows, p["prev_start"], p["prev_to"])
        prev_split_full = _split(prev_rows, p["prev_start"], p["prev_end"])
        ok = prev_full and _split_matches(prev_split_to, previous)
    if not ok:
        log.warning(
            json.dumps({"msg": "cashflow_split_incomplete", "from_date": start.isoformat()})
        )
        cur_split = prev_split_to = prev_split_full = None

    out: dict[str, Any] = {
        "as_of": cur["as_of"],
        "app_date": cur["app_date"],
        "period": {
            "kind": p["kind"],
            "from_date": start.isoformat(),
            "to_date": today.isoformat(),
            "end_date": p["end"].isoformat(),
            "day_index": p["day_index"],
            "days_total": p["days_total"],
        },
        "current": _totals(current, cur_split),
        "by_jar": [],
        "daily": _series(_daily(service, sub, start, today), start, cur_split),
        "unclassified_pending_vnd": current["unclassified_pending_vnd"],
        "split_complete": cur_split is not None,
    }
    prev_by_jar: dict[str, dict[str, Any]] = {}
    if previous is not None:
        out["previous"] = {
            **_totals(previous, prev_split_to),
            "end_date": p["prev_end"].isoformat(),
        }
        change: dict[str, Any] = {"spent_vnd": current["spent_vnd"] - previous["spent_vnd"]}
        if cur_split is not None:
            change["regular_vnd"] = (
                out["current"]["regular_spent_vnd"] - out["previous"]["regular_spent_vnd"]
            )
        out["change"] = change
        out["previous_daily"] = _series(
            _daily(service, sub, p["prev_start"], p["prev_end"]), p["prev_start"], prev_split_full
        )
        prev_by_jar = {j["jar"]: j for j in previous["by_jar"]}

    jars: list[dict[str, Any]] = []
    for j in current["by_jar"]:
        jars.append(_jar(j["jar"], j["name"], j["spent_vnd"], j["tx_count"], cur_split))
    for code, j in prev_by_jar.items():  # hũ kỳ trước có chi mà kỳ này chưa: vẫn hiện để thấy giảm
        if code not in {x["jar"] for x in jars}:
            jars.append(_jar(code, j["name"], 0, 0, cur_split))
    if previous is not None:
        for x in jars:
            before = prev_by_jar.get(x["jar"], {}).get("spent_vnd", 0)
            x["previous_spent_vnd"] = before
            x["change_vnd"] = x["spent_vnd"] - before
    jars.sort(key=lambda x: (-x["spent_vnd"], -x.get("previous_spent_vnd", 0), x["jar"]))
    out["by_jar"] = jars
    return out


def _jar(
    code: str, name: str, spent: int, count: int, split: dict[str, Any] | None
) -> dict[str, Any]:
    item: dict[str, Any] = {"jar": code, "name": name, "spent_vnd": spent, "tx_count": count}
    if split is not None:
        s = split["by_jar"].get(code, {"obligation": 0, "credit": 0})
        item["obligation_vnd"] = s["obligation"]
        item["credit_vnd"] = s["credit"]
    return item
