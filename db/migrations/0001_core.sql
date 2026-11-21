-- 0001_core: schema lõi của Yofina Foresight (PostgreSQL 17+, Aurora Serverless v2).
--
-- CÁCH CHẠY (xem thêm db/README.md)
-- * Chạy bằng secret MASTER, qua RDS Data API, bởi Lambda migrator (infra-cdk/lambdas/migrator);
--   không bao giờ bằng role yofina_app.
-- * Data API chỉ nhận một câu lệnh mỗi lần gọi, nên migrator tách file theo dấu chấm phẩy kết thúc
--   câu lệnh, có nhận biết chuỗi, chú thích và thân dollar-quote (hàm plpgsql, khối DO). Vì vậy MỌI
--   câu lệnh trong file này phải kết thúc bằng dấu chấm phẩy.
-- * Migrator chạy cả file trong MỘT transaction rồi ghi bảng schema_migrations.
-- * MẬT KHẨU của role yofina_app KHÔNG nằm trong file này và file này không nhận tham số nào:
--   migrator tự tạo hoặc đổi mật khẩu từ secret của role đó (ALTER ROLE ... PASSWORD) trước khi chạy
--   các file. Ở đây chỉ bảo đảm role tồn tại với đúng thuộc tính.
-- * Viết lại được (idempotent): IF NOT EXISTS, CREATE OR REPLACE, DROP POLICY IF EXISTS.
-- * Tránh viết dấu hai chấm dính liền chữ cái hoặc dấu gạch dưới (kể cả trong chú thích): Data API có
--   thể hiểu nhầm là tham số có tên. Dạng ép kiểu với hai dấu hai chấm liền nhau thì được.

CREATE TABLE IF NOT EXISTS schema_migrations (
  version    text PRIMARY KEY,
  checksum   text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);

-- Role ứng dụng: không phải owner, không bypass RLS. Không đặt mật khẩu ở đây (xem ghi chú đầu file).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'yofina_app') THEN
    CREATE ROLE yofina_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
  END IF;
END
$$;

ALTER ROLE yofina_app LOGIN NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;

ALTER ROLE yofina_app SET search_path = public;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;

GRANT USAGE ON SCHEMA public TO yofina_app;

-- ===== users: id là sub của Cognito (text). Bảng này cũng có RLS, theo cột id. =====
CREATE TABLE IF NOT EXISTS users (
  id                 text PRIMARY KEY CHECK (length(id) > 0),
  display_name       text NOT NULL CHECK (length(display_name) BETWEEN 1 AND 80),
  monthly_salary_vnd numeric(14,0) CHECK (monthly_salary_vnd IS NULL OR monthly_salary_vnd >= 0),
  payday_day         smallint CHECK (payday_day IS NULL OR payday_day BETWEEN 1 AND 31),
  risk_tolerance     text CHECK (risk_tolerance IS NULL OR risk_tolerance IN ('low', 'medium', 'high')),
  clock_offset_days  integer NOT NULL DEFAULT 0 CHECK (clock_offset_days BETWEEN -3650 AND 3650),
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

COMMENT ON COLUMN users.clock_offset_days IS 'Ngày mô phỏng = ngày hiện tại (giờ ứng dụng) + giá trị này. Xem ADR-0003.';

-- ===== jars: khóa là (user_id, code); code ổn định, chữ thường không dấu. =====
CREATE TABLE IF NOT EXISTS jars (
  user_id       text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  code          text NOT NULL CHECK (code ~ '^[a-z][a-z0-9_]{0,31}$'),
  name          text NOT NULL CHECK (length(name) BETWEEN 1 AND 40),
  color_key     text NOT NULL CHECK (color_key ~ '^[a-z][a-z0-9_-]{0,31}$'),
  icon_key      text NOT NULL CHECK (icon_key ~ '^[a-z][a-z0-9_-]{0,31}$'),
  balance_vnd   numeric(14,0) NOT NULL DEFAULT 0 CHECK (balance_vnd >= 0),
  split_percent numeric(5,2) NOT NULL DEFAULT 0 CHECK (split_percent BETWEEN 0 AND 100),
  sort_order    smallint NOT NULL DEFAULT 0,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, code)
);

CREATE INDEX IF NOT EXISTS jars_user_sort_idx ON jars (user_id, sort_order, code);

