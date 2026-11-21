"""Tra giá (Price List API, chỉ-đọc) cho các model ứng viên. In dòng giá on-demand input/output token."""
import boto3, json, sys
p = boto3.client("pricing", region_name="us-east-1")
want = ["Kimi K3", "Kimi K2.5", "Qwen3 Next", "Qwen3 32B", "gpt-oss-120b", "GPT OSS 120B", "Mistral Large 3", "DeepSeek V3.2", "Nova 2 Lite", "Nova Lite", "Nova Pro", "Nova Micro", "Haiku 4.5", "Sonnet 4.6", "Gemma 3 27B", "GLM 4.7", "GLM-4.7"]
out = {}
SC = sys.argv[1]
for rg in ["ap-southeast-1", "us-east-1"]:
    tok = None; n = 0
    while True:
        kw = dict(ServiceCode=SC, Filters=[{"Type": "TERM_MATCH", "Field": "regionCode", "Value": rg}], MaxResults=100)
        if tok: kw["NextToken"] = tok
        r = p.get_products(**kw); n += len(r["PriceList"])
        for s in r["PriceList"]:
            d = json.loads(s); a = d["product"]["attributes"]
            name = a.get("model", "") + " " + a.get("modelId", "")
            if not any(w.lower() in name.lower() for w in want): continue
            inf = a.get("inferenceType", ""); usage = a.get("usagetype", "")
            for t in d["terms"].get("OnDemand", {}).values():
                for pd in t["priceDimensions"].values():
                    out.setdefault(rg, []).append((a.get("model"), inf, usage.split(":")[-1][:60], pd["pricePerUnit"].get("USD"), pd["unit"]))
        tok = r.get("NextToken")
        if not tok: break
    print(rg, "tổng dòng:", n)
for rg, rows in out.items():
    print("==", rg)
    for r in sorted(set(map(tuple, rows)), key=lambda x: (str(x[0]), str(x[1]), str(x[2]))): print(r)
