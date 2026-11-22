"""F6 nạp dữ liệu (phase 5, luồng A) trên môi trường THẬT: REST `/ingest/*` -> S3 presigned POST -> SQS -> worker -> Aurora/Bedrock.

Một luồng có thứ tự trên tài khoản demo `giamkhao3` (persona `vy`, có thu nhập ngoài ví), mỗi bước là một test, chia sẻ trạng thái
qua fixture `vy` (module). Mọi khẳng định dựa trên phản hồi thật của API đã deploy; thân phản hồi kiểm bằng `schema_validator`
với schema OpenAPI/khối của hợp đồng. Không khẳng định số dòng chính xác do mô hình sinh, chỉ khoảng và bất biến.

Điều kiện: stack ingest đã deploy, ledger đã có `RESET_DELETES` mới (đặt lại xóa `ingest_*` và `consents`), `giamkhao3` đã vào nhóm
`persona-vy` và đã nạp dữ liệu `vy` (xem `data/personas/README.md`).

Các bước CHẬM (gọi Aurora đang thức dậy, S3 -> SQS -> Lambda, Bedrock): `test_04` (tới 240 giây), `test_09` (tới 120 giây),
`test_10` (tới 180 giây). Tổng thường dưới 6 phút. Test cuối đặt lại tài khoản; fixture `vy` cũng đặt lại khi kết thúc nếu test
cuối không chạy tới (không để lại rác trên tài khoản dùng chung).

Thứ tự chạy khác thứ tự liệt kê trong yêu cầu ở MỘT chỗ: thử dùng lại token (`test_08`) chạy ngay sau khi chốt, trước các bước chậm,
vì token xác nhận sống ngắn (vài phút); để sau thì lỗi sẽ là `TOKEN_EXPIRED` chứ không phải `TOKEN_REUSED`.
"""

from __future__ import annotations

import re
import time
from collections import Counter
from typing import Any

import httpx
import pytest
from conftest import REPO, call_api, login_access_token

WHO = "giamkhao3"
CSV_PATH = REPO / "data" / "personas" / "samples" / "vy_sao_ke_vcb.csv"
CAT_PATH = REPO / "evals" / "ingest" / "synthetic" / "img" / "s25_cat.png"
RECEIPT_SCHEMA = "https://contracts.yofina.invalid/blocks/receipt_action.schema.json"
SYSTEM_JARS = {"tien_vao_khac", "chua_phan_loai"}
OPEN_STATUSES = ("auto_added", "pending")
TERMINAL = ("review", "done", "failed", "rejected")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")


# --- tiện ích -----------------------------------------------------------------------------------------------------------
class Vy:
    """Gọi REST bằng token của `giamkhao3` và giữ trạng thái giữa các bước."""

    def __init__(self, base: str, token: str) -> None:
        self.base, self.token = base, token
        self.state: dict[str, Any] = {}

    def call(self, method: str, path: str, body=None, *, timeout: float = 60.0):
        status, resp, _ms = call_api(self.base, method, path, self.token, body, timeout=timeout)
        return status, resp

    def get(self, path: str, **kw):
        status, body = self.call("GET", path, **kw)
        assert status == 200, (path, status, body)
        return body

    def reset(self) -> dict:
        status, body = self.call("POST", "/demo/reset", timeout=120)  # Aurora có thể đang thức dậy
        assert status == 200, body
        return body


@pytest.fixture(scope="module")
def vy(base, sess, accounts):
    assert WHO in accounts, f"tài khoản demo {WHO} chưa có trong secret yofina-demo-accounts"
    who = Vy(base, login_access_token(WHO, sess=sess, accounts=accounts))
    yield who
    if not who.state.get("cleaned"):
        who.reset()


def code(body) -> str:
    return body["error"]["code"]


def vnd_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def request_upload(vy: Vy, kind: str, mime: str, data: bytes, *, consent: bool | None):
    body: dict[str, Any] = {"source_kind": kind, "mime": mime, "size_bytes": len(data)}
    if consent is not None:
        body["consent"] = consent
    return vy.call("POST", "/ingest/uploads", body)


def put_to_s3(up: dict, data: bytes, mime: str) -> None:
    """Tải thẳng lên S3 bằng presigned POST: trường form theo đúng thứ tự cấp, trường `file` đặt CUỐI (httpx gửi `data` trước `files`)."""
    r = httpx.post(
        up["url"], data=up["fields"], files={"file": ("upload", data, mime)}, timeout=60.0
    )
    assert r.status_code in (200, 201, 204), (r.status_code, r.text[:500])


