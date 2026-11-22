-- 0050_ingest: nạp dữ liệu từ ảnh và CSV (F6, phase 5, luồng A). Không sửa 0001 tới 0009 (migrator kiểm checksum).
--
-- Nội dung (quyết định chi tiết: contracts/README.md mục "Phase 5 (F6): nạp dữ liệu"):
-- * transactions.funding_source thêm 'external': chi hoặc thu NGOÀI ví (ngân hàng khác, thẻ), nạp từ tệp. Dòng external có
--   jar_code (dòng chi) để tính hành vi chi của hũ nhưng KHÔNG BAO GIỜ đổi số dư hũ (như credit). Không có dòng chuyển hũ
--   external, không gắn nghĩa vụ. Bất biến của sổ cái giữ nguyên: số dư mỗi hũ = tổng amount_vnd các dòng funding_source jar.
-- * Bảng mới (RLS FORCE theo app.user_id): ingest_jobs (một lần nạp một tệp), ingest_rows (dòng trích được, ĐÃ che PII, chờ
--   duyệt), consents (đồng ý theo nguồn nạp). Không cột nào chứa ảnh hay văn bản thô chưa che.
-- * Thay hàm app_get_daily_spend của 0005 (cùng chữ ký, cùng kiểu trả về): nay tính dòng chi funding_source jar VÀ external.
-- * Thay hàm app_get_forecast_context của 0009 (cùng chữ ký, cùng hình dạng payload): coverage.spend_vnd cộng chi ngoài ví,
--   coverage.income_vnd cộng thu nhập ngoài ví. Người dùng không có dòng external nào thì mọi số Y HỆT bản 0009.
-- * Thay app_get_cashflow_summary của 0005: by_jar và income_by_type chỉ còn là dòng tiền của VÍ (không gồm external), thêm
--   khóa external tách riêng. Thay app_get_overview (0007) và app_get_overview_extras (0005): giao dịch gần đây của Tổng quan
--   là của ví nên không gồm dòng external (lịch sử Hoạt động và Chi tiết hũ vẫn có, kèm funding_source).
-- * Hàm mới cho luồng nạp: tạo job, cập nhật job, chèn dòng, đọc job và dòng, sửa hũ một dòng, chốt dòng, đồng ý, độ phủ
--   hiện tại (cùng số với app_get_forecast_context), khử trùng với sổ cái (app_find_ingest_matches, cửa sổ là tham số).
--
-- Quy ước như 0005 (db/README.md): chạy bằng secret MASTER qua Lambda migrator, một transaction, tách câu lệnh bằng dòng chỉ
-- gồm "-- @@", viết lại được, hàm SECURITY INVOKER tự đặt app.user_id, mọi truy vấn nhiều dòng có LIMIT. Không viết dấu hai
-- chấm dính liền chữ cái hoặc gạch dưới (kể cả trong chú thích); ép kiểu bằng hai dấu hai chấm thì được.

-- ===== transactions: nguồn trả external =====
-- jar và credit như 0005; external chỉ với chi (bắt buộc có jar_code) hoặc thu; không chuyển hũ, không gắn nghĩa vụ.
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_funding_check;

-- @@
ALTER TABLE transactions ADD CONSTRAINT transactions_funding_check CHECK (
  funding_source IN ('jar', 'credit', 'external')
  AND (funding_source = 'jar' OR kind = 'expense' OR (funding_source = 'external' AND kind = 'income'))
  AND (funding_source <> 'external' OR (transfer_id IS NULL AND obligation_id IS NULL))
  AND (funding_source <> 'external' OR kind <> 'expense' OR jar_code IS NOT NULL)
);

-- @@
-- ===== ingest_jobs: một lần nạp (một tệp ảnh hoặc CSV) =====
-- s3_key chỉ gồm tiền tố người dùng và id (không có tên tệp gốc). content_sha256 đặt sau khi tải lên, để phát hiện cùng tệp.
-- status: awaiting_upload (đã cấp URL), queued, processing, review (đã trích, chờ duyệt), done (đã chốt), failed (lỗi hệ thống
-- hoặc không đọc được), rejected (không phải tài liệu tài chính, loại không hỗ trợ, trùng tệp). Kết thúc thì có finished_at.
CREATE TABLE IF NOT EXISTS ingest_jobs (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  source_kind      text NOT NULL CHECK (source_kind IN ('image', 'csv')),
  s3_key           text NOT NULL CHECK (length(s3_key) BETWEEN 1 AND 512),
  content_sha256   text CHECK (content_sha256 IS NULL OR content_sha256 ~ '^[0-9a-f]{64}$'),
  mime             text NOT NULL CHECK (length(mime) BETWEEN 1 AND 100),
  size_bytes       bigint CHECK (size_bytes IS NULL OR size_bytes > 0),
  status           text NOT NULL DEFAULT 'awaiting_upload',
  error_code       text CHECK (error_code IS NULL OR error_code ~ '^[A-Z][A-Z0-9_]{0,63}$'),
  error_message    text CHECK (error_message IS NULL OR length(error_message) <= 280),
  progress         smallint NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  rows_total       integer NOT NULL DEFAULT 0 CHECK (rows_total >= 0),
  rows_auto_added  integer NOT NULL DEFAULT 0 CHECK (rows_auto_added >= 0),
  rows_review      integer NOT NULL DEFAULT 0 CHECK (rows_review >= 0),
  rows_duplicate   integer NOT NULL DEFAULT 0 CHECK (rows_duplicate >= 0),
  coverage_before  numeric(4,3) CHECK (coverage_before IS NULL OR coverage_before BETWEEN 0 AND 1),
  coverage_after   numeric(4,3) CHECK (coverage_after IS NULL OR coverage_after BETWEEN 0 AND 1),
  model            text CHECK (model IS NULL OR length(model) <= 80),
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  finished_at      timestamptz,
  UNIQUE (user_id, id),
  CONSTRAINT ingest_jobs_status_check CHECK (
    status IN ('awaiting_upload', 'queued', 'processing', 'review', 'done', 'failed', 'rejected')
  ),
  CONSTRAINT ingest_jobs_finished_check CHECK (
    (status IN ('done', 'failed', 'rejected')) = (finished_at IS NOT NULL)
  ),
  CONSTRAINT ingest_jobs_error_check CHECK (status NOT IN ('failed', 'rejected') OR error_code IS NOT NULL)
);

