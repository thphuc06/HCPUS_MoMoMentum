"""In rút gọn một file SSE đã lưu: python show_sse.py file [độ dài tối đa mỗi event]"""
import json, sys

path = sys.argv[1]
width = int(sys.argv[2]) if len(sys.argv) > 2 else 330
skip_text = "--no-text" in sys.argv
for line in open(path, encoding="utf-8"):
    if not line.startswith("data:"):
        continue
    e = json.loads(line[5:])
    if skip_text and e["type"] == "TEXT_MESSAGE_CONTENT":
        continue
    print(json.dumps(e, ensure_ascii=False)[:width])
