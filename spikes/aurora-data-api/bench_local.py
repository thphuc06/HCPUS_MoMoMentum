import json, sys
from bench_core import *
from cfg import *
admin, app, _ = apis()
n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
res = run_bench(admin, app, n=n)
res["_vector"] = None
print(json.dumps(res, indent=1))
