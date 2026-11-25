-- Danh mục mẫu cho onboarding và Reset data. Migration 0055 cũng nạp danh mục này.
UPDATE jar_templates SET is_default = false WHERE is_default AND code NOT IN
  ('chi_hang_ngay', 'nghia_vu', 'du_phong', 'quy_don', 'muc_tieu', 'tich_luy_dai_han');
-- Experimental split (percent): 35 / 35 / 15 / 5 / 5 / 5.
INSERT INTO jar_templates (code, name, color_key, icon_key, kind, default_split_percent, is_default, sort_order, purpose) VALUES
  ('chi_hang_ngay', 'Chi hằng ngày', 'violet', 'utensils', 'spending', 35, true, 10, NULL),
  ('nghia_vu', 'Nghĩa vụ', 'slate', 'wallet', 'obligation', 35, true, 20, NULL),
  ('du_phong', 'Dự phòng', 'blue', 'shield', 'saving', 15, true, 30, 'buffer'),
  ('quy_don', 'Quỹ dồn', 'teal', 'calendar', 'saving', 5, true, 40, 'sinking'),
  ('muc_tieu', 'Mục tiêu', 'orchid', 'target', 'saving', 5, true, 50, 'goal'),
  ('tich_luy_dai_han', 'Tích lũy dài hạn', 'sky', 'piggybank', 'saving', 5, true, 60, 'long_term'),
  ('an_uong',  'Ăn uống',  'violet', 'utensils', 'spending',   25, false, 10, NULL),
  ('di_lai',   'Đi lại',   'sky',    'bus',      'spending',   10, false, 20, NULL),
  ('hoa_don',  'Hóa đơn',  'brown',  'receipt',  'spending',   30, false, 30, NULL),
  ('giai_tri', 'Giải trí', 'orchid', 'gamepad',  'spending',   10, false, 40, NULL),
  ('du_lich',  'Du lịch',  'teal',   'plane',    'saving',      5, false, 50, NULL)
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name, color_key = EXCLUDED.color_key, icon_key = EXCLUDED.icon_key,
  kind = EXCLUDED.kind, default_split_percent = EXCLUDED.default_split_percent,
  is_default = EXCLUDED.is_default, sort_order = EXCLUDED.sort_order, purpose = EXCLUDED.purpose;
