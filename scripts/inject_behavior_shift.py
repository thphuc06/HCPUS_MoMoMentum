# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3[crt]>=1.43,<2", "pycognito>=2024.5"]
# ///
"""Thêm giao dịch chi lệch mức cũ cho MỘT tài khoản thử để kiểm phát hiện đổi hành vi (tiêu chí 3 của phase 4).

    uv run scripts/inject_behavior_shift.py minh                       # chạy thử (mặc định): đọc dữ liệu, in kế hoạch, KHÔNG ghi
    uv run scripts/inject_behavior_shift.py minh --apply --consent     # ghi thật hai tuần chi lệch mức
    uv run scripts/inject_behavior_shift.py minh --mode one-off --apply --consent   # đối chứng: MỘT khoản lớn đơn lẻ

Cách làm: REST/ledger HIỆN CÓ, không ghi thẳng DB, không dùng secret master. `record_transaction` luôn ghi vào ngày mô phỏng HÔM NAY nên
không thêm được chi tiêu của hai tuần đã qua; đường duy nhất có ngày giao dịch của quá khứ là luồng nạp dữ liệu (F6): script dựng một
sao kê CSV kiểu Vietcombank (cùng định dạng `data/personas/samples/vy_sao_ke_vcb.csv`), tải lên bằng `POST /ingest/uploads` (S3
presigned POST), chờ worker đọc xong, đặt hũ cho từng dòng (`POST /ingest/rows/{id}/jar`) rồi chốt bằng `POST /ingest/confirmations`
và `POST /ingest/actions` (`confirm_rows`, token xác nhận). Dòng được ghi với `funding_source = external` (không đổi số dư hũ) nhưng vào
lịch sử chi của hũ (`app_get_daily_spend`), nên chuỗi chi theo tuần của hũ đổi đúng như một thói quen chi mới.

Mọi số đọc từ dữ liệu của chính tài khoản: mức chi tuần cũ là trung vị các tuần đầy đủ TRƯỚC hai tuần cuối của hũ (`GET /transactions`);
số khoản, nơi chi (tên cửa hàng) lấy từ lịch sử của hũ đó. `--factor` là bội số mức cũ cần đạt ở MỖI tuần lệch (mặc định 2: đủ lớn
để PELT xác nhận sau hai tuần giữ mức); chế độ `one-off` thêm một khoản bằng `--one-off-multiple` lần mức chi tuần cũ (mặc định 10).

Sau khi ghi (`--apply`), script in lệnh để chạy batch đêm. Việc phát hiện nằm ở `yofina_forecast.change.detect_and_store` (N2) do
người điều phối nối vào `run_user`:
  - Mong đợi (`--mode shift`): `behavior_flags` có một dòng `confirmed` cho hũ, `behavior.changed` đã phát, lộ trình phiên bản mới có
    lý do "hành vi thay đổi" (khi Lambda sinh lại lộ trình đã deploy).
  - Mong đợi (`--mode one-off`): KHÔNG có dấu hiệu `confirmed` mới và không có lộ trình mới.
Thao tác GHI (`--apply`) chạy trên tài khoản thử; hỏi chủ dự án trước khi chạy trên AWS thật, và đặt lại tài khoản sau khi thử
(`POST /demo/reset`, nút "Đặt lại dữ liệu") để không để rác trên tài khoản dùng chung.
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import random
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol

WEEK = 7
OPEN_ROW_STATUSES = ("auto_added", "pending")
CSV_HEADER = [
    "STT",
    "Ngày giao dịch",
    "Số tham chiếu",
    "Số tiền ghi nợ",
    "Số tiền ghi có",
    "Nội dung chi tiết",
]
ROUND = 1000  # VND, như bộ sinh persona
JOB_TERMINAL = ("review", "done", "failed", "rejected")
SEED = "inject_behavior_shift"  # hạt cố định: cùng dữ liệu vào thì cùng khoản thêm (chạy thử và chạy thật khớp nhau)


class ShiftError(RuntimeError):
    """Không lập được kế hoạch hoặc một bước REST thất bại (thông điệp tiếng Việt, in ra cho người chạy)."""


# --- kế hoạch (thuần, không I/O) --------------------------------------------------------------------------
@dataclass(frozen=True)
class Spend:
    """Một khoản chi trong lịch sử của hũ (từ `GET /transactions`)."""

    day: date
    amount_vnd: int
    merchant: str | None


@dataclass(frozen=True)
class PlannedRow:
    day: date
    amount_vnd: int
    description: str


def spend_of(tx: Mapping[str, Any], jar: str) -> Spend | None:
    """Khoản chi trừ tiền của hũ `jar`, không gắn nghĩa vụ (cùng quy tắc với `app_get_daily_spend`); None nếu không phải."""
    if tx.get("kind") != "expense" or tx.get("jar") != jar or tx.get("obligation_id"):
        return None
    if tx.get("funding_source") == "credit":
        return None
    return Spend(
        date.fromisoformat(str(tx["app_date"])[:10]), abs(int(tx["amount_vnd"])), tx.get("merchant")
    )


def weekly_totals(spends: Sequence[Spend], app_date: date, n_weeks: int) -> list[int]:
    """Tổng chi của `n_weeks` tuần đầy đủ gần nhất, CŨ TỚI MỚI; tuần mới nhất kết thúc hôm qua (như chuỗi tuần của bộ phát hiện)."""
    last = app_date - timedelta(days=1)
    out: list[int] = []
    for k in range(n_weeks, 0, -1):
        end = last - timedelta(days=WEEK * (k - 1))
        start = end - timedelta(days=WEEK - 1)
        out.append(sum(s.amount_vnd for s in spends if start <= s.day <= end))
    return out


def baseline_weekly(spends: Sequence[Spend], app_date: date, shift_weeks: int) -> int:
    """Mức chi tuần cũ: trung vị các tuần đầy đủ có chi TRƯỚC `shift_weeks` tuần cuối."""
    first = min((s.day for s in spends), default=None)
    if first is None:
        raise ShiftError("Hũ này chưa có khoản chi nào để lấy mức chi cũ.")
    total_weeks = ((app_date - timedelta(days=1)) - first).days // WEEK + 1
    weeks = weekly_totals(spends, app_date, total_weeks)[: max(total_weeks - shift_weeks, 0)]
    weeks = [w for w in weeks if w > 0]
    if len(weeks) < 2:
        raise ShiftError(
            "Chưa đủ lịch sử trước các tuần lệch để lấy mức chi cũ "
            f"(cần ít nhất 2 tuần có chi, đang có {len(weeks)}); chọn tài khoản có nhiều lịch sử hơn."
        )
    return round(statistics.median(weeks))


def _split(rng: random.Random, total: int, n: int) -> list[int]:
    """Chia `total` thành `n` khoản dương làm tròn 1.000: trọng số 0,6 đến 1,4, khoản lớn nhất nhận phần dư."""
    n = max(1, min(n, total // ROUND))
    w = [rng.uniform(0.6, 1.4) for _ in range(n)]
    parts = [max(ROUND, int(total * x / sum(w)) // ROUND * ROUND) for x in w]
    parts[parts.index(max(parts))] += total - sum(parts)
    return parts


def plan_shift(
    spends: Sequence[Spend],
    app_date: date,
    *,
    factor: float,
    shift_weeks: int = 2,
    seed: str = SEED,
) -> list[PlannedRow]:
    """Các khoản chi cần thêm để mỗi tuần trong `shift_weeks` tuần cuối đạt `factor` lần mức chi tuần cũ (không bớt tuần đã cao hơn)."""
    if factor <= 1:
        raise ShiftError("--factor phải lớn hơn 1.")
    base = baseline_weekly(spends, app_date, shift_weeks)
    target = round(base * factor)
    now_weeks = weekly_totals(spends, app_date, shift_weeks)
    span_weeks = max((app_date - min(s.day for s in spends)).days / WEEK, 1.0)
    n_per_week = max(3, round(len(spends) / span_weeks))  # số khoản chi tuần điển hình của hũ này
    names = [name for name, _ in Counter(s.merchant for s in spends if s.merchant).most_common()]
    rng = random.Random(f"{seed}:{app_date.isoformat()}:{factor}:{shift_weeks}")
    rows: list[PlannedRow] = []
    last = app_date - timedelta(days=1)
    for i, current in enumerate(now_weeks):  # i = 0 là tuần cũ nhất trong các tuần lệch
        extra = target - current
        if extra < ROUND:
            continue
        end = last - timedelta(days=WEEK * (shift_weeks - 1 - i))
        days = [end - timedelta(days=d) for d in range(WEEK)]
        for amount in _split(rng, extra // ROUND * ROUND, n_per_week):
            rows.append(
                PlannedRow(rng.choice(days), amount, rng.choice(names) if names else "Chi tiêu")
            )
    if not rows:
        raise ShiftError(
            f"Hai tuần cuối của hũ đã đạt {factor} lần mức cũ ({base:,} VND mỗi tuần); không có gì để thêm."
        )
    return sorted(rows, key=lambda r: (r.day, r.amount_vnd))


def plan_one_off(
    spends: Sequence[Spend], app_date: date, *, multiple: float, shift_weeks: int = 2
) -> list[PlannedRow]:
    """MỘT khoản chi lớn đơn lẻ, bằng `multiple` lần mức chi tuần cũ, rơi vào giữa tuần cuối."""
    if multiple <= 1:
        raise ShiftError("--one-off-multiple phải lớn hơn 1.")
    base = baseline_weekly(spends, app_date, shift_weeks)
    names = [name for name, _ in Counter(s.merchant for s in spends if s.merchant).most_common()]
    return [
        PlannedRow(
            app_date - timedelta(days=4),
            round(base * multiple) // ROUND * ROUND,
            names[0] if names else "Chi tiêu",
        )
    ]


def build_csv(rows: Sequence[PlannedRow], *, run_id: str) -> bytes:
    """Sao kê CSV kiểu Vietcombank (cột và cách ghi như `data/personas/samples/vy_sao_ke_vcb.csv`, có BOM UTF-8). `run_id` vào số tham
    chiếu để hai lần chạy khác nhau không có cùng nội dung (một tệp trùng nội dung bị từ chối `INGEST_DUPLICATE_FILE`)."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(CSV_HEADER)
    for i, r in enumerate(rows, 1):
        w.writerow(
            [
                i,
                r.day.strftime("%d/%m/%Y"),
                f"{run_id[:4]} - {10000 + i}",
                f"{r.amount_vnd:,}",
                "",
                f"THANH TOAN {r.description.upper()} FT{run_id[4:10]}{i:03d}",
            ]
        )
    return ("﻿" + buf.getvalue()).encode("utf-8")


