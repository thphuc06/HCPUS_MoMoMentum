"""Bản GIẢ của embedding và model nhỏ, CHỈ cho chế độ khô của bộ kiểm (`run_eval.py --mode dry`): chạy được khi chưa có AWS.

Không dùng trong mã sản phẩm và kết quả của chế độ khô KHÔNG phản ánh chất lượng thật (không dùng để hiệu chỉnh ngưỡng): mục đích duy nhất là
kiểm đường ống (bộ dữ liệu, mô phỏng, chỉ số, báo cáo, hiệu chỉnh) chạy từ đầu đến cuối.

- `HashingEmbedder`: vector 1024 chiều tất định từ băm các từ và bộ ba ký tự (cosine cao khi chuỗi chia sẻ ký tự, nên "ca phe" gần "cafe phe").
- `KeywordJudge`: chọn hũ có nhiều từ trùng nhất với từ vựng gốc `base_vocabulary.json` trong dữ kiện giao dịch; không biết gì ngoài đó.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from yofina_classify.model import JarInfo, Verdict

from yofina_core.wallet import EMBEDDING_DIMENSIONS

ROOT = Path(__file__).resolve().parents[2]
MODEL_ID = "fake-hashing-1024"


def _bucket(token: str) -> tuple[int, float]:
    h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
    return h % EMBEDDING_DIMENSIONS, 1.0 if (h >> 100) & 1 else -1.0


def hash_vector(text: str) -> list[float]:
    v = np.zeros(EMBEDDING_DIMENSIONS)
    padded = f"  {text}  "
    for tri in (padded[i : i + 3] for i in range(len(padded) - 2)):
        i, sign = _bucket("t:" + tri)
        v[i] += 0.5 * sign
    for w in text.split():
        i, sign = _bucket("w:" + w)
        v[i] += 1.0 * sign
    n = np.linalg.norm(v)
    return (v / n if n else v).tolist()


class HashingEmbedder:
    """Cổng `live` của `CachedEmbedder` (có `embed_many`)."""

    def embed_many(self, texts: list[str]) -> tuple[str, list[list[float]]]:
        return MODEL_ID, [hash_vector(t) for t in texts]


class KeywordJudge:
    def __init__(self) -> None:
        base = json.loads(
            (ROOT / "data" / "personas" / "classify_labels" / "base_vocabulary.json").read_text(
                encoding="utf-8"
            )
        )["labels"]
        self.vocab = {
            jar: {w for t in texts for w in t.split() if len(w) > 2} for jar, texts in base.items()
        }

    def __call__(self, prompt: str, jars: dict[str, JarInfo]) -> Verdict:
        from yofina_core.pii import fold

        data: dict[str, Any] = json.loads(prompt)
        tx = data["giao_dich"]
        words = set(
            fold(
                " ".join(str(tx.get(k) or "") for k in ("doi_tac_da_che", "loi_nhan_da_che"))
            ).split()
        )
        scores = {jar: len(words & v) for jar, v in self.vocab.items() if jar in jars}
        best = max(scores, key=lambda j: scores[j], default=None)
        if best is None or scores[best] == 0:
            return Verdict(None, 0.0)
        return Verdict(best, min(0.5 + 0.1 * scores[best], 0.8))
