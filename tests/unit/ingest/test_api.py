"""REST `/ingest/*` với repo giả: kiểm đầu vào, đồng ý, presigned POST, danh sách, đổi hũ, ánh xạ lỗi. Luồng ghi sổ cái thật nằm ở
tests/local_pg/test_ingest_flow.py (PostgreSQL thật)."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from ingest_helpers import PNG  # noqa: F401
from yofina_ingest.api import IngestApi, s3_presigner
from yofina_ingest.repo import UserContext
from yofina_ingest.rest import handle_http
from yofina_ingest.settings import IngestRuntime

from yofina_core.confirm import ConfirmService
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.ingest import IngestSettings
from yofina_core.llm import BudgetCapReached
from yofina_core.quota import UPLOAD, AccountQuota

NOW = datetime(2026, 12, 10, 3, 0, tzinfo=UTC)
USER = "sub-minh"
JARS = [
    {
        "code": "an_uong",
        "name": "Ăn uống",
        "color_key": "violet",
        "icon_key": "utensils",
        "kind": "spending",
    },
    {"code": "di_lai", "name": "Đi lại", "color_key": "sky", "icon_key": "bus", "kind": "spending"},
]


class MemJti:
    def __init__(self) -> None:
        self.used: set[str] = set()

    def consume(self, jti: str, exp: int) -> None:
        if jti in self.used:
            raise YofinaError(ErrorCode.TOKEN_REUSED, "dùng rồi")
        self.used.add(jti)


class FakeRepo:
    def __init__(self) -> None:
        self.consent_rows: dict[str, dict[str, Any]] = {}
        self.created: list[tuple] = []
        self.healed = 0
        self.job_rows: list[dict[str, Any]] = []
        self.row_result: dict[str, Any] | None = None
        self.state: dict[str, Any] | None = None
        self.has_user = True

    def user(self, uid):
        return UserContext(-19, "Minh") if self.has_user else None

    def consents(self, uid):
        return self.consent_rows

    def grant_consent(self, uid, source, version):
        self.consent_rows[source] = {"source": source, "revoked_at": None, "version": version}

    def heal_after_reset(self, uid):
        self.healed += 1
        return 0

    def create_job(self, uid, job_id, kind, key, mime, size):
        self.created.append((uid, job_id, kind, key, mime, size))
        return {"id": job_id}

    def list_jobs(self, uid, limit):
        self.limit = limit
        return self.job_rows[:limit]

    def set_row_jar(self, uid, row_id, jar):
        return self.row_result

    def row_state(self, uid, row_id):
        return self.state

    def jar_rows(self, uid):
        return JARS

    def get_job(self, uid, job_id, limit):
        return None


@pytest.fixture()
def api(monkeypatch):
    for k, v in {
        "AWS_ACCESS_KEY_ID": "AKIAEXAMPLE",
        "AWS_SECRET_ACCESS_KEY": "secret",
        "AWS_DEFAULT_REGION": "ap-southeast-1",
    }.items():
        monkeypatch.setenv(k, v)
    repo = FakeRepo()
    rt = IngestRuntime(
        settings=IngestSettings(), bucket="yofina-ingest-test", upload_prefix="u/", app_timezone="Asia/Ho_Chi_Minh",
        forecast_history_window_days=330, forecast_function_name="", max_receive_count=3, offer_ttl_seconds=600,
    )  # fmt: skip
    confirm = ConfirmService(
        lambda: b"k" * 32, MemJti(), ttl_seconds=120, max_ttl_seconds=120, clock=lambda: NOW
    )
    svc = IngestApi(repo, confirm, rt, presigner=s3_presigner("ap-southeast-1"), clock=lambda: NOW)
    return svc, repo


def event(
    method: str, path: str, body: Any = None, *, sub: str | None = USER, query: dict | None = None
) -> dict[str, Any]:
    claims = {"sub": sub} if sub else {}
    ev: dict[str, Any] = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method, "path": path},
            "authorizer": {"jwt": {"claims": claims}},
        },
        "headers": {},
    }
    if body is not None:
        ev["body"] = json.dumps(body)
    if query:
        ev["queryStringParameters"] = query
    return ev


def call(svc, method, path, body=None, **kw):
    out = handle_http(event(method, path, body, **kw), svc)
    return out["statusCode"], json.loads(out["body"])


# --- POST /ingest/uploads ----------------------------------------------------------------------------------------------------
def test_cap_url_tai_len_dung_chinh_sach_va_khoa(api):
    svc, repo = api
    code, body = call(
        svc,
        "POST",
        "/ingest/uploads",
        {"source_kind": "image", "mime": "image/png", "size_bytes": 12345, "consent": True},
    )
    assert code == 200
    uid, job_id, kind, key, mime, size = repo.created[0]
    assert (uid, kind, mime, size) == (USER, "image", "image/png", 12345)
    assert key == f"u/{USER}/{job_id}" == body["key"] and body["job_id"] == job_id
    assert body["url"].startswith("https://") and "yofina-ingest-test" in body["url"]
    assert body["max_bytes"] == 3_750_000 and body["mime_types"] == [
        "image/png",
        "image/jpeg",
        "image/webp",
    ]
    assert body["expires_at"] == "2026-12-10T03:05:00Z"
    fields = body["fields"]
    assert fields["key"] == key and fields["Content-Type"] == "image/png"
    policy = json.loads(base64.b64decode(fields["policy"]))
    assert ["content-length-range", 1, 3_750_000] in policy["conditions"]
    assert {"Content-Type": "image/png"} in policy["conditions"] and {"key": key} in policy[
        "conditions"
    ]
    assert repo.healed == 1  # tự chữa sau đặt lại demo chạy trước khi tạo job
    assert repo.consent_rows["image_upload"]["version"] == IngestSettings().ingest_consent_version


def test_lan_dau_phai_dong_y_lan_sau_thi_khong(api):
    svc, repo = api
    body = {"source_kind": "csv", "mime": "text/csv", "size_bytes": 100}
    code, err = call(svc, "POST", "/ingest/uploads", body)
    assert (code, err["error"]["code"]) == (403, "CONSENT_REQUIRED") and not repo.created
    call(svc, "POST", "/ingest/uploads", {**body, "consent": True})
    assert call(svc, "POST", "/ingest/uploads", body)[0] == 200  # đã đồng ý nguồn csv
    # đồng ý theo nguồn: ảnh vẫn chưa
    assert (
        call(
            svc,
            "POST",
            "/ingest/uploads",
            {"source_kind": "image", "mime": "image/png", "size_bytes": 1},
        )[0]
        == 403
    )
    # rút đồng ý thì hỏi lại
    repo.consent_rows["csv_upload"]["revoked_at"] = NOW
    assert call(svc, "POST", "/ingest/uploads", body)[0] == 403


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        (
            {"source_kind": "image", "mime": "application/pdf", "size_bytes": 10, "consent": True},
            415,
            "INGEST_UNSUPPORTED_TYPE",
        ),
        (
            {"source_kind": "image", "mime": "text/csv", "size_bytes": 10, "consent": True},
            415,
            "INGEST_UNSUPPORTED_TYPE",
        ),
        (
            {"source_kind": "image", "mime": "image/png", "size_bytes": 3_750_001, "consent": True},
            413,
            "INGEST_TOO_LARGE",
        ),
        (
            {"source_kind": "csv", "mime": "text/csv", "size_bytes": 2_000_001, "consent": True},
            413,
            "INGEST_TOO_LARGE",
        ),
        ({"source_kind": "pdf", "mime": "image/png", "size_bytes": 10}, 400, "PARAMS_INVALID"),
        ({"source_kind": "image", "mime": "image/png", "size_bytes": 0}, 400, "PARAMS_INVALID"),
        ({"source_kind": "image", "mime": "image/png", "size_bytes": "10"}, 400, "PARAMS_INVALID"),
        (
            {"source_kind": "image", "mime": "image/png", "size_bytes": 10, "consent": "yes"},
            400,
            "PARAMS_INVALID",
        ),
        ({"source_kind": "image", "size_bytes": 10}, 400, "PARAMS_INVALID"),
    ],
)
def test_kiem_loai_va_kich_thuoc_truoc_khi_tao_gi(api, body, status, code):
    svc, repo = api
    got, err = call(svc, "POST", "/ingest/uploads", body)
    assert (
        (got, err["error"]["code"]) == (status, code) and not repo.created and not repo.consent_rows
    )


def test_mime_co_tham_so_va_chu_hoa_van_hop_le(api):
    svc, repo = api
    code, _ = call(
        svc,
        "POST",
        "/ingest/uploads",
        {
            "source_kind": "image",
            "mime": "Image/PNG; charset=binary",
            "size_bytes": 5,
            "consent": True,
        },
    )
    assert code == 200 and repo.created[0][4] == "image/png"


def test_tai_khoan_chua_co_ho_so(api):
    svc, repo = api
    repo.has_user = False
    code, err = call(
        svc,
        "POST",
        "/ingest/uploads",
        {"source_kind": "image", "mime": "image/png", "size_bytes": 5, "consent": True},
    )
    assert (code, err["error"]["code"]) == (422, "PROFILE_INCOMPLETE") and not repo.created


# --- trần nạp tệp theo tài khoản mỗi ngày (#13, B4) ------------------------------------------------------------------------
class CountingUsage:
    """Bộ đếm giả cùng giao kèo với `DynamoUsageStore.consume`: tăng nguyên tử, đủ trần thì ném `BudgetCapReached`."""

    def __init__(self, start: int = 0) -> None:
        self.n = start

    def consume(self, *, day: str, model: str, cap: int, ttl_epoch: int) -> int:
        if self.n >= cap:
            raise BudgetCapReached(model)
        self.n += 1
        return self.n


def quota_api(api, used: int) -> tuple[IngestApi, FakeRepo, list[str], CountingUsage]:
    svc, repo = api
    presigned: list[str] = []

    def presign(bucket: str, key: str, mime: str, max_bytes: int, ttl: int) -> dict[str, Any]:
        presigned.append(key)
        return {"url": "https://s3.invalid/", "fields": {"key": key}}

    usage = CountingUsage(used)
    quota = AccountQuota(UPLOAD, store=usage, cap=20, now=lambda: NOW)
    return (
        IngestApi(
            repo, svc.confirm, svc.rt, presigner=presign, clock=lambda: NOW, upload_quota=quota
        ),
        repo,
        presigned,
        usage,
    )


def test_cham_tran_nap_tep_thi_429_co_ma_khong_cap_url_khong_tao_job(api):
    svc, repo, presigned, _ = quota_api(api, used=20)
    body = {"source_kind": "image", "mime": "image/png", "size_bytes": 5, "consent": True}
    code, err = call(svc, "POST", "/ingest/uploads", body)
    assert (code, err["error"]["code"]) == (429, "DAILY_QUOTA_EXCEEDED")
    assert "20" in err["error"]["message"] and "vẫn xem" in err["error"]["message"]
    assert repo.created == [] and presigned == []


def test_chi_lan_cap_url_moi_tinh_vao_tran(api):
    svc, repo, presigned, usage = quota_api(api, used=0)
    image = {"source_kind": "image", "mime": "image/png", "size_bytes": 5}
    assert call(svc, "POST", "/ingest/uploads", image)[0] == 403  # chưa đồng ý
    assert call(svc, "POST", "/ingest/uploads", {**image, "mime": "application/pdf"})[0] == 415
    assert usage.n == 0
    assert call(svc, "POST", "/ingest/uploads", {**image, "consent": True})[0] == 200
    assert usage.n == 1 and len(repo.created) == len(presigned) == 1


# --- danh tính, đường dẫn -----------------------------------------------------------------------------------------------------
def test_khong_co_sub_la_401_va_user_id_trong_than_bi_bo_qua(api):
    svc, repo = api
    code, err = call(svc, "GET", "/ingest/jobs", sub=None)
    assert (code, err["error"]["code"]) == (401, "UNAUTHENTICATED")
    body = {
        "source_kind": "image",
        "mime": "image/png",
        "size_bytes": 5,
        "consent": True,
        "user_id": "sub-khac",
    }
    call(svc, "POST", "/ingest/uploads", body)
    assert repo.created[0][0] == USER


def test_duong_dan_la_va_phuong_thuc_sai(api):
    svc, _ = api
    assert call(svc, "GET", "/ingest/khac")[0] == 400
    assert call(svc, "DELETE", "/ingest/jobs")[0] == 400
    assert (
        call(svc, "PATCH", f"/ingest/rows/{uuid.uuid4()}")[0] == 400
    )  # đổi hũ là POST .../jar (CORS chỉ GET/POST)


# --- GET /ingest/jobs ---------------------------------------------------------------------------------------------------------
def test_danh_sach_job_dung_hinh_dang_summary(api):
    svc, repo = api
    j1, j2 = str(uuid.uuid4()), str(uuid.uuid4())
    repo.job_rows = [
        {"id": j1, "source_kind": "image", "status": "review", "progress": 100, "rows_total": 5, "rows_auto_added": 3,
         "rows_review": 2, "rows_duplicate": 0, "error_code": None, "created_at": datetime(2026, 12, 10, 2, 59, 30, tzinfo=UTC), "finished_at": None},
        {"id": j2, "source_kind": "image", "status": "rejected", "progress": 100, "rows_total": 0, "rows_auto_added": 0,
         "rows_review": 0, "rows_duplicate": 0, "error_code": "INGEST_NOT_FINANCIAL", "created_at": datetime(2026, 12, 9, 8, 10, tzinfo=UTC),
         "finished_at": datetime(2026, 12, 9, 8, 10, 20, tzinfo=UTC)},
    ]  # fmt: skip
    code, body = call(svc, "GET", "/ingest/jobs")
    assert code == 200 and repo.limit == 10  # mặc định 10
    a, b = body["jobs"]
    assert a == {"job_id": j1, "status": "review", "source_kind": "image", "progress": 100, "rows_total": 5,
                 "created_at": "2026-12-10T02:59:30Z", "updated_at": "2026-12-10T02:59:30Z"}  # fmt: skip
    assert b["error_code"] == "INGEST_NOT_FINANCIAL" and b["finished_at"] == "2026-12-09T08:10:20Z"
    assert set(a) | set(b) <= {
        "job_id",
        "status",
        "source_kind",
        "progress",
        "rows_total",
        "error_code",
        "error_message",
        "created_at",
        "updated_at",
        "finished_at",
    }
    assert call(svc, "GET", "/ingest/jobs", query={"limit": "3"})[0] == 200 and repo.limit == 3


@pytest.mark.parametrize("limit", ["0", "21", "abc", "-1"])
def test_limit_ngoai_khoang(api, limit):
    svc, _ = api
    code, err = call(svc, "GET", "/ingest/jobs", query={"limit": limit})
    assert (code, err["error"]["code"]) == (400, "PARAMS_INVALID")


def test_job_khong_co_hoac_id_hong_la_404(api):
    svc, _ = api
    for jid in (str(uuid.uuid4()), "khong-phai-uuid"):
        code, err = call(svc, "GET", f"/ingest/jobs/{jid}")
        assert (code, err["error"]["code"]) == (404, "INGEST_JOB_NOT_FOUND")


# --- POST /ingest/rows/{row_id}/jar ------------------------------------------------------------------------------------------
def test_doi_hu_thanh_cong_tra_hu_day_du(api):
    svc, repo = api
    rid = str(uuid.uuid4())
    repo.row_result = {
        "row_id": rid,
        "suggested_jar_code": "di_lai",
        "jar_source": "user",
        "review_status": "pending",
    }
    code, body = call(svc, "POST", f"/ingest/rows/{rid}/jar", {"jar": "di_lai"})
    assert code == 200
    assert body == {
        "row_id": rid,
        "suggested_jar": {
            "code": "di_lai",
            "name": "Đi lại",
            "color_key": "sky",
            "icon_key": "bus",
        },
        "jar_source": "user",
    }


@pytest.mark.parametrize(
    ("state", "jar", "status", "code"),
    [
        (None, "di_lai", 404, "INGEST_JOB_NOT_FOUND"),
        (
            {"kind": "income", "review_status": "pending", "job_status": "review"},
            "di_lai",
            400,
            "PARAMS_INVALID",
        ),
        (
            {"kind": "expense", "review_status": "approved", "job_status": "done"},
            "di_lai",
            409,
            "INGEST_JOB_NOT_READY",
        ),
        (
            {"kind": "expense", "review_status": "pending", "job_status": "review"},
            "hu_la",
            404,
            "JAR_NOT_FOUND",
        ),
        (
            {"kind": "expense", "review_status": "pending", "job_status": "review"},
            "BAD CODE",
            400,
            "PARAMS_INVALID",
        ),
    ],
)
def test_doi_hu_khong_duoc_thi_bao_dung_ly_do(api, state, jar, status, code):
    svc, repo = api
    repo.state = state
    got, err = call(svc, "POST", f"/ingest/rows/{uuid.uuid4()}/jar", {"jar": jar})
    assert (got, err["error"]["code"]) == (status, code)


# --- xác nhận ---------------------------------------------------------------------------------------------------------------------
def test_tool_khac_confirm_rows_la_400_params_invalid(api):
    svc, _ = api
    for path in ("/ingest/confirmations", "/ingest/actions"):
        for tool in ("move_between_jars", "record_transaction", "khong_co", None):
            code, err = call(
                svc,
                "POST",
                path,
                {"tool": tool, "params": {"job_id": str(uuid.uuid4())}, "confirm_token": "a.b"},
            )
            assert (code, err["error"]["code"]) == (400, "PARAMS_INVALID"), (path, tool)


def test_action_khong_token_la_428_va_params_sai_la_400(api):
    svc, _ = api
    jid, rid = str(uuid.uuid4()), str(uuid.uuid4())
    code, err = call(
        svc,
        "POST",
        "/ingest/actions",
        {"tool": "confirm_rows", "params": {"job_id": jid, "rows": [{"row_id": rid}]}},
    )
    assert (code, err["error"]["code"]) == (428, "NEEDS_CONFIRMATION")
    code, err = call(
        svc,
        "POST",
        "/ingest/actions",
        {"tool": "confirm_rows", "params": {"job_id": jid}, "confirm_token": "a.b"},
    )
    assert (code, err["error"]["code"]) == (
        400,
        "PARAMS_INVALID",
    )  # không có dòng nào để ghi hay bỏ
    code, err = call(
        svc,
        "POST",
        "/ingest/confirmations",
        {
            "tool": "confirm_rows",
            "params": {"job_id": jid, "rows": [{"row_id": rid}, {"row_id": rid}]},
        },
    )
    assert (code, err["error"]["code"]) == (400, "PARAMS_INVALID")
    code, err = call(svc, "POST", "/ingest/actions", {"tool": "confirm_rows"})
    assert (code, err["error"]["code"]) == (400, "PARAMS_INVALID")


def test_token_gia_bi_tu_choi_truoc_khi_doc_gi(api):
    svc, _ = api
    jid, rid = str(uuid.uuid4()), str(uuid.uuid4())
    code, err = call(
        svc,
        "POST",
        "/ingest/actions",
        {
            "tool": "confirm_rows",
            "params": {"job_id": jid, "rows": [{"row_id": rid}]},
            "confirm_token": "aaaa.bbbb",
        },
    )
    assert (code, err["error"]["code"]) == (403, "TOKEN_INVALID")


def test_loi_khong_biet_la_500_khong_ro_chi_tiet(api, monkeypatch):
    svc, repo = api
    monkeypatch.setattr(
        repo, "list_jobs", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("SQL bí mật"))
    )
    code, err = call(svc, "GET", "/ingest/jobs")
    assert code == 500 and "bí mật" not in json.dumps(err, ensure_ascii=False)
