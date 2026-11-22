-- 0005_wallet: ví mô phỏng của phase 2 (hũ có loại, người nhận, nghĩa vụ, hạn mức trả sau, sự kiện lương,
-- luật phân loại, bảng tra loại giao dịch, biểu phí có cấu trúc).
--
-- Nội dung (chi tiết thiết kế: docs/plan/phases/phase-2-vi-va-du-bao.md mục "Quyết định hợp đồng phase 2"):
-- * jars: thêm kind (spending, saving, obligation, system), system_role (other_income, unclassified), mục tiêu và hạn.
--   "Tiền vào khác" và "Chưa phân loại" là HAI HŨ HỆ THỐNG (kind system) của mỗi người dùng, không phải bảng riêng.
--   Số dư mọi hũ cộng lại là tổng số dư của ví mô phỏng. Hũ chưa phân loại được phép ÂM (tiền đã chi nhưng chưa xếp hũ).
-- * transactions: thêm tx_type, funding_source (jar hoặc credit), payee_id, obligation_id, dedupe_key, nhãn phân loại.
--   Cột merchant là đối tác, cột note là lời nhắn (đã có từ 0001). Dòng funding_source credit KHÔNG đổi số dư hũ.
-- * Bảng mới có user_id (RLS FORCE): payees, obligations, credit_lines, category_rules, salary_events.
-- * Bảng tra dùng chung, không có user_id, chỉ SELECT cho yofina_app: tx_type_map, fee_schedules, jar_templates.
--   Dữ liệu của chúng nằm ở db/seed/*.sql (nạp bằng scripts/migrate.py --seed), không nằm trong file này.
-- * confirm_resolutions: biên nhận của tool ghi mới không có transfer_id, nên bỏ NOT NULL ở cột đó.
--
-- Quy ước như 0001 (db/README.md): chạy bằng secret MASTER qua Lambda migrator, một transaction, tách câu lệnh
-- bằng dòng chỉ gồm "-- @@", viết lại được, RLS FORCE theo user_id, hàm đọc SECURITY INVOKER tự đặt app.user_id,
-- mọi truy vấn nhiều dòng có LIMIT. Không viết dấu hai chấm dính liền chữ cái hoặc gạch dưới (kể cả trong chú thích),
-- ép kiểu bằng hai dấu hai chấm thì được. Không đụng mật khẩu role. Không chạy ALTER ROLE ở đây.

-- ===== payees: người nhận của ví mô phỏng (dữ liệu seed theo persona; không lưu số tài khoản đầy đủ) =====
CREATE TABLE IF NOT EXISTS payees (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  name         text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
  account_hint text CHECK (account_hint IS NULL OR length(account_hint) <= 40),
  is_favorite  boolean NOT NULL DEFAULT false,
  last_used_at timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, id)
);

-- @@
CREATE INDEX IF NOT EXISTS payees_user_idx ON payees (user_id, is_favorite DESC, last_used_at DESC NULLS LAST, name);

-- @@
-- ===== obligations: mọi khoản tiền ra theo lịch (trả sau tự sinh, khoản vay, tiền trọ, hóa đơn, thuê bao) =====
-- amount_vnd là số tiền KỲ VỌNG (dùng cho dự báo). Khoản có khoảng thì thêm amount_min_vnd và amount_max_vnd.
-- due_date là ngày đến hạn KẾ TIẾP (ngày mô phỏng). Khoản lặp (cycle khác once) được trả thì dời due_date, không đổi trạng thái.
-- Trả sau (kind bnpl, source bnpl_auto): một dòng hoạt động cho mỗi ngày đến hạn, mua thêm trong kỳ thì cộng dồn principal_vnd.
CREATE TABLE IF NOT EXISTS obligations (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  kind                  text NOT NULL,
  name                  text NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
  amount_vnd            numeric(14,0) NOT NULL CHECK (amount_vnd > 0),
  amount_min_vnd        numeric(14,0),
  amount_max_vnd        numeric(14,0),
  fee_vnd               numeric(14,0) NOT NULL DEFAULT 0 CHECK (fee_vnd >= 0),
  principal_vnd         numeric(14,0) CHECK (principal_vnd IS NULL OR principal_vnd > 0),
  due_date              date NOT NULL,
  cycle                 text NOT NULL DEFAULT 'once',
  due_day               smallint CHECK (due_day IS NULL OR due_day BETWEEN 1 AND 31),
  status                text NOT NULL DEFAULT 'active',
  pay_jar_code          text,
  is_essential          boolean NOT NULL DEFAULT false,
  source                text NOT NULL DEFAULT 'declared',
  source_transaction_id uuid,
  fee_schedule_id       uuid,
  paid_at               timestamptz,
  paid_transaction_id   uuid,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, id),
  FOREIGN KEY (user_id, pay_jar_code) REFERENCES jars (user_id, code),
  CONSTRAINT obligations_kind_check CHECK (kind IN ('bnpl', 'loan', 'rent', 'bill', 'subscription')),
  CONSTRAINT obligations_cycle_check CHECK (cycle IN ('once', 'weekly', 'monthly', 'yearly')),
  CONSTRAINT obligations_status_check CHECK (status IN ('active', 'paid', 'cancelled')),
  CONSTRAINT obligations_source_check CHECK (source IN ('declared', 'bnpl_auto')),
  CONSTRAINT obligations_range_check CHECK (
    (amount_min_vnd IS NULL) = (amount_max_vnd IS NULL)
    AND (amount_min_vnd IS NULL OR (amount_min_vnd <= amount_vnd AND amount_vnd <= amount_max_vnd))
  ),
  CONSTRAINT obligations_bnpl_check CHECK (
    (kind = 'bnpl') = (source = 'bnpl_auto')
    AND (kind <> 'bnpl' OR (principal_vnd IS NOT NULL AND amount_vnd = principal_vnd + fee_vnd))
  )
);

-- @@
CREATE INDEX IF NOT EXISTS obligations_user_due_idx ON obligations (user_id, status, due_date);

-- @@
CREATE UNIQUE INDEX IF NOT EXISTS obligations_bnpl_cycle_uidx ON obligations (user_id, due_date)
  WHERE kind = 'bnpl' AND status = 'active';

-- @@
-- ===== credit_lines: hạn mức trả sau mô phỏng (một dòng mỗi người dùng) =====
-- outstanding_vnd là tổng GỐC chưa trả của các nghĩa vụ bnpl đang hoạt động (phí không tính vào dư nợ).
CREATE TABLE IF NOT EXISTS credit_lines (
  user_id         text PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
  product_code    text NOT NULL DEFAULT 'bnpl_sim' CHECK (product_code ~ '^[a-z][a-z0-9_]{0,31}$'),
  limit_vnd       numeric(14,0) NOT NULL CHECK (limit_vnd >= 0),
  outstanding_vnd numeric(14,0) NOT NULL DEFAULT 0 CHECK (outstanding_vnd >= 0),
  due_day         smallint NOT NULL DEFAULT 5 CHECK (due_day BETWEEN 1 AND 31),
  status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CHECK (outstanding_vnd <= limit_vnd)
);

-- @@
-- ===== category_rules: luật phân loại học từ lần người dùng sửa (bước 1 của phân loại; phase 4 dùng) =====
CREATE TABLE IF NOT EXISTS category_rules (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  match_type     text NOT NULL CHECK (match_type IN ('payee', 'merchant')),
  payee_id       uuid,
  merchant_key   text CHECK (merchant_key IS NULL OR length(merchant_key) BETWEEN 1 AND 120),
  jar_code       text NOT NULL,
  scope          text NOT NULL CHECK (scope IN ('once', 'always')),
  transaction_id uuid,
  hit_count      integer NOT NULL DEFAULT 0 CHECK (hit_count >= 0),
  last_used_at   timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (user_id, jar_code) REFERENCES jars (user_id, code) ON DELETE CASCADE,
  FOREIGN KEY (user_id, payee_id) REFERENCES payees (user_id, id) ON DELETE CASCADE,
  CHECK ((match_type = 'payee') = (payee_id IS NOT NULL)),
  CHECK ((match_type = 'merchant') = (merchant_key IS NOT NULL))
);

-- @@
-- Mỗi (người dùng, đối tượng) chỉ một luật "luôn luôn"; luật "một lần" chỉ để ghi lại lần sửa.
CREATE UNIQUE INDEX IF NOT EXISTS category_rules_payee_always_uidx ON category_rules (user_id, payee_id)
  WHERE scope = 'always' AND match_type = 'payee';

-- @@
CREATE UNIQUE INDEX IF NOT EXISTS category_rules_merchant_always_uidx ON category_rules (user_id, merchant_key)
  WHERE scope = 'always' AND match_type = 'merchant';

-- @@
-- ===== jars: loại hũ, hũ hệ thống, mục tiêu và hạn =====
ALTER TABLE jars ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'spending';

-- @@
ALTER TABLE jars ADD COLUMN IF NOT EXISTS system_role text;

-- @@
ALTER TABLE jars ADD COLUMN IF NOT EXISTS goal_vnd numeric(14,0);

-- @@
ALTER TABLE jars ADD COLUMN IF NOT EXISTS goal_date date;

-- @@
ALTER TABLE jars DROP CONSTRAINT IF EXISTS jars_kind_check;

-- @@
ALTER TABLE jars ADD CONSTRAINT jars_kind_check CHECK (kind IN ('spending', 'saving', 'obligation', 'system'));

-- @@
ALTER TABLE jars DROP CONSTRAINT IF EXISTS jars_system_check;

-- @@
-- Hũ hệ thống có system_role (và ngược lại), không có tỷ lệ chia lương, không có mục tiêu.
ALTER TABLE jars ADD CONSTRAINT jars_system_check CHECK (
  (kind = 'system') = (system_role IS NOT NULL)
  AND (system_role IS NULL OR system_role IN ('other_income', 'unclassified'))
  AND (kind <> 'system' OR (split_percent = 0 AND goal_vnd IS NULL AND goal_date IS NULL))
);

-- @@
ALTER TABLE jars DROP CONSTRAINT IF EXISTS jars_goal_check;

-- @@
ALTER TABLE jars ADD CONSTRAINT jars_goal_check CHECK (
  (goal_vnd IS NULL OR goal_vnd > 0) AND (goal_date IS NULL OR goal_vnd IS NOT NULL)
);

-- @@
-- Số dư không âm, trừ hũ chưa phân loại (tiền đã chi nhưng chưa xếp hũ nên số dư của nó âm).
-- Gỡ MỌI ràng buộc CHECK cũ nhắc tới balance_vnd (của 0001, tên tự đặt là jars_balance_vnd_check) trừ ràng buộc mới, kể cả
-- khi tên khác: nếu sót thì số dư âm của Chưa phân loại vẫn bị chặn.
DO $$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT c.conname
    FROM pg_constraint c
    WHERE c.conrelid = 'jars'::regclass
      AND c.contype = 'c'
      AND c.conname <> 'jars_balance_check'
      AND pg_get_constraintdef(c.oid) LIKE '%balance_vnd%'
  LOOP
    EXECUTE format('ALTER TABLE jars DROP CONSTRAINT %I', r.conname);
  END LOOP;
END
$$;

-- @@
ALTER TABLE jars DROP CONSTRAINT IF EXISTS jars_balance_check;

-- @@
ALTER TABLE jars ADD CONSTRAINT jars_balance_check CHECK (balance_vnd >= 0 OR coalesce(system_role, '') = 'unclassified');

-- @@
CREATE UNIQUE INDEX IF NOT EXISTS jars_system_role_uidx ON jars (user_id, system_role) WHERE system_role IS NOT NULL;

-- @@
-- ===== transactions: loại giao dịch, nguồn trả, người nhận, nghĩa vụ, khử trùng, nhãn phân loại =====
-- tx_type là mã trong tx_type_map (không có khóa ngoại để file seed không phải chạy trước khi ghi sổ cái).
-- funding_source: jar (trừ số dư hũ) hoặc credit (mua bằng hạn mức trả sau: KHÔNG đổi số dư hũ, jar_code là hũ để tính chi tiêu).
-- Bất biến: số dư mỗi hũ bằng tổng amount_vnd của các dòng funding_source jar của hũ đó.
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS tx_type text NOT NULL DEFAULT 'other';

-- @@
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS funding_source text NOT NULL DEFAULT 'jar';

-- @@
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS payee_id uuid;

-- @@
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS obligation_id uuid;

-- @@
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS dedupe_key text;

-- @@
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS classified_by text;

-- @@
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS classification_confidence numeric(4,3);

-- @@
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS needs_review boolean NOT NULL DEFAULT false;

-- @@
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS suggested_jars text[];

-- @@
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_tx_type_check;

-- @@
ALTER TABLE transactions ADD CONSTRAINT transactions_tx_type_check CHECK (tx_type ~ '^[a-z][a-z0-9_]{0,39}$');

-- @@
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_funding_check;

-- @@
ALTER TABLE transactions ADD CONSTRAINT transactions_funding_check CHECK (
  funding_source IN ('jar', 'credit') AND (funding_source = 'jar' OR kind = 'expense')
);

-- @@
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_classified_check;

-- @@
ALTER TABLE transactions ADD CONSTRAINT transactions_classified_check CHECK (
  (classified_by IS NULL OR classified_by IN ('user', 'type_map', 'rule', 'embedding', 'llm', 'seed'))
  AND (classification_confidence IS NULL OR classification_confidence BETWEEN 0 AND 1)
  AND (suggested_jars IS NULL OR cardinality(suggested_jars) <= 2)
);

-- @@
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_dedupe_check;

-- @@
ALTER TABLE transactions ADD CONSTRAINT transactions_dedupe_check CHECK (dedupe_key IS NULL OR dedupe_key ~ '^[0-9a-f]{64}$');

-- @@
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_payee_fk;

-- @@
ALTER TABLE transactions ADD CONSTRAINT transactions_payee_fk FOREIGN KEY (user_id, payee_id) REFERENCES payees (user_id, id);

-- @@
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_obligation_fk;

-- @@
ALTER TABLE transactions ADD CONSTRAINT transactions_obligation_fk FOREIGN KEY (user_id, obligation_id) REFERENCES obligations (user_id, id);

-- @@
-- Khử trùng: khóa băm (ngày mô phỏng, số tiền, đối tác chuẩn hóa, phần phân biệt) duy nhất theo người dùng; vắng thì không kiểm.
CREATE UNIQUE INDEX IF NOT EXISTS transactions_dedupe_uidx ON transactions (user_id, dedupe_key) WHERE dedupe_key IS NOT NULL;

-- @@
CREATE INDEX IF NOT EXISTS transactions_review_idx ON transactions (user_id, occurred_at DESC, id DESC) WHERE needs_review;

-- @@
CREATE INDEX IF NOT EXISTS transactions_user_date_idx ON transactions (user_id, app_date, jar_code);

-- @@
-- ===== salary_events: lương về, chờ người dùng xác nhận một chạm rồi chia vào hũ =====
-- period_date là kỳ lương (ngày lương gần nhất với ngày nhận). status pending (chờ), confirmed (đã chia), kept_other (giữ ở Tiền vào khác).
-- deviation_percent là lệch so với lương đã khai lúc nhận (dương: nhiều hơn). ask_update_salary bật khi lệch quá ngưỡng cấu hình.
CREATE TABLE IF NOT EXISTS salary_events (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  period_date        date NOT NULL,
  transaction_id     uuid NOT NULL,
  received_on        date NOT NULL,
  expected_vnd       numeric(14,0) CHECK (expected_vnd IS NULL OR expected_vnd > 0),
  amount_vnd         numeric(14,0) NOT NULL CHECK (amount_vnd > 0),
  deviation_percent  numeric(8,2) NOT NULL DEFAULT 0,
  ask_update_salary  boolean NOT NULL DEFAULT false,
  status             text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'kept_other')),
  split              jsonb CHECK (split IS NULL OR jsonb_typeof(split) = 'array'),
  confirmed_at       timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (transaction_id),
  FOREIGN KEY (transaction_id) REFERENCES transactions (id) ON DELETE CASCADE,
  CHECK ((status = 'pending') = (confirmed_at IS NULL))
);

-- @@
CREATE INDEX IF NOT EXISTS salary_events_user_idx ON salary_events (user_id, status, period_date DESC);

-- @@
-- ===== bảng tra dùng chung (không có user_id, không RLS): chỉ đọc với yofina_app, dữ liệu ở db/seed/*.sql =====
-- tx_type_map: bước 0 của phân loại (loại giao dịch sang hũ). Trả về default_jar_code (mã hũ chuẩn, nếu người dùng có hũ đó)
-- hoặc system_role (hũ hệ thống). Cả hai trống: loại nội bộ, không phân loại.
CREATE TABLE IF NOT EXISTS tx_type_map (
  tx_type          text PRIMARY KEY CHECK (tx_type ~ '^[a-z][a-z0-9_]{0,39}$'),
  label            text NOT NULL CHECK (length(label) BETWEEN 1 AND 60),
  direction        text NOT NULL CHECK (direction IN ('in', 'out', 'internal')),
  default_jar_code text CHECK (default_jar_code IS NULL OR default_jar_code ~ '^[a-z][a-z0-9_]{0,31}$'),
  system_role      text CHECK (system_role IS NULL OR system_role IN ('other_income', 'unclassified')),
  is_selectable    boolean NOT NULL DEFAULT true,
  sort_order       smallint NOT NULL DEFAULT 0,
  CHECK (default_jar_code IS NULL OR system_role IS NULL),
  CHECK (direction = 'internal' OR default_jar_code IS NOT NULL OR system_role IS NOT NULL)
);

-- @@
-- fee_schedules: biểu phí có cấu trúc theo sản phẩm tín dụng, kèm nguồn và ngày hiệu lực (không gắn cứng trong mã).
-- period: per_month, per_transaction, once. condition_code: always, month_has_transaction, overdue.
-- Phí cố định dùng amount_vnd, phí theo tỷ lệ dùng rate_percent (đúng một trong hai).
CREATE TABLE IF NOT EXISTS fee_schedules (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_code   text NOT NULL CHECK (product_code ~ '^[a-z][a-z0-9_]{0,31}$'),
  product_label  text NOT NULL CHECK (length(product_label) BETWEEN 1 AND 60),
  fee_type       text NOT NULL CHECK (fee_type ~ '^[a-z][a-z0-9_]{0,39}$'),
  amount_vnd     numeric(14,0) CHECK (amount_vnd IS NULL OR amount_vnd >= 0),
  rate_percent   numeric(7,4) CHECK (rate_percent IS NULL OR rate_percent >= 0),
  period         text NOT NULL CHECK (period IN ('per_month', 'per_transaction', 'once')),
  condition_code text NOT NULL CHECK (condition_code IN ('always', 'month_has_transaction', 'overdue')),
  condition_note text CHECK (condition_note IS NULL OR length(condition_note) <= 200),
  source_name    text NOT NULL CHECK (length(source_name) BETWEEN 1 AND 200),
  source_url     text NOT NULL CHECK (source_url ~ '^https://'),
  effective_from date NOT NULL,
  effective_to   date,
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (product_code, fee_type, effective_from),
  CHECK ((amount_vnd IS NULL) <> (rate_percent IS NULL)),
  CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

-- @@
-- jar_templates: gợi ý hũ mặc định cho tài khoản mới (onboarding chỉ cần lương và ngày nhận thì hệ thống tạo hũ từ đây).
CREATE TABLE IF NOT EXISTS jar_templates (
  code                  text PRIMARY KEY CHECK (code ~ '^[a-z][a-z0-9_]{0,31}$'),
  name                  text NOT NULL CHECK (length(name) BETWEEN 1 AND 40),
  color_key             text NOT NULL CHECK (color_key ~ '^[a-z][a-z0-9_-]{0,31}$'),
  icon_key              text NOT NULL CHECK (icon_key ~ '^[a-z][a-z0-9_-]{0,31}$'),
  kind                  text NOT NULL CHECK (kind IN ('spending', 'saving', 'obligation')),
  default_split_percent numeric(5,2) NOT NULL CHECK (default_split_percent BETWEEN 0 AND 100),
  is_default            boolean NOT NULL DEFAULT true,
  sort_order            smallint NOT NULL DEFAULT 0
);

-- @@
-- ===== confirm_resolutions: biên nhận của tool ghi mới không nhất thiết có transfer_id =====
-- Cột transfer_id giữ tên cũ để tương thích; với tool khác chuyển hũ nó mang reference_id của biên nhận (có thể trống).
ALTER TABLE confirm_resolutions ALTER COLUMN transfer_id DROP NOT NULL;

-- @@
ALTER TABLE confirm_resolutions ADD COLUMN IF NOT EXISTS action_tool text;

-- @@
-- ===== Row Level Security cho mọi bảng mới có user_id =====
ALTER TABLE payees ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE payees FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON payees;

-- @@
CREATE POLICY user_isolation ON payees
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
ALTER TABLE obligations ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE obligations FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON obligations;

-- @@
CREATE POLICY user_isolation ON obligations
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
ALTER TABLE credit_lines ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE credit_lines FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON credit_lines;

-- @@
CREATE POLICY user_isolation ON credit_lines
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
ALTER TABLE category_rules ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE category_rules FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON category_rules;

-- @@
CREATE POLICY user_isolation ON category_rules
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
ALTER TABLE salary_events ENABLE ROW LEVEL SECURITY;

-- @@
ALTER TABLE salary_events FORCE ROW LEVEL SECURITY;

-- @@
DROP POLICY IF EXISTS user_isolation ON salary_events;

-- @@
CREATE POLICY user_isolation ON salary_events
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- @@
-- ===== Quyền tối thiểu =====
-- Các bảng người dùng mới: đọc, thêm, sửa, xóa (xóa khi đặt lại demo hoặc người dùng gỡ một khoản).
GRANT SELECT, INSERT, UPDATE, DELETE ON payees TO yofina_app;

-- @@
GRANT SELECT, INSERT, UPDATE, DELETE ON obligations TO yofina_app;

-- @@
GRANT SELECT, INSERT, UPDATE, DELETE ON credit_lines TO yofina_app;

-- @@
GRANT SELECT, INSERT, UPDATE, DELETE ON category_rules TO yofina_app;

-- @@
GRANT SELECT, INSERT, UPDATE, DELETE ON salary_events TO yofina_app;

-- @@
-- Sổ cái vẫn không cho sửa số tiền, hũ nguồn trả hay thời điểm; chỉ các cột phân loại và liên kết được sửa (gán lại hũ, xem lại).
GRANT UPDATE (jar_code, needs_review, classified_by, classification_confidence, suggested_jars, obligation_id, payee_id) ON transactions TO yofina_app;

-- @@
GRANT SELECT ON tx_type_map TO yofina_app;

-- @@
GRANT SELECT ON fee_schedules TO yofina_app;

-- @@
GRANT SELECT ON jar_templates TO yofina_app;

-- @@
-- ===== Hàm đọc (SECURITY INVOKER, tự đặt app.user_id, có LIMIT) =====
-- Tạo hai hũ hệ thống nếu chưa có (Tiền vào khác, Chưa phân loại). Gọi ở onboarding, đặt lại demo và nạp seed. Trả số hũ vừa tạo.
CREATE OR REPLACE FUNCTION app_ensure_system_jars(p_user_id text)
RETURNS integer
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
  created integer;
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  INSERT INTO jars (user_id, code, name, color_key, icon_key, balance_vnd, split_percent, sort_order, kind, system_role)
  SELECT p_user_id, v.code, v.name, 'gray', v.icon_key, 0, 0, v.sort_order, 'system', v.system_role
  FROM (VALUES
    ('tien_vao_khac', 'Tiền vào khác', 'inbox', 1000, 'other_income'),
    ('chua_phan_loai', 'Chưa phân loại', 'help', 1001, 'unclassified')
  ) AS v (code, name, icon_key, sort_order, system_role)
  WHERE EXISTS (SELECT 1 FROM users u WHERE u.id = p_user_id)
  ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS created = ROW_COUNT;
  RETURN created;
END
$$;

-- @@
-- Mọi hũ của người dùng (kể cả hũ hệ thống), theo thứ tự hiển thị, đủ cột của phase 2 (tối đa 40).
CREATE OR REPLACE FUNCTION app_list_jars(p_user_id text)
RETURNS TABLE (
  code text, name text, color_key text, icon_key text, balance_vnd numeric, split_percent numeric,
  sort_order smallint, kind text, system_role text, goal_vnd numeric, goal_date date
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT j.code, j.name, j.color_key, j.icon_key, j.balance_vnd, j.split_percent,
           j.sort_order, j.kind, j.system_role, j.goal_vnd, j.goal_date
    FROM jars j
    ORDER BY j.sort_order, j.code
    LIMIT 40;
END
$$;

-- @@
-- Nghĩa vụ theo trạng thái ('active', 'paid', 'cancelled' hoặc 'all'), đến hạn không muộn hơn p_due_before nếu có, ngày đến hạn gần nhất trước.
CREATE OR REPLACE FUNCTION app_list_obligations(
  p_user_id    text,
  p_status     text DEFAULT 'active',
  p_due_before date DEFAULT NULL,
  p_limit      integer DEFAULT 50
)
RETURNS TABLE (
  id uuid, kind text, name text, amount_vnd numeric, amount_min_vnd numeric, amount_max_vnd numeric,
  fee_vnd numeric, principal_vnd numeric, due_date date, cycle text, due_day smallint, status text,
  pay_jar_code text, is_essential boolean, source text, source_transaction_id uuid,
  paid_at timestamptz, paid_transaction_id uuid
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT o.id, o.kind, o.name, o.amount_vnd, o.amount_min_vnd, o.amount_max_vnd,
           o.fee_vnd, o.principal_vnd, o.due_date, o.cycle, o.due_day, o.status,
           o.pay_jar_code, o.is_essential, o.source, o.source_transaction_id,
           o.paid_at, o.paid_transaction_id
    FROM obligations o
    WHERE (p_status IS NULL OR p_status = 'all' OR o.status = p_status)
      AND (p_due_before IS NULL OR o.due_date <= p_due_before)
    ORDER BY o.due_date, o.id
    LIMIT LEAST(GREATEST(coalesce(p_limit, 50), 1), 100);
END
$$;

-- @@
-- Người nhận đã lưu: yêu thích trước, rồi dùng gần nhất (tối đa 100).
CREATE OR REPLACE FUNCTION app_list_payees(p_user_id text, p_limit integer DEFAULT 50)
RETURNS TABLE (id uuid, name text, account_hint text, is_favorite boolean, last_used_at timestamptz)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT p.id, p.name, p.account_hint, p.is_favorite, p.last_used_at
    FROM payees p
    ORDER BY p.is_favorite DESC, p.last_used_at DESC NULLS LAST, p.name
    LIMIT LEAST(GREATEST(coalesce(p_limit, 50), 1), 100);
END
$$;

-- @@
-- Hạn mức trả sau mô phỏng: 0 hoặc 1 dòng.
CREATE OR REPLACE FUNCTION app_get_credit_line(p_user_id text)
RETURNS TABLE (product_code text, limit_vnd numeric, outstanding_vnd numeric, due_day smallint, status text)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT c.product_code, c.limit_vnd, c.outstanding_vnd, c.due_day, c.status
    FROM credit_lines c
    LIMIT 1;
END
$$;

-- @@
-- Giao dịch có lọc và phân trang con trỏ (occurred_at, id) giảm dần. Xin limit + 1 để biết còn nữa không (tối đa 51 dòng).
-- Con trỏ: truyền p_cursor_at và p_cursor_id của dòng cuối trang trước. p_kind, p_tx_type, p_jar lọc đúng bằng.
CREATE OR REPLACE FUNCTION app_list_transactions(
  p_user_id      text,
  p_jar          text DEFAULT NULL,
  p_from         date DEFAULT NULL,
  p_to           date DEFAULT NULL,
  p_kind         text DEFAULT NULL,
  p_tx_type      text DEFAULT NULL,
  p_needs_review boolean DEFAULT NULL,
  p_cursor_at    timestamptz DEFAULT NULL,
  p_cursor_id    uuid DEFAULT NULL,
  p_limit        integer DEFAULT 20
)
RETURNS TABLE (
  id uuid, occurred_at timestamptz, app_date date, kind text, jar_code text, amount_vnd numeric,
  merchant text, note text, transfer_id uuid, tx_type text, funding_source text, payee_id uuid,
  payee_name text, obligation_id uuid, needs_review boolean, classified_by text
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT t.id, t.occurred_at, t.app_date, t.kind, t.jar_code, t.amount_vnd,
           t.merchant, t.note, t.transfer_id, t.tx_type, t.funding_source, t.payee_id,
           p.name, t.obligation_id, t.needs_review, t.classified_by
    FROM transactions t
    LEFT JOIN payees p ON p.user_id = t.user_id AND p.id = t.payee_id
    WHERE (p_jar IS NULL OR t.jar_code = p_jar)
      AND (p_from IS NULL OR t.app_date >= p_from)
      AND (p_to IS NULL OR t.app_date <= p_to)
      AND (p_kind IS NULL OR t.kind = p_kind)
      AND (p_tx_type IS NULL OR t.tx_type = p_tx_type)
      AND (p_needs_review IS NULL OR t.needs_review = p_needs_review)
      AND (p_cursor_at IS NULL OR (t.occurred_at, t.id) < (p_cursor_at, coalesce(p_cursor_id, 'ffffffff-ffff-ffff-ffff-ffffffffffff'::uuid)))
    ORDER BY t.occurred_at DESC, t.id DESC
    LIMIT LEAST(GREATEST(coalesce(p_limit, 20), 1), 51);
END
$$;

-- @@
-- Giao dịch đang ở hũ Chưa phân loại hoặc đánh dấu cần xem lại (không gồm dòng chuyển hũ), mới nhất trước (tối đa 50).
CREATE OR REPLACE FUNCTION app_get_unclassified(p_user_id text, p_limit integer DEFAULT 20)
RETURNS TABLE (
  id uuid, occurred_at timestamptz, app_date date, kind text, jar_code text, amount_vnd numeric,
  merchant text, note text, tx_type text, payee_id uuid, payee_name text, needs_review boolean,
  classified_by text, classification_confidence numeric, suggested_jars text[]
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT t.id, t.occurred_at, t.app_date, t.kind, t.jar_code, t.amount_vnd,
           t.merchant, t.note, t.tx_type, t.payee_id, p.name, t.needs_review,
           t.classified_by, t.classification_confidence, t.suggested_jars
    FROM transactions t
    LEFT JOIN payees p ON p.user_id = t.user_id AND p.id = t.payee_id
    LEFT JOIN jars j ON j.user_id = t.user_id AND j.code = t.jar_code
    WHERE t.kind <> 'transfer'
      AND (t.needs_review OR j.system_role = 'unclassified')
    ORDER BY t.occurred_at DESC, t.id DESC
    LIMIT LEAST(GREATEST(coalesce(p_limit, 20), 1), 50);
END
$$;

-- @@
-- Chi tiêu theo hũ theo ngày trong khoảng [p_from, p_to] (ngày mô phỏng): đầu vào lịch sử của dự báo.
-- Chỉ tính dòng chi trừ số dư hũ (funding_source jar) và KHÔNG gắn nghĩa vụ (obligation_id trống): khoản trả theo lịch đã nằm
-- trong lịch nghĩa vụ, tính hai lần là sai. Ngày không có chi tiêu không có dòng (người gọi điền 0). Hũ hệ thống không có dòng.
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
      AND t.funding_source = 'jar'
      AND t.obligation_id IS NULL
      AND j.kind <> 'system'
      AND t.app_date BETWEEN p_from AND p_to
    GROUP BY t.jar_code, t.app_date
    ORDER BY t.jar_code, t.app_date
    LIMIT 5000;
END
$$;

-- @@
-- Tổng thu chi trong [p_from, p_to] (ngày mô phỏng), dạng jsonb một lệnh gọi:
-- by_jar: chi tiêu theo hũ (mọi nguồn trả, kể cả trả sau); income_by_type: tiền vào theo loại giao dịch (lương tách khỏi tiền vào khác).
-- Không tính dòng chuyển hũ và chia lương (kind transfer).
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
        WHERE t.kind = 'expense' AND t.app_date BETWEEN p_from AND p_to
        GROUP BY t.jar_code
        LIMIT 40
      ) s
    ),
    'income_by_type', (
      SELECT coalesce(jsonb_agg(jsonb_build_object('tx_type', s.tx_type, 'amount_vnd', s.total, 'tx_count', s.n) ORDER BY s.tx_type), '[]'::jsonb)
      FROM (
        SELECT t.tx_type, sum(t.amount_vnd) AS total, count(*) AS n
        FROM transactions t
        WHERE t.kind = 'income' AND t.app_date BETWEEN p_from AND p_to
        GROUP BY t.tx_type
        LIMIT 40
      ) s
    )
  );
END
$$;

-- @@
-- Sự kiện lương theo trạng thái ('pending', 'confirmed', 'kept_other' hoặc 'all'), kỳ lương mới nhất trước (tối đa 20).
CREATE OR REPLACE FUNCTION app_list_salary_events(p_user_id text, p_status text DEFAULT 'pending', p_limit integer DEFAULT 5)
RETURNS TABLE (
  id uuid, period_date date, transaction_id uuid, received_on date, expected_vnd numeric, amount_vnd numeric,
  deviation_percent numeric, ask_update_salary boolean, status text, confirmed_at timestamptz
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT e.id, e.period_date, e.transaction_id, e.received_on, e.expected_vnd, e.amount_vnd,
           e.deviation_percent, e.ask_update_salary, e.status, e.confirmed_at
    FROM salary_events e
    WHERE p_status IS NULL OR p_status = 'all' OR e.status = p_status
    ORDER BY e.period_date DESC, e.id
    LIMIT LEAST(GREATEST(coalesce(p_limit, 5), 1), 20);
END
$$;

-- @@
-- Mọi thứ Tổng quan cần ngoài số dư hũ và dự báo, trong MỘT lệnh gọi (jsonb). p_today là ngày mô phỏng do người gọi tính (app_today).
-- profile: hồ sơ đã khai; credit_line; obligations_due: nghĩa vụ đang hoạt động đến hạn trong 30 ngày tới (tối đa 5);
-- salary_event: sự kiện lương chờ xác nhận mới nhất; confirmed_period: kỳ lương đã xác nhận gần nhất (period_date);
-- recent_transactions: 5 giao dịch gần nhất (không gồm dòng chuyển hũ); needs_review_count: số giao dịch cần xem lại hoặc chưa phân loại.
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
        WHERE t.kind <> 'transfer'
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
REVOKE ALL ON FUNCTION app_ensure_system_jars(text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_list_jars(text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_list_obligations(text, text, date, integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_list_payees(text, integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_credit_line(text) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_list_transactions(text, text, date, date, text, text, boolean, timestamptz, uuid, integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_unclassified(text, integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_daily_spend(text, date, date) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_cashflow_summary(text, date, date) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_list_salary_events(text, text, integer) FROM PUBLIC;

-- @@
REVOKE ALL ON FUNCTION app_get_overview_extras(text, date) FROM PUBLIC;

-- @@
GRANT EXECUTE ON FUNCTION app_ensure_system_jars(text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_list_jars(text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_list_obligations(text, text, date, integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_list_payees(text, integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_credit_line(text) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_list_transactions(text, text, date, date, text, text, boolean, timestamptz, uuid, integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_unclassified(text, integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_daily_spend(text, date, date) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_cashflow_summary(text, date, date) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_list_salary_events(text, text, integer) TO yofina_app;

-- @@
GRANT EXECUTE ON FUNCTION app_get_overview_extras(text, date) TO yofina_app;
