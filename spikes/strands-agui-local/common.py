"""Cấu hình chung cho các spike."""
import os, time
from strands.models import BedrockModel
from botocore.config import Config

HAIKU = os.environ.get("SPIKE_MODEL", "global.anthropic.claude-haiku-4-5-20251001-v1:0")
REGION = os.environ.get("SPIKE_REGION", "ap-southeast-1")

def model(max_tokens=1024, model_id=None):
    return BedrockModel(
        model_id=model_id or HAIKU, region_name=REGION, temperature=0.0, max_tokens=max_tokens,
        boto_client_config=Config(retries={"max_attempts": 8, "mode": "adaptive"}, read_timeout=120),
    )

JARS = {
    "an_uong": {"name": "Ăn uống", "balance_vnd": 1_250_000, "budget_vnd": 3_000_000},
    "di_lai": {"name": "Đi lại", "balance_vnd": 640_000, "budget_vnd": 1_000_000},
    "giai_tri": {"name": "Giải trí", "balance_vnd": 420_000, "budget_vnd": 800_000},
}