-- @@
CREATE INDEX IF NOT EXISTS ingest_jobs_user_idx ON ingest_jobs (user_id, created_at DESC, id DESC);

-- @@
-- Cùng nội dung tệp chỉ một job còn sống mỗi người dùng (job lỗi hoặc bị từ chối thì nạp lại được).
CREATE UNIQUE INDEX IF NOT EXISTS ingest_jobs_content_uidx ON ingest_jobs (user_id, content_sha256)
  WHERE content_sha256 IS NOT NULL AND status NOT IN ('failed', 'rejected');

-- @@
-- ===== ingest_rows: dòng trích được, ĐÃ che PII (số tài khoản, số điện thoại, tên người khác) trước khi lưu =====
-- amount_vnd luôn dương, hướng nằm ở kind. review_status: auto_added (tin cậy cao, được CHỌN SẴN trong khối duyệt; chưa vào
-- sổ cái), pending (chờ người dùng), approved (đã ghi vào sổ cái, có transaction_id), rejected (người dùng bỏ), duplicate
-- (trùng một giao dịch đã có, duplicate_of_transaction_id). Chỉ confirm_rows (có token) ghi sổ cái.
-- transaction_id và duplicate_of_transaction_id KHÔNG có khóa ngoại: đặt lại demo xóa transactions trước bảng này.
-- dedupe_key cùng công thức với transactions.dedupe_key (contracts/README.md, "Khử trùng"), duy nhất theo người dùng: nạp
-- lại cùng tệp hay ảnh không sinh dòng thứ hai.
CREATE TABLE IF NOT EXISTS ingest_rows (
  id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id                      uuid NOT NULL,
  user_id                     text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  seq                         integer NOT NULL CHECK (seq BETWEEN 1 AND 10000),
  kind                        text NOT NULL CHECK (kind IN ('expense', 'income')),
  app_date                    date NOT NULL,
  amount_vnd                  numeric(14,0) NOT NULL CHECK (amount_vnd > 0),
  counterparty                text CHECK (counterparty IS NULL OR length(counterparty) BETWEEN 1 AND 120),
  description                 text CHECK (description IS NULL OR length(description) BETWEEN 1 AND 200),
  extract_confidence          numeric(4,3) NOT NULL CHECK (extract_confidence BETWEEN 0 AND 1),
  suggested_jar_code          text CHECK (suggested_jar_code IS NULL OR suggested_jar_code ~ '^[a-z][a-z0-9_]{0,31}$'),
  jar_confidence              numeric(4,3) CHECK (jar_confidence IS NULL OR jar_confidence BETWEEN 0 AND 1),
  jar_source                  text CHECK (jar_source IS NULL OR jar_source IN ('type_map', 'rule', 'model', 'user')),
  tx_type                     text CHECK (tx_type IS NULL OR tx_type ~ '^[a-z][a-z0-9_]{0,39}$'),
  review_status               text NOT NULL DEFAULT 'pending',
  duplicate_of_transaction_id uuid,
  transaction_id              uuid,
  dedupe_key                  text NOT NULL CHECK (dedupe_key ~ '^[0-9a-f]{64}$'),
  created_at                  timestamptz NOT NULL DEFAULT now(),
  updated_at                  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (job_id, seq),
  FOREIGN KEY (user_id, job_id) REFERENCES ingest_jobs (user_id, id) ON DELETE CASCADE,
  CONSTRAINT ingest_rows_review_check CHECK (
    review_status IN ('auto_added', 'pending', 'approved', 'rejected', 'duplicate')
  ),
  CONSTRAINT ingest_rows_links_check CHECK (
    (review_status <> 'duplicate' OR duplicate_of_transaction_id IS NOT NULL)
    AND (review_status <> 'approved' OR transaction_id IS NOT NULL)
    AND ((jar_source IS NULL) = (suggested_jar_code IS NULL))
  )
);

-- @@
CREATE UNIQUE INDEX IF NOT EXISTS ingest_rows_dedupe_uidx ON ingest_rows (user_id, dedupe_key);

-- @@
-- ===== consents: đồng ý theo nguồn nạp (một dòng mỗi người dùng mỗi nguồn; rút lại thì có revoked_at) =====
CREATE TABLE IF NOT EXISTS consents (
  user_id    text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  source     text NOT NULL CHECK (source IN ('image_upload', 'csv_upload')),
  granted_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz,
  version    text NOT NULL CHECK (length(version) BETWEEN 1 AND 20),
  PRIMARY KEY (user_id, source),
  CHECK (revoked_at IS NULL OR revoked_at >= granted_at)
);

-- @@
-- ===== Row Level Security =====
ALTER TABLE ingest_jobs ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE ingest_jobs FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON ingest_jobs;

-- @@
CREATE POLICY user_isolation ON ingest_jobs
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
ALTER TABLE ingest_rows ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE ingest_rows FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON ingest_rows;

-- @@
CREATE POLICY user_isolation ON ingest_rows
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
ALTER TABLE consents ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE consents FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON consents;

-- @@
CREATE POLICY user_isolation ON consents
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
-- ===== Quyền tối thiểu: đọc, thêm, sửa, xóa (xóa khi đặt lại demo) =====
GRANT SELECT, INSERT, UPDATE, DELETE ON ingest_jobs TO yofina_app;

-- @@
GRANT SELECT, INSERT, UPDATE, DELETE ON ingest_rows TO yofina_app;

-- @@
GRANT SELECT, INSERT, UPDATE, DELETE ON consents TO yofina_app;

