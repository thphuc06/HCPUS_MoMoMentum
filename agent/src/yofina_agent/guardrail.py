"""L0: Bedrock Guardrail `yofina-guardrail` gọi qua `ApplyGuardrail` (lọc đầu vào và đầu ra).

- Dùng `bedrock-runtime:ApplyGuardrail` thay vì gắn guardrail vào lời gọi model: lọc được cả câu hỏi của người dùng lẫn lời do tầng Python
  viết, không phụ thuộc model nào. Id/version đọc từ cấu hình (`AgentSettings.guardrail_id/version`: env hoặc SSM `/yofina/guardrail/...`).
- TẮT được bằng `YOFINA_GUARDRAIL_ENABLED=false` (chạy local khi chưa có guardrail); bật mà chưa có id thì cũng tắt và ghi log rõ ràng.
- Lỗi dịch vụ: theo `guardrail_fail_open` (mặc định mở: lượt vẫn chạy, các lớp tất định phía sau vẫn đứng; có log). Đặt đóng để chặn khi lỗi.
- Nội dung gửi đi đã được che PII (`yofina_core.pii`) ở lớp gọi.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Literal

from yofina_agent.settings import AgentSettings

log = logging.getLogger("yofina.agent.guardrail")

Source = Literal["INPUT", "OUTPUT"]


@dataclass(frozen=True)
class GuardrailResult:
    blocked: bool
    reason: str | None = None  # `topic:<tên>`, `content:<loại>`, `prompt_attack`, `error`
    latency_ms: int = 0
    skipped: bool = False  # tắt hoặc chưa cấu hình
    error: str | None = None


NOT_APPLIED = GuardrailResult(blocked=False, skipped=True)


def reason_from_assessments(assessments: list[dict[str, Any]]) -> str:
    """Lý do chặn gọn từ phần `assessments` của ApplyGuardrail (chỉ để log và trace, không hiện cho người dùng)."""
    for a in assessments:
        for t in (a.get("topicPolicy") or {}).get("topics", []):
            if t.get("action") == "BLOCKED":
                return f"topic:{t.get('name', '?')}"
        for f in (a.get("contentPolicy") or {}).get("filters", []):
            if f.get("action") == "BLOCKED":
                return "prompt_attack" if f.get("type") == "PROMPT_ATTACK" else f"content:{f.get('type', '?')}"
    return "other"


class Guardrail:
    def __init__(self, settings: AgentSettings, *, region: str, client: Any | None = None) -> None:
        self._s, self._region, self._client = settings, region, client
        self.enabled = bool(settings.guardrail_enabled)
        if self.enabled and not (settings.guardrail_id and settings.guardrail_version):
            log.warning(
                json.dumps(
                    {
                        "event": "guardrail_disabled",
                        "reason": "chưa có guardrail_id/guardrail_version (env hoặc SSM /yofina/guardrail/...)",
                    }
                )
            )
            self.enabled = False

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3  # import muộn: chỉ khi thật sự gọi

            self._client = boto3.client("bedrock-runtime", region_name=self._region)
        return self._client

    def _apply(self, text: str, source: Source) -> GuardrailResult:
        started = time.perf_counter()
        try:
            resp = self.client.apply_guardrail(
                guardrailIdentifier=self._s.guardrail_id,
                guardrailVersion=self._s.guardrail_version,
                source=source,
                content=[{"text": {"text": text}}],
            )
        except Exception as exc:  # noqa: BLE001
            ms = int((time.perf_counter() - started) * 1000)
            log.warning(json.dumps({"event": "guardrail_error", "source": source, "error": f"{type(exc).__name__}: {exc}"[:300]}))
            return GuardrailResult(
                blocked=not self._s.guardrail_fail_open,
                reason="error",
                latency_ms=ms,
                error=type(exc).__name__,
            )
        ms = int((time.perf_counter() - started) * 1000)
        if resp.get("action") == "GUARDRAIL_INTERVENED":
            reason = reason_from_assessments(list(resp.get("assessments") or []))
            log.info(json.dumps({"event": "guardrail_blocked", "source": source, "reason": reason, "ms": ms}))
            return GuardrailResult(blocked=True, reason=reason, latency_ms=ms)
        return GuardrailResult(blocked=False, latency_ms=ms)

    async def check(self, text: str, source: Source) -> GuardrailResult:
        """Kiểm một đoạn văn bản (đã che PII). Không bao giờ ném ngoại lệ ra ngoài."""
        if not self.enabled or not text.strip():
            return NOT_APPLIED
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._apply, text, source),
                timeout=self._s.guardrail_timeout_seconds,
            )
        except TimeoutError:
            log.warning(json.dumps({"event": "guardrail_timeout", "source": source}))
            return GuardrailResult(
                blocked=not self._s.guardrail_fail_open,
                reason="error",
                latency_ms=int(self._s.guardrail_timeout_seconds * 1000),
                error="Timeout",
            )
