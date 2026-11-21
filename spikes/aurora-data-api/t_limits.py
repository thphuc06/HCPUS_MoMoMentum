"""Giới hạn: 1 MiB, Batch, kiểu dữ liệu."""
import json, time
from bench_core import *
from cfg import *

admin, app, _ = apis()


def tryq(label, fn):
    try:
        r = fn()
        print(f"{label}: {r}")
    except Exception as e:
        print(f"{label}: LỖI {type(e).__name__}: {str(e)[:300]}")


def raw(a, sql, params):
    return a.c.execute_statement(resourceArn=a.cluster, secretArn=a.secret, database=a.db, sql=sql, parameters=params)["records"][0]


admin.q("DELETE FROM transactions WHERE user_id='zz'"); admin.q("DELETE FROM jars WHERE user_id='zz'")
print("== 1 MiB")
for rows, w in [(500, 1000), (900, 1000), (1100, 1000), (3000, 1000)]:
    tryq(f"{rows} dòng x {w} ký tự (~{rows*w/1048576:.2f} MiB)", lambda: len(admin.q(f"SELECT repeat('x',{w}) FROM generate_series(1,{rows})")["records"]))
tryq("1 dòng 1.2 MB", lambda: len(admin.q("SELECT repeat('x',1200000)")["records"][0][0]["stringValue"]))
tryq("formatRecordsAs=JSON 3000x1000", lambda: len(admin.q("SELECT repeat('x',1000) c FROM generate_series(1,3000)", formatRecordsAs="JSON").get("formattedRecords", "")))
tryq("210 dòng forecast", lambda: len(admin.q(SQL_FC, {"u": "user-a"})["records"]))
r = admin.q("SELECT id, code, balance FROM jars WHERE user_id='user-a' LIMIT 2")
print("kích thước JSON phản hồi 2 dòng jars:", len(json.dumps(r["records"])))

print("== BatchExecuteStatement")
tryq("1001 parameter sets", lambda: len(admin.batch("INSERT INTO jars (id,user_id,code) VALUES (:id,'zz','x') ON CONFLICT DO NOTHING", [dict(id=i) for i in range(1001)])["updateResults"]))
t = time.perf_counter()
tryq("1000 parameter sets (1 lệnh)", lambda: len(admin.batch("INSERT INTO transactions (user_id,jar_id,amount,merchant,occurred_at,meta) VALUES ('zz',1,:a,'b',now(),'{}')", [dict(a=i) for i in range(1000)])["updateResults"]))
print("  ms:", round((time.perf_counter() - t) * 1000))
t = time.perf_counter()
tx = admin.begin()
admin.batch("INSERT INTO transactions (user_id,jar_id,amount,merchant,occurred_at,meta) VALUES ('zz',1,:a,'b',now(),'{}')", [dict(a=i) for i in range(200)], tx=tx)
admin.rollback(tx)
print("200 sets trong transaction + rollback ms:", round((time.perf_counter() - t) * 1000), "| còn lại zz:", admin.q("SELECT count(*) FROM transactions WHERE user_id='zz'")["records"][0][0])
admin.q("DELETE FROM transactions WHERE user_id='zz'")
admin.q("DELETE FROM jars WHERE user_id='zz'")

print("== Kiểu dữ liệu (trả về thô)")
r = admin.q("SELECT 12345678901234.5678::numeric(20,4) AS num, 100000::numeric(14,0) AS n0, now() AS tstz, current_date AS d, '{\"a\":1,\"b\":[1,2]}'::jsonb AS j, true AS b, 9223372036854775807::bigint AS big, 1.5::float8 AS f, gen_random_uuid() AS u, ARRAY[1,2,3] AS arr, '\\xdeadbeef'::bytea AS by, NULL::text AS nul, 'abc'::text AS t", includeResultMetadata=True)
for m, f in zip(r["columnMetadata"], r["records"][0]):
    print(f"  {m['name']:5s} typeName={m['typeName']:12s} -> {f}")
r = admin.q("SELECT 12345678901234.5678::numeric(20,4) AS num, 100000::numeric(14,0) n0, 9223372036854775807::bigint big", resultSetOptions={"decimalReturnType": "DOUBLE_OR_LONG", "longReturnType": "STRING"})
print("  decimalReturnType=DOUBLE_OR_LONG, longReturnType=STRING:", r["records"][0])
r = admin.q("SELECT code, balance, updated_at, jsonb_build_object('k',1) m FROM jars WHERE user_id='user-a' LIMIT 2", formatRecordsAs="JSON")
print("  formatRecordsAs=JSON:", r.get("formattedRecords"))

print("== tham số")
tryq("jsonb tham số + CAST", lambda: admin.q("SELECT CAST(:j AS jsonb)->>'a' ", {"j": '{"a":"x"}'})["records"][0])
tryq("numeric stringValue + typeHint DECIMAL", lambda: raw(admin, "SELECT :n::numeric + 1", [{"name": "n", "value": {"stringValue": "12.50"}, "typeHint": "DECIMAL"}]))
tryq("timestamptz typeHint TIMESTAMP", lambda: raw(admin, "SELECT :t::timestamptz", [{"name": "t", "value": {"stringValue": "2026-11-21 10:00:00"}, "typeHint": "TIMESTAMP"}]))
tryq("timestamptz tham số KHÔNG cast/hint (so với now())", lambda: admin.q("SELECT 1 WHERE now() > :t", {"t": "2026-11-21 10:00:00"})["records"])