-- ===== transactions: sổ cái, mỗi dòng là tác động lên MỘT hũ, số tiền có dấu (âm: ra khỏi hũ). =====
-- Chuyển hũ = hai dòng cùng transfer_id (một âm ở hũ nguồn, một dương ở hũ đích).
-- jar_code NULL = chưa gán hũ. source là chuỗi tự do (seed, manual, move, ...), migration sau mở rộng.
CREATE TABLE IF NOT EXISTS transactions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  occurred_at timestamptz NOT NULL,
  app_date    date NOT NULL,
  kind        text NOT NULL CHECK (kind IN ('expense', 'income', 'transfer')),
  jar_code    text,
  amount_vnd  numeric(14,0) NOT NULL CHECK (amount_vnd <> 0),
  merchant    text CHECK (merchant IS NULL OR length(merchant) <= 120),
  note        text CHECK (note IS NULL OR length(note) <= 200),
  transfer_id uuid,
  source      text NOT NULL DEFAULT 'manual' CHECK (length(source) BETWEEN 1 AND 32),
  created_at  timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (user_id, jar_code) REFERENCES jars (user_id, code),
  CHECK (kind <> 'transfer' OR (transfer_id IS NOT NULL AND jar_code IS NOT NULL)),
  CHECK (kind <> 'expense' OR amount_vnd < 0),
  CHECK (kind <> 'income' OR amount_vnd > 0)
);

