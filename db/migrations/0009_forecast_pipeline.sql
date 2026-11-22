-- 0009_forecast_pipeline: hàm DB cho pipeline dự báo (luồng C, phase 2). Không đổi bảng.
--
-- * app_get_forecast_context: MỌI thứ pipeline cần để dựng đầu vào dự báo của MỘT người dùng, trong một lệnh gọi Data API: bảng
--   (section, jar_code, payload jsonb) gồm một dòng meta (ngày mô phỏng, hồ sơ, dữ kiện độ phủ dữ liệu), mỗi hũ một dòng (kèm chuỗi
--   chi tiêu theo ngày đã lấp ngày 0) và mỗi nghĩa vụ đang hoạt động một dòng; mỗi dòng nhỏ hơn 64 KB (giới hạn của Data API).
--   Ngày mô phỏng tính ngay trong hàm (cùng công thức app_get_overview).
-- * app_get_forecast_run: một lần chạy kèm params (jsonb), để đường sự kiện (update_forecast) đọc lại phân phối đã fit. Có thể lọc
--   jar_state theo danh sách hũ (mã cách nhau bằng dấu phẩy) vì Data API giới hạn 64 KB mỗi dòng kết quả.
-- * app_list_forecast_users: người dùng đã khai lương và ngày nhận (đối tượng của batch đêm). Chỉ trả id. SECURITY DEFINER vì RLS
--   của bảng users theo từng người dùng nên role yofina_app không tự liệt kê được; hàm này không nhận tham số nào ngoài giới hạn
--   số dòng và không trả cột nào khác ngoài id.
-- * app_prune_forecast_runs: viết lại để KHÔNG BAO GIỜ xóa lần chạy mới nhất chứa một hũ nào đó (lần chạy theo sự kiện chỉ có vài hũ,
--   nên bản cũ có thể làm mất dự báo của hũ khác sau một loạt giao dịch).
--
-- Quy ước như 0005 (db/README.md): chạy bằng secret MASTER, một transaction, tách bằng dòng "-- @@", viết lại được, hàm đọc
-- SECURITY INVOKER tự đặt app.user_id, có LIMIT. Không viết dấu hai chấm dính liền chữ cái hoặc gạch dưới (kể cả trong chú thích).

CREATE OR REPLACE FUNCTION app_get_forecast_context(
  p_user_id text, p_now timestamptz, p_tz text, p_window_days integer DEFAULT 330
)
RETURNS TABLE (section text, jar_code text, payload jsonb)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_offset integer;
  v_today  date;
  v_first  date;
  v_from   date;
  v_income numeric;
  v_spend  numeric;
  v_net    numeric;
  v_end    numeric;
  v_rows   integer;
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  SELECT u.clock_offset_days INTO v_offset FROM users u LIMIT 1;
  IF NOT FOUND THEN
    RETURN;
  END IF;
  v_today := (p_now AT TIME ZONE p_tz)::date + coalesce(v_offset, 0);
  SELECT min(t.app_date) INTO v_first FROM transactions t;
  v_from := greatest(coalesce(v_first, v_today), v_today - greatest(coalesce(p_window_days, 330), 1));

  SELECT coalesce(sum(t.amount_vnd) FILTER (WHERE t.kind = 'income' AND t.tx_type = 'salary'), 0),
         coalesce(sum(-t.amount_vnd) FILTER (WHERE t.kind = 'expense' AND t.funding_source = 'jar'), 0),
         coalesce(sum(t.amount_vnd) FILTER (WHERE t.funding_source = 'jar'), 0)
    INTO v_income, v_spend, v_net
    FROM transactions t
    WHERE t.app_date >= v_from;
  SELECT coalesce(sum(j.balance_vnd), 0) INTO v_end FROM jars j;

  SELECT count(*) INTO v_rows FROM app_get_daily_spend(p_user_id, v_from, v_today - 1);

  RETURN QUERY
    SELECT 'meta'::text, NULL::text, jsonb_build_object(
      'app_date', v_today,
      'history_start', v_from,
      'spend_rows', v_rows,
      'profile', (
        SELECT jsonb_build_object(
          'monthly_salary_vnd', u.monthly_salary_vnd, 'payday_day', u.payday_day, 'clock_offset_days', u.clock_offset_days)
        FROM users u LIMIT 1),
      'coverage', jsonb_build_object(
        'income_vnd', v_income, 'spend_vnd', v_spend, 'balance_end_vnd', v_end, 'balance_start_vnd', v_end - v_net)
    );
  RETURN QUERY
    WITH ds AS MATERIALIZED (
      SELECT d.jar_code AS jc, d.day AS dd, d.spent_vnd AS sv FROM app_get_daily_spend(p_user_id, v_from, v_today - 1) d
    )
    SELECT 'jar'::text, j.code, jsonb_build_object(
      'code', j.code, 'name', j.name, 'kind', j.kind, 'balance_vnd', j.balance_vnd,
      'split_percent', j.split_percent, 'sort_order', j.sort_order,
      'spend', (
        SELECT coalesce(jsonb_agg(coalesce(s.sv, 0)::bigint ORDER BY g.d), '[]'::jsonb)
        FROM generate_series(v_from::timestamp, (v_today - 1)::timestamp, interval '1 day') AS g(d)
        LEFT JOIN ds s ON s.jc = j.code AND s.dd = g.d::date
      )
    )
    FROM (SELECT * FROM jars ORDER BY sort_order, code LIMIT 40) j;
  RETURN QUERY
    SELECT 'obligation'::text, o.pay_jar_code, jsonb_build_object(
      'id', o.id, 'kind', o.kind, 'name', o.name, 'amount_vnd', o.amount_vnd, 'amount_min_vnd', o.amount_min_vnd,
      'amount_max_vnd', o.amount_max_vnd, 'due_date', o.due_date, 'cycle', o.cycle, 'due_day', o.due_day,
      'pay_jar_code', o.pay_jar_code)
    FROM app_list_obligations(p_user_id, 'active', NULL, 100) o;
