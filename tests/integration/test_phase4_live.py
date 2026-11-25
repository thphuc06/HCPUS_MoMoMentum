"""Phase 4 (chống chịu, lộ trình, phân hũ tự động) trên môi trường THẬT: REST (JWT Cognito) -> Lambda ledger / forecast -> Aurora,
tool qua AgentCore Gateway thật, Lambda `yofina-classify` nghe sự kiện thật trên `yofina-bus`.

Tiêu chí phase 4 phần backend: 1 (điểm chống chịu của `minh`, ba cú sốc: số lấy từ engine, KHÔNG ép số Figma 58 -> 34), 2 (bản
`proposed` lý do `behavior_changed`, so được với bản trước, quyết định/sửa bước/chọn phiên bản), 7 (chuyển cho
đối tác mới: trong 60 giây có hũ hoặc vào hỏi gộp; sửa hũ "luôn luôn cho người này" thì giao dịch kế tiếp tự đúng), 8 phần thời gian
giải LP (`solver.elapsed_ms`). Số đo ghi vào `build/reports/phase4-live-measures.json`.

Seed của `minh` không còn cài sẵn bản v3 `behavior_changed` (issue #22: sau đặt lại chỉ có v1 đã thay, v2 đang dùng). Bản đó được tạo
bằng đường thật của cảnh 4 (fixture `behavior_proposal`, dùng cho test 06 tới 10): nạp tệp sao kê hai tuần qua REST `/ingest/*`, chốt
dòng, bước PELT của lần tính lại dự báo xác nhận đổi hành vi, Lambda `yofina-roadmap-regen` lưu bản chờ chọn. Bước này gọi model planner
(Sonnet, một lượt sinh lộ trình) và chờ tới 4 phút cho mỗi lần chạy module.

Không có model hay số dựng sẵn: mọi số đọc từ phản hồi thật; điểm tổng được tính lại từ bốn thành phần bằng trọng số của
`resilience_defaults.json` (cùng file engine đọc). Test chạy tuần tự (thứ tự tên) vì cùng dùng tài khoản `minh`.
"""

from __future__ import annotations

import json
import time
import uuid

import pytest
from conftest import REPO, demo_balances

pytestmark = pytest.mark.usefixtures("fresh")

BLOCKS = "https://contracts.yofina.invalid/blocks"
TOOLS = "https://contracts.yofina.invalid/tools"
CORE = REPO / "libs" / "yofina_core" / "src" / "yofina_core"
REPORT_DIR = REPO / "build" / "reports"
MEASURES: dict[str, object] = {}
UNCLASSIFIED = "chua_phan_loai"
CLASSIFY_WAIT_SECONDS = 60.0
NO_USER = "00000000-0000-4000-8000-000000000000"
#: tệp sao kê cảnh 4 (gắn ngày neo 21/11 của ví demo: đặt lại rồi nạp trong cùng ngày), như tests/local_pg/test_change_flow.py
SCENE4_CSV = REPO / "data" / "personas" / "samples" / "minh_sao_ke_2_tuan.csv"
#: S3 -> SQS -> worker nạp (Aurora có thể đang thức), rồi tính lại dự báo, PELT, `behavior.changed`, Lambda sinh lại lộ trình (model)
SCENE4_WAIT_SECONDS = 240.0
INGEST_TERMINAL = ("review", "done", "failed", "rejected")
INGEST_OPEN = ("auto_added", "pending")

NEW_TOOLS = {
    "planner___optimize_allocation",
    "planner___save_roadmap",
    "planner___get_roadmap",
    "forecast___get_resilience_score",
    "forecast___stress_test",
}


def code(body) -> str:
    return body["error"]["code"]