-- @@
-- ===== Chuẩn hóa đối tác (khớp yofina_core.params.fold_text): chữ thường, bỏ dấu tiếng Việt, đ thành d, gộp khoảng trắng =====
CREATE OR REPLACE FUNCTION app_fold_text(p_text text)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
SET search_path = public, pg_temp
AS $$
  SELECT btrim(regexp_replace(
    translate(
      lower(coalesce(p_text, '')),
      'áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÉÈẺẼẸÊẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÚÙỦŨỤƯỨỪỬỮỰÝỲỶỸỴđĐ',
      'aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyaaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyydd'
    ),
    '\s+', ' ', 'g'))
$$;

-- @@
-- ===== Đầu vào dự báo: thay hàm app_get_daily_spend của 0005 =====
-- Chi tiêu theo hũ theo ngày trong [p_from, p_to] (ngày mô phỏng). Tính dòng chi funding_source jar (trừ số dư hũ) VÀ external
-- (chi ngoài ví, nạp từ tệp: không đổi số dư nhưng là hành vi chi của hũ). Vẫn bỏ dòng gắn nghĩa vụ (đã nằm trong lịch nghĩa vụ)
-- và hũ hệ thống; dòng credit vẫn không tính. Ngày không có chi tiêu không có dòng (người gọi điền 0).
CREATE OR REPLACE FUNCTION app_get_daily_spend(p_user_id text, p_from date, p_to date)
RETURNS TABLE (jar_code text, day date, spent_vnd numeric, tx_count bigint)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT t.jar_code, t.app_date, sum(-t.amount_vnd), count(*)
    FROM transactions t
    JOIN jars j ON j.user_id = t.user_id AND j.code = t.jar_code
    WHERE t.kind = 'expense'
      AND t.funding_source IN ('jar', 'external')
      AND t.obligation_id IS NULL
      AND j.kind <> 'system'
      AND t.app_date BETWEEN p_from AND p_to
    GROUP BY t.jar_code, t.app_date
    ORDER BY t.jar_code, t.app_date
    LIMIT 5000;
END
$$;