def describe(plan: Sequence[PlannedRow], jar: str, base: int, mode: str) -> str:
    total = sum(r.amount_vnd for r in plan)
    lines = [
        f"Chế độ {mode}: hũ {jar}, mức chi tuần cũ (trung vị) {base:,} VND.",
        f"Sẽ thêm {len(plan)} khoản chi, tổng {total:,} VND, từ {plan[0].day} đến {plan[-1].day}:",
    ]
    lines += [f"  {r.day}  {r.amount_vnd:>12,}  {r.description}" for r in plan]
    return "\n".join(lines)


# --- REST -------------------------------------------------------------------------------------------------------
class Api(Protocol):
    """Phần REST script dùng (bản thật `HttpApi`; test dùng bản giả)."""

    def get(self, path: str) -> Any: ...

    def post(self, path: str, body: Any) -> Any: ...

    def upload(self, up: Mapping[str, Any], data: bytes, mime: str) -> None: ...


def history(api: Api, jar: str, *, max_pages: int = 40) -> tuple[date, list[Spend]]:
    """(ngày mô phỏng hôm nay, các khoản chi của hũ), đọc hết các trang `GET /transactions`."""
    spends: list[Spend] = []
    app_date: date | None = None
    path = f"/transactions?jar={jar}&kind=expense&limit=50"
    for _ in range(max_pages):
        page = api.get(path)
        app_date = date.fromisoformat(page["app_date"])
        spends += [s for t in page["transactions"] if (s := spend_of(t, jar))]
        if not page.get("next_cursor"):
            break
        path = f"/transactions?jar={jar}&kind=expense&limit=50&cursor={page['next_cursor']}"
    if app_date is None:
        raise ShiftError("Không đọc được ngày mô phỏng.")
    return app_date, spends