def poll_job(vy: Vy, job_id: str, *, until=TERMINAL, timeout: float) -> dict:
    """GET /ingest/jobs/{id} với backoff (2 -> 8 giây) tới khi `status` thuộc `until`. Lỗi tạm thời của Aurora đang thức (502/503/504) thì thử lại."""
    end = time.monotonic() + timeout
    delay, last = 2.0, None
    while time.monotonic() < end:
        status, body = vy.call("GET", f"/ingest/jobs/{job_id}")
        if status in (502, 503, 504):
            last = (status, body)
        else:
            assert status == 200, (status, body)
            last = (status, body["status"], body["progress"])
            if body["status"] in until:
                return body
        time.sleep(delay)
        delay = min(delay * 1.4, 8.0)
    pytest.fail(f"job {job_id} chưa tới {until} sau {timeout:.0f} giây; lần đọc cuối: {last}")


def open_expense_rows(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["kind"] == "expense" and r["review_status"] in OPEN_STATUSES]


def all_transactions(vy: Vy, schema_validator) -> list[dict]:
    out: list[dict] = []
    path = "/transactions?limit=50"
    for _ in range(20):
        page = vy.get(path)
        schema_validator.openapi("TransactionsResponse", page)
        out += page["transactions"]
        if not page.get("next_cursor"):
            return out
        path = f"/transactions?limit=50&cursor={page['next_cursor']}"
    pytest.fail("phân trang giao dịch không dừng sau 20 trang")


def need(vy: Vy, *keys: str) -> None:
    missing = [k for k in keys if k not in vy.state]
    if missing:
        pytest.skip(f"phụ thuộc bước trước chưa chạy xong: thiếu {missing}")


# --- 1. đặt lại, ghi số dư hũ ban đầu -------------------------------------------------------------------------------------
def test_01_dat_lai_sach_va_ghi_so_du_hu_ban_dau(vy, schema_validator):
    vy.reset()
    ov = vy.get("/overview")
    schema_validator.openapi("OverviewResponse", ov)
    assert ov["profile"]["onboarded"] is True and ov["jars"]
    vy.state["overview0"] = ov
    vy.state["balances0"] = {j["code"]: j["balance_vnd"] for j in ov["jars"]}
    assert all(vnd_int(v) for v in vy.state["balances0"].values())
    # persona vy có sẵn dòng thu nhập ngoài ví (funding external) từ bộ sinh: ghi lại làm mốc
    base_ext = [
        t for t in all_transactions(vy, schema_validator) if t.get("funding_source") == "external"
    ]
    assert base_ext and all(t["kind"] == "income" for t in base_ext)
    vy.state["base_external_ids"] = {t["id"] for t in base_ext}
    # đặt lại đã xóa job nạp cũ (và đồng ý, kiểm ở test sau)
    jobs = vy.get("/ingest/jobs")
    schema_validator.openapi("IngestJobListResponse", jobs)
    assert jobs["jobs"] == []


# --- 2. đồng ý, xin URL, tải CSV lên S3 -----------------------------------------------------------------------------------
def test_02_csv_lan_dau_khong_dong_y_thi_403_va_khong_tao_job(vy):
    need(vy, "balances0")
    data = CSV_PATH.read_bytes()
    status, body = request_upload(vy, "csv", "text/csv", data, consent=None)
    # sau đặt lại `consents` đã bị xóa (RESET_DELETES mới); 200 nghĩa là ledger đã deploy chưa xóa đồng ý
    assert (status, code(body)) == (403, "CONSENT_REQUIRED"), (status, body)
    status, body = request_upload(vy, "csv", "text/csv", data, consent=False)
    assert (status, code(body)) == (403, "CONSENT_REQUIRED")
    assert vy.get("/ingest/jobs")["jobs"] == []


