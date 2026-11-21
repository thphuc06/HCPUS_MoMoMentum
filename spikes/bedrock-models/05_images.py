"""Mục 5b: đưa 3 ảnh thông báo chuyển khoản giả lập cho model đa phương thức, trích JSON, chấm từng trường.
Dùng: python 05_images.py <region> <key|modelId>[,<key|modelId>...]"""
import sys, json, re, time, unicodedata, difflib
from common import *

region = sys.argv[1]
keys = sys.argv[2].split(",")
c = client(region, read_timeout=180)
TRUTH = json.load(open("images/truth.json", encoding="utf8"))
PROMPT = ("Đây là ảnh chụp thông báo chuyển khoản/thanh toán (dữ liệu hư cấu). Trích thông tin và chỉ trả về MỘT đối tượng JSON, không giải thích, với các khóa: "
          '{"amount_vnd": số nguyên VND (không dấu chấm, bỏ dấu âm), "time": "YYYY-MM-DD HH:MM", "counterparty": "tên người/đơn vị nhận, giữ nguyên chữ trên ảnh", '
          '"note": "nội dung/lời nhắn, giữ nguyên chữ trên ảnh"}')


def strip(s):
    s = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def ext_json(txt):
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def score(res, truth):
    if not res:
        return dict(amount=False, time=False, counterparty=False, counterparty_noaccent=False, note=False, note_sim=0.0)
    amt = re.sub(r"\D", "", str(res.get("amount_vnd", "")))
    t = str(res.get("time", "")).strip()
    cp = str(res.get("counterparty", "")).strip()
    nt = str(res.get("note", "")).strip()
    return dict(amount=amt == str(truth["amount_vnd"]), time=t[:16] == truth["time"],
                counterparty=cp.lower() == truth["counterparty"].lower(), counterparty_noaccent=strip(cp).lower() == strip(truth["counterparty"]).lower(),
                note=nt.lower() == truth["note"].lower(), note_sim=round(difflib.SequenceMatcher(None, nt.lower(), truth["note"].lower()).ratio(), 2))


allres = {}
for k in keys:
    mid = MODELS.get(k, k)
    rows = []
    for case in TRUTH:
        img = open("images/" + case["file"], "rb").read()
        kw = dict(modelId=mid, messages=[{"role": "user", "content": [{"image": {"format": "png", "source": {"bytes": img}}}, {"text": PROMPT}]}],
                  inferenceConfig={"maxTokens": 1200})
        logs = []
        try:
            pace(k, 12.0 if ("anthropic" in mid) else 1.5)
            t0 = time.perf_counter()
            r, _ = with_retry(lambda: c.converse(**kw), tries=6, base=10, log=logs)
            dt = time.perf_counter() - t0
            txt = "".join(b.get("text", "") for b in r["output"]["message"]["content"])
            res = ext_json(txt)
            rows.append(dict(file=case["file"], secs=round(dt, 2), parsed=res, score=score(res, case["truth"]), usage=r["usage"], raw=None if res else txt[:300]))
        except Exception as e:
            rows.append(dict(file=case["file"], error=err_str(e)))
            if "AccessDenied" in err_str(e) or "ValidationException" in err_str(e):
                break
    ok = [r for r in rows if "score" in r]
    summ = {f: sum(1 for r in ok if r["score"][f]) for f in ("amount", "time", "counterparty", "counterparty_noaccent", "note")}
    allres[k] = dict(model=mid, region=region, n_ok=len(ok), summary=summ, rows=rows)
    print(f"[{region}] {k}: gọi được {len(ok)}/3; đúng trên 3 ảnh: {summ}; median {med([r['secs'] for r in ok])}s")
    for r in rows:
        if "error" in r:
            print("    LỖI", r["error"][:200])
        else:
            print("   ", r["file"], json.dumps(r["parsed"], ensure_ascii=False), {a: b for a, b in r["score"].items() if a in ("note_sim",)})
    sys.stdout.flush()
    json.dump(allres, open(f"results_05_images_{region}_{int(time.time())}.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