-- @@
-- ===== Dữ kiện độ phủ dữ liệu từ p_from (dùng chung cho app_get_forecast_context và app_get_data_coverage) =====
-- income_vnd = lương vào ví (kind income, tx_type salary, funding jar) + mọi thu nhập ngoài ví (kind income, funding external).
-- spend_vnd  = chi trong ví (funding jar) + chi ngoài ví (funding external). net_jar_vnd = tổng amount_vnd dòng jar (biến
-- động số dư ví trong cửa sổ). balance_end_vnd = tổng số dư mọi hũ. Không có dòng external thì đúng bằng các số của 0009.
CREATE OR REPLACE FUNCTION app_coverage_facts(p_user_id text, p_from date)
RETURNS TABLE (
  income_vnd numeric, spend_vnd numeric, net_jar_vnd numeric, balance_end_vnd numeric,
  external_spend_vnd numeric, external_income_vnd numeric
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT
      coalesce(sum(t.amount_vnd) FILTER (WHERE t.kind = 'income' AND t.tx_type = 'salary' AND t.funding_source = 'jar'), 0)
        + coalesce(sum(t.amount_vnd) FILTER (WHERE t.kind = 'income' AND t.funding_source = 'external'), 0),
      coalesce(sum(-t.amount_vnd) FILTER (WHERE t.kind = 'expense' AND t.funding_source IN ('jar', 'external')), 0),
      coalesce(sum(t.amount_vnd) FILTER (WHERE t.funding_source = 'jar'), 0),
      (SELECT coalesce(sum(j.balance_vnd), 0) FROM jars j),
      coalesce(sum(-t.amount_vnd) FILTER (WHERE t.kind = 'expense' AND t.funding_source = 'external'), 0),
      coalesce(sum(t.amount_vnd) FILTER (WHERE t.kind = 'income' AND t.funding_source = 'external'), 0)
    FROM transactions t
    WHERE t.app_date >= p_from;
END
$$;

-- @@
-- ===== Đầu vào dự báo: thay hàm app_get_forecast_context của 0009 (cùng chữ ký, cùng hình dạng payload) =====
-- Chỉ đổi cách tính coverage.spend_vnd và coverage.income_vnd (qua app_coverage_facts); balance_start_vnd và balance_end_vnd
-- như cũ (chỉ hũ trong ví). Lambda dự báo đã deploy đọc đúng bốn khóa này rồi quality.data_coverage tính độ phủ, nên công thức
-- mới có hiệu lực mà không phải deploy lại Lambda.
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

  SELECT f.income_vnd, f.spend_vnd, f.net_jar_vnd, f.balance_end_vnd
    INTO v_income, v_spend, v_net, v_end
    FROM app_coverage_facts(p_user_id, v_from) f;

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
-- ===== Độ phủ dữ liệu hiện tại: CÙNG số mà app_get_forecast_context đưa vào quality.data_coverage =====
-- Cùng cách tính ngày mô phỏng và history_start với app_get_forecast_context (p_window_days là cùng cấu hình
-- forecast_history_window_days). Trả các thành phần thô; Python tính tỷ lệ bằng đúng công thức của quality.data_coverage.
-- Kèm phần ngoài ví để khối coverage_change nói được đã thêm bao nhiêu. 0 hoặc 1 dòng.
CREATE OR REPLACE FUNCTION app_get_data_coverage(
  p_user_id text, p_now timestamptz, p_tz text, p_window_days integer DEFAULT 330
)
RETURNS TABLE (
  app_date date, history_start date, income_vnd numeric, spend_vnd numeric, balance_start_vnd numeric,
  balance_end_vnd numeric, external_spend_vnd numeric, external_income_vnd numeric
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_offset integer;
  v_today  date;
  v_first  date;
  v_from   date;
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  SELECT u.clock_offset_days INTO v_offset FROM users u LIMIT 1;
  IF NOT FOUND THEN
    RETURN;
  END IF;
  v_today := (p_now AT TIME ZONE p_tz)::date + coalesce(v_offset, 0);
  SELECT min(t.app_date) INTO v_first FROM transactions t;
  v_from := greatest(coalesce(v_first, v_today), v_today - greatest(coalesce(p_window_days, 330), 1));
  RETURN QUERY
    SELECT v_today, v_from, f.income_vnd, f.spend_vnd, f.balance_end_vnd - f.net_jar_vnd, f.balance_end_vnd,
           f.external_spend_vnd, f.external_income_vnd
    FROM app_coverage_facts(p_user_id, v_from) f
    LIMIT 1;
END
$$;

-- @@
-- ===== Dòng tiền: thay app_get_cashflow_summary của 0005 =====
-- by_jar (chi theo hũ, mọi nguồn trả CỦA VÍ: jar và credit) và income_by_type (tiền vào ví) KHÔNG gồm dòng external: đây là
-- luồng tiền của ví, cộng chi ngoài ví vào sẽ làm "đã chi" lớn hơn tiền thật rời ví. Phần ngoài ví tách ở khóa external
-- (spent_vnd, income_vnd, tx_count). Không tính dòng chuyển hũ và chia lương. Người dùng không có dòng external: by_jar và
-- income_by_type y hệt bản 0005.
CREATE OR REPLACE FUNCTION app_get_cashflow_summary(p_user_id text, p_from date, p_to date)
RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN jsonb_build_object(
    'by_jar', (
      SELECT coalesce(jsonb_agg(jsonb_build_object('jar_code', s.jar_code, 'spent_vnd', s.spent, 'tx_count', s.n) ORDER BY s.jar_code), '[]'::jsonb)
      FROM (
        SELECT t.jar_code, sum(-t.amount_vnd) AS spent, count(*) AS n
        FROM transactions t
        WHERE t.kind = 'expense' AND t.funding_source <> 'external' AND t.app_date BETWEEN p_from AND p_to
        GROUP BY t.jar_code
        LIMIT 40
      ) s
    ),
    'income_by_type', (
      SELECT coalesce(jsonb_agg(jsonb_build_object('tx_type', s.tx_type, 'amount_vnd', s.total, 'tx_count', s.n) ORDER BY s.tx_type), '[]'::jsonb)
      FROM (
        SELECT t.tx_type, sum(t.amount_vnd) AS total, count(*) AS n
        FROM transactions t
        WHERE t.kind = 'income' AND t.funding_source <> 'external' AND t.app_date BETWEEN p_from AND p_to
        GROUP BY t.tx_type
        LIMIT 40
      ) s
    ),
    'external', (
      SELECT jsonb_build_object(
        'spent_vnd', coalesce(sum(-t.amount_vnd) FILTER (WHERE t.kind = 'expense'), 0),
        'income_vnd', coalesce(sum(t.amount_vnd) FILTER (WHERE t.kind = 'income'), 0),
        'tx_count', count(*))
      FROM transactions t
      WHERE t.funding_source = 'external' AND t.app_date BETWEEN p_from AND p_to
    )
  );
END
$$;

-- @@
-- ===== Tổng quan: thay app_get_overview của 0007 =====
-- Giống hệt 0007, trừ recent_transactions: giao dịch gần đây của VÍ nên không gồm dòng external (chúng vẫn ở lịch sử Hoạt
-- động và Chi tiết hũ). review_count không đổi (dòng external do confirm_rows ghi luôn có needs_review false và hũ người dùng).
CREATE OR REPLACE FUNCTION app_get_overview(p_user_id text, p_now timestamptz, p_tz text)
RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_offset integer;
  v_today  date;
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  SELECT u.clock_offset_days INTO v_offset FROM users u LIMIT 1;
  v_today := (p_now AT TIME ZONE p_tz)::date + coalesce(v_offset, 0);
  RETURN jsonb_build_object(
    'app_date', v_today,
    'profile', (
      SELECT jsonb_build_object(
        'display_name', u.display_name, 'monthly_salary_vnd', u.monthly_salary_vnd, 'payday_day', u.payday_day,
        'risk_tolerance', u.risk_tolerance, 'clock_offset_days', u.clock_offset_days)
      FROM users u LIMIT 1
    ),
    'jars', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
        'code', j.code, 'name', j.name, 'color_key', j.color_key, 'icon_key', j.icon_key,
        'balance_vnd', j.balance_vnd, 'split_percent', j.split_percent, 'sort_order', j.sort_order,
        'kind', j.kind, 'system_role', j.system_role, 'goal_vnd', j.goal_vnd, 'goal_date', j.goal_date
      ) ORDER BY j.sort_order, j.code), '[]'::jsonb)
      FROM (SELECT * FROM jars ORDER BY sort_order, code LIMIT 40) j
    ),
    'forecasts', (
      SELECT coalesce(jsonb_agg(to_jsonb(f) ORDER BY f.jar_code), '[]'::jsonb)
      FROM app_get_forecast_summaries(p_user_id) f
    ),
    'credit_line', (
      SELECT jsonb_build_object(
        'product_code', c.product_code, 'limit_vnd', c.limit_vnd, 'outstanding_vnd', c.outstanding_vnd,
        'due_day', c.due_day, 'status', c.status)
      FROM credit_lines c LIMIT 1
    ),
    'obligations_due', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
        'id', o.id, 'kind', o.kind, 'name', o.name, 'amount_vnd', o.amount_vnd, 'amount_min_vnd', o.amount_min_vnd,
        'amount_max_vnd', o.amount_max_vnd, 'fee_vnd', o.fee_vnd, 'principal_vnd', o.principal_vnd,
        'due_date', o.due_date, 'cycle', o.cycle, 'due_day', o.due_day, 'status', o.status,
        'pay_jar_code', o.pay_jar_code, 'is_essential', o.is_essential, 'source', o.source
      ) ORDER BY o.due_date, o.id), '[]'::jsonb)
      FROM (
        SELECT * FROM obligations
        WHERE status = 'active' AND due_date <= v_today + 30
        ORDER BY due_date, id
        LIMIT 5
      ) o
    ),
    'salary_event', (
      SELECT jsonb_build_object(
        'id', e.id, 'period_date', e.period_date, 'received_on', e.received_on, 'expected_vnd', e.expected_vnd,
        'amount_vnd', e.amount_vnd, 'deviation_percent', e.deviation_percent,
        'ask_update_salary', e.ask_update_salary, 'status', e.status)
      FROM salary_events e
      WHERE e.status = 'pending'
      ORDER BY e.period_date DESC, e.id
      LIMIT 1
    ),
    'confirmed_period', (
      SELECT max(e.period_date) FROM salary_events e WHERE e.status = 'confirmed'
    ),
    'recent_transactions', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
        'id', r.id, 'occurred_at', r.occurred_at, 'app_date', r.app_date, 'kind', r.kind, 'jar_code', r.jar_code,
        'amount_vnd', r.amount_vnd, 'merchant', r.merchant, 'note', r.note, 'tx_type', r.tx_type,
        'funding_source', r.funding_source, 'payee_id', r.payee_id, 'payee_name', r.payee_name,
        'obligation_id', r.obligation_id, 'needs_review', r.needs_review
      ) ORDER BY r.occurred_at DESC, r.id DESC), '[]'::jsonb)
      FROM (
        SELECT t.id, t.occurred_at, t.app_date, t.kind, t.jar_code, t.amount_vnd, t.merchant, t.note, t.tx_type,
               t.funding_source, t.payee_id, p.name AS payee_name, t.obligation_id, t.needs_review
        FROM transactions t
        LEFT JOIN payees p ON p.user_id = t.user_id AND p.id = t.payee_id
        WHERE t.kind <> 'transfer' AND t.funding_source <> 'external'
        ORDER BY t.occurred_at DESC, t.id DESC
        LIMIT 5
      ) r
    ),
    'review_count', (
      SELECT count(*)
      FROM transactions t
      LEFT JOIN jars j ON j.user_id = t.user_id AND j.code = t.jar_code
      WHERE t.kind <> 'transfer' AND (t.needs_review OR j.system_role = 'unclassified')
    )
  );
