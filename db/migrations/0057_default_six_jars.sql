-- 0057_default_six_jars: mở rộng schema cho bộ hũ mặc định, chưa đổi bộ hũ đang dùng (lộ trình docs/plan/default-six-jars-rollout.md,
-- Bước 1). Không sửa 0001 tới 0056 (migrator kiểm checksum).
--
-- * jars.purpose, jar_templates.purpose (text, tùy chọn): mục đích của hũ tiết kiệm (buffer, sinking, goal, long_term); NULL với dữ
--   liệu cũ và với hũ không phải saving. jars_goal_check cho phép hũ sinking, long_term có hạn mà chưa có số tiền.
-- * Hàm đọc mới app_get_jar_state_with_purpose, app_get_overview_with_purpose, app_get_jar_detail_with_purpose bọc hàm đọc cũ và
--   thêm purpose; hàm cũ giữ nguyên để Ledger cũ chạy được trong lúc chạy xen kẽ.
-- * Bật bộ ba hũ của onboarding là việc của 0059 (migration cuối), không phải file này.
--
-- Quy ước như 0005 tới 0056 (db/README.md): chạy bằng secret MASTER, một transaction, tách bằng dòng "-- @@", hàm đọc
-- SECURITY INVOKER tự đặt app.user_id. Không viết dấu hai chấm dính liền chữ cái hoặc gạch dưới (kể cả trong chú thích).

ALTER TABLE jars ADD COLUMN purpose text CHECK (
  purpose IS NULL OR (kind = 'saving' AND purpose IN ('buffer', 'sinking', 'goal', 'long_term'))
);
-- @@
ALTER TABLE jar_templates ADD COLUMN purpose text CHECK (
  purpose IS NULL OR (kind = 'saving' AND purpose IN ('buffer', 'sinking', 'goal', 'long_term'))
);
-- @@
ALTER TABLE jars DROP CONSTRAINT jars_goal_check;
-- @@
ALTER TABLE jars ADD CONSTRAINT jars_goal_check CHECK (
  (goal_vnd IS NULL OR goal_vnd > 0)
  AND (goal_date IS NULL OR goal_vnd IS NOT NULL OR coalesce(purpose IN ('sinking', 'long_term'), false))
);
-- @@
-- Ledger opts into purpose-aware reads through new invoker functions.
CREATE FUNCTION app_get_jar_state_with_purpose(p_user_id text)
RETURNS TABLE (
  clock_offset_days integer,
  code text, name text, color_key text, icon_key text, balance_vnd numeric, split_percent numeric,
  sort_order smallint, kind text, system_role text, goal_vnd numeric, goal_date date, purpose text
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT s.*, j.purpose
    FROM app_get_jar_state(p_user_id) s
    LEFT JOIN jars j ON j.user_id = p_user_id AND j.code = s.code
    ORDER BY s.sort_order, s.code;
END
$$;
-- @@
CREATE FUNCTION app_get_overview_with_purpose(p_user_id text, p_now timestamptz, p_tz text)
RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_data jsonb := app_get_overview(p_user_id, p_now, p_tz);
  v_jars jsonb;
BEGIN
  SELECT coalesce(jsonb_agg(
    item.jar || jsonb_strip_nulls(jsonb_build_object('purpose', j.purpose))
    ORDER BY item.ordinality
  ), '[]'::jsonb)
  INTO v_jars
  FROM jsonb_array_elements(v_data->'jars') WITH ORDINALITY AS item(jar, ordinality)
  LEFT JOIN jars j ON j.user_id = p_user_id AND j.code = item.jar->>'code';
  RETURN jsonb_set(v_data, '{jars}', v_jars);
END
$$;
-- @@
CREATE FUNCTION app_get_jar_detail_with_purpose(
  p_user_id text, p_jar_code text, p_now timestamptz, p_tz text
)
RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_data jsonb := app_get_jar_detail(p_user_id, p_jar_code, p_now, p_tz);
  v_purpose text;
BEGIN
  SELECT j.purpose INTO v_purpose FROM jars j WHERE j.user_id = p_user_id AND j.code = p_jar_code;
  IF v_purpose IS NOT NULL THEN
    v_data := jsonb_set(v_data, '{jar,purpose}', to_jsonb(v_purpose));
  END IF;
  RETURN v_data;
END
$$;
-- @@
REVOKE ALL ON FUNCTION app_get_jar_state_with_purpose(text) FROM PUBLIC;
-- @@
REVOKE ALL ON FUNCTION app_get_overview_with_purpose(text, timestamptz, text) FROM PUBLIC;
-- @@
REVOKE ALL ON FUNCTION app_get_jar_detail_with_purpose(text, text, timestamptz, text) FROM PUBLIC;
-- @@
GRANT EXECUTE ON FUNCTION app_get_jar_state_with_purpose(text) TO yofina_app;
-- @@
GRANT EXECUTE ON FUNCTION app_get_overview_with_purpose(text, timestamptz, text) TO yofina_app;
-- @@
GRANT EXECUTE ON FUNCTION app_get_jar_detail_with_purpose(text, text, timestamptz, text) TO yofina_app;
