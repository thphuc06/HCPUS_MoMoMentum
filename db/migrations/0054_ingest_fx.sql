-- 0054_ingest_fx: nạp chứng từ ngoại tệ và lý do con khi tệp không còn giao dịch nào (F6, phase 5). Không sửa 0001 tới 0053
-- (migrator kiểm checksum).
--
-- Nội dung (quyết định chi tiết: contracts/README.md mục "Phase 5 (F6): nạp dữ liệu", phần "Chứng từ ngoại tệ"):
-- * ingest_rows.fx (jsonb object, tùy chọn): dòng ghi bằng ngoại tệ. Khóa currency (ISO 4217, khác VND), amount_original (chuỗi
--   thập phân đúng như chứng từ), status (converted hoặc rate_unavailable), và khi converted thì rate (VND cho một đơn vị), rate_type (sell),
--   rate_source (vietcombank), rate_date. Hình dạng là `IngestFx` của contracts/blocks/ingest_review.schema.json.
-- * ingest_rows.amount_vnd được NULL, CHỈ khi dòng ngoại tệ chưa có tỷ giá (fx ->> 'status' = 'rate_unavailable'): người dùng
--   nhập số VND lúc chốt (confirm_rows ghi số đó vào cả transactions và dòng nạp). Dòng approved luôn có amount_vnd.
-- * ingest_jobs.error_reason (tùy chọn): lý do con của mã INGEST_NO_TRANSACTIONS (unexecuted_form, not_completed,
--   own_account_transfer, cash_withdrawal, no_amount, no_rows).
-- * Thay app_update_ingest_job của 0050 (cùng chữ ký, cùng kiểu trả về): p_patch nhận thêm khóa error_reason.
-- * Thay app_insert_ingest_rows của 0050 (cùng chữ ký, cùng kiểu trả về): mỗi phần tử nhận thêm khóa fx (object), amount_vnd vắng
--   được khi fx chưa có tỷ giá.
-- * Thay app_get_ingest_job của 0050 (cùng chữ ký, cùng kiểu trả về): payload job thêm error_reason, payload row thêm fx.
--
-- Quy ước như 0005 tới 0053 (db/README.md): chạy bằng secret MASTER, một transaction, tách bằng dòng "-- @@", viết lại được,
-- RLS FORCE giữ nguyên. Không viết dấu hai chấm dính liền chữ cái hoặc gạch dưới (kể cả trong chú thích). Quyền giữ nguyên:
-- CREATE OR REPLACE không đổi GRANT của hàm, cột mới thuộc bảng đã cấp quyền cho yofina_app.

-- ===== ingest_rows: dòng ngoại tệ =====
ALTER TABLE ingest_rows ADD COLUMN IF NOT EXISTS fx jsonb;

-- @@
ALTER TABLE ingest_rows DROP CONSTRAINT IF EXISTS ingest_rows_fx_check;

-- @@
ALTER TABLE ingest_rows ADD CONSTRAINT ingest_rows_fx_check CHECK (
  fx IS NULL OR (
    jsonb_typeof(fx) = 'object'
    AND octet_length(fx::text) <= 400
    AND (fx ->> 'currency') ~ '^[A-Z]{3}$'
    AND (fx ->> 'currency') <> 'VND'
    AND (fx ->> 'amount_original') ~ '^[0-9]{1,12}([.][0-9]{1,4})?$'
    AND (fx ->> 'status') IN ('converted', 'rate_unavailable')
  )
);

-- @@
ALTER TABLE ingest_rows ALTER COLUMN amount_vnd DROP NOT NULL;

-- @@
ALTER TABLE ingest_rows DROP CONSTRAINT IF EXISTS ingest_rows_amount_check;

-- @@
-- CHECK cũ của cột (amount_vnd > 0) vẫn còn và vẫn đúng với số có mặt; ràng buộc này nói khi nào được vắng.
ALTER TABLE ingest_rows ADD CONSTRAINT ingest_rows_amount_check CHECK (
  (amount_vnd IS NOT NULL OR (fx ->> 'status') = 'rate_unavailable')
  AND (review_status <> 'approved' OR amount_vnd IS NOT NULL)
);

-- @@
-- ===== ingest_jobs: lý do con của INGEST_NO_TRANSACTIONS =====
ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS error_reason text;

-- @@
ALTER TABLE ingest_jobs DROP CONSTRAINT IF EXISTS ingest_jobs_error_reason_check;

-- @@
ALTER TABLE ingest_jobs ADD CONSTRAINT ingest_jobs_error_reason_check CHECK (
  error_reason IS NULL OR error_reason IN (
    'unexecuted_form', 'not_completed', 'own_account_transfer', 'cash_withdrawal', 'no_amount', 'no_rows'
  )
);

-- @@
-- Như 0050, thêm khóa error_reason của p_patch.
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
      error_reason    = coalesce(v_patch ->> 'error_reason', j.error_reason),
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
-- Như 0050, thêm khóa fx (object; giá trị khác object thì bỏ) và amount_vnd vắng được (ràng buộc ingest_rows_amount_check quyết định).
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
      suggested_jar_code, jar_confidence, jar_source, tx_type, review_status, duplicate_of_transaction_id, dedupe_key, fx
    )
    SELECT p_job_id, p_user_id, (e ->> 'seq')::integer, e ->> 'kind', (e ->> 'app_date')::date,
           (e ->> 'amount_vnd')::numeric(14,0), e ->> 'counterparty', e ->> 'description',
           (e ->> 'extract_confidence')::numeric(4,3), e ->> 'suggested_jar_code', (e ->> 'jar_confidence')::numeric(4,3),
           e ->> 'jar_source', e ->> 'tx_type', coalesce(e ->> 'review_status', 'pending'),
           (e ->> 'duplicate_of_transaction_id')::uuid, e ->> 'dedupe_key',
           CASE WHEN jsonb_typeof(e -> 'fx') = 'object' THEN e -> 'fx' END
    FROM jsonb_array_elements(p_rows) AS x(e)
    ON CONFLICT (user_id, dedupe_key) DO NOTHING
    RETURNING r.seq, r.id;
END
$$;

-- @@
-- Như 0050, payload job thêm error_reason, payload row thêm fx.
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
      'error_reason', j.error_reason,
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
      'dedupe_key', r.dedupe_key, 'fx', r.fx)
    FROM ingest_rows r
    WHERE r.job_id = p_job_id
    ORDER BY r.seq
    LIMIT LEAST(GREATEST(coalesce(p_row_limit, 200), 1), 500);
END
$$;
