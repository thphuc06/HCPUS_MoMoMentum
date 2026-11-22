-- 0007_wallet_ops: hàm đọc gộp cho Tổng quan và Chi tiết hũ, tra cứu theo id, và trạng thái "đã hủy" của đề nghị.
--
-- Nội dung:
-- * confirm_resolutions: thêm cột status (done hoặc cancelled). Người dùng bấm "Không" thì server ghi một dòng cancelled
--   (receipt trống); dòng done vẫn mang receipt. Hai hàm đọc được tạo lại có thêm cột status.
-- * app_get_confirm_block: lấy khối confirm đã lưu của một cuộc hội thoại (để server ép hạn expires_at của đề nghị).
-- * app_get_jar_state: số dư MỌI hũ (kể cả hũ hệ thống, kèm loại, mục tiêu) cùng độ lệch đồng hồ, trong một lệnh gọi.
-- * app_get_overview: mọi thứ Tổng quan cần trong MỘT lệnh gọi (hồ sơ, hũ, tóm tắt dự báo, hạn mức, nghĩa vụ sắp đến hạn,
--   lương chờ, giao dịch gần đây, số cần xem lại). Ngày mô phỏng tính ngay trong hàm từ p_now và p_tz.
-- * app_get_jar_detail: hũ, tóm tắt dự báo, giao dịch gần đây và nghĩa vụ của MỘT hũ trong một lệnh gọi.
-- * app_get_transaction, app_get_review_stats, app_get_jar_usage: tra một giao dịch theo id; đếm giao dịch cần xem lại; mức dùng
--   của từng hũ (để biết hũ nào bỏ được khi lưu danh sách hũ).
--
-- Quy ước như 0005 (db/README.md): chạy bằng secret MASTER, một transaction, tách bằng dòng "-- @@", viết lại được, hàm đọc
-- SECURITY INVOKER tự đặt app.user_id, mọi truy vấn nhiều dòng có LIMIT. Không viết dấu hai chấm dính liền chữ cái hoặc
-- gạch dưới (kể cả trong chú thích); ép kiểu bằng hai dấu hai chấm thì được.

-- ===== confirm_resolutions: thêm trạng thái cancelled =====
ALTER TABLE confirm_resolutions ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'done';

-- @@
ALTER TABLE confirm_resolutions ALTER COLUMN receipt DROP NOT NULL;

-- @@
ALTER TABLE confirm_resolutions DROP CONSTRAINT IF EXISTS confirm_resolutions_status_check;

-- @@
ALTER TABLE confirm_resolutions ADD CONSTRAINT confirm_resolutions_status_check CHECK (
  status IN ('done', 'cancelled') AND ((status = 'done') = (receipt IS NOT NULL))
);

-- @@
DROP FUNCTION IF EXISTS app_get_confirm_resolutions(text, text, integer);

-- @@
DROP FUNCTION IF EXISTS app_get_confirm_resolution(text, text);

-- @@
-- Các đề nghị đã xử lý (done hoặc cancelled) của một cuộc hội thoại, cũ tới mới (tối đa 300).
CREATE FUNCTION app_get_confirm_resolutions(
  p_user_id         text,
  p_conversation_id text,
  p_limit           integer DEFAULT 100
)
RETURNS TABLE (confirm_block_id text, transfer_id uuid, receipt jsonb, resolved_at timestamptz, status text)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT s.confirm_block_id, s.transfer_id, s.receipt, s.resolved_at, s.status
    FROM (
      SELECT r.id, r.confirm_block_id, r.transfer_id, r.receipt, r.resolved_at, r.status
      FROM confirm_resolutions r
      WHERE r.conversation_id = p_conversation_id
      ORDER BY r.id DESC
      LIMIT LEAST(GREATEST(coalesce(p_limit, 100), 1), 300)
    ) s
    ORDER BY s.id;
END
$$;

-- @@
-- Một đề nghị theo id (kiểm trước khi cấp token xác nhận): 0 hoặc 1 dòng.
CREATE FUNCTION app_get_confirm_resolution(
  p_user_id          text,
  p_confirm_block_id text
)
RETURNS TABLE (confirm_block_id text, transfer_id uuid, receipt jsonb, resolved_at timestamptz, status text)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT r.confirm_block_id, r.transfer_id, r.receipt, r.resolved_at, r.status
    FROM confirm_resolutions r
    WHERE r.confirm_block_id = p_confirm_block_id
    LIMIT 1;
