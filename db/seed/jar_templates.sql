-- Bootstrap the legacy onboarding layout. Activation is owned by migration 0059.
-- Existing catalogue rows take precedence so reseeding cannot switch the active layout. The one exception is the colour and icon
-- of Chi hằng ngày (issue #39) whose row migration 0059 creates with the colour and icon of Ăn uống. The upsert rewrites only
-- those two columns of that row (as the demo layout in gateway/tools/ledger/yofina_ledger/jar_layout.py), never is_default,
-- the split or the order. Before 0059 the row is added switched off, and 0059 then owns every other column.
INSERT INTO jar_templates (code, name, color_key, icon_key, kind, default_split_percent, is_default, sort_order) VALUES
  ('an_uong',  'Ăn uống',  'violet', 'utensils', 'spending',   25, true, 10),
  ('di_lai',   'Đi lại',   'sky',    'bus',      'spending',   10, true, 20),
  ('hoa_don',  'Hóa đơn',  'brown',  'receipt',  'spending',   30, true, 30),
  ('giai_tri', 'Giải trí', 'orchid', 'gamepad',  'spending',   10, true, 40),
  ('du_lich',  'Du lịch',  'teal',   'plane',    'saving',      5, true, 50),
  ('du_phong', 'Dự phòng', 'blue',   'shield',   'saving',     15, true, 60),
  ('nghia_vu', 'Nghĩa vụ', 'slate',  'wallet',   'obligation',  5, true, 70),
  ('chi_hang_ngay', 'Chi hằng ngày', 'brown', 'basket', 'spending', 42, false, 10)
ON CONFLICT (code) DO UPDATE SET color_key = EXCLUDED.color_key, icon_key = EXCLUDED.icon_key
  WHERE jar_templates.code = 'chi_hang_ngay';