CREATE INDEX IF NOT EXISTS transactions_user_time_idx ON transactions (user_id, occurred_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS transactions_user_jar_time_idx ON transactions (user_id, jar_code, occurred_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS transactions_transfer_idx ON transactions (transfer_id) WHERE transfer_id IS NOT NULL;

-- ===== audit_events: chỉ thêm, không sửa, không xóa (kể cả khi đặt lại dữ liệu demo). =====
-- Không có khóa ngoại tới users để bản ghi sống lâu hơn người dùng.
CREATE TABLE IF NOT EXISTS audit_events (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    text NOT NULL CHECK (length(user_id) > 0),
  trace_id   text CHECK (trace_id IS NULL OR length(trace_id) <= 64),
  event_type text NOT NULL CHECK (length(event_type) BETWEEN 1 AND 64),
  tool       text CHECK (tool IS NULL OR length(tool) <= 64),
  outcome    text NOT NULL CHECK (outcome IN ('ok', 'rejected', 'error')),
  code       text CHECK (code IS NULL OR length(code) <= 64),
  params     jsonb CHECK (params IS NULL OR jsonb_typeof(params) = 'object'),
  details    jsonb CHECK (details IS NULL OR jsonb_typeof(details) = 'object'),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_events_user_time_idx ON audit_events (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS audit_events_trace_idx ON audit_events (trace_id) WHERE trace_id IS NOT NULL;

-- ===== turn_blocks: khối UI đã phát, để phát lại khi tải lại trang. =====
-- Thứ tự toàn cục theo id (identity); seq là thứ tự khối trong một lượt (trace_id).
-- Cùng block.id trong một cuộc hội thoại: phía đọc lấy dòng có id lớn nhất.
CREATE TABLE IF NOT EXISTS turn_blocks (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id         text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  conversation_id text NOT NULL CHECK (length(conversation_id) BETWEEN 1 AND 256),
  trace_id        text NOT NULL CHECK (length(trace_id) BETWEEN 1 AND 64),
  seq             integer NOT NULL CHECK (seq >= 0),
  block           jsonb NOT NULL CHECK (jsonb_typeof(block) = 'object'),
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, conversation_id, trace_id, seq)
);

CREATE INDEX IF NOT EXISTS turn_blocks_conversation_idx ON turn_blocks (user_id, conversation_id, id);

-- ===== Row Level Security: mọi bảng dữ liệu người dùng. =====
-- app.user_id do code tin cậy đặt bằng set_config(..., true) trong transaction hoặc trong hàm app_*.
-- Chưa đặt thì current_setting(..., true) là NULL hoặc chuỗi rỗng: policy ra NULL/false, không thấy dòng nào.
-- FORCE áp RLS cả với chủ bảng thường; riêng master của Aurora (rds_superuser) vẫn vượt RLS,
-- nên mọi tool phải dùng secret của yofina_app (docs/research/spike-aurora-data-api.md mục 4).
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

ALTER TABLE users FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_isolation ON users;

CREATE POLICY user_isolation ON users
  USING (id = current_setting('app.user_id', true))
  WITH CHECK (id = current_setting('app.user_id', true));

ALTER TABLE jars ENABLE ROW LEVEL SECURITY;

ALTER TABLE jars FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_isolation ON jars;

CREATE POLICY user_isolation ON jars
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

ALTER TABLE transactions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_isolation ON transactions;

CREATE POLICY user_isolation ON transactions
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_isolation ON audit_events;

CREATE POLICY user_isolation ON audit_events
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

ALTER TABLE turn_blocks ENABLE ROW LEVEL SECURITY;

ALTER TABLE turn_blocks FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_isolation ON turn_blocks;

CREATE POLICY user_isolation ON turn_blocks
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- ===== Quyền tối thiểu cho yofina_app (không có TRUNCATE, REFERENCES, TRIGGER; không đụng schema_migrations). =====
-- users: không xóa (xóa người dùng là việc quản trị). audit_events: chỉ thêm. transactions: không sửa.
GRANT SELECT, INSERT, UPDATE ON users TO yofina_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON jars TO yofina_app;

GRANT SELECT, INSERT, DELETE ON transactions TO yofina_app;

GRANT SELECT, INSERT ON audit_events TO yofina_app;

GRANT SELECT, INSERT, DELETE ON turn_blocks TO yofina_app;

-- ===== Hàm đọc: SECURITY INVOKER (RLS áp theo role gọi), một lệnh gọi Data API mỗi truy vấn. =====
-- Mỗi hàm tự đặt app.user_id trong transaction của chính lệnh gọi (mẫu spike Aurora mục 4.2).
-- Tránh dấu hai chấm dính liền chữ trong thân hàm (xem ghi chú đầu file).
CREATE OR REPLACE FUNCTION app_get_jar_balances(p_user_id text)
RETURNS TABLE (
  code text, name text, color_key text, icon_key text,
  balance_vnd numeric, split_percent numeric, sort_order smallint
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT j.code, j.name, j.color_key, j.icon_key, j.balance_vnd, j.split_percent, j.sort_order
    FROM jars j
    ORDER BY j.sort_order, j.code
    LIMIT 20;
END
$$;

CREATE OR REPLACE FUNCTION app_get_user(p_user_id text)
RETURNS TABLE (
  id text, display_name text, monthly_salary_vnd numeric, payday_day smallint,
  risk_tolerance text, clock_offset_days integer
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT u.id, u.display_name, u.monthly_salary_vnd, u.payday_day, u.risk_tolerance, u.clock_offset_days
    FROM users u
    LIMIT 1;
END
$$;

-- Tối đa 51 dòng mỗi lần (1 MiB là giới hạn cứng của Data API). Người gọi xin limit + 1 để biết còn nữa không.
CREATE OR REPLACE FUNCTION app_query_transactions(
  p_user_id text,
  p_jar     text DEFAULT NULL,
  p_from    date DEFAULT NULL,
  p_to      date DEFAULT NULL,
  p_limit   integer DEFAULT 20
)
RETURNS TABLE (
  id uuid, occurred_at timestamptz, app_date date, kind text, jar_code text,
  amount_vnd numeric, merchant text, note text, transfer_id uuid
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT t.id, t.occurred_at, t.app_date, t.kind, t.jar_code, t.amount_vnd, t.merchant, t.note, t.transfer_id
    FROM transactions t
    WHERE (p_jar IS NULL OR t.jar_code = p_jar)
      AND (p_from IS NULL OR t.app_date >= p_from)
      AND (p_to IS NULL OR t.app_date <= p_to)
    ORDER BY t.occurred_at DESC, t.id DESC
    LIMIT LEAST(GREATEST(coalesce(p_limit, 20), 1), 51);
END
$$;

-- Các khối gần nhất của một cuộc hội thoại, theo thứ tự cũ tới mới (tối đa 300).
CREATE OR REPLACE FUNCTION app_get_conversation_blocks(
  p_user_id         text,
  p_conversation_id text,
  p_limit           integer DEFAULT 200
)
RETURNS TABLE (id bigint, trace_id text, seq integer, block jsonb, created_at timestamptz)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT s.id, s.trace_id, s.seq, s.block, s.created_at
    FROM (
      SELECT b.id, b.trace_id, b.seq, b.block, b.created_at
      FROM turn_blocks b
      WHERE b.conversation_id = p_conversation_id
      ORDER BY b.id DESC
      LIMIT LEAST(GREATEST(coalesce(p_limit, 200), 1), 300)
    ) s
    ORDER BY s.id;
END
$$;

REVOKE ALL ON FUNCTION app_get_jar_balances(text) FROM PUBLIC;

REVOKE ALL ON FUNCTION app_get_user(text) FROM PUBLIC;

REVOKE ALL ON FUNCTION app_query_transactions(text, text, date, date, integer) FROM PUBLIC;

REVOKE ALL ON FUNCTION app_get_conversation_blocks(text, text, integer) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app_get_jar_balances(text) TO yofina_app;

GRANT EXECUTE ON FUNCTION app_get_user(text) TO yofina_app;

GRANT EXECUTE ON FUNCTION app_query_transactions(text, text, date, date, integer) TO yofina_app;

GRANT EXECUTE ON FUNCTION app_get_conversation_blocks(text, text, integer) TO yofina_app;
