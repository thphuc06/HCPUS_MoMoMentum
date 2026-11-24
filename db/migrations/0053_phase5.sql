-- 0053_phase5: hồ sơ hành vi, bản tin của cổng giá trị, kho tri thức RAG, nhật ký xóa dữ liệu, đọc trace cho bảng vận hành (phase 5).
--
-- * behavior_profiles: hồ sơ hành vi theo NGÀY MÔ PHỎNG (F7): đặc trưng (`features`, jsonb object), nhóm hành vi (`segment`), nhận xét
--   kèm bằng chứng số (`insights`, mảng tối đa 6), MỘT việc cần làm (`next_step`), phiên bản cấu hình (`config_version`). Một dòng mỗi
--   (người dùng, ngày): batch đêm tính lại thì ghi đè. Hình dạng jsonb là `BehaviorProfileData` của contracts/blocks/behavior_insight.
-- * nudges (mở rộng 0010): bản tin chủ động của cổng giá trị (`source = system`, FR13), tối đa MỘT mỗi (người dùng, ngày mô phỏng),
--   DB bảo đảm bằng chỉ mục duy nhất một phần. Thêm giá trị ước tính (`value_vnd`), lý do cổng (`gate_reason`), tiêu đề và lý do hiển
--   thị (`title`, `body`), phản hồi của người dùng (`outcome`, `outcome_at`). `kind` nới thêm ba loại chỉ cổng sinh; bản tin của cổng
--   có `fire_on` = ngày tạo (CHECK cũ đòi sau ngày tạo nên được thay).
-- * kb_documents, kb_chunks: kho tri thức RAG DÙNG CHUNG (không theo người dùng, không có user_id, không RLS), như các bảng tra
--   tx_type_map, fee_schedules của 0005: yofina_app chỉ SELECT; nạp và sửa bằng script đồng bộ chạy secret MASTER (cùng cách nạp
--   db/seed). Lý do: nội dung là tài liệu công khai mô phỏng, giống nhau với mọi người dùng; không cho role ứng dụng ghi để một Lambda
--   bị chèn lệnh không đầu độc được kho trích dẫn. Đoạn (`kb_chunks`) có embedding vector(1024) (vai `embedding`, Cohere) với chỉ mục
--   HNSW cosine, và `tsv` (tsvector cấu hình simple trên văn bản đã bỏ dấu bằng app_fold_text của 0050, cột sinh STORED) với chỉ mục
--   GIN. Truy xuất lai: app_kb_search hợp nhất hai danh sách bằng Reciprocal Rank Fusion (k = 60), lọc kho, sản phẩm, ngày hiệu lực.
-- * data_deletions: nhật ký "Xóa dữ liệu của tôi": trạng thái từng bước (s3, memory, aurora) và số lượng đã xóa, KHÔNG chứa dữ liệu đã
--   xóa. Không có khóa ngoại tới users vì dòng nhật ký phải còn sau khi users của người đó bị xóa. RLS theo user_id; yofina_app không
--   có DELETE.
-- * app_delete_user_data (SECURITY DEFINER): xóa MỌI dòng của một người dùng ở mọi bảng có cột user_id (kể cả audit_events, bảng chỉ
--   thêm với yofina_app) rồi dòng users, trong transaction của lệnh gọi; chỉ chạy khi có dòng data_deletions `running` của chính người
--   đó (Lambda chỉ tạo dòng đó sau khi kiểm token xác nhận). Duyệt bảng theo information_schema nên bảng mới của phase sau cũng bị xóa.
-- * app_ops_list_traces, app_ops_get_trace, app_ops_summary, app_ops_model_calls_by_day (SECURITY DEFINER): bảng vận hành đọc bản ghi
--   lượt của MỌI người dùng (RLS của audit_events theo từng người nên yofina_app không tự đọc được). Chỉ trả cột đã chọn; người dùng
--   hiện bằng user_ref (12 ký tự hex đầu của sha256 của user_id), không trả user_id, conversation_id, câu hỏi hay câu trả lời. Quyền
--   nhóm Cognito `ops` do Lambda kiểm TRƯỚC khi gọi (DB không biết JWT).
-- * audit_events: nới CHECK của intent từ mười (0052) thành mười bốn (thêm behavior, knowledge, ingest, memory; wallet.AUDIT_INTENTS).
--
-- Hàm đọc theo người dùng: SECURITY INVOKER, tự đặt app.user_id, có LIMIT. SECURITY DEFINER chỉ cho việc cần vượt RLS theo thiết kế
-- (như app_list_forecast_users của 0009): REVOKE khỏi PUBLIC, chỉ yofina_app được EXECUTE, SET search_path cố định.
-- Quy ước như 0005 tới 0052 (db/README.md): chạy bằng secret MASTER, một transaction, tách bằng dòng "-- @@", viết lại được, RLS
-- FORCE. Không viết dấu hai chấm dính liền chữ cái hoặc gạch dưới. Không sửa 0001 tới 0052 (migrator kiểm checksum). Đặt lại demo phải
-- xóa thêm behavior_profiles (RESET_DELETES ở gateway/tools/ledger, việc của luồng p5-behavior); data_deletions và kb_* không bị đặt lại.

