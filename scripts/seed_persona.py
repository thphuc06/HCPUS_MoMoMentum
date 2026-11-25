# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3[crt]>=1.43,<2", "pydantic>=2.9,<3", "tzdata>=2024.1"]
# ///
"""Nạp persona cho MỘT tài khoản demo ngay từ máy bạn qua RDS Data API, KHÔNG cần Lambda ledger đã deploy lại.

    uv run scripts/seed_persona.py giamkhao3                 # chạy thử (mặc định): dựng dữ liệu, in kế hoạch, KHÔNG gọi AWS
    uv run scripts/seed_persona.py giamkhao3 --apply         # ghi thật: nhóm Cognito + sổ cái trong Aurora

Vì sao có script này: `POST /demo/reset` (và nút "Đặt lại dữ liệu") chỉ biết các persona có trong zip của Lambda `yofina-ledger`
(`data/personas` đóng cùng zip). Persona mới như `vy` chưa có trong zip đã deploy cho tới khi ledger được đóng gói lại và deploy;
script này dùng CHÍNH mã đặt lại của ledger như thư viện (`LedgerService.reset_demo`: bộ sinh `personas.generate` + `materialize`,
rồi `LedgerRepo.reset_user`: MỘT transaction xóa dữ liệu của chính tài khoản đó, nạp hũ, nghĩa vụ, sổ cái kể cả dòng
`funding_source external`, dựng lại số dư hũ từ các dòng trả bằng hũ) nên kết quả y hệt một lần đặt lại.

Dry-run (không có `--apply`) không import boto3 và không mở kết nối nào: chỉ chạy bộ sinh cục bộ, kiểm bất biến (số dư mỗi hũ = tổng các
dòng trả bằng hũ), in số dòng theo nguồn trả và độ phủ dữ liệu dự kiến bằng `yofina_core.ingest.coverage_ratio` trên đúng các dòng sẽ ghi.

`--apply` làm (theo thứ tự; thao tác GHI nằm ở bước 3 và 4, hỏi chủ dự án trước khi chạy trên AWS thật):
1. Đọc (không ghi): SSM `/yofina/db/*`, user Cognito của tài khoản (lấy `sub`, là khóa RLS `app.user_id`), cấu hình Lambda ledger
   (`YOFINA_DEMO_ANCHOR_DATE`, `YOFINA_APP_TIMEZONE`, ... để cùng ngày neo với endpoint; quyền `lambda:GetFunctionConfiguration`).
2. Dùng secret của role `yofina_app` (không phải master): Data API tự đọc secret bằng quyền của người chạy.
3. GHI Cognito: nhóm `persona-<persona>` (tạo nếu thiếu) và đưa tài khoản vào nhóm đó (như scripts/seed_demo.py). `--skip-group` bỏ bước này.
4. GHI Aurora: `reset_demo` (xóa rồi nạp lại dữ liệu CỦA TÀI KHOẢN NÀY, phát `profile.updated`). `--forecast` tính dự báo ngay
   (gọi Lambda `yofina-forecast-batch`); không có thì dự báo được tính khi tài khoản mở app (đọc cũ kích hoạt tính lại).

Lưu ý: nhóm Cognito đổi sang `persona-vy` mà ledger CHƯA biết `vy` thì nút "Đặt lại dữ liệu" của tài khoản đó trả 403 (xem
data/personas/README.md, mục "Nạp persona mới lên AWS").
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
for _extra in ("libs/yofina_core/src", "gateway/tools/ledger", "data"):
    sys.path.insert(0, str(ROOT / _extra))

import personas  # noqa: E402
from yofina_core import ingest  # noqa: E402

ACCOUNTS_FILE = ROOT / "data" / "personas" / "accounts.json"
#: mặc định khi chạy thử (khớp context CDK `demoAnchorDate` và `appTimezone` của stack YofinaTools); `--apply` đọc từ Lambda đã deploy
DEFAULT_ANCHOR = "2026-11-21"
DEFAULT_TZ = "Asia/Ho_Chi_Minh"
DEFAULT_LEDGER_FUNCTION = "yofina-ledger"


def plan(
    persona: str, *, anchor: date, now: datetime, tz: ZoneInfo, user_id: str = "dry-run"
) -> dict:
    """Dựng dữ liệu sẽ nạp và kiểm bất biến. Thuần (không I/O), dùng cho chạy thử và test.

    Trả: `materialized`, số dòng theo (kind, funding_source), số dư mỗi hũ dựng từ dòng trả bằng hũ (đúng thứ `SQL_RECOMPUTE_BALANCES`
    sẽ ghi), các thành phần độ phủ và độ phủ dự kiến."""
    data = personas.generate(persona, anchor=anchor)
    mat = personas.materialize(data, anchor=anchor, now=now, tz=tz, user_id=user_id)
    rows = mat.transaction_rows
    jar_codes = {j["code"] for j in mat.jars}
    jar_rows = [r for r in rows if r["funding_source"] == "jar"]
    # hai hũ hệ thống do `app_ensure_system_jars` tạo; dòng của chúng vẫn là dòng trả bằng hũ
    for r in jar_rows:
        if r["jar_code"] is None:
            raise AssertionError(f"Dòng trả bằng hũ không có hũ: {r['id']}")
    balances: dict[str, int] = {}
    for r in jar_rows:
        balances[r["jar_code"]] = balances.get(r["jar_code"], 0) + int(r["amount"])
    for r in rows:
        if (
            r["funding_source"] == "external"
        ):  # không đổi số dư; thu nhập ngoài ví không hũ, chi ngoài ví có hũ
            if r["transfer_id"] or r["obligation_id"]:
                raise AssertionError(f"Dòng external có chuyển hũ hoặc nghĩa vụ: {r['id']}")
            if r["kind"] == "expense" and r["jar_code"] not in jar_codes:
                raise AssertionError(f"Chi ngoài ví thiếu hũ: {r['id']}")
    for j in data.jars:  # bất biến bộ sinh: số dư cuối từng hũ bằng số dư cần đạt trong spec
        if balances.get(j.code, 0) != j.balance_vnd:
            raise AssertionError(
                f"Hũ {j.code}: số dư dựng {balances.get(j.code, 0)} khác {j.balance_vnd}"
            )
    income = sum(
        int(r["amount"])
        for r in rows
        if r["kind"] == "income"
        and (
            (r["tx_type"] == "salary" and r["funding_source"] == "jar")
            or r["funding_source"] == "external"
        )
    )
    spend = sum(
        -int(r["amount"])
        for r in rows
        if r["kind"] == "expense" and r["funding_source"] in ("jar", "external")
    )
    net_jar = sum(int(r["amount"]) for r in jar_rows)
    facts = {
        "income_vnd": income,
        "spend_vnd": spend,
        "balance_start_vnd": 0,  # số dư đầu cửa sổ: lịch sử bắt đầu từ ngày đầu, số dư đầu kỳ là một dòng giao dịch
        "balance_end_vnd": net_jar,
    }
    return {
        "materialized": mat,
        "counts": Counter((r["kind"], r["funding_source"]) for r in rows),
        "balances": balances,
        "facts": facts,
        "coverage": ingest.coverage_ratio(facts),
    }


def print_plan(account: str, persona: str, p: dict) -> None:
    mat = p["materialized"]
    print(f"tài khoản {account} -> persona {persona}")
    print(
        f"  ngày neo {mat.app_date}, clock_offset_days {mat.clock_offset_days}, "
        f"{len(mat.jars)} hũ, {len(mat.transaction_rows)} dòng sổ cái, {len(mat.obligations)} nghĩa vụ, {len(mat.payees)} người nhận"
    )
    for (kind, funding), n in sorted(p["counts"].items()):
        print(f"  dòng {kind:8s} funding_source={funding:8s}: {n}")
    for j in mat.jars:
        print(f"  hũ {j['code']:12s} số dư {p['balances'].get(j['code'], 0):>12,} đ")
    print(f"  thành phần độ phủ: {json.dumps(p['facts'])}")
    print(f"  độ phủ dữ liệu dự kiến: {p['coverage']}")


def apply(args, account: str, persona: str, mapping_prefix: str) -> int:
    """Phần GHI. Import boto3 và mã ledger tại đây để chạy thử không cần mạng."""
    from _yofina import REGION, session, ssm_param
    from create_demo_users import EMAIL_DOMAIN
    from seed_demo import ensure_groups

    from yofina_core.config import Config
    from yofina_core.db import DataApi, DataApiSettings
    from yofina_ledger.events import EventPublisher
    from yofina_ledger.forecast_client import ForecastClient
    from yofina_ledger.repo import LedgerRepo
    from yofina_ledger.service import LedgerService
    from yofina_ledger.settings import LedgerSettings

    sess = session()
    email = f"{account}@{EMAIL_DOMAIN}"
    idp = sess.client("cognito-idp")
    pool = ssm_param("auth/user-pool-id", sess=sess)
    attrs = idp.admin_get_user(UserPoolId=pool, Username=email)["UserAttributes"]
    sub = next(a["Value"] for a in attrs if a["Name"] == "sub")

    env = sess.client("lambda").get_function_configuration(FunctionName=args.ledger_function)[
        "Environment"
    ]["Variables"]
    cfg = Config(env=env)
    settings = LedgerSettings.from_config(cfg)
    print(
        f"ledger {args.ledger_function}: ngày neo {settings.demo_anchor_date}, múi giờ {settings.app_timezone}",
        file=sys.stderr,
    )

    if not args.skip_group:
        ops = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))["ops_accounts"]
        ensure_groups(
            sess, {account: persona}, mapping_prefix, {account: {"email": email}}, ops_accounts=ops
        )

    db = DataApi(
        DataApiSettings(
            ssm_param("db/cluster-arn", sess=sess),
            ssm_param("db/app-secret-arn", sess=sess),
            ssm_param("db/name", sess=sess),
        ),
        region=REGION,
    )
    forecast = (
        ForecastClient(
            env["YOFINA_FORECAST_FUNCTION_NAME"],
            region=REGION,
            sync_timeout_seconds=float(env.get("YOFINA_FORECAST_SYNC_TIMEOUT_SECONDS", "22")),
        )
        if args.forecast
        else None
    )
    svc = LedgerService(
        LedgerRepo(db),
        None,  # type: ignore[arg-type]  # đặt lại demo không dùng token xác nhận
        settings,
        events=EventPublisher(settings.event_bus_name, region=REGION),
        forecast=forecast,
    )
    out = svc.reset_demo(sub, persona, trace_id=uuid.uuid4().hex[:16])
    print(json.dumps(out, ensure_ascii=False))

    row = db.query(
        "SELECT * FROM app_get_data_coverage(CAST(:uid AS text), CAST(:now AS timestamptz), CAST(:tz AS text), "
        "CAST(:win AS integer))",
        {
            "uid": sub,
            "now": datetime.now(UTC),
            "tz": settings.app_timezone,
            "win": int(env.get("YOFINA_FORECAST_HISTORY_WINDOW_DAYS", "330")),
        },
        max_rows=1,
    )
    if row:
        print(f"độ phủ dữ liệu trong DB sau khi nạp: {ingest.coverage_ratio(row[0])}")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # console Windows mặc định cp1252
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "account", help="tài khoản demo trong data/personas/accounts.json (ví dụ giamkhao3)"
    )
    ap.add_argument("--persona", help="persona (mặc định: theo accounts.json)")
    ap.add_argument(
        "--apply", action="store_true", help="ghi thật (mặc định chỉ chạy thử, không gọi AWS)"
    )
    ap.add_argument("--dry-run", action="store_true", help="ép chạy thử (mặc định đã vậy)")
    ap.add_argument(
        "--forecast", action="store_true", help="--apply: tính dự báo đồng bộ sau khi nạp"
    )
    ap.add_argument("--skip-group", action="store_true", help="--apply: không đổi nhóm Cognito")
    ap.add_argument("--ledger-function", default=DEFAULT_LEDGER_FUNCTION)
    ap.add_argument(
        "--anchor", default=DEFAULT_ANCHOR, help="chỉ cho chạy thử; --apply đọc từ Lambda"
    )
    ap.add_argument("--tz", default=DEFAULT_TZ, help="chỉ cho chạy thử; --apply đọc từ Lambda")
    args = ap.parse_args()

    cfg = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
    mapping: dict[str, str] = cfg["demo_accounts"]
    if args.account not in mapping:
        raise SystemExit(f"không có trong accounts.json: {args.account}")
    persona = args.persona or mapping[args.account]
    if persona not in personas.available_personas():
        raise SystemExit(f"không có persona {persona!r} (có: {personas.available_personas()})")

    p = plan(
        persona,
        anchor=date.fromisoformat(args.anchor),
        now=datetime.now(UTC),
        tz=ZoneInfo(args.tz),
    )
    print_plan(args.account, persona, p)
    if args.dry_run or not args.apply:
        print("CHẠY THỬ: chưa ghi gì, chưa gọi AWS. Thêm --apply để ghi thật.")
        return 0
    return apply(args, args.account, persona, cfg["group_prefix"])


if __name__ == "__main__":
    sys.exit(main())
