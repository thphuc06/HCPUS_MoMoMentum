"""Tiện ích dùng chung: client, che account ID, gọi có retry/throttle, ghi JSON kết quả."""
import json, re, time, statistics
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

ACCT = re.compile(r"\b\d{12}\b")
def mask(s): return ACCT.sub("<acct>", str(s))

def client(region, retries=0, read_timeout=120):
    return boto3.client("bedrock-runtime", region_name=region,
        config=Config(retries={"max_attempts": retries + 1, "mode": "standard"} if retries else {"max_attempts": 1},
                      read_timeout=read_timeout, connect_timeout=10))

# model ID -> (tên ngắn)
MODELS = {
    "haiku55": "global.anthropic.claude-haiku-5-5",
    "sonnet55": "global.anthropic.claude-sonnet-5-5",
    "haiku45": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
    "sonnet46": "global.anthropic.claude-sonnet-4-6",
    "sonnet5": "global.anthropic.claude-sonnet-5",
    "nova2lite": "global.amazon.nova-2-lite-v1:0",
    "novalite": "apac.amazon.nova-lite-v1:0",
    "novamicro": "apac.amazon.nova-micro-v1:0",
    "novapro": "apac.amazon.nova-pro-v1:0",
}

def with_retry(fn, tries=9, base=15.0, log=None):
    """Chờ rồi thử lại khi Throttling; trả (kết quả, số lần retry). Ném lỗi cuối nếu vẫn bị chặn."""
    last = None
    for i in range(tries):
        try:
            return fn(), i
        except ClientError as e:
            code = e.response["Error"]["Code"]
            last = e
            if code in ("ThrottlingException", "ServiceUnavailableException", "ModelNotReadyException") and i < tries - 1:
                w = min(base * (1.5 ** i), 70)
                if log is not None: log.append(f"retry {i+1} sau {code}, nghỉ {w:.0f}s")
                time.sleep(w)
                continue
            raise
    raise last

def err_str(e):
    if isinstance(e, ClientError):
        return f"{e.response['Error']['Code']}: {mask(e.response['Error'].get('Message',''))} (HTTP {e.response['ResponseMetadata']['HTTPStatusCode']})"
    return f"{type(e).__name__}: {mask(e)}"

def med(xs): return statistics.median(xs) if xs else None


_last = {}
def pace(key, gap=None):
    """Giữ khoảng cách tối thiểu giữa 2 lần gọi cùng model (quota ~10 RPM, dùng chung với agent khác)."""
    now = time.time()
    gap = gap if gap is not None else (3.0 if key.startswith("nova") else 12.0)
    w = _last.get(key, 0) + gap - now
    if w > 0: time.sleep(w)
    _last[key] = time.time()
