-- Migration THỬ có lỗi ở câu lệnh thứ hai: câu đầu phải bị rollback.
CREATE TABLE migrator_selftest_bad (id int);
SELECT * FROM bang_khong_ton_tai;
