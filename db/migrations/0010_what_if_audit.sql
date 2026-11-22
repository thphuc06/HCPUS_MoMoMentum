-- 0010_what_if_audit: what-if, lời nhắc, phản hồi và bản ghi lượt đủ cho bảng "Vì sao" (phase 3).
--
-- Thêm ba bảng và mở rộng audit_events:
-- * scenarios: một lần chạy kịch bản what-if (spec đã chuẩn hóa, kết quả gọn). Dữ liệu DẪN XUẤT như forecasts: tính lại
--   được, dọn được, không phải sổ cái. Ghi lại để "Vì sao" và phản hồi tham chiếu được.
-- * nudges: lời nhắc người dùng đã xác nhận (tool schedule_nudge, đi qua token như mọi thao tác ghi). Phase 3 chỉ lưu và hủy;
--   việc gửi nhắc theo ngày là phase 4 và 5 (F7), nên cột `status` đã có `sent` và `dismissed`.
-- * feedback: người dùng chấp nhận hoặc từ chối một phương án (POST /feedback). Không đụng tiền nên không cần token.
-- * audit_events: thêm cột có kiểu cho BẢN GHI LƯỢT (event_type = 'agent_turn'): dữ liệu đã dùng, luật đã kiểm, độ tin cậy,
--   khối đã phát, số token, thời lượng từng bước. Là jsonb có kiểu rõ (CHECK jsonb_typeof) thay vì nhiều cột rời, vì mỗi phần
--   là một mảng hoặc đối tượng có hình dạng riêng do hợp đồng (contracts/tools/audit.results.schema.json) quy định, và chỉ
--   được đọc cả cụm để dựng khối explain. Bảng vẫn chỉ thêm, không sửa, không xóa: bản ghi lượt phải được ghi MỘT LẦN, đủ cột.
--
-- Hàm đọc cho GET /traces/{trace_id}: app_get_trace. Người khác hỏi trace của bạn thì không có dòng nào (RLS cộng điều kiện
-- user_id), nên REST trả 404 như trace không tồn tại.
--
-- Quy ước như 0005 tới 0009 (db/README.md): chạy bằng secret MASTER, một transaction, tách bằng dòng "-- @@", viết lại được,
-- RLS FORCE, hàm đọc SECURITY INVOKER, có LIMIT. Không viết dấu hai chấm dính liền chữ cái hoặc gạch dưới.
-- Không sửa 0001 tới 0009.

CREATE TABLE IF NOT EXISTS scenarios (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  trace_id         text CHECK (trace_id IS NULL OR length(trace_id) BETWEEN 1 AND 64),
  kind             text NOT NULL CHECK (kind IN ('one_time_purchase', 'bnpl_purchase', 'income_change', 'recurring_expense', 'jar_transfer', 'goal_delay')),
  spec             jsonb NOT NULL CHECK (jsonb_typeof(spec) = 'object'),
  spec_hash        text NOT NULL CHECK (spec_hash ~ '^[0-9a-f]{64}$'),
  app_date         date NOT NULL,
  baseline_run_id  uuid,
  n_paths          integer NOT NULL CHECK (n_paths > 0),
  seed             bigint,
  result           jsonb NOT NULL CHECK (jsonb_typeof(result) = 'object' AND octet_length(result::text) <= 60000),
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, id)
);

-- @@
-- baseline_run_id trỏ lần chạy dự báo nền nhưng KHÔNG có khóa ngoại: app_prune_forecast_runs xóa lần chạy cũ, còn kịch bản
-- cũ vẫn được đọc lại. result giới hạn 60000 ký tự vì Data API giới hạn khoảng 64 KB mỗi dòng kết quả.
CREATE INDEX IF NOT EXISTS scenarios_user_time_idx ON scenarios (user_id, created_at DESC, id);

-- @@
CREATE INDEX IF NOT EXISTS scenarios_user_trace_idx ON scenarios (user_id, trace_id) WHERE trace_id IS NOT NULL;

