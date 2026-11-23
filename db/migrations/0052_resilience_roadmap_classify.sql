-- 0052_resilience_roadmap_classify: điểm chống chịu, lộ trình có phiên bản, đổi hành vi, phân hũ tự động bằng embedding (phase 4).
--
-- Thêm pgvector và tám bảng, nới CHECK ý định của audit_events:
-- * resilience_scores: điểm chống chịu theo NGÀY MÔ PHỎNG (F4): điểm 0..100, bốn thành phần Save, Spend, Borrow, Plan (mỗi thành phần
--   có điểm, trọng số, câu giải thích do code dựng và đầu vào, nằm trong cột jsonb `components`), nhóm điểm, đầu vào đã dùng
--   (`inputs`: ảnh chụp dữ kiện, không phải số của từng thành phần). Một dòng mỗi (người dùng, ngày): tính lại thì ghi đè.
-- * roadmaps: lộ trình theo giai đoạn (F5), mỗi lần lưu là MỘT phiên bản mới `version` tăng dần theo người dùng, không sửa nội dung
--   cũ (cột `plan` bất biến: yofina_app chỉ được UPDATE `status`, `step_states`, `updated_at`). `status`: active (đang dùng, tối đa
--   một), proposed (bản mới chờ người dùng chọn, tối đa một), superseded, discarded. Trạng thái từng bước nằm ở `step_states`
--   (đối tượng step_id -> {status, decided_at, edited}); bước vắng trong đó là `pending`. Phiên bản và chuyển trạng thái đi qua hàm
--   `app_save_roadmap`, `app_decide_roadmap_version`, `app_set_roadmap_step_state` (khóa theo người dùng để hai yêu cầu song song
--   không sinh trùng số phiên bản).
-- * roadmap_jobs: một lần sinh lại chạy nền (REST hỏi tiến độ bằng polling): trạng thái, bước đang chạy, phần trăm, kết quả. Mỗi người
--   dùng tối đa một lần đang chạy; `dedupe_key` làm sự kiện giao ít nhất một lần (behavior.changed) không sinh trùng.
-- * behavior_flags: dấu hiệu đổi hành vi chi tiêu theo hũ: nghi (CUSUM hoặc PageHinkley trong đường sự kiện), đã xác nhận (PELT trong
--   batch đêm, mức mới giữ khoảng 2 tuần), báo nhầm, đã dùng để sinh lại lộ trình. Mức cũ và mới tính theo VND mỗi tuần.
-- * tx_embeddings: embedding (vector 1024 chiều, vai `embedding` = cohere.embed-multilingual-v3) của chuỗi giao dịch ĐÃ CHUẨN HÓA
--   (bỏ dấu, chữ thường, mở rộng viết tắt), một dòng mỗi giao dịch. BẢNG RIÊNG, không phải cột của `transactions`: Data API trả
--   `vector` dạng chuỗi (khoảng 10 KB mỗi dòng), cột này sẽ làm phình mọi câu SELECT, RETURNING và hàm app_* của sổ cái; bảng riêng
--   chỉ đọc khi cần. Không có chỉ mục vector (tra theo transaction_id).
-- * tx_embeddings_labeled: bộ nhãn cho k-NN của MỖI người dùng (RLS): chuỗi chuẩn hóa -> hũ, nguồn user (người dùng sửa) hoặc seed
--   (nhãn của persona), kèm embedding. Chỉ mục HNSW cosine. Ngưỡng cosine do cấu hình, hiệu chỉnh trên dữ liệu (spike Bedrock §6:
--   KHÔNG dùng 0,97 của proposal). Bộ nhãn không có dòng nào cho người dùng mới hoàn toàn: khi đó phân loại rơi sang bước LLM.
-- * review_asks: câu hỏi gộp của một ngày mô phỏng (hỏi MỘT lần mỗi ngày): mở, đã xong, hoặc người dùng để sau.
-- * payees: thêm `correction_count` (số lần người dùng sửa hũ cho người nhận này) và `auto_min_confidence` (ngưỡng tự gán riêng của
--   người nhận, NULL là dùng ngưỡng chung của cấu hình): sửa nhiều lần thì nâng ngưỡng.
-- * audit_events: nới CHECK của `intent` từ bảy ý định (0010) thành mười (thêm resilience, stress, roadmap).
--
-- Hàm đọc app_*: SECURITY INVOKER, tự đặt app.user_id, có LIMIT. Hàm ghi chỉ cho thao tác cần tính nguyên tử (phiên bản lộ trình).
-- Lỗi nghiệp vụ trong hàm là RAISE EXCEPTION có tiền tố là mã `ErrorCode` ("ROADMAP_VERSION_CONFLICT: ...", "ROADMAP_NOT_FOUND: ...",
-- "ROADMAP_INVALID: ...") để tầng Lambda đổi sang mã lỗi REST.
--
-- Quy ước như 0005 tới 0051 (db/README.md): chạy bằng secret MASTER (CREATE EXTENSION cần quyền rds_superuser), một transaction, tách
-- bằng dòng "-- @@", viết lại được, RLS FORCE, hàm đọc SECURITY INVOKER. Không viết dấu hai chấm dính liền chữ cái hoặc gạch dưới.
-- Không sửa 0001 tới 0051 (migrator kiểm checksum). Đặt lại demo phải xóa thêm các bảng mới (RESET_DELETES; việc của luồng A và B).

