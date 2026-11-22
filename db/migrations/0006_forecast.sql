-- 0006_forecast: kết quả dự báo 30 ngày theo hũ (F1): lần chạy, tóm tắt mỗi hũ, phân vị theo ngày.
--
-- Ba bảng, đều có user_id và RLS FORCE:
-- * forecast_runs: một lần chạy (nightly, event, manual, reset, read). Mang metadata của cả lần chạy.
-- * forecast_jar_summaries: kết quả tổng hợp MỖI HŨ của một lần chạy (một dòng mỗi (run_id, jar_code)).
-- * forecasts: phân vị theo ngày mỗi hũ (chi tiêu ngày P10/P50/P90 và SỐ DƯ cuối ngày P10/P50/P90).
--
-- Vì sao tóm tắt là bảng con chứ không phải jsonb trong forecast_runs: Tổng quan cần "lần chạy mới nhất của MỖI hũ" trong một
-- truy vấn có chỉ mục (DISTINCT ON), có kiểu rõ (ngày cạn, xác suất, trạng thái đủ/sát/hụt) để lọc và kiểm bằng CHECK,
-- và một lần chạy theo sự kiện chỉ chạm một vài hũ nên không có dòng cho hũ khác. Metadata cả lần chạy (model, độ phủ, nhãn
-- tin cậy, cờ ước lượng ban đầu) dùng chung cho mọi hũ nên nằm ở forecast_runs.
--
-- Mốc nghĩa vụ và mốc lương KHÔNG lưu ở đây: ghép lúc đọc từ obligations và lịch lương (một nguồn sự thật).
-- Ngày đều là ngày mô phỏng của người dùng (ADR-0003). Ngày dự báo bắt đầu từ app_date + 1.
--
-- Quy ước như 0005 (db/README.md): chạy bằng secret MASTER, một transaction, tách bằng dòng "-- @@", viết lại được,
-- RLS FORCE, hàm đọc SECURITY INVOKER, có LIMIT. Không viết dấu hai chấm dính liền chữ cái hoặc gạch dưới.

CREATE TABLE IF NOT EXISTS forecast_runs (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  model                text NOT NULL CHECK (model ~ '^[a-z][a-z0-9_]{0,39}$'),
  model_version        text CHECK (model_version IS NULL OR length(model_version) <= 40),
  computed_at          timestamptz NOT NULL DEFAULT now(),
  app_date             date NOT NULL,
  horizon_days         smallint NOT NULL CHECK (horizon_days BETWEEN 1 AND 90),
  history_days         integer NOT NULL CHECK (history_days >= 0),
  data_coverage        numeric(4,3) CHECK (data_coverage IS NULL OR data_coverage BETWEEN 0 AND 1),
  confidence_label     text NOT NULL CHECK (confidence_label IN ('high', 'medium', 'low')),
  is_initial_estimate  boolean NOT NULL DEFAULT false,
  trigger              text NOT NULL CHECK (trigger IN ('nightly', 'event', 'manual', 'reset', 'read')),
  n_paths              integer CHECK (n_paths IS NULL OR n_paths > 0),
  seed                 bigint,
  parent_run_id        uuid,
  source_event_id      text CHECK (source_event_id IS NULL OR length(source_event_id) <= 80),
  params               jsonb CHECK (params IS NULL OR jsonb_typeof(params) = 'object'),
  UNIQUE (user_id, id)
);

-- @@
CREATE INDEX IF NOT EXISTS forecast_runs_user_time_idx ON forecast_runs (user_id, computed_at DESC, id);

-- @@
CREATE TABLE IF NOT EXISTS forecast_jar_summaries (
  run_id                 uuid NOT NULL,
  user_id                text NOT NULL,
  jar_code               text NOT NULL,
  start_balance_vnd      numeric(14,0) NOT NULL,
  payday_date            date NOT NULL,
  days_to_payday         smallint NOT NULL CHECK (days_to_payday >= 0),
  runout_date            date,
  p_shortfall            numeric(5,4) CHECK (p_shortfall IS NULL OR p_shortfall BETWEEN 0 AND 1),
  p_shortfall_se         numeric(6,5) CHECK (p_shortfall_se IS NULL OR p_shortfall_se >= 0),
  status                 text NOT NULL CHECK (status IN ('ok', 'tight', 'short')),
  confidence_band        text NOT NULL CHECK (confidence_band IN ('high', 'medium', 'low')),
  show_probability       boolean NOT NULL DEFAULT false,
  series_kind            text CHECK (series_kind IS NULL OR series_kind IN ('dense', 'sparse', 'cold_start')),
  PRIMARY KEY (run_id, jar_code),
  FOREIGN KEY (user_id, run_id) REFERENCES forecast_runs (user_id, id) ON DELETE CASCADE,
  FOREIGN KEY (user_id, jar_code) REFERENCES jars (user_id, code) ON DELETE CASCADE,
  CHECK (show_probability = (p_shortfall IS NOT NULL))
);

-- @@
CREATE INDEX IF NOT EXISTS forecast_jar_summaries_user_jar_idx ON forecast_jar_summaries (user_id, jar_code, run_id);

