"""Tạo schema, dữ liệu giả, role ứng dụng (non-owner), secret ứng dụng. Chạy bằng secret master."""
import json, secrets, string, random, datetime as dt
import boto3
from bench_core import *
from cfg import *

admin, _, (cl, ad, ap) = apis()
sm = boto3.client("secretsmanager", region_name=REGION)

DDL = [
 "CREATE EXTENSION IF NOT EXISTS vector",
 "CREATE TABLE IF NOT EXISTS jars (id int NOT NULL, user_id text NOT NULL, code text NOT NULL, balance numeric(14,0) NOT NULL DEFAULT 0, updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (user_id, id))",
 "CREATE TABLE IF NOT EXISTS transactions (id bigserial PRIMARY KEY, user_id text NOT NULL, jar_id int NOT NULL, amount numeric(14,0) NOT NULL, merchant text, occurred_at timestamptz NOT NULL, meta jsonb)",
 "CREATE INDEX IF NOT EXISTS tx_user_jar_time ON transactions (user_id, jar_id, occurred_at DESC)",
 "CREATE TABLE IF NOT EXISTS forecasts (user_id text NOT NULL, jar_id int NOT NULL, day date NOT NULL, p10 numeric(14,0), p50 numeric(14,0), p90 numeric(14,0), PRIMARY KEY (user_id, jar_id, day))",
]
for s in DDL:
    admin.q(s)
print("extension:", admin.q("SELECT extversion FROM pg_extension WHERE extname='vector'")["records"])
print("version:", admin.q("SELECT version()")["records"][0][0]["stringValue"][:80])

CODES = ["NEC", "FFA", "LTS", "EDU", "PLAY", "GIVE", "FIN"]
if admin.q("SELECT count(*) FROM jars")["records"][0][0]["longValue"] == 0:
    admin.batch("INSERT INTO jars (id,user_id,code,balance) VALUES (:id,:u,:c,:b)",
        [dict(id=i + 1, u=u, c=c, b=random.randint(1, 50) * 100000) for u in USERS for i, c in enumerate(CODES)])
    random.seed(1)
    rows = []
    now = dt.datetime.utcnow()
    for u in USERS:
        for k in range(2000):
            ts = now - dt.timedelta(minutes=random.randint(0, 90 * 24 * 60))
            rows.append(dict(u=u, j=random.randint(1, 7), amt=random.randint(-500, 500) * 1000,
                             m=random.choice(["Grab", "Shopee", "Highlands", "Circle K", "Bach Hoa Xanh", "MoMo"]),
                             ts=ts.strftime("%Y-%m-%d %H:%M:%S")))
    for i in range(0, len(rows), 500):
        admin.batch("INSERT INTO transactions (user_id,jar_id,amount,merchant,occurred_at,meta) "
                    "VALUES (:u,:j,:amt,:m,CAST(:ts AS timestamptz),'{\"src\":\"seed\"}'::jsonb)", rows[i:i + 500])
    fc = [dict(u=u, j=j, d=d, p10=random.randint(0, 20) * 100000, p50=random.randint(20, 40) * 100000,
               p90=random.randint(40, 60) * 100000)
          for u in USERS for j in range(1, 8) for d in range(0, 30)]
    admin.batch("INSERT INTO forecasts (user_id,jar_id,day,p10,p50,p90) VALUES (:u,:j,CURRENT_DATE+CAST(:d AS int),:p10,:p50,:p90)", fc)
for t in ("jars", "transactions", "forecasts"):
    print(t, admin.q(f"SELECT count(*) FROM {t}")["records"][0][0])

# RLS + role ứng dụng
pw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
exists = admin.q("SELECT 1 FROM pg_roles WHERE rolname='yofina_app'")["records"]
if not exists:
    admin.q(f"CREATE ROLE yofina_app LOGIN PASSWORD '{pw}' NOSUPERUSER NOBYPASSRLS")
    sm.create_secret(Name=APP_SECRET_NAME, Tags=[{"Key": "project", "Value": "yofina-spike"}],
                     SecretString=json.dumps({"username": "yofina_app", "password": pw}))
    print("app secret created")
admin.q("GRANT USAGE ON SCHEMA public TO yofina_app")
admin.q("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO yofina_app")
admin.q("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO yofina_app")
for t in ("jars", "transactions", "forecasts"):
    admin.q(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
    admin.q(f"DROP POLICY IF EXISTS user_iso ON {t}")
    admin.q(f"CREATE POLICY user_iso ON {t} USING (user_id = current_setting('app.user_id', true)) "
            f"WITH CHECK (user_id = current_setting('app.user_id', true))")
print("done")