CREATE EXTENSION IF NOT EXISTS vector;

-- @@
-- ===== resilience_scores =====
CREATE TABLE IF NOT EXISTS resilience_scores (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  app_date        date NOT NULL,
  score           smallint NOT NULL CHECK (score BETWEEN 0 AND 100),
  band            text NOT NULL CHECK (band IN ('weak', 'fair', 'strong')),
  weakest         text NOT NULL CHECK (weakest IN ('save', 'spend', 'borrow', 'plan')),
  headline        text NOT NULL CHECK (length(headline) BETWEEN 1 AND 160),
  components      jsonb NOT NULL CHECK (jsonb_typeof(components) = 'array' AND jsonb_array_length(components) = 4),
  inputs          jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(inputs) = 'object'),
  basis           jsonb NOT NULL CHECK (jsonb_typeof(basis) = 'object'),
  config_version  text NOT NULL CHECK (length(config_version) BETWEEN 1 AND 40),
  source          text NOT NULL CHECK (source IN ('nightly', 'reset', 'event', 'read')),
  computed_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, app_date),
  CHECK (octet_length(components::text) + octet_length(inputs::text) + octet_length(basis::text) <= 40000)
);

-- @@
-- ===== roadmaps =====
CREATE TABLE IF NOT EXISTS roadmaps (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  version           integer NOT NULL CHECK (version BETWEEN 1 AND 10000),
  status            text NOT NULL CHECK (status IN ('active', 'proposed', 'superseded', 'discarded')),
  reason_code       text NOT NULL CHECK (reason_code IN ('initial', 'behavior_changed', 'goal_changed', 'income_changed', 'forecast_drift', 'user_request', 'step_edited')),
  reason_text       text NOT NULL CHECK (length(reason_text) BETWEEN 1 AND 160),
  reason_detail     jsonb CHECK (reason_detail IS NULL OR jsonb_typeof(reason_detail) = 'array'),
  behavior_flag_id  uuid,
  based_on_version  integer CHECK (based_on_version IS NULL OR based_on_version >= 1),
  feasibility       text NOT NULL CHECK (feasibility IN ('on_track', 'relaxed', 'infeasible')),
  app_date          date NOT NULL,
  plan              jsonb NOT NULL CHECK (jsonb_typeof(plan) = 'object' AND octet_length(plan::text) <= 50000),
  step_states       jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(step_states) = 'object'),
  rules_version     text NOT NULL CHECK (length(rules_version) BETWEEN 1 AND 40),
  trace_id          text CHECK (trace_id IS NULL OR length(trace_id) BETWEEN 1 AND 64),
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, version),
  CHECK (based_on_version IS NULL OR based_on_version < version)
);

-- @@
-- plan = {headline, horizon, goals, phases (bước ở trạng thái pending), alternatives, basis}: phần còn lại của khối roadmap nằm ở các
-- cột. behavior_flag_id không có khóa ngoại vì dấu hiệu là dữ liệu dẫn xuất có thể dọn; plan không giữ lại tên người nhận hay PII.
CREATE UNIQUE INDEX IF NOT EXISTS roadmaps_one_active_idx ON roadmaps (user_id) WHERE status = 'active';

-- @@
CREATE UNIQUE INDEX IF NOT EXISTS roadmaps_one_proposed_idx ON roadmaps (user_id) WHERE status = 'proposed';

-- @@
-- ===== roadmap_jobs =====
CREATE TABLE IF NOT EXISTS roadmap_jobs (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  status            text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
  trigger           text NOT NULL CHECK (trigger IN ('user_request', 'behavior_changed', 'goal_changed', 'income_changed', 'forecast_drift')),
  stage             text CHECK (stage IS NULL OR stage IN ('context', 'draft', 'allocate', 'suitability', 'save')),
  progress          smallint NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  alternative_id    text CHECK (alternative_id IS NULL OR alternative_id ~ '^[a-z][a-z0-9_]{0,31}$'),
  note              text CHECK (note IS NULL OR length(note) BETWEEN 1 AND 200),
  based_on_version  integer CHECK (based_on_version IS NULL OR based_on_version >= 1),
  behavior_flag_id  uuid,
  dedupe_key        text CHECK (dedupe_key IS NULL OR length(dedupe_key) BETWEEN 1 AND 80),
  roadmap_id        uuid,
  version           integer CHECK (version IS NULL OR version >= 1),
  error_code        text CHECK (error_code IS NULL OR error_code ~ '^[A-Z][A-Z0-9_]*$'),
  error_message     text CHECK (error_message IS NULL OR length(error_message) BETWEEN 1 AND 280),
  requested_at      timestamptz NOT NULL DEFAULT now(),
  started_at        timestamptz,
  finished_at       timestamptz,
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CHECK ((status IN ('done', 'failed')) = (finished_at IS NOT NULL)),
  CHECK ((status = 'done') = (roadmap_id IS NOT NULL AND version IS NOT NULL)),
  CHECK ((status = 'failed') = (error_code IS NOT NULL AND error_message IS NOT NULL)),
  CHECK (status <> 'done' OR progress = 100)
);

