-- 0003_conversation_turns: văn bản của từng lượt hội thoại, để tải lại trang vẫn thấy câu hỏi và câu trả lời.
--
-- Vì sao: `turn_blocks` (0001) chỉ giữ khối UI. Frontend vẽ lại cả cuộc hội thoại cần thêm câu người dùng
-- gõ và câu trả lời bằng chữ của agent. Một dòng mỗi lượt, khóa theo (user_id, conversation_id, trace_id);
-- conversation_id là session id của AgentCore Runtime. Ghi bởi tool save_turn (qua Gateway, user_id do
-- interceptor ghi đè), đọc bởi REST GET /conversations. Không lưu token hay bí mật nào.
--
-- Quy ước như 0001 (db/README.md): mỗi câu lệnh kết thúc bằng dấu chấm phẩy, RLS FORCE theo user_id,
-- hàm đọc SECURITY INVOKER tự đặt app.user_id, có LIMIT, không dấu hai chấm dính liền chữ cái hoặc gạch dưới.

CREATE TABLE IF NOT EXISTS conversation_turns (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id         text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  conversation_id text NOT NULL CHECK (length(conversation_id) BETWEEN 1 AND 256),
  trace_id        text NOT NULL CHECK (length(trace_id) BETWEEN 1 AND 64),
  user_text       text NOT NULL DEFAULT '' CHECK (length(user_text) <= 4000),
  assistant_text  text NOT NULL DEFAULT '' CHECK (length(assistant_text) <= 8000),
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, conversation_id, trace_id)
);

CREATE INDEX IF NOT EXISTS conversation_turns_conv_idx ON conversation_turns (user_id, conversation_id, id);

CREATE INDEX IF NOT EXISTS conversation_turns_recent_idx ON conversation_turns (user_id, created_at DESC);

ALTER TABLE conversation_turns ENABLE ROW LEVEL SECURITY;

ALTER TABLE conversation_turns FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_isolation ON conversation_turns;

CREATE POLICY user_isolation ON conversation_turns
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

GRANT SELECT, INSERT, UPDATE, DELETE ON conversation_turns TO yofina_app;

-- Các lượt gần nhất của một cuộc hội thoại, cũ tới mới (tối đa 100).
CREATE OR REPLACE FUNCTION app_get_conversation_turns(
  p_user_id         text,
  p_conversation_id text,
  p_limit           integer DEFAULT 50
)
RETURNS TABLE (id bigint, trace_id text, user_text text, assistant_text text, created_at timestamptz)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT s.id, s.trace_id, s.user_text, s.assistant_text, s.created_at
    FROM (
      SELECT t.id, t.trace_id, t.user_text, t.assistant_text, t.created_at
      FROM conversation_turns t
      WHERE t.conversation_id = p_conversation_id
      ORDER BY t.id DESC
      LIMIT LEAST(GREATEST(coalesce(p_limit, 50), 1), 100)
    ) s
    ORDER BY s.id;
END
$$;

-- Các cuộc hội thoại gần đây: số lượt, lần hoạt động cuối, câu hỏi đầu tiên (tối đa 50).
CREATE OR REPLACE FUNCTION app_list_conversations(
  p_user_id text,
  p_limit   integer DEFAULT 20
)
RETURNS TABLE (conversation_id text, turns bigint, last_activity_at timestamptz, preview text)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT t.conversation_id,
           count(*) AS turns,
           max(t.created_at) AS last_activity_at,
           (array_agg(t.user_text ORDER BY t.id))[1] AS preview
    FROM conversation_turns t
    GROUP BY t.conversation_id
    ORDER BY max(t.created_at) DESC
    LIMIT LEAST(GREATEST(coalesce(p_limit, 20), 1), 50);
END
$$;

REVOKE ALL ON FUNCTION app_get_conversation_turns(text, text, integer) FROM PUBLIC;

REVOKE ALL ON FUNCTION app_list_conversations(text, integer) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app_get_conversation_turns(text, text, integer) TO yofina_app;

GRANT EXECUTE ON FUNCTION app_list_conversations(text, integer) TO yofina_app;
