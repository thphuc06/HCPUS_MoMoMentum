"""Hạ tầng test của luồng nạp dữ liệu: đường import, Bedrock giả và kho bộ nhớ (không đặt tên conftest để khỏi đè tests/unit/conftest.py).

`FakeBedrock` thay client `bedrock-runtime`: ghi lại mọi yêu cầu `converse` và trả đúng dạng phản hồi có `toolUse`, nên `LlmGateway`
thật (chuỗi dự phòng, bộ đếm, ép tool, kiểm schema) chạy nguyên vẹn; chỉ phần mạng bị thay.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
_ADDED = []
for extra in (
    "libs/yofina_core/src",
    "pipelines/ingest",
    "gateway/tools/ingest",
    "gateway/tools/ledger",
):
    p = str(REPO / extra)
    if p not in sys.path:
        sys.path.insert(0, p)
        _ADDED.append(p)

# Nạp trước MỌI mô-đun mà test dùng rồi gỡ đường import của gói nạp dữ liệu khỏi sys.path: test_eval_ingest_scoring kiểm
# "thiếu backend thì thoát mã 2" bằng cách trỏ BACKEND_PATH tới thư mục không có, nên gói này không được tìm thấy qua sys.path
# toàn phiên (các mô-đun đã nạp vẫn nằm trong sys.modules).
import yofina_ingest.api  # noqa: E402
import yofina_ingest.classify  # noqa: E402
import yofina_ingest.context  # noqa: E402
import yofina_ingest.csvparse  # noqa: E402
import yofina_ingest.gateway_api  # noqa: E402
import yofina_ingest.normalize  # noqa: E402
import yofina_ingest.prompts  # noqa: E402
import yofina_ingest.repo  # noqa: E402
import yofina_ingest.rest  # noqa: E402
import yofina_ingest.schemas  # noqa: E402
import yofina_ingest.settings  # noqa: E402
import yofina_ingest.worker  # noqa: E402, F401
from yofina_ingest.extract import MemoryUsageStore  # noqa: E402

for _p in _ADDED:
    if _p.endswith((r"pipelines\ingest", "pipelines/ingest")):
        sys.path.remove(_p)

from yofina_core.config import Config  # noqa: E402
from yofina_core.llm import LlmGateway, load_settings  # noqa: E402

SYNTH = REPO / "evals" / "ingest" / "synthetic"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


class FakeBedrock:
    """Client `bedrock-runtime` giả. `script`: danh sách (hoặc hàm) kết quả cho từng lần gọi: dict (input của tool `report`)
    hoặc ngoại lệ để ném."""

    def __init__(self, script: list[Any] | Callable[[dict[str, Any]], Any]) -> None:
        self.script = script
        self.requests: list[dict[str, Any]] = []
        self.embed_requests: list[dict[str, Any]] = []
        self.embed_error: BaseException | None = None

    def converse(self, **req: Any) -> dict[str, Any]:
        self.requests.append(req)
        item = (
            self.script(req)
            if callable(self.script)
            else self.script[min(len(self.requests) - 1, len(self.script) - 1)]
        )
        if isinstance(item, BaseException):
            raise item
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "toolUseId": f"t{len(self.requests)}",
                                "name": "report",
                                "input": item,
                            }
                        }
                    ],
                }
            },
            "usage": {"inputTokens": 10, "outputTokens": 5},
        }

    def invoke_model(self, **req: Any) -> dict[str, Any]:
        """Embedding (Cohere qua `InvokeModel`): vector 1024 chiều do `embed_vector` dựng từ chuỗi (giống nhau thì vector giống nhau)."""
        body = json.loads(req["body"])
        self.embed_requests.append(body)
        if self.embed_error is not None:
            raise self.embed_error
        vecs = [embed_vector(t) for t in body["texts"]]
        return {
            "body": _Body(json.dumps({"embeddings": vecs}).encode()),
            "ResponseMetadata": {"HTTPHeaders": {"x-amzn-bedrock-input-token-count": "3"}},
        }

    def texts(self) -> str:
        """Toàn bộ văn bản đã gửi cho model (system và tin nhắn), để kiểm không có PII."""
        parts: list[str] = []
        for r in self.requests:
            parts += [s["text"] for s in r.get("system", [])]
            for m in r["messages"]:
                for c in m["content"]:
                    if "text" in c:
                        parts.append(c["text"])
        return "\n".join(parts)


class _Body:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def read(self) -> bytes:
        return self.data


def embed_vector(text: str, dims: int = 1024) -> list[float]:
    """Vector đơn vị tất định của một chuỗi: chuỗi giống hệt cho cùng vector (độ giống cosine 1)."""
    import hashlib
    import math

    seed = hashlib.sha256(text.encode("utf-8")).digest()
    raw = [((seed[i % 32] * (i + 1)) % 251) - 125 for i in range(dims)]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [x / norm for x in raw]


def make_gateway(client: FakeBedrock) -> LlmGateway:
    return LlmGateway(
        load_settings(Config({}), env={}),
        client=client,
        usage=MemoryUsageStore(),
        sleep=lambda _s: None,
    )


def csv_bytes(name: str) -> bytes:
    return (SYNTH / "csv" / name).read_bytes()


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


class FakeLabelStore:
    """`LabelStore` trong bộ nhớ: nhãn khớp chính xác theo chuỗi, láng giềng k-NN cố định, lịch sử theo đối tác. Ghi lại các lần gọi."""

    def __init__(self) -> None:
        self.exact: dict[str, list[Any]] = {}
        self.neighbors: list[Any] = []
        self.hist: dict[str, dict[str, int]] = {}
        self.corr: dict[str, int] = {}
        self.calls: list[tuple[str, Any]] = []

    def find_exact(self, user_id, text_norm):
        self.calls.append(("exact", (user_id, text_norm)))
        return list(self.exact.get(text_norm, []))

    def knn(self, user_id, vector, k):
        self.calls.append(("knn", (user_id, len(vector), k)))
        return list(self.neighbors)

    def history(self, user_id, merchants):
        self.calls.append(("history", (user_id, list(merchants))))
        return {m.lower(): dict(self.hist[m.lower()]) for m in merchants if m.lower() in self.hist}

    def corrections(self, user_id, keys):
        self.calls.append(("corrections", (user_id, list(keys))))
        return {k: self.corr[k] for k in keys if k in self.corr}
