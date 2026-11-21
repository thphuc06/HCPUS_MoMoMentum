"""Lõi đo độ trễ RDS Data API. Dùng chung cho máy local và Lambda."""
import time, json, os, random
import boto3

REGION = "ap-southeast-1"
USERS = ["user-a", "user-b", "user-c"]


def pct(xs, p):
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def stats(xs):
    return {"n": len(xs), "min": round(min(xs), 1), "p50": round(pct(xs, 50), 1),
            "p95": round(pct(xs, 95), 1), "p99": round(pct(xs, 99), 1),
            "max": round(max(xs), 1), "mean": round(sum(xs) / len(xs), 1)}


def param(name, v, hint=None):
    if v is None:
        val = {"isNull": True}
    elif isinstance(v, bool):
        val = {"booleanValue": v}
    elif isinstance(v, int):
        val = {"longValue": v}
    elif isinstance(v, float):
        val = {"doubleValue": v}
    else:
        val = {"stringValue": str(v)}
    p = {"name": name, "value": val}
    if hint:
        p["typeHint"] = hint
    return p


class Api:
    def __init__(self, cluster_arn, secret_arn, database="spike", region=REGION):
        self.c = boto3.client("rds-data", region_name=region)
        self.cluster, self.secret, self.db = cluster_arn, secret_arn, database

    def q(self, sql, params=None, tx=None, **kw):
        a = dict(resourceArn=self.cluster, secretArn=self.secret, database=self.db, sql=sql)
        if params:
            a["parameters"] = [param(k, v) for k, v in params.items()]
        if tx:
            a["transactionId"] = tx
        a.update(kw)
        return self.c.execute_statement(**a)

    def batch(self, sql, param_sets, tx=None):
        a = dict(resourceArn=self.cluster, secretArn=self.secret, database=self.db, sql=sql,
                 parameterSets=[[param(k, v) for k, v in ps.items()] for ps in param_sets])
        if tx:
            a["transactionId"] = tx
        return self.c.batch_execute_statement(**a)

    def begin(self):
        return self.c.begin_transaction(resourceArn=self.cluster, secretArn=self.secret,
                                        database=self.db)["transactionId"]

    def commit(self, tx):
        return self.c.commit_transaction(resourceArn=self.cluster, secretArn=self.secret, transactionId=tx)

    def rollback(self, tx):
        return self.c.rollback_transaction(resourceArn=self.cluster, secretArn=self.secret, transactionId=tx)


SQL_JARS = "SELECT code, balance FROM jars WHERE user_id = :u ORDER BY code"
SQL_AGG = "SELECT jar_id, SUM(amount) AS bal FROM transactions WHERE user_id = :u GROUP BY jar_id ORDER BY jar_id"
SQL_FC = ("SELECT jar_id, day, p10, p50, p90 FROM forecasts WHERE user_id = :u "
          "AND day >= CURRENT_DATE AND day < CURRENT_DATE + 30 ORDER BY jar_id, day")
SQL_TX = ("SELECT id, jar_id, amount, merchant, occurred_at FROM transactions WHERE user_id = :u "
          "AND jar_id = :j AND occurred_at >= now() - interval '60 days' ORDER BY occurred_at DESC LIMIT 50")
SQL_INS = ("INSERT INTO transactions (user_id, jar_id, amount, merchant, occurred_at, meta) "
           "VALUES (:u, :j, :amt, 'bench', now(), '{}'::jsonb)")
SQL_UPD = "UPDATE jars SET balance = balance + :amt WHERE user_id = :u AND id = :j"


def rls_wrap(a, fn):
    """BeginTransaction + set_config(...,true) + truy vấn + Commit (4 lệnh gọi)."""
    def run(u, *args):
        tx = a.begin()
        a.q("SELECT set_config('app.user_id', :u, true)", {"u": u}, tx=tx)
        r = fn(a, u, tx, *args)
        a.commit(tx)
        return r
    return run


def ops(a):
    """Mỗi op nhận (uid) và tự gọi Data API; trả về số lệnh gọi."""
    def jars(u): a.q(SQL_JARS, {"u": u})
    def agg(u): a.q(SQL_AGG, {"u": u})
    def fc(u): a.q(SQL_FC, {"u": u})
    def txf(u): a.q(SQL_TX, {"u": u, "j": 1})
    def one(u): a.q("SELECT 1")
    def flow3(u):
        a.q(SQL_JARS, {"u": u}); a.q(SQL_FC, {"u": u}); a.q(SQL_TX, {"u": u, "j": 1})
    def write(u):
        tx = a.begin()
        a.q(SQL_INS, {"u": u, "j": 1, "amt": 1000}, tx=tx)
        a.q(SQL_UPD, {"u": u, "j": 1, "amt": 1000}, tx=tx)
        a.commit(tx)
    return {"select1": one, "balances_jars": jars, "balances_agg": agg, "forecast_30x7": fc,
            "tx_filtered": txf, "flow3_plain": flow3, "write_tx_2stmt": write}


