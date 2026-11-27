"""F6 trên PostgreSQL thật cục bộ: REST `/ingest/*` + worker + `confirm_rows` từ đầu tới cuối (repo thật, SQL thật, RLS thật, role
`yofina_app`), Bedrock và S3 giả. Chạy cùng bộ local_pg (lệnh ở docstring của conftest.py).

Kiểm: số dư hũ KHÔNG đổi; dòng external ghi đúng một lần với khóa khử trùng của dòng; chốt lại không ghi thêm; token dùng lại bị từ chối;
RLS giữa hai người dùng; khử trùng với sổ cái; luật người dùng đọc từ `category_rules`; tự chữa sau khi ledger CŨ đặt lại demo.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import date
from typing import Any

import pytest
from conftest import KEY, REPO, MemoryJti

for extra in ("pipelines/ingest", "gateway/tools/ingest"):
    p = str(REPO / extra)
    if p not in sys.path:
        sys.path.insert(0, p)

from yofina_ingest.api import IngestApi  # noqa: E402
from yofina_ingest.extract import MemoryUsageStore  # noqa: E402
from yofina_ingest.repo import IngestRepo  # noqa: E402
from yofina_ingest.rest import handle_http  # noqa: E402
from yofina_ingest.settings import IngestRuntime  # noqa: E402
from yofina_ingest.worker import Storage, Worker, handle_sqs  # noqa: E402

from yofina_core.blocks import parse_block  # noqa: E402
from yofina_core.config import Config  # noqa: E402
from yofina_core.confirm import ConfirmService  # noqa: E402
from yofina_core.ingest import IngestSettings, content_sha256, coverage_ratio, row_dedupe_key  # noqa: E402
from yofina_core.llm import LlmGateway, load_settings  # noqa: E402

MINH, LAN = "sub-minh", "sub-lan"
BUCKET = "yofina-ingest-test"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x01" * 80
TZ = "Asia/Ho_Chi_Minh"


class FakeBedrock:
    def __init__(self, doc: dict[str, Any]) -> None:
        self.doc = doc
        self.requests: list[dict[str, Any]] = []

    def converse(self, **req: Any) -> dict[str, Any]:
        self.requests.append(req)
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"toolUse": {"toolUseId": "t", "name": "report", "input": self.doc}}
                    ],
                }
            },
            "usage": {"inputTokens": 1, "outputTokens": 1},
        }


class ThrottledBedrock:
    """Bedrock giả luôn nghẽn (Converse và embedding): hũ của mọi dòng phải đến từ đường tất định của bộ phân loại (bảng loại giao
    dịch, nhãn seed khớp chính xác), như trên app khi model bận. Dòng không quyết được thì chờ người dùng chọn."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def _fail(self, op: str, req: dict[str, Any]):
        from botocore.exceptions import ClientError

        self.requests.append(req)
        raise ClientError({"Error": {"Code": "ThrottlingException", "Message": "x"}}, op)

    def converse(self, **req: Any):
        self._fail("Converse", req)

    def invoke_model(self, **req: Any):
        self._fail("InvokeModel", req)


class FakeStorage(Storage):
    def __init__(self) -> None:
        super().__init__()
        self.objects: dict[str, bytes] = {}

    def get(self, bucket, key, max_bytes):
        return self.objects[key][: max_bytes + 1]

    def delete(self, bucket, key):
        self.objects.pop(key, None)


def tx_row(**kw):
    base = {
        "date": "2026-11-18", "amount_vnd": 59370, "direction": "out", "status": "completed",
        "counterparty": "Highlands Coffee", "counterparty_is_person": False, "description": "Thanh toan don HC-55102",
        "tx_type": "food_drink", "jar_code": "an_uong", "jar_confidence": 0.95, "confidence": 0.97,
    }  # fmt: skip
    base.update(kw)
    return base


def doc(*rows):
    return {"document_type": "transaction_history", "readable": True, "rows": list(rows)}


THREE_ROWS = doc(
    tx_row(),
    tx_row(date="2026-11-19", amount_vnd=45230, counterparty="Grab", description="Grab bike", tx_type="ride_hailing", jar_code="di_lai"),
    tx_row(date="2026-11-17", amount_vnd=2_017_000, direction="in", counterparty="Cong ty ABC", description="tra luong", tx_type="salary", jar_code=None),
    tx_row(date="2026-11-16", amount_vnd=12_340, counterparty="Quan la", tx_type="other_expense", jar_code=None, confidence=0.7, description="khong ro"),
)  # fmt: skip


def fake_presign(bucket: str, key: str, mime: str, max_bytes: int, ttl: int) -> dict[str, Any]:
    """Presigned POST giả (chữ ký thật được kiểm ở tests/unit/ingest/test_api.py; môi trường này không có boto3)."""
    return {
        "url": f"https://{bucket}.s3.example.invalid/",
        "fields": {"key": key, "Content-Type": mime},
    }


