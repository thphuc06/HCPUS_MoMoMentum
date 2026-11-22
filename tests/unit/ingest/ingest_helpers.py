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
import yofina_ingest.context  # noqa: E402
import yofina_ingest.csvparse  # noqa: E402
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
