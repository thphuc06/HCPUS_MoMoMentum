"""Dùng chung cho test persona có thu nhập ngoài ví (đơn vị và local_pg): dải mục tiêu và dựng lại thành phần độ phủ từ dữ liệu bộ sinh."""

from __future__ import annotations

#: dải mục tiêu của kịch bản demo cảnh 5 (số liệu là kết quả tính, đây chỉ là khoảng chấp nhận)
BEFORE_RANGE = (0.60, 0.70)
AFTER_RANGE = (0.80, 0.90)


def coverage_facts(data, extra_expenses: int = 0, extra_income: int = 0) -> dict[str, int]:
    """Các thành phần của `app_coverage_facts` trên dữ liệu bộ sinh (cửa sổ từ ngày đầu lịch sử, như `history_start`).

    income = lương vào ví (income, salary, jar) + thu nhập ngoài ví; spend = chi dòng jar + chi dòng external; net_jar = tổng dòng jar;
    balance_end = tổng số dư mọi hũ; balance_start = balance_end - net_jar. `extra_*` là phần ngoài ví nạp thêm từ tệp."""
    tx = data.transactions
    income = sum(
        t.amount_vnd
        for t in tx
        if t.kind == "income" and t.tx_type == "salary" and t.funding_source == "jar"
    )
    income += sum(t.amount_vnd for t in tx if t.kind == "income" and t.funding_source == "external")
    spend = sum(
        -t.amount_vnd for t in tx if t.kind == "expense" and t.funding_source in ("jar", "external")
    )
    net_jar = sum(t.amount_vnd for t in tx if t.funding_source == "jar")
    end = sum(j.balance_vnd for j in data.jars) + sum(data.system_balances.values())
    return {
        "income_vnd": income + extra_income,
        "spend_vnd": spend + extra_expenses,
        "balance_start_vnd": end - net_jar,
        "balance_end_vnd": end,
    }
