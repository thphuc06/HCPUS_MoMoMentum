-- 0051_scenario_conversation: gắn kịch bản what-if với cuộc chat và lưu danh sách khoản đã gộp (gộp kịch bản trong một cuộc chat).
--
-- Bối cảnh: người dùng hỏi "nếu mua giày 800 nghìn từ hũ Giải trí", lát sau hỏi "nếu mua dép 300 nghìn từ hũ Giải trí". Agent hỏi
-- lại có còn giữ ý định mua giày không; nếu còn thì chạy MỘT mô phỏng gộp cả hai (tool run_scenario nhận with_scenarios). Để agent
-- biết trong cuộc chat này đã chạy kịch bản nào, mỗi lần chạy lưu thêm:
-- * conversation_id: id phiên của cuộc chat (session id của AgentCore Runtime, tối đa 256 ký tự). KHÔNG dùng trace_id: cột
--   trace_id do Lambda forecast tự sinh, khác trace của lượt chat, nên không nối được qua trace.
-- * bundle: mảng JSON các spec (dạng wire, đã chuẩn hóa) mà mô phỏng đã gộp, theo thứ tự áp; phần tử cuối là `spec` chính. Dòng cũ
--   (trước 0051) có NULL ở cả hai cột; đọc lại thì coi bundle là [spec].
--
-- Hàm đọc app_list_conversation_scenarios: các kịch bản của CHÍNH người gọi trong một cuộc chat, mới nhất trước. Trả thêm
-- result_label (nhãn gộp của khối trước-sau đầu tiên) và result_bundle (tóm tắt từng khoản có nhãn riêng, nằm trong cột result).
-- Người khác dùng cùng conversation_id thì không thấy dòng nào (RLS cộng điều kiện user_id).
--
-- Quy ước như 0005 tới 0010 (db/README.md): chạy bằng secret MASTER, một transaction, tách bằng dòng "-- @@", viết lại được,
-- hàm đọc SECURITY INVOKER tự đặt app.user_id và có LIMIT. Không viết dấu hai chấm dính liền chữ cái hoặc gạch dưới.
-- Không sửa 0001 tới 0010 (migrator kiểm checksum). Quyền của yofina_app trên scenarios (SELECT, INSERT, DELETE) và RLS giữ nguyên.

ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS conversation_id text CHECK (conversation_id IS NULL OR length(conversation_id) BETWEEN 1 AND 256);

-- @@
ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS bundle jsonb CHECK (bundle IS NULL OR jsonb_typeof(bundle) = 'array');

-- @@
CREATE INDEX IF NOT EXISTS scenarios_user_conversation_idx ON scenarios (user_id, conversation_id, created_at DESC) WHERE conversation_id IS NOT NULL;

-- @@
-- Các kịch bản đã chạy trong một cuộc chat của chính người gọi, mới nhất trước. p_limit bị kẹp trong 1 tới 10 (mặc định 5).
CREATE OR REPLACE FUNCTION app_list_conversation_scenarios(p_user_id text, p_conversation_id text, p_limit integer DEFAULT 5)
RETURNS TABLE (
  id uuid, kind text, spec jsonb, bundle jsonb, result_label text, result_bundle jsonb, created_at timestamptz
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT s.id, s.kind, s.spec, s.bundle,
           s.result #>> '{timelines,0,compare,label}',
           s.result -> 'bundle',
           s.created_at
    FROM scenarios s
    WHERE s.user_id = p_user_id AND s.conversation_id = p_conversation_id
    ORDER BY s.created_at DESC, s.id DESC
    LIMIT LEAST(GREATEST(coalesce(p_limit, 5), 1), 10);
END
$$;

-- @@
REVOKE ALL ON FUNCTION app_list_conversation_scenarios(text, text, integer) FROM PUBLIC;

-- @@
GRANT EXECUTE ON FUNCTION app_list_conversation_scenarios(text, text, integer) TO yofina_app;