-- @@
CREATE TABLE IF NOT EXISTS nudges (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  kind              text NOT NULL CHECK (kind IN ('runout_warning', 'obligation_due', 'salary_pending', 'review_needed', 'low_data', 'purchase_review')),
  fire_on           date NOT NULL,
  created_app_date  date NOT NULL,
  jar_code          text CHECK (jar_code IS NULL OR jar_code ~ '^[a-z][a-z0-9_]{0,31}$'),
  note              text CHECK (note IS NULL OR length(note) BETWEEN 1 AND 120),
  status            text NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'sent', 'cancelled', 'dismissed')),
  source            text NOT NULL DEFAULT 'user_option' CHECK (source IN ('user_option', 'agent', 'system')),
  scenario_id       uuid,
  trace_id          text CHECK (trace_id IS NULL OR length(trace_id) BETWEEN 1 AND 64),
  dedupe_key        text CHECK (dedupe_key IS NULL OR length(dedupe_key) BETWEEN 1 AND 80),
  schedule_name     text CHECK (schedule_name IS NULL OR length(schedule_name) BETWEEN 1 AND 128),
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  cancelled_at      timestamptz,
  sent_at           timestamptz,
  UNIQUE (user_id, id),
  CHECK (fire_on > created_app_date),
  CHECK ((status = 'cancelled') = (cancelled_at IS NOT NULL)),
  CHECK ((status = 'sent') = (sent_at IS NOT NULL))
);

-- @@
-- Ngày đều là ngày mô phỏng (ADR-0003). scenario_id không có khóa ngoại vì kịch bản là dữ liệu dẫn xuất được dọn. schedule_name
-- để dành cho tên lịch EventBridge Scheduler khi phase 4 và 5 gửi nhắc thật.
CREATE INDEX IF NOT EXISTS nudges_user_status_idx ON nudges (user_id, status, fire_on);

-- @@
CREATE UNIQUE INDEX IF NOT EXISTS nudges_user_dedupe_idx ON nudges (user_id, dedupe_key) WHERE dedupe_key IS NOT NULL;

-- @@
CREATE TABLE IF NOT EXISTS feedback (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  trace_id     text NOT NULL CHECK (length(trace_id) BETWEEN 1 AND 64),
  block_id     text NOT NULL DEFAULT '' CHECK (length(block_id) <= 128),
  option_id    text NOT NULL CHECK (option_id ~ '^[a-z][a-z0-9_]{0,31}$'),
  decision     text NOT NULL CHECK (decision IN ('accepted', 'rejected')),
  reason       text CHECK (reason IS NULL OR length(reason) BETWEEN 1 AND 200),
  scenario_id  uuid,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, trace_id, block_id, option_id)
);

-- @@
-- Một phản hồi cho mỗi (trace, khối, phương án): gửi lại thì cập nhật quyết định (người dùng đổi ý). block_id rỗng nghĩa là
-- khối không có id (REST bỏ trường), để khóa duy nhất không dính NULL.
CREATE INDEX IF NOT EXISTS feedback_user_time_idx ON feedback (user_id, created_at DESC);

-- @@
ALTER TABLE scenarios ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE scenarios FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON scenarios;

-- @@
CREATE POLICY user_isolation ON scenarios
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
ALTER TABLE nudges ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE nudges FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON nudges;

-- @@
CREATE POLICY user_isolation ON nudges
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE feedback FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON feedback;

-- @@
CREATE POLICY user_isolation ON feedback
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
-- Kịch bản là dữ liệu dẫn xuất: chỉ thêm và xóa (dọn, đặt lại demo), không sửa một lần chạy đã ghi.
GRANT SELECT, INSERT, DELETE ON scenarios TO yofina_app;

-- @@
-- Lời nhắc đổi trạng thái (hủy, đã gửi) nên có UPDATE; phản hồi cập nhật khi người dùng đổi ý.
GRANT SELECT, INSERT, UPDATE, DELETE ON nudges TO yofina_app;

-- @@
GRANT SELECT, INSERT, UPDATE, DELETE ON feedback TO yofina_app;

-- @@
-- ===== audit_events: cột có kiểu cho bản ghi lượt. Quyền của yofina_app (SELECT, INSERT) và RLS giữ nguyên. =====
ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS conversation_id text CHECK (conversation_id IS NULL OR length(conversation_id) BETWEEN 1 AND 256);

-- @@
ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS intent text CHECK (intent IS NULL OR intent IN ('lookup', 'what_if', 'affordability', 'profile_update', 'move', 'out_of_scope', 'chitchat'));

-- @@
ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS data_used jsonb CHECK (data_used IS NULL OR jsonb_typeof(data_used) = 'array');

-- @@
ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS rules_checked jsonb CHECK (rules_checked IS NULL OR jsonb_typeof(rules_checked) = 'array');

-- @@
ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS confidence jsonb CHECK (confidence IS NULL OR jsonb_typeof(confidence) = 'object');

-- @@
ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS blocks_emitted jsonb CHECK (blocks_emitted IS NULL OR jsonb_typeof(blocks_emitted) = 'array');

-- @@
ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS token_usage jsonb CHECK (token_usage IS NULL OR jsonb_typeof(token_usage) = 'object');