-- @@
-- Phân vị theo ngày. Số dư có thể ÂM (đường mô phỏng đi qua mức hụt), nên không có CHECK không âm ở cột số dư.
-- Chi tiêu ngày không âm. Thứ tự phân vị p10 <= p50 <= p90 được kiểm ở cả hai nhóm.
CREATE TABLE IF NOT EXISTS forecasts (
  run_id            uuid NOT NULL,
  user_id           text NOT NULL,
  jar_code          text NOT NULL,
  day               date NOT NULL,
  spend_p10_vnd     numeric(14,0) NOT NULL CHECK (spend_p10_vnd >= 0),
  spend_p50_vnd     numeric(14,0) NOT NULL CHECK (spend_p50_vnd >= 0),
  spend_p90_vnd     numeric(14,0) NOT NULL CHECK (spend_p90_vnd >= 0),
  balance_p10_vnd   numeric(14,0) NOT NULL,
  balance_p50_vnd   numeric(14,0) NOT NULL,
  balance_p90_vnd   numeric(14,0) NOT NULL,
  PRIMARY KEY (run_id, jar_code, day),
  FOREIGN KEY (user_id, run_id) REFERENCES forecast_runs (user_id, id) ON DELETE CASCADE,
  FOREIGN KEY (user_id, jar_code) REFERENCES jars (user_id, code) ON DELETE CASCADE,
  CHECK (spend_p10_vnd <= spend_p50_vnd AND spend_p50_vnd <= spend_p90_vnd),
  CHECK (balance_p10_vnd <= balance_p50_vnd AND balance_p50_vnd <= balance_p90_vnd)
);

-- @@
CREATE INDEX IF NOT EXISTS forecasts_user_jar_idx ON forecasts (user_id, jar_code, run_id, day);

-- @@
ALTER TABLE forecast_runs ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE forecast_runs FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON forecast_runs;

-- @@
CREATE POLICY user_isolation ON forecast_runs
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
ALTER TABLE forecast_jar_summaries ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE forecast_jar_summaries FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON forecast_jar_summaries;

-- @@
CREATE POLICY user_isolation ON forecast_jar_summaries
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
ALTER TABLE forecasts ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE forecasts FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON forecasts;

-- @@
CREATE POLICY user_isolation ON forecasts
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
-- Kết quả dự báo là bản ghi chỉ thêm và xóa (dọn lần chạy cũ, đặt lại demo); không sửa một lần chạy đã ghi.
GRANT SELECT, INSERT, DELETE ON forecast_runs TO yofina_app;

-- @@
GRANT SELECT, INSERT, DELETE ON forecast_jar_summaries TO yofina_app;

-- @@
GRANT SELECT, INSERT, DELETE ON forecasts TO yofina_app;

-- @@
-- Tóm tắt MỚI NHẤT của mỗi hũ (một dòng mỗi hũ có dự báo, tối đa 40), kèm metadata lần chạy. p_jar_code lọc một hũ nếu có.
-- "Mới nhất" tính theo thời điểm tính (computed_at, rồi id) của lần chạy có chứa hũ đó, nên lần chạy theo sự kiện chỉ chạm
-- vài hũ không làm mất dự báo của hũ khác.
CREATE OR REPLACE FUNCTION app_get_forecast_summaries(p_user_id text, p_jar_code text DEFAULT NULL)
RETURNS TABLE (
  jar_code text, run_id uuid, computed_at timestamptz, run_app_date date, model text, model_version text,
  trigger text, horizon_days smallint, history_days integer, data_coverage numeric, confidence_label text,
  is_initial_estimate boolean, start_balance_vnd numeric, payday_date date, days_to_payday smallint,
  runout_date date, p_shortfall numeric, p_shortfall_se numeric, status text, confidence_band text,
  show_probability boolean, series_kind text
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
           s.show_probability, s.series_kind
    FROM forecast_jar_summaries s
    JOIN forecast_runs r ON r.user_id = s.user_id AND r.id = s.run_id
    WHERE p_jar_code IS NULL OR s.jar_code = p_jar_code
    ORDER BY s.jar_code, r.computed_at DESC, r.id DESC
    LIMIT 40;
END
$$;

-- @@
-- Chuỗi theo ngày của hũ trong lần chạy MỚI NHẤT có chứa hũ đó, theo ngày tăng dần (tối đa 90 dòng).
CREATE OR REPLACE FUNCTION app_get_forecast_series(p_user_id text, p_jar_code text)
RETURNS TABLE (
  run_id uuid, day date,
  spend_p10_vnd numeric, spend_p50_vnd numeric, spend_p90_vnd numeric,
  balance_p10_vnd numeric, balance_p50_vnd numeric, balance_p90_vnd numeric
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  latest uuid;
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  SELECT s.run_id INTO latest
  FROM forecast_jar_summaries s
  JOIN forecast_runs r ON r.user_id = s.user_id AND r.id = s.run_id
  WHERE s.jar_code = p_jar_code
  ORDER BY r.computed_at DESC, r.id DESC
  LIMIT 1;
  IF latest IS NULL THEN
    RETURN;
  END IF;
  RETURN QUERY
    SELECT f.run_id, f.day, f.spend_p10_vnd, f.spend_p50_vnd, f.spend_p90_vnd,
           f.balance_p10_vnd, f.balance_p50_vnd, f.balance_p90_vnd
    FROM forecasts f
    WHERE f.run_id = latest AND f.jar_code = p_jar_code
    ORDER BY f.day
    LIMIT 90;
END
$$;

-- @@
-- Dọn lần chạy cũ: giữ p_keep lần chạy mới nhất của người dùng, xóa phần còn lại (kéo theo tóm tắt và dòng ngày). Trả số lần chạy đã xóa.
-- Một lần chạy theo sự kiện không có dòng cho mọi hũ, nên p_keep nên đủ lớn (mặc định 5) để mỗi hũ còn một lần chạy chứa nó.
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
  );
  GET DIAGNOSTICS removed = ROW_COUNT;
  RETURN removed;
END
$$;

-- @@
REVOKE ALL ON FUNCTION app_get_forecast_summaries(text, text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_forecast_series(text, text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_prune_forecast_runs(text, integer) FROM PUBLIC;

-- @@
GRANT EXECUTE ON FUNCTION app_get_forecast_summaries(text, text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_forecast_series(text, text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_prune_forecast_runs(text, integer) TO yofina_app;