END
$$;

-- @@
-- ===== Tổng quan bản cũ: thay app_get_overview_extras của 0005 (không còn mã nào gọi, sửa để hai bản không lệch nhau) =====
CREATE OR REPLACE FUNCTION app_get_overview_extras(p_user_id text, p_today date)
RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN jsonb_build_object(
    'profile', (
      SELECT jsonb_build_object(
        'display_name', u.display_name, 'monthly_salary_vnd', u.monthly_salary_vnd, 'payday_day', u.payday_day,
        'risk_tolerance', u.risk_tolerance, 'clock_offset_days', u.clock_offset_days)
      FROM users u LIMIT 1
    ),
    'credit_line', (
      SELECT jsonb_build_object(
        'product_code', c.product_code, 'limit_vnd', c.limit_vnd, 'outstanding_vnd', c.outstanding_vnd,
        'due_day', c.due_day, 'status', c.status)
      FROM credit_lines c LIMIT 1
    ),
    'obligations_due', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
        'id', o.id, 'kind', o.kind, 'name', o.name, 'amount_vnd', o.amount_vnd, 'fee_vnd', o.fee_vnd,
        'due_date', o.due_date, 'pay_jar_code', o.pay_jar_code, 'is_essential', o.is_essential
      ) ORDER BY o.due_date, o.id), '[]'::jsonb)
      FROM (
        SELECT * FROM obligations
        WHERE status = 'active' AND due_date <= p_today + 30
        ORDER BY due_date, id
        LIMIT 5
      ) o
    ),
    'salary_event', (
      SELECT jsonb_build_object(
        'id', e.id, 'period_date', e.period_date, 'received_on', e.received_on, 'expected_vnd', e.expected_vnd,
        'amount_vnd', e.amount_vnd, 'deviation_percent', e.deviation_percent,
        'ask_update_salary', e.ask_update_salary, 'status', e.status)
      FROM salary_events e
      WHERE e.status = 'pending'
      ORDER BY e.period_date DESC, e.id
      LIMIT 1
    ),
    'confirmed_period', (
      SELECT max(e.period_date) FROM salary_events e WHERE e.status = 'confirmed'
    ),
    'recent_transactions', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
        'id', r.id, 'occurred_at', r.occurred_at, 'app_date', r.app_date, 'kind', r.kind, 'jar_code', r.jar_code,
        'amount_vnd', r.amount_vnd, 'merchant', r.merchant, 'note', r.note, 'tx_type', r.tx_type,
        'funding_source', r.funding_source, 'payee_name', r.payee_name
      ) ORDER BY r.occurred_at DESC, r.id DESC), '[]'::jsonb)
      FROM (
        SELECT t.id, t.occurred_at, t.app_date, t.kind, t.jar_code, t.amount_vnd, t.merchant, t.note,
               t.tx_type, t.funding_source, p.name AS payee_name
        FROM transactions t
        LEFT JOIN payees p ON p.user_id = t.user_id AND p.id = t.payee_id
        WHERE t.kind <> 'transfer' AND t.funding_source <> 'external'
        ORDER BY t.occurred_at DESC, t.id DESC
        LIMIT 5
      ) r
    ),
    'needs_review_count', (
      SELECT count(*)
      FROM transactions t
      LEFT JOIN jars j ON j.user_id = t.user_id AND j.code = t.jar_code
      WHERE t.kind <> 'transfer' AND (t.needs_review OR j.system_role = 'unclassified')
    )
  );
END
$$;

