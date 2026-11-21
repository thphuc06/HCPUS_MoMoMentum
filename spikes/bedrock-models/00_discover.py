"""Liệt kê model và inference profile khả dụng (chỉ-đọc)."""
import boto3, json, re, sys
region = sys.argv[1] if len(sys.argv) > 1 else "ap-southeast-1"
b = boto3.client("bedrock", region_name=region)
fm = b.list_foundation_models()["modelSummaries"]
print(f"== {region}: {len(fm)} foundation models")
for m in sorted(fm, key=lambda x: x["modelId"]):
    if any(k in m["modelId"] for k in ("claude", "nova", "cohere", "titan")):
        print(m["modelId"], m["inferenceTypesSupported"], m["inputModalities"], m["outputModalities"])
ps = b.list_inference_profiles(typeEquals="SYSTEM_DEFINED", maxResults=1000)["inferenceProfileSummaries"]
print(f"== profiles: {len(ps)}")
for p in sorted(ps, key=lambda x: x["inferenceProfileId"]):
    if any(k in p["inferenceProfileId"] for k in ("claude-haiku-4-5","claude-haiku-5","claude-sonnet-4-6","claude-sonnet-5","nova","cohere")):
        print(p["inferenceProfileId"], p["status"])
