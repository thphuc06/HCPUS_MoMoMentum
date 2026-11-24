"""Worker SQS: bản tin S3 -> job -> trích -> khử trùng -> `ingest_rows`; bỏ qua, từ chối, giao lại, DLQ. Repo và S3 giả trong bộ nhớ,
Bedrock giả nhưng `LlmGateway` thật."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from ingest_helpers import PNG, FakeBedrock, FakeLabelStore, make_gateway
from yofina_ingest.context import Rule
from yofina_ingest.extract import Candidate
from yofina_ingest.settings import IngestRuntime
from yofina_ingest.worker import Worker, handle_sqs, parse_key, pick_matches, s3_records

from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.ingest import IngestSettings, content_sha256, row_dedupe_key
from yofina_core.params import TxTypeInfo

NOW = datetime(2026, 12, 10, 3, 0, tzinfo=UTC)  # offset -19 ngày: ngày mô phỏng 21/11/2026
BUCKET = "yofina-ingest-test"
USER = "sub-minh"
TYPE_MAP = {
    "food_drink": TxTypeInfo("food_drink", "out", "an_uong", None, "Ăn uống"),
    "transfer_person": TxTypeInfo(
        "transfer_person", "out", None, "unclassified", "Chuyển tiền", True, True
    ),
    "salary": TxTypeInfo("salary", "in", None, "other_income", "Lương"),
}
JARS = [
    {
        "code": "an_uong",
        "name": "Ăn uống",
        "color_key": "violet",
        "icon_key": "utensils",
        "kind": "spending",
    },
    {"code": "di_lai", "name": "Đi lại", "color_key": "sky", "icon_key": "bus", "kind": "spending"},
    {
        "code": "chua_phan_loai",
        "name": "Chưa phân loại",
        "color_key": "slate",
        "icon_key": "box",
        "kind": "system",
    },
]


class FakeRepo:
    """Cùng giao diện với `IngestRepo` phần worker dùng, cùng máy trạng thái của `app_update_ingest_job`."""

    def __init__(self) -> None:
        self.labels = FakeLabelStore()
        self.jobs: dict[str, dict[str, Any]] = {}
        self.rows: dict[str, list[dict[str, Any]]] = {}
        self.matches: list[dict[str, Any]] = []
        self.details: dict[str, dict[str, Any]] = {}
        self.details_asked: list[list[str]] = []
        self.fail_with: Exception | None = None
        self.history: list[tuple[str, str]] = []
        self.coverage: dict[str, Any] | None = {
            "income_vnd": Decimal(10_000_000),
            "spend_vnd": Decimal(4_000_000),
            "balance_start_vnd": Decimal(1_000_000),
            "balance_end_vnd": Decimal(3_000_000),
        }

    def add_job(
        self, status: str = "awaiting_upload", kind: str = "image", mime: str = "image/png"
    ) -> tuple[str, str]:
        jid = str(uuid.uuid4())
        key = f"u/{USER}/{jid}"
        self.jobs[jid] = {
            "id": jid, "source_kind": kind, "s3_key": key, "mime": mime, "status": status, "progress": 0,
            "content_sha256": None, "rows_total": 0, "error_code": None, "error_message": None,
        }  # fmt: skip
        return jid, key

    # --- giao diện ---
    def get_job(self, uid, job_id, row_limit=200):
        if self.fail_with:
            raise self.fail_with
        j = self.jobs.get(job_id)
        return (dict(j), list(self.rows.get(job_id, []))) if j else None

    def find_job_by_content(self, uid, sha):
        for j in self.jobs.values():
            if j["content_sha256"] == sha and j["status"] not in ("failed", "rejected"):
                return {"id": j["id"], "status": j["status"]}
        return None

    def update_job(self, uid, job_id, status, progress=None, patch=None):
        j = self.jobs[job_id]
        ok = {
            ("awaiting_upload", "queued"), ("queued", "processing"), ("processing", "review"), ("processing", "done"),
            ("review", "done"),
        }  # fmt: skip
        cur = j["status"]
        if cur in ("done", "failed", "rejected") or not (
            cur == status or status in ("failed", "rejected") or (cur, status) in ok
        ):
            return None
        j.update({k: v for k, v in (patch or {}).items() if v is not None})
        j["status"] = status
        if progress is not None:
            j["progress"] = max(j["progress"], progress)
        self.history.append((job_id, status))
        return {"id": job_id, "status": status}

    def user(self, uid):
        from yofina_ingest.repo import UserContext

        return UserContext(-19, "Minh")

    def jar_rows(self, uid):
        return JARS

    def payee_names(self, uid):
        return ["Highlands Coffee"]

    def tx_types(self):
        return TYPE_MAP

    def rules(self, uid):
        return [Rule("grab", "di_lai")]

    def label_store(self):
        return self.labels

    def find_matches(self, uid, candidates, window):
        self.window = window
        self.candidates = list(candidates)
        return list(self.matches)

    def matched_transactions(self, uid, tx_ids):
        self.details_asked.append(list(tx_ids))
        return {t: self.details[t] for t in tx_ids if t in self.details}

    def insert_rows(self, uid, job_id, rows):
        stored = self.rows.setdefault(job_id, [])
        seen = {r["dedupe_key"] for js in self.rows.values() for r in js}
        ids = {}
        for r in rows:
            if r["dedupe_key"] in seen:
                continue
            ids[r["seq"]] = str(uuid.uuid4())
            stored.append({**r, "id": ids[r["seq"]]})
        return ids

    def coverage_facts(self, uid, now, tz, window):
        return self.coverage


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def get(self, bucket, key, max_bytes):
        if key not in self.objects:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return self.objects[key][: max_bytes + 1]

    def delete(self, bucket, key):
        self.deleted.append(key)
        self.objects.pop(key, None)


def runtime(**kw) -> IngestRuntime:
    base = dict(
        settings=IngestSettings(), bucket=BUCKET, upload_prefix="u/", app_timezone="Asia/Ho_Chi_Minh",
        forecast_history_window_days=330, forecast_function_name="", max_receive_count=3, offer_ttl_seconds=600,
    )  # fmt: skip
    base.update(kw)
    return IngestRuntime(**base)


def good_doc(**row_kw):
    row = {
        "date": "2026-11-18", "amount_vnd": 59000, "direction": "out", "status": "completed",
        "counterparty": "Highlands Coffee", "counterparty_is_person": False,
        "description": "Thanh toan don HC-55102", "tx_type": "food_drink", "jar_code": "an_uong",
        "jar_confidence": 0.9, "confidence": 0.97,
    }  # fmt: skip
    row.update(row_kw)
    return {"document_type": "transfer_receipt", "readable": True, "rows": [row]}


@pytest.fixture()
def env():
    repo, storage = FakeRepo(), FakeStorage()

    def make(script) -> tuple[Worker, FakeBedrock]:
        client = FakeBedrock(script)
        return Worker(
            repo, storage, runtime(), gateway=make_gateway(client), clock=lambda: NOW
        ), client

    return repo, storage, make


def sqs_event(
    key: str, *, receive: int = 1, bucket: str = BUCKET, mid: str = "m1"
) -> dict[str, Any]:
    body = {
        "Records": [
            {
                "eventName": "ObjectCreated:Post",
                "s3": {"bucket": {"name": bucket}, "object": {"key": key}},
            }
        ]
    }
    return {
        "Records": [
            {
                "messageId": mid,
                "body": json.dumps(body),
                "attributes": {"ApproximateReceiveCount": str(receive)},
            }
        ]
    }


def run(worker: Worker, event: dict[str, Any]) -> dict[str, Any]:
    return handle_sqs(event, worker, max_receive_count=3)


# --- khóa và bản tin ---------------------------------------------------------------------------------------------------------
def test_parse_key_va_ban_tin_s3():
    jid = str(uuid.uuid4())
    assert parse_key(f"u/{USER}/{jid}", "u/") == (USER, jid)
    for bad in (
        "x/a/b",
        f"u/{USER}",
        f"u/{USER}/khong-phai-uuid",
        f"u/{USER}/{jid}/extra",
        f"u//{jid}",
    ):
        assert parse_key(bad, "u/") is None
    body = {
        "Records": [
            {
                "eventName": "ObjectCreated:Post",
                "s3": {"bucket": {"name": "b"}, "object": {"key": "u/a%3Ab/c+d"}},
            }
        ]
    }
    assert s3_records(body) == [("b", "u/a:b/c d")]
    assert s3_records({"Service": "Amazon S3", "Event": "s3:TestEvent"}) == []
    assert s3_records({"Records": [{"eventName": "ObjectRemoved:Delete", "s3": {}}]}) == []


# --- đường đi thành công --------------------------------------------------------------------------------------------------------
def test_job_thanh_cong_ghi_dong_da_che_va_chuyen_sang_review(env):
    repo, storage, make = env
    jid, key = repo.add_job()
    storage.objects[key] = PNG
    worker, client = make(
        [
            good_doc(
                counterparty="NGUYEN VAN A",
                counterparty_is_person=True,
                description="CK cho NGUYEN VAN A 0123456789",
                tx_type="transfer_person",
            )
        ]
    )
    assert run(worker, sqs_event(key)) == {"batchItemFailures": []}
    job = repo.jobs[jid]
    assert job["status"] == "review" and job["progress"] == 100
    assert job["content_sha256"] == content_sha256(PNG)
    assert (
        job["rows_total"],
        job["rows_auto_added"],
        job["rows_review"],
        job["rows_duplicate"],
    ) == (1, 1, 1, 0)
    assert job["coverage_before"] == 0.6  # (4.0 + 3.0 - 1.0) / 10.0
    assert job["model"].endswith("claude-sonnet-4-6")
    (r,) = repo.rows[jid]
    assert (
        r["counterparty"] == "N***"
        and "0123456789" not in r["description"]
        and "****6789" in r["description"]
    )
    assert (r["review_status"], r["suggested_jar_code"], r["jar_source"]) == (
        "auto_added",
        "an_uong",
        "model",
    )
    assert r["dedupe_key"] == row_dedupe_key(
        app_date=date(2026, 11, 18),
        amount_vnd=59000,
        counterparty="N***",
        content_sha256=content_sha256(PNG),
        seq=1,
    )
    assert storage.deleted == [key]  # không giữ ảnh gốc
    statuses = [s for _, s in repo.history]
    assert statuses[0] == "queued" and statuses[-1] == "review" and "processing" in statuses
    assert "NGUYEN" not in client.texts()


def test_ngu_canh_nguoi_dung_di_vao_loi_nhac_va_luat(env):
    repo, storage, make = env
    jid, key = repo.add_job()
    storage.objects[key] = PNG
    worker, client = make([good_doc(counterparty="GRAB VN", tx_type=None, jar_code="du_lich")])
    run(worker, sqs_event(key))
    system = client.requests[0]["system"][0]["text"]
    assert (
        "an_uong: Ăn uống" in system
        and "di_lai: Đi lại" in system
        and "chua_phan_loai" not in system
    )
    (r,) = repo.rows[jid]
    assert (r["suggested_jar_code"], r["jar_source"]) == (
        "di_lai",
        "rule",
    )  # luật người dùng thắng đề xuất của model


def test_dong_trung_so_cai_thanh_duplicate_khong_tu_chon(env):
    repo, storage, make = env
    jid, key = repo.add_job()
    storage.objects[key] = PNG
    tx_far, tx_near = str(uuid.uuid4()), str(uuid.uuid4())
    repo.matches = [
        {"idx": 1, "transaction_id": tx_far, "funding_source": "jar", "app_date": date(2026, 11, 20), "day_diff": 2, "counterparty_match": True},
        {"idx": 1, "transaction_id": tx_near, "funding_source": "credit", "app_date": date(2026, 11, 18), "day_diff": 0, "counterparty_match": True},
    ]  # fmt: skip
    worker, _ = make([good_doc()])
    run(worker, sqs_event(key))
    (r,) = repo.rows[jid]
    assert (r["review_status"], r["duplicate_of_transaction_id"]) == ("duplicate", tx_near)
    job = repo.jobs[jid]
    assert (job["rows_duplicate"], job["rows_review"], job["rows_auto_added"]) == (1, 0, 0)
    assert repo.window == IngestSettings().ingest_dedupe_window_days
    sent = repo.candidates[0]
    assert (
        sent["kind"] == "expense"
        and sent["amount_vnd"] == 59000
        and sent["counterparty"] == "highlands coffee"
    )


def cand(seq: int, cp: str | None, desc: str | None = None, amount: int = 59000) -> Candidate:
    return Candidate(seq=seq, kind="expense", app_date=date(2026, 11, 1), amount_vnd=amount, counterparty=cp,
                     description=desc, extract_confidence=0.95)  # fmt: skip


def test_pick_matches_uu_tien_doi_tac_roi_gan_ngay():
    a = {"idx": 1, "transaction_id": "a", "day_diff": 0, "counterparty_match": False}
    b = {"idx": 1, "transaction_id": "b", "day_diff": 2, "counterparty_match": True}
    c = {"idx": 2, "transaction_id": "c", "day_diff": -1, "counterparty_match": True}
    d = {"idx": 2, "transaction_id": "d", "day_diff": 3, "counterparty_match": True}
    best = pick_matches([a, b, c, d], {1: cand(1, "Highlands Coffee"), 2: cand(2, "Grab")}, 3)
    assert best[1]["transaction_id"] == "b" and best[2]["transaction_id"] == "c"


def test_doi_tac_khop_nhung_ngoai_cua_so_khong_trung():
    m = {"idx": 1, "transaction_id": "a", "day_diff": 4, "counterparty_match": True}
    assert pick_matches([m], {1: cand(1, "Highlands Coffee")}, 3) == {}

def test_dong_nap_khac_doi_tac_vao_hang_cho_duyet_khong_bi_danh_trung(env):
    repo, storage, make = env
    jid, key = repo.add_job()
    storage.objects[key] = PNG
    repo.matches = [
        {"idx": 1, "transaction_id": str(uuid.uuid4()), "funding_source": "jar", "app_date": date(2026, 11, 18), "day_diff": 0, "counterparty_match": False},
    ]  # fmt: skip
    worker, _ = make([good_doc()])  # Highlands Coffee 59.000 ₫; giao dịch ví cùng số tiền ở cửa hàng khác
    run(worker, sqs_event(key))
    (r,) = repo.rows[jid]
    assert r["review_status"] != "duplicate" and "duplicate_of_transaction_id" not in r
    assert repo.jobs[jid]["rows_duplicate"] == 0


def test_dong_tien_phong_trung_dong_anh_da_che_doi_tac_thanh_duplicate(env):
    """Dòng 15 của `c01` sau khi ảnh `s02` đã chốt: đối tác "TIEN PHONG" so với "N***" (đã che) là không biết, nội dung gần giống."""
    repo, storage, make = env
    jid, key = repo.add_job()
    storage.objects[key] = PNG
    s02_tx = str(uuid.uuid4())
    repo.matches = [
        {"idx": 1, "transaction_id": s02_tx, "funding_source": "external", "app_date": date(2026, 11, 1), "day_diff": 0, "counterparty_match": False},
    ]  # fmt: skip
    repo.details = {s02_tx: {"transaction_id": s02_tx, "merchant": "N***", "note": "MINH CK tien phong thang 11"}}
    worker, _ = make(
        [
            good_doc(
                date="2026-11-01", amount_vnd=1_500_000, counterparty="TIEN PHONG", counterparty_is_person=False,
                description="MBVCB.3765569.CK tien phong T11", tx_type=None, jar_code=None,
            )
        ]
    )  # fmt: skip
    run(worker, sqs_event(key))
    assert repo.details_asked == [[s02_tx]]
    (r,) = repo.rows[jid]
    assert (r["review_status"], r["duplicate_of_transaction_id"]) == ("duplicate", s02_tx)
    assert repo.jobs[jid]["rows_duplicate"] == 1


def test_moi_dong_da_co_thi_job_bi_tu_choi_trung_tep(env):
    repo, storage, make = env
    jid, key = repo.add_job()
    storage.objects[key] = PNG
    worker, _ = make([good_doc()])
    # khóa khử trùng của dòng đã có sẵn (nạp lại cùng nội dung)
    key_row = row_dedupe_key(
        app_date=date(2026, 11, 18),
        amount_vnd=59000,
        counterparty="Highlands Coffee",
        content_sha256=content_sha256(PNG),
        seq=1,
    )
    repo.rows["other"] = [{"dedupe_key": key_row}]
    run(worker, sqs_event(key))
    assert (
        repo.jobs[jid]["status"] == "rejected"
        and repo.jobs[jid]["error_code"] == "INGEST_DUPLICATE_FILE"
    )


# --- bỏ qua và từ chối -----------------------------------------------------------------------------------------------------------
def test_khoa_la_bucket_la_hoac_job_khong_con_cho_tep_thi_bo_qua(env):
    repo, storage, make = env
    worker, client = make([good_doc()])
    jid, key = repo.add_job(status="review")
    storage.objects[key] = PNG
    assert run(worker, sqs_event(key)) == {"batchItemFailures": []}  # tải lại cùng URL
    assert run(worker, sqs_event("x/y/z")) == {"batchItemFailures": []}
    assert run(worker, sqs_event(key, bucket="bucket-la")) == {"batchItemFailures": []}
    assert run(worker, sqs_event(f"u/{USER}/{uuid.uuid4()}")) == {
        "batchItemFailures": []
    }  # job không có
    assert repo.jobs[jid]["status"] == "review" and client.requests == [] and storage.deleted == []


def test_s3_key_khac_voi_khoa_da_luu_thi_bo_qua(env):
    repo, storage, make = env
    jid, key = repo.add_job()
    repo.jobs[jid]["s3_key"] = f"u/someone-else/{jid}"
    storage.objects[key] = PNG
    worker, client = make([good_doc()])
    run(worker, sqs_event(key))
    assert repo.jobs[jid]["status"] == "awaiting_upload" and client.requests == []


def test_cung_noi_dung_voi_job_con_song_thi_job_moi_bi_tu_choi(env):
    repo, storage, make = env
    first, _ = repo.add_job()
    repo.jobs[first].update(status="review", content_sha256=content_sha256(PNG))
    second, k2 = repo.add_job()
    storage.objects[k2] = PNG
    worker, client = make([good_doc()])
    run(worker, sqs_event(k2))
    assert (
        repo.jobs[second]["status"] == "rejected"
        and repo.jobs[second]["error_code"] == "INGEST_DUPLICATE_FILE"
    )
    assert client.requests == [] and storage.deleted == [k2]
    # job cũ đã failed thì nạp lại được
    repo.jobs[first]["status"] = "failed"
    third, k3 = repo.add_job()
    storage.objects[k3] = PNG
    run(worker, sqs_event(k3))
    assert repo.jobs[third]["status"] == "review"


def test_anh_khong_phai_tai_chinh_job_rejected_voi_ma_loi(env):
    repo, storage, make = env
    jid, key = repo.add_job()
    storage.objects[key] = PNG
    worker, _ = make([{"document_type": "not_financial", "rows": []}])
    run(worker, sqs_event(key))
    j = repo.jobs[jid]
    assert (j["status"], j["error_code"]) == ("rejected", "INGEST_NOT_FINANCIAL") and j[
        "error_message"
    ]
    assert repo.rows.get(jid) is None and storage.deleted == [key]


def test_man_xac_nhan_chua_thuc_hien_khong_sinh_dong_nao(env):
    repo, storage, make = env
    jid, key = repo.add_job()
    storage.objects[key] = PNG
    worker, _ = make([good_doc(status="pending")])
    run(worker, sqs_event(key))
    assert repo.jobs[jid]["status"] == "rejected" and not repo.rows.get(jid)


def test_tep_qua_lon_va_loai_tep_sai(env):
    repo, storage, make = env
    worker, _ = make([good_doc()])
    jid, key = repo.add_job()
    storage.objects[key] = PNG + b"\x00" * (IngestSettings().ingest_image_max_bytes + 10)
    run(worker, sqs_event(key))
    assert (repo.jobs[jid]["status"], repo.jobs[jid]["error_code"]) == (
        "rejected",
        "INGEST_TOO_LARGE",
    )
    jid2, key2 = repo.add_job()
    storage.objects[key2] = b"not an image at all"
    run(worker, sqs_event(key2))
    assert (repo.jobs[jid2]["status"], repo.jobs[jid2]["error_code"]) == (
        "rejected",
        "INGEST_UNSUPPORTED_TYPE",
    )


def test_het_han_muc_model_job_failed_khong_giao_lai(env):
    from yofina_core.llm import LlmSettings, ModelSpec

    repo, storage, make = env
    jid, key = repo.add_job()
    storage.objects[key] = PNG
    worker, client = make([good_doc()])
    worker.gateway.settings = LlmSettings(roles={"ingest": (ModelSpec("m", 0, 0),)})
    assert run(worker, sqs_event(key)) == {"batchItemFailures": []}
    assert (repo.jobs[jid]["status"], repo.jobs[jid]["error_code"]) == (
        "failed",
        "MODEL_BUDGET_EXCEEDED",
    )
    assert client.requests == []


# --- lỗi tạm thời, giao lại, DLQ ---------------------------------------------------------------------------------------------------
def throttled():
    from botocore.exceptions import ClientError

    return ClientError({"Error": {"Code": "ThrottlingException", "Message": "x"}}, "Converse")


def test_model_nghen_giao_lai_roi_chay_tiep_tu_trang_thai_processing(env):
    repo, storage, make = env
    jid, key = repo.add_job()
    storage.objects[key] = PNG
    worker, _ = make(
        [throttled(), throttled(), good_doc()]
    )  # Sonnet và Kimi đều nghẽn ở lần giao đầu
    assert run(worker, sqs_event(key, receive=1)) == {
        "batchItemFailures": [{"itemIdentifier": "m1"}]
    }
    assert (
        repo.jobs[jid]["status"] == "processing" and storage.deleted == []
    )  # tệp gốc còn nguyên cho lần sau
    assert run(worker, sqs_event(key, receive=2)) == {"batchItemFailures": []}
    assert repo.jobs[jid]["status"] == "review"


def test_lan_giao_cuoi_job_duoc_danh_dau_failed_truoc_khi_vao_dlq(env):
    repo, storage, make = env
    jid, key = repo.add_job()
    storage.objects[key] = PNG
    worker, _ = make([throttled()])
    assert run(worker, sqs_event(key, receive=3)) == {
        "batchItemFailures": []
    }  # đã đánh dấu failed, không cần giao lại
    assert (repo.jobs[jid]["status"], repo.jobs[jid]["error_code"]) == ("failed", "INTERNAL_ERROR")


def test_aurora_dang_day_giao_lai_va_lan_cuoi_danh_dau_failed(env):
    repo, storage, make = env
    jid, key = repo.add_job()
    storage.objects[key] = PNG
    worker, _ = make([good_doc()])
    repo.fail_with = YofinaError(ErrorCode.DATABASE_UNAVAILABLE, "dậy")
    assert run(worker, sqs_event(key, receive=1))["batchItemFailures"] == [{"itemIdentifier": "m1"}]
    repo.fail_with = None
    assert run(worker, sqs_event(key, receive=2)) == {"batchItemFailures": []}
    assert repo.jobs[jid]["status"] == "review"


def test_loi_khong_ngo_toi_giao_lai_va_lan_cuoi_danh_dau_failed(env):
    repo, storage, make = env
    jid, key = repo.add_job()
    storage.objects[key] = PNG
    worker, _ = make([good_doc()])
    repo.insert_rows = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("hỏng"))  # type: ignore[method-assign]
    assert run(worker, sqs_event(key, receive=1))["batchItemFailures"] == [{"itemIdentifier": "m1"}]
    out = run(worker, sqs_event(key, receive=3))
    assert out["batchItemFailures"] == [{"itemIdentifier": "m1"}]  # vẫn trả lỗi để bản tin vào DLQ
    assert (repo.jobs[jid]["status"], repo.jobs[jid]["error_code"]) == ("failed", "INTERNAL_ERROR")


def test_loi_mot_ban_tin_khong_keo_theo_ban_tin_khac_va_ban_tin_hong_bi_bo(env):
    repo, storage, make = env
    j1, k1 = repo.add_job()
    j2, k2 = repo.add_job()
    storage.objects[k2] = PNG  # k1 không có tệp: bỏ qua vì NoSuchKey
    worker, _ = make([good_doc()])
    ev = sqs_event(k1, mid="a")
    ev["Records"] += sqs_event(k2, mid="b")["Records"] + [
        {"messageId": "c", "body": "{không phải json", "attributes": {}}
    ]
    assert run(worker, ev) == {"batchItemFailures": []}
    assert repo.jobs[j2]["status"] == "review" and repo.jobs[j1]["status"] == "awaiting_upload"


def test_csv_di_het_duong_worker_khong_goi_model_vision(env):
    repo, storage, make = env
    jid, key = repo.add_job(kind="csv", mime="text/csv")
    storage.objects[key] = (
        b'Ngay,So tien ghi no,So tien ghi co,Noi dung\n01/11/2026,"50,000",,GRAB VIETNAM FT2611229988\n02/11/2026,,"9,000,000",TRA LUONG T10\n'
    )

    def script(req):
        text = req["messages"][0]["content"][0]["text"]
        import re

        idx = [int(m.group(1)) for m in re.finditer(r"^(\d+) \|", text, re.M)]
        return {
            "rows": [
                {"idx": i, "jar_code": "di_lai", "jar_confidence": 0.9, "tx_type": "ride_hailing"}
                for i in idx
            ]
        }

    worker, client = make(script)
    run(worker, sqs_event(key))
    j = repo.jobs[jid]
    assert j["status"] == "review" and j["rows_total"] == 2
    assert all(r["modelId"].endswith("nova-2-lite-v1:0") for r in client.requests)
    kinds = sorted((r["kind"], r["review_status"]) for r in repo.rows[jid])
    assert kinds == [("expense", "auto_added"), ("income", "auto_added")]


def test_handler_worker_op_eval_extract_khong_dung_db_va_bo_qua_s3(monkeypatch):
    """`scripts/eval_ingest.py --via-lambda` gọi trực tiếp op này: chỉ trích, không đọc DB hay S3."""
    import base64
    import importlib.util

    from ingest_helpers import REPO
    from yofina_ingest import extract as ex

    spec = importlib.util.spec_from_file_location(
        "handler_worker_under_test", REPO / "gateway/tools/ingest/handler_worker.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    client = FakeBedrock([{"document_type": "not_financial", "rows": []}])
    monkeypatch.setattr(ex, "eval_gateway", lambda: make_gateway(client))
    monkeypatch.setattr(
        mod,
        "get_worker",
        lambda: (_ for _ in ()).throw(AssertionError("không được dựng worker/DB")),
    )
    out = mod.handler(
        {
            "op": "eval_extract",
            "filename": "s24.png",
            "content_type": "image/png",
            "data_b64": base64.b64encode(PNG).decode(),
        },
        None,
    )
    assert (out["status"], out["error_code"]) == ("error", "not_financial") and len(
        client.requests
    ) == 1