def wait_job(api: Api, job_id: str, *, timeout: float, sleep: float = 3.0) -> dict:
    end = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < end:
        job = api.get(f"/ingest/jobs/{job_id}")
        last = (job["status"], job.get("progress"))
        if job["status"] in JOB_TERMINAL:
            return job
        time.sleep(sleep)
    raise ShiftError(
        f"Job nạp {job_id} chưa xong sau {timeout:.0f} giây (trạng thái cuối: {last})."
    )


def apply_plan(
    api: Api, plan: Sequence[PlannedRow], jar: str, *, consent: bool, timeout: float
) -> dict[str, Any]:
    """Tải sao kê lên, chờ đọc, đặt hũ, chốt. Trả tóm tắt (số dòng ghi, trùng, bỏ)."""
    data = build_csv(plan, run_id=uuid.uuid4().hex)
    body: dict[str, Any] = {"source_kind": "csv", "mime": "text/csv", "size_bytes": len(data)}
    if consent:
        body["consent"] = True
    up = api.post("/ingest/uploads", body)
    job_id = up["job_id"]
    api.upload(up, data, "text/csv")
    job = wait_job(api, job_id, timeout=timeout)
    if job["status"] != "review":
        raise ShiftError(
            f"Job nạp kết thúc ở trạng thái {job['status']}: {job.get('error_code')} {job.get('error_message', '')}"
        )
    rows = job["review"]["data"]["rows"]
    jars = {j["code"] for j in job["review"]["data"]["jars"]}
    if jar not in jars:
        raise ShiftError(f"Hũ {jar} không có trong danh sách hũ của lần nạp ({sorted(jars)}).")
    open_rows = [
        r for r in rows if r["review_status"] in OPEN_ROW_STATUSES and r["kind"] == "expense"
    ]
    duplicates = [r for r in rows if r["review_status"] == "duplicate"]
    if not open_rows:
        raise ShiftError(
            "Mọi dòng đều bị coi là trùng sổ cái hoặc đã bị loại; không có gì để chốt."
        )
    for r in open_rows:  # đặt hũ cho mọi dòng (một chạm), không tin gợi ý của mô hình
        if r.get("suggested_jar", {}).get("code") != jar:
            api.post(f"/ingest/rows/{r['row_id']}/jar", {"jar": jar})
    params = {
        "job_id": job_id,
        "rows": [{"row_id": r["row_id"], "jar": jar} for r in open_rows],
    }
    conf = api.post("/ingest/confirmations", {"tool": "confirm_rows", "params": params})
    receipt = api.post(
        "/ingest/actions",
        {
            "tool": "confirm_rows",
            "params": conf.get("params", params),
            "confirm_token": conf["confirm_token"],
        },
    )
    return {
        "job_id": job_id,
        "rows_written": len(open_rows),
        "rows_duplicate": len(duplicates),
        "amount_vnd": sum(int(r["amount_vnd"]) for r in open_rows),
        "receipt_type": receipt.get("type"),
    }


