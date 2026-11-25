-- 0055_runout_date_shown: hũ thưa không nêu ngày cạn cụ thể (#25). Không sửa 0001 tới 0054 (migrator kiểm checksum).
--
-- * app_get_forecast_summaries: tạo lại (DROP rồi CREATE vì đổi kiểu trả về) với đúng các cột của 0008 theo cùng thứ tự, thêm cột cuối
--   runout_date_shown (boolean) = cờ params.show_runout_date của lần chạy chứa tóm tắt, theo mã hũ. Engine ML ghi cờ này khi bật
--   hiệu chỉnh lại (sai là hũ thưa, ngày cạn sai trung bình hơn 6 ngày trên backtest); lần chạy cũ hoặc công tắc tắt không có khóa
--   thì đúng, nghĩa là vẫn nêu ngày như trước. Cột runout_date giữ nguyên; bên dùng (ledger, forecast) bỏ ngày khi cờ sai.
--   Không thêm cột lưu: pipeline dự báo không phải ghi thêm gì. app_get_overview (bản của 0050) và app_get_jar_detail (0007) lấy cột
--   mới tự động vì chúng đổi cả dòng sang jsonb.
--
-- Quy ước như 0005 tới 0054 (db/README.md): chạy bằng secret MASTER, một transaction, tách bằng dòng "-- @@", viết lại được, hàm đọc
-- SECURITY INVOKER tự đặt app.user_id, có LIMIT. Không viết dấu hai chấm dính liền chữ cái hoặc gạch dưới (kể cả trong chú thích).

DROP FUNCTION IF EXISTS app_get_forecast_summaries(text, text);

-- @@
CREATE FUNCTION app_get_forecast_summaries(p_user_id text, p_jar_code text DEFAULT NULL)
RETURNS TABLE (
  jar_code text, run_id uuid, computed_at timestamptz, run_app_date date, model text, model_version text,
  trigger text, horizon_days smallint, history_days integer, data_coverage numeric, confidence_label text,
  is_initial_estimate boolean, start_balance_vnd numeric, payday_date date, days_to_payday smallint,
  runout_date date, p_shortfall numeric, p_shortfall_se numeric, status text, confidence_band text,
  show_probability boolean, series_kind text, forecast_floor_vnd numeric, runout_date_shown boolean
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT DISTINCT ON (s.jar_code)
           s.jar_code, s.run_id, r.computed_at, r.app_date, r.model, r.model_version,
           r.trigger, r.horizon_days, r.history_days, r.data_coverage, r.confidence_label,
           r.is_initial_estimate, s.start_balance_vnd, s.payday_date, s.days_to_payday,
           s.runout_date, s.p_shortfall, s.p_shortfall_se, s.status, s.confidence_band,
           s.show_probability, s.series_kind,
           (SELECT min(f.balance_p50_vnd) FROM forecasts f
              WHERE f.run_id = s.run_id AND f.jar_code = s.jar_code AND f.day < s.payday_date),
           COALESCE((r.params -> 'show_runout_date' ->> s.jar_code)::boolean, true)
    FROM forecast_jar_summaries s
    JOIN forecast_runs r ON r.user_id = s.user_id AND r.id = s.run_id
    WHERE p_jar_code IS NULL OR s.jar_code = p_jar_code
    ORDER BY s.jar_code, r.computed_at DESC, r.id DESC
    LIMIT 40;
END
$$;

-- @@
REVOKE ALL ON FUNCTION app_get_forecast_summaries(text, text) FROM PUBLIC;

-- @@
GRANT EXECUTE ON FUNCTION app_get_forecast_summaries(text, text) TO yofina_app;
