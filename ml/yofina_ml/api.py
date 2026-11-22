"""Hàm công khai của gói ML mà pipeline gọi. HIỆN CHỈ CÓ CHỮ KÝ (hợp đồng): luồng ML thay thân hàm, GIỮ nguyên
chữ ký, kiểu vào và kiểu ra. Chi tiết ngữ nghĩa ở `ml/README.md` mục "Giao diện".

Luồng pipeline (`pipelines/nightly`, `pipelines/event`, `gateway/tools/forecast`) chỉ import từ đây và từ
`yofina_ml.types`; test của pipeline thay hai hàm này bằng bản giả (monkeypatch), không cần thuật toán thật.
"""

from __future__ import annotations

from collections.abc import Sequence

from yofina_ml.types import ForecastInputs, ForecastResult


def forecast_user(inputs: ForecastInputs) -> ForecastResult:
    """Dự báo 30 ngày (hoặc `inputs.horizon_days`) cho MỌI hũ trong `inputs.jars`.

    Mỗi hũ: dự báo phân vị chi tiêu ngày (hurdle theo lịch hoặc seasonal naive, khởi đầu lạnh theo luật khi lịch sử
    ngắn), hiệu chỉnh khoảng bằng ACI, rồi Monte Carlo số dư (cộng lịch nghĩa vụ và lương tất định) cho ra phân vị số dư
    theo ngày, ngày cạn, xác suất hụt trước `inputs.next_payday` và sai số chuẩn. Thuần hàm: cùng `inputs` (có
    `config.seed`) cho cùng kết quả; không I/O, không đồng hồ hệ thống.

    Phải đảm bảo (test hợp đồng của pipeline dựa vào): `result.jars` cùng thứ tự `inputs.jars`; mỗi hũ đúng
    `horizon_days` dòng ngày bắt đầu từ `app_date + 1`; bất biến phân vị của `DayQuantiles`; `p_shortfall is None`
    khi và chỉ khi `show_probability` sai; `run.is_initial_estimate` đúng khi `run.history_days <
    config.cold_start_min_days`, khi đó `confidence_label` là low và `show_probability` sai ở mọi hũ.
    """
    raise NotImplementedError("luồng ML cài (docs/plan/phases/phase-2-vi-va-du-bao.md, luồng B)")


def update_forecast(
    inputs: ForecastInputs,
    previous: ForecastResult,
    jar_codes: Sequence[str],
) -> ForecastResult:
    """Chỉnh nhanh theo sự kiện (< 1 phút): tính lại Monte Carlo cho các hũ trong `jar_codes` trên phân vị chi tiêu
    ngày ĐÃ CÓ trong `previous` (không huấn luyện lại model, không chạy lại ACI), với số dư, lịch nghĩa vụ và lương mới
    trong `inputs`.

    Trả `ForecastResult` CHỈ gồm các hũ trong `jar_codes` (cùng thứ tự `jar_codes`); `run` kế thừa `model` của `previous`
    và cập nhật `app_date`. Hũ không có trong `previous` thì ném `KeyError` (pipeline rơi về `forecast_user` đầy đủ).
    Thuần hàm như `forecast_user`.
    """
    raise NotImplementedError("luồng ML cài (docs/plan/phases/phase-2-vi-va-du-bao.md, luồng B)")