END
$$;

-- @@
-- Khối confirm đã lưu (mới nhất) theo id trong một cuộc hội thoại: để biết expires_at của đề nghị. 0 hoặc 1 dòng.
CREATE OR REPLACE FUNCTION app_get_confirm_block(
  p_user_id         text,
  p_conversation_id text,
  p_block_id        text
)
RETURNS TABLE (block jsonb)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT b.block
    FROM turn_blocks b
    WHERE b.conversation_id = p_conversation_id
      AND b.block ->> 'id' = p_block_id
    ORDER BY b.id DESC
    LIMIT 1;
END
$$;

-- @@
-- Số dư MỌI hũ của người dùng (kể cả hũ hệ thống) kèm độ lệch đồng hồ. Người dùng chưa có hàng users thì không ra dòng nào;
-- có hàng users mà chưa có hũ thì một dòng với cột hũ NULL.
CREATE OR REPLACE FUNCTION app_get_jar_state(p_user_id text)
RETURNS TABLE (
  clock_offset_days integer,
  code text, name text, color_key text, icon_key text, balance_vnd numeric, split_percent numeric,
  sort_order smallint, kind text, system_role text, goal_vnd numeric, goal_date date
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT u.clock_offset_days, j.code, j.name, j.color_key, j.icon_key, j.balance_vnd, j.split_percent,
           j.sort_order, j.kind, j.system_role, j.goal_vnd, j.goal_date
    FROM users u
    LEFT JOIN jars j ON j.user_id = u.id
    ORDER BY j.sort_order, j.code
    LIMIT 40;
END
$$;

-- @@
-- Một giao dịch theo id (0 hoặc 1 dòng), kèm tên người nhận. Dùng cho assign_jar.
CREATE OR REPLACE FUNCTION app_get_transaction(p_user_id text, p_id uuid)
RETURNS TABLE (
  id uuid, occurred_at timestamptz, app_date date, kind text, jar_code text, amount_vnd numeric,
  merchant text, note text, transfer_id uuid, tx_type text, funding_source text, payee_id uuid,
  payee_name text, obligation_id uuid, needs_review boolean
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT t.id, t.occurred_at, t.app_date, t.kind, t.jar_code, t.amount_vnd, t.merchant, t.note, t.transfer_id,
           t.tx_type, t.funding_source, t.payee_id, p.name, t.obligation_id, t.needs_review
    FROM transactions t
    LEFT JOIN payees p ON p.user_id = t.user_id AND p.id = t.payee_id
    WHERE t.id = p_id
    LIMIT 1;
END
$$;

-- @@
-- Mức dùng của từng hũ người dùng: số dư, số nghĩa vụ đang hoạt động trả bằng hũ, số dòng sổ cái. Dùng để báo hũ nào bỏ được.
CREATE OR REPLACE FUNCTION app_get_jar_usage(p_user_id text)
RETURNS TABLE (code text, name text, balance_vnd numeric, active_obligations bigint, tx_count bigint)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT j.code, j.name, j.balance_vnd,
           (SELECT count(*) FROM obligations o
              WHERE o.user_id = j.user_id AND o.pay_jar_code = j.code AND o.status = 'active'),
           (SELECT count(*) FROM transactions t WHERE t.user_id = j.user_id AND t.jar_code = j.code)
    FROM jars j
    WHERE j.kind <> 'system'
    ORDER BY j.code
    LIMIT 40;
END
$$;

-- @@
-- Số giao dịch cần xem lại hoặc đang ở Chưa phân loại, và số tiền đã chi chưa phân loại (giá trị tuyệt đối của số dư âm).
CREATE OR REPLACE FUNCTION app_get_review_stats(p_user_id text)
RETURNS TABLE (review_count bigint, pending_total numeric)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT
      (SELECT count(*) FROM transactions t
         LEFT JOIN jars j ON j.user_id = t.user_id AND j.code = t.jar_code
         WHERE t.kind <> 'transfer' AND (t.needs_review OR j.system_role = 'unclassified')),
      (SELECT coalesce(sum(greatest(-j.balance_vnd, 0)), 0) FROM jars j WHERE j.system_role = 'unclassified');
END
$$;

-- @@
-- Tổng quan trong MỘT lệnh gọi. p_now là thời điểm thật, p_tz múi giờ ứng dụng; ngày mô phỏng = ngày theo p_tz cộng
-- clock_offset_days của người dùng (ADR-0003). Người dùng chưa có hồ sơ: profile null, jars rỗng, app_date theo offset 0.
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
        WHERE t.kind <> 'transfer'
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
-- Chi tiết MỘT hũ trong một lệnh gọi: hũ (null nếu không có), tóm tắt dự báo mới nhất, 10 giao dịch gần đây của hũ và nghĩa vụ
-- đang hoạt động trả bằng hũ này (tối đa 10).
CREATE OR REPLACE FUNCTION app_get_jar_detail(p_user_id text, p_jar_code text, p_now timestamptz, p_tz text)
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
    'jar', (
      SELECT jsonb_build_object(
        'code', j.code, 'name', j.name, 'color_key', j.color_key, 'icon_key', j.icon_key,
        'balance_vnd', j.balance_vnd, 'split_percent', j.split_percent, 'sort_order', j.sort_order,
        'kind', j.kind, 'system_role', j.system_role, 'goal_vnd', j.goal_vnd, 'goal_date', j.goal_date)
      FROM jars j WHERE j.code = p_jar_code LIMIT 1
    ),
    'forecast', (
      SELECT to_jsonb(f) FROM app_get_forecast_summaries(p_user_id, p_jar_code) f LIMIT 1
    ),
    'recent_transactions', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
        'id', r.id, 'occurred_at', r.occurred_at, 'app_date', r.app_date, 'kind', r.kind, 'jar_code', r.jar_code,
        'amount_vnd', r.amount_vnd, 'merchant', r.merchant, 'note', r.note, 'transfer_id', r.transfer_id,
        'tx_type', r.tx_type, 'funding_source', r.funding_source, 'payee_id', r.payee_id,
        'payee_name', r.payee_name, 'obligation_id', r.obligation_id, 'needs_review', r.needs_review
      ) ORDER BY r.occurred_at DESC, r.id DESC), '[]'::jsonb)
      FROM (
        SELECT t.id, t.occurred_at, t.app_date, t.kind, t.jar_code, t.amount_vnd, t.merchant, t.note, t.transfer_id,
               t.tx_type, t.funding_source, t.payee_id, p.name AS payee_name, t.obligation_id, t.needs_review
        FROM transactions t
        LEFT JOIN payees p ON p.user_id = t.user_id AND p.id = t.payee_id
        WHERE t.jar_code = p_jar_code
        ORDER BY t.occurred_at DESC, t.id DESC
        LIMIT 10
      ) r
    ),
    'obligations', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
        'id', o.id, 'kind', o.kind, 'name', o.name, 'amount_vnd', o.amount_vnd, 'amount_min_vnd', o.amount_min_vnd,
        'amount_max_vnd', o.amount_max_vnd, 'fee_vnd', o.fee_vnd, 'principal_vnd', o.principal_vnd,
        'due_date', o.due_date, 'cycle', o.cycle, 'due_day', o.due_day, 'status', o.status,
        'pay_jar_code', o.pay_jar_code, 'is_essential', o.is_essential, 'source', o.source
      ) ORDER BY o.due_date, o.id), '[]'::jsonb)
      FROM (
        SELECT * FROM obligations
        WHERE status = 'active' AND pay_jar_code = p_jar_code
        ORDER BY due_date, id
        LIMIT 10
      ) o
    )
  );
END
$$;

-- @@
REVOKE ALL ON FUNCTION app_get_confirm_resolutions(text, text, integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_confirm_resolution(text, text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_confirm_block(text, text, text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_jar_state(text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_transaction(text, uuid) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_jar_usage(text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_review_stats(text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_overview(text, timestamptz, text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_jar_detail(text, text, timestamptz, text) FROM PUBLIC;

-- @@
GRANT EXECUTE ON FUNCTION app_get_confirm_resolutions(text, text, integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_confirm_resolution(text, text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_confirm_block(text, text, text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_jar_state(text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_transaction(text, uuid) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_jar_usage(text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_review_stats(text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_overview(text, timestamptz, text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_jar_detail(text, text, timestamptz, text) TO yofina_app;
