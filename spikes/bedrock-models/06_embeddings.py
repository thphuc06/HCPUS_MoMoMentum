"""Mục 6: embedding tiếng Việt không dấu/viết tắt. Dữ liệu giao dịch hoàn toàn hư cấu."""
import sys, json, time, unicodedata, itertools
import numpy as np
from common import *

# (hũ, khái niệm, [biến thể có dấu / không dấu / viết tắt])
DATA = [
 ("an_uong", "highlands", ["highlands coffee", "cf highland", "cà phê highlands", "ca phe highlands"]),
 ("an_uong", "com_tam", ["ăn trưa cơm tấm", "an trua com tam", "an trua com tam 40k"]),
 ("an_uong", "tra_sua", ["trà sữa gongcha", "tra sua gong cha", "ts gongcha"]),
 ("hoa_don", "nuoc", ["tiền nước tháng 11", "ck tien nuoc t11", "tien nuoc thang 11"]),
 ("hoa_don", "dien", ["tiền điện tháng 11", "tien dien t11", "ck tien dien thang 11"]),
 ("hoa_don", "internet", ["cước internet fpt", "cuoc internet fpt", "tt hd wifi fpt"]),
 ("di_chuyen", "grab", ["grab đi làm", "grab di lam", "gr di lam"]),
 ("di_chuyen", "xang", ["đổ xăng 50k", "do xang 50k", "xang xe 50k"]),
 ("giai_tri", "netflix", ["netflix tháng 11", "netflix thang 11", "nf t11"]),
 ("giai_tri", "phim", ["xem phim cgv", "xem phim cgv cuoi tuan", "cgv ve phim"]),
 ("tien_tro", "tro", ["tiền trọ tháng 11", "tien tro t11", "ck tien tro thang 11"]),
 ("tien_tro", "coc", ["tiền cọc phòng", "tien coc phong tro", "dat coc phong"]),
 ("mua_sam", "shopee", ["mua áo shopee", "mua ao shopee", "shopee don hang ao thun"]),
 ("mua_sam", "sach", ["mua sách tiki", "mua sach tiki", "tiki sach"]),
]
ITEMS = [(j, c, t) for j, c, ts in DATA for t in ts]
TEXTS = [t for _, _, t in ITEMS]; JAR = [j for j, _, _ in ITEMS]; CON = [c for _, c, _ in ITEMS]
KEY_PAIRS = [("tiền nước tháng 11", "ck tien nuoc t11"), ("tiền nước tháng 11", "tien nuoc thang 11"), ("highlands coffee", "cf highland"),
             ("cà phê highlands", "ca phe highlands"), ("tiền trọ tháng 11", "tien tro t11"), ("tiền điện tháng 11", "tiền nước tháng 11"),
             ("tiền trọ tháng 11", "tiền nước tháng 11"), ("highlands coffee", "ăn trưa cơm tấm"), ("netflix tháng 11", "nf t11")]

def strip(s):
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")

def embed_cohere_v3(c, mid, texts, itype):
    out = []
    for i in range(0, len(texts), 96):
        r = c.invoke_model(modelId=mid, body=json.dumps({"texts": texts[i:i+96], "input_type": itype, "truncate": "NONE"}))
        out += json.loads(r["body"].read())["embeddings"]
    return np.array(out)

def embed_cohere_v4(c, mid, texts, itype):
    out = []
    for i in range(0, len(texts), 96):
        r = c.invoke_model(modelId=mid, body=json.dumps({"texts": texts[i:i+96], "input_type": itype, "embedding_types": ["float"], "output_dimension": 1024, "truncate": "NONE"}))
        out += json.loads(r["body"].read())["embeddings"]["float"]
    return np.array(out)

def embed_titan(c, mid, texts, itype):
    out = []
    for t in texts:
        r = c.invoke_model(modelId=mid, body=json.dumps({"inputText": t, "dimensions": 1024, "normalize": True}))
        out.append(json.loads(r["body"].read())["embedding"])
    return np.array(out)

