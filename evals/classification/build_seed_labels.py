"""Sinh nhãn k-NN seed của persona (`data/personas/classify_labels/<persona>.json`) bằng Bedrock THẬT (vai `embedding`).

    $env:AWS_REGION='ap-southeast-1'; $env:YOFINA_USAGE_TABLE='yofina-usage'
    uv run python evals/classification/build_seed_labels.py [--persona minh ...]

Nguồn nhãn của một persona: (1) cửa hàng trong `specs/<persona>.json` (kèm hũ), (2) `base_vocabulary.json` (từ vựng gốc dùng chung), chỉ giữ nhãn
của hũ mà persona có. Chuỗi được chuẩn hóa bằng đúng `yofina_classify.text.normalize_text` của Lambda; trùng chuỗi thì giữ một. Mỗi persona một lần
gọi embedding (gom lô). Định dạng file: `yofina_ledger.classify_seed` (float16 base64). Nạp vào Aurora: `classify_seed.apply_seed_labels` sau khi đặt lại demo.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for extra in ("libs/yofina_core/src", "gateway/tools/ledger", "pipelines/classify", "data"):
    sys.path.insert(0, str(ROOT / extra))

PERSONAS_DIR = ROOT / "data" / "personas"
OUT_DIR = PERSONAS_DIR / "classify_labels"


def label_sources(persona: str) -> list[tuple[str, str]]:
    """[(văn bản gốc, mã hũ)] của persona, chưa chuẩn hóa."""
    spec = json.loads((PERSONAS_DIR / "specs" / f"{persona}.json").read_text(encoding="utf-8"))
    jars = {j["code"] for j in spec["jars"]}
    out: list[tuple[str, str]] = []
    for j in spec["jars"]:
        out += [(m["name"], j["code"]) for m in j.get("merchants", [])]
    base = json.loads((OUT_DIR / "base_vocabulary.json").read_text(encoding="utf-8"))["labels"]
    for jar, texts in base.items():
        if jar in jars:
            out += [(t, jar) for t in texts]
    return out


def normalized_labels(persona: str) -> list[tuple[str, str]]:
    from yofina_classify.text import normalize_text

    seen: dict[str, str] = {}
    for text, jar in label_sources(persona):
        norm = normalize_text(text)
        if norm and norm not in seen:
            seen[norm] = jar
    return sorted(seen.items())


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", action="append")
    args = ap.parse_args()
    from yofina_core.llm import EMBED_INPUT_DOCUMENT, LlmGateway
    from yofina_core.wallet import EMBEDDING_DIMENSIONS
    from yofina_ledger.classify_seed import ENCODING, encode_vector

    gw = LlmGateway()
    for persona in args.persona or ["minh", "lan", "khoa"]:
        labels = normalized_labels(persona)
        res = gw.embed("embedding", [t for t, _ in labels], input_type=EMBED_INPUT_DOCUMENT)
        data = {
            "persona": persona,
            "model": res.model_id,
            "dimensions": EMBEDDING_DIMENSIONS,
            "encoding": ENCODING,
            "labels": [
                {"text_norm": t, "jar_code": j, "embedding": encode_vector(v)}
                for (t, j), v in zip(labels, res.vectors, strict=True)
            ],
        }
        (OUT_DIR / f"{persona}.json").write_text(
            json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"{persona}: {len(labels)} nhãn, model {res.model_id}, {res.calls} lời gọi embedding")
    return 0


if __name__ == "__main__":
    sys.exit(main())
