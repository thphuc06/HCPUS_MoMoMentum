"""Pipeline dự báo trên môi trường THẬT (phase 2, luồng C): Lambda forecast, SQS, EventBridge, Step Functions, Aurora, Gateway.

Tiêu chí phase 2 của luồng này: 1 (cảnh 1 sau đặt lại), 2 (giao dịch 200.000 ₫ -> dự báo mới trong 60 giây), 3 (chạy tay
`yofina-nightly`), 5 (`khoa` ước lượng ban đầu), 6 (Trả sau thành mốc), 8 phần Gateway (tool `forecast___get_forecast` cùng số với
REST; phần chat qua Runtime ở test_forecast_chat.py), 9 (gửi trùng sự kiện), 10 (p95 `GET /overview`). Bảng `forecast_runs` đọc bằng
secret master CHỈ để đếm và dọn trong test (sản phẩm không bao giờ dùng master).
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from conftest import demo_balances, demo_wallet, flow, master_data_api
from measure_wallet import lambda_side

pytestmark = pytest.mark.usefixtures("fresh")

# số dư ví demo của minh sau đặt lại (issue #39: Chi hằng ngày cạnh các hũ tự thêm, Hóa đơn gộp vào Nghĩa vụ, Du lịch là hũ goal
# `muc_tieu`, thêm Đầu tư 0 ₫), suy từ bộ sinh persona qua cùng ánh xạ mã hũ của đặt lại; tổng là 7.730.000 ₫ của bảng số Figma cộng
# số dư hũ Chi hằng ngày
DEMO_BALANCES = demo_balances("minh")
# Trả sau của minh trên ví demo đến hạn ngày 3 (`DEMO_CREDIT_DUE_DAY`, trước lương 05/12) thay vì ngày 5 của spec
MINH_BNPL_DUE = f"2026-12-{demo_wallet('minh').credit_due_day:02d}"


def get(api, who, path, **kw):
    status, body = api(who, "GET", path, **kw)
    assert status == 200, (path, body)
    return body


def forecast(api, who, jar):
    return get(api, who, f"/forecasts/{jar}")


@pytest.fixture(scope="module")
def master(sess):
    return master_data_api(sess)


def runs_where(master, sub: str, where: str = "TRUE", **params):
    sql = (
        "SELECT id, trigger, computed_at, source_event_id, params->'pipeline'->>'mode' AS mode "
        f"FROM forecast_runs WHERE user_id = :uid AND {where} ORDER BY computed_at"
    )
    return master.query(sql, {"uid": sub, **params}, max_rows=200)


def wait_for(fn, timeout: float, step: float = 2.0, what: str = "điều kiện"):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = fn()
        if last:
            return last
        time.sleep(step)
    raise AssertionError(f"quá {timeout:.0f} giây mà chưa thấy {what} (lần cuối: {last!r})")


def settle(master, sub: str, quiet: float = 8.0, timeout: float = 60.0) -> int:
    """Chờ tới khi không còn lần chạy mới của người dùng trong `quiet` giây. Đặt lại demo phát `profile.updated` NGAY SAU lần tính
    đồng bộ, nên consumer chạy thêm một lần đầy đủ vài giây sau: chờ nó xong trước khi đo."""
    end, last, since = time.time() + timeout, -1, time.time()
    while time.time() < end:
        n = len(runs_where(master, sub))
        if n != last:
            last, since = n, time.time()
        elif time.time() - since >= quiet:
            return n
        time.sleep(2)
    return last


# --- tiêu chí 1: cảnh 1 ---------------------------------------------------------------------------------------
def test_sau_dat_lai_minh_hu_an_uong_can_23_11_con_12_ngay_toi_ky_luong(api):
    body = api("minh", "POST", "/demo/reset", timeout=60)[1]
    assert body["forecast_ready"] is True and body["app_date"] == "2026-11-21"
    ov = get(api, "minh", "/overview")
    assert {j["code"]: j["balance_vnd"] for j in ov["jars"]} == DEMO_BALANCES
    assert ov["forecast"] is not None and ov["forecast"]["stale"] is False
    block = forecast(api, "minh", "an_uong")
    d = block["data"]
    assert d["status"] == "short" and d["runout_date"] == "2026-11-23"
    assert (
        d["payday"] == {"date": "2026-12-05", "days_until": 14} and d["origin_date"] == "2026-11-21"
    )
    assert d["start_balance_vnd"] == 380_000 and d["horizon_days"] == 30 and len(d["days"]) == 30
    assert "23/11" in block["fallback_text"] and "12 ngày" in block["fallback_text"]
    an = next(j for j in ov["jars"] if j["code"] == "an_uong")
    assert an["status"] == "short" and an["runout_date"] == "2026-11-23"
    assert an["forecast_floor_vnd"] < 0  # vạch "mực dự báo" của thẻ hũ
    card = ov["proactive_card"]
    assert card["data"]["kind"] == "runout_warning" and "23/11" in card["fallback_text"]
    assert card["data"].get("jar_code") in (
        None,
        "an_uong",
    )  # thẻ của Tổng quan vẫn là Ăn uống, không phải Chi hằng ngày
    # các hũ khác: không hũ nào báo hụt; Nghĩa vụ (gộp Hóa đơn) sát vì tiền điện 26/11 và Trả sau 03/12 (rollout Bước 5: khả năng hụt
    # 0,26); hũ goal Du lịch và Đầu tư 0 ₫ (không gì rút tiền) đủ; Chi hằng ngày (chi lặt vặt, khối `demo_jars`) đủ tới lương
    status = {j["code"]: j["status"] for j in ov["jars"]}
    assert (
        status["nghia_vu"] in ("tight", "ok")
        and status["muc_tieu"] == "ok"
        and status["dau_tu"] == "ok"
        and status["di_lai"] == "ok"
        and status["chi_hang_ngay"] == "ok"
    )


def test_ket_qua_dat_lai_on_dinh_qua_nhieu_lan(api):
    seen = []
    for _ in range(2):
        assert api("minh", "POST", "/demo/reset", timeout=60)[1]["forecast_ready"] is True
        d = forecast(api, "minh", "an_uong")["data"]
        seen.append(
            (d["runout_date"], d["status"], d["p_shortfall"], [x["p50_vnd"] for x in d["days"][:5]])
        )
    assert seen[0] == seen[1]


def test_khoa_uoc_luong_ban_dau_khong_co_xac_suat(api):
    body = api("khoa", "POST", "/demo/reset", timeout=60)[1]
    assert body["forecast_ready"] is True
    for jar in ("an_uong", "nghia_vu"):  # ví demo: Hóa đơn của khoa gộp vào Nghĩa vụ
        d = forecast(api, "khoa", jar)["data"]
        assert d["is_initial_estimate"] is True and d["confidence_band"] == "low"
        assert (
            d["history_days"] == 18 and "p_shortfall" not in d and d["model"] == "cold_start_rules"
        )
    ov = get(api, "khoa", "/overview")
    assert (
        ov["forecast"]["is_initial_estimate"] is True and ov["forecast"]["confidence_band"] == "low"
    )


# --- tiêu chí 2: giao dịch -> dự báo mới trong 60 giây -------------------------------------------------------------
def test_giao_dich_200k_cap_nhat_du_bao_hu_an_uong_trong_60_giay(api, subs, master):
    api("minh", "POST", "/demo/reset", timeout=60)
    settle(master, subs["minh"])
    before = forecast(api, "minh", "an_uong")
    di_lai_before = forecast(api, "minh", "di_lai")["data"]["computed_at"]
    t0 = time.time()
    status, receipt = flow(
        api, "minh", "record_transaction",
        {"kind": "expense", "amount_vnd": 200_000, "jar": "an_uong", "tx_type": "food_drink", "counterparty": "Cơm tấm Cô Ba"},
    )  # fmt: skip
    assert status == 200, receipt
    assert {j["code"]: j["balance_vnd"] for j in get(api, "minh", "/jars")["jars"]}[
        "an_uong"
    ] == 180_000  # số dư đổi ngay

    def updated():
        blk = forecast(api, "minh", "an_uong")
        if (
            blk["data"]["computed_at"] > before["data"]["computed_at"]
            and blk["data"]["start_balance_vnd"] == 180_000
        ):
            return blk
        return None

    after = wait_for(updated, 60, what="dự báo mới của hũ Ăn uống")
    lag = time.time() - t0
    print(f"độ trễ giao dịch -> dự báo mới: {lag:.1f} giây")
    assert lag <= 60
    assert (
        after["data"]["days"][0]["p50_vnd"] < 180_000
        and after["data"]["runout_date"] <= "2026-11-23"
    )
    assert after["data"]["stale"] is False
    # các hũ khác không bị tính lại (chỉnh nhanh chỉ chạm hũ liên quan)
    assert forecast(api, "minh", "di_lai")["data"]["computed_at"] == di_lai_before


# --- tiêu chí 9: gửi trùng một sự kiện ---------------------------------------------------------------------------
def test_gui_trung_su_kien_cung_event_id_khong_tinh_hai_lan(api, sess, subs, master):
    sub = subs["minh"]
    api("minh", "POST", "/demo/reset", timeout=60)
    settle(master, sub)
    status, receipt = flow(
        api, "minh", "record_transaction",
        {"kind": "expense", "amount_vnd": 25_000, "jar": "di_lai", "tx_type": "public_transport", "counterparty": "Xe buýt"},
    )  # fmt: skip
    assert status == 200, receipt
    event_id = receipt["data"]["reference_id"]  # transaction.recorded.event_id = id dòng sổ cái
    first = wait_for(
        lambda: runs_where(master, sub, "source_event_id = :e", e=event_id),
        60,
        what="lần chạy của sự kiện",
    )
    assert len(first) == 1 and first[0]["trigger"] == "event" and first[0]["mode"] == "fast"
    detail = {
        "v": 1, "event_id": event_id, "user_id": sub, "transaction_id": event_id,
        "occurred_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "app_date": "2026-11-21",
        "kind": "expense", "tx_type": "public_transport", "funding_source": "jar", "amount_vnd": 25_000,
        "jar_codes": ["di_lai"], "effects": [{"jar_code": "di_lai", "delta_vnd": -25_000, "balance_after_vnd": 615_000}],
    }  # fmt: skip
    events = sess.client("events")
    bus = sess.client("ssm").get_parameter(Name="/yofina/events/bus-name")["Parameter"]["Value"]
    for _ in range(2):  # gửi trùng hai lần nữa cùng event_id
        r = events.put_events(Entries=[{
            "EventBusName": bus, "Source": "yofina.ledger", "DetailType": "transaction.recorded",
            "Detail": json.dumps(detail),
        }])  # fmt: skip
        assert r["FailedEntryCount"] == 0
    time.sleep(25)  # đủ để SQS giao và consumer xử lý (hoặc bỏ qua vì trùng)
    again = runs_where(master, sub, "source_event_id = :e", e=event_id)
    assert len(again) == 1, "cùng event_id mà tính nhiều lần"
    table = sess.client("ssm").get_parameter(Name="/yofina/forecast/idempotency-table")[
        "Parameter"
    ]["Value"]
    item = sess.client("dynamodb").get_item(TableName=table, Key={"event_id": {"S": event_id}})[
        "Item"
    ]
    assert item["status"]["S"] == "done" and "ttl" in item


# --- tiêu chí 6: mua Trả sau thành mốc trên biểu đồ ------------------------------------------------------------------
def test_mua_tra_sau_300k_hien_thanh_moc_va_dong_du_bao_hu_nghia_vu(api, subs, master):
    api("minh", "POST", "/demo/reset", timeout=60)
    settle(master, subs["minh"])

    def mark(blk):
        return next(
            e
            for e in blk["data"]["events"]
            if e["kind"] == "obligation" and e["date"] == MINH_BNPL_DUE
        )

    before = forecast(api, "minh", "nghia_vu")
    assert mark(before)["amount_vnd"] == 1_000_000
    p50_before = next(d["p50_vnd"] for d in before["data"]["days"] if d["date"] == MINH_BNPL_DUE)
    status, receipt = flow(
        api, "minh", "record_transaction",
        {"kind": "expense", "amount_vnd": 300_000, "jar": "giai_tri", "tx_type": "entertainment", "funding": "credit", "counterparty": "Tiki"},
    )  # fmt: skip
    assert status == 200, receipt
    blk = forecast(api, "minh", "nghia_vu")
    assert (
        mark(blk)["amount_vnd"] == 1_300_000
    )  # mua thêm cộng dồn vào nghĩa vụ Trả sau của kỳ (phí tính một lần)

    def recomputed():
        b = forecast(api, "minh", "nghia_vu")
        return b if b["data"]["computed_at"] > before["data"]["computed_at"] else None

    after = wait_for(recomputed, 60, what="dự báo hũ Nghĩa vụ sau khi nghĩa vụ đổi")
    p50_after = next(d["p50_vnd"] for d in after["data"]["days"] if d["date"] == MINH_BNPL_DUE)
    assert p50_before - p50_after == pytest.approx(
        300_000, abs=1
    )  # cùng dãy ngẫu nhiên: lệch đúng bằng khoản thêm


def test_tai_khoan_lan_mua_tra_sau_sinh_nghia_vu_333k_han_ngay_5(api):
    api("lan", "POST", "/demo/reset", timeout=60)
    status, receipt = flow(
        api, "lan", "record_transaction",
        {"kind": "expense", "amount_vnd": 300_000, "jar": "giai_tri", "tx_type": "entertainment", "funding": "credit", "counterparty": "Tiki"},
    )  # fmt: skip
    assert status == 200, receipt
    obs = get(api, "lan", "/obligations")["obligations"]
    [bnpl] = [o for o in obs if o["kind"] == "bnpl"]
    assert bnpl["amount_vnd"] == 333_000 and bnpl["due_date"] == "2026-12-05"


# --- độ tươi: Tổng quan kích hoạt nền, Chi tiết hũ tính lại đồng bộ ---------------------------------------------------
def age_runs(master, sub: str, seconds: int) -> None:
    """Làm cũ mọi lần chạy của người dùng (chỉ trong test, bằng secret master): lùi `computed_at` `seconds` giây."""
    with master.transaction(sub) as tx:
        tx.execute(
            "UPDATE forecast_runs SET computed_at = computed_at - make_interval(secs => :s) WHERE user_id = :u",
            {"s": seconds, "u": sub},
        )


def test_tong_quan_khi_du_bao_cu_tra_stale_va_kich_hoat_tinh_lai_nen(api, subs, master):
    sub = subs["lan"]
    api("lan", "POST", "/demo/reset", timeout=60)
    settle(master, sub)
    age_runs(master, sub, 7200)  # quá độ tươi 3.600 giây
    t = time.time()
    ov = get(api, "lan", "/overview")
    assert ov["forecast"]["stale"] is True  # lần này trả bản cũ ngay, không chờ
    print(f"GET /overview khi dự báo cũ: {(time.time() - t) * 1000:.0f} ms")
    wait_for(
        lambda: runs_where(master, sub, "trigger = 'read'"),
        60,
        what="lần tính nền do Tổng quan kích hoạt",
    )
    assert get(api, "lan", "/overview")["forecast"]["stale"] is False  # lần đọc sau thấy số mới


def test_chi_tiet_hu_khi_du_bao_cu_tinh_lai_dong_bo_roi_tra(api, subs, master):
    sub = subs["lan"]
    api("lan", "POST", "/demo/reset", timeout=60)
    settle(master, sub)
    old = forecast(api, "lan", "an_uong")["data"]["computed_at"]
    age_runs(master, sub, 7200)
    blk = forecast(api, "lan", "an_uong")  # tính lại đồng bộ rồi trả
    assert blk["data"]["stale"] is False and blk["data"]["computed_at"] > old
    assert runs_where(master, sub, "trigger = 'read'")


# --- tiêu chí 3: chạy tay yofina-nightly ------------------------------------------------------------------------------
def test_nightly_chay_tay_thanh_cong_cho_ca_sau_tai_khoan(sess, subs, master):
    sfn, ssm = sess.client("stepfunctions"), sess.client("ssm")
    arn = ssm.get_parameter(Name="/yofina/forecast/nightly-arn")["Parameter"]["Value"]
    started = datetime.now(UTC)
    ex = sfn.start_execution(stateMachineArn=arn, name=f"test-{uuid.uuid4().hex[:12]}")[
        "executionArn"
    ]

    def done():
        d = sfn.describe_execution(executionArn=ex)
        return d if d["status"] != "RUNNING" else None

    d = wait_for(done, 180, step=3, what="execution kết thúc")
    assert d["status"] == "SUCCEEDED", d.get("cause") or d.get("error")
    out = json.loads(d["output"])
    assert out["failed"] == 0 and out["total"] >= 6 and out["ok"] >= 6, out
    for who in ("minh", "lan", "khoa"):
        fresh_runs = runs_where(
            master,
            subs[who],
            "trigger = 'nightly' AND computed_at >= CAST(:t AS timestamptz)",
            t=(
                started - timedelta(seconds=120)
            ).isoformat(),  # đồng hồ máy chạy test lệch vài giây so với AWS
        )
        assert fresh_runs, f"{who}: không có bản ghi forecast_runs mới của batch đêm"
    print(f"yofina-nightly: {out}, {(d['stopDate'] - d['startDate']).total_seconds():.1f} giây")


def test_lich_dem_02_00_gio_viet_nam_va_alarm_da_dung(sess):
    sch = sess.client("scheduler").get_schedule(Name="yofina-nightly-0200")
    assert sch["ScheduleExpression"] == "cron(0 2 * * ? *)"
    assert sch["ScheduleExpressionTimezone"] == "Asia/Ho_Chi_Minh" and sch["State"] == "ENABLED"
    cw = sess.client("cloudwatch")
    names = {a["AlarmName"] for a in cw.describe_alarms(AlarmNamePrefix="yofina-")["MetricAlarms"]}
    assert {
        "yofina-nightly-failed",
        "yofina-nightly-timed-out",
        "yofina-forecast-events-dlq-not-empty",
    } <= names


def test_hang_doi_su_kien_co_dlq_va_trong(sess):
    sqs, ssm = sess.client("sqs"), sess.client("ssm")
    url = ssm.get_parameter(Name="/yofina/forecast/events-queue-url")["Parameter"]["Value"]
    attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["All"])["Attributes"]
    policy = json.loads(attrs["RedrivePolicy"])
    assert (
        policy["maxReceiveCount"] >= 2
        and "yofina-forecast-events-dlq" in policy["deadLetterTargetArn"]
    )
    dlq = sqs.get_queue_url(QueueName="yofina-forecast-events-dlq")["QueueUrl"]
    assert (
        int(
            sqs.get_queue_attributes(QueueUrl=dlq, AttributeNames=["ApproximateNumberOfMessages"])[
                "Attributes"
            ]["ApproximateNumberOfMessages"]
        )
        == 0
    )


# --- Gateway: tool forecast___get_forecast cùng số với REST -------------------------------------------------------
def test_tool_forecast_qua_gateway_cung_so_voi_rest_va_khop_hop_dong(
    gw, api, schema_validator, subs, master
):
    api("minh", "POST", "/demo/reset", timeout=60)
    settle(master, subs["minh"])
    names = gw("minh").tool_names()
    assert "forecast___get_forecast" in names and "ledger___get_jar_balances" in names
    reply = gw("minh").call("forecast___get_forecast", {"jar": "an_uong"})
    assert reply.status == "OK", reply.text
    schema_validator(
        "https://contracts.yofina.invalid/tools/forecast.results.schema.json#/$defs/GetForecastResult",
        reply.data,
    )
    rest = forecast(api, "minh", "an_uong")
    assert reply.data["data"] == rest["data"], "tool và REST phải trả cùng một dự báo"
    # hũ không có, hũ hệ thống và tham số thiếu
    bad = gw("minh").call("forecast___get_forecast", {"jar": "khong_co"})
    assert bad.status == "ERROR" and bad.data["code"] == "JAR_NOT_FOUND"
    sysjar = gw("minh").call("forecast___get_forecast", {"jar": "tien_vao_khac"})
    assert sysjar.status == "ERROR" and sysjar.data["code"] == "FORECAST_NOT_APPLICABLE"


def test_tool_forecast_user_id_la_cua_chinh_nguoi_goi_khong_doc_duoc_cua_nguoi_khac(
    gw, subs, api, master
):
    # interceptor ghi đè user_id bằng sub của JWT: gửi user_id của người khác vẫn trả dự báo của CHÍNH người gọi
    api("lan", "POST", "/demo/reset", timeout=60)
    settle(master, subs["lan"])
    reply = gw("lan").call("forecast___get_forecast", {"jar": "an_uong", "user_id": subs["minh"]})
    assert reply.status == "OK"
    lan_rest = forecast(api, "lan", "an_uong")
    assert reply.data["data"] == lan_rest["data"]  # dữ liệu của lan, không phải của minh


def test_tool_forecast_tinh_lai_khi_chua_co_du_bao(gw, api, subs, master):
    # xóa dự báo của lan (bằng master, chỉ trong test) rồi gọi tool: tool tự tính rồi trả
    sub = subs["lan"]
    api("lan", "POST", "/demo/reset", timeout=60)
    settle(master, sub)  # đợi lần chạy đầy đủ do profile.updated của đặt lại xong, rồi mới xóa
    with master.transaction(sub) as tx:
        tx.execute("DELETE FROM forecast_runs WHERE user_id = :u", {"u": sub})
    reply = gw("lan").call("forecast___get_forecast", {"jar": "an_uong"})
    assert reply.status == "OK" and reply.data["data"]["stale"] is False
    assert runs_where(master, sub, "trigger = 'read'")


# --- tiêu chí 10: GET /overview sau khi có dự báo -----------------------------------------------------------------
def test_overview_p95_phia_lambda_duoi_300ms(api, sess):
    api("minh", "POST", "/demo/reset", timeout=60)
    start_ms = int(time.time() * 1000)
    client_ms = []
    for _ in range(40):
        t = time.time()
        status, body = api("minh", "GET", "/overview")
        client_ms.append((time.time() - t) * 1000)
        assert status == 200 and body["forecast"] is not None
    time.sleep(45)  # log Lambda cần một lúc để tới CloudWatch
    lam = lambda_side(sess, start_ms, int(time.time() * 1000)).get("GET /overview", [])
    assert len(lam) >= 20, f"chỉ thấy {len(lam)} dòng log"
    lam.sort()
    p50, p95 = lam[len(lam) // 2], lam[int(len(lam) * 0.95) - 1]
    cs = sorted(client_ms)
    print(f"GET /overview phía Lambda: p50 {p50:.0f} ms, p95 {p95:.0f} ms (n={len(lam)}); phía máy gọi: p50 {cs[len(cs)//2]:.0f} ms, p95 {cs[int(len(cs)*0.95)-1]:.0f} ms")  # fmt: skip
    assert p95 < 300
