-- Bootstrap the legacy onboarding layout. Activation is owned by migration 0059.
-- Existing catalogue rows take precedence so reseeding cannot switch the active layout.
INSERT INTO jar_templates (code, name, color_key, icon_key, kind, default_split_percent, is_default, sort_order) VALUES
  ('an_uong',  'Ăn uống',  'violet', 'utensils', 'spending',   25, true, 10),
  ('di_lai',   'Đi lại',   'sky',    'bus',      'spending',   10, true, 20),
  ('hoa_don',  'Hóa đơn',  'brown',  'receipt',  'spending',   30, true, 30),
  ('giai_tri', 'Giải trí', 'orchid', 'gamepad',  'spending',   10, true, 40),
  ('du_lich',  'Du lịch',  'teal',   'plane',    'saving',      5, true, 50),
  ('du_phong', 'Dự phòng', 'blue',   'shield',   'saving',     15, true, 60),
  ('nghia_vu', 'Nghĩa vụ', 'slate',  'wallet',   'obligation',  5, true, 70)
ON CONFLICT (code) DO NOTHING;

-- Chi hằng ngày (issue #39). Migration 0059 creates its row with the colour and icon of Ăn uống. Rewrite only those two columns,
-- as the demo layout (gateway/tools/ledger/yofina_ledger/jar_layout.py). No other column, and no row before 0059 (no layout switch).
UPDATE jar_templates SET color_key = 'brown', icon_key = 'basket' WHERE code = 'chi_hang_ngay';
