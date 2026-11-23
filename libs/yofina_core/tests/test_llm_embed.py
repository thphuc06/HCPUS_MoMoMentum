"""Unit test của `LlmGateway.embed` (Cohere Embed v3 qua InvokeModel). Client Bedrock và bộ đếm giả chỉ có ở đây."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from botocore.exceptions import ClientError

from yofina_core.config import Config
from yofina_core.llm import (
    EMBED_MAX_BATCH,
    EMBED_MAX_CHARS,
    AllModelsFailed,
    BudgetCapReached,
    LlmGateway,
    LlmSettings,
    ModelBudgetExceeded,
    ModelSpec,
    TurnScope,
)

FIXED_NOW = datetime(2026, 11, 21, 15, 0, tzinfo=UTC)


class FakeEmbedClient:
    def __init__(self, script: list[Any] | None = None, dim: int = 4) -> None:
        self.script = list(script or [])
        self.calls: list[dict[str, Any]] = []
        self.dim = dim

    def invoke_model(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(kw)
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, BaseException):
                raise item
        body = json.loads(kw["body"])
        vecs = [
            [float(len(t)), 1.0, 0.0, float(i)][: self.dim] for i, t in enumerate(body["texts"])
        ]
        raw = json.dumps({"embeddings": vecs, "response_type": "embeddings_floats"}).encode()
        return {
            "body": io.BytesIO(raw),
            "ResponseMetadata": {"HTTPHeaders": {"x-amzn-bedrock-input-token-count": "7"}},
        }


class FakeUsage:
    def __init__(self, cap: int = 100) -> None:
        self.n = 0
        self.cap = cap

    def consume(self, *, day: str, model: str, cap: int, ttl_epoch: int) -> int:
        if self.n >= self.cap:
            raise BudgetCapReached(model)
        self.n += 1
        return self.n


def gw(client: FakeEmbedClient, usage: FakeUsage | None = None, models: int = 1) -> LlmGateway:
    specs = tuple(ModelSpec(f"emb-{i}", rpm=0, daily_cap=100) for i in range(models))
    return LlmGateway(
        LlmSettings(roles={"embedding": specs}),
        config=Config({}),
        client=client,
        usage=usage or FakeUsage(),
        now=lambda: FIXED_NOW,
        sleep=lambda s: None,
    )


def err(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "x"}}, "InvokeModel")


def test_gom_lo_toi_da_96_chuoi_va_giu_thu_tu():
    client = FakeEmbedClient()
    usage = FakeUsage()
    texts = [f"giao dich {i}" for i in range(EMBED_MAX_BATCH * 2 + 5)]
    res = gw(client, usage).embed("embedding", texts)
    assert [len(json.loads(c["body"])["texts"]) for c in client.calls] == [96, 96, 5]
    assert res.calls == 3 and usage.n == 3  # mỗi lô là một lời gọi được đếm vào trần ngày
    assert len(res.vectors) == len(texts)
    assert res.vectors[0][0] == float(len("giao dich 0"))
    assert res.input_tokens == 21 and res.model_id == "emb-0"


def test_body_dung_tai_lieu_va_input_type():
    client = FakeEmbedClient()
    gw(client).embed("embedding", ["a"], input_type="search_query")
    call = client.calls[0]
    body = json.loads(call["body"])
    assert body == {"texts": ["a"], "input_type": "search_query", "truncate": "END"}
    assert call["modelId"] == "emb-0" and call["contentType"] == "application/json"


def test_input_type_la_la_bi_tu_choi_va_chuoi_dai_bi_cat():
    client = FakeEmbedClient()
    g = gw(client)
    with pytest.raises(ValueError):
        g.embed("embedding", ["a"], input_type="classification")
    g.embed("embedding", ["x" * (EMBED_MAX_CHARS + 50)])
    assert len(json.loads(client.calls[0]["body"])["texts"][0]) == EMBED_MAX_CHARS


def test_danh_sach_rong_khong_goi_model():
    client = FakeEmbedClient()
    res = gw(client).embed("embedding", [])
    assert res.vectors == [] and client.calls == []


def test_du_phong_sang_model_ke_tiep_khi_throttle():
    client = FakeEmbedClient([err("ThrottlingException")])
    res = gw(client, models=2).embed("embedding", ["a", "b"])
    assert res.model_id == "emb-1" and res.attempts == [("emb-0", "ThrottlingException")]


def test_lo_sau_di_lai_dung_model_cua_lo_dau():
    # lô 1 chạy ở emb-0; lô 2 bị throttle thì KHÔNG sang emb-1 (vector của hai model không so sánh được) mà báo lỗi
    client = FakeEmbedClient([None, err("ThrottlingException")])
    with pytest.raises(ClientError):
        gw(client, models=2).embed("embedding", [f"t{i}" for i in range(EMBED_MAX_BATCH + 1)])
    assert [c["modelId"] for c in client.calls] == ["emb-0", "emb-0"]


def test_het_model_thi_all_models_failed():
    client = FakeEmbedClient([err("ThrottlingException"), err("AccessDeniedException")])
    with pytest.raises(AllModelsFailed):
        gw(client, models=2).embed("embedding", ["a"])


def test_cham_tran_ngay_thi_khong_goi_model():
    client = FakeEmbedClient()
    with pytest.raises(ModelBudgetExceeded):
        gw(client, FakeUsage(cap=0)).embed("embedding", ["a"])
    assert client.calls == []


def test_tran_luot_hoi_thoai_tinh_theo_lo():
    client = FakeEmbedClient()
    scope = TurnScope(max_calls=1)
    g = gw(client)
    with pytest.raises(ModelBudgetExceeded):
        g.embed("embedding", [f"t{i}" for i in range(EMBED_MAX_BATCH + 1)], scope=scope)
    assert scope.calls == 1


def test_loi_khong_phai_tam_thoi_ra_thang_ngoai():
    client = FakeEmbedClient([err("ValidationException")])
    with pytest.raises(ClientError):
        gw(client, models=2).embed("embedding", ["a"])
    assert len(client.calls) == 1