ABBR = {"ck": "chuyen khoan", "t11": "thang 11", "cf": "ca phe", "tt": "thanh toan", "hd": "hoa don", "ts": "tra sua", "gr": "grab", "nf": "netflix"}
def normalize(s):
    """strip dấu + hạ chữ thường + mở rộng viết tắt phổ biến (từ điển tự soạn)."""
    return " ".join(ABBR.get(w, w) for w in strip(s).lower().split())

def analyze(E, texts=TEXTS):
    E = E / np.linalg.norm(E, axis=1, keepdims=True); S = E @ E.T; n = len(texts)
    same_con, same_jar, diff_jar = [], [], []
    for i, j in itertools.combinations(range(n), 2):
        (same_con if CON[i] == CON[j] else same_jar if JAR[i] == JAR[j] else diff_jar).append(S[i, j])
    # 1-NN leave-one-out
    S2 = S.copy(); np.fill_diagonal(S2, -9); nn = S2.argmax(1)
    acc_jar = float(np.mean([JAR[nn[i]] == JAR[i] for i in range(n)])); acc_con = float(np.mean([CON[nn[i]] == CON[i] for i in range(n)]))
    wrong = [(texts[i], texts[nn[i]], round(float(S[i, nn[i]]), 3)) for i in range(n) if JAR[nn[i]] != JAR[i]]
    st = lambda a: dict(mean=round(float(np.mean(a)), 3), min=round(float(np.min(a)), 3), max=round(float(np.max(a)), 3), n=len(a))
    ge97 = lambda a: round(float(np.mean(np.array(a) >= 0.97)), 3)
    idx = {t: i for i, t in enumerate(TEXTS)}
    kp = {f"{a} | {b}": round(float(S[idx[a], idx[b]]), 3) for a, b in KEY_PAIRS}
    # ngưỡng tốt nhất tách cùng-ý với khác-ý (cùng hũ khác ý + khác hũ)
    neg = same_jar + diff_jar; pos = same_con
    best = max(((th, (np.mean(np.array(pos) >= th) + np.mean(np.array(neg) < th)) / 2) for th in np.arange(0.3, 1.0, 0.005)), key=lambda x: x[1])
    return dict(same_concept=st(same_con), same_jar_diff_concept=st(same_jar), diff_jar=st(diff_jar),
                frac_same_concept_ge_0_97=ge97(same_con), frac_diffjar_ge_0_97=ge97(diff_jar), frac_samejar_ge_0_97=ge97(same_jar),
                nn_jar_acc=round(acc_jar, 3), nn_concept_acc=round(acc_con, 3), nn_jar_errors=wrong, key_pairs=kp,
                best_threshold=dict(th=round(float(best[0]), 3), balanced_acc=round(float(best[1]), 3)))

if __name__ == "__main__":
    runs = [("ap-southeast-1", "cohere.embed-multilingual-v3", embed_cohere_v3), ("ap-southeast-1", "global.cohere.embed-v4:0", embed_cohere_v4),
            ("us-east-1", "amazon.titan-embed-text-v2:0", embed_titan)]
    res = {}
    for region, mid, fn in runs:
        c = client(region)
        for itype in (["search_document", "classification"] if "cohere" in mid else ["-"]):
            for variant in ("raw", "stripped", "normalized"):
                texts = {"raw": TEXTS, "stripped": [strip(t) for t in TEXTS], "normalized": [normalize(t) for t in TEXTS]}[variant]
                name = f"{region}|{mid}|{itype}|{variant}"
                t0 = time.time()
                try:
                    E, _ = with_retry(lambda: fn(c, mid, texts, itype), base=5)
                    r = analyze(E, texts); r["secs"] = round(time.time() - t0, 2); r["dim"] = int(E.shape[1]); res[name] = r
                    print(name, json.dumps({k: v for k, v in r.items() if k not in ("nn_jar_errors", "key_pairs")}, ensure_ascii=False))
                    print("   sai:", r["nn_jar_errors"]); print("   cặp:", r["key_pairs"], flush=True)
                except Exception as e:
                    res[name] = {"error": err_str(e)}; print(name, "LỖI", err_str(e), flush=True)
                time.sleep(3)
    json.dump(res, open("results_06_embeddings.json", "w"), ensure_ascii=False, indent=1)
    print("n texts:", len(TEXTS))
