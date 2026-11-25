"""Cảnh 4 chạy thật (issue #22), đầu cuối offline: tệp sao kê "hai tuần gần nhất" -> bộ đọc CSV -> bộ phân loại KHÔNG có model -> mọi
dòng tự vào hũ Ăn uống -> ghép vào lịch sử 120 ngày của `minh` -> PELT (`change_defaults.json`) xác nhận điểm gãy.

Không gọi AWS: model và embedding là Bedrock giả LUÔN lỗi (nghẽn), nên mọi quyết định hũ phải đến từ đường tất định của bộ phân loại.
Kho nhãn là nhãn seed của persona mà đặt lại demo nạp (`classify_seed.apply_seed_labels`), tra khớp chính xác như
`app_find_labeled_exact`."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pytest
from botocore.exceptions import ClientError
from ingest_helpers import REPO, FakeBedrock, FakeLabelStore, make_gateway
from yofina_classify.model import ExactLabel
from yofina_ingest import extract as ex
from yofina_ingest.context import eval_context

from personas import generate
from yofina_core.ingest import IngestSettings
from yofina_core.pii import PiiPolicy
from yofina_ledger.classify_seed import load_seed_set
from yofina_ml import change as ch
from yofina_ml.backtest.change_calibration import persona_daily_spend

ANCHOR = date(2026, 11, 21)  # ngày neo demo (YOFINA_DEMO_ANCHOR_DATE)
NAME = "minh_sao_ke_2_tuan.csv"
DATA_CSV = REPO / "data" / "personas" / "samples" / NAME
PUBLIC_CSV = REPO / "frontend" / "public" / "samples" / NAME
USER = "sub-giamkhao1"


def minh_context(store: FakeLabelStore):
    """Ngữ cảnh nạp như worker dựng cho một tài khoản persona `minh` vừa đặt lại: hũ của persona, bảng loại giao dịch của seed, chính
    sách che PII theo người nhận và tên hiển thị, kho nhãn của người dùng."""
    d = generate("minh", anchor=ANCHOR)
    c = eval_context(ANCHOR)
    c.jars = [
        {"code": j.code, "name": j.name, "color_key": j.color_key, "icon_key": j.icon_key, "kind": j.kind}
        for j in d.jars
        if j.kind != "system"
    ]  # fmt: skip
    c.policy = PiiPolicy.build(keep=[p.name for p in d.payees], self_names=[d.display_name])
    c.user_id, c.store, c.tz = USER, store, ZoneInfo("Asia/Ho_Chi_Minh")
    return c


def seed_label_store(jar_codes: set[str]) -> FakeLabelStore:
    """Nhãn seed của `minh` (chỉ hũ người dùng có, như `apply_seed_labels`), tra theo chuỗi đã chuẩn hóa."""
    store = FakeLabelStore()
    seed = load_seed_set("minh")
    assert seed is not None
    for i, lab in enumerate(x for x in seed.labels if x.jar_code in jar_codes):
        store.exact.setdefault(lab.text_norm, []).append(ExactLabel(lab.jar_code, "seed", i))
    return store


def throttled_gateway():
    throttle = ClientError({"Error": {"Code": "ThrottlingException", "Message": "x"}}, "Converse")
    client = FakeBedrock([throttle])
    client.embed_error = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "x"}}, "InvokeModel"
    )
    return make_gateway(client), client


def test_sao_ke_canh_4_tu_vao_an_uong_khong_can_model_va_pelt_xac_nhan():
    store = seed_label_store({j.code for j in generate("minh", anchor=ANCHOR).jars})
    gw, client = throttled_gateway()
    res = ex.extract_rows(
        DATA_CSV.read_bytes(),
        filename=NAME,
        content_type="text/csv",
        ctx=minh_context(store),
        gateway=gw,
    )
    rows = res.candidates
    # bộ đọc CSV nhận đủ cột bằng bảng tên cột; mọi dòng là khoản chi đọc được
    assert rows and res.dropped == []
    assert client.requests and res.warnings[0].startswith(
        "labels_unavailable"
    )  # model có được gọi nhưng lỗi
    assert all(c.kind == "expense" and c.amount_vnd and c.amount_vnd > 0 for c in rows)
    # không dòng nào phải hỏi: mọi dòng tự chọn sẵn vào Ăn uống, không cần model hay embedding
    assert [(c.jar_code, c.auto_add) for c in rows] == [("an_uong", True)] * len(rows)
    assert client.embed_requests == []

    # hai tuần gần nhất tính từ ngày neo (tuần mới nhất kết thúc hôm qua)
    assert {c.app_date for c in rows} <= {ANCHOR - timedelta(days=k) for k in range(1, 15)}
    assert {(ANCHOR - timedelta(days=1) - c.app_date).days // 7 for c in rows} == {0, 1}

    # không trùng khoản chi đã seed: bộ khử trùng chỉ so giao dịch cùng số tiền lệch không quá cửa sổ ngày
    window = IngestSettings().ingest_dedupe_window_days
    seeded = [
        (ANCHOR - timedelta(days=t.days_ago), abs(t.amount_vnd))
        for t in generate("minh", anchor=ANCHOR).transactions
        if t.kind == "expense"
    ]
    clashes = [
        (c.app_date, c.amount_vnd)
        for c in rows
        for day, amount in seeded
        if amount == c.amount_vnd and abs((day - c.app_date).days) <= window
    ]
    assert clashes == []

    # ghép vào lịch sử 120 ngày của minh: PELT với tham số hiện tại xác nhận mức mới của hai tuần cuối
    params = ch.load_params()
    daily = persona_daily_spend("minh", ANCHOR)["an_uong"]
    assert (
        ch.detect_confirmed(ch.prepare_weekly(daily, params), params) is None
    )  # lịch sử không có điểm gãy cài sẵn
    shifted = daily.copy()
    for c in rows:
        shifted[len(shifted) - (ANCHOR - c.app_date).days] += c.amount_vnd
    series = ch.prepare_weekly(shifted, params)
    hit = ch.detect_confirmed(series, params)
    assert hit is not None and hit.direction == "up"
    assert hit.weeks_held == 2 and hit.change_index == series.n_weeks - 2


@pytest.fixture(scope="module")
def generator():
    path = REPO / "data" / "personas" / "samples" / "make_scene4_csv.py"
    spec = importlib.util.spec_from_file_location("make_scene4_csv", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.modules.pop(spec.name, None)


def test_tep_da_commit_dung_la_dau_ra_cua_bo_sinh_va_ban_cong_khai_cung_noi_dung(generator):
    """Không sửa tay tệp: hai bản (cho repo và cho trang web giám khảo tải về) là đúng đầu ra của bộ sinh ở ngày neo."""
    out = generator.generate(ANCHOR)
    assert DATA_CSV.read_bytes() == out.data
    # bản công khai có thể bị git đổi xuống dòng khi checkout (không có luật -text cho thư mục frontend): so nội dung
    assert PUBLIC_CSV.read_bytes().replace(b"\r\n", b"\n") == out.data.replace(b"\r\n", b"\n")
    assert out.factor <= 2.5  # mục tiêu của issue #22
