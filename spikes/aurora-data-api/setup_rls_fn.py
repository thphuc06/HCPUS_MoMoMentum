"""Hàm plpgsql SECURITY INVOKER: set_config + truy vấn trong 1 lệnh Data API; RLS vẫn áp theo role gọi."""
from cfg import *
from bench_core import *
admin, app, _ = apis()
admin.q("""CREATE OR REPLACE FUNCTION rls_jars(p_user text) RETURNS TABLE(code text, balance numeric)
LANGUAGE plpgsql AS $$ BEGIN PERFORM set_config('app.user_id', p_user, true);
RETURN QUERY SELECT j.code, j.balance FROM jars j ORDER BY j.code; END $$""")
admin.q("""CREATE OR REPLACE FUNCTION rls_forecast(p_user text) RETURNS TABLE(jar_id int, day date, p10 numeric, p50 numeric, p90 numeric)
LANGUAGE plpgsql AS $$ BEGIN PERFORM set_config('app.user_id', p_user, true);
RETURN QUERY SELECT f.jar_id, f.day, f.p10, f.p50, f.p90 FROM forecasts f WHERE f.day >= CURRENT_DATE AND f.day < CURRENT_DATE + 30 ORDER BY f.jar_id, f.day; END $$""")
admin.q("""CREATE OR REPLACE FUNCTION rls_txs(p_user text, p_jar int) RETURNS TABLE(id bigint, jar_id int, amount numeric, merchant text, occurred_at timestamptz)
LANGUAGE plpgsql AS $$ BEGIN PERFORM set_config('app.user_id', p_user, true);
RETURN QUERY SELECT t.id, t.jar_id, t.amount, t.merchant, t.occurred_at FROM transactions t WHERE t.jar_id = p_jar AND t.occurred_at >= now() - interval '60 days' ORDER BY t.occurred_at DESC LIMIT 50; END $$""")
admin.q("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO yofina_app")
for u in ("user-a", "user-b"):
    r1 = app.q("SELECT count(*) FROM rls_jars(:u)", {"u": u})["records"][0][0]
    r2 = app.q("SELECT count(*), min(jar_id) FROM rls_forecast(:u)", {"u": u})["records"][0]
    r3 = app.q("SELECT count(*) FROM rls_txs(:u, 1)", {"u": u})["records"][0][0]
    print(u, r1, r2, r3)
    print(" kiểm user_id thực:", app.q("SELECT string_agg(DISTINCT user_id,',') FROM transactions, (SELECT 1 FROM rls_jars(:u) LIMIT 1) s", {"u": u})["records"])
print("không gọi hàm:", app.q("SELECT count(*) FROM jars")["records"])