CREATE EXTENSION IF NOT EXISTS vector;

-- @@
-- ===== behavior_profiles =====
CREATE TABLE IF NOT EXISTS behavior_profiles (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  app_date        date NOT NULL,
  ready           boolean NOT NULL,
  config_version  text NOT NULL CHECK (length(config_version) BETWEEN 1 AND 40),
  history_days    integer NOT NULL CHECK (history_days >= 0),
  headline        text NOT NULL CHECK (length(headline) BETWEEN 1 AND 160),
  features        jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(features) = 'object'),
  segment         jsonb CHECK (segment IS NULL OR jsonb_typeof(segment) = 'object'),
  insights        jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(insights) = 'array' AND jsonb_array_length(insights) <= 6),
  next_step       jsonb CHECK (next_step IS NULL OR jsonb_typeof(next_step) = 'object'),
  source          text NOT NULL CHECK (source IN ('nightly', 'reset', 'manual')),
  model           text CHECK (model IS NULL OR length(model) BETWEEN 1 AND 80),
  computed_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, app_date),
  CHECK (ready OR (jsonb_array_length(insights) = 0 AND next_step IS NULL)),
  CHECK (NOT ready OR (jsonb_array_length(insights) >= 1 AND next_step IS NOT NULL)),
  CHECK (octet_length(features::text) + octet_length(insights::text) + coalesce(octet_length(segment::text), 0)
         + coalesce(octet_length(next_step::text), 0) <= 40000)
);

-- @@
-- ===== nudges: bản tin của cổng giá trị (mở rộng 0010) =====
ALTER TABLE nudges ADD COLUMN IF NOT EXISTS value_vnd numeric(14,0) CHECK (value_vnd IS NULL OR value_vnd >= 0);

-- @@
ALTER TABLE nudges ADD COLUMN IF NOT EXISTS gate_reason jsonb CHECK (gate_reason IS NULL OR jsonb_typeof(gate_reason) = 'object');

-- @@
ALTER TABLE nudges ADD COLUMN IF NOT EXISTS title text CHECK (title IS NULL OR length(title) BETWEEN 1 AND 80);

-- @@
ALTER TABLE nudges ADD COLUMN IF NOT EXISTS body text CHECK (body IS NULL OR length(body) BETWEEN 1 AND 200);

-- @@
ALTER TABLE nudges ADD COLUMN IF NOT EXISTS outcome text CHECK (outcome IS NULL OR outcome IN ('acted', 'dismissed', 'snoozed', 'less_like_this'));

-- @@
ALTER TABLE nudges ADD COLUMN IF NOT EXISTS outcome_at timestamptz;

-- @@
ALTER TABLE nudges DROP CONSTRAINT IF EXISTS nudges_outcome_at_check;

-- @@
ALTER TABLE nudges ADD CONSTRAINT nudges_outcome_at_check CHECK ((outcome IS NULL) = (outcome_at IS NULL));

-- @@
-- Loại: sáu loại lên lịch được của 0010 (wallet.NUDGE_KINDS) và ba loại chỉ cổng giá trị sinh (wallet.ALL_NUDGE_KINDS).
ALTER TABLE nudges DROP CONSTRAINT IF EXISTS nudges_kind_check;

-- @@
ALTER TABLE nudges ADD CONSTRAINT nudges_kind_check CHECK (kind IN ('runout_warning', 'obligation_due', 'salary_pending', 'review_needed', 'low_data', 'purchase_review', 'roadmap_proposed', 'resilience_drop', 'behavior_insight'));

-- @@
-- CHECK (fire_on > created_app_date) của 0010 là ràng buộc bảng không đặt tên (Postgres tự đặt tên): tìm theo định nghĩa rồi bỏ, thay bằng
-- ràng buộc có tên cho phép bản tin của cổng (source system) hiện ngay trong ngày tạo.
DO $$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT c.conname FROM pg_constraint c
    WHERE c.conrelid = 'public.nudges'::regclass AND c.contype = 'c'
      AND pg_get_constraintdef(c.oid) LIKE '%fire_on > created_app_date%'
      AND c.conname <> 'nudges_fire_on_check'
  LOOP
    EXECUTE format('ALTER TABLE nudges DROP CONSTRAINT %I', r.conname);
  END LOOP;