class HttpApi:
    """REST thật bằng `scripts/_demo_auth.py` (đăng nhập SRP tài khoản demo, token không in ra)."""

    def __init__(self, base: str, token: str) -> None:
        self.base, self.token = base, token

    def _call(self, method: str, path: str, body: Any = None) -> Any:
        from _demo_auth import call_api

        status, resp, _ms = call_api(self.base, method, path, self.token, body, timeout=60.0)
        if status != 200:
            err = resp.get("error", {}) if isinstance(resp, dict) else {}
            raise ShiftError(
                f"{method} {path} -> {status} {err.get('code', '')} {err.get('message', resp)}"
            )
        return resp

    def get(self, path: str) -> Any:
        return self._call("GET", path)

    def post(self, path: str, body: Any) -> Any:
        return self._call("POST", path, body)

    def upload(self, up: Mapping[str, Any], data: bytes, mime: str) -> None:
        """Presigned POST của S3: trường form theo đúng thứ tự cấp, trường `file` đặt CUỐI."""
        boundary = "----yofina" + uuid.uuid4().hex
        parts: list[bytes] = []
        for k, v in up["fields"].items():
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
            )
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="upload"\r\n'
            f"Content-Type: {mime}\r\n\r\n".encode()
            + data
            + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(
            up["url"],
            data=b"".join(parts),
            method="POST",
            headers={"content-type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60.0) as resp:
                ok = resp.status in (200, 201, 204)
        except urllib.error.HTTPError as exc:
            raise ShiftError(f"Tải lên S3 thất bại: {exc.code} {exc.read()[:300]!r}") from exc
        if not ok:
            raise ShiftError("Tải lên S3 thất bại.")


def jwt_sub(token: str) -> str:
    """Claim `sub` của access token (chỉ để in hướng dẫn; không kiểm chữ ký)."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return str(json.loads(base64.urlsafe_b64decode(payload))["sub"])


def next_steps(sub: str, mode: str, jar: str) -> str:
    expect = (
        f"behavior_flags có một dòng confirmed cho hũ {jar} và sự kiện behavior.changed đã phát"
        if mode == "shift"
        else f"KHÔNG có dòng confirmed mới cho hũ {jar} (một khoản lớn đơn lẻ không phải đổi hành vi)"
    )
    return (
        "\nBước tiếp theo (chạy batch đêm cho tài khoản này, sau khi người điều phối đã nối N2 vào run_user):\n"
        f"  aws lambda invoke --region ap-southeast-1 --function-name yofina-forecast-batch --cli-binary-format raw-in-base64-out "
        f"--payload '{json.dumps({'op': 'run_user', 'user_id': sub, 'trigger': 'nightly'})}' out.json\n"
        f"Mong đợi: {expect}.\n"
        "Kiểm: SELECT jar_code, status, method, direction, old_weekly_vnd, new_weekly_vnd, change_point_date, weeks_held "
        "FROM behavior_flags WHERE user_id = '<sub>'; rồi GET /roadmap (phiên bản mới, lý do behavior_changed).\n"
        "Sau khi thử, đặt lại tài khoản (POST /demo/reset hoặc nút Đặt lại dữ liệu) để xóa dữ liệu đã thêm."
    )


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument(
        "account", help="tên tài khoản demo trong secret yofina-demo-accounts (ví dụ minh)"
    )
    ap.add_argument("--mode", choices=("shift", "one-off"), default="shift")
    ap.add_argument("--jar", default="an_uong", help="mã hũ chi tiêu (mặc định an_uong)")
    ap.add_argument(
        "--factor", type=float, default=2.0, help="bội số mức chi tuần cũ cần đạt ở mỗi tuần lệch"
    )
    ap.add_argument("--weeks", type=int, default=2, help="số tuần lệch mức (mặc định 2)")
    ap.add_argument(
        "--one-off-multiple",
        type=float,
        default=10.0,
        help="khoản lớn đơn lẻ = số lần mức chi tuần cũ",
    )
    ap.add_argument(
        "--apply", action="store_true", help="GHI thật qua REST (không có thì chỉ chạy thử)"
    )
    ap.add_argument(
        "--consent",
        action="store_true",
        help="đồng ý nạp dữ liệu CSV cho tài khoản này (cần lần đầu)",
    )
    ap.add_argument("--timeout", type=float, default=300.0, help="giây chờ worker đọc tệp")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    from _demo_auth import api_url, login_access_token

    token = login_access_token(args.account)
    api = HttpApi(api_url(), token)
    app_date, spends = history(api, args.jar)
    base = baseline_weekly(spends, app_date, args.weeks)
    plan = (
        plan_shift(spends, app_date, factor=args.factor, shift_weeks=args.weeks)
        if args.mode == "shift"
        else plan_one_off(spends, app_date, multiple=args.one_off_multiple, shift_weeks=args.weeks)
    )
    print(describe(plan, args.jar, base, args.mode))
    if not args.apply:
        print("\nChạy thử: chưa ghi gì. Thêm --apply (và --consent lần đầu) để ghi thật.")
        return 0
    summary = apply_plan(api, plan, args.jar, consent=args.consent, timeout=args.timeout)
    print("\nĐã chốt:", json.dumps(summary, ensure_ascii=False))
    print(next_steps(jwt_sub(token), args.mode, args.jar))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ShiftError as exc:
        print("Lỗi:", exc, file=sys.stderr)
        sys.exit(1)