-- @@
-- ===== Luồng nạp: hàm ghi một lệnh gọi (SECURITY INVOKER, tự đặt app.user_id, RLS áp theo role gọi) =====
-- Tạo job lúc cấp URL tải lên. p_id do server sinh (nằm trong s3_key). Trả dòng vừa tạo.
CREATE OR REPLACE FUNCTION app_create_ingest_job(
  p_user_id text, p_id uuid, p_source_kind text, p_s3_key text, p_mime text, p_size_bytes bigint DEFAULT NULL
)
RETURNS TABLE (id uuid, status text, created_at timestamptz)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    INSERT INTO ingest_jobs AS j (id, user_id, source_kind, s3_key, mime, size_bytes)
    VALUES (p_id, p_user_id, p_source_kind, p_s3_key, p_mime, p_size_bytes)
    RETURNING j.id, j.status, j.created_at;
END
$$;

-- @@
-- Job còn sống (không failed, không rejected) có cùng nội dung tệp, để báo "tệp này đã nạp" trước khi đặt content_sha256.
CREATE OR REPLACE FUNCTION app_find_ingest_job_by_content(p_user_id text, p_content_sha256 text)
RETURNS TABLE (id uuid, status text, created_at timestamptz)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT j.id, j.status, j.created_at
    FROM ingest_jobs j
    WHERE j.content_sha256 = p_content_sha256 AND j.status NOT IN ('failed', 'rejected')
    ORDER BY j.created_at, j.id
    LIMIT 1;
END
$$;

-- @@
-- Cập nhật trạng thái và tiến độ. Chuyển trạng thái hợp lệ: awaiting_upload -> queued; queued -> processing; processing ->
-- review hoặc done; review -> done; mọi trạng thái chưa kết thúc -> failed hoặc rejected; giữ nguyên trạng thái để cập nhật
-- tiến độ. Trạng thái kết thúc (done, failed, rejected) không đổi nữa. Chuyển sai hoặc không có job: không có dòng trả về.
-- p_patch (jsonb, khóa tùy chọn): content_sha256, size_bytes, error_code, error_message, rows_total, rows_auto_added,
-- rows_review, rows_duplicate, coverage_before, coverage_after, model. Tiến độ không lùi; done thì 100.
-- failed hoặc rejected thì xóa các dòng chưa chốt của job (nạp lại cùng tệp được, khóa khử trùng không giữ dòng cũ).
CREATE OR REPLACE FUNCTION app_update_ingest_job(
  p_user_id text, p_job_id uuid, p_status text, p_progress integer DEFAULT NULL, p_patch jsonb DEFAULT '{}'::jsonb
)
RETURNS TABLE (id uuid, status text, progress smallint, updated_at timestamptz, finished_at timestamptz)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_patch jsonb := coalesce(p_patch, '{}'::jsonb);
  v_final boolean := p_status IN ('done', 'failed', 'rejected');
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    UPDATE ingest_jobs AS j SET
      status          = p_status,
      progress        = CASE WHEN p_status = 'done' THEN 100
                             ELSE greatest(j.progress, least(greatest(coalesce(p_progress, j.progress), 0), 100)) END,
      content_sha256  = coalesce(v_patch ->> 'content_sha256', j.content_sha256),
      size_bytes      = coalesce((v_patch ->> 'size_bytes')::bigint, j.size_bytes),
      error_code      = coalesce(v_patch ->> 'error_code', j.error_code),
      error_message   = coalesce(left(v_patch ->> 'error_message', 280), j.error_message),
      rows_total      = coalesce((v_patch ->> 'rows_total')::integer, j.rows_total),
      rows_auto_added = coalesce((v_patch ->> 'rows_auto_added')::integer, j.rows_auto_added),
      rows_review     = coalesce((v_patch ->> 'rows_review')::integer, j.rows_review),
      rows_duplicate  = coalesce((v_patch ->> 'rows_duplicate')::integer, j.rows_duplicate),
      coverage_before = coalesce((v_patch ->> 'coverage_before')::numeric(4,3), j.coverage_before),
      coverage_after  = coalesce((v_patch ->> 'coverage_after')::numeric(4,3), j.coverage_after),
      model           = coalesce(left(v_patch ->> 'model', 80), j.model),
      updated_at      = now(),
      finished_at     = CASE WHEN v_final THEN now() ELSE NULL END
    WHERE j.id = p_job_id
      AND j.status NOT IN ('done', 'failed', 'rejected')
      AND (
        j.status = p_status
        OR p_status IN ('failed', 'rejected')
        OR (j.status = 'awaiting_upload' AND p_status = 'queued')
        OR (j.status = 'queued' AND p_status = 'processing')
        OR (j.status = 'processing' AND p_status IN ('review', 'done'))
        OR (j.status = 'review' AND p_status = 'done')
      )
    RETURNING j.id, j.status, j.progress, j.updated_at, j.finished_at;
  -- chỉ dọn khi lần chuyển trạng thái này thật sự xảy ra (FOUND sau RETURN QUERY là có ít nhất một dòng)
  IF FOUND AND p_status IN ('failed', 'rejected') THEN
    DELETE FROM ingest_rows r
    WHERE r.job_id = p_job_id AND r.review_status IN ('auto_added', 'pending', 'duplicate');
  END IF;
END
$$;