def test_03_loai_tep_va_kich_thuoc_sai_bi_tu_choi_truoc_khi_tao_job(vy):
    need(vy, "balances0")
    status, body = vy.call(
        "POST",
        "/ingest/uploads",
        {"source_kind": "csv", "mime": "application/pdf", "size_bytes": 1000, "consent": True},
    )
    assert (status, code(body)) == (415, "INGEST_UNSUPPORTED_TYPE")
    status, body = vy.call(
        "POST",
        "/ingest/uploads",
        {"source_kind": "csv", "mime": "text/csv", "size_bytes": 50_000_000, "consent": True},
    )
    assert (status, code(body)) == (413, "INGEST_TOO_LARGE")
    status, body = vy.call(
        "POST", "/ingest/uploads", {"source_kind": "pdf", "mime": "text/csv", "size_bytes": 10}
    )
    assert (status, code(body)) == (400, "PARAMS_INVALID")
    assert vy.get("/ingest/jobs")["jobs"] == []


def test_04_csv_co_dong_y_cap_url_tai_len_s3_roi_job_toi_review(vy, schema_validator):
    """CHẬM: tới 240 giây (S3 -> SQS -> worker, Aurora thức dậy ~20 giây, Bedrock Nova gợi ý hũ)."""
    need(vy, "balances0")
    data = CSV_PATH.read_bytes()
    status, up = request_upload(vy, "csv", "text/csv", data, consent=True)
    assert status == 200, up
    schema_validator.openapi("IngestUploadResponse", up)
    assert up["key"].endswith(up["job_id"]) and up["url"].startswith("https://")
    assert up["fields"].get("key") == up["key"] and "policy" in up["fields"]
    assert up["max_bytes"] >= len(data) and "text/csv" in up["mime_types"]
    job_id = up["job_id"]
    vy.state["csv_job_id"] = job_id
    # job vừa tạo ở awaiting_upload (chưa có tệp)
    created = vy.get(f"/ingest/jobs/{job_id}")
    schema_validator.openapi("IngestJobResponse", created)
    assert created["status"] == "awaiting_upload" and created["source_kind"] == "csv"
    assert "review" not in created

    put_to_s3(up, data, "text/csv")

    job = poll_job(vy, job_id, timeout=240)  # --- CHẬM ---
    schema_validator.openapi("IngestJobResponse", job)
    assert job["status"] == "review", job
    assert "error_code" not in job and "coverage_change" not in job
    review = job["review"]
    assert review["type"] == "ingest_review" and review["id"] == f"ingest_review:{job_id}"
    d = review["data"]
    assert d["job_id"] == job_id and d["status"] == "review" and d["source_kind"] == "csv"

    rows = d["rows"]
    # sao kê mẫu có 41 dòng (39 chi, 2 thu): khoảng rộng, không đòi đúng số
    assert 20 <= d["rows_total"] <= 41, d["rows_total"]
    assert job["rows_total"] == d["rows_total"] == len(rows)
    seqs = [r["seq"] for r in rows]
    assert seqs == sorted(set(seqs)), "seq phải tăng dần và không trùng"
    assert len({r["row_id"] for r in rows}) == len(rows)
    assert all(vnd_int(r["amount_vnd"]) and r["amount_vnd"] > 0 for r in rows)
    assert all(0 <= r["extract_confidence"] <= 1 for r in rows)
    tally = Counter(r["review_status"] for r in rows)
    counts = d["counts"]
    assert {k: counts[k] for k in tally} == dict(tally)
    assert sum(counts.values()) == d["rows_total"]
    assert counts["approved"] == counts["rejected"] == 0
    # hũ để đổi một chạm: hũ người dùng, không có hũ hệ thống, nằm trong hũ của tài khoản
    jar_codes = [j["code"] for j in d["jars"]]
    assert jar_codes and not SYSTEM_JARS & set(jar_codes)
    assert set(jar_codes) <= set(vy.state["balances0"])
    for r in rows:
        if r["kind"] == "expense" and "suggested_jar" in r:
            assert r["suggested_jar"]["code"] in jar_codes
            assert r.get("jar_source") in ("type_map", "rule", "model", "user")
            assert 0 <= r.get("jar_confidence", 0) <= 1
        if r["kind"] == "income":
            assert "suggested_jar" not in r  # dòng thu không có hũ
        if r["review_status"] == "duplicate":
            assert r["duplicate_of"]
    assert open_expense_rows(rows), "phải còn ít nhất một dòng chi để duyệt"

    listed = vy.get("/ingest/jobs")
    schema_validator.openapi("IngestJobListResponse", listed)
    (mine,) = [j for j in listed["jobs"] if j["job_id"] == job_id]
    assert mine["status"] == "review" and mine["rows_total"] == d["rows_total"]
    vy.state["review"] = d


