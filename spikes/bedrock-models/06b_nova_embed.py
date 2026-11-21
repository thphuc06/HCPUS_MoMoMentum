"""Mục 6 bổ sung: Nova 2 Multimodal Embeddings (chỉ có ở us-east-1) trên cùng bộ 43 chuỗi."""
import json, time
from importlib import import_module
from common import *

M = import_module("06_embeddings")
import numpy as np

region, mid = "us-east-1", "amazon.nova-2-multimodal-embeddings-v1:0"
c = client(region)


def embed(texts):
    out = []
    for t in texts:
        body = {"taskType": "SINGLE_EMBEDDING", "singleEmbeddingParams": {"embeddingPurpose": "GENERIC_INDEX", "embeddingDimension": 1024,
                                                                         "text": {"truncationMode": "END", "value": t}}}
        pace("novaemb", 3.2)
        r, _ = with_retry(lambda: c.invoke_model(modelId=mid, body=json.dumps(body)), base=5)
        out.append(json.loads(r["body"].read())["embeddings"][0]["embedding"])
    return np.array(out)


res = {}
for variant in ("raw", "normalized"):
    texts = M.TEXTS if variant == "raw" else [M.normalize(t) for t in M.TEXTS]
    E = embed(texts)
    r = M.analyze(E, texts)
    r["dim"] = int(E.shape[1])
    res[f"{region}|{mid}|GENERIC_INDEX|{variant}"] = r
    print(variant, json.dumps({k: v for k, v in r.items() if k not in ("nn_jar_errors", "key_pairs")}, ensure_ascii=False))
    print("   sai:", r["nn_jar_errors"])
    print("   cặp:", r["key_pairs"], flush=True)
json.dump(res, open("results_06b_nova_embed.json", "w"), ensure_ascii=False, indent=1)