END
$$;

-- @@
ALTER TABLE nudges DROP CONSTRAINT IF EXISTS nudges_fire_on_check;

-- @@
ALTER TABLE nudges ADD CONSTRAINT nudges_fire_on_check CHECK (fire_on > created_app_date OR (source = 'system' AND fire_on = created_app_date));

-- @@
-- Bản tin của cổng luôn có tiêu đề, lý do hiển thị và lý do cổng (để giải thích và truy vết).
ALTER TABLE nudges DROP CONSTRAINT IF EXISTS nudges_system_fields_check;

-- @@
ALTER TABLE nudges ADD CONSTRAINT nudges_system_fields_check CHECK (source <> 'system' OR (title IS NOT NULL AND body IS NOT NULL AND gate_reason IS NOT NULL));

-- @@
-- Tối đa MỘT bản tin của cổng mỗi (người dùng, ngày mô phỏng); bản đã hủy không tính.
CREATE UNIQUE INDEX IF NOT EXISTS nudges_system_one_per_day_idx ON nudges (user_id, fire_on) WHERE source = 'system' AND status <> 'cancelled';

-- @@
-- ===== kb_documents, kb_chunks: kho tri thức dùng chung =====
CREATE TABLE IF NOT EXISTS kb_documents (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_key         text NOT NULL CHECK (doc_key ~ '^[a-z0-9][a-z0-9_-]{0,63}$'),
  version         integer NOT NULL DEFAULT 1 CHECK (version BETWEEN 1 AND 10000),
  corpus          text NOT NULL CHECK (corpus IN ('fees', 'personal_finance', 'suitability')),
  title           text NOT NULL CHECK (length(title) BETWEEN 1 AND 120),
  product_code    text CHECK (product_code IS NULL OR product_code ~ '^[a-z][a-z0-9_]{0,31}$'),
  effective_from  date NOT NULL,
  effective_to    date,
  source_name     text NOT NULL CHECK (length(source_name) BETWEEN 1 AND 200),
  source_url      text NOT NULL CHECK (source_url ~ '^https://' AND length(source_url) <= 500),
  lang            text NOT NULL DEFAULT 'vi' CHECK (lang IN ('vi', 'en')),
  content_sha256  text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'retired')),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (doc_key, version),
  CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

-- @@
-- Mỗi tài liệu một phiên bản đang dùng; phiên bản cũ thành retired (giữ để đọc lại trích dẫn cũ, không tìm thấy nữa).
CREATE UNIQUE INDEX IF NOT EXISTS kb_documents_one_active_idx ON kb_documents (doc_key) WHERE status = 'active';

-- @@
CREATE TABLE IF NOT EXISTS kb_chunks (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id   uuid NOT NULL REFERENCES kb_documents (id) ON DELETE CASCADE,
  seq           integer NOT NULL CHECK (seq >= 0),
  clause_ref    text CHECK (clause_ref IS NULL OR length(clause_ref) BETWEEN 1 AND 40),
  heading       text CHECK (heading IS NULL OR length(heading) BETWEEN 1 AND 120),
  body          text NOT NULL CHECK (length(body) BETWEEN 1 AND 4000),
  token_count   integer CHECK (token_count IS NULL OR token_count >= 0),
  embed_model   text NOT NULL CHECK (length(embed_model) BETWEEN 1 AND 80),
  embedding     vector(1024) NOT NULL,
  tsv           tsvector GENERATED ALWAYS AS (to_tsvector('simple', app_fold_text(coalesce(heading, '') || ' ' || body))) STORED,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, seq)
);

-- @@
-- HNSW cosine như tx_embeddings_labeled của 0052 (Aurora pgvector 0.8.2, bản cục bộ 0.6.2: chỉ dùng thứ có ở cả hai).
CREATE INDEX IF NOT EXISTS kb_chunks_hnsw_idx ON kb_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- @@
CREATE INDEX IF NOT EXISTS kb_chunks_tsv_idx ON kb_chunks USING gin (tsv);

-- @@
-- ===== data_deletions: nhật ký xóa dữ liệu (không có khóa ngoại tới users, xem chú thích đầu file) =====
CREATE TABLE IF NOT EXISTS data_deletions (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       text NOT NULL CHECK (length(user_id) BETWEEN 1 AND 128),
  scope         text NOT NULL DEFAULT 'all' CHECK (scope IN ('all')),
  status        text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'done', 'partial', 'failed')),
  steps         jsonb NOT NULL CHECK (jsonb_typeof(steps) = 'object' AND octet_length(steps::text) <= 2000),
  trace_id      text CHECK (trace_id IS NULL OR length(trace_id) BETWEEN 1 AND 64),
  requested_at  timestamptz NOT NULL DEFAULT now(),
  finished_at   timestamptz,
  updated_at    timestamptz NOT NULL DEFAULT now(),
  CHECK ((status = 'running') = (finished_at IS NULL))
);