-- @@
-- Chèn các dòng đã trích và đã che PII (mảng jsonb, tối đa 500 dòng mỗi lần). Mỗi phần tử: seq, kind, app_date, amount_vnd
-- (dương), counterparty, description, extract_confidence, suggested_jar_code, jar_confidence, jar_source, tx_type,
-- review_status (auto_added, pending hoặc duplicate), duplicate_of_transaction_id, dedupe_key. Dòng trùng khóa khử trùng
-- với dòng đã có (nạp lại cùng tệp) bị bỏ qua. Trả seq và id của các dòng ĐÃ chèn.
CREATE OR REPLACE FUNCTION app_insert_ingest_rows(p_user_id text, p_job_id uuid, p_rows jsonb)
RETURNS TABLE (seq integer, row_id uuid)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  IF jsonb_typeof(p_rows) <> 'array' OR jsonb_array_length(p_rows) > 500 THEN
    RAISE EXCEPTION 'p_rows phải là mảng tối đa 500 phần tử' USING ERRCODE = '22023';
  END IF;
  RETURN QUERY
    INSERT INTO ingest_rows AS r (
      job_id, user_id, seq, kind, app_date, amount_vnd, counterparty, description, extract_confidence,
      suggested_jar_code, jar_confidence, jar_source, tx_type, review_status, duplicate_of_transaction_id, dedupe_key
    )
    SELECT p_job_id, p_user_id, (e ->> 'seq')::integer, e ->> 'kind', (e ->> 'app_date')::date,
           (e ->> 'amount_vnd')::numeric(14,0), e ->> 'counterparty', e ->> 'description',
           (e ->> 'extract_confidence')::numeric(4,3), e ->> 'suggested_jar_code', (e ->> 'jar_confidence')::numeric(4,3),
           e ->> 'jar_source', e ->> 'tx_type', coalesce(e ->> 'review_status', 'pending'),
           (e ->> 'duplicate_of_transaction_id')::uuid, e ->> 'dedupe_key'
    FROM jsonb_array_elements(p_rows) AS x(e)
    ON CONFLICT (user_id, dedupe_key) DO NOTHING
    RETURNING r.seq, r.id;
END
$$;

-- @@
-- Một job kèm các dòng của nó: bảng (section, payload jsonb), dòng 'job' trước rồi mỗi dòng trích một dòng 'row' theo seq
-- (tối đa p_row_limit, trần 500). Nhiều dòng nhỏ thay vì một jsonb lớn (Data API giới hạn 64 KB mỗi dòng kết quả).
-- Không có job (hoặc job của người khác): không có dòng nào.
CREATE OR REPLACE FUNCTION app_get_ingest_job(p_user_id text, p_job_id uuid, p_row_limit integer DEFAULT 200)
RETURNS TABLE (section text, payload jsonb)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT 'job'::text, jsonb_build_object(
      'id', j.id, 'source_kind', j.source_kind, 's3_key', j.s3_key, 'content_sha256', j.content_sha256, 'mime', j.mime,
      'size_bytes', j.size_bytes, 'status', j.status, 'error_code', j.error_code, 'error_message', j.error_message,
      'progress', j.progress, 'rows_total', j.rows_total, 'rows_auto_added', j.rows_auto_added,
      'rows_review', j.rows_review, 'rows_duplicate', j.rows_duplicate, 'coverage_before', j.coverage_before,
      'coverage_after', j.coverage_after, 'model', j.model, 'created_at', j.created_at, 'updated_at', j.updated_at,
      'finished_at', j.finished_at)
    FROM ingest_jobs j
    WHERE j.id = p_job_id
    LIMIT 1;
  RETURN QUERY
    SELECT 'row'::text, jsonb_build_object(
      'id', r.id, 'seq', r.seq, 'kind', r.kind, 'app_date', r.app_date, 'amount_vnd', r.amount_vnd,
      'counterparty', r.counterparty, 'description', r.description, 'extract_confidence', r.extract_confidence,
      'suggested_jar_code', r.suggested_jar_code, 'jar_confidence', r.jar_confidence, 'jar_source', r.jar_source,
      'tx_type', r.tx_type, 'review_status', r.review_status,
      'duplicate_of_transaction_id', r.duplicate_of_transaction_id, 'transaction_id', r.transaction_id,
      'dedupe_key', r.dedupe_key)
    FROM ingest_rows r
    WHERE r.job_id = p_job_id
    ORDER BY r.seq
    LIMIT LEAST(GREATEST(coalesce(p_row_limit, 200), 1), 500);
END
$$;