END
$$;

-- @@
CREATE OR REPLACE FUNCTION app_get_forecast_run(p_user_id text, p_run_id uuid, p_jar_codes text DEFAULT NULL)
RETURNS TABLE (
  run_id uuid, model text, model_version text, computed_at timestamptz, run_app_date date, horizon_days smallint,
  history_days integer, data_coverage numeric, confidence_label text, is_initial_estimate boolean, n_paths integer,
  seed bigint, params jsonb
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT r.id, r.model, r.model_version, r.computed_at, r.app_date, r.horizon_days, r.history_days, r.data_coverage,
           r.confidence_label, r.is_initial_estimate, r.n_paths, r.seed,
           CASE
             WHEN p_jar_codes IS NULL OR r.params IS NULL THEN r.params
             ELSE jsonb_set(
               r.params, '{jar_state}',
               coalesce(
                 (SELECT jsonb_object_agg(e.key, e.value)
                    FROM jsonb_each(coalesce(r.params -> 'jar_state', '{}'::jsonb)) e
                    WHERE e.key = ANY (string_to_array(p_jar_codes, ','))),
                 '{}'::jsonb))
           END
    FROM forecast_runs r
    WHERE r.id = p_run_id
    LIMIT 1;
END
$$;

-- @@
CREATE OR REPLACE FUNCTION app_list_forecast_users(p_limit integer DEFAULT 200)
RETURNS TABLE (user_id text)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
  RETURN QUERY
    SELECT u.id
    FROM users u
    WHERE u.monthly_salary_vnd IS NOT NULL AND u.payday_day IS NOT NULL
    ORDER BY u.id
    LIMIT LEAST(GREATEST(coalesce(p_limit, 200), 1), 500);
END
$$;

-- @@
-- Giữ p_keep lần chạy mới nhất, cộng LẦN CHẠY MỚI NHẤT CỦA MỖI HŨ (kể cả khi nó đã cũ hơn p_keep); xóa phần còn lại.
-- Trả số lần chạy đã xóa (kéo theo tóm tắt và dòng ngày).
CREATE OR REPLACE FUNCTION app_prune_forecast_runs(p_user_id text, p_keep integer DEFAULT 5)
RETURNS integer
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  removed integer;
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  DELETE FROM forecast_runs r
  WHERE r.id IN (
      SELECT x.id FROM forecast_runs x
      ORDER BY x.computed_at DESC, x.id DESC
      OFFSET GREATEST(coalesce(p_keep, 5), 1)
    )
    AND r.id NOT IN (
      SELECT DISTINCT ON (s.jar_code) s.run_id
      FROM forecast_jar_summaries s
      JOIN forecast_runs rr ON rr.user_id = s.user_id AND rr.id = s.run_id
      ORDER BY s.jar_code, rr.computed_at DESC, rr.id DESC
    );
  GET DIAGNOSTICS removed = ROW_COUNT;
  RETURN removed;
END
$$;

-- @@
REVOKE ALL ON FUNCTION app_get_forecast_context(text, timestamptz, text, integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_forecast_run(text, uuid, text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_list_forecast_users(integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_prune_forecast_runs(text, integer) FROM PUBLIC;

-- @@
GRANT EXECUTE ON FUNCTION app_get_forecast_context(text, timestamptz, text, integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_forecast_run(text, uuid, text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_list_forecast_users(integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_prune_forecast_runs(text, integer) TO yofina_app;