-- @@
CREATE UNIQUE INDEX IF NOT EXISTS data_deletions_one_running_idx ON data_deletions (user_id) WHERE status = 'running';

-- @@
CREATE INDEX IF NOT EXISTS data_deletions_user_time_idx ON data_deletions (user_id, requested_at DESC);

-- @@
-- ===== audit_events: nới CHECK ý định (mười của 0052 thành mười bốn) =====
ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS audit_events_intent_check;

-- @@
ALTER TABLE audit_events ADD CONSTRAINT audit_events_intent_check CHECK (intent IS NULL OR intent IN ('lookup', 'what_if', 'affordability', 'profile_update', 'move', 'out_of_scope', 'chitchat', 'resilience', 'stress', 'roadmap', 'behavior', 'knowledge', 'ingest', 'memory'));

-- @@
-- ===== RLS: ENABLE và FORCE, policy user_isolation theo app.user_id (kb_* dùng chung nên không có RLS) =====
ALTER TABLE behavior_profiles ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE behavior_profiles FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON behavior_profiles;

-- @@
CREATE POLICY user_isolation ON behavior_profiles
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
ALTER TABLE data_deletions ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE data_deletions FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON data_deletions;

-- @@
CREATE POLICY user_isolation ON data_deletions
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
-- ===== Quyền của yofina_app (tối thiểu) =====
GRANT SELECT, INSERT, UPDATE, DELETE ON behavior_profiles TO yofina_app;

-- @@
-- Kho tri thức: chỉ đọc (nạp bằng secret MASTER).
GRANT SELECT ON kb_documents TO yofina_app;

-- @@
GRANT SELECT ON kb_chunks TO yofina_app;

-- @@
-- Nhật ký xóa: thêm và cập nhật trạng thái, không xóa.
GRANT SELECT, INSERT, UPDATE ON data_deletions TO yofina_app;

