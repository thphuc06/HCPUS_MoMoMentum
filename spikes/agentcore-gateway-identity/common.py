"""Helper dùng chung cho spike. Không chứa secret/account ID; ARN dựng lúc chạy."""
import json, pathlib, datetime, boto3

REGION = "ap-southeast-1"
PREFIX = "yofina-spike-gw-"
TAGS = {"project": "yofina-spike"}
HERE = pathlib.Path(__file__).parent
STATE = HERE / "state.json"          # chỉ chứa tên/ID tài nguyên (không secret, không account ID)
MANIFEST = HERE / "RESOURCES.md"

sess = boto3.Session(region_name=REGION)


def client(name):
    return sess.client(name, region_name=REGION)


_account = None


def account():
    global _account
    if _account is None:
        _account = client("sts").get_caller_identity()["Account"]
    return _account


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_state(**kw):
    s = load_state()
    s.update(kw)
    STATE.write_text(json.dumps(s, indent=2))
    return s


def record(kind, name, delete_cmd):
    """Ghi NGAY vào manifest khi vừa tạo tài nguyên."""
    if not MANIFEST.exists():
        MANIFEST.write_text(
            "# RESOURCES - tài nguyên AWS tạo bởi spike agentcore-gateway-identity\n\n"
            f"Region: `{REGION}`. Tiền tố `{PREFIX}`, tag `project=yofina-spike`. "
            "Không có account ID/secret/token trong file này.\n\n"
            "| Thời điểm (UTC) | Loại | Tên / ID | Lệnh xóa |\n|---|---|---|---|\n",
            encoding="utf-8")
    ts = datetime.datetime.now(datetime.UTC).strftime("%H:%M:%S")
    with MANIFEST.open("a", encoding="utf-8") as f:
        f.write(f"| {ts} | {kind} | `{name}` | `{delete_cmd}` |\n")


def tag_list():
    return [{"Key": k, "Value": v} for k, v in TAGS.items()]
