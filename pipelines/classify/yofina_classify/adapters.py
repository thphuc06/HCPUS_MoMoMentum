"""Cổng nối bộ phân loại với Bedrock thật qua `yofina_core.llm` (đếm lượt gọi, trần ngày, chuỗi dự phòng): embedding và model nhỏ."""

from __future__ import annotations

from collections.abc import Mapping

from yofina_classify import llm_step
from yofina_classify.model import JarInfo, Verdict
from yofina_core.llm import EMBED_INPUT_DOCUMENT, LlmGateway, TurnScope

EMBED_ROLE = "embedding"


class GatewayEmbedder:
    """`Embedder` trên vai `embedding`. Nhãn lưu và chuỗi tra cùng `search_document` (so giống đối xứng, đúng cách spike Bedrock §6 đo)."""

    def __init__(self, gateway: LlmGateway) -> None:
        self.gateway = gateway

    def embed(self, text_norm: str) -> tuple[str, list[float]]:
        res = self.gateway.embed(EMBED_ROLE, [text_norm], input_type=EMBED_INPUT_DOCUMENT)
        return res.model_id, res.vectors[0]

    def embed_many(self, texts: list[str]) -> tuple[str, list[list[float]]]:
        """Nhúng nhiều chuỗi một lần (gom lô tối đa 96): cho bộ kiểm và script sinh nhãn seed."""
        res = self.gateway.embed(EMBED_ROLE, texts, input_type=EMBED_INPUT_DOCUMENT)
        return res.model_id, res.vectors


class GatewayJudge:
    """`judge(prompt, jars) -> Verdict` trên vai `small`; mã hũ model trả phải thuộc `jars` (danh sách hũ của người dùng)."""

    def __init__(self, gateway: LlmGateway) -> None:
        self.gateway = gateway

    def __call__(self, prompt: str, jars: Mapping[str, JarInfo]) -> Verdict:
        return llm_step.judge(self.gateway, prompt, jars, scope=TurnScope())
