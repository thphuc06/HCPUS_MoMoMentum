"""Che PII (chưa cài; không cài giả).

Guardrails không che PII trong kết quả tool và không có mẫu PII Việt Nam, nên việc che nằm ở
Lambda tool và bước nạp dữ liệu (docs/architecture/overview.md, mục "Bỏ và hoãn"): regex SĐT,
CCCD/CMND, số tài khoản, email. Module này sẽ được cài ở phase 5 (luồng nạp dữ liệu), trước khi
bất kỳ văn bản người dùng nào đi vào log, bộ nhớ dài hạn hoặc prompt.
"""