-- @@
-- roadmap_id không có khóa ngoại (bản lộ trình có thể bị dọn khi đặt lại demo trong khi lịch sử job vẫn đọc được).
CREATE UNIQUE INDEX IF NOT EXISTS roadmap_jobs_one_live_idx ON roadmap_jobs (user_id) WHERE status IN ('queued', 'running');

-- @@
CREATE UNIQUE INDEX IF NOT EXISTS roadmap_jobs_dedupe_idx ON roadmap_jobs (user_id, dedupe_key) WHERE dedupe_key IS NOT NULL;

-- @@
CREATE INDEX IF NOT EXISTS roadmap_jobs_user_time_idx ON roadmap_jobs (user_id, requested_at DESC, id);

-- @@
-- ===== behavior_flags =====
CREATE TABLE IF NOT EXISTS behavior_flags (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  jar_code            text NOT NULL,
  status              text NOT NULL DEFAULT 'suspected' CHECK (status IN ('suspected', 'confirmed', 'dismissed', 'applied')),
  method              text NOT NULL CHECK (method IN ('cusum', 'page_hinkley', 'pelt')),
  direction           text NOT NULL CHECK (direction IN ('up', 'down')),
  old_weekly_vnd      numeric(14,0) NOT NULL CHECK (old_weekly_vnd >= 0),
  new_weekly_vnd      numeric(14,0) NOT NULL CHECK (new_weekly_vnd >= 0),
  suspected_app_date  date NOT NULL,
  change_point_date   date,
  confirmed_app_date  date,
  weeks_held          integer CHECK (weeks_held IS NULL OR weeks_held >= 0),
  detail              jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(detail) = 'object'),
  roadmap_job_id      uuid,
  applied_at          timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (user_id, jar_code) REFERENCES jars (user_id, code) ON DELETE CASCADE,
  CHECK (new_weekly_vnd <> old_weekly_vnd),
  CHECK ((direction = 'up') = (new_weekly_vnd > old_weekly_vnd)),
  CHECK ((status IN ('confirmed', 'applied')) = (confirmed_app_date IS NOT NULL)),
  CHECK ((status = 'applied') = (applied_at IS NOT NULL))
);

-- @@
-- Mỗi (người dùng, hũ) chỉ một dấu hiệu đang mở (nghi hoặc đã xác nhận chưa dùng). detail ghi tham số của bộ phát hiện (ngưỡng z,
-- penalty, số tuần, phiên bản cấu hình, tỷ lệ báo nhầm đã hiệu chỉnh) để truy vết; không chứa PII.
CREATE UNIQUE INDEX IF NOT EXISTS behavior_flags_open_idx ON behavior_flags (user_id, jar_code) WHERE status IN ('suspected', 'confirmed');

-- @@
CREATE INDEX IF NOT EXISTS behavior_flags_user_status_idx ON behavior_flags (user_id, status, created_at DESC, id);

