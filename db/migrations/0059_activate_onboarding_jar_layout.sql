-- 0059_activate_onboarding_jar_layout: bật bộ ba hũ của onboarding (Chi hằng ngày, Nghĩa vụ, Dự phòng) trong danh mục jar_templates
-- (lộ trình docs/plan/default-six-jars-rollout.md, Bước 1 và 7). Không sửa 0001 tới 0058 (migrator kiểm checksum).
--
-- Thứ tự: chạy SAU 0057 và 0058 (schema tương thích) và sau khi Ledger đọc được purpose; PHẢI là migration cuối của lộ trình để bước
-- bật bộ ba tách được khỏi phần schema khi phát hành (Bước 7). Seed db/seed/jar_templates.sql không bật bộ mới.
--
-- Quy ước như 0005 tới 0058 (db/README.md): chạy bằng secret MASTER, một transaction, tách bằng dòng "-- @@", viết lại được. Không
-- viết dấu hai chấm dính liền chữ cái hoặc gạch dưới (kể cả trong chú thích).

-- Activate the three-jar onboarding layout after Ledger supports purpose.
UPDATE jar_templates SET is_default = false WHERE is_default AND code NOT IN
  ('chi_hang_ngay', 'nghia_vu', 'du_phong');
-- @@
-- Experimental split (percent): 42 / 33 / 25.
INSERT INTO jar_templates (code, name, color_key, icon_key, kind, default_split_percent, is_default, sort_order, purpose) VALUES
  ('chi_hang_ngay', 'Chi hằng ngày', 'violet', 'utensils', 'spending', 42, true, 10, NULL),
  ('nghia_vu', 'Nghĩa vụ', 'slate', 'wallet', 'obligation', 33, true, 20, NULL),
  ('du_phong', 'Dự phòng', 'blue', 'shield', 'saving', 25, true, 30, 'buffer'),
  ('quy_don', 'Quỹ dồn', 'teal', 'calendar', 'saving', 0, false, 40, 'sinking'),
  ('muc_tieu', 'Mục tiêu', 'orchid', 'target', 'saving', 0, false, 50, 'goal'),
  ('tich_luy_dai_han', 'Tích lũy dài hạn', 'sky', 'piggybank', 'saving', 0, false, 60, 'long_term'),
  ('an_uong',  'Ăn uống',  'violet', 'utensils', 'spending',   25, false, 10, NULL),
  ('di_lai',   'Đi lại',   'sky',    'bus',      'spending',   10, false, 20, NULL),
  ('hoa_don',  'Hóa đơn',  'brown',  'receipt',  'spending',   30, false, 30, NULL),
  ('giai_tri', 'Giải trí', 'orchid', 'gamepad',  'spending',   10, false, 40, NULL),
  ('du_lich',  'Du lịch',  'teal',   'plane',    'saving',      5, false, 50, NULL)
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name, color_key = EXCLUDED.color_key, icon_key = EXCLUDED.icon_key,
  kind = EXCLUDED.kind, default_split_percent = EXCLUDED.default_split_percent,
  is_default = EXCLUDED.is_default, sort_order = EXCLUDED.sort_order, purpose = EXCLUDED.purpose;