def rls_ops(a):
    def mk(sqls):
        def f(u):
            tx = a.begin()
            a.q("SELECT set_config('app.user_id', :u, true)", {"u": u}, tx=tx)
            for s, p in sqls:
                a.q(s, dict(p, u=u), tx=tx)
            a.commit(tx)
        return f
    def fn_jars(u): a.q("SELECT code, balance FROM rls_jars(:u)", {"u": u})
    def fn_flow3(u):
        a.q("SELECT code, balance FROM rls_jars(:u)", {"u": u})
        a.q("SELECT jar_id, day, p10, p50, p90 FROM rls_forecast(:u)", {"u": u})
        a.q("SELECT id, jar_id, amount, merchant, occurred_at FROM rls_txs(:u, 1)", {"u": u})
    return {"rls_tx_balances_jars": mk([(SQL_JARS, {})]),
            "rls_tx_flow3": mk([(SQL_JARS, {}), (SQL_FC, {}), (SQL_TX, {"j": 1})]),
            "rls_fn_balances_jars": fn_jars, "rls_fn_flow3": fn_flow3}


def run_bench(admin_api, app_api, n=50, only=None):
    out = {}
    plan = list(ops(admin_api).items()) + list(rls_ops(app_api).items())
    for name, fn in plan:
        if only and name not in only:
            continue
        t = time.perf_counter(); fn(USERS[0]); first = (time.perf_counter() - t) * 1000
        xs = []
        for i in range(n):
            u = USERS[i % 3]
            t = time.perf_counter(); fn(u); xs.append((time.perf_counter() - t) * 1000)
        out[name] = dict(stats(xs), first=round(first, 1))
    return out


def vector_bench(a, n=50, dim=1024):
    rnd = random.Random(3)
    sql = "SELECT id, embedding <=> CAST(:q AS vector) AS dist FROM docs ORDER BY embedding <=> CAST(:q AS vector) LIMIT 5"
    xs = []
    for i in range(n + 1):
        q = "[" + ",".join(f"{rnd.uniform(-1, 1):.6f}" for _ in range(dim)) + "]"
        t = time.perf_counter(); a.q(sql, {"q": q}); xs.append((time.perf_counter() - t) * 1000)
    return dict(stats(xs[1:]), first=round(xs[0], 1))


def probe(a, n=50):
    """Tách nguồn ~50 ms: kích thước phản hồi/yêu cầu và từng lệnh gọi riêng lẻ."""
    cases = {
        "select1": lambda: a.q("SELECT 1"),
        "select1_resp_200B": lambda: a.q("SELECT 1, repeat('x',200)"),
        "select1_resp_3KB": lambda: a.q("SELECT 1, repeat('x',3000)"),
        "select1_req_3KB_comment": lambda: a.q("/*" + "y" * 3000 + "*/ SELECT 1"),
        "jars_param_u": lambda: a.q(SQL_JARS, {"u": "user-a"}),
        "jars_param_u+3KB_resp": lambda: a.q("SELECT code, balance, repeat('x',3000) FROM jars WHERE user_id=:u", {"u": "user-a"}),
        "tx_filtered_limit1": lambda: a.q(SQL_TX.replace("LIMIT 50", "LIMIT 1"), {"u": "user-a", "j": 1}),
        "tx_filtered_limit50": lambda: a.q(SQL_TX, {"u": "user-a", "j": 1}),
    }
    out = {}
    for k, f in cases.items():
        f(); xs = []
        for _ in range(n):
            t = time.perf_counter(); f(); xs.append((time.perf_counter() - t) * 1000)
        out[k] = stats(xs)
    # từng lệnh trong transaction
    bx, ix, cx = [], [], []
    for _ in range(n):
        t = time.perf_counter(); tx = a.begin(); bx.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter(); a.q(SQL_INS, {"u": "user-a", "j": 1, "amt": 1}, tx=tx); ix.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter(); a.commit(tx); cx.append((time.perf_counter() - t) * 1000)
    out["BeginTransaction"], out["insert_in_tx"], out["CommitTransaction"] = stats(bx), stats(ix), stats(cx)
    return out