-- @@
-- ===== tx_embeddings: embedding của MỘT giao dịch (bảng riêng, xem chú thích đầu file) =====
CREATE TABLE IF NOT EXISTS tx_embeddings (
  transaction_id  uuid PRIMARY KEY REFERENCES transactions (id) ON DELETE CASCADE,
  user_id         text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  text_norm       text NOT NULL CHECK (length(text_norm) BETWEEN 1 AND 300),
  model           text NOT NULL CHECK (length(model) BETWEEN 1 AND 80),
  embedding       vector(1024) NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- @@
-- ===== tx_embeddings_labeled: bộ nhãn k-NN của từng người dùng =====
CREATE TABLE IF NOT EXISTS tx_embeddings_labeled (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  text_norm       text NOT NULL CHECK (length(text_norm) BETWEEN 1 AND 300),
  jar_code        text NOT NULL,
  source          text NOT NULL CHECK (source IN ('user', 'seed')),
  transaction_id  uuid,
  model           text NOT NULL CHECK (length(model) BETWEEN 1 AND 80),
  embedding       vector(1024) NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (user_id, jar_code) REFERENCES jars (user_id, code) ON DELETE CASCADE,
  UNIQUE (user_id, text_norm, jar_code)
);

-- @@
-- Chỉ mục HNSW cosine (vector_cosine_ops, khoảng cách bằng toán tử cosine). Khóa duy nhất (user_id, text_norm, jar_code) cũng phục vụ
-- bước "khớp chuỗi chính xác trước, rồi mới k-NN". Lưu ý: HNSW lọc theo user_id SAU khi quét chỉ mục, nên với bộ nhãn rất lớn của nhiều
-- người dùng có thể trả ít hơn k dòng; bộ nhãn mỗi người nhỏ nên planner thường chọn quét tuần tự. Aurora pgvector 0.8.2 có
-- hnsw.iterative_scan (bản 0.6.2 của test cục bộ thì không): luồng B quyết định khi đo.
CREATE INDEX IF NOT EXISTS tx_embeddings_labeled_hnsw_idx ON tx_embeddings_labeled USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- @@
-- ===== review_asks: câu hỏi gộp của một ngày =====
CREATE TABLE IF NOT EXISTS review_asks (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  ask_date           date NOT NULL,
  status             text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'answered', 'skipped')),
  item_count         integer NOT NULL CHECK (item_count >= 0),
  pending_total_vnd  numeric(14,0) NOT NULL DEFAULT 0 CHECK (pending_total_vnd >= 0),
  created_at         timestamptz NOT NULL DEFAULT now(),
  resolved_at        timestamptz,
  UNIQUE (user_id, ask_date),
  CHECK ((status = 'open') = (resolved_at IS NULL))
);

-- @@
-- ===== payees: ngưỡng tự gán riêng của người nhận =====
ALTER TABLE payees ADD COLUMN IF NOT EXISTS correction_count integer NOT NULL DEFAULT 0 CHECK (correction_count >= 0);

-- @@
ALTER TABLE payees ADD COLUMN IF NOT EXISTS auto_min_confidence numeric(4,3) CHECK (auto_min_confidence IS NULL OR auto_min_confidence BETWEEN 0 AND 1);

-- @@
-- ===== audit_events: nới CHECK ý định (bảy ý định của 0010 thành mười) =====
ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS audit_events_intent_check;

-- @@
ALTER TABLE audit_events ADD CONSTRAINT audit_events_intent_check CHECK (intent IS NULL OR intent IN ('lookup', 'what_if', 'affordability', 'profile_update', 'move', 'out_of_scope', 'chitchat', 'resilience', 'stress', 'roadmap'));

-- @@
-- ===== RLS: ENABLE và FORCE, policy user_isolation theo app.user_id =====
ALTER TABLE resilience_scores ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE resilience_scores FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON resilience_scores;

-- @@
CREATE POLICY user_isolation ON resilience_scores
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
ALTER TABLE roadmaps ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE roadmaps FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON roadmaps;

-- @@
CREATE POLICY user_isolation ON roadmaps
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
ALTER TABLE roadmap_jobs ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE roadmap_jobs FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON roadmap_jobs;

-- @@
CREATE POLICY user_isolation ON roadmap_jobs
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
ALTER TABLE behavior_flags ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE behavior_flags FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON behavior_flags;

-- @@
CREATE POLICY user_isolation ON behavior_flags
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
ALTER TABLE tx_embeddings ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE tx_embeddings FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON tx_embeddings;

-- @@
CREATE POLICY user_isolation ON tx_embeddings
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
ALTER TABLE tx_embeddings_labeled ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE tx_embeddings_labeled FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON tx_embeddings_labeled;

-- @@
CREATE POLICY user_isolation ON tx_embeddings_labeled
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
ALTER TABLE review_asks ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE review_asks FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON review_asks;

-- @@
CREATE POLICY user_isolation ON review_asks
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
-- ===== Quyền của yofina_app (tối thiểu) =====
GRANT SELECT, INSERT, UPDATE, DELETE ON resilience_scores TO yofina_app;

-- @@
-- Nội dung một phiên bản lộ trình bất biến: chỉ cho UPDATE trạng thái, trạng thái từng bước và thời điểm sửa (và DELETE để đặt lại demo).
GRANT SELECT, INSERT, DELETE ON roadmaps TO yofina_app;

-- @@
GRANT UPDATE (status, step_states, updated_at) ON roadmaps TO yofina_app;

-- @@
GRANT SELECT, INSERT, UPDATE, DELETE ON roadmap_jobs TO yofina_app;

-- @@
GRANT SELECT, INSERT, UPDATE, DELETE ON behavior_flags TO yofina_app;

-- @@
GRANT SELECT, INSERT, DELETE ON tx_embeddings TO yofina_app;

-- @@
GRANT SELECT, INSERT, UPDATE, DELETE ON tx_embeddings_labeled TO yofina_app;

