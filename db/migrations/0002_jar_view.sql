-- 0002_jar_view: một hàm đọc trả số dư hũ KÈM độ lệch đồng hồ mô phỏng của người dùng.
--
-- Vì sao: GET /jars và tool get_jar_balances cần cả số dư lẫn ngày mô phỏng (ADR-0003, ngày =
-- ngày hiện tại + clock_offset_days). Hai hàm riêng thì tốn hai lệnh gọi Data API (~50 ms mỗi lệnh);
-- hàm này gộp thành một lệnh. LEFT JOIN để người dùng có hàng users nhưng chưa có hũ vẫn cho ra một
-- dòng (cột hũ NULL) với độ lệch đồng hồ đúng; người dùng chưa có hàng users thì không ra dòng nào.
--
-- Quy ước như 0001 (db/README.md): mỗi câu lệnh kết thúc bằng dấu chấm phẩy, SECURITY INVOKER,
-- tự set_config bên trong, có LIMIT, không dấu hai chấm dính liền chữ cái hoặc dấu gạch dưới.

CREATE OR REPLACE FUNCTION app_get_jar_view(p_user_id text)
RETURNS TABLE (
  clock_offset_days integer,
  code text, name text, color_key text, icon_key text,
  balance_vnd numeric, split_percent numeric, sort_order smallint
)
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
  PERFORM set_config('app.user_id', p_user_id, true);
  RETURN QUERY
    SELECT u.clock_offset_days, j.code, j.name, j.color_key, j.icon_key,
           j.balance_vnd, j.split_percent, j.sort_order
    FROM users u
    LEFT JOIN jars j ON j.user_id = u.id
    ORDER BY j.sort_order, j.code
    LIMIT 20;
END
$$;

REVOKE ALL ON FUNCTION app_get_jar_view(text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app_get_jar_view(text) TO yofina_app;
