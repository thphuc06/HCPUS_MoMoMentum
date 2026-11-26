"""Cảnh 4 trên ví demo 8 hũ (issue #39, lỗi thấy sau deploy đợt 3): nạp `minh_sao_ke_2_tuan.csv` thì cả 32 dòng phải tự chọn sẵn hũ Ăn
uống, như trên ví 7 hũ cũ.

Trên app (26/11, job 875e407f…) 25 dòng tự thêm, 7 dòng (6 Circle K, 1 Bách Hóa Xanh) vào "cần duyệt" với `jar_source` `type_map` và độ tin
cậy hũ 0,65 = `review_min_confidence`: đúng nhánh "bảng loại giao dịch và đề xuất hũ của model bất đồng" của `yofina_ingest.classify`. Lượt
gắn nhãn của model thấy hũ Chi hằng ngày trong danh sách hũ nên đề xuất hũ đó cho cửa hàng tiện lợi, siêu thị, trong khi loại nó gắn
(đi chợ, siêu thị) có hũ riêng Ăn uống trên ví. Hai đoán cùng một loại (hũ chung của chính loại đó) nên không còn bị coi là bất đồng.

Đường nạp thật như `test_change_flow.py` (REST `/ingest/*`, worker, `confirm_rows` trên PostgreSQL cục bộ). Bedrock giả đóng vai lượt gắn
nhãn: đề xuất Chi hằng ngày cho hai đối tác đó khi ví có hũ này (như model trên app), Ăn uống cho các dòng còn lại; embedding luôn nghẽn.
"""

from __future__ import annotations

from typing import Any

import pytest
from conftest import REPO
from ledger_fakes import http_event
from test_ingest_flow import Ctx

from yofina_ledger.rest_api import handle_http

SCENE4_CSV = REPO / "data" / "personas" / "samples" / "minh_sao_ke_2_tuan.csv"
GROCERY_PARTNERS = ("Circle K", "Bách Hóa Xanh")
DAILY = "chi_hang_ngay"


