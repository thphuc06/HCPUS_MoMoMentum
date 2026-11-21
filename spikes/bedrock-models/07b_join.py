"""Gộp quota TPM/RPM theo (model, phạm vi), lọc applied TPM > 0; ghép với ListFoundationModels (modalities, inference types)."""
import json, re, sys, boto3, collections
out = {}
for rg in ["ap-southeast-1", "us-east-1"]:
    rows = json.load(open(f"results_07_quotas_{rg}.json", encoding="utf8"))
    agg = collections.defaultdict(dict)
    pat = re.compile(r"^(On-demand|Cross-region|Global cross-region) model inference (tokens|requests) per (minute|day) for (.+)$")
    for r in rows:
        m = pat.match(r["name"])
        if not m: continue
        scope, kind, per, model = m.groups()
        agg[(model, scope)][("TPM" if kind == "tokens" else "RPM") if per == "minute" else "TPD"] = (r["applied"], r["default"])
    b = boto3.client("bedrock", region_name=rg)
    fm = b.list_foundation_models()["modelSummaries"]
    prof = b.list_inference_profiles(typeEquals="SYSTEM_DEFINED", maxResults=1000)["inferenceProfileSummaries"]
    out[rg] = dict(agg={f"{k[0]}|{k[1]}": v for k, v in agg.items()},
                   fm=[dict(id=m["modelId"], name=m["modelName"], prov=m["providerName"], inp=m["inputModalities"], out=m["outputModalities"], inf=m["inferenceTypesSupported"]) for m in fm],
                   prof=[p["inferenceProfileId"] for p in prof])
json.dump(out, open("results_07_joined.json", "w"), ensure_ascii=False, indent=1)
for rg, d in out.items():
    print("=====", rg, "models:", len(d["fm"]), "profiles:", len(d["prof"]))
    for k, v in sorted(d["agg"].items()):
        tpm = v.get("TPM", (None, None))[0]; rpm = v.get("RPM", (None, None))[0]
        if (tpm or 0) > 0 or (rpm is not None and rpm > 0 and tpm is None):
            print(f"{k:75s} TPM={tpm} RPM={rpm}  (default TPM={v.get('TPM',(0,None))[1]} RPM={v.get('RPM',(0,None))[1]})")
