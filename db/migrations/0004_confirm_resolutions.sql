-- 0004_confirm_resolutions: trạng thái "đã thực hiện" của một khối `confirm`, do server giữ.
--
-- Vì sao: khối `confirm` được lưu như lúc agent phát (turn_blocks), còn việc người dùng đã bấm xác nhận thì
-- trước đây chỉ nằm ở frontend. Tải lại trang thì nút "Xác nhận" hiện lại và bấm lần nữa sẽ chuyển tiền lần hai.
-- Bảng này ghi: một đề nghị (confirm_block_id) của một người dùng chỉ được thực hiện MỘT lần (UNIQUE), kèm
-- khối `receipt` đã trả để phát lại. Dòng được thêm trong CÙNG transaction với thao tác sổ cái (repo.apply_move):
-- trùng khóa thì cả transaction rollback, không ghi gì (mã ALREADY_APPLIED). Đọc bởi GET /conversations/{id}.
--
-- Khóa theo (user_id, confirm_block_id), không theo conversation_id: người dùng không thể "né" bằng cách đổi
-- conversation_id; và id khối của người khác chỉ tạo ra dòng của chính người gọi (RLS), không đụng dòng của ai.
-- Không chứa token hay bí mật nào; `receipt` là đúng khối POST /actions đã trả.
--
-- Quy ước như 0001 (db/README.md): mỗi câu lệnh kết thúc bằng dấu chấm phẩy, RLS FORCE theo user_id,
-- hàm đọc SECURITY INVOKER tự đặt app.user_id, có LIMIT, không dấu hai chấm dính liền chữ cái hoặc gạch dưới.

CREATE TABLE IF NOT EXISTS confirm_resolutions (
  id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id          text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  confirm_block_id text NOT NULL CHECK (length(confirm_block_id) BETWEEN 1 AND 128),
  conversation_id  text NOT NULL CHECK (length(conversation_id) BETWEEN 1 AND 256),
  transfer_id      uuid NOT NULL,
  receipt          jsonb NOT NULL CHECK (jsonb_typeof(receipt) = 'object'),
  resolved_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, confirm_block_id)
);

CREATE INDEX IF NOT EXISTS confirm_resolutions_conv_idx ON confirm_resolutions (user_id, conversation_id, id);

ALTER TABLE confirm_resolutions ENABLE ROW LEVEL SECURITY;

ALTER TABLE confirm_resolutions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_isolation ON confirm_resolutions;

CREATE POLICY user_isolation ON confirm_resolutions
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));

-- Chỉ thêm và xóa (xóa khi đặt lại demo); không sửa: một đề nghị đã thực hiện thì không đổi nữa.
GRANT SELECT, INSERT, DELETE ON confirm_resolutions TO yofina_app;

-- Các đề nghị đã thực hiện của một cuộc hội thoại, cũ tới mới (tối đa 300).
CREATE OR REPLACE FUNCTION app_get_confirm_resolutions(
  p_user_id         text,
  p_conversation_id text,
  p_limit           integer DEFAULT 100
)
RETURNS TABLE (confirm_block_id text, transfer_id uuid, receipt jsonb, resolved_at timestamptz)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT s.confirm_block_id, s.transfer_id, s.receipt, s.resolved_at
    FROM (
      SELECT r.id, r.confirm_block_id, r.transfer_id, r.receipt, r.resolved_at
      FROM confirm_resolutions r
      WHERE r.conversation_id = p_conversation_id
      ORDER BY r.id DESC
      LIMIT LEAST(GREATEST(coalesce(p_limit, 100), 1), 300)
    ) s
    ORDER BY s.id;
END
$$;

-- Một đề nghị theo id (kiểm trước khi cấp token xác nhận): 0 hoặc 1 dòng.
CREATE OR REPLACE FUNCTION app_get_confirm_resolution(
  p_user_id          text,
  p_confirm_block_id text
)
RETURNS TABLE (confirm_block_id text, transfer_id uuid, receipt jsonb, resolved_at timestamptz)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT r.confirm_block_id, r.transfer_id, r.receipt, r.resolved_at
    FROM confirm_resolutions r
    WHERE r.confirm_block_id = p_confirm_block_id
    LIMIT 1;
END
$$;

REVOKE ALL ON FUNCTION app_get_confirm_resolutions(text, text, integer) FROM PUBLIC;

REVOKE ALL ON FUNCTION app_get_confirm_resolution(text, text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app_get_confirm_resolutions(text, text, integer) TO yofina_app;

GRANT EXECUTE ON FUNCTION app_get_confirm_resolution(text, text) TO yofina_app;
