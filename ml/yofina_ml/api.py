"""Hàm công khai của gói ML mà pipeline gọi. Chữ ký, kiểu vào và kiểu ra là HỢP ĐỒNG (`ml/README.md` mục "Giao diện");
thân hàm nằm ở `yofina_ml.forecast`.

Luồng pipeline (`pipelines/nightly`, `pipelines/event`, `gateway/tools/forecast`) chỉ import từ đây và từ
`yofina_ml.types`; test của pipeline thay hai hàm này bằng bản giả (monkeypatch), không cần thuật toán thật.
"""

from __future__ import annotations

from collections.abc import Sequence

from yofina_ml import forecast as _impl
from yofina_ml.types import ForecastInputs, ForecastResult


def forecast_user(inputs: ForecastInputs) -> ForecastResult:
    """Dự báo `inputs.horizon_days` ngày cho MỌI hũ trong `inputs.jars`.

    Mỗi hũ: chọn mô hình theo số ngày lịch sử (khởi đầu lạnh theo luật khi ngắn, hurdle theo lịch khi đủ), hiệu chỉnh khoảng
    theo ngày bằng ACI, rồi Monte Carlo số dư (cộng lịch nghĩa vụ và lương tất định) cho phân vị số dư theo ngày, ngày cạn,
    xác suất hụt trước `inputs.next_payday` và sai số chuẩn. Thuần hàm: cùng `inputs` (có `config.seed`) cho cùng kết quả;
    không I/O, không đồng hồ hệ thống. `config.seed` là hạt giống gốc: hạt của từng hũ suy ra từ (seed, ngày gốc, mã hũ), nên
    hai lần chạy cùng seed nhưng khác số dư hoặc lịch dùng chung dãy ngẫu nhiên ("common random numbers", dùng cho what-if).

    Bảo đảm (đã kiểm bằng `yofina_ml.contract.check_result`): `result.jars` cùng thứ tự `inputs.jars`; mỗi hũ đúng
    `horizon_days` dòng ngày bắt đầu từ `app_date + 1`; bất biến phân vị của `DayQuantiles`; `p_shortfall is None` khi và chỉ
    khi `show_probability` sai; `run.is_initial_estimate` đúng khi `run.history_days < config.cold_start_min_days`, khi đó
    `confidence_label` là low và `show_probability` sai ở mọi hũ. `show_probability` cũng sai khi hũ có ít ngày lịch sử hơn
    `probability_min_history_days` của loại chuỗi (hiệu chỉnh, BR-31); khi đó vẫn có `status` và `confidence_band`.
    """
    return _impl.forecast_user(inputs)


def update_forecast(
    inputs: ForecastInputs,
    previous: ForecastResult,
    jar_codes: Sequence[str],
) -> ForecastResult:
    """Chỉnh nhanh theo sự kiện (< 1 phút): tính lại Monte Carlo cho các hũ trong `jar_codes` trên phân phối chi tiêu ngày
    ĐÃ CÓ của `previous` (không fit lại mô hình, không chạy lại ACI), với số dư, lịch nghĩa vụ và lương mới trong `inputs`.

    Phân phối đã có được đọc từ `previous.run.params["jar_state"]` (do `forecast_user` ghi); thiếu thì dựng từ ba phân vị
    chi tiêu ngày của `previous` (kém chính xác hơn). Trả `ForecastResult` CHỈ gồm các hũ trong `jar_codes` (cùng thứ tự
    `jar_codes`); `run` kế thừa `model` của `previous` và cập nhật `app_date`. Hũ không có trong `previous` thì ném `KeyError`
    (pipeline rơi về `forecast_user` đầy đủ). Thuần hàm như `forecast_user`.
    """
    return _impl.update_forecast(inputs, previous, jar_codes)


def runout_date_shown(result: ForecastResult, jar_code: str) -> bool:
    """Có nên nêu NGÀY cạn (`JarSummary.runout_date`) của hũ này không.

    Sai khi hiệu chỉnh bật `recalibrate` (#25) và hũ là hũ thưa (trừ hũ nghĩa vụ): ngày cạn của hũ thưa sai trung bình 5-6
    ngày trên backtest, nên bên dùng hiện "có thể cạn trước ngày lương" kèm `p_shortfall` (khi `show_probability`) thay cho
    một ngày cụ thể. Đọc từ `result.run.params["show_runout_date"]` ({mã hũ: bool}); kết quả cũ hoặc công tắc tắt không có
    khóa đó thì luôn đúng (như trước). `runout_date` vẫn được ghi như cũ để không vỡ bên dùng chưa đọc cờ này.
    """
    shown = (result.run.params or {}).get("show_runout_date") or {}
    return bool(shown.get(jar_code, True))
