import unittest

from sqlsplit import checksum, named_params, split_migration, split_statements


class SplitTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(split_statements("SELECT 1; SELECT 2;"), ["SELECT 1", "SELECT 2"])

    def test_no_trailing_semicolon(self):
        self.assertEqual(split_statements("SELECT 1"), ["SELECT 1"])

    def test_semicolon_in_string_and_comment(self):
        sql = "-- a; b\nSELECT 'x;y', \"a;b\"; /* c; d */ SELECT 2"
        r = split_statements(sql)
        self.assertEqual(len(r), 2)
        self.assertIn("'x;y'", r[0])

    def test_dollar_quote_function(self):
        sql = "CREATE FUNCTION f() RETURNS int LANGUAGE plpgsql AS $$ BEGIN PERFORM 1; RETURN 1; END $$;\nSELECT f();"
        r = split_statements(sql)
        self.assertEqual(len(r), 2)
        self.assertTrue(r[0].endswith("$$"))

    def test_tagged_dollar_quote(self):
        sql = "DO $body$ BEGIN RAISE NOTICE '$$;'; END $body$; SELECT 1;"
        self.assertEqual(len(split_statements(sql)), 2)

    def test_escaped_quote(self):
        self.assertEqual(split_statements("SELECT 'it''s; ok'; SELECT 2"), ["SELECT 'it''s; ok'", "SELECT 2"])
        self.assertEqual(len(split_statements(r"SELECT E'a\';b'; SELECT 2")), 2)

    def test_comment_only_dropped(self):
        self.assertEqual(split_statements("-- nothing\n;/* x */;SELECT 1;"), ["SELECT 1"])

    def test_positional_param_not_dollar_quote(self):
        self.assertEqual(len(split_statements("SELECT $1; SELECT $2")), 2)

    def test_nested_block_comment(self):
        self.assertEqual(split_statements("/* a /* b; */ c; */ SELECT 1;"), ["/* a /* b; */ c; */ SELECT 1"])

    def test_cast_and_assignment(self):
        sql = "SELECT 'a'::text; DO $$ DECLARE x int := 1; BEGIN NULL; END $$;"
        self.assertEqual(len(split_statements(sql)), 2)


class MigrationContractTest(unittest.TestCase):
    def test_at_at_separator_keeps_semicolons_inside(self):
        sql = (
            "-- đầu\nCREATE TABLE a (x int);\n-- @@\n-- chú thích\n"
            "DO $$ BEGIN PERFORM 1; END $$\n-- @@\n-- chỉ chú thích\n-- @@\nSELECT 1\n"
        )
        self.assertEqual(
            split_migration(sql),
            ["CREATE TABLE a (x int)", "DO $$ BEGIN PERFORM 1; END $$", "SELECT 1"],
        )

    def test_without_separator_falls_back_to_semicolons(self):
        self.assertEqual(split_migration("SELECT 1; SELECT 2;"), ["SELECT 1", "SELECT 2"])

    def test_named_params(self):
        self.assertEqual(named_params("SELECT set_config('x', :app_password, true)"), ["app_password"])
        self.assertEqual(named_params("SELECT 'a'::text, '12:30', -- :ignored\n $$ :inbody $$"), [])
        self.assertEqual(named_params("SELECT :a, :b, :a"), ["a", "b"])

    def test_checksum_normalizes_crlf(self):
        self.assertEqual(checksum("a\r\nb"), checksum("a\nb"))

    def test_matches_real_migration_file(self):
        # 0001_core.sql dùng quy ước -- @@; không câu lệnh nào được rỗng hoặc chứa dòng phân tách
        from pathlib import Path

        f = Path(__file__).resolve().parents[3] / "db" / "migrations" / "0001_core.sql"
        if not f.is_file():
            self.skipTest("chưa có 0001_core.sql")
        stmts = split_migration(f.read_text(encoding="utf-8"))
        self.assertGreater(len(stmts), 10)
        self.assertTrue(all(s.strip() and "-- @@" not in s for s in stmts))


if __name__ == "__main__":
    unittest.main()
