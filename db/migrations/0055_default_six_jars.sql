-- Six default jars. Existing user rows and their allocations are preserved.
ALTER TABLE jars ADD COLUMN purpose text CHECK (
  purpose IS NULL OR (kind = 'saving' AND purpose IN ('buffer', 'sinking', 'goal', 'long_term'))
);
ALTER TABLE jar_templates ADD COLUMN purpose text CHECK (
  purpose IS NULL OR (kind = 'saving' AND purpose IN ('buffer', 'sinking', 'goal', 'long_term'))
);
ALTER TABLE jars DROP CONSTRAINT jars_goal_check;
ALTER TABLE jars ADD CONSTRAINT jars_goal_check CHECK (
  (goal_vnd IS NULL OR goal_vnd > 0)
  AND (goal_date IS NULL OR goal_vnd IS NOT NULL OR coalesce(purpose IN ('sinking', 'long_term'), false))
);

UPDATE jar_templates SET is_default = false WHERE is_default AND code NOT IN
  ('chi_hang_ngay', 'nghia_vu', 'du_phong', 'quy_don', 'muc_tieu', 'tich_luy_dai_han');
-- Experimental split (percent): 35 / 35 / 15 / 5 / 5 / 5.
INSERT INTO jar_templates (code, name, color_key, icon_key, kind, default_split_percent, is_default, sort_order, purpose) VALUES
  ('chi_hang_ngay', 'Chi hằng ngày', 'violet', 'utensils', 'spending', 35, true, 10, NULL),
  ('nghia_vu', 'Nghĩa vụ', 'slate', 'wallet', 'obligation', 35, true, 20, NULL),
  ('du_phong', 'Dự phòng', 'blue', 'shield', 'saving', 15, true, 30, 'buffer'),
  ('quy_don', 'Quỹ dồn', 'teal', 'calendar', 'saving', 5, true, 40, 'sinking'),
  ('muc_tieu', 'Mục tiêu', 'orchid', 'target', 'saving', 5, true, 50, 'goal'),
  ('tich_luy_dai_han', 'Tích lũy dài hạn', 'sky', 'piggybank', 'saving', 5, true, 60, 'long_term'),
  ('an_uong',  'Ăn uống',  'violet', 'utensils', 'spending',   25, false, 10, NULL),
  ('di_lai',   'Đi lại',   'sky',    'bus',      'spending',   10, false, 20, NULL),
  ('hoa_don',  'Hóa đơn',  'brown',  'receipt',  'spending',   30, false, 30, NULL),
  ('giai_tri', 'Giải trí', 'orchid', 'gamepad',  'spending',   10, false, 40, NULL),
  ('du_lich',  'Du lịch',  'teal',   'plane',    'saving',      5, false, 50, NULL)
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name, color_key = EXCLUDED.color_key, icon_key = EXCLUDED.icon_key,
  kind = EXCLUDED.kind, default_split_percent = EXCLUDED.default_split_percent,
  is_default = EXCLUDED.is_default, sort_order = EXCLUDED.sort_order, purpose = EXCLUDED.purpose;

DROP FUNCTION app_list_jars(text);

CREATE OR REPLACE FUNCTION app_list_jars(p_user_id text)
RETURNS TABLE (
  code text, name text, color_key text, icon_key text, balance_vnd numeric, split_percent numeric,
  sort_order smallint, kind text, system_role text, goal_vnd numeric, goal_date date, purpose text
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT j.code, j.name, j.color_key, j.icon_key, j.balance_vnd, j.split_percent,
           j.sort_order, j.kind, j.system_role, j.goal_vnd, j.goal_date, j.purpose
    FROM jars j
    ORDER BY j.sort_order, j.code
    LIMIT 40;
END
$$;

REVOKE ALL ON FUNCTION app_list_jars(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app_list_jars(text) TO yofina_app;

DROP FUNCTION app_get_jar_state(text);

CREATE OR REPLACE FUNCTION app_get_jar_state(p_user_id text)
RETURNS TABLE (
  clock_offset_days integer,
  code text, name text, color_key text, icon_key text, balance_vnd numeric, split_percent numeric,
  sort_order smallint, kind text, system_role text, goal_vnd numeric, goal_date date, purpose text
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT u.clock_offset_days, j.code, j.name, j.color_key, j.icon_key, j.balance_vnd, j.split_percent,
           j.sort_order, j.kind, j.system_role, j.goal_vnd, j.goal_date, j.purpose
    FROM users u
    LEFT JOIN jars j ON j.user_id = u.id
    ORDER BY j.sort_order, j.code
    LIMIT 40;
END
$$;

REVOKE ALL ON FUNCTION app_get_jar_state(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app_get_jar_state(text) TO yofina_app;

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
        'kind', j.kind, 'system_role', j.system_role, 'goal_vnd', j.goal_vnd, 'goal_date', j.goal_date, 'purpose', j.purpose
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
        'kind', j.kind, 'system_role', j.system_role, 'goal_vnd', j.goal_vnd, 'goal_date', j.goal_date, 'purpose', j.purpose)
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
    ) || jsonb_strip_nulls(jsonb_build_object('purpose', j.purpose))
    FROM (SELECT * FROM jars ORDER BY sort_order, code LIMIT 40) j;
  RETURN QUERY
    SELECT 'obligation'::text, o.pay_jar_code, jsonb_build_object(
      'id', o.id, 'kind', o.kind, 'name', o.name, 'amount_vnd', o.amount_vnd, 'amount_min_vnd', o.amount_min_vnd,
      'amount_max_vnd', o.amount_max_vnd, 'due_date', o.due_date, 'cycle', o.cycle, 'due_day', o.due_day,
      'pay_jar_code', o.pay_jar_code)
    FROM app_list_obligations(p_user_id, 'active', NULL, 100) o;
END
$$;
