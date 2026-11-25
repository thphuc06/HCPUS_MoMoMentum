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

import numpy as np
import pytest
from botocore.exceptions import ClientError
from ingest_helpers import REPO, FakeBedrock, FakeLabelStore, make_gateway
from yofina_classify.model import ExactLabel
from yofina_ingest import extract as ex
from yofina_ingest.context import eval_context

from personas import generate
from personas.six_jars import apply_demo_layout
from yofina_core.ingest import IngestSettings
from yofina_core.pii import PiiPolicy
from yofina_ledger.classify_seed import label_jar_pairs, load_seed_set
from yofina_ledger.jar_layout import DEMO_LAYOUT
from yofina_ml import change as ch
from yofina_ml.backtest.change_calibration import persona_daily_spend

ANCHOR = date(2026, 11, 21)  # ngày neo demo (YOFINA_DEMO_ANCHOR_DATE)
NAME = "minh_sao_ke_2_tuan.csv"
DATA_CSV = REPO / "data" / "personas" / "samples" / NAME
PUBLIC_CSV = REPO / "frontend" / "public" / "samples" / NAME
USER = "sub-giamkhao1"


def minh_data(layout: str):
    """Persona `minh` ở ngày neo: ví persona (`persona`) hoặc ví demo mà `POST /demo/reset` nạp (`demo`, issue #39)."""
    d = generate("minh", anchor=ANCHOR)
    return apply_demo_layout(d, DEMO_LAYOUT) if layout == "demo" else d


def minh_context(store: FakeLabelStore, layout: str = "persona"):
    """Ngữ cảnh nạp như worker dựng cho một tài khoản persona `minh` vừa đặt lại: hũ của ví, bảng loại giao dịch của seed, chính
    sách che PII theo người nhận và tên hiển thị, kho nhãn của người dùng."""
    d = minh_data(layout)
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
    """Nhãn seed của `minh` vào hũ của ví như `apply_seed_labels` (`classify_seed.label_jar_pairs`: hũ riêng khớp nhóm thắng hũ chung),
    tra theo chuỗi đã chuẩn hóa."""
    store = FakeLabelStore()
    seed = load_seed_set("minh")
    assert seed is not None
    for i, (lab, code) in enumerate(label_jar_pairs(seed, jar_codes)):
        store.exact.setdefault(lab.text_norm, []).append(ExactLabel(code, "seed", i))
    return store


def throttled_gateway():
    throttle = ClientError({"Error": {"Code": "ThrottlingException", "Message": "x"}}, "Converse")
    client = FakeBedrock([throttle])
    client.embed_error = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "x"}}, "InvokeModel"
    )
    return make_gateway(client), client


@pytest.fixture(scope="module", params=["persona", "demo"])
def layout(request):
    """Ví persona (như `main`) và ví demo có hũ tự thêm (issue #39): cảnh 4 phải chạy như nhau trên cả hai."""
    return request.param


@pytest.fixture(scope="module")
def extracted(layout):
    """Tệp cảnh 4 qua `extract_rows` với kho nhãn seed của `minh` và Bedrock giả luôn nghẽn: (kết quả, client giả)."""
    store = seed_label_store({j.code for j in minh_data(layout).jars})
    gw, client = throttled_gateway()
    res = ex.extract_rows(
        DATA_CSV.read_bytes(),
        filename=NAME,
        content_type="text/csv",
        ctx=minh_context(store, layout),
        gateway=gw,
    )
    return res, client


def test_sao_ke_canh_4_tu_vao_an_uong_khong_can_model_khong_trung_so_cai(extracted):
    res, client = extracted
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


@pytest.mark.parametrize("drift_days", [0, 1])
def test_pelt_xac_nhan_khi_tai_trong_ngay_dat_lai_hoac_tre_mot_ngay(extracted, drift_days):
    """Ghép các dòng vào lịch sử 120 ngày của minh: PELT với tham số hiện tại xác nhận mức chi tăng. Ngày mô phỏng đi theo ngày thật kể
    từ lần đặt lại, nên giám khảo đặt lại rồi để qua ngày mới tải thì chuỗi có thêm ngày neo (không có chi seed nào) và tuần mới nhất
    lệch một ngày so với tệp; tệp phải đủ bền cho cả lệch 1 ngày."""
    rows = extracted[0].candidates
    params = ch.load_params()
    daily = persona_daily_spend("minh", ANCHOR)["an_uong"]
    # ví demo giữ nguyên mọi dòng của hũ Ăn uống: chuỗi chi mà bộ phát hiện đọc (chi trừ tiền hũ, không gắn nghĩa vụ) y hệt
    demo_daily = np.zeros(len(daily))
    for tx in minh_data("demo").transactions:
        if (
            tx.kind == "expense" and tx.jar_code == "an_uong" and tx.funding_source == "jar"
            and tx.obligation_key is None and 1 <= tx.days_ago <= len(daily)
        ):  # fmt: skip
            demo_daily[len(daily) - tx.days_ago] += -tx.amount_vnd
    assert np.array_equal(demo_daily, daily)
    assert (
        ch.detect_confirmed(ch.prepare_weekly(daily, params), params) is None
    )  # lịch sử không có điểm gãy cài sẵn
    today = ANCHOR + timedelta(days=drift_days)
    shifted = np.concatenate([daily, np.zeros(drift_days)])  # thêm các ngày từ ngày neo tới hôm qua
    for c in rows:
        shifted[len(shifted) - (today - c.app_date).days] += c.amount_vnd
    series = ch.prepare_weekly(shifted, params)
    hit = ch.detect_confirmed(series, params)
    assert hit is not None and hit.direction == "up"
    assert hit.weeks_held >= 2
    if drift_days == 0:  # hai tuần của tệp trùng đúng hai tuần cuối
        assert hit.weeks_held == 2 and hit.change_index == series.n_weeks - 2


@pytest.fixture(scope="module")
def generator():
    """Bộ sinh tệp, nạp từ đường dẫn. Bộ sinh thêm thư mục nguồn (có `pipelines/ingest`) vào `sys.path` khi nạp; trả `sys.path` và các
    module của script về như cũ khi xong, vì `test_eval_ingest_scoring` cần `yofina_ingest` KHÔNG tìm thấy qua `sys.path`."""
    saved_path, before = list(sys.path), set(sys.modules)
    path = REPO / "data" / "personas" / "samples" / "make_scene4_csv.py"
    spec = importlib.util.spec_from_file_location("make_scene4_csv", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.path[:] = saved_path
        for name in ("make_scene4_csv", "measure_scene4_pelt", "inject_behavior_shift"):
            if name not in before:
                sys.modules.pop(name, None)


def test_tep_da_commit_dung_la_dau_ra_cua_bo_sinh_va_ban_cong_khai_cung_noi_dung(generator):
    """Không sửa tay tệp: hai bản (cho repo và cho trang web giám khảo tải về) là đúng đầu ra của bộ sinh ở ngày neo."""
    out = generator.generate(ANCHOR)
    assert DATA_CSV.read_bytes() == out.data
    # bản công khai có thể bị git đổi xuống dòng khi checkout (không có luật -text cho thư mục frontend): so nội dung
    assert PUBLIC_CSV.read_bytes().replace(b"\r\n", b"\n") == out.data.replace(b"\r\n", b"\n")
    # chủ dự án chốt 3,0 lần cho bền khi tải trễ một ngày; 3,0 chưa đủ bền thì bộ sinh lấy hệ số nhỏ nhất đủ bền, không quá 4,0
    assert 3.0 <= out.factor <= 4.0