# --- 4. đổi hũ đề xuất một chạm ---------------------------------------------------------------------------------------------
def test_05_doi_hu_de_xuat_cua_mot_dong_chi(vy, schema_validator):
    need(vy, "review")
    job_id, d = vy.state["csv_job_id"], vy.state["review"]
    cands = open_expense_rows(d["rows"])
    row = next((r for r in cands if r["review_status"] == "pending"), cands[0])
    current = row.get("suggested_jar", {}).get("code")
    target = next(c for c in (j["code"] for j in d["jars"]) if c != current)

    status, out = vy.call("POST", f"/ingest/rows/{row['row_id']}/jar", {"jar": target})
    assert status == 200, out
    schema_validator.openapi("IngestRowJarResponse", out)
    assert out["row_id"] == row["row_id"] and out["jar_source"] == "user"
    assert out["suggested_jar"]["code"] == target
    # lỗi: hũ không có -> JAR_NOT_FOUND, không đổi gì
    status, err = vy.call("POST", f"/ingest/rows/{row['row_id']}/jar", {"jar": "khong_co_hu"})
    assert (status, code(err)) == (404, "JAR_NOT_FOUND")
    assert vy.call("POST", f"/ingest/rows/{row['row_id']}/jar", {"jar": "Sai Ma"})[0] == 400

    after = vy.get(f"/ingest/jobs/{job_id}")
    schema_validator.openapi("IngestJobResponse", after)
    again = {r["row_id"]: r for r in after["review"]["data"]["rows"]}[row["row_id"]]
    assert again["suggested_jar"]["code"] == target and again["jar_source"] == "user"
    assert again["review_status"] == row["review_status"]  # chỉ đổi đề xuất, không đổi trạng thái
    # chưa ghi sổ cái: số dư hũ vẫn như ban đầu
    assert {j["code"]: j["balance_vnd"] for j in vy.get("/overview")["jars"]} == vy.state[
        "balances0"
    ]
    vy.state["review"] = after["review"]["data"]


# --- 5. chốt các dòng: token rồi biên nhận ---------------------------------------------------------------------------------
def test_06_xac_nhan_roi_chot_dong_ghi_external_va_do_phu_tang(vy, schema_validator):
    need(vy, "review")
    job_id, d = vy.state["csv_job_id"], vy.state["review"]
    first_jar = d["jars"][0]["code"]
    selected = [r for r in d["rows"] if r["review_status"] in OPEN_STATUSES]  # đúng lựa chọn UI gửi
    assert selected
    params_rows: list[dict] = []
    effective: list[dict] = []  # (loại, tiền, hũ) của từng dòng sẽ ghi
    for r in selected:
        item: dict[str, Any] = {"row_id": r["row_id"]}
        jar = None
        if r["kind"] == "expense":
            jar = r.get("suggested_jar", {}).get("code")
            if jar is None:  # dòng chi chưa có hũ thì người dùng phải chọn (UI bắt buộc)
                jar = item["jar"] = first_jar
        params_rows.append(item)
        effective.append({"kind": r["kind"], "amount": r["amount_vnd"], "jar": jar})
    params = {"job_id": job_id, "rows": params_rows}
    spend = sum(e["amount"] for e in effective if e["kind"] == "expense")
    income = sum(e["amount"] for e in effective if e["kind"] == "income")

    # không có token thì không ghi gì
    status, body = vy.call("POST", "/ingest/actions", {"tool": "confirm_rows", "params": params})
    assert (status, code(body)) == (428, "NEEDS_CONFIRMATION")
    # tool khác không đi qua /ingest/*
    status, body = vy.call(
        "POST",
        "/ingest/confirmations",
        {"tool": "record_transaction", "params": {"kind": "expense", "amount_vnd": 1000}},
    )
    assert status == 400, body

    status, conf = vy.call(
        "POST", "/ingest/confirmations", {"tool": "confirm_rows", "params": params}
    )
    assert status == 200, conf
    schema_validator.openapi("ConfirmationResponse", conf)
    assert conf["tool"] == "confirm_rows" and TOKEN_RE.match(conf["confirm_token"])
    assert conf["ttl_seconds"] > 0
    pv = conf["preview"]
    assert str(len(selected)) in pv["summary"]
    changes = {c["label"]: c for c in pv["changes"]}
    assert changes["Số dư các hũ"]["after"] == "Không đổi"
    # xem trước không ghi: job vẫn review, số dư hũ không đổi
    assert vy.get(f"/ingest/jobs/{job_id}")["status"] == "review"
    assert {j["code"]: j["balance_vnd"] for j in vy.get("/overview")["jars"]} == vy.state[
        "balances0"
    ]

    status, receipt = vy.call(
        "POST",
        "/ingest/actions",
        {"tool": "confirm_rows", "params": conf["params"], "confirm_token": conf["confirm_token"]},
    )
    assert status == 200, receipt
    schema_validator(RECEIPT_SCHEMA, receipt)
    assert receipt["type"] == "receipt_action"
    rd = receipt["data"]
    assert rd["tool"] == "confirm_rows" and rd["jars_after"] == []
    assert rd["reference_id"] == job_id
    if spend:
        assert rd["amount_vnd"] == spend
    cc = rd["coverage_change"]
    assert cc["type"] == "coverage_change" and cc["id"] == f"coverage_change:{job_id}"
    cd = cc["data"]
    assert cd["job_id"] == job_id and cd["rows_added"] == len(selected)
    assert cd["external_spend_added_vnd"] == spend
    assert cd.get("external_income_added_vnd", 0) == income
    assert {j["code"] for j in cd["jars_affected"]} == {
        e["jar"] for e in effective if e["kind"] == "expense"
    }
    before, after = cd["before"], cd["after"]
    assert 0 <= before <= 1 and 0 <= after <= 1, (before, after)
    assert after > before, (before, after)

    done = vy.get(f"/ingest/jobs/{job_id}")
    schema_validator.openapi("IngestJobResponse", done)
    assert done["status"] == "done" and "coverage_change" in done
    assert done["review"]["data"]["counts"]["approved"] == len(selected)
    assert done["coverage_change"]["data"]["rows_added"] == len(selected)
    vy.state.update(conf=conf, params=params, effective=effective, spend=spend, income=income)