-- @@
-- ===== Hàm đọc theo người dùng (SECURITY INVOKER) =====
-- Hồ sơ hành vi mới nhất không sau ngày p_app_date (ngày mô phỏng; NULL là mới nhất).
CREATE OR REPLACE FUNCTION app_get_behavior_profile(p_user_id text, p_app_date date DEFAULT NULL)
RETURNS TABLE (
  id uuid, app_date date, ready boolean, config_version text, history_days integer, headline text, features jsonb,
  segment jsonb, insights jsonb, next_step jsonb, source text, model text, computed_at timestamptz
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT b.id, b.app_date, b.ready, b.config_version, b.history_days, b.headline, b.features,
           b.segment, b.insights, b.next_step, b.source, b.model, b.computed_at
    FROM behavior_profiles b
    WHERE b.user_id = p_user_id AND (p_app_date IS NULL OR b.app_date <= p_app_date)
    ORDER BY b.app_date DESC
    LIMIT 1;
END
$$;

-- @@
-- Bản tin của cổng cho ngày mô phỏng p_app_date (tối đa một dòng; bản đã hủy không tính).
CREATE OR REPLACE FUNCTION app_get_today_nudge(p_user_id text, p_app_date date)
RETURNS TABLE (
  id uuid, kind text, fire_on date, jar_code text, title text, body text, value_vnd numeric, gate_reason jsonb,
  status text, outcome text, outcome_at timestamptz, trace_id text, created_at timestamptz
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT n.id, n.kind, n.fire_on, n.jar_code, n.title, n.body, n.value_vnd, n.gate_reason,
           n.status, n.outcome, n.outcome_at, n.trace_id, n.created_at
    FROM nudges n
    WHERE n.user_id = p_user_id AND n.source = 'system' AND n.fire_on = p_app_date AND n.status <> 'cancelled'
    ORDER BY n.created_at DESC
    LIMIT 1;
END
$$;

-- @@
-- Phản hồi của người dùng với bản tin của cổng, theo loại, từ ngày p_since (ngày mô phỏng): cổng dùng để hạ bậc loại bị "Ít nhắc loại
-- này" và để không nhắc lại loại vừa bị bỏ qua.
CREATE OR REPLACE FUNCTION app_nudge_outcome_stats(p_user_id text, p_since date)
RETURNS TABLE (kind text, shown bigint, acted bigint, dismissed bigint, snoozed bigint, less_like_this bigint, last_outcome_at timestamptz)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT n.kind, count(*),
           count(*) FILTER (WHERE n.outcome = 'acted'),
           count(*) FILTER (WHERE n.outcome = 'dismissed'),
           count(*) FILTER (WHERE n.outcome = 'snoozed'),
           count(*) FILTER (WHERE n.outcome = 'less_like_this'),
           max(n.outcome_at)
    FROM nudges n
    WHERE n.user_id = p_user_id AND n.source = 'system' AND n.fire_on >= p_since
    GROUP BY n.kind
    ORDER BY n.kind
    LIMIT 20;
END
$$;

-- @@
-- Ghi phản hồi cho MỘT bản tin của cổng (idempotent: cùng outcome thì không đổi outcome_at). dismissed cũng đổi status thành dismissed.
-- Không phải bản tin của người gọi, không phải source system hoặc đã hủy: không có dòng nào (REST trả 404 NUDGE_NOT_FOUND).
CREATE OR REPLACE FUNCTION app_set_nudge_outcome(p_user_id text, p_nudge_id uuid, p_outcome text)
RETURNS TABLE (id uuid, outcome text, outcome_at timestamptz)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  IF p_outcome IS NULL OR p_outcome NOT IN ('acted', 'dismissed', 'snoozed', 'less_like_this') THEN
    RAISE EXCEPTION 'PARAMS_INVALID: outcome phải là acted, dismissed, snoozed hoặc less_like_this';
  END IF;
  RETURN QUERY
    UPDATE nudges n
       SET outcome = p_outcome,
           outcome_at = CASE WHEN n.outcome IS NOT DISTINCT FROM p_outcome THEN n.outcome_at ELSE now() END,
           status = CASE WHEN p_outcome = 'dismissed' THEN 'dismissed' ELSE n.status END,
           updated_at = now()
     WHERE n.user_id = p_user_id AND n.id = p_nudge_id AND n.source = 'system' AND n.status <> 'cancelled'
    RETURNING n.id, n.outcome, n.outcome_at;
END
$$;

-- @@
-- ===== Kho tri thức: truy xuất lai (SECURITY INVOKER, dữ liệu dùng chung nên không đặt app.user_id) =====
-- p_query_embedding là vector dạng chuỗi '[0.1,0.2,...]' (đúng 1024 số) hoặc NULL (khi không tính được embedding: chỉ còn từ khóa).
-- Từ khóa: bỏ dấu bằng app_fold_text rồi plainto_tsquery cấu hình simple, nối các từ bằng HOẶC (câu hỏi tự nhiên dài, đòi đủ mọi từ thì
-- gần như không khớp). Mỗi đường lấy p_candidates ứng viên trong các đoạn đủ điều kiện (tài liệu active, còn hiệu lực ở p_on_date, đúng
-- kho, đúng sản phẩm hoặc không gắn sản phẩm), rồi hợp nhất RRF: điểm = tổng 1/(60 + hạng) chia cho 2/61 (về 0..1, cùng công thức
-- yofina_core.knowledge.rrf_score). Trả tối đa p_k đoạn (1..8), điểm giảm dần.
CREATE OR REPLACE FUNCTION app_kb_search(
  p_query_text text, p_query_embedding text, p_on_date date, p_corpus text DEFAULT NULL, p_product text DEFAULT NULL,
  p_k integer DEFAULT 4, p_candidates integer DEFAULT 40
)
RETURNS TABLE (
  chunk_id uuid, document_id uuid, doc_key text, title text, corpus text, clause_ref text, heading text, chunk_text text,
  product_code text, effective_from date, effective_to date, source_name text, source_url text,
  vector_rank integer, text_rank integer, score double precision
)
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_k integer := LEAST(GREATEST(coalesce(p_k, 4), 1), 8);
  v_c integer := LEAST(GREATEST(coalesce(p_candidates, 40), 1), 200);
  v_vec vector(1024);
  v_q tsquery;
BEGIN
  IF p_on_date IS NULL THEN
    RAISE EXCEPTION 'PARAMS_INVALID: thiếu ngày hiệu lực';
  END IF;
  IF p_query_embedding IS NOT NULL THEN
    v_vec := p_query_embedding::vector(1024);
  END IF;
  IF length(btrim(coalesce(p_query_text, ''))) > 0 THEN
    v_q := nullif(replace(plainto_tsquery('simple', app_fold_text(p_query_text))::text, ' & ', ' | '), '')::tsquery;
  END IF;
  RETURN QUERY
    WITH eligible AS (
      SELECT c.id AS cid
      FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id
      WHERE d.status = 'active'
        AND d.effective_from <= p_on_date AND (d.effective_to IS NULL OR d.effective_to >= p_on_date)
        AND (p_corpus IS NULL OR d.corpus = p_corpus)
        AND (p_product IS NULL OR d.product_code IS NULL OR d.product_code = p_product)
    ),
    vec AS (
      SELECT x.cid, (row_number() OVER (ORDER BY x.dist, x.cid))::integer AS rnk
      FROM (
        SELECT c.id AS cid, c.embedding <=> v_vec AS dist
        FROM kb_chunks c JOIN eligible e ON e.cid = c.id
        WHERE v_vec IS NOT NULL
        ORDER BY c.embedding <=> v_vec, c.id
        LIMIT v_c
      ) x
    ),
    txt AS (
      SELECT x.cid, (row_number() OVER (ORDER BY x.rank_cd DESC, x.cid))::integer AS rnk
      FROM (
        SELECT c.id AS cid, ts_rank_cd(c.tsv, v_q) AS rank_cd
        FROM kb_chunks c JOIN eligible e ON e.cid = c.id
        WHERE v_q IS NOT NULL AND c.tsv @@ v_q
        ORDER BY ts_rank_cd(c.tsv, v_q) DESC, c.id
        LIMIT v_c
      ) x
    ),
    fused AS (
      SELECT coalesce(v.cid, t.cid) AS cid, v.rnk AS vr, t.rnk AS tr,
             ((coalesce(1.0 / (60 + v.rnk), 0) + coalesce(1.0 / (60 + t.rnk), 0)) / (2.0 / 61))::double precision AS sc
      FROM vec v FULL JOIN txt t ON t.cid = v.cid
    )
    SELECT c.id, d.id, d.doc_key, d.title, d.corpus, c.clause_ref, c.heading, c.body,
           d.product_code, d.effective_from, d.effective_to, d.source_name, d.source_url,
           f.vr, f.tr, f.sc
    FROM fused f JOIN kb_chunks c ON c.id = f.cid JOIN kb_documents d ON d.id = c.document_id
    ORDER BY f.sc DESC, c.id
    LIMIT v_k;
END
$$;

-- @@
-- ===== Xóa dữ liệu của tôi (SECURITY DEFINER) =====
-- Xóa mọi dòng của p_user_id ở mọi bảng public có cột user_id (trừ data_deletions), rồi dòng users (khóa ngoại CASCADE dọn phần còn lại),
-- và kiểm không còn dòng nào. Trả số dòng đã đếm TRƯỚC khi xóa theo từng bảng (users là 1 nếu có hồ sơ). Chỉ chạy khi p_deletion_id là
-- lần xóa đang chạy (running) của chính người đó: Lambda tạo dòng đó sau khi kiểm token xác nhận, nên hàm không xóa được người khác dù
-- gọi trực tiếp với user_id khác. Đặt app.user_id cho người đó để nếu RLS áp cho chủ hàm thì vẫn chỉ thấy dòng của họ.
CREATE OR REPLACE FUNCTION app_delete_user_data(p_user_id text, p_deletion_id uuid)
RETURNS TABLE (relname text, deleted bigint)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  t record;
  v_n bigint;
  v_left bigint := 0;
BEGIN
  IF p_user_id IS NULL OR length(p_user_id) = 0 THEN
    RAISE EXCEPTION 'PARAMS_INVALID: thiếu người dùng';
  END IF;
  PERFORM set_config('app.user_id', p_user_id, true);
  PERFORM 1 FROM data_deletions x WHERE x.id = p_deletion_id AND x.user_id = p_user_id AND x.status = 'running';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'PARAMS_INVALID: không có lần xóa đang chạy của người dùng này';
  END IF;
  FOR t IN
    SELECT c.table_name AS tbl
    FROM information_schema.columns c JOIN information_schema.tables s
      ON s.table_schema = c.table_schema AND s.table_name = c.table_name
    WHERE c.table_schema = 'public' AND c.column_name = 'user_id' AND s.table_type = 'BASE TABLE'
      AND c.table_name <> 'data_deletions'
    ORDER BY c.table_name
  LOOP
    EXECUTE format('SELECT count(*) FROM %I WHERE user_id = $1', t.tbl) INTO v_n USING p_user_id;
    IF v_n > 0 THEN
      relname := t.tbl;
      deleted := v_n;
      RETURN NEXT;
    END IF;
  END LOOP;
  -- Bảng không có khóa ngoại tới users (audit_events, forecasts, forecast_jar_summaries...) không được CASCADE dọn.
  DELETE FROM audit_events a WHERE a.user_id = p_user_id;
  DELETE FROM users u WHERE u.id = p_user_id;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  IF v_n > 0 THEN
    relname := 'users';
    deleted := v_n;
    RETURN NEXT;
  END IF;
  FOR t IN
    SELECT c.table_name AS tbl
    FROM information_schema.columns c JOIN information_schema.tables s
      ON s.table_schema = c.table_schema AND s.table_name = c.table_name
    WHERE c.table_schema = 'public' AND c.column_name = 'user_id' AND s.table_type = 'BASE TABLE'
      AND c.table_name <> 'data_deletions'
    ORDER BY c.table_name
  LOOP
    EXECUTE format('DELETE FROM %I WHERE user_id = $1', t.tbl) USING p_user_id;
    EXECUTE format('SELECT count(*) FROM %I WHERE user_id = $1', t.tbl) INTO v_n USING p_user_id;
    v_left := v_left + v_n;
  END LOOP;
  IF v_left > 0 THEN
    RAISE EXCEPTION 'INTERNAL_ERROR: còn dữ liệu của người dùng sau khi xóa';
  END IF;
  RETURN;
END
$$;

-- @@
-- ===== Bảng vận hành (SECURITY DEFINER, đọc audit_events của mọi người dùng; quyền nhóm ops do Lambda kiểm) =====
-- Danh sách bản ghi lượt, mới nhất trước, phân trang theo (created_at, trace_id) của dòng cuối trang trước. Không trả user_id hay
-- conversation_id; user_ref là 12 ký tự hex đầu của sha256(user_id).
CREATE OR REPLACE FUNCTION app_ops_list_traces(
  p_from timestamptz, p_to timestamptz, p_intent text DEFAULT NULL, p_outcome text DEFAULT NULL, p_min_duration integer DEFAULT NULL,
  p_before_created timestamptz DEFAULT NULL, p_before_trace text DEFAULT NULL, p_limit integer DEFAULT 50
)
RETURNS TABLE (
  trace_id text, created_at timestamptz, user_ref text, intent text, outcome text, code text, duration_ms integer,
  token_usage jsonb, step_timings jsonb, rules_checked jsonb
)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
  IF p_from IS NULL OR p_to IS NULL OR p_to < p_from THEN
    RAISE EXCEPTION 'PARAMS_INVALID: khoảng thời gian không hợp lệ';
  END IF;
  RETURN QUERY
    SELECT a.trace_id, a.created_at, left(encode(sha256(convert_to(a.user_id, 'UTF8')), 'hex'), 12), a.intent, a.outcome, a.code,
           a.duration_ms, a.token_usage, a.step_timings, a.rules_checked
    FROM audit_events a
    WHERE a.event_type = 'agent_turn' AND a.trace_id IS NOT NULL
      AND a.created_at >= p_from AND a.created_at <= p_to
      AND (p_intent IS NULL OR a.intent = p_intent)
      AND (p_outcome IS NULL OR a.outcome = p_outcome)
      AND (p_min_duration IS NULL OR a.duration_ms >= p_min_duration)
      AND (p_before_created IS NULL OR (a.created_at, a.trace_id) < (p_before_created, coalesce(p_before_trace, '')))
    ORDER BY a.created_at DESC, a.trace_id DESC
    LIMIT LEAST(GREATEST(coalesce(p_limit, 50), 1), 100);
END
$$;

-- @@
-- Một bản ghi lượt theo trace_id (của bất kỳ người dùng nào), đủ cột cho màn trace; không có user_id và conversation_id.
CREATE OR REPLACE FUNCTION app_ops_get_trace(p_trace_id text)
RETURNS TABLE (
  trace_id text, created_at timestamptz, user_ref text, intent text, outcome text, code text, data_used jsonb, rules_checked jsonb,
  confidence jsonb, blocks_emitted jsonb, token_usage jsonb, step_timings jsonb, duration_ms integer
)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
  RETURN QUERY
    SELECT a.trace_id, a.created_at, left(encode(sha256(convert_to(a.user_id, 'UTF8')), 'hex'), 12), a.intent, a.outcome, a.code,
           a.data_used, a.rules_checked, a.confidence, a.blocks_emitted, a.token_usage, a.step_timings, a.duration_ms
    FROM audit_events a
    WHERE a.event_type = 'agent_turn' AND a.trace_id = p_trace_id
    ORDER BY a.created_at DESC
    LIMIT 1;
END
$$;

-- @@
-- Số tổng hợp trong khoảng thời gian thật (tối đa 31 ngày): lượt, độ trễ p50 và p95, lần gọi tool (bước có tên chứa ba gạch dưới) và
-- lỗi tool (status error hoặc denied), luật fail, token và lượt gọi model.
CREATE OR REPLACE FUNCTION app_ops_summary(p_from timestamptz, p_to timestamptz)
RETURNS TABLE (
  turns bigint, turns_rejected bigint, turns_error bigint, p50_ms integer, p95_ms integer, tool_calls bigint, tool_errors bigint,
  rule_fails bigint, input_tokens bigint, output_tokens bigint, model_calls bigint
)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
  IF p_from IS NULL OR p_to IS NULL OR p_to < p_from OR p_to - p_from > interval '31 days' THEN
    RAISE EXCEPTION 'PARAMS_INVALID: khoảng thời gian phải hợp lệ và không quá 31 ngày';
  END IF;
  RETURN QUERY
    WITH t AS (
      SELECT a.outcome, a.duration_ms, a.step_timings, a.rules_checked, a.token_usage
      FROM audit_events a
      WHERE a.event_type = 'agent_turn' AND a.created_at >= p_from AND a.created_at <= p_to
    )
    SELECT count(*),
           count(*) FILTER (WHERE t.outcome = 'rejected'),
           count(*) FILTER (WHERE t.outcome = 'error'),
           (percentile_cont(0.5) WITHIN GROUP (ORDER BY t.duration_ms))::integer,
           (percentile_cont(0.95) WITHIN GROUP (ORDER BY t.duration_ms))::integer,
           coalesce(sum((SELECT count(*) FROM jsonb_array_elements(coalesce(t.step_timings, '[]'::jsonb)) s
                          WHERE position('___' in (s ->> 'step')) > 0)), 0)::bigint,
           coalesce(sum((SELECT count(*) FROM jsonb_array_elements(coalesce(t.step_timings, '[]'::jsonb)) s
                          WHERE position('___' in (s ->> 'step')) > 0 AND s ->> 'status' IN ('error', 'denied'))), 0)::bigint,
           coalesce(sum((SELECT count(*) FROM jsonb_array_elements(coalesce(t.rules_checked, '[]'::jsonb)) r
                          WHERE r ->> 'outcome' = 'fail')), 0)::bigint,
           coalesce(sum((t.token_usage ->> 'input_tokens')::bigint), 0)::bigint,
           coalesce(sum((t.token_usage ->> 'output_tokens')::bigint), 0)::bigint,
           coalesce(sum((t.token_usage ->> 'model_calls')::bigint), 0)::bigint
    FROM t
    LIMIT 1;
END
$$;

-- @@
-- Lượt gọi model theo ngày UTC của thời điểm thật (trần gọi model tính theo ngày thật), tối đa 31 ngày.
CREATE OR REPLACE FUNCTION app_ops_model_calls_by_day(p_from timestamptz, p_to timestamptz)
RETURNS TABLE (day date, turns bigint, model_calls bigint)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
  IF p_from IS NULL OR p_to IS NULL OR p_to < p_from OR p_to - p_from > interval '31 days' THEN
    RAISE EXCEPTION 'PARAMS_INVALID: khoảng thời gian phải hợp lệ và không quá 31 ngày';
  END IF;
  RETURN QUERY
    SELECT (a.created_at AT TIME ZONE 'UTC')::date AS d, count(*),
           coalesce(sum((a.token_usage ->> 'model_calls')::bigint), 0)::bigint
    FROM audit_events a
    WHERE a.event_type = 'agent_turn' AND a.created_at >= p_from AND a.created_at <= p_to
    GROUP BY 1
    ORDER BY 1
    LIMIT 32;
END
$$;

-- @@
REVOKE ALL ON FUNCTION app_get_behavior_profile(text, date) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_today_nudge(text, date) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_nudge_outcome_stats(text, date) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_set_nudge_outcome(text, uuid, text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_kb_search(text, text, date, text, text, integer, integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_delete_user_data(text, uuid) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_ops_list_traces(timestamptz, timestamptz, text, text, integer, timestamptz, text, integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_ops_get_trace(text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_ops_summary(timestamptz, timestamptz) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_ops_model_calls_by_day(timestamptz, timestamptz) FROM PUBLIC;

-- @@
GRANT EXECUTE ON FUNCTION app_get_behavior_profile(text, date) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_today_nudge(text, date) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_nudge_outcome_stats(text, date) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_set_nudge_outcome(text, uuid, text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_kb_search(text, text, date, text, text, integer, integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_delete_user_data(text, uuid) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_ops_list_traces(timestamptz, timestamptz, text, text, integer, timestamptz, text, integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_ops_get_trace(text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_ops_summary(timestamptz, timestamptz) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_ops_model_calls_by_day(timestamptz, timestamptz) TO yofina_app;