class Ctx:
    """Một môi trường nạp: API + worker thật trên cùng Data API cục bộ."""

    def __init__(self, env) -> None:
        self.env = env
        self.repo = IngestRepo(env.db)
        self.storage = FakeStorage()
        self.forecast_calls: list[tuple[str, str]] = []
        self.forecast_fail = False
        self.rt = IngestRuntime(
            settings=IngestSettings(), bucket=BUCKET, upload_prefix="u/", app_timezone=TZ,
            forecast_history_window_days=330, forecast_function_name="x", max_receive_count=3, offer_ttl_seconds=600,
        )  # fmt: skip
        self.jti = MemoryJti()
        confirm = ConfirmService(
            lambda: KEY, self.jti, ttl_seconds=120, max_ttl_seconds=120, clock=env.clock
        )

        def trigger(uid: str, trig: str) -> bool:
            if self.forecast_fail:
                raise RuntimeError("Lambda dự báo hỏng")
            self.forecast_calls.append((uid, trig))
            return True

        self.api = IngestApi(
            self.repo,
            confirm,
            self.rt,
            presigner=fake_presign,
            forecast_trigger=trigger,
            clock=env.clock,
        )

    # --- REST ---
    def call(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        user: str = MINH,
        query: dict | None = None,
    ):
        ev: dict[str, Any] = {
            "rawPath": path,
            "requestContext": {
                "http": {"method": method, "path": path},
                "authorizer": {"jwt": {"claims": {"sub": user}}},
            },
            "headers": {},
        }
        if body is not None:
            ev["body"] = json.dumps(body)
        if query:
            ev["queryStringParameters"] = query
        out = handle_http(ev, self.api)
        return out["statusCode"], json.loads(out["body"])

    def upload(
        self, user: str = MINH, kind: str = "image", mime: str = "image/png"
    ) -> dict[str, Any]:
        code, body = self.call(
            "POST",
            "/ingest/uploads",
            {"source_kind": kind, "mime": mime, "size_bytes": 1000, "consent": True},
            user=user,
        )
        assert code == 200, body
        return body

    def process(
        self, up: dict[str, Any], data: bytes, model_doc: dict[str, Any], user: str = MINH
    ) -> FakeBedrock:
        """S3 nhận tệp rồi bắn thông báo qua SQS: worker xử lý."""
        client = FakeBedrock(model_doc)
        self.run_worker(up, data, client)
        return client

    def run_worker(self, up: dict[str, Any], data: bytes, client: Any) -> None:
        """S3 nhận tệp rồi bắn thông báo qua SQS: worker xử lý với client Bedrock `client`."""
        self.storage.objects[up["key"]] = data
        gw = LlmGateway(
            load_settings(Config({}), env={}),
            client=client,
            usage=MemoryUsageStore(),
            sleep=lambda _s: None,
        )
        worker = Worker(self.repo, self.storage, self.rt, gateway=gw, clock=self.env.clock)
        body = {
            "Records": [
                {
                    "eventName": "ObjectCreated:Post",
                    "s3": {"bucket": {"name": BUCKET}, "object": {"key": up["key"]}},
                }
            ]
        }
        ev = {
            "Records": [
                {
                    "messageId": "m",
                    "body": json.dumps(body),
                    "attributes": {"ApproximateReceiveCount": "1"},
                }
            ]
        }
        assert handle_sqs(ev, worker, max_receive_count=3) == {"batchItemFailures": []}

    def job(self, job_id: str, user: str = MINH) -> dict[str, Any]:
        code, body = self.call("GET", f"/ingest/jobs/{job_id}", user=user)
        assert code == 200, body
        return body

    def confirm(self, params: dict[str, Any], user: str = MINH):
        code, issued = self.call(
            "POST", "/ingest/confirmations", {"tool": "confirm_rows", "params": params}, user=user
        )
        if code != 200:
            return code, issued
        return self.call(
            "POST",
            "/ingest/actions",
            {
                "tool": "confirm_rows",
                "params": issued["params"],
                "confirm_token": issued["confirm_token"],
            },
            user=user,
        )


@pytest.fixture()
def ing(env):
    env.reset(MINH)
    env.reset(LAN)
    return Ctx(env)


def balances(env, user=MINH) -> dict[str, int]:
    with env.master() as m:
        rows = m.execute(
            "SELECT code, balance_vnd FROM jars WHERE user_id = %s ORDER BY code", (user,)
        ).fetchall()
    return {c: int(b) for c, b in rows}


def q(env, sql: str, *args):
    with env.master() as m:
        return m.execute(sql, args).fetchall()


def external(env, user=MINH):
    return q(
        env,
        "SELECT id, kind, jar_code, amount_vnd, app_date, source, funding_source, needs_review, dedupe_key, tx_type, classified_by, merchant "
        "FROM transactions WHERE user_id = %s AND funding_source = 'external' ORDER BY app_date, amount_vnd",
        user,
    )


