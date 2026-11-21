"""Mở rộng mục 2: liệt kê quota áp dụng (Service Quotas, chỉ đọc) của Bedrock theo model, kèm giá trị mặc định AWS."""
import sys, json, boto3
region = sys.argv[1]
sq = boto3.client("service-quotas", region_name=region)
def lst(fn):
    out, tok = [], None
    while True:
        kw = dict(ServiceCode="bedrock", MaxResults=100); 
        if tok: kw["NextToken"] = tok
        r = fn(**kw); out += r["Quotas"]; tok = r.get("NextToken")
        if not tok: return out
applied = {q["QuotaCode"]: q for q in lst(sq.list_service_quotas)}
default = {q["QuotaCode"]: q for q in lst(sq.list_aws_default_service_quotas)}
rows = []
for code, d in default.items():
    a = applied.get(code)
    rows.append(dict(code=code, name=d["QuotaName"], default=d["Value"], applied=a["Value"] if a else None, adjustable=d.get("Adjustable")))
json.dump(rows, open(f"results_07_quotas_{region}.json", "w"), ensure_ascii=False, indent=1)
print(region, "tổng", len(rows), "quota; applied>0:", sum(1 for r in rows if (r["applied"] or 0) > 0))
