-- Seed gợi ý hũ mặc định cho tài khoản mới (onboarding chỉ bắt buộc lương và ngày nhận: hệ thống tạo hũ từ bảng này).
-- Dữ liệu sản phẩm, không phải dữ liệu persona. Mã hũ khớp default_jar_code của db/seed/tx_type_map.sql.
-- Tổng default_split_percent của các dòng is_default bằng 100.
-- Nạp bằng scripts/migrate.py --seed. Viết lại được: ON CONFLICT DO UPDATE.

INSERT INTO jar_templates (code, name, color_key, icon_key, kind, default_split_percent, is_default, sort_order) VALUES
  ('an_uong',  'Ăn uống',  'violet', 'utensils', 'spending',   25, true, 10),
  ('di_lai',   'Đi lại',   'sky',    'bus',      'spending',   10, true, 20),
  ('hoa_don',  'Hóa đơn',  'brown',  'receipt',  'spending',   30, true, 30),
  ('giai_tri', 'Giải trí', 'orchid', 'gamepad',  'spending',   10, true, 40),
  ('du_lich',  'Du lịch',  'teal',   'plane',    'saving',      5, true, 50),
  ('du_phong', 'Dự phòng', 'blue',   'shield',   'saving',     15, true, 60),
  ('nghia_vu', 'Nghĩa vụ', 'slate',  'wallet',   'obligation',  5, true, 70)
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name,
  color_key = EXCLUDED.color_key,
  icon_key = EXCLUDED.icon_key,
  kind = EXCLUDED.kind,
  default_split_percent = EXCLUDED.default_split_percent,
  is_default = EXCLUDED.is_default,
  sort_order = EXCLUDED.sort_order;