-- @@
-- Các job gần đây của người dùng, mới nhất trước (tối đa 20): để agent trả lời "mình vừa nạp ảnh".
CREATE OR REPLACE FUNCTION app_list_ingest_jobs(p_user_id text, p_limit integer DEFAULT 5)
RETURNS TABLE (
  id uuid, source_kind text, status text, progress smallint, rows_total integer, rows_auto_added integer,
  rows_review integer, rows_duplicate integer, error_code text, created_at timestamptz, finished_at timestamptz
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT j.id, j.source_kind, j.status, j.progress, j.rows_total, j.rows_auto_added, j.rows_review, j.rows_duplicate,
           j.error_code, j.created_at, j.finished_at
    FROM ingest_jobs j
    ORDER BY j.created_at DESC, j.id DESC
    LIMIT LEAST(GREATEST(coalesce(p_limit, 5), 1), 20);
END
$$;

-- @@
-- Người dùng đổi hũ đề xuất của MỘT dòng chi (chưa chốt, job đang chờ duyệt): chỉ đổi đề xuất, KHÔNG ghi sổ cái.
-- Hũ phải là hũ người dùng (không phải hũ hệ thống). jar_source thành user, jar_confidence 1. Không hợp lệ: không có dòng.
CREATE OR REPLACE FUNCTION app_set_ingest_row_jar(p_user_id text, p_row_id uuid, p_jar_code text)
RETURNS TABLE (row_id uuid, suggested_jar_code text, jar_source text, review_status text)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    UPDATE ingest_rows AS r SET
      suggested_jar_code = p_jar_code, jar_source = 'user', jar_confidence = 1, updated_at = now()
    FROM ingest_jobs j
    WHERE r.id = p_row_id
      AND j.user_id = r.user_id AND j.id = r.job_id AND j.status = 'review'
      AND r.kind = 'expense'
      AND r.review_status IN ('auto_added', 'pending')
      AND EXISTS (SELECT 1 FROM jars x WHERE x.user_id = r.user_id AND x.code = p_jar_code AND x.kind <> 'system')
    RETURNING r.id, r.suggested_jar_code, r.jar_source, r.review_status;
END
$$;

-- @@
-- Ghi (hoặc làm mới) đồng ý của một nguồn nạp: granted_at bây giờ, bỏ revoked_at. Trả dòng sau khi ghi.
CREATE OR REPLACE FUNCTION app_grant_consent(p_user_id text, p_source text, p_version text)
RETURNS TABLE (source text, granted_at timestamptz, revoked_at timestamptz, version text)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    INSERT INTO consents AS c (user_id, source, granted_at, revoked_at, version)
    VALUES (p_user_id, p_source, now(), NULL, p_version)
    ON CONFLICT ON CONSTRAINT consents_pkey DO UPDATE SET granted_at = now(), revoked_at = NULL, version = EXCLUDED.version
    RETURNING c.source, c.granted_at, c.revoked_at, c.version;
END
$$;

-- @@
-- Đồng ý hiện có của người dùng (tối đa 2 dòng, một mỗi nguồn).
CREATE OR REPLACE FUNCTION app_get_consents(p_user_id text)
RETURNS TABLE (source text, granted_at timestamptz, revoked_at timestamptz, version text)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT c.source, c.granted_at, c.revoked_at, c.version
    FROM consents c
    ORDER BY c.source
    LIMIT 2;
END
$$;

-- @@
-- ===== Khử trùng chặt với sổ cái: một khoản không được vừa ở trong ví vừa ở ngoài ví =====
-- p_rows: mảng jsonb (tối đa 500) các dòng ứng viên {idx, app_date, amount_vnd (tuyệt đối), counterparty (đã chuẩn hóa bằng
-- fold_text, có thể rỗng), kind (expense hoặc income)}. Với mỗi ứng viên trả các giao dịch ĐÃ CÓ của người dùng ở MỌI nguồn
-- trả (jar, credit, external), cùng kind, cùng số tiền tuyệt đối, lệch ngày không quá p_window_days (tham số, kẹp 0..30),
-- kèm counterparty_match (đối tác chuẩn hóa của giao dịch bằng hoặc chứa đối tác ứng viên, hoặc ngược lại, khi cả hai có ít
-- nhất 3 ký tự). Không gồm dòng chuyển hũ. Sắp theo idx, lệch ngày nhỏ trước, đối tác khớp trước. Tối đa 2000 dòng.
CREATE OR REPLACE FUNCTION app_find_ingest_matches(p_user_id text, p_rows jsonb, p_window_days integer)
RETURNS TABLE (
  idx integer, transaction_id uuid, funding_source text, app_date date, day_diff integer, counterparty_match boolean
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_win integer := least(greatest(coalesce(p_window_days, 0), 0), 30);
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  IF jsonb_typeof(p_rows) <> 'array' OR jsonb_array_length(p_rows) > 500 THEN
    RAISE EXCEPTION 'p_rows phải là mảng tối đa 500 phần tử' USING ERRCODE = '22023';
  END IF;
  RETURN QUERY
    WITH c AS (
      SELECT (e ->> 'idx')::integer AS ci, (e ->> 'app_date')::date AS cd, abs((e ->> 'amount_vnd')::numeric) AS ca,
             coalesce(app_fold_text(e ->> 'counterparty'), '') AS cp, e ->> 'kind' AS ck
      FROM jsonb_array_elements(p_rows) AS x(e)
    ),
    m AS (
      SELECT c.ci, t.id AS tid, t.funding_source AS fs, t.app_date AS td, (t.app_date - c.cd) AS dd,
             (length(c.cp) >= 3 AND length(w.who) >= 3
               AND (w.who = c.cp OR position(c.cp IN w.who) > 0 OR position(w.who IN c.cp) > 0)) AS hit
      FROM c
      JOIN transactions t
        ON t.kind = c.ck AND abs(t.amount_vnd) = c.ca AND t.app_date BETWEEN c.cd - v_win AND c.cd + v_win
      LEFT JOIN payees p ON p.user_id = t.user_id AND p.id = t.payee_id
      CROSS JOIN LATERAL (SELECT app_fold_text(coalesce(p.name, t.merchant, '')) AS who) w
      WHERE t.kind <> 'transfer'
    )
    SELECT m.ci, m.tid, m.fs, m.td, m.dd, m.hit
    FROM m
    ORDER BY m.ci, abs(m.dd), m.hit DESC, m.tid
    LIMIT 2000;
END
$$;

-- @@
-- ===== Quyền hàm: chỉ yofina_app được EXECUTE =====
REVOKE ALL ON FUNCTION app_fold_text(text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_daily_spend(text, date, date) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_coverage_facts(text, date) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_forecast_context(text, timestamptz, text, integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_data_coverage(text, timestamptz, text, integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_cashflow_summary(text, date, date) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_overview(text, timestamptz, text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_overview_extras(text, date) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_create_ingest_job(text, uuid, text, text, text, bigint) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_find_ingest_job_by_content(text, text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_update_ingest_job(text, uuid, text, integer, jsonb) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_insert_ingest_rows(text, uuid, jsonb) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_ingest_job(text, uuid, integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_list_ingest_jobs(text, integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_set_ingest_row_jar(text, uuid, text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_grant_consent(text, text, text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_consents(text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_find_ingest_matches(text, jsonb, integer) FROM PUBLIC;

-- @@
GRANT EXECUTE ON FUNCTION app_fold_text(text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_daily_spend(text, date, date) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_coverage_facts(text, date) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_forecast_context(text, timestamptz, text, integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_data_coverage(text, timestamptz, text, integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_cashflow_summary(text, date, date) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_overview(text, timestamptz, text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_overview_extras(text, date) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_create_ingest_job(text, uuid, text, text, text, bigint) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_find_ingest_job_by_content(text, text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_update_ingest_job(text, uuid, text, integer, jsonb) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_insert_ingest_rows(text, uuid, jsonb) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_ingest_job(text, uuid, integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_list_ingest_jobs(text, integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_set_ingest_row_jar(text, uuid, text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_grant_consent(text, text, text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_consents(text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_find_ingest_matches(text, jsonb, integer) TO yofina_app;
