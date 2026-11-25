-- 0058_sinking_commitments: khoản cần của hũ Quỹ dồn (lộ trình docs/plan/default-six-jars-rollout.md, Bước 2 và 3). Không sửa 0001
-- tới 0057 (migrator kiểm checksum). Chạy sau 0057 (cần cột purpose và các hàm *_with_purpose).
--
-- * jars.sinking_items (jsonb, mặc định mảng rỗng): các khoản cần của một hũ sinking (tên, số tiền, ngày cần). Ví cũ nhận mảng rỗng;
--   chỉ hũ purpose sinking được có phần tử.
-- * Hàm đọc mới app_get_jar_state_with_commitments (bọc app_get_jar_state_with_purpose, thêm sinking_items).
-- * Thay app_get_overview_with_purpose, app_get_jar_detail_with_purpose của 0057 (cùng chữ ký, cùng kiểu trả về): thêm khóa
--   sinking_items khi mảng không rỗng.
--
-- Quy ước như 0005 tới 0057 (db/README.md): chạy bằng secret MASTER, một transaction, tách bằng dòng "-- @@", hàm đọc
-- SECURITY INVOKER tự đặt app.user_id. Không viết dấu hai chấm dính liền chữ cái hoặc gạch dưới (kể cả trong chú thích).

-- One sinking jar can hold multiple dated commitments. Existing wallets default to an empty list.
ALTER TABLE jars ADD COLUMN sinking_items jsonb NOT NULL DEFAULT '[]'::jsonb
  CHECK (
    jsonb_typeof(sinking_items) = 'array'
    AND (sinking_items = '[]'::jsonb OR purpose IS NOT DISTINCT FROM 'sinking')
  );
-- @@
CREATE FUNCTION app_get_jar_state_with_commitments(p_user_id text)
RETURNS TABLE (
  clock_offset_days integer,
  code text, name text, color_key text, icon_key text, balance_vnd numeric, split_percent numeric,
  sort_order smallint, kind text, system_role text, goal_vnd numeric, goal_date date, purpose text, sinking_items jsonb
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT s.*, j.sinking_items
    FROM app_get_jar_state_with_purpose(p_user_id) s
    LEFT JOIN jars j ON j.user_id = p_user_id AND j.code = s.code
    ORDER BY s.sort_order, s.code;
END
$$;
-- @@
CREATE OR REPLACE FUNCTION app_get_overview_with_purpose(p_user_id text, p_now timestamptz, p_tz text)
RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_data jsonb := app_get_overview(p_user_id, p_now, p_tz);
  v_jars jsonb;
BEGIN
  SELECT coalesce(jsonb_agg(
    item.jar || jsonb_strip_nulls(jsonb_build_object(
      'purpose', j.purpose, 'sinking_items', NULLIF(j.sinking_items, '[]'::jsonb)
    ))
    ORDER BY item.ordinality
  ), '[]'::jsonb)
  INTO v_jars
  FROM jsonb_array_elements(v_data->'jars') WITH ORDINALITY AS item(jar, ordinality)
  LEFT JOIN jars j ON j.user_id = p_user_id AND j.code = item.jar->>'code';
  RETURN jsonb_set(v_data, '{jars}', v_jars);
END
$$;
-- @@
CREATE OR REPLACE FUNCTION app_get_jar_detail_with_purpose(
  p_user_id text, p_jar_code text, p_now timestamptz, p_tz text
)
RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_data jsonb := app_get_jar_detail(p_user_id, p_jar_code, p_now, p_tz);
  v_metadata jsonb;
BEGIN
  SELECT jsonb_strip_nulls(jsonb_build_object(
    'purpose', j.purpose, 'sinking_items', NULLIF(j.sinking_items, '[]'::jsonb)
  )) INTO v_metadata FROM jars j WHERE j.user_id = p_user_id AND j.code = p_jar_code;
  IF v_data->'jar' IS NOT NULL AND v_metadata IS NOT NULL THEN
    v_data := jsonb_set(v_data, '{jar}', (v_data->'jar') || v_metadata);
  END IF;
  RETURN v_data;
END
$$;
-- @@
REVOKE ALL ON FUNCTION app_get_jar_state_with_commitments(text) FROM PUBLIC;
-- @@
GRANT EXECUTE ON FUNCTION app_get_jar_state_with_commitments(text) TO yofina_app;
