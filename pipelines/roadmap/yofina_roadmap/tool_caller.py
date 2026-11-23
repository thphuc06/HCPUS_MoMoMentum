"""Gọi tool Lambda bằng danh tính dịch vụ, với user_id cố định theo sự kiện."""

from __future__ import annotations

import asyncio
import base64
import json
from contextlib import closing
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from yofina_agent import notices
from yofina_agent.tools import ToolKind, ToolOutcome, classify_result

from yofina_core.errors import ErrorCode
from yofina_roadmap.settings import ALLOWED_TOOLS


class LambdaTools:
    def __init__(self, client: Any, functions: dict[str, str], user_id: str) -> None:
        self._client = client
        self._functions = functions
        self._user_id = user_id

    async def __call__(self, short_name: str, args: dict[str, Any], target: str) -> ToolOutcome:
        name = f"{target}___{short_name}"
        if short_name not in ALLOWED_TOOLS.get(target, ()) or "confirm_token" in args:
            return ToolOutcome(
                name,
                ToolKind.DENIED,
                code=ErrorCode.FORBIDDEN.value,
                message=notices.FORBIDDEN_MESSAGE,
            )
        return await asyncio.to_thread(self._invoke, name, self._functions[target], args)

    def _invoke(self, name: str, function: str, args: dict[str, Any]) -> ToolOutcome:
        context = json.dumps({"custom": {"bedrockAgentCoreToolName": name}}).encode()
        payload = json.dumps({**args, "user_id": self._user_id}, ensure_ascii=False).encode()
        try:
            response = self._client.invoke(
                FunctionName=function,
                InvocationType="RequestResponse",
                ClientContext=base64.b64encode(context).decode("ascii"),
                Payload=payload,
            )
            stream = response.get("Payload")
            body = b""
            if stream is not None:
                with closing(stream):
                    if not response.get("FunctionError"):
                        body = stream.read()
        except (BotoCoreError, ClientError, OSError):
            return self._unavailable(name)
        if response.get("FunctionError") or response.get("StatusCode") != 200:
            return self._unavailable(name)
        try:
            result = json.loads(body)
        except (UnicodeError, ValueError):
            result = None
        return classify_result(name, {"structuredContent": result})

    @staticmethod
    def _unavailable(name: str) -> ToolOutcome:
        return ToolOutcome(
            name,
            ToolKind.UNAVAILABLE,
            code=ErrorCode.DATABASE_UNAVAILABLE.value,
            message=notices.UNAVAILABLE_MESSAGE,
        )
