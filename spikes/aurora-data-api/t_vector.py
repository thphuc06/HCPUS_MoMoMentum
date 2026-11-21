"""pgvector qua Data API: extension, vector(1024), HNSW, truyền tham số, độ trễ."""
import random, time, json, sys
from bench_core import *
from cfg import *

admin, app, _ = apis()
DIM = 1024
random.seed(7)
vec = lambda: "[" + ",".join(f"{random.uniform(-1, 1):.6f}" for _ in range(DIM)) + "]"

print("pgvector extversion:", admin.q("SELECT extversion FROM pg_extension WHERE extname='vector'")["records"][0][0]["stringValue"])
print("available:", [r[0]["stringValue"] + " " + r[1]["stringValue"] for r in admin.q("SELECT name, default_version FROM pg_available_extensions WHERE name='vector'")["records"]])
admin.q("DROP TABLE IF EXISTS docs")
admin.q(f"CREATE TABLE docs (id serial PRIMARY KEY, user_id text, content text, embedding vector({DIM}))")
t = time.perf_counter()
admin.q("CREATE INDEX docs_hnsw ON docs USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)")
print("create hnsw ms", round((time.perf_counter() - t) * 1000))

# thử các cách truyền tham số
tests = {
 "plain :emb (stringValue) vào cột vector": "INSERT INTO docs (user_id, content, embedding) VALUES ('user-a','x', :emb)",
 "CAST(:emb AS vector)": "INSERT INTO docs (user_id, content, embedding) VALUES ('user-a','x', CAST(:emb AS vector))",
 ":emb::vector": "INSERT INTO docs (user_id, content, embedding) VALUES ('user-a','x', :emb::vector)",
}
for k, s in tests.items():
    try:
        admin.q(s, {"emb": vec()}); print("OK  ", k)
    except Exception as e:
        print("FAIL", k, "->", str(e)[:200])
try:
    r = admin.q("INSERT INTO docs (user_id, content, embedding) VALUES ('user-a','x', CAST(:emb AS vector))", {"emb": "[1,2,3]"})
except Exception as e:
    print("sai chiều:", str(e)[:200])

# chèn hàng loạt 300 vector bằng BatchExecuteStatement
sets = [dict(u=random.choice(USERS), c=f"doc {i}", e=vec()) for i in range(300)]
t = time.perf_counter()
for i in range(0, 300, 50):
    admin.batch("INSERT INTO docs (user_id, content, embedding) VALUES (:u,:c,CAST(:e AS vector))", sets[i:i + 50])
print("batch insert 300x1024 ms", round((time.perf_counter() - t) * 1000), "count", admin.q("SELECT count(*) FROM docs")["records"][0][0])
admin.q("ANALYZE docs")

# đọc cột vector ra
r = admin.q("SELECT embedding FROM docs LIMIT 1", includeResultMetadata=True)
f = r["records"][0][0]
print("kiểu trả về cột vector:", list(f.keys()), "|", str(f)[:80], "...", "| columnMetadata type:", r["columnMetadata"][0]["typeName"])
r = admin.q("SELECT embedding::text FROM docs LIMIT 1"); print("embedding::text len", len(r["records"][0][0]["stringValue"]))

# kNN
q = vec()
sql = "SELECT id, content, embedding <=> CAST(:q AS vector) AS dist FROM docs ORDER BY embedding <=> CAST(:q AS vector) LIMIT 5"
r = admin.q(sql, {"q": q})
print("knn rows:", [(x[0]["longValue"], round(x[2]["doubleValue"], 4)) for x in r["records"]])
r = admin.q("SELECT id FROM docs WHERE user_id=:u ORDER BY embedding <=> CAST(:q AS vector) LIMIT 5", {"u": "user-a", "q": q})
print("knn+filter rows:", len(r["records"]))
# plan: có dùng HNSW không (trong transaction để SET LOCAL)
tx = admin.begin()
admin.q("SET LOCAL enable_seqscan = off", tx=tx)
plan = admin.q("EXPLAIN " + sql, {"q": q}, tx=tx)
print("EXPLAIN (enable_seqscan=off):", [x[0]["stringValue"] for x in plan["records"]][:4])
admin.commit(tx)
plan = admin.q("EXPLAIN " + sql, {"q": q})
print("EXPLAIN (mặc định, 300 dòng):", [x[0]["stringValue"] for x in plan["records"]][:3])
# độ trễ
xs = []; ys = []
for i in range(60):
    qq = vec()
    t = time.perf_counter(); admin.q(sql, {"q": qq}); xs.append((time.perf_counter() - t) * 1000)
print("knn top5 local:", stats(xs[1:]), "first", round(xs[0], 1))
# so sánh: giữ payload nhỏ - không có
