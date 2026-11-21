"""RLS phần 2: kiểm CTE một lệnh có đáng tin không; kiểm vì sao owner vẫn thấy hết sau FORCE."""
from bench_core import *
from cfg import *
admin, app, _ = apis()
def tryq(label, fn):
    try: print(f"{label}: {fn()}")
    except Exception as e: print(f"{label}: LỖI {str(e)[:200]}")
print(admin.q("SELECT rolname, rolsuper::text, rolbypassrls::text FROM pg_roles WHERE rolname IN ('rds_superuser','spikeadmin','yofina_app')")["records"])
Q = "WITH s AS (SELECT set_config('app.user_id',:u,true) x) SELECT string_agg(DISTINCT user_id, ',') FROM {t}, s"
for t in ("jars", "transactions", "forecasts"):
    for u in ("user-b", "user-c"):
        tryq(f"CTE 1 lệnh [{t}] u={u}", lambda: app.q(Q.format(t=t), {"u": u})["records"])
# kiểm truy vấn có index lookup theo user_id (không dùng seq scan)
tryq("CTE + truy vấn có WHERE user_id (index) u=user-b", lambda: app.q("WITH s AS (SELECT set_config('app.user_id',:u,true) x) SELECT string_agg(DISTINCT t.user_id, ',') FROM transactions t, s WHERE t.jar_id = 1", {"u": "user-b"})["records"])
tryq("CTE: SELECT từ s sau (LATERAL kiểu 2)", lambda: app.q("SELECT string_agg(DISTINCT j.user_id, ',') FROM (SELECT set_config('app.user_id',:u,true)) s CROSS JOIN LATERAL (SELECT user_id FROM jars) j", {"u": "user-c"})["records"])