def load_config(name: str) -> dict:
    return json.loads((CORE / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module", autouse=True)
def write_measures():
    yield
    if MEASURES:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        (REPORT_DIR / "phase4-live-measures.json").write_text(
            json.dumps(MEASURES, ensure_ascii=False, indent=2), encoding="utf-8"
        )


@pytest.fixture(scope="module")
def shock_ids() -> list[str]:
    return [s["shock_id"] for s in load_config("shocks.json")["shocks"]]


def balances(api, who: str = "minh") -> dict[str, int]:
    status, body = api(who, "GET", "/jars")
    assert status == 200, body
    return {j["code"]: j["balance_vnd"] for j in body["jars"]}


def step_status(block: dict, step_id: str) -> str:
    for phase in block["data"]["phases"]:
        for step in phase["steps"]:
            if step["step_id"] == step_id:
                return step["status"]
    raise AssertionError(f"không có bước {step_id}")


def all_step_ids(block: dict) -> list[str]:
    return [s["step_id"] for p in block["data"]["phases"] for s in p["steps"]]


# --- 1. điểm chống chịu -------------------------------------------------------------------------------------------------------
def test_01_diem_chong_chiu_dung_schema_du_bon_thanh_phan_va_khop_phep_tinh(api, schema_validator):
    status, block = api("minh", "GET", "/resilience", timeout=120)
    assert status == 200, block
    schema_validator(f"{BLOCKS}/resilience_score.schema.json", block)
    schema_validator.openapi("ResilienceScoreResponse", block)
    data = block["data"]
    assert [c["key"] for c in data["components"]] == ["save", "spend", "borrow", "plan"]

    weights = {k: v["value"] for k, v in load_config("resilience_defaults.json")["weights"].items()}
    applicable = [c for c in data["components"] if c["applicable"]]
    total_w = sum(weights[c["key"]] for c in applicable)
    for c in applicable:
        assert c["weight"] == pytest.approx(weights[c["key"]] / total_w, abs=0.005)
        assert c["explanation"] and c["inputs"]
    assert sum(c["weight"] for c in applicable) == pytest.approx(1.0, abs=0.01)
    expected = sum(c["weight"] * c["score"] for c in applicable)
    assert abs(data["score"] - expected) <= 1, (data["score"], expected)
    assert data["weakest"] == min(applicable, key=lambda c: c["score"])["key"]
    assert "không phải điểm tín dụng" in data["disclaimer"].lower()
    assert data["band"] in {"weak", "fair", "strong"}

    status, again = api("minh", "GET", "/resilience")
    assert status == 200 and again["data"]["score"] == data["score"]  # đọc lại không đổi số
    MEASURES["resilience_minh"] = {
        "score": data["score"],
        "band": data["band"],
        "weakest": data["weakest"],
        "config_version": data["config_version"],
        "components": {c["key"]: c["score"] for c in data["components"]},
        "figma_reference": "58 (chỉ để so; dùng số engine)",
    }


def test_02_ba_cu_soc_doc_tu_du_lieu(api, schema_validator, shock_ids):
    status, body = api("minh", "GET", "/resilience/shocks")
    assert status == 200, body
    schema_validator.openapi("ShocksResponse", body)
    assert [s["shock_id"] for s in body["shocks"]] == shock_ids and len(shock_ids) == 3
    assert {s["kind"] for s in body["shocks"]} == {"income_loss", "expense_increase", "health_event"}


def test_03_moi_cu_soc_ra_stress_result_diem_sau_khong_lon_hon_diem_truoc(
    api, schema_validator, shock_ids
):
    status, score_block = api("minh", "GET", "/resilience")
    assert status == 200
    before = score_block["data"]["score"]
    measured = {}
    for shock_id in shock_ids:
        t0 = time.perf_counter()
        status, block = api(
            "minh", "POST", "/resilience/stress", {"shock_id": shock_id}, timeout=120
        )
        elapsed = time.perf_counter() - t0
        assert status == 200, (shock_id, block)
        schema_validator(f"{BLOCKS}/stress_result.schema.json", block)
        schema_validator.openapi("StressResultResponse", block)
        d = block["data"]
        assert d["shock"]["shock_id"] == shock_id
        assert d["score_before"] == before
        assert d["score_after"] <= d["score_before"]
        assert d["score_delta"] == d["score_after"] - d["score_before"]
        assert d["status"] in {"ok", "tight", "short"}
        assert (d["shortfall_vnd"] > 0) == (d["status"] == "short")
        if "runway_days_total" in d:
            assert 0 <= d["runway_days_total"] <= d["horizon_days"]
        assert d["common_random_numbers"] is True and d["method"] == "monte_carlo"
        # cùng đầu vào, cùng dãy số ngẫu nhiên: gọi lại ra đúng kết quả cũ
        status, again = api("minh", "POST", "/resilience/stress", {"shock_id": shock_id})
        assert status == 200 and again["data"]["score_after"] == d["score_after"]
        measured[shock_id] = {
            "status": d["status"],
            "score_before": d["score_before"],
            "score_after": d["score_after"],
            "runway_days_total": d.get("runway_days_total"),
            "runway_days_emergency": d.get("runway_days_emergency"),
            "shortfall_vnd": d["shortfall_vnd"],
            "seconds": round(elapsed, 2),
        }
    MEASURES["stress_minh"] = measured
    # ít nhất một cú sốc làm điểm thật sự tụt (mất việc): engine có phản ứng với dữ liệu
    assert any(m["score_after"] < m["score_before"] for m in measured.values())


def test_04_cu_soc_la_va_cu_soc_thieu_bi_tu_choi(api):
    status, body = api("minh", "POST", "/resilience/stress", {"shock_id": "khong_co_cu_soc_nay"})
    assert (status, code(body)) == (404, "SHOCK_NOT_FOUND")
    status, body = api("minh", "POST", "/resilience/stress", {})
    assert status == 400
    status, body = api(
        "minh", "POST", "/resilience/stress", {"shock_id": "mat_viec_2_thang", "user_id": NO_USER}
    )
    assert status == 400  # không nhận user_id từ thân yêu cầu


def test_05_diem_cua_lan_khac_minh_va_khong_co_token_la_401(api):
    status, minh = api("minh", "GET", "/resilience")
    status_l, lan = api("lan", "GET", "/resilience", timeout=120)
    assert status == 200 and status_l == 200
    assert lan["data"] != minh["data"] and lan["id"] != minh["id"]
    status, _ = api(None, "GET", "/resilience")
    assert status == 401


# --- 2. lộ trình ------------------------------------------------------------------------------------------------------------
def _poll(api, path: str, done, *, timeout: float, what: str) -> dict:
    """GET `path` của minh (backoff 2 -> 8 giây) tới khi `done(body)`; lỗi tạm thời của Aurora đang thức (502/503/504) thì thử lại."""
    end = time.monotonic() + timeout
    delay, last = 2.0, None
    while time.monotonic() < end:
        status, body = api("minh", "GET", path, timeout=60)
        last = (status, body)
        if status not in (502, 503, 504):
            assert status == 200, (path, status, body)
            if done(body):
                return body
        time.sleep(delay)
        delay = min(delay * 1.4, 8.0)
    pytest.fail(f"{what} chưa xong sau {timeout:.0f} giây; lần đọc cuối: {last}")


@pytest.fixture(scope="module")
def behavior_proposal(api, fresh) -> dict:
    """Bản chờ chọn lý do `behavior_changed` tạo bằng ĐƯỜNG THẬT của cảnh 4, như tests/local_pg/test_change_flow.py nhưng trên AWS: nạp
    `minh_sao_ke_2_tuan.csv` qua REST `/ingest/*` (S3 presigned POST, worker), chốt mọi dòng đã tự chọn hũ bằng token; ingest kích hoạt
    tính lại dự báo (`manual`), bước PELT xác nhận đổi hành vi hũ Ăn uống và phát `behavior.changed`, Lambda `yofina-roadmap-regen` lưu bản
    `proposed`. Không cài dấu hiệu hay phiên bản bằng tay. Trả số phiên bản trước khi nạp (`active`, `latest`) và bản chờ (`proposed`)."""
    from test_ingest_live import put_to_s3  # tải lên S3 đúng thứ tự trường của presigned POST

    before = _poll(api, "/roadmap/versions", lambda b: True, timeout=60, what="đọc phiên bản lộ trình")
    assert "proposed_version" not in before, before  # seed không còn bản chờ (issue #22)
    latest = max(v["version"] for v in before["versions"])

    t0 = time.monotonic()
    data = SCENE4_CSV.read_bytes()
    status, up = api(
        "minh", "POST", "/ingest/uploads",
        {"source_kind": "csv", "mime": "text/csv", "size_bytes": len(data), "consent": True},
    )  # fmt: skip
    assert status == 200, up
    put_to_s3(up, data, "text/csv")
    job = _poll(
        api, f"/ingest/jobs/{up['job_id']}", lambda b: b["status"] in INGEST_TERMINAL,
        timeout=SCENE4_WAIT_SECONDS, what="job nạp sao kê cảnh 4",
    )  # fmt: skip
    assert job["status"] == "review", job
    rows = [r for r in job["review"]["data"]["rows"] if r["review_status"] in INGEST_OPEN]
    # cảnh 4 trên app: mọi dòng chi tự vào Ăn uống, không phải chọn hũ
    assert rows and {r.get("suggested_jar", {}).get("code") for r in rows if r["kind"] == "expense"} == {"an_uong"}, rows
    params = {"job_id": up["job_id"], "rows": [{"row_id": r["row_id"]} for r in rows]}
    status, conf = api("minh", "POST", "/ingest/confirmations", {"tool": "confirm_rows", "params": params})
    assert status == 200, conf
    status, receipt = api(
        "minh", "POST", "/ingest/actions",
        {"tool": "confirm_rows", "params": conf["params"], "confirm_token": conf["confirm_token"]},
    )  # fmt: skip
    assert status == 200, receipt

    def proposed_ready(body: dict) -> bool:
        job_ = body.get("current_job") or {}
        assert job_.get("status") != "failed", job_  # job sinh lại lỗi: dừng ngay, không chờ hết giờ
        n = body.get("proposed_version")
        return n is not None and {v["version"]: v for v in body["versions"]}[n]["reason_code"] == "behavior_changed"

    after = _poll(
        api, "/roadmap/versions", proposed_ready, timeout=SCENE4_WAIT_SECONDS,
        what="bản lộ trình behavior_changed sau khi nạp sao kê cảnh 4",
    )  # fmt: skip
    MEASURES["scene4_proposal_seconds"] = round(time.monotonic() - t0, 1)
    return {"active": before["active_version"], "latest": latest, "proposed": after["proposed_version"]}


def test_06_sau_nap_sao_ke_canh_4_co_v1_superseded_v2_active_v3_proposed_behavior_changed(
    api, schema_validator, behavior_proposal
):
    active, proposed = behavior_proposal["active"], behavior_proposal["proposed"]
    status, body = api("minh", "GET", "/roadmap/versions")
    assert status == 200, body
    schema_validator.openapi("RoadmapVersionsResponse", body)
    by_version = {v["version"]: v for v in body["versions"]}
    # seed: v1 đã thay, v2 đang dùng; bản mới là bản lớn nhất cộng một, xuất phát từ bản đang dùng
    assert (active, proposed) == (2, behavior_proposal["latest"] + 1)
    assert [by_version[n]["status"] for n in (1, active, proposed)] == ["superseded", "active", "proposed"]
    assert by_version[1]["reason_code"] == "initial"
    assert by_version[proposed]["reason_code"] == "behavior_changed"
    assert by_version[proposed]["based_on_version"] == active
    assert body["active_version"] == active and body["proposed_version"] == proposed
    assert [v["version"] for v in body["versions"]] == sorted(by_version, reverse=True)


def test_07_doc_lo_trinh_dang_dung_va_ban_cho_chon(api, schema_validator, behavior_proposal):
    active, proposed_v = behavior_proposal["active"], behavior_proposal["proposed"]
    status, active_block = api("minh", "GET", "/roadmap", timeout=60)
    assert status == 200, active_block
    schema_validator(f"{BLOCKS}/roadmap.schema.json", active_block)
    schema_validator.openapi("RoadmapResponse", active_block)
    assert active_block["data"]["version"] == active and active_block["data"]["status"] == "active"
    status, proposed = api("minh", "GET", f"/roadmap?version={proposed_v}")
    assert status == 200, proposed
    schema_validator(f"{BLOCKS}/roadmap.schema.json", proposed)
    d = proposed["data"]
    assert d["version"] == proposed_v and d["status"] == "proposed"
    assert d["reason"]["code"] == "behavior_changed" and d["reason"]["behavior_flag_id"]
    assert sum(d["counts"].values()) == len(all_step_ids(proposed))
    for phase in d["phases"]:
        for step in phase["steps"]:
            assert step["reason"] and step["status"] in {"pending", "accepted", "rejected"}


def test_08_so_phien_ban_moi_voi_ban_cu(api, schema_validator, behavior_proposal):
    active, proposed = behavior_proposal["active"], behavior_proposal["proposed"]
    status, diff = api("minh", "GET", "/roadmap/diff", timeout=60)
    assert status == 200, diff
    schema_validator(f"{BLOCKS}/roadmap_diff.schema.json", diff)
    schema_validator.openapi("RoadmapDiffResponse", diff)
    d = diff["data"]
    assert (d["from_version"], d["to_version"], d["to_status"]) == (active, proposed, "proposed")
    assert d["reason"]["code"] == "behavior_changed" and d["can_adopt"] is True
    counts = d["counts"]
    assert counts["added"] + counts["removed"] + counts["changed"] >= 1
    assert len(d["changes"]) == counts["added"] + counts["removed"] + counts["changed"]
    status, explicit = api("minh", "GET", f"/roadmap/diff?from_version=1&to_version={active}")
    assert status == 200, explicit
    assert (explicit["data"]["from_version"], explicit["data"]["to_version"]) == (1, active)
    assert explicit["data"]["can_adopt"] is False  # bản đang dùng không phải bản chờ chọn
    status, body = api("minh", "GET", f"/roadmap/diff?from_version={active}&to_version={active}")
    assert status == 400  # hai phiên bản trùng nhau
    status, body = api("minh", "GET", f"/roadmap/diff?from_version={active}&to_version=99")
    assert (status, code(body)) == (404, "ROADMAP_NOT_FOUND")


def test_09_quyet_dinh_mot_buoc_khong_dung_den_so_du(api, schema_validator, behavior_proposal):
    version = behavior_proposal["proposed"]
    status, proposed = api("minh", "GET", f"/roadmap?version={version}")
    assert status == 200, proposed
    steps = all_step_ids(proposed)
    assert len(steps) >= 2
    before = balances(api)
    status, accepted = api(
        "minh", "POST", f"/roadmap/steps/{steps[0]}/decision", {"version": version, "decision": "accepted"}
    )
    assert status == 200, accepted
    schema_validator(f"{BLOCKS}/roadmap.schema.json", accepted)
    assert step_status(accepted, steps[0]) == "accepted"
    assert accepted["data"]["version"] == version and accepted["data"]["status"] == "proposed"
    assert accepted["data"]["counts"]["accepted"] == 1
    status, rejected = api(
        "minh",
        "POST",
        f"/roadmap/steps/{steps[1]}/decision",
        {"version": version, "decision": "rejected", "reason": "Tháng này em chưa làm được"},
    )
    assert status == 200, rejected
    assert step_status(rejected, steps[1]) == "rejected"
    assert step_status(rejected, steps[0]) == "accepted"  # quyết định trước vẫn còn
    assert rejected["data"]["counts"]["rejected"] == 1
    assert balances(api) == before  # chấp nhận bước không tự chuyển tiền (ADR-0002)
    status, undone = api(
        "minh", "POST", f"/roadmap/steps/{steps[1]}/decision", {"version": version, "decision": "pending"}
    )
    assert status == 200 and step_status(undone, steps[1]) == "pending"


def test_10_loi_khi_quyet_dinh_buoc_la_hoac_tham_so_sai(api, behavior_proposal):
    version = behavior_proposal["proposed"]
    status, proposed = api("minh", "GET", f"/roadmap?version={version}")
    assert status == 200, proposed
    step = all_step_ids(proposed)[0]  # bước có thật của bản do model lập: lỗi dưới đây là do tham số, không do thiếu bước
    status, body = api(
        "minh", "POST", "/roadmap/steps/khong_co_buoc/decision", {"version": version, "decision": "accepted"}
    )
    assert (status, code(body)) == (404, "ROADMAP_NOT_FOUND")
    status, body = api(
        "minh", "POST", f"/roadmap/steps/{step}/decision", {"version": 99, "decision": "accepted"}
    )
    assert (status, code(body)) == (404, "ROADMAP_NOT_FOUND")
    status, body = api(
        "minh", "POST", f"/roadmap/steps/{step}/decision", {"version": version, "decision": "maybe"}
    )
    assert status == 400
    status, body = api("minh", "POST", f"/roadmap/steps/{step}/edit", {"version": version})
    assert status == 400  # phải có amount_vnd hoặc due_date
    status, body = api("lan", "GET", "/roadmap")
    assert (status, code(body)) == (404, "ROADMAP_NOT_FOUND")  # Lan chưa có lộ trình, không thấy của Minh
    status, body = api("lan", "GET", f"/roadmap?version={version}")
    assert (status, code(body)) == (404, "ROADMAP_NOT_FOUND")


def test_11_yeu_cau_sinh_lai_tra_job_goi_lai_tra_dung_job_do(api, schema_validator):
    status, job = api("minh", "POST", "/roadmap/regenerate", {"note": "Tháng này tôi muốn tiết kiệm hơn"})
    assert status == 200, job
    schema_validator.openapi("RoadmapJob", job)
    assert job["trigger"] == "user_request" and job["status"] in {"queued", "running", "done"}
    status, same = api("minh", "POST", "/roadmap/regenerate", {})
    assert status == 200 and same["job_id"] == job["job_id"]  # đang có job thì trả chính job đó
    status, polled = api("minh", "GET", f"/roadmap/jobs/{job['job_id']}")
    assert status == 200 and polled["job_id"] == job["job_id"]
    schema_validator.openapi("RoadmapJob", polled)
    if polled["status"] not in {"done", "failed"}:
        status, versions = api("minh", "GET", "/roadmap/versions")
        assert versions["current_job"]["job_id"] == job["job_id"]
        schema_validator.openapi("RoadmapVersionsResponse", versions)
    MEASURES["regenerate_job_status"] = polled["status"]
    status, body = api("minh", "GET", f"/roadmap/jobs/{NO_USER}")
    assert (status, code(body)) == (404, "ROADMAP_NOT_FOUND")  # job lạ
    status, body = api("lan", "GET", f"/roadmap/jobs/{job['job_id']}")
    assert (status, code(body)) == (404, "ROADMAP_NOT_FOUND")  # job của người khác cũng như không có

    # Lambda yofina-roadmap-regen chạy job trong nền (Sonnet + Data API + Invoke tool): chờ tới khi xong, job phải `done` và có
    # phiên bản mới. Xong thì đặt lại minh: bản mới đã loại bản v3 `proposed` mà các test sau cần.
    t0 = time.monotonic()
    while polled["status"] not in {"done", "failed"} and time.monotonic() - t0 < 240:
        time.sleep(5)
        status, polled = api("minh", "GET", f"/roadmap/jobs/{job['job_id']}")
        assert status == 200, polled
    MEASURES["regenerate_job_status"] = polled["status"]
    MEASURES["regenerate_job_seconds"] = round(time.monotonic() - t0, 1)
    assert polled["status"] == "done", polled
    schema_validator.openapi("RoadmapJob", polled)
    status, latest = api("minh", "GET", "/roadmap?which=latest")
    assert status == 200 and latest["data"]["reason"]["code"] == "user_request", latest
    from conftest import reset_account

    reset_account(api, "minh")


#: khóa của một bước trong bản nháp `save_roadmap` (planner.json); khối đọc ra còn có trạng thái và luật đã kiểm do Lambda điền
DRAFT_STEP_KEYS = (
    "step_id", "kind", "title", "reason", "ai_generated", "amount_vnd", "jar_code", "to_jar_code", "due_date",
    "metrics", "action",
)  # fmt: skip


def propose_from_active(api, gw, schema_validator) -> dict:
    """Bản đề xuất dựng từ bản đang dùng qua đúng tool `planner___save_roadmap` của Gateway (seed của minh không còn bản chờ chọn từ
    #22: sau đặt lại chỉ có v1 đã thay và v2 đang dùng). Bản thứ hai trở đi `save_roadmap` lưu là `proposed`, kiểm lại suitability từng
    bước như mọi bản nháp. Trả khối dữ liệu của bản vừa lưu."""
    status, active = api("minh", "GET", "/roadmap")
    assert status == 200, active
    d = active["data"]
    assert d["status"] == "active", d
    phases = [
        {
            **{k: v for k, v in ph.items() if k != "steps"},
            "steps": [{k: s[k] for k in DRAFT_STEP_KEYS if k in s} for s in ph["steps"]],
        }
        for ph in d["phases"]
    ]
    draft = {
        "reason_code": "user_request",
        "based_on_version": d["version"],
        "feasibility": d["feasibility"],
        "goals": d["goals"],
        "alternatives": d.get("alternatives", []),
        "phases": phases,
    }
    reply = gw("minh").call("planner___save_roadmap", draft)
    # dự báo của lần đặt lại được tính trong nền (batch sau `/demo/reset`): chưa có thì save_roadmap trả FORECAST_UNAVAILABLE
    t0 = time.monotonic()
    while reply.status == "ERROR" and reply.data["code"] == "FORECAST_UNAVAILABLE" and time.monotonic() - t0 < 90:
        time.sleep(5)
        reply = gw("minh").call("planner___save_roadmap", draft)
    assert reply.status == "OK", reply.text
    schema_validator(f"{TOOLS}/planner.results.schema.json#/$defs/SaveRoadmapResult", reply.data)
    saved = reply.data["data"]
    assert saved["status"] == "proposed" and saved["based_on_version"] == d["version"], saved
    return saved


def test_12_dung_ban_moi_roi_sua_mot_buoc_ra_ban_active_moi(api, gw, schema_validator):
    from conftest import reset_account

    reset_account(api, "minh")
    new = propose_from_active(api, gw, schema_validator)["version"]
    status, adopted = api("minh", "POST", f"/roadmap/versions/{new}/decision", {"decision": "adopt"})
    assert status == 200, adopted
    assert adopted["data"]["version"] == new and adopted["data"]["status"] == "active"
    status, versions = api("minh", "GET", "/roadmap/versions")
    by_version = {v["version"]: v for v in versions["versions"]}
    assert by_version[new]["status"] == "active" and by_version[new - 1]["status"] == "superseded"
    assert versions["active_version"] == new and "proposed_version" not in versions

    status, current = api("minh", "GET", "/roadmap")
    editable = [
        (s["step_id"], s["amount_vnd"])
        for p in current["data"]["phases"]
        for s in p["steps"]
        if s.get("amount_vnd")
    ]
    assert editable, "lộ trình mẫu phải có ít nhất một bước có số tiền"
    step_id, amount = editable[0]
    new_amount = amount - 10_000 if amount > 10_000 else amount + 10_000
    before = balances(api)
    status, edited = api(
        "minh", "POST", f"/roadmap/steps/{step_id}/edit", {"version": new, "amount_vnd": new_amount}
    )
    assert status == 200, edited
    schema_validator(f"{BLOCKS}/roadmap.schema.json", edited)
    d = edited["data"]
    assert d["version"] == new + 1 and d["status"] == "active" and d["based_on_version"] == new
    assert d["reason"]["code"] == "step_edited"
    assert [s["amount_vnd"] for p in d["phases"] for s in p["steps"] if s["step_id"] == step_id] == [
        new_amount
    ]
    assert balances(api) == before  # sửa bước chỉ lưu phiên bản, không đổi số dư
    status, versions = api("minh", "GET", "/roadmap/versions")
    by_version = {v["version"]: v for v in versions["versions"]}
    assert by_version[new + 1]["status"] == "active" and by_version[new]["status"] == "superseded"
    # sửa lên bản không còn active bị từ chối (đọc lại lộ trình rồi mới sửa)
    status, body = api(
        "minh", "POST", f"/roadmap/steps/{step_id}/edit", {"version": new, "amount_vnd": amount}
    )
    assert (status, code(body)) == (409, "ROADMAP_VERSION_CONFLICT")
    assert "�" not in body["error"]["message"]  # thông điệp tiếng Việt không bị hỏng mã hóa


def test_13_giu_ban_cu_thi_ban_cho_chon_bi_bo(api, gw, schema_validator):
    from conftest import reset_account

    reset_account(api, "minh")
    new = propose_from_active(api, gw, schema_validator)["version"]
    status, kept = api("minh", "POST", f"/roadmap/versions/{new}/decision", {"decision": "keep_previous"})
    assert status == 200, kept
    assert kept["data"]["version"] == new and kept["data"]["status"] == "discarded"  # trả bản đã bỏ để giao diện hiện trạng thái
    status, versions = api("minh", "GET", "/roadmap/versions")
    by_version = {v["version"]: v for v in versions["versions"]}
    assert by_version[new]["status"] == "discarded" and by_version[new - 1]["status"] == "active"
    assert "proposed_version" not in versions
    status, body = api("minh", "POST", f"/roadmap/versions/{new}/decision", {"decision": "adopt"})
    assert (status, code(body)) == (409, "ROADMAP_VERSION_CONFLICT")
    assert "�" not in body["error"]["message"]
    reset_account(api, "minh")  # trả minh về v1, v2 ban đầu cho các test sau


# --- 3. tool qua Gateway ------------------------------------------------------------------------------------------------------
def test_14_gateway_co_nam_tool_moi(gw):
    names = set(gw("minh").tool_names())
    assert NEW_TOOLS <= names, NEW_TOOLS - names


def test_15_optimize_allocation_qua_gateway_chay_that_proxy_ledger_sang_forecast(gw, schema_validator):
    t0 = time.perf_counter()
    reply = gw("minh").call("planner___optimize_allocation", {})
    elapsed = time.perf_counter() - t0
    assert not reply.is_error and reply.status == "OK", reply.text
    schema_validator(f"{TOOLS}/planner.results.schema.json#/$defs/OptimizeAllocationResult", reply.data)
    d = reply.data["data"]
    assert d["status"] in {"optimal", "relaxed", "infeasible"}
    assert (
        sum(line["proposed_monthly_vnd"] for line in d["lines"]) + d["unallocated_vnd"]
        == d["income_monthly_vnd"]
    )  # tiền bảo toàn
    assert d["solver"]["elapsed_ms"] >= 0
    if d["status"] == "infeasible":
        assert len(d["alternatives"]) == 2
    MEASURES["optimize_allocation_minh"] = {
        "status": d["status"],
        "solver_elapsed_ms": d["solver"]["elapsed_ms"],
        "total_call_seconds": round(elapsed, 2),
        "income_monthly_vnd": d["income_monthly_vnd"],
        "unallocated_vnd": d["unallocated_vnd"],
    }
    # goals ghi đè: mục tiêu tuỳ ý cho một hũ có thật vẫn ra kết quả đúng schema
    reply = gw("minh").call(
        "planner___optimize_allocation", {"goals": [{"jar": "muc_tieu", "weight": 3}]}  # hũ goal Du lịch của ví demo (#39)
    )
    assert reply.status == "OK", reply.text
    schema_validator(f"{TOOLS}/planner.results.schema.json#/$defs/OptimizeAllocationResult", reply.data)


def test_16_get_resilience_score_va_stress_test_qua_gateway_khop_rest(gw, api, schema_validator):
    _, rest = api("minh", "GET", "/resilience")
    reply = gw("minh").call("forecast___get_resilience_score", {})
    assert reply.status == "OK", reply.text
    schema_validator(f"{TOOLS}/forecast.results.schema.json#/$defs/GetResilienceScoreResult", reply.data)
    assert reply.data["data"]["score"] == rest["data"]["score"]
    assert [c["score"] for c in reply.data["data"]["components"]] == [
        c["score"] for c in rest["data"]["components"]
    ]

    _, rest_stress = api("minh", "POST", "/resilience/stress", {"shock_id": "mat_viec_2_thang"})
    reply = gw("minh").call("forecast___stress_test", {"shock_id": "mat_viec_2_thang"})
    assert reply.status == "OK", reply.text
    schema_validator(f"{TOOLS}/forecast.results.schema.json#/$defs/StressTestResult", reply.data)
    assert reply.data["data"]["score_after"] == rest_stress["data"]["score_after"]
    assert reply.data["data"]["shortfall_vnd"] == rest_stress["data"]["shortfall_vnd"]

    bad = gw("minh").call("forecast___stress_test", {"shock_id": "khong_co_cu_soc_nay"})
    assert bad.status == "ERROR" and bad.data["code"] == "SHOCK_NOT_FOUND"
    schema_validator(f"{TOOLS}/forecast.results.schema.json#/$defs/StressTestResult", bad.data)


def test_17_get_roadmap_qua_gateway_va_loi_khong_co_lo_trinh(gw, api, subs, schema_validator):
    from conftest import reset_account

    reset_account(api, "minh")
    reply = gw("minh").call("planner___get_roadmap", {})
    assert reply.status == "OK", reply.text
    schema_validator(f"{TOOLS}/planner.results.schema.json#/$defs/GetRoadmapResult", reply.data)
    active = reply.data["data"]["version"]
    assert active == 2 and reply.data["data"]["status"] == "active"
    new = propose_from_active(api, gw, schema_validator)["version"]  # bản chờ chọn tạo qua đúng tool save_roadmap
    proposed = gw("minh").call("planner___get_roadmap", {"version": new})
    assert proposed.status == "OK" and proposed.data["data"]["status"] == "proposed"
    schema_validator(f"{TOOLS}/planner.results.schema.json#/$defs/GetRoadmapResult", proposed.data)
    latest = gw("minh").call("planner___get_roadmap", {"which": "latest"})
    assert latest.status == "OK" and latest.data["data"]["version"] == new
    still = gw("minh").call("planner___get_roadmap", {})
    assert still.status == "OK" and still.data["data"]["version"] == active  # mặc định vẫn là bản đang dùng
    missing = gw("minh").call("planner___get_roadmap", {"version": 99})
    assert missing.status == "ERROR" and missing.data["code"] == "ROADMAP_NOT_FOUND"
    # Lan gửi user_id của Minh: interceptor ghi đè bằng danh tính của Lan, nên Lan không thấy lộ trình của Minh
    sneaky = gw("lan").call("planner___get_roadmap", {"user_id": subs["minh"]})
    assert sneaky.status == "ERROR" and sneaky.data["code"] == "ROADMAP_NOT_FOUND"
    lan_score = gw("lan").call("forecast___get_resilience_score", {"user_id": subs["minh"]})
    minh_score = gw("minh").call("forecast___get_resilience_score", {})
    assert lan_score.status == "OK" and minh_score.status == "OK"
    assert lan_score.data["data"]["components"] != minh_score.data["data"]["components"]  # số của Lan, không phải của Minh


def test_18_save_roadmap_chay_lai_suitability_va_khong_luu_ban_vi_pham(gw, api, schema_validator):
    from conftest import reset_account

    reset_account(api, "minh")
    n_before = len(api("minh", "GET", "/roadmap/versions")[1]["versions"])
    # đề xuất dồn toàn bộ hũ Nghĩa vụ (hũ trả nghĩa vụ thiết yếu; ví demo của issue #39 gộp Hóa đơn vào đây) sang hũ goal Du lịch khi
    # nghĩa vụ chưa trả: luật obligations_first phải chặn
    draft = {
        "reason_code": "user_request",
        "feasibility": "on_track",
        "based_on_version": 2,
        "goals": [],
        "alternatives": [],
        "phases": [
            {
                "phase_id": "p1",
                "title": "Thử",
                "start_date": "2026-11-21",
                "end_date": "2026-12-05",
                "steps": [
                    {
                        "step_id": "rut_tien_lon",
                        "kind": "set_aside",
                        "title": "Dành toàn bộ hũ Nghĩa vụ cho Du lịch",
                        "reason": "Thử bước vượt khả năng.",
                        "amount_vnd": demo_balances("minh")["nghia_vu"],
                        "jar_code": "nghia_vu",
                        "to_jar_code": "muc_tieu",
                    }
                ],
            }
        ],
    }
    reply = gw("minh").call("planner___save_roadmap", draft)
    schema_validator(f"{TOOLS}/planner.results.schema.json#/$defs/SaveRoadmapResult", reply.data)
    assert reply.status == "ERROR" and reply.data["code"] == "ROADMAP_INVALID", reply.text
    assert len(api("minh", "GET", "/roadmap/versions")[1]["versions"]) == n_before  # không lưu gì
    MEASURES["save_roadmap_invalid"] = {"code": reply.data["code"], "message": reply.data["message"]}


# --- 4. phân hũ tự động -------------------------------------------------------------------------------------------------------
def record_transfer(api, counterparty: str, note: str, amount: int = 85_000) -> str:
    """Chi cho đối tác (chưa chọn hũ) qua đường ghi sẵn có: /confirmations rồi /actions (không có đường tắt)."""
    params = {
        "kind": "expense",
        "amount_vnd": amount,
        "tx_type": "transfer_person",
        "counterparty": counterparty,
        "client_ref": uuid.uuid4().hex[:24],
    }
    if note:
        params["note"] = note
    status, conf = api("minh", "POST", "/confirmations", {"tool": "record_transaction", "params": params})
    assert status == 200, conf
    status, receipt = api(
        "minh",
        "POST",
        "/actions",
        {
            "tool": "record_transaction",
            "params": conf["params"],
            "confirm_token": conf["confirm_token"],
        },
    )
    assert status == 200, receipt
    assert receipt["data"]["jars_after"][0]["code"] == UNCLASSIFIED  # ghi xong nằm ở Chưa phân loại
    return receipt["data"]["reference_id"]


def find_tx(api, tx_id: str) -> dict:
    status, body = api("minh", "GET", "/transactions?limit=20")
    assert status == 200, body
    return next(t for t in body["transactions"] if t["id"] == tx_id)


def review_ids(api, schema_validator, mode: str = "review") -> dict[str, dict]:
    status, block = api("minh", "GET", f"/review?mode={mode}&limit=50")
    assert status == 200, block
    schema_validator(f"{BLOCKS}/review_list.schema.json", block)
    schema_validator.openapi("ReviewListResponse", block)
    assert block["data"]["mode"] == mode
    return {i["transaction_id"]: i for i in block["data"]["items"]}


def wait_processed(api, schema_validator, tx_id: str, *, wait: float = CLASSIFY_WAIT_SECONDS):
    """Poll thưa (3 giây) tới khi Lambda phân loại đã xử lý giao dịch: có hũ, hoặc nằm trong danh sách hỏi gộp kèm gợi ý hay dấu vết
    phân loại (một khoản vừa ghi cũng nằm trong danh sách hỏi gộp nhưng chưa có gợi ý). Trả (giao dịch, giây)."""
    t0 = time.perf_counter()
    while True:
        tx = find_tx(api, tx_id)
        elapsed = time.perf_counter() - t0
        if tx["jar"] != UNCLASSIFIED:
            return tx, elapsed
        asked = review_ids(api, schema_validator, "daily_ask").get(tx_id)
        if asked and (asked["suggestions"] or "classified_by" in asked or "confidence" in asked):
            return tx, elapsed  # đã xử lý nhưng chưa đủ tin cậy: ở lại Chưa phân loại kèm gợi ý (khoản chưa xử lý thì chưa có gợi ý)
        if elapsed > wait:
            pytest.fail(f"giao dịch {tx_id} chưa được phân loại sau {wait:.0f} giây: {tx}")
        time.sleep(3)


def assign(api, tx_id: str, jar: str, remember: str):
    params = {"transaction_id": tx_id, "jar": jar, "remember": remember}
    status, conf = api("minh", "POST", "/confirmations", {"tool": "assign_jar", "params": params})
    assert status == 200, conf
    status, receipt = api(
        "minh",
        "POST",
        "/actions",
        {"tool": "assign_jar", "params": conf["params"], "confirm_token": conf["confirm_token"]},
    )
    assert status == 200, receipt
    return receipt


def other_jar(api, current: str, amount: int) -> str:
    """Một hũ thật khác hũ hiện tại, đủ tiền (hũ có nhiều tiền nhất)."""
    jars = {c: b for c, b in balances(api).items() if c not in {current, UNCLASSIFIED}}
    code_, bal = max(jars.items(), key=lambda kv: kv[1])
    assert bal >= amount
    return code_


def test_19_chuyen_cho_doi_tac_moi_duoc_phan_loai_trong_60_giay(api, schema_validator):
    name = f"Tran Quoc Bao {uuid.uuid4().hex[:6]}"  # đối tác chưa từng gặp (sinh lúc chạy)
    tx_id = record_transfer(api, name, "tien com trua")
    tx, elapsed = wait_processed(api, schema_validator, tx_id)
    assert elapsed <= CLASSIFY_WAIT_SECONDS
    items = review_ids(api, schema_validator)
    if tx["jar"] != UNCLASSIFIED:
        # tự gán: hoặc tin cậy cao (không còn cờ), hoặc tin cậy vừa (cờ xem lại và có trong "Xem lại")
        assert tx["needs_review"] == (tx_id in items)
        if tx_id in items:
            assert items[tx_id]["tier"] == "review" and items[tx_id]["current_jar"]["code"] == tx["jar"]
        outcome = "auto" if not tx["needs_review"] else "review"
    else:
        asks = review_ids(api, schema_validator, "daily_ask")
        assert asks[tx_id]["tier"] == "ask" and len(asks[tx_id]["suggestions"]) <= 2
        outcome = "ask"
    MEASURES["classify_new_counterparty"] = {
        "seconds_to_processed": round(elapsed, 1),
        "outcome": outcome,
        "jar": tx["jar"],
    }


def test_20_dung_roi_luon_luon_cho_nguoi_nay_thi_giao_dich_ke_tiep_tu_vao_dung_hu(api, schema_validator):
    name = f"Le Thi Hoa {uuid.uuid4().hex[:6]}"
    first = record_transfer(api, name, "tien com trua")
    tx, _ = wait_processed(api, schema_validator, first)
    target = tx["jar"] if tx["jar"] != UNCLASSIFIED else other_jar(api, UNCLASSIFIED, 85_000)
    assign(api, first, target, "always")  # "đúng rồi" (cùng hũ) hoặc gán hũ, kèm luật luôn luôn
    done = find_tx(api, first)
    assert done["jar"] == target and done["needs_review"] is False
    assert first not in review_ids(api, schema_validator)

    second = record_transfer(api, name, "")  # cùng người, không lời nhắn
    t0 = time.perf_counter()
    tx2, elapsed = wait_processed(api, schema_validator, second)
    assert tx2["jar"] == target and tx2["needs_review"] is False, tx2  # luật luôn luôn: tự gán, không hỏi
    MEASURES["classify_rule_always_same_jar"] = {"seconds": round(elapsed, 1), "jar": target}
    assert time.perf_counter() - t0 < CLASSIFY_WAIT_SECONDS


def test_21_sua_sang_hu_khac_luon_luon_thi_giao_dich_ke_tiep_cung_nguoi_tu_dung(api, schema_validator):
    """Tiêu chí 7: sửa hũ với "luôn luôn cho người này" rồi giao dịch kế tiếp cho cùng người tự vào hũ đã sửa."""
    name = f"Pham Van Nam {uuid.uuid4().hex[:6]}"
    first = record_transfer(api, name, "tien com trua")
    tx, _ = wait_processed(api, schema_validator, first)
    target = other_jar(api, tx["jar"], 85_000)  # CHỦ ĐỘNG khác hũ mà hệ thống chọn
    assert target != tx["jar"]
    receipt = assign(api, first, target, "always")
    assert receipt["data"]["tool"] == "assign_jar"
    assert find_tx(api, first)["jar"] == target

    second = record_transfer(api, name, "chuyen khoan")
    tx2, elapsed = wait_processed(api, schema_validator, second)
    assert tx2["jar"] == target, f"giao dịch kế tiếp phải vào {target}, đang ở {tx2['jar']}"
    assert tx2["needs_review"] is False
    MEASURES["classify_rule_always_correction"] = {
        "system_first_jar": tx["jar"],
        "corrected_to": target,
        "second_tx_jar": tx2["jar"],
        "seconds": round(elapsed, 1),
    }
    # luật chỉ áp cho đúng người đó: một đối tác khác không bị kéo theo
    other = record_transfer(api, f"Vo Thanh Tung {uuid.uuid4().hex[:6]}", "tien com trua")
    tx3, _ = wait_processed(api, schema_validator, other)
    if tx3["jar"] != UNCLASSIFIED and tx["jar"] != target:
        assert tx3["jar"] != target or tx3["needs_review"]


def test_22_hoi_gop_bo_qua_mot_lan_va_loi_tham_so(api, schema_validator):
    status, block = api("minh", "GET", "/review?mode=daily_ask")
    assert status == 200, block
    schema_validator(f"{BLOCKS}/review_list.schema.json", block)
    ask = block["data"]["ask"]
    assert ask["status"] in {"open", "answered", "skipped"}
    MEASURES["daily_ask_before_skip"] = {"count": block["data"]["count"], "ask": ask}
    status, out = api("minh", "POST", "/review/daily-ask/skip", {"ask_date": ask["ask_date"]})
    if status == 200:  # đã có câu hỏi gộp được lưu cho ngày này (do Lambda phân loại tạo khi một khoản chưa đủ tin cậy)
        schema_validator.openapi("ReviewAskResponse", out)
        assert out["status"] in {"skipped", "answered"}
        status, again = api("minh", "POST", "/review/daily-ask/skip", {"ask_date": ask["ask_date"]})
        assert status == 200 and again["status"] == out["status"]  # idempotent
    else:  # chưa có dòng `review_asks` (chỉ khoản đặt sẵn lúc đặt lại, chưa qua pipeline): từ chối rõ ràng
        assert (status, code(out)) == (400, "PARAMS_INVALID")
    MEASURES["daily_ask_skip_status"] = status
    status, body = api("minh", "POST", "/review/daily-ask/skip", {"ask_date": "khong-phai-ngay"})
    assert status == 400
    status, body = api("minh", "GET", "/review?mode=khong_co")
    assert status == 400
    status, body = api(None, "GET", "/review")
    assert status == 401
