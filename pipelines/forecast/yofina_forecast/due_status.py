"""Trạng thái hiển thị của một hũ từ kết quả dự báo và các khoản đến hạn trước lương (#39, BR-22): một định nghĩa cho mọi nơi hiện
trạng thái đủ/sát/hụt.

Xác suất hụt của engine ML (và trạng thái suy từ nó) chỉ xét các ngày TRƯỚC ngày lương. Khoản đến hạn ĐÚNG ngày lương thuộc "trước lương"
và trả bằng số dư trước khi lương về (`yofina_core.schedule.due_before_payday`, `obligation_window`), nên một khoản như vậy lớn hơn số dư
trước lương làm danh sách khoản đến hạn có khoản thiếu trong khi trạng thái của engine vẫn là "đủ". Hũ hụt tới kỳ lương theo
`short_by_payday` thì trạng thái hiển thị là hụt và không hiện xác suất của engine (con số đó nói ngược lại).

Dùng ở hai chỗ: thẻ what-if (`scenario`) và lần chạy dự báo thường trước khi ghi (`runner`, `with_due_status`), nên khối dự báo, Tổng
quan, chip trạng thái và bản gọn cho agent (đều đọc tóm tắt đã ghi) cùng một trạng thái. Mô phỏng Monte Carlo không đổi.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from yofina_core.schedule import obligation_window
from yofina_ml.types import ForecastInputs, ForecastResult, JarForecast, JarInput


def events_payload(jar: JarInput, *, include_original_dates: bool = False) -> list[dict[str, Any]]:
    """Mốc của hũ (khoản ra, khoản vào) dạng khối dự báo, theo ngày rồi nghĩa vụ trước lương rồi nhãn. `include_original_dates`: kèm
    ngày đến hạn gốc của khoản quá hạn (dự báo trừ vào ngày đầu)."""
    out: list[dict[str, Any]] = []
    for f in (*jar.outflows, *jar.inflows):
        item: dict[str, Any] = {
            "date": f.date.isoformat(),
            "kind": f.kind,
            "label": f.label,
            "amount_vnd": f.amount_vnd,
        }
        if include_original_dates and f.original_due_date is not None:
            item["original_due_date"] = f.original_due_date.isoformat()
        if f.amount_max_vnd is not None and f.amount_max_vnd > f.amount_vnd:
            item["amount_max_vnd"] = f.amount_max_vnd
        out.append(item)
    out.sort(key=lambda e: (e["date"], 0 if e["kind"] == "obligation" else 1, e["label"]))
    return out


def runs_out_by_payday(jf: JarForecast) -> bool:
    """Số dư P50 chạm ngưỡng cạn TRƯỚC hoặc ĐÚNG ngày lương kế. Xác suất của engine không xét ngày lương, nên hũ cạn ngay ngày lương (một
    khoản đến hạn ngày đó lớn hơn số dư cộng phần lương về hũ) có xác suất "trước kỳ lương" bằng 0 mà vẫn cạn."""
    s = jf.summary
    return s.runout_date is not None and s.runout_date <= s.payday_date


def due_window(inputs: ForecastInputs, jf: JarForecast) -> dict[str, Any]:
    """Khoản đến hạn trước lương (gồm ngày lương) của hũ của `jf` và khoản thiếu đầu tiên theo số dư P50 của chính dự báo đó
    (`yofina_core.schedule.obligation_window`: khoản đến hạn đúng ngày lương trả bằng số dư trước khi lương ngày đó về)."""
    jar = next(j for j in inputs.jars if j.code == jf.summary.jar_code)
    return obligation_window(
        events_payload(jar, include_original_dates=True),
        jf.summary.payday_date.isoformat(),
        {d.date.isoformat(): d.balance_p50_vnd for d in jf.days},
        opening_balance_vnd=jar.balance_vnd,
    )


def short_by_payday(jf: JarForecast, window: Mapping[str, Any] | None) -> bool:
    """Hụt tới kỳ lương mà xác suất của engine không thấy: hũ cạn trước hoặc đúng ngày lương, hoặc một khoản đến hạn trước lương thiếu
    tiền (`window`, từ `due_window`)."""
    return runs_out_by_payday(jf) or bool(window and window.get("first_shortfall"))


def shown_status(jf: JarForecast, window: Mapping[str, Any] | None = None) -> str:
    """Trạng thái hiển thị: trạng thái của engine, trừ khi hũ hụt tới kỳ lương theo `short_by_payday` thì là hụt (cùng nghĩa "hụt trước
    kỳ lương" mà người dùng đọc cạnh ngày cạn, số dư thấp nhất và khoản thiếu đầu tiên)."""
    return "short" if short_by_payday(jf, window) else jf.summary.status


def shown_p(jf: JarForecast, window: Mapping[str, Any] | None = None) -> float | None:
    """Xác suất hụt để hiển thị. Bỏ khi hũ hụt mà engine không thấy (`short_by_payday` trong khi trạng thái của engine chưa là hụt): con
    số của engine (thường 0%) sẽ nói ngược với trạng thái hụt; khi đó chỉ nói ngày cạn hoặc khoản thiếu."""
    s = jf.summary
    if not s.show_probability or s.p_shortfall is None:
        return None
    if short_by_payday(jf, window) and s.status != "short":
        return None
    return round(float(s.p_shortfall), 4)


def with_due_status(inputs: ForecastInputs, result: ForecastResult) -> ForecastResult:
    """Kết quả dự báo với trạng thái hiển thị của từng hũ (`shown_status`, `shown_p`) trước khi ghi: hũ hụt tới kỳ lương mà engine không
    thấy thì tóm tắt ghi trạng thái hụt và không phát xác suất (ràng buộc của bảng: không phát xác suất thì không có số). Chuỗi số dư theo
    ngày, ngày cạn và mọi số của engine giữ nguyên."""
    jars = []
    for jf in result.jars:
        window = due_window(inputs, jf)
        s = jf.summary
        if shown_status(jf, window) != s.status:
            hidden = shown_p(jf, window) is None
            s = replace(
                s,
                status="short",
                show_probability=s.show_probability and not hidden,
                p_shortfall=None if hidden else s.p_shortfall,
                p_shortfall_se=None if hidden else s.p_shortfall_se,
            )
            jf = replace(jf, summary=s)
        jars.append(jf)
    return replace(result, jars=tuple(jars))
