-- Seed bảng tra bước 0 của phân loại: loại giao dịch sang hũ (không dùng ML). Dữ liệu sản phẩm, không phải dữ liệu persona.
--
-- default_jar_code là mã hũ chuẩn (khớp db/seed/jar_templates.sql); người dùng không có hũ đó thì rơi về hũ hệ thống
-- unclassified. system_role gán thẳng vào hũ hệ thống. Cả hai trống ở loại nội bộ (direction internal).
-- Cột is_person_transfer (migration 0008) đánh dấu loại "chuyển tiền cho người khác" để giao diện không đoán theo tên.
-- Nạp bằng scripts/migrate.py --seed (qua Lambda migrator, secret master). Viết lại được: ON CONFLICT DO UPDATE.
-- Mỗi câu lệnh kết thúc bằng dấu chấm phẩy, không có dấu hai chấm dính liền chữ cái.

INSERT INTO tx_type_map (tx_type, label, direction, default_jar_code, system_role, is_selectable, sort_order, is_person_transfer) VALUES
  ('food_drink',         'Ăn uống',                      'out', 'an_uong',  NULL,           true,  10, false),
  ('food_delivery',      'Giao đồ ăn',                   'out', 'an_uong',  NULL,           true,  11, false),
  ('grocery',            'Đi chợ, siêu thị',             'out', 'an_uong',  NULL,           true,  12, false),
  ('qr_food',            'Quét QR quán ăn, cà phê',      'out', 'an_uong',  NULL,           true,  13, false),
  ('ride_hailing',       'Gọi xe',                       'out', 'di_lai',   NULL,           true,  20, false),
  ('public_transport',   'Xe buýt, tàu, metro',          'out', 'di_lai',   NULL,           true,  21, false),
  ('fuel',               'Xăng xe',                      'out', 'di_lai',   NULL,           true,  22, false),
  ('qr_transport',       'Quét QR vận tải',              'out', 'di_lai',   NULL,           true,  23, false),
  ('bill_electricity',   'Tiền điện',                    'out', 'hoa_don',  NULL,           true,  30, false),
  ('bill_water',         'Tiền nước',                    'out', 'hoa_don',  NULL,           true,  31, false),
  ('bill_internet',      'Internet',                     'out', 'hoa_don',  NULL,           true,  32, false),
  ('bill_phone',         'Cước điện thoại',              'out', 'hoa_don',  NULL,           true,  33, false),
  ('phone_topup',        'Nạp điện thoại',               'out', 'hoa_don',  NULL,           true,  34, false),
  ('rent',               'Tiền thuê nhà',                'out', 'hoa_don',  NULL,           true,  35, false),
  ('subscription',       'Gói thuê bao',                 'out', 'giai_tri', NULL,           true,  40, false),
  ('entertainment',      'Giải trí',                     'out', 'giai_tri', NULL,           true,  41, false),
  ('qr_entertainment',   'Quét QR giải trí',             'out', 'giai_tri', NULL,           true,  42, false),
  ('travel',             'Du lịch',                      'out', 'du_lich',  NULL,           true,  50, false),
  ('obligation_payment', 'Trả nghĩa vụ',                 'out', 'nghia_vu', NULL,           true,  60, false),
  ('bnpl_purchase',      'Mua bằng Trả sau (mô phỏng)',  'out', NULL,       'unclassified', true,  61, false),
  ('transfer_person',    'Chuyển tiền cho người khác',   'out', NULL,       'unclassified', true,  70, true),
  ('qr_other',           'Quét QR cửa hàng khác',        'out', NULL,       'unclassified', true,  71, false),
  ('other_expense',      'Chi tiêu khác',                'out', NULL,       'unclassified', true,  99, false),
  ('salary',             'Lương',                        'in',  NULL,       'other_income', true,  100, false),
  ('friend_repay',       'Bạn trả lại tiền',             'in',  NULL,       'other_income', true,  101, false),
  ('refund',             'Hoàn tiền',                    'in',  NULL,       'other_income', true,  102, false),
  ('bank_topup',         'Nạp từ ngân hàng',             'in',  NULL,       'other_income', true,  103, false),
  ('income_other',       'Tiền vào khác',                'in',  NULL,       'other_income', true,  109, false),
  ('jar_transfer',       'Chuyển giữa các hũ',           'internal', NULL,  NULL,           false, 200, false),
  ('salary_split',       'Chia lương vào hũ',            'internal', NULL,  NULL,           false, 201, false),
  ('jar_assign',         'Gán hũ cho giao dịch',         'internal', NULL,  NULL,           false, 202, false)
ON CONFLICT (tx_type) DO UPDATE SET
  label = EXCLUDED.label,
  direction = EXCLUDED.direction,
  default_jar_code = EXCLUDED.default_jar_code,
  system_role = EXCLUDED.system_role,
  is_selectable = EXCLUDED.is_selectable,
  sort_order = EXCLUDED.sort_order,
  is_person_transfer = EXCLUDED.is_person_transfer;