-- @@
GRANT SELECT, INSERT, UPDATE, DELETE ON review_asks TO yofina_app;

-- @@
-- Điểm chống chịu mới nhất không sau ngày p_app_date (ngày mô phỏng; NULL là mới nhất), kèm điểm của lần tính liền trước nó.
CREATE OR REPLACE FUNCTION app_get_resilience_score(p_user_id text, p_app_date date DEFAULT NULL)
RETURNS TABLE (
  id uuid, app_date date, score smallint, band text, weakest text, headline text, components jsonb, inputs jsonb,
  basis jsonb, config_version text, source text, computed_at timestamptz, previous_score smallint
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT r.id, r.app_date, r.score, r.band, r.weakest, r.headline, r.components, r.inputs,
           r.basis, r.config_version, r.source, r.computed_at,
           (SELECT p.score FROM resilience_scores p
             WHERE p.user_id = r.user_id AND p.app_date < r.app_date
             ORDER BY p.app_date DESC LIMIT 1)
    FROM resilience_scores r
    WHERE r.user_id = p_user_id AND (p_app_date IS NULL OR r.app_date <= p_app_date)
    ORDER BY r.app_date DESC
    LIMIT 1;
END
$$;

-- @@
-- Đọc MỘT phiên bản lộ trình. p_version có thì lấy đúng bản đó; không thì theo p_which: active (mặc định; không có bản đang dùng thì lấy
-- bản mới nhất), proposed (bản chờ chọn, không có thì không dòng nào), latest (phiên bản lớn nhất). Người khác đọc thì không có dòng.
CREATE OR REPLACE FUNCTION app_get_roadmap(p_user_id text, p_version integer DEFAULT NULL, p_which text DEFAULT 'active')
RETURNS TABLE (
  id uuid, version integer, status text, reason_code text, reason_text text, reason_detail jsonb, behavior_flag_id uuid,
  based_on_version integer, feasibility text, app_date date, plan jsonb, step_states jsonb, rules_version text,
  trace_id text, created_at timestamptz, updated_at timestamptz
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT r.id, r.version, r.status, r.reason_code, r.reason_text, r.reason_detail, r.behavior_flag_id,
           r.based_on_version, r.feasibility, r.app_date, r.plan, r.step_states, r.rules_version,
           r.trace_id, r.created_at, r.updated_at
    FROM roadmaps r
    WHERE r.user_id = p_user_id
      AND CASE
            WHEN p_version IS NOT NULL THEN r.version = p_version
            WHEN p_which = 'proposed' THEN r.status = 'proposed'
            ELSE true
          END
    ORDER BY CASE WHEN p_version IS NULL AND coalesce(p_which, 'active') NOT IN ('latest', 'proposed') AND r.status = 'active' THEN 0 ELSE 1 END,
             r.version DESC
    LIMIT 1;
END
$$;

-- @@
-- Danh sách phiên bản (mới nhất trước), không mang plan. steps_total, accepted_count, rejected_count để dựng RoadmapCounts (chờ = tổng trừ hai số kia).
CREATE OR REPLACE FUNCTION app_list_roadmap_versions(p_user_id text, p_limit integer DEFAULT 20)
RETURNS TABLE (
  id uuid, version integer, status text, reason_code text, reason_text text, based_on_version integer,
  feasibility text, app_date date, created_at timestamptz, steps_total bigint, accepted_count bigint, rejected_count bigint
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT r.id, r.version, r.status, r.reason_code, r.reason_text, r.based_on_version,
           r.feasibility, r.app_date, r.created_at,
           (SELECT count(*) FROM jsonb_array_elements(r.plan -> 'phases') ph, jsonb_array_elements(ph -> 'steps') st),
           (SELECT count(*) FROM jsonb_each(r.step_states) e WHERE e.value ->> 'status' = 'accepted'),
           (SELECT count(*) FROM jsonb_each(r.step_states) e WHERE e.value ->> 'status' = 'rejected')
    FROM roadmaps r
    WHERE r.user_id = p_user_id
    ORDER BY r.version DESC
    LIMIT LEAST(GREATEST(coalesce(p_limit, 20), 1), 50);
END
$$;

-- @@
-- Lưu MỘT phiên bản mới, nguyên tử: khóa dòng users của người gọi (hai yêu cầu song song không sinh trùng số), kiểm bản gốc còn sống
-- (active hoặc proposed), gán version = lớn nhất + 1. Bản mới active thì bản active cũ thành superseded và bản proposed (nếu có) bị
-- bỏ (discarded); bản mới proposed thì chỉ bản proposed cũ bị bỏ. plan do Lambda dựng và đã kiểm suitability; ở đây không đọc plan.
CREATE OR REPLACE FUNCTION app_save_roadmap(
  p_user_id text, p_reason_code text, p_reason_text text, p_reason_detail jsonb, p_behavior_flag_id uuid,
  p_based_on_version integer, p_feasibility text, p_app_date date, p_plan jsonb, p_rules_version text,
  p_status text, p_trace_id text
)
RETURNS TABLE (id uuid, version integer, status text, created_at timestamptz)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_max integer;
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  IF p_status IS NULL OR p_status NOT IN ('active', 'proposed') THEN
    RAISE EXCEPTION 'ROADMAP_INVALID: phiên bản mới chỉ có thể là active hoặc proposed';
  END IF;
  PERFORM 1 FROM users u WHERE u.id = p_user_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'PROFILE_INCOMPLETE: người dùng chưa có hồ sơ';
  END IF;
  SELECT coalesce(max(r.version), 0) INTO v_max FROM roadmaps r WHERE r.user_id = p_user_id;
  IF p_reason_code = 'initial' AND v_max > 0 THEN
    RAISE EXCEPTION 'ROADMAP_VERSION_CONFLICT: đã có lộ trình, không thể là bản đầu tiên';
  END IF;
  IF p_based_on_version IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM roadmaps r
    WHERE r.user_id = p_user_id AND r.version = p_based_on_version AND r.status IN ('active', 'proposed')
  ) THEN
    RAISE EXCEPTION 'ROADMAP_VERSION_CONFLICT: bản gốc đã bị thay hoặc không còn, hãy đọc lại lộ trình';
  END IF;
  IF p_status = 'active' THEN
    UPDATE roadmaps r SET status = 'superseded', updated_at = now() WHERE r.user_id = p_user_id AND r.status = 'active';
  END IF;
  UPDATE roadmaps r SET status = 'discarded', updated_at = now() WHERE r.user_id = p_user_id AND r.status = 'proposed';
  RETURN QUERY
    INSERT INTO roadmaps AS n (user_id, version, status, reason_code, reason_text, reason_detail, behavior_flag_id,
                               based_on_version, feasibility, app_date, plan, rules_version, trace_id)
    VALUES (p_user_id, v_max + 1, p_status, p_reason_code, p_reason_text, p_reason_detail, p_behavior_flag_id,
            p_based_on_version, p_feasibility, p_app_date, p_plan, p_rules_version, p_trace_id)
    RETURNING n.id, n.version, n.status, n.created_at;
END
$$;

-- @@
-- Người dùng chọn với bản chờ (proposed): adopt thì bản đó thành active và bản active cũ thành superseded; keep_previous thì bản đó
-- bị bỏ (discarded), bản đang dùng giữ nguyên. Gọi lại với cùng quyết định là không đổi gì (idempotent). Trả dòng của bản được chọn.
CREATE OR REPLACE FUNCTION app_decide_roadmap_version(p_user_id text, p_version integer, p_decision text)
RETURNS TABLE (id uuid, version integer, status text)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_status text;
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  IF p_decision IS NULL OR p_decision NOT IN ('adopt', 'keep_previous') THEN
    RAISE EXCEPTION 'ROADMAP_INVALID: quyết định phải là adopt hoặc keep_previous';
  END IF;
  PERFORM 1 FROM users u WHERE u.id = p_user_id FOR UPDATE;
  SELECT r.status INTO v_status FROM roadmaps r WHERE r.user_id = p_user_id AND r.version = p_version;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'ROADMAP_NOT_FOUND: không có phiên bản này';
  END IF;
  IF p_decision = 'adopt' AND v_status = 'proposed' THEN
    UPDATE roadmaps r SET status = 'superseded', updated_at = now() WHERE r.user_id = p_user_id AND r.status = 'active';
    UPDATE roadmaps r SET status = 'active', updated_at = now() WHERE r.user_id = p_user_id AND r.version = p_version;
  ELSIF p_decision = 'keep_previous' AND v_status = 'proposed' THEN
    UPDATE roadmaps r SET status = 'discarded', updated_at = now() WHERE r.user_id = p_user_id AND r.version = p_version;
  ELSIF NOT ((p_decision = 'adopt' AND v_status = 'active') OR (p_decision = 'keep_previous' AND v_status = 'discarded')) THEN
    RAISE EXCEPTION 'ROADMAP_VERSION_CONFLICT: bản này không còn ở trạng thái chờ chọn';
  END IF;
  RETURN QUERY SELECT r.id, r.version, r.status FROM roadmaps r WHERE r.user_id = p_user_id AND r.version = p_version;
END
$$;

-- @@
-- Chấp nhận, từ chối hoặc đưa về chờ một bước. Chỉ làm được trên bản active hoặc proposed. Bước phải có trong plan. pending xóa trạng thái
-- đã ghi; accepted và rejected ghi {status, decided_at} (p_edited đúng thì thêm edited). Chấp nhận KHÔNG đổi số dư.
CREATE OR REPLACE FUNCTION app_set_roadmap_step_state(
  p_user_id text, p_version integer, p_step_id text, p_status text, p_edited boolean DEFAULT NULL
)
RETURNS TABLE (id uuid, version integer, step_states jsonb)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_status text;
  v_plan jsonb;
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  IF p_status IS NULL OR p_status NOT IN ('accepted', 'rejected', 'pending') THEN
    RAISE EXCEPTION 'ROADMAP_INVALID: trạng thái bước phải là accepted, rejected hoặc pending';
  END IF;
  SELECT r.status, r.plan INTO v_status, v_plan FROM roadmaps r WHERE r.user_id = p_user_id AND r.version = p_version FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'ROADMAP_NOT_FOUND: không có phiên bản này';
  END IF;
  IF v_status NOT IN ('active', 'proposed') THEN
    RAISE EXCEPTION 'ROADMAP_VERSION_CONFLICT: phiên bản này đã bị thay hoặc bỏ';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM jsonb_array_elements(v_plan -> 'phases') ph, jsonb_array_elements(ph -> 'steps') st WHERE st ->> 'step_id' = p_step_id
  ) THEN
    RAISE EXCEPTION 'ROADMAP_NOT_FOUND: không có bước này trong phiên bản';
  END IF;
  RETURN QUERY
    UPDATE roadmaps AS r
    SET step_states = CASE
          WHEN p_status = 'pending' THEN r.step_states - p_step_id
          ELSE jsonb_set(r.step_states, ARRAY[p_step_id],
                         jsonb_build_object('status', p_status, 'decided_at', to_jsonb(now()))
                         || CASE WHEN coalesce(p_edited, false) THEN jsonb_build_object('edited', true) ELSE '{}'::jsonb END,
                         true)
        END,
        updated_at = now()
    WHERE r.user_id = p_user_id AND r.version = p_version
    RETURNING r.id, r.version, r.step_states;
END
$$;

-- @@
-- Một lần sinh lại (job) của chính người gọi. Mới nhất trước khi không có p_job_id.
CREATE OR REPLACE FUNCTION app_get_roadmap_job(p_user_id text, p_job_id uuid DEFAULT NULL)
RETURNS TABLE (
  id uuid, status text, trigger text, stage text, progress smallint, alternative_id text, based_on_version integer,
  behavior_flag_id uuid, roadmap_id uuid, version integer, error_code text, error_message text,
  requested_at timestamptz, started_at timestamptz, finished_at timestamptz
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT j.id, j.status, j.trigger, j.stage, j.progress, j.alternative_id, j.based_on_version,
           j.behavior_flag_id, j.roadmap_id, j.version, j.error_code, j.error_message,
           j.requested_at, j.started_at, j.finished_at
    FROM roadmap_jobs j
    WHERE j.user_id = p_user_id AND (p_job_id IS NULL OR j.id = p_job_id)
    ORDER BY j.requested_at DESC, j.id DESC
    LIMIT 1;
END
$$;

-- @@
-- Danh sách "Xem lại" (p_mode review: đã được tự gán hũ và đánh dấu cần xem lại, ở hũ người dùng) hoặc hỏi gộp (p_mode daily_ask: đang ở
-- hũ Chưa phân loại). Không gồm dòng chuyển hũ. Mới nhất trước, tối đa 50. total_count và total_vnd là tổng của TOÀN BỘ tập thuộc chế độ
-- (trước khi cắt LIMIT), lặp lại ở mỗi dòng. Số tiền là giá trị tuyệt đối.
CREATE OR REPLACE FUNCTION app_get_review_list(p_user_id text, p_mode text DEFAULT 'review', p_limit integer DEFAULT 20)
RETURNS TABLE (
  transaction_id uuid, occurred_at timestamptz, app_date date, kind text, amount_vnd numeric, merchant text, note text,
  tx_type text, payee_id uuid, payee_name text, jar_code text, jar_name text, classified_by text,
  classification_confidence numeric, suggested_jars text[], total_count bigint, total_vnd numeric
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT t.id, t.occurred_at, t.app_date, t.kind, abs(t.amount_vnd), t.merchant, t.note,
           t.tx_type, t.payee_id, p.name, t.jar_code, j.name, t.classified_by,
           t.classification_confidence, t.suggested_jars,
           count(*) OVER (), sum(abs(t.amount_vnd)) OVER ()
    FROM transactions t
    LEFT JOIN payees p ON p.user_id = t.user_id AND p.id = t.payee_id
    LEFT JOIN jars j ON j.user_id = t.user_id AND j.code = t.jar_code
    WHERE t.user_id = p_user_id
      AND t.kind <> 'transfer'
      AND CASE
            WHEN p_mode = 'daily_ask' THEN j.system_role = 'unclassified'
            ELSE t.needs_review AND j.system_role IS DISTINCT FROM 'unclassified'
          END
    ORDER BY t.occurred_at DESC, t.id DESC
    LIMIT LEAST(GREATEST(coalesce(p_limit, 20), 1), 50);
END
$$;

-- @@
-- Câu hỏi gộp của một ngày mô phỏng (không có dòng nếu hôm đó chưa hỏi).
CREATE OR REPLACE FUNCTION app_get_review_ask(p_user_id text, p_ask_date date)
RETURNS TABLE (id uuid, ask_date date, status text, item_count integer, pending_total_vnd numeric, created_at timestamptz, resolved_at timestamptz)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT a.id, a.ask_date, a.status, a.item_count, a.pending_total_vnd, a.created_at, a.resolved_at
    FROM review_asks a
    WHERE a.user_id = p_user_id AND a.ask_date = p_ask_date
    LIMIT 1;
END
$$;

-- @@
-- Dấu hiệu đổi hành vi của người gọi (mới nhất trước), lọc theo trạng thái nếu có.
CREATE OR REPLACE FUNCTION app_list_behavior_flags(p_user_id text, p_status text DEFAULT NULL, p_limit integer DEFAULT 20)
RETURNS TABLE (
  id uuid, jar_code text, status text, method text, direction text, old_weekly_vnd numeric, new_weekly_vnd numeric,
  suspected_app_date date, change_point_date date, confirmed_app_date date, weeks_held integer, detail jsonb,
  roadmap_job_id uuid, applied_at timestamptz, created_at timestamptz
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT f.id, f.jar_code, f.status, f.method, f.direction, f.old_weekly_vnd, f.new_weekly_vnd,
           f.suspected_app_date, f.change_point_date, f.confirmed_app_date, f.weeks_held, f.detail,
           f.roadmap_job_id, f.applied_at, f.created_at
    FROM behavior_flags f
    WHERE f.user_id = p_user_id AND (p_status IS NULL OR f.status = p_status)
    ORDER BY f.created_at DESC, f.id DESC
    LIMIT LEAST(GREATEST(coalesce(p_limit, 20), 1), 50);
END
$$;

-- @@
-- Bước 2 của phân loại, phần k-NN: p_embedding là vector dạng chuỗi (ví dụ '[0.1,0.2,...]', đúng 1024 số; sai số chiều thì Postgres báo lỗi). Trả
-- tối đa p_k nhãn gần nhất của CHÍNH người gọi, distance là khoảng cách cosine (0 là giống hệt; độ giống là 1 trừ distance).
CREATE OR REPLACE FUNCTION app_knn_labeled(p_user_id text, p_embedding text, p_k integer DEFAULT 5)
RETURNS TABLE (id uuid, jar_code text, text_norm text, source text, distance double precision)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT l.id, l.jar_code, l.text_norm, l.source, (l.embedding <=> p_embedding::vector)::double precision
    FROM tx_embeddings_labeled l
    WHERE l.user_id = p_user_id
    ORDER BY l.embedding <=> p_embedding::vector
    LIMIT LEAST(GREATEST(coalesce(p_k, 5), 1), 20);
END
$$;

-- @@
-- Bước 2 của phân loại, phần khớp chuỗi chính xác (làm trước k-NN): nhãn của chính người gọi có đúng chuỗi đã chuẩn hóa này, mới nhất trước.
CREATE OR REPLACE FUNCTION app_find_labeled_exact(p_user_id text, p_text_norm text)
RETURNS TABLE (id uuid, jar_code text, source text, created_at timestamptz)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT l.id, l.jar_code, l.source, l.created_at
    FROM tx_embeddings_labeled l
    WHERE l.user_id = p_user_id AND l.text_norm = p_text_norm
    ORDER BY l.created_at DESC, l.id DESC
    LIMIT 5;
END
$$;

-- @@
REVOKE ALL ON FUNCTION app_get_resilience_score(text, date) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_roadmap(text, integer, text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_list_roadmap_versions(text, integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_save_roadmap(text, text, text, jsonb, uuid, integer, text, date, jsonb, text, text, text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_decide_roadmap_version(text, integer, text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_set_roadmap_step_state(text, integer, text, text, boolean) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_roadmap_job(text, uuid) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_review_list(text, text, integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_review_ask(text, date) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_list_behavior_flags(text, text, integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_knn_labeled(text, text, integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_find_labeled_exact(text, text) FROM PUBLIC;

-- @@
GRANT EXECUTE ON FUNCTION app_get_resilience_score(text, date) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_roadmap(text, integer, text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_list_roadmap_versions(text, integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_save_roadmap(text, text, text, jsonb, uuid, integer, text, date, jsonb, text, text, text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_decide_roadmap_version(text, integer, text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_set_roadmap_step_state(text, integer, text, text, boolean) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_roadmap_job(text, uuid) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_review_list(text, text, integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_review_ask(text, date) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_list_behavior_flags(text, text, integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_knn_labeled(text, text, integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_find_labeled_exact(text, text) TO yofina_app;
