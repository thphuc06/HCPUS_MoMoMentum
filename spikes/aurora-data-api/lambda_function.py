import os, json, time, socket
import bench_core as b

_CACHE = {}


def _apis():
    if not _CACHE:
        cluster = os.environ["CLUSTER_ARN"]
        _CACHE["admin"] = b.Api(cluster, os.environ["ADMIN_SECRET_ARN"])
        _CACHE["app"] = b.Api(cluster, os.environ["APP_SECRET_ARN"])
        _CACHE["fresh"] = True
    else:
        _CACHE["fresh"] = False
    return _CACHE["admin"], _CACHE["app"], _CACHE["fresh"]


def _meas(out, label, f, n=40):
    f()
    xs = []
    for _ in range(n):
        t = time.perf_counter()
        f()
        xs.append((time.perf_counter() - t) * 1000)
    out[label] = b.stats(xs)


def handler(event, context):
    admin, app, fresh = _apis()
    n = int(event.get("n", 50))
    mode = event.get("mode", "bench")
    if mode == "vector":
        return {"fresh_env": fresh, "vector_top5_1024d": b.vector_bench(admin, n=n)}
    if mode == "wake":
        log = []
        t_all = time.perf_counter()
        while time.perf_counter() - t_all < 120:
            t = time.perf_counter()
            try:
                admin.q("SELECT 1")
                log.append(["ok", round((time.perf_counter() - t) * 1000)])
                break
            except Exception as e:
                log.append([type(e).__name__ + ": " + str(e)[:160], round((time.perf_counter() - t) * 1000)])
                time.sleep(1)
        total = round((time.perf_counter() - t_all) * 1000)
        nxt = []
        for _ in range(5):
            t = time.perf_counter(); admin.q("SELECT 1"); nxt.append(round((time.perf_counter() - t) * 1000))
        return {"fresh_env": fresh, "attempts": log, "total_ms_to_first_success": total, "next5_ms": nxt}
    if mode == "probe":
        return {"fresh_env": fresh, "probe": b.probe(admin, n=n)}
    if mode == "probe2":
        out = {}
        for w in (0, 300, 600, 900, 1200, 1500, 2000):
            _meas(out, f"resp_pad_{w}B", lambda w=w: admin.q(f"SELECT 1 AS a, repeat('x',{w}) AS pad"))
        # thu TCP_QUICKACK cho cac ket noi moi
        import urllib3.connection as uc
        if hasattr(socket, "TCP_QUICKACK"):
            uc.HTTPConnection.default_socket_options = list(uc.HTTPConnection.default_socket_options) + [
                (socket.IPPROTO_TCP, socket.TCP_QUICKACK, 1)]
            admin2 = b.Api(os.environ["CLUSTER_ARN"], os.environ["ADMIN_SECRET_ARN"])
            _meas(out, "quickack_select1", lambda: admin2.q("SELECT 1"))
        return {"probe2": out}
    res = b.run_bench(admin, app, n=n, only=event.get("only"))
    return {"fresh_env": fresh, "n": n, "results": res, "memory": context.memory_limit_in_mb}
