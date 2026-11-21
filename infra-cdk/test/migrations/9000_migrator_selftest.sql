-- Migration THỬ để kiểm migrator (không thuộc schema sản phẩm). Chứa dấu chấm phẩy trong chuỗi,
-- chú thích; và dollar-quote để thử bộ tách câu lệnh.
CREATE TABLE migrator_selftest (id int PRIMARY KEY, note text NOT NULL);
INSERT INTO migrator_selftest VALUES (1, 'a;b'), (2, 'c::d'); -- chú thích; có dấu chấm phẩy
CREATE FUNCTION migrator_selftest_fn(x int) RETURNS int LANGUAGE plpgsql AS $$
DECLARE y int := 0;
BEGIN
  y := x + 1; -- dấu ; trong thân hàm
  RETURN y;
END $$;
GRANT SELECT ON migrator_selftest TO yofina_app;