class LabelingBedrock:
    """Lượt gắn nhãn CSV giả (vai `ingest_columns`, công cụ `report`): đọc từng dòng `idx | chiều | đối tác | nội dung` của lời nhắn và trả
    loại, hũ như model thật đã làm trên app. Hũ đề xuất chỉ lấy trong danh sách hũ của lời nhắc hệ thống (model chỉ thấy hũ của ví)."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def converse(self, **req: Any) -> dict[str, Any]:
        self.requests.append(req)
        system = " ".join(part.get("text", "") for part in req.get("system", []))
        has_daily = f"- {DAILY}:" in system
        text = req["messages"][0]["content"][0]["text"]
        rows = []
        for line in text.splitlines()[1:]:
            idx, _direction, rest = line.split("|", 2)
            grocery = any(p in rest for p in GROCERY_PARTNERS)
            rows.append(
                {
                    "idx": int(idx),
                    "merchant": rest.split("|")[0].strip(),
                    "is_person": False,
                    "own_account_transfer": False,
                    "tx_type": "grocery" if grocery else "food_drink",
                    "jar_code": DAILY if grocery and has_daily else ("an_uong" if "- an_uong:" in system else DAILY),
                    "jar_confidence": 0.9,
                }
            )
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"toolUse": {"toolUseId": "t", "name": "report", "input": {"rows": rows}}}],
                }
            },
            "usage": {"inputTokens": 1, "outputTokens": 1},
        }

    def invoke_model(self, **req: Any):
        from botocore.exceptions import ClientError

        raise ClientError({"Error": {"Code": "ThrottlingException", "Message": "x"}}, "InvokeModel")


def _load(env, user: str) -> tuple[Ctx, dict[str, Any], LabelingBedrock]:
    ing = Ctx(env)
    up = ing.upload(user, kind="csv", mime="text/csv")
    client = LabelingBedrock()
    ing.run_worker(up, SCENE4_CSV.read_bytes(), client)
    job = ing.job(up["job_id"], user=user)
    assert job["status"] == "review", job
    return ing, job, client


def _jar_codes(env, user: str) -> set[str]:
    return {j["code"] for j in env.svc.jars_response(user, trace_id="t" * 8)["jars"]}


def _assert_all_auto(job: dict[str, Any], jar: str) -> None:
    data = job["review"]["data"]
    rows = data["rows"]
    assert len(rows) == 32
    by_partner = {r["counterparty"]: r for r in rows}
    assert set(GROCERY_PARTNERS) <= set(by_partner)
    assert {r["suggested_jar"]["code"] for r in rows} == {jar}
    assert {r["jar_source"] for r in rows} == {"type_map"}
    assert {r["review_status"] for r in rows} == {"auto_added"}, [
        (r["counterparty"], r["jar_confidence"]) for r in rows if r["review_status"] != "auto_added"
    ]
    assert data["counts"]["auto_added"] == 32 and data["counts"]["pending"] == 0


def test_vi_demo_8_hu_32_dong_tu_vao_an_uong_xac_nhan_mot_lan(env):
    user = "sub-canh4-demo8"
    r = handle_http(http_event("POST", "/demo/reset", sub=user, groups="persona-minh"), env.svc)
    assert r["statusCode"] == 200, r
    assert {DAILY, "an_uong"} <= _jar_codes(env, user)
    ing, job, client = _load(env, user)
    # model thấy Chi hằng ngày và đề xuất nó cho hai đối tác tạp hóa (như trên app)
    assert client.requests and f"- {DAILY}:" in " ".join(p.get("text", "") for p in client.requests[0]["system"])
    _assert_all_auto(job, "an_uong")
    rows = job["review"]["data"]["rows"]
    code, receipt = ing.confirm({"job_id": job["job_id"], "rows": [{"row_id": r["row_id"]} for r in rows]}, user=user)
    assert code == 200, receipt
    with env.master() as m:
        n = m.execute(
            "SELECT count(*) FROM transactions WHERE user_id = %s AND funding_source = 'external' AND kind = 'expense' "
            "AND jar_code = 'an_uong'",
            [user],
        ).fetchone()[0]
    assert n == 32


def test_vi_7_hu_cu_giu_hanh_vi(env):
    user = "sub-canh4-legacy7"
    env.reset(user, "minh")
    assert DAILY not in _jar_codes(env, user)
    _, job, _ = _load(env, user)
    _assert_all_auto(job, "an_uong")


@pytest.mark.parametrize("with_food", [False, True], ids=["vi-3-hu", "vi-3-hu-them-an-uong"])
def test_vi_3_hu_giu_hanh_vi(env, with_food):
    user = f"canh4-three-{int(with_food)}"
    env.act(user, "update_profile", {"monthly_salary_vnd": 9_000_000, "payday_day": 5})
    if with_food:
        templates = {t["code"]: t for t in env.svc.jar_templates_response()["templates"]}
        keys = ("code", "name", "color_key", "icon_key", "kind", "split_percent", "purpose", "goal_vnd", "goal_date")
        jars = [{k: j[k] for k in keys if k in j} for j in env.svc.jars_response(user, trace_id="t" * 8)["jars"]]
        for j in jars:
            if j["code"] == DAILY:
                j["split_percent"] -= 20
        food = {k: templates["an_uong"][k] for k in keys if k in templates["an_uong"]}
        env.act(user, "save_jars", {"jars": [*jars, {**food, "split_percent": 20}]})
    assert (("an_uong" in _jar_codes(env, user)) is with_food) and DAILY in _jar_codes(env, user)
    _, job, _ = _load(env, user)
    # ví 3 hũ: mọi dòng vào Chi hằng ngày; thêm Ăn uống thì Ăn uống thắng hũ chung
    _assert_all_auto(job, "an_uong" if with_food else DAILY)


def test_tai_lai_dung_tep_khi_lan_truoc_chua_chot_thi_chi_duong_ve_lan_do(env):
    """Rời màn duyệt mà chưa xác nhận rồi tải lại đúng tệp (#39, trên app bị chặn "Tệp này đã được nạp trước đó rồi"): một nội dung tệp
    chỉ có một lần nạp còn sống (khóa khử trùng dòng tính từ băm tệp) nên lần tải sau vẫn bị từ chối, nhưng chỉ ra lần đang chờ duyệt;
    lần đó còn nguyên và chốt được. Lần đã chốt thì lần tải sau chỉ ra lần đã chốt (`done`)."""
    user = "sub-canh4-reupload"
    r = handle_http(http_event("POST", "/demo/reset", sub=user, groups="persona-minh"), env.svc)
    assert r["statusCode"] == 200, r
    ing, first, _ = _load(env, user)
    up = ing.upload(user, kind="csv", mime="text/csv")
    ing.run_worker(up, SCENE4_CSV.read_bytes(), LabelingBedrock())
    again = ing.job(up["job_id"], user=user)
    assert (again["status"], again["error_code"]) == ("rejected", "INGEST_DUPLICATE_FILE")
    assert again["duplicate_of"] == {"job_id": first["job_id"], "status": "review"}
    still = ing.job(first["job_id"], user=user)
    assert still["status"] == "review" and len(still["review"]["data"]["rows"]) == 32
    rows = still["review"]["data"]["rows"]
    code, _ = ing.confirm({"job_id": first["job_id"], "rows": [{"row_id": r["row_id"]} for r in rows]}, user=user)
    assert code == 200
    assert ing.job(up["job_id"], user=user)["duplicate_of"] == {"job_id": first["job_id"], "status": "done"}
    # tệp khác nội dung: không phải job trùng tệp nên không có duplicate_of
    other = ing.upload(user, kind="csv", mime="text/csv")
    ing.run_worker(other, b"STT,Ngay,So tien\n1,07/11/2026,1000\n", LabelingBedrock())
    assert "duplicate_of" not in ing.job(other["job_id"], user=user)