# --- 6. số dư hũ không đổi, giao dịch external có trong lịch sử --------------------------------------------------------------
def test_07_so_du_hu_khong_doi_va_lich_su_co_dong_external(vy, schema_validator):
    need(vy, "effective")
    ov = vy.get("/overview")
    schema_validator.openapi("OverviewResponse", ov)
    assert {j["code"]: j["balance_vnd"] for j in ov["jars"]} == vy.state["balances0"]
    assert ov["balance"] == vy.state["overview0"]["balance"]
    # giao dịch gần đây của Tổng quan là của VÍ: không có dòng external
    assert all(t.get("funding_source") != "external" for t in ov["recent_transactions"])

    txs = all_transactions(vy, schema_validator)
    base_ids = vy.state["base_external_ids"]
    external = [
        t for t in txs if t.get("funding_source") == "external" and t["id"] not in base_ids
    ]
    eff = vy.state["effective"]
    assert len(external) == len(eff)
    ext_exp = [t for t in external if t["kind"] == "expense"]
    ext_inc = [t for t in external if t["kind"] == "income"]
    assert sum(abs(t["amount_vnd"]) for t in ext_exp) == vy.state["spend"]
    assert sum(abs(t["amount_vnd"]) for t in ext_inc) == vy.state["income"]
    # mỗi dòng chi ghi đúng vào hũ đã chọn (kể cả dòng đã đổi hũ ở test_05)
    assert Counter(t["jar"] for t in ext_exp) == Counter(
        e["jar"] for e in eff if e["kind"] == "expense"
    )
    # tổng số dòng external (gồm mốc của persona) để các bước sau kiểm không ghi thêm
    vy.state["external_count"] = len(external) + len(base_ids)


# --- 9 (đưa lên sớm). dùng lại token ----------------------------------------------------------------------------------------
def test_08_dung_lai_token_da_dung_bi_tu_choi_va_khong_ghi_them(vy, schema_validator):
    need(vy, "conf", "external_count")
    conf, job_id = vy.state["conf"], vy.state["csv_job_id"]
    status, body = vy.call(
        "POST",
        "/ingest/actions",
        {"tool": "confirm_rows", "params": conf["params"], "confirm_token": conf["confirm_token"]},
    )
    assert (status, code(body)) == (409, "TOKEN_REUSED"), body
    # chốt lại không token trên job đã done cũng không ghi: lần xem trước bị từ chối vì đã chốt
    status, body = vy.call(
        "POST", "/ingest/confirmations", {"tool": "confirm_rows", "params": vy.state["params"]}
    )
    assert (status, code(body)) == (409, "ALREADY_APPLIED")
    external = [
        t for t in all_transactions(vy, schema_validator) if t.get("funding_source") == "external"
    ]
    assert len(external) == vy.state["external_count"]
    assert vy.get(f"/ingest/jobs/{job_id}")["status"] == "done"


