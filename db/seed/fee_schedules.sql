-- Seed biểu phí có cấu trúc của sản phẩm trả sau mô phỏng ("Trả sau (mô phỏng)", mã bnpl_sim).
--
-- Chỉ có MỘT khoản phí có nguồn công khai: phí dịch vụ 33.000 đồng mỗi tháng có giao dịch (nguồn ở cột source_name và
-- source_url; dẫn lại trong docs/references/links.md). effective_from là ngày nguồn được ghi nhận, không phải ngày nhà
-- cung cấp bắt đầu thu. Không bịa thêm khoản phí nào (ví dụ phí trả chậm) khi chưa có nguồn: thêm một dòng ở đây khi có
-- nguồn, kèm effective_from. Nghĩa vụ trả sau lưu fee_schedule_id của dòng đã áp dụng.
-- Nạp bằng scripts/migrate.py --seed. Viết lại được: ON CONFLICT (product_code, fee_type, effective_from) DO UPDATE.

INSERT INTO fee_schedules (
  product_code, product_label, fee_type, amount_vnd, rate_percent, period, condition_code, condition_note,
  source_name, source_url, effective_from, effective_to
) VALUES (
  'bnpl_sim', 'Trả sau (mô phỏng)', 'monthly_service_fee', 33000, NULL, 'per_month', 'month_has_transaction',
  'Tính một lần trong tháng nếu tháng đó có ít nhất một giao dịch bằng hạn mức.',
  'Biểu phí công khai của sản phẩm trả sau, dùng làm ví dụ cho sản phẩm mô phỏng',
  'https://www.momo.vn/vi-tra-sau', DATE '2026-03-31', NULL
)
ON CONFLICT (product_code, fee_type, effective_from) DO UPDATE SET
  product_label = EXCLUDED.product_label,
  amount_vnd = EXCLUDED.amount_vnd,
  rate_percent = EXCLUDED.rate_percent,
  period = EXCLUDED.period,
  condition_code = EXCLUDED.condition_code,
  condition_note = EXCLUDED.condition_note,
  source_name = EXCLUDED.source_name,
  source_url = EXCLUDED.source_url,
  effective_to = EXCLUDED.effective_to;