def ids_by_amount(job: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {r["amount_vnd"]: r for r in job["review"]["data"]["rows"]}


# --- đường chính ------------------------------------------------------------------------------------------------------------
def test_duong_chinh_tu_tai_len_toi_chot_so_du_hu_khong_doi(ing, env):
    before_balances = balances(env)
    up = ing.upload()
    assert up["key"] == f"u/{MINH}/{up['job_id']}" and up["fields"]["key"] == up["key"]
    assert ing.job(up["job_id"])["status"] == "awaiting_upload"
    ing.process(up, PNG, THREE_ROWS)

    job = ing.job(up["job_id"])
    assert job["status"] == "review" and job["rows_total"] == 4 and job["progress"] == 100
    review = job["review"]
    parse_block(review)  # khối hợp lệ theo Pydantic của hợp đồng
    data = review["data"]
    assert data["counts"] == {
        "auto_added": 3,
        "pending": 1,
        "approved": 0,
        "rejected": 0,
        "duplicate": 0,
    }
    rows = ids_by_amount(job)
    assert (
        rows[59370]["suggested_jar"]["code"] == "an_uong"
        and rows[59370]["jar_source"] == "type_map"
    )
    assert rows[45230]["suggested_jar"]["code"] == "di_lai"
    assert rows[2_017_000]["kind"] == "income" and "suggested_jar" not in rows[2_017_000]
    assert rows[12_340]["review_status"] == "pending" and "suggested_jar" not in rows[12_340]
    assert {j["code"] for j in data["jars"]} >= {"an_uong", "di_lai"}
    assert "chua_phan_loai" not in {j["code"] for j in data["jars"]}

    # đổi hũ một chạm: chỉ đổi đề xuất, không ghi sổ cái
    code, body = ing.call("POST", f"/ingest/rows/{rows[12_340]['row_id']}/jar", {"jar": "giai_tri"})
    assert (
        code == 200 and body["suggested_jar"]["code"] == "giai_tri" and body["jar_source"] == "user"
    )
    assert external(env) == []

    # xác nhận rồi chốt: ghi 3 dòng (chi an_uong, chi giai_tri, thu), bỏ dòng đi lại
    params = {
        "job_id": up["job_id"],
        "rows": [
            {"row_id": rows[59370]["row_id"]},
            {"row_id": rows[12_340]["row_id"]},
            {"row_id": rows[2_017_000]["row_id"]},
        ],
        "reject_row_ids": [rows[45230]["row_id"]],
    }
    code, issued = ing.call(
        "POST", "/ingest/confirmations", {"tool": "confirm_rows", "params": params}
    )
    assert code == 200 and issued["tool"] == "confirm_rows" and len(issued["params_hash"]) == 64
    assert issued["preview"]["summary"] and issued["preview"]["warnings"]
    changes = {c["label"]: c for c in issued["preview"]["changes"]}
    assert changes["Số dư các hũ"] == {"label": "Số dư các hũ", "after": "Không đổi"}
    assert "Độ phủ dữ liệu" in changes
    assert external(env) == []  # xác nhận không ghi gì

    code, receipt = ing.call(
        "POST",
        "/ingest/actions",
        {
            "tool": "confirm_rows",
            "params": issued["params"],
            "confirm_token": issued["confirm_token"],
        },
    )
    assert code == 200, receipt
    parse_block(receipt)
    assert receipt["type"] == "receipt_action" and receipt["data"]["tool"] == "confirm_rows"
    assert receipt["data"]["reference_id"] == up["job_id"] and receipt["data"]["jars_after"] == []
    cov = receipt["data"]["coverage_change"]
    assert cov["type"] == "coverage_change" and cov["data"]["rows_added"] == 3
    assert (
        cov["data"]["external_spend_added_vnd"] == 59370 + 12340
        and cov["data"]["external_income_added_vnd"] == 2_017_000
    )
    assert {j["code"] for j in cov["data"]["jars_affected"]} == {"an_uong", "giai_tri"}
    assert cov["data"]["forecast_refresh"] == "queued" and ing.forecast_calls == [(MINH, "manual")]

    # sổ cái: đúng ba dòng external, số dư hũ KHÔNG đổi
    assert balances(env) == before_balances
    ext = external(env)
    assert len(ext) == 3
    by_amount = {abs(int(r[3])): r for r in ext}
    chi, thu = by_amount[59370], by_amount[2_017_000]
    assert (chi[1], chi[2], int(chi[3]), chi[4], chi[5], chi[6], chi[7]) == (
        "expense",
        "an_uong",
        -59370,
        date(2026, 11, 18),
        "ingest",
        "external",
        False,
    )
    assert chi[8] == row_dedupe_key(
        app_date=date(2026, 11, 18),
        amount_vnd=59370,
        counterparty="Highlands Coffee",
        content_sha256=content_sha256(PNG),
        seq=1,
    )
    assert (chi[9], chi[10], chi[11]) == ("food_drink", "type_map", "Highlands Coffee")
    assert (thu[1], thu[2], int(thu[3]), thu[9], thu[10]) == (
        "income",
        None,
        2_017_000,
        "salary",
        None,
    )
    assert (by_amount[12340][2], by_amount[12340][10]) == ("giai_tri", "user")

    # job done, dòng đã duyệt có transaction_id, dòng bị bỏ là rejected, độ phủ lưu lại
    done = ing.job(up["job_id"])
    assert done["status"] == "done" and done["finished_at"]
    assert done["review"]["data"]["counts"] == {
        "auto_added": 0,
        "pending": 0,
        "approved": 3,
        "rejected": 1,
        "duplicate": 0,
    }
    assert (
        done["coverage_change"]["data"]["rows_added"] == 3
        and done["coverage_change"]["data"]["after"] == cov["data"]["after"]
    )
    approved = q(
        env,
        "SELECT count(*) FROM ingest_rows r JOIN transactions t ON t.id = r.transaction_id WHERE r.job_id = %s AND r.review_status = 'approved'",
        up["job_id"],
    )
    assert approved[0][0] == 3

    # độ phủ lưu lại khớp công thức dự báo (cùng số với app_get_data_coverage). Ví của minh là ví đóng: mọi thu nhập là lương vào
    # ví nên độ phủ đã kẹp ở 1,0 và không đổi sau khi nạp; "nạp làm độ phủ tăng" kiểm trên vy (ca dưới, tệp mẫu của cảnh 5)
    facts = ing.repo.coverage_facts(MINH, env.clock.now, TZ, 330)
    assert cov["data"]["after"] == coverage_ratio(facts)
    assert cov["data"]["before"] == cov["data"]["after"] == 1.0

    # nhật ký audit không chứa token
    audit = q(
        env,
        "SELECT event_type, params::text FROM audit_events WHERE user_id = %s AND event_type = 'confirm_rows'",
        MINH,
    )
    assert len(audit) == 1 and "confirm_token" not in audit[0][1]

    # danh sách job gần đây
    code, listing = ing.call("GET", "/ingest/jobs")
    assert (
        code == 200
        and listing["jobs"][0]["job_id"] == up["job_id"]
        and listing["jobs"][0]["status"] == "done"
    )


def test_vy_nap_tep_mau_canh_5_qua_duong_chinh_do_phu_tang_dung_cong_thuc(env):
    """Độ phủ tăng sau khi nạp (ý của đường chính) trên persona có độ phủ dưới 1: `vy` (thu nhập ngoài ví) đặt lại bằng đúng đường của
    `POST /demo/reset`, tải tệp mẫu của cảnh 5 (`vy_sao_ke_vcb.csv`) qua REST nạp, worker, `confirm_rows`. Kỳ vọng suy từ bộ sinh
    persona (`persona_coverage.coverage_facts`): độ phủ trước bằng số của dữ liệu sinh, sau bằng số đó cộng đúng các khoản chi đã chốt;
    hai dòng tiền vào của tệp là thu nhập ngoài ví đã có nên không chốt (không cộng đôi)."""
    from conftest import ANCHOR
    from persona_coverage import coverage_facts as persona_facts

    from personas import generate, generate_out_of_wallet
    from personas.six_jars import apply_demo_layout
    from yofina_ledger.jar_layout import DEMO_LAYOUT
    from yofina_ml import quality
    from yofina_ml.types import CoverageInputs

    vy = "sub-vy-canh5"  # người dùng riêng mang persona vy (audit của lần nạp không xóa khi đặt lại)
    env.svc.reset_demo(vy, "vy", trace_id="t" * 8)
    ing = Ctx(env)
    data = generate("vy", anchor=ANCHOR)
    demo = apply_demo_layout(data, DEMO_LAYOUT)  # ví mà đặt lại nạp: thành phần độ phủ tính trên ví này
    before = coverage_ratio(ing.repo.coverage_facts(vy, env.clock.now, TZ, 330))
    assert before == quality.data_coverage(CoverageInputs(**persona_facts(demo))) < 1.0
    bal_before = balances(env, vy)

    up = ing.upload(vy, kind="csv", mime="text/csv")
    ing.run_worker(up, (REPO / "data/personas/samples/vy_sao_ke_vcb.csv").read_bytes(), ThrottledBedrock())
    job = ing.job(up["job_id"], user=vy)
    assert job["status"] == "review", job
    rows = job["review"]["data"]["rows"]
    # dòng tiền vào của tệp là thu nhập freelance đã có trong sổ cái (ngoài ví): chỉ chốt dòng chi, bỏ mọi dòng khác
    incomes = [r for r in rows if r["kind"] == "income"]
    assert len(incomes) == len([t for t in generate_out_of_wallet("vy", anchor=ANCHOR, data=data).source("statement").rows if t.kind == "income"])
    # README của data/personas: hai dòng này là "trùng" (đối tác "STUDIO NANG…" của sao kê là "Studio Nắng (freelance thiết kế)")
    assert {r["review_status"] for r in incomes} == {"duplicate"}
    open_rows = [r for r in rows if r["review_status"] != "duplicate"]
    take = [r for r in open_rows if r["kind"] == "expense" and "suggested_jar" in r]
    skip = [r for r in open_rows if r not in take]
    assert take  # hầu hết dòng chi tự có hũ gợi ý (README "Tệp mẫu cho cảnh 5")
    code, receipt = ing.confirm(
        {
            "job_id": up["job_id"],
            "rows": [{"row_id": r["row_id"]} for r in take],
            "reject_row_ids": [r["row_id"] for r in skip],
        },
        user=vy,
    )
    assert code == 200, receipt
    cov = receipt["data"]["coverage_change"]["data"]
    spent = sum(r["amount_vnd"] for r in take)
    assert cov["rows_added"] == len(take) and cov["external_spend_added_vnd"] == spent
    assert cov.get("external_income_added_vnd", 0) == 0
    after = quality.data_coverage(CoverageInputs(**persona_facts(demo, extra_expenses=spent)))
    assert (cov["before"], cov["after"]) == (before, after) and after > before
    assert cov["after"] == coverage_ratio(ing.repo.coverage_facts(vy, env.clock.now, TZ, 330))
    assert balances(env, vy) == bal_before  # dòng external không đổi số dư hũ


def test_chot_lai_khong_ghi_them_va_token_dung_lai_bi_tu_choi(ing, env):
    up = ing.upload()
    ing.process(up, PNG, THREE_ROWS)
    rows = ids_by_amount(ing.job(up["job_id"]))
    params = {
        "job_id": up["job_id"],
        "rows": [{"row_id": rows[59370]["row_id"]}],
        "reject_row_ids": [],
    }
    code, issued = ing.call(
        "POST", "/ingest/confirmations", {"tool": "confirm_rows", "params": params}
    )
    body = {
        "tool": "confirm_rows",
        "params": issued["params"],
        "confirm_token": issued["confirm_token"],
    }
    assert ing.call("POST", "/ingest/actions", body)[0] == 200
    n_tx = q(env, "SELECT count(*) FROM transactions WHERE user_id = %s", MINH)[0][0]
    bal = balances(env)

    code, err = ing.call("POST", "/ingest/actions", body)  # cùng token
    assert (code, err["error"]["code"]) == (409, "TOKEN_REUSED")
    code, err = ing.confirm(params)  # token mới cho job đã xong
    assert (code, err["error"]["code"]) == (409, "ALREADY_APPLIED")
    assert q(env, "SELECT count(*) FROM transactions WHERE user_id = %s", MINH)[0][0] == n_tx
    assert balances(env) == bal and len(external(env)) == 1
    # dòng chưa nhắc tới được coi là bỏ khi job đóng
    done = ing.job(up["job_id"])
    assert (
        done["review"]["data"]["counts"]["approved"] == 1
        and done["review"]["data"]["counts"]["rejected"] == 3
    )


def test_token_gan_voi_nguoi_va_tham_so(ing, env):
    up = ing.upload()
    ing.process(up, PNG, THREE_ROWS)
    rows = ids_by_amount(ing.job(up["job_id"]))
    a, b = rows[59370]["row_id"], rows[45230]["row_id"]
    code, issued = ing.call(
        "POST",
        "/ingest/confirmations",
        {"tool": "confirm_rows", "params": {"job_id": up["job_id"], "rows": [{"row_id": a}]}},
    )
    tok = issued["confirm_token"]
    bal = balances(env)
    # đổi tham số sau khi ký
    code, err = ing.call(
        "POST",
        "/ingest/actions",
        {
            "tool": "confirm_rows",
            "params": {"job_id": up["job_id"], "rows": [{"row_id": a}, {"row_id": b}]},
            "confirm_token": tok,
        },
    )
    assert (code, err["error"]["code"]) == (409, "PARAMS_MISMATCH")
    # người khác dùng token
    code, err = ing.call(
        "POST",
        "/ingest/actions",
        {"tool": "confirm_rows", "params": issued["params"], "confirm_token": tok},
        user=LAN,
    )
    assert (code, err["error"]["code"]) == (403, "TOKEN_INVALID")
    assert external(env) == [] and balances(env) == bal
    # token vẫn dùng được sau khi bị từ chối do tham số sai
    assert (
        ing.call(
            "POST",
            "/ingest/actions",
            {"tool": "confirm_rows", "params": issued["params"], "confirm_token": tok},
        )[0]
        == 200
    )


def test_kiem_nghiep_vu_truoc_khi_ky_token(ing, env):
    up = ing.upload()
    ing.process(up, PNG, THREE_ROWS)
    rows = ids_by_amount(ing.job(up["job_id"]))
    job = up["job_id"]
    stray = str(uuid.uuid4())
    for params, code_want in [
        ({"job_id": job, "rows": [{"row_id": stray}]}, "PARAMS_INVALID"),  # dòng không thuộc job
        (
            {"job_id": job, "rows": [{"row_id": rows[12_340]["row_id"]}]},
            "PARAMS_INVALID",
        ),  # dòng chi chưa có hũ
        (
            {"job_id": job, "rows": [{"row_id": rows[12_340]["row_id"], "jar": "hu_la"}]},
            "JAR_NOT_FOUND",
        ),
        (
            {"job_id": job, "rows": [{"row_id": rows[12_340]["row_id"], "jar": "chua_phan_loai"}]},
            "JAR_NOT_FOUND",
        ),  # hũ hệ thống
        (
            {"job_id": str(uuid.uuid4()), "rows": [{"row_id": rows[59370]["row_id"]}]},
            "INGEST_JOB_NOT_FOUND",
        ),
    ]:
        code, err = ing.call(
            "POST", "/ingest/confirmations", {"tool": "confirm_rows", "params": params}
        )
        assert err["error"]["code"] == code_want, (params, err)
    assert external(env) == []
    # job chưa đọc xong thì chưa chốt được
    up2 = ing.upload()
    code, err = ing.call(
        "POST",
        "/ingest/confirmations",
        {"tool": "confirm_rows", "params": {"job_id": up2["job_id"], "rows": [{"row_id": stray}]}},
    )
    assert (code, err["error"]["code"]) == (409, "INGEST_JOB_NOT_READY")


def test_hai_nguoi_dung_khong_thay_viec_cua_nhau(ing, env):
    up = ing.upload()
    ing.process(up, PNG, THREE_ROWS)
    rows = ids_by_amount(ing.job(up["job_id"]))
    code, err = ing.call("GET", f"/ingest/jobs/{up['job_id']}", user=LAN)
    assert (code, err["error"]["code"]) == (404, "INGEST_JOB_NOT_FOUND")
    code, err = ing.call(
        "POST", f"/ingest/rows/{rows[59370]['row_id']}/jar", {"jar": "di_lai"}, user=LAN
    )
    assert (code, err["error"]["code"]) == (404, "INGEST_JOB_NOT_FOUND")
    code, err = ing.call(
        "POST",
        "/ingest/confirmations",
        {
            "tool": "confirm_rows",
            "params": {"job_id": up["job_id"], "rows": [{"row_id": rows[59370]["row_id"]}]},
        },
        user=LAN,
    )
    assert code == 404
    assert ing.call("GET", "/ingest/jobs", user=LAN)[1] == {"jobs": []}
    assert external(env, LAN) == [] and external(env) == []


def test_du_bao_loi_khong_lam_hong_viec_da_ghi(ing, env):
    up = ing.upload()
    ing.process(up, PNG, THREE_ROWS)
    rows = ids_by_amount(ing.job(up["job_id"]))
    ing.forecast_fail = True
    code, receipt = ing.confirm(
        {"job_id": up["job_id"], "rows": [{"row_id": rows[59370]["row_id"]}]}
    )
    assert (
        code == 200 and receipt["data"]["coverage_change"]["data"]["forecast_refresh"] == "skipped"
    )
    assert len(external(env)) == 1


# --- khử trùng, luật, nội dung ----------------------------------------------------------------------------------------------
def test_dong_trung_giao_dich_da_co_trong_vi_thanh_duplicate_va_khong_chot_duoc(ing, env):
    amount = 59_371
    merchant = "Highlands Coffee"
    env.act(MINH, "record_transaction", {
        "kind": "expense", "amount_vnd": amount, "jar": "an_uong", "counterparty": merchant,
    })
    tx = q(
        env,
        "SELECT id, app_date, abs(amount_vnd) FROM transactions WHERE user_id = %s "
        "AND kind = 'expense' AND funding_source = 'jar' AND amount_vnd = %s AND merchant = %s",
        MINH, -amount, merchant,
    )[0]
    near = tx[1].isoformat()
    up = ing.upload()
    ing.process(
        up, PNG, doc(tx_row(date=near, amount_vnd=amount, counterparty=merchant), tx_row(amount_vnd=777_000))
    )
    job = ing.job(up["job_id"])
    rows = ids_by_amount(job)
    dup = rows[int(tx[2])]
    assert dup["review_status"] == "duplicate" and dup["duplicate_of"] == str(tx[0])
    assert (
        job["review"]["data"]["counts"]["duplicate"] == 1
        and rows[777_000]["review_status"] == "auto_added"
    )
    code, err = ing.confirm({"job_id": up["job_id"], "rows": [{"row_id": dup["row_id"]}]})
    assert (code, err["error"]["code"]) == (400, "PARAMS_INVALID")
    # cùng số tiền nhưng lệch ngày quá cửa sổ thì không phải bản trùng
    far = ing.upload()
    ing.process(far, PNG + b"2", doc(tx_row(date="2025-01-05", amount_vnd=int(tx[2]))))
    assert ids_by_amount(ing.job(far["job_id"]))[int(tx[2])]["review_status"] == "auto_added"


def _statuses(job: dict[str, Any], amount: int) -> list[str]:
    return sorted(r["review_status"] for r in job["review"]["data"]["rows"] if r["amount_vnd"] == amount)


def _confirm_one(ing: Ctx, data: bytes, row: dict[str, Any]) -> None:
    """Nạp một ảnh một dòng rồi chốt dòng đó vào sổ cái (ngoài ví) như màn duyệt."""
    up = ing.upload()
    ing.process(up, data, doc(row))
    (r,) = ing.job(up["job_id"])["review"]["data"]["rows"]
    code, receipt = ing.confirm({"job_id": up["job_id"], "rows": [{"row_id": r["row_id"], "jar": "giai_tri"}]})
    assert code == 200, receipt


def test_hai_ly_ca_phe_giong_het_so_da_co_mot_thi_mot_dong_trung_mot_dong_moi(ing, env):
    """Ghép một-một (C6 của #39): ví ghi một ly Highlands 45.000 ₫, ảnh lịch sử có hai ly cùng ngày. Một dòng là bản trùng, dòng kia
    là lần mua thật: vào hàng duyệt, chốt được."""
    amount, merchant = 45_000, "Highlands Coffee"
    env.act(MINH, "record_transaction", {"kind": "expense", "amount_vnd": amount, "jar": "an_uong", "counterparty": merchant})
    (tx_id, day) = q(
        env, "SELECT id, app_date FROM transactions WHERE user_id = %s AND funding_source = 'jar' AND amount_vnd = %s "
        "AND merchant = %s ORDER BY created_at DESC LIMIT 1", MINH, -amount, merchant,
    )[0]  # fmt: skip
    up = ing.upload()
    cup = tx_row(date=day.isoformat(), amount_vnd=amount, counterparty=merchant, description="Ca phe sua da")
    ing.process(up, PNG, doc(cup, cup))
    job = ing.job(up["job_id"])
    rows = [r for r in job["review"]["data"]["rows"] if r["amount_vnd"] == amount]
    assert _statuses(job, amount) == ["auto_added", "duplicate"] and job["review"]["data"]["counts"]["duplicate"] == 1
    assert next(r for r in rows if r["review_status"] == "duplicate")["duplicate_of"] == str(tx_id)
    fresh = next(r for r in rows if r["review_status"] != "duplicate")
    assert ing.confirm({"job_id": up["job_id"], "rows": [{"row_id": fresh["row_id"]}]})[0] == 200
    assert [abs(int(r[3])) for r in external(env)] == [amount]


def test_hai_lan_chuyen_500k_cho_cung_nguoi_so_da_co_mot_thi_mot_lan_la_moi(ing, env):
    """Lần nạp trước đã chốt một khoản chuyển 500.000 ₫ cho "Nguyễn Thu Hà" (người nhận đã lưu, tên không bị che); sao kê sau có hai
    lần chuyển 500.000 ₫ cho cùng người, cùng ngày: chỉ một lần là bản trùng."""
    send = tx_row(date="2026-11-18", amount_vnd=500_000, counterparty="Nguyễn Thu Hà", counterparty_is_person=True,
                  description="CK Nguyen Thu Ha", tx_type="transfer_person", jar_code=None)  # fmt: skip
    _confirm_one(ing, PNG, send)
    (prior,) = external(env)
    assert prior[11] == "Nguyễn Thu Hà"
    up = ing.upload()
    ing.process(up, PNG + b"sao-ke", doc(send, {**send, "description": "CK Nguyen Thu Ha lan 2"}))
    job = ing.job(up["job_id"])
    assert _statuses(job, 500_000) == ["duplicate", "pending"]
    assert next(r for r in job["review"]["data"]["rows"] if r["review_status"] == "duplicate")["duplicate_of"] == str(prior[0])


def test_hai_khoan_1_trieu_cho_hai_nguoi_da_che_ten_khong_trung(ing, env):
    """Sổ cái có khoản 1.000.000 ₫ ngoài ví cho một người đã che tên ("N***", lần nạp trước); ảnh mới có khoản 1.000.000 ₫ cùng ngày cho
    người khác cũng bị che ("T***"). Cùng số tiền không đủ bằng chứng là cùng người: dòng mới vào hàng duyệt, không bị ẩn."""
    first = tx_row(date="2026-11-18", amount_vnd=1_000_000, counterparty="NGUYEN VAN A", counterparty_is_person=True,
                   description="CK", tx_type="transfer_person", jar_code=None)  # fmt: skip
    _confirm_one(ing, PNG, first)
    assert [r[11] for r in external(env)] == ["N***"]
    up = ing.upload()
    ing.process(up, PNG + b"khac", doc({**first, "counterparty": "TRAN VAN B"}))
    job = ing.job(up["job_id"])
    (r,) = job["review"]["data"]["rows"]
    assert (r["counterparty"], r["review_status"]) == ("T***", "pending")
    assert job["review"]["data"]["counts"]["duplicate"] == 0


def test_cung_noi_dung_voi_job_con_song_bi_tu_choi_va_nap_lai_duoc_sau_khi_that_bai(ing, env):
    first = ing.upload()
    ing.process(first, PNG, THREE_ROWS)
    second = ing.upload()
    ing.process(second, PNG, THREE_ROWS)
    j = ing.job(second["job_id"])
    assert (j["status"], j["error_code"]) == ("rejected", "INGEST_DUPLICATE_FILE")
    assert ing.job(first["job_id"])["status"] == "review"
    # job đầu bị từ chối thì dọn dòng chưa chốt, nạp lại được
    ing.repo.update_job(
        MINH,
        first["job_id"],
        "rejected",
        patch={"error_code": "INGEST_NOT_FINANCIAL", "error_message": "x"},
    )
    third = ing.upload()
    ing.process(third, PNG, THREE_ROWS)
    assert ing.job(third["job_id"])["status"] == "review"


def test_luat_nguoi_dung_trong_category_rules_thang_de_xuat_cua_model(ing, env):
    with env.master() as m:
        m.execute(
            "INSERT INTO category_rules (user_id, match_type, merchant_key, jar_code, scope) VALUES (%s, 'merchant', 'highlands coffee', 'giai_tri', 'always')",
            (MINH,),
        )
    up = ing.upload()
    ing.process(up, PNG, doc(tx_row()))
    (r,) = ing.job(up["job_id"])["review"]["data"]["rows"]
    assert (r["suggested_jar"]["code"], r["jar_source"], r["jar_confidence"]) == (
        "giai_tri",
        "rule",
        0.99,
    )


def test_pii_da_che_truoc_khi_luu_va_khong_co_cot_van_ban_tho(ing, env):
    up = ing.upload()
    client = ing.process(
        up,
        PNG,
        doc(
            tx_row(
                counterparty="NGUYEN VAN A",
                counterparty_is_person=True,
                description="CK cho NGUYEN VAN A STK 0123456789 sdt 0912345678",
                tx_type="transfer_person",
                jar_code="an_uong",
            )
        ),
    )
    stored = q(
        env, "SELECT counterparty, description FROM ingest_rows WHERE job_id = %s", up["job_id"]
    )[0]
    blob = " ".join(stored)
    assert (
        "NGUYEN" not in blob
        and "0123456789" not in blob
        and "0912345678" not in blob
        and stored[0] == "N***"
    )
    logs = json.dumps(client.requests[0]["system"], ensure_ascii=False)
    assert "0123456789" not in logs
    assert (
        q(env, "SELECT s3_key FROM ingest_jobs WHERE id = %s", up["job_id"])[0][0] == up["key"]
    )  # khóa chỉ có người dùng và id


def test_csv_den_cuoi_c01_co_dong_thu_va_chi(ing, env):
    data = (REPO / "evals/ingest/synthetic/csv/c01_vcb_50.csv").read_bytes()
    up = ing.upload(kind="csv", mime="text/csv")
    ing.storage.objects[up["key"]] = data

    def script_gateway():
        class Csv(FakeBedrock):
            def converse(self, **req):
                text = req["messages"][0]["content"][0]["text"]
                idx = [int(m.group(1)) for m in re.finditer(r"^(\d+) \|", text, re.M)]
                self.doc = {
                    "rows": [
                        {
                            "idx": i,
                            "jar_code": "an_uong",
                            "jar_confidence": 0.9,
                            "tx_type": "food_drink",
                        }
                        for i in idx
                    ]
                }
                return super().converse(**req)

        return Csv({})

    gw = LlmGateway(
        load_settings(Config({}), env={}),
        client=script_gateway(),
        usage=MemoryUsageStore(),
        sleep=lambda _s: None,
    )
    worker = Worker(ing.repo, ing.storage, ing.rt, gateway=gw, clock=env.clock)
    body = {
        "Records": [
            {
                "eventName": "ObjectCreated:Post",
                "s3": {"bucket": {"name": BUCKET}, "object": {"key": up["key"]}},
            }
        ]
    }
    handle_sqs(
        {"Records": [{"messageId": "m", "body": json.dumps(body), "attributes": {}}]},
        worker,
        max_receive_count=3,
    )
    job = ing.job(up["job_id"])
    assert job["status"] == "review" and job["rows_total"] == 50
    kinds = {r["kind"] for r in job["review"]["data"]["rows"]}
    assert kinds == {"expense", "income"}


# --- tự chữa sau khi ledger cũ đặt lại demo ------------------------------------------------------------------------------------
def test_tu_chua_sau_dat_lai_demo_bang_ledger_cu_nap_lai_cung_tep_duoc(ing, env):
    up = ing.upload()
    ing.process(up, PNG, THREE_ROWS)
    rows = ids_by_amount(ing.job(up["job_id"]))
    code, _ = ing.confirm(
        {
            "job_id": up["job_id"],
            "rows": [{"row_id": rows[59370]["row_id"]}, {"row_id": rows[2_017_000]["row_id"]}],
        }
    )
    assert code == 200 and len(external(env)) == 2

    # Ledger CŨ đặt lại demo: xóa giao dịch của người dùng nhưng KHÔNG xóa bảng nạp (nên dòng approved mồ côi)
    with env.master() as m:
        m.execute(
            "DELETE FROM transactions WHERE user_id = %s AND funding_source = 'external'", (MINH,)
        )
    assert (
        q(
            env,
            "SELECT count(*) FROM ingest_rows WHERE user_id = %s AND review_status = 'approved'",
            MINH,
        )[0][0]
        == 2
    )
    assert q(env, "SELECT count(*) FROM ingest_jobs WHERE user_id = %s", MINH)[0][0] == 1

    # Không tự chữa thì cùng tệp bị chặn (khóa khử trùng và trùng nội dung); POST /uploads tự dọn rồi nạp lại bình thường
    again = ing.upload()
    assert (
        q(env, "SELECT count(*) FROM ingest_jobs WHERE user_id = %s", MINH)[0][0] == 1
    )  # job cũ đã xóa, chỉ còn job mới
    assert q(env, "SELECT count(*) FROM ingest_rows WHERE user_id = %s", MINH)[0][0] == 0
    ing.process(again, PNG, THREE_ROWS)
    j = ing.job(again["job_id"])
    assert j["status"] == "review" and j["rows_total"] == 4
    code, _receipt = ing.confirm(
        {"job_id": again["job_id"], "rows": [{"row_id": ids_by_amount(j)[59370]["row_id"]}]}
    )
    assert code == 200 and len(external(env)) == 1


def test_tu_chua_khong_dung_vao_viec_dang_cho_duyet_hay_nguoi_khac(ing, env):
    pending = ing.upload()
    ing.process(pending, PNG, THREE_ROWS)
    other = ing.upload(user=LAN)
    ing.process(other, PNG, THREE_ROWS, user=LAN)
    assert ing.repo.heal_after_reset(MINH) == 0
    assert ing.job(pending["job_id"])["status"] == "review"
    assert ing.job(other["job_id"], user=LAN)["status"] == "review"


def test_dat_lai_cua_ledger_moi_xoa_du_lieu_nap_va_nap_lai_duoc(ing, env):
    up = ing.upload()
    ing.process(up, PNG, THREE_ROWS)
    rows = ids_by_amount(ing.job(up["job_id"]))
    assert (
        ing.confirm({"job_id": up["job_id"], "rows": [{"row_id": rows[59370]["row_id"]}]})[0] == 200
    )
    env.reset(MINH)  # ledger của repo này xóa luôn bảng nạp và consents
    assert q(env, "SELECT count(*) FROM ingest_jobs WHERE user_id = %s", MINH)[0][0] == 0
    assert q(env, "SELECT count(*) FROM consents WHERE user_id = %s", MINH)[0][0] == 0
    code, err = ing.call(
        "POST", "/ingest/uploads", {"source_kind": "image", "mime": "image/png", "size_bytes": 10}
    )
    assert (code, err["error"]["code"]) == (
        403,
        "CONSENT_REQUIRED",
    )  # đặt lại đưa về trạng thái chưa từng nạp
    again = ing.upload()
    ing.process(again, PNG, THREE_ROWS)
    assert ing.job(again["job_id"])["status"] == "review"