# --- 7. nạp lại đúng tệp ------------------------------------------------------------------------------------------------------
def test_09_nap_lai_cung_tep_csv_bi_tu_choi_trung_noi_dung(vy, schema_validator):
    """CHẬM: tới 120 giây. API nhận yêu cầu bình thường (chưa biết nội dung); worker băm tệp rồi đặt job `rejected`."""
    need(vy, "external_count")
    data = CSV_PATH.read_bytes()
    # đồng ý đã lưu từ lần đầu nên không cần gửi lại `consent`
    status, up = request_upload(vy, "csv", "text/csv", data, consent=None)
    assert status == 200, up
    schema_validator.openapi("IngestUploadResponse", up)
    assert up["job_id"] != vy.state["csv_job_id"]
    put_to_s3(up, data, "text/csv")

    job = poll_job(vy, up["job_id"], timeout=120)  # --- CHẬM ---
    schema_validator.openapi("IngestJobResponse", job)
    assert job["status"] == "rejected", job
    assert job["error_code"] == "INGEST_DUPLICATE_FILE"
    assert 1 <= len(job["error_message"]) <= 280
    assert "review" not in job
    listed = vy.get("/ingest/jobs")["jobs"]
    mine = next(j for j in listed if j["job_id"] == up["job_id"])
    assert mine["status"] == "rejected" and mine["error_code"] == "INGEST_DUPLICATE_FILE"
    # lần nạp gốc không bị đụng tới
    assert vy.get(f"/ingest/jobs/{vy.state['csv_job_id']}")["status"] == "done"


# --- 8. ảnh không phải tài chính -------------------------------------------------------------------------------------------------
def test_10_anh_meo_bi_tu_choi_khong_phai_tai_chinh(vy, schema_validator):
    """CHẬM: tới 180 giây (Bedrock đọc ảnh). Đồng ý theo NGUỒN: đồng ý CSV không thay cho đồng ý ảnh."""
    need(vy, "external_count")
    data = CAT_PATH.read_bytes()
    status, body = request_upload(vy, "image", "image/png", data, consent=None)
    assert (status, code(body)) == (403, "CONSENT_REQUIRED"), (status, body)
    status, up = request_upload(vy, "image", "image/png", data, consent=True)
    assert status == 200, up
    schema_validator.openapi("IngestUploadResponse", up)
    assert "image/png" in up["mime_types"]
    put_to_s3(up, data, "image/png")

    job = poll_job(vy, up["job_id"], timeout=180)  # --- CHẬM ---
    schema_validator.openapi("IngestJobResponse", job)
    assert job["status"] == "rejected", job
    assert job["error_code"] == "INGEST_NOT_FINANCIAL"
    assert 1 <= len(job["error_message"]) <= 280
    assert "review" not in job and job["source_kind"] == "image"
    # ảnh bị từ chối không để lại dòng nào trong sổ cái
    external = [
        t for t in all_transactions(vy, schema_validator) if t.get("funding_source") == "external"
    ]
    assert len(external) == vy.state["external_count"]


# --- 10. dọn: đặt lại tài khoản ----------------------------------------------------------------------------------------------------
def test_11_dat_lai_lan_cuoi_de_tai_khoan_sach(vy, schema_validator):
    need(vy, "balances0")
    vy.reset()
    vy.state["cleaned"] = True
    assert vy.get("/ingest/jobs")["jobs"] == []
    ov = vy.get("/overview")
    assert {j["code"]: j["balance_vnd"] for j in ov["jars"]} == vy.state["balances0"]
    # chỉ còn các dòng thu nhập ngoài ví do bộ sinh persona tạo (id mới sau khi đặt lại)
    ext_after = [
        t for t in all_transactions(vy, schema_validator) if t.get("funding_source") == "external"
    ]
    assert len(ext_after) == len(vy.state["base_external_ids"])
    assert all(t["kind"] == "income" for t in ext_after)
    # đồng ý cũng bị xóa: đòi lại như lúc đầu
    status, body = request_upload(vy, "csv", "text/csv", CSV_PATH.read_bytes(), consent=None)
    assert (status, code(body)) == (403, "CONSENT_REQUIRED")
