-- 0056_ingest_pii_kinds: loại PII đã che của từng dòng nạp (F6, issue #16 cảnh 5). Không sửa 0001 tới 0055 (migrator kiểm checksum).
--
-- Nội dung (quyết định chi tiết: contracts/README.md mục "Phase 5 (F6): nạp dữ liệu", phần "Che PII"):
-- * ingest_rows.pii_masked (text[], tùy chọn): các LOẠI PII mà bước trích đã che trong đối tác và nội dung của dòng, theo thứ tự
--   name, phone, account, card (yofina_core.pii.ROW_PII_KINDS). KHÔNG bao giờ chứa giá trị trước khi che. Mảng rỗng là không che gì;
--   NULL là dòng nạp trước 0056 (không biết). Màn duyệt hiện "Đã che: tên, SĐT, số TK" từ cột này.
-- * Thay app_insert_ingest_rows của 0054 (cùng chữ ký, cùng kiểu trả về): mỗi phần tử nhận thêm khóa pii_masked (mảng chuỗi; giá trị
--   khác mảng thì bỏ, phần tử lạ bị ingest_rows_pii_masked_check chặn).
-- * Thay app_get_ingest_job của 0054 (cùng chữ ký, cùng kiểu trả về): payload row thêm pii_masked.
--
-- Quy ước như 0005 tới 0055 (db/README.md): chạy bằng secret MASTER, một transaction, tách bằng dòng "-- @@", viết lại được,
-- RLS FORCE giữ nguyên. Không viết dấu hai chấm dính liền chữ cái hoặc gạch dưới (kể cả trong chú thích). Quyền giữ nguyên:
-- CREATE OR REPLACE không đổi GRANT của hàm, cột mới thuộc bảng đã cấp quyền cho yofina_app.

-- ===== ingest_rows: loại PII đã che =====
ALTER TABLE ingest_rows ADD COLUMN IF NOT EXISTS pii_masked text[];

-- @@
ALTER TABLE ingest_rows DROP CONSTRAINT IF EXISTS ingest_rows_pii_masked_check;

-- @@
ALTER TABLE ingest_rows ADD CONSTRAINT ingest_rows_pii_masked_check CHECK (
  pii_masked IS NULL OR pii_masked <@ ARRAY['name', 'phone', 'account', 'card']::text[]
);

-- @@
-- Như 0054, thêm khóa pii_masked (mảng chuỗi; giá trị khác mảng thì NULL).
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
      suggested_jar_code, jar_confidence, jar_source, tx_type, review_status, duplicate_of_transaction_id, dedupe_key, fx, pii_masked
    )
    SELECT p_job_id, p_user_id, (e ->> 'seq')::integer, e ->> 'kind', (e ->> 'app_date')::date,
           (e ->> 'amount_vnd')::numeric(14,0), e ->> 'counterparty', e ->> 'description',
           (e ->> 'extract_confidence')::numeric(4,3), e ->> 'suggested_jar_code', (e ->> 'jar_confidence')::numeric(4,3),
           e ->> 'jar_source', e ->> 'tx_type', coalesce(e ->> 'review_status', 'pending'),
           (e ->> 'duplicate_of_transaction_id')::uuid, e ->> 'dedupe_key',
           CASE WHEN jsonb_typeof(e -> 'fx') = 'object' THEN e -> 'fx' END,
           CASE WHEN jsonb_typeof(e -> 'pii_masked') = 'array'
                THEN ARRAY(SELECT jsonb_array_elements_text(e -> 'pii_masked')) END
    FROM jsonb_array_elements(p_rows) AS x(e)
    ON CONFLICT (user_id, dedupe_key) DO NOTHING
    RETURNING r.seq, r.id;
END
$$;

-- @@
-- Như 0054, payload row thêm pii_masked.
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
      'dedupe_key', r.dedupe_key, 'fx', r.fx, 'pii_masked', r.pii_masked)
    FROM ingest_rows r
    WHERE r.job_id = p_job_id
    ORDER BY r.seq
    LIMIT LEAST(GREATEST(coalesce(p_row_limit, 200), 1), 500);
END
$$;