-- @@
ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS step_timings jsonb CHECK (step_timings IS NULL OR jsonb_typeof(step_timings) = 'array');

-- @@
ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS duration_ms integer CHECK (duration_ms IS NULL OR duration_ms >= 0);

-- @@
-- Mỗi lượt đúng một bản ghi lượt (event_type agent_turn). Ghi lại cùng trace_id thì ON CONFLICT DO NOTHING, vì bảng chỉ thêm.
CREATE UNIQUE INDEX IF NOT EXISTS audit_events_turn_once_idx ON audit_events (user_id, trace_id) WHERE event_type = 'agent_turn' AND trace_id IS NOT NULL;

-- @@
-- ===== Hàm đọc (SECURITY INVOKER, tự đặt app.user_id, có LIMIT) =====
-- Bản ghi lượt của chính người gọi. Trace của người khác hoặc không tồn tại: không có dòng nào.
CREATE OR REPLACE FUNCTION app_get_trace(p_user_id text, p_trace_id text)
RETURNS TABLE (
  trace_id text, created_at timestamptz, conversation_id text, intent text, outcome text, code text,
  data_used jsonb, rules_checked jsonb, confidence jsonb, blocks_emitted jsonb, token_usage jsonb,
  step_timings jsonb, duration_ms integer
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT a.trace_id, a.created_at, a.conversation_id, a.intent, a.outcome, a.code,
           a.data_used, a.rules_checked, a.confidence, a.blocks_emitted, a.token_usage,
           a.step_timings, a.duration_ms
    FROM audit_events a
    WHERE a.user_id = p_user_id AND a.event_type = 'agent_turn' AND a.trace_id = p_trace_id
    ORDER BY a.created_at DESC
    LIMIT 1;
END
$$;

-- @@
-- Một kịch bản đã chạy của chính người gọi.
CREATE OR REPLACE FUNCTION app_get_scenario(p_user_id text, p_scenario_id uuid)
RETURNS TABLE (
  id uuid, trace_id text, kind text, spec jsonb, spec_hash text, app_date date,
  baseline_run_id uuid, n_paths integer, seed bigint, result jsonb, created_at timestamptz
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT s.id, s.trace_id, s.kind, s.spec, s.spec_hash, s.app_date,
           s.baseline_run_id, s.n_paths, s.seed, s.result, s.created_at
    FROM scenarios s
    WHERE s.user_id = p_user_id AND s.id = p_scenario_id
    LIMIT 1;
END
$$;

-- @@
-- Lời nhắc của chính người gọi, theo ngày nhắc tăng dần. p_status rỗng thì lấy mọi trạng thái.
CREATE OR REPLACE FUNCTION app_list_nudges(p_user_id text, p_status text DEFAULT NULL, p_limit integer DEFAULT 50)
RETURNS TABLE (
  id uuid, kind text, fire_on date, jar_code text, note text, status text, source text,
  scenario_id uuid, trace_id text, created_app_date date, created_at timestamptz
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT n.id, n.kind, n.fire_on, n.jar_code, n.note, n.status, n.source,
           n.scenario_id, n.trace_id, n.created_app_date, n.created_at
    FROM nudges n
    WHERE n.user_id = p_user_id AND (p_status IS NULL OR n.status = p_status)
    ORDER BY n.fire_on, n.created_at, n.id
    LIMIT LEAST(GREATEST(coalesce(p_limit, 50), 1), 200);
END
$$;

-- @@
-- Dọn kịch bản cũ: giữ p_keep lần chạy mới nhất của người dùng. Trả số dòng đã xóa.
CREATE OR REPLACE FUNCTION app_prune_scenarios(p_user_id text, p_keep integer DEFAULT 50)
RETURNS integer
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  removed integer;
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  DELETE FROM scenarios s
  WHERE s.id IN (
    SELECT x.id FROM scenarios x
    ORDER BY x.created_at DESC, x.id DESC
    OFFSET GREATEST(coalesce(p_keep, 50), 1)
  );
  GET DIAGNOSTICS removed = ROW_COUNT;
  RETURN removed;
END
$$;

-- @@
REVOKE ALL ON FUNCTION app_get_trace(text, text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_scenario(text, uuid) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_list_nudges(text, text, integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_prune_scenarios(text, integer) FROM PUBLIC;

-- @@
GRANT EXECUTE ON FUNCTION app_get_trace(text, text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_scenario(text, uuid) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_list_nudges(text, text, integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_prune_scenarios(text, integer) TO yofina_app;
