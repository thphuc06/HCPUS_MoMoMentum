"""Sinh các bảng markdown từ file JSON kết quả (để không gõ tay số liệu)."""
import json, glob
def L(f): return json.load(open(f, encoding="utf8"))
print("### A. 02 latency (maxTokens 100, 3 lần, trung vị)")
for rg in ("ap-southeast-1", "us-east-1"):
    for k, o in L(f"results_02_latency_{rg}.json").items():
        print(f"| {rg} | {k} | {o['ttft_med']:.2f} | {o['total_stream_med']:.2f} | {o['total_converse_med']:.2f} | {o['out_tokens']} | {len(o['notes'])} |")
print("### B. 08 probe (maxTokens 300, độ dài tự nhiên, 3 lần)")
for g in ("ap", "us"):
    for k, o in L(f"results_08_probe_{g}.json").items():
        t = o["text"]
        if "error" in t: print(f"| {g} | {k} | LỖI {t['error'][:60]} |"); continue
        print(f"| {g} | {k} | {t['ttft_text_med']:.2f} | {t['ttft_any_med']:.2f} | {t['total_med']:.2f} | {t['out_tokens']} |")
print("### C. images")
allr = {}
for f in sorted(glob.glob("results_05_images_all.json")): allr.update({(v['region'], k): v for k, v in L(f).items()})
for (rg, k), v in allr.items():
    s = v["summary"]; print(f"| {rg} | {k} | {v['n_ok']}/3 | {s['amount']} | {s['time']} | {s['counterparty']} / {s['counterparty_noaccent']} | {s['note']} | {med([r['secs'] for r in v['rows'] if 'secs' in r]) if False else ''} |")
