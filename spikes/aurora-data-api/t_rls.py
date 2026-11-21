"""RLS qua Data API: set_config trong/ngoài transaction, role app vs owner."""
from bench_core import *
from cfg import *

admin, app, _ = apis()


def cnt(r):
    return r["records"][0][0].get("longValue", r["records"][0][0])


def tryq(label, fn):
    try:
        r = fn()
        print(f"{label}: {r}")
    except Exception as e:
        print(f"{label}: LỖI {type(e).__name__}: {str(e)[:220]}")


def vals(r):
    return [list(x.values())[0] for x in r["records"][0]]


print("== vai trò")
print("app  :", vals(app.q("SELECT current_user::text, (SELECT rolsuper FROM pg_roles WHERE rolname=current_user)::text, (SELECT rolbypassrls FROM pg_roles WHERE rolname=current_user)::text, (SELECT tableowner FROM pg_tables WHERE tablename='jars')")))
print("admin:", vals(admin.q("SELECT current_user::text, (SELECT rolsuper FROM pg_roles WHERE rolname=current_user)::text, (SELECT rolbypassrls FROM pg_roles WHERE rolname=current_user)::text, (SELECT string_agg(rolname,',') FROM pg_roles r JOIN pg_auth_members m ON m.roleid=r.oid WHERE m.member=(SELECT oid FROM pg_roles WHERE rolname=current_user))")))

print("== 1. app role, không set_config")
tryq("count jars", lambda: cnt(app.q("SELECT count(*) FROM jars")))

print("== 2. set_config NGOÀI transaction")


def outside(is_local):
    app.q(f"SELECT set_config('app.user_id','user-a',{'true' if is_local else 'false'})")
    return app.q("SELECT count(*), current_setting('app.user_id', true) FROM jars")["records"][0]


tryq("is_local=true  rồi gọi riêng SELECT", lambda: outside(True))
tryq("is_local=false rồi gọi riêng SELECT", lambda: outside(False))
leaks = 0
for i in range(30):
    app.q("SELECT set_config('app.user_id','user-a',false)")
    leaks += cnt(app.q("SELECT count(*) FROM jars")) > 0
print("rò rỉ session-level qua 30 lần gọi (số lần thấy dòng):", leaks)

print("== 3. TRONG transaction (set_config true)")
tx = app.begin()
app.q("SELECT set_config('app.user_id','user-a',true)", tx=tx)
print("count jars:", cnt(app.q("SELECT count(*) FROM jars", tx=tx)))
print("jars của user-b nhìn thấy:", cnt(app.q("SELECT count(*) FROM jars WHERE user_id='user-b'", tx=tx)))
print("transactions:", cnt(app.q("SELECT count(*) FROM transactions", tx=tx)), "| forecasts:", cnt(app.q("SELECT count(*) FROM forecasts", tx=tx)))
tryq("INSERT hộ user-b (WITH CHECK)", lambda: app.q("INSERT INTO jars (id,user_id,code) VALUES (99,'user-b','X')", tx=tx))
app.rollback(tx)
tx = app.begin()
tryq("transaction mới: current_setting", lambda: app.q("SELECT current_setting('app.user_id', true)", tx=tx)["records"][0])
tryq("count jars (transaction mới, chưa set)", lambda: cnt(app.q("SELECT count(*) FROM jars", tx=tx)))
app.rollback(tx)
tx = app.begin()
app.q("SELECT set_config('app.user_id','user-a',true)", tx=tx)
app.commit(tx)
tryq("sau commit, gọi ngoài tx", lambda: cnt(app.q("SELECT count(*) FROM jars")))

print("== 4. một lệnh duy nhất")
tryq("CTE set_config + SELECT", lambda: cnt(app.q("WITH s AS (SELECT set_config('app.user_id','user-a',true) u) SELECT count(*) FROM jars, s")))
tryq("nhiều câu ';' trong 1 ExecuteStatement", lambda: app.q("SELECT set_config('app.user_id','user-a',true); SELECT count(*) FROM jars")["records"])
tryq("CTE MATERIALIZED, tham số user-b", lambda: app.q("WITH s AS MATERIALIZED (SELECT set_config('app.user_id',:u,true)) SELECT count(*) FROM s, jars", {"u": "user-b"})["records"])

print("== 5. owner (secret master)")
tryq("admin count jars không set_config", lambda: cnt(admin.q("SELECT count(*) FROM jars")))
admin.q("ALTER TABLE jars FORCE ROW LEVEL SECURITY")
tryq("sau FORCE RLS", lambda: cnt(admin.q("SELECT count(*) FROM jars")))
admin.q("ALTER TABLE jars NO FORCE ROW LEVEL SECURITY")

print("== 6. role app tự tắt RLS?")
tryq("app: ALTER TABLE jars DISABLE ROW LEVEL SECURITY", lambda: app.q("ALTER TABLE jars DISABLE ROW LEVEL SECURITY"))
tryq("app: set_config user khác rồi đọc (app tự khai) ", lambda: (lambda tx: (app.q("SELECT set_config('app.user_id','user-b',true)", tx=tx), cnt(app.q("SELECT count(*) FROM jars", tx=tx)))[1])(app.begin()))
