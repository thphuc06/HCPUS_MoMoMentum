"""Quét bí mật và thông tin không được lộ trong repo public (việc B2 của phase 6, issue #36). Thuần Python, chạy offline, không gọi
AWS, không cần cài thêm công cụ.

    uv run python scripts/scan_repo.py                  # cây làm việc: các tệp `git ls-files`, nội dung đang nằm trên đĩa
    uv run python scripts/scan_repo.py --ref p6/rc      # nội dung ĐÃ COMMIT của một commit (`git archive`); make_submission_zip dùng
    uv run python scripts/scan_repo.py --history        # mọi dòng được thêm trong lịch sử của HEAD (`git log -p`): chỉ báo cáo
    uv run python scripts/scan_repo.py --history --json # như trên, dạng JSON

Luật (`RULES`):

- `aws-account-id`: dãy đúng 12 chữ số trong ngữ cảnh AWS: ARN (cả dạng mã hóa URL `%3A`), khóa `account`/`accountId`/
  `CDK_DEFAULT_ACCOUNT`..., chữ "AWS" đứng ngay trước, host `*.amazonaws.com`/`*.aws.amazon.com`, đường dẫn `amazonaws.com/<id>/`,
  tên tài nguyên `<tên>-<id>-<Region>` (bucket bootstrap CDK), `s3://`. Dãy 12 chữ số trơn (số tiền, mã băm, UUID) không bị báo.
- `aws-access-key-id` (`AKIA`, `ASIA`, `ABIA`, `ACCA` + 16 ký tự), `aws-secret-access-key` (40 ký tự sau khóa `aws_secret...`),
  `private-key` (dòng mở đầu khóa riêng PEM), `token` (dạng có tiền tố của GitHub, GitLab, Slack, Google, Stripe, OpenAI, Anthropic,
  npm, PyPI, Hugging Face), `jwt`, `generic-secret` (khóa tên `*secret`, `*token`, `*api_key`... gán chuỗi có độ ngẫu nhiên cao).
- `password`: khóa tên `*password`/`*passwd`/`*pwd`/`mat_khau` gán một chuỗi; mật khẩu trong URL `scheme://user:<mật khẩu>@host`;
  trong tệp không phải mã nguồn thêm dạng chữ "Mật khẩu: ..." / "password: ...". Giá trị lấy từ biến (`{`, `$`, `<`, `%(`), chữ
  giữ chỗ (`...`, `***`, `password`, `changeme`) và tên biến môi trường không bị báo.
- `email`: địa chỉ thư, trừ miền dành cho ví dụ (RFC 2606/6761: `example.com/.net/.org` và miền con, đuôi `.example`, `.invalid`,
  `.test`, `.localhost`, như `demo.yofina.example`) và "đuôi" là phần mở rộng tệp (`icon@2x.png`).
- `phone`, `account-number`: CHỈ trong tệp dữ liệu và tài liệu (`DATA_EXTS`: json, jsonl, csv, txt, sql, yaml, md...; không phải mã
  nguồn hay tệp khóa phiên bản). `phone` là số điện thoại Việt Nam (di động `0[35789]` 10 số, cố định `02` 11 số, `+84`), nhận các cách tách nhóm
  thường gặp (`0973 518 246`, `097.351.8246`) nhưng không nhận ngày giờ hay số thập phân. `account-number` dùng hình dạng dãy số của
  `yofina_core.pii` (từ 8 chữ số, nhóm ngăn bằng MỘT dấu cách hoặc gạch, không dính chữ, không ngăn bằng dấu chấm) VÀ cần từ khóa tài
  khoản ngay trước (`STK`, `tài khoản`, `account`, `Debit-`...), vì dữ liệu mẫu đầy số tiền dài; bỏ dấu thời gian Unix
  (`yofina_core.pii.is_epoch_at`). Không dùng thẳng bộ bắt số điện thoại của `pii` (nó che dư có chủ ý, ví dụ ngày `05-11-2026 07`),
  vì bộ quét cần ít báo nhầm hơn bộ che.

Danh sách cho phép đọc từ `.gitleaks.toml` (một nguồn cho cả gitleaks của CI và script này; `--config` để chọn tệp khác):

- `[[allowlists]]` của gitleaks áp nguyên nghĩa (`targetRules`, `condition`, `paths`, `regexes`, `regexTarget`, `stopwords`,
  `commits`), luật gitleaks ánh xạ sang luật ở đây qua `GITLEAKS_RULES` (ví dụ `generic-api-key` -> `generic-secret`, `password`).
- `[[scan_repo.allow]]` cho các luật gitleaks không có (account ID, email, số điện thoại, số tài khoản): `description` (bắt buộc, lý
  do), `rules` (bắt buộc), ít nhất một trong `values` (giá trị đúng, so sau khi bỏ dấu ngăn với số; `+84` coi như `0`), `regexes`
  (tìm trên giá trị), `email_domains`; thêm `paths` (regex trên đường dẫn) để thu hẹp. Mục chỉ có `paths` bị từ chối (bỏ qua cả
  tệp là quá rộng). gitleaks bỏ qua khóa lạ nên bảng `scan_repo` không ảnh hưởng job `secrets`.

Mỗi mục, của gitleaks hay của script, phải có `description`. Với `--ref`, tệp cấu hình mặc định là `.gitleaks.toml` CỦA commit đó
(danh sách cho phép đi cùng nội dung được duyệt); chế độ khác đọc tệp trên đĩa. Repo không có tệp đó thì chỉ dùng luật dựng sẵn.

Mã thoát: 0 không có phát hiện (`--history` luôn 0: lịch sử không sửa được bằng một commit mới, chỉ báo cáo cho Q5 của phase 6),
1 có phát hiện, 2 lỗi cấu hình hoặc git. Script không bao giờ in nguyên giá trị: chỉ đường dẫn, dòng, luật, giá trị đã che (`mask`).
"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import subprocess
import sys
import tarfile
import tomllib
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[1]
CONFIG_NAME = ".gitleaks.toml"

try:
    from yofina_core import pii
except ImportError:  # chạy bằng python không có workspace uv: lấy thẳng mã nguồn trong repo
    sys.path.insert(0, str(REPO / "libs" / "yofina_core" / "src"))
    from yofina_core import pii

#: luật -> mô tả ngắn (in ra cuối báo cáo, và để kiểm `rules` của mục cho phép)
RULES: dict[str, str] = {
    "aws-account-id": "account ID AWS 12 chữ số trong ngữ cảnh AWS",
    "aws-access-key-id": "khóa truy cập AWS (AKIA/ASIA...)",
    "aws-secret-access-key": "secret access key AWS",
    "private-key": "khóa riêng PEM",
    "token": "token có tiền tố của dịch vụ (GitHub, Slack, Google...)",
    "jwt": "JWT",
    "generic-secret": "secret/token/khóa API gán cứng",
    "password": "mật khẩu gán cứng",
    "email": "email thật",
    "phone": "số điện thoại Việt Nam trong dữ liệu mẫu",
    "account-number": "số tài khoản trong dữ liệu mẫu",
}
#: luật gitleaks -> luật ở đây (để `[[allowlists]]` của `.gitleaks.toml` có hiệu lực với cùng loại phát hiện)
GITLEAKS_RULES: dict[str, tuple[str, ...]] = {
    "aws-access-token": ("aws-access-key-id",),
    "private-key": ("private-key",),
    "jwt": ("jwt",),
    "jwt-base64": ("jwt",),
    "generic-api-key": ("generic-secret", "password"),
    **{
        r: ("token",)
        for r in (
            "github-pat", "github-fine-grained-pat", "github-oauth", "github-app-token", "github-refresh-token",
            "gitlab-pat", "slack-bot-token", "slack-user-token", "slack-app-token", "slack-config-access-token",
            "slack-config-refresh-token", "slack-legacy-bot-token", "slack-legacy-workspace-token", "slack-legacy-token",
            "slack-webhook-url", "gcp-api-key", "stripe-access-token", "openai-api-key", "anthropic-api-key",
            "anthropic-admin-api-key", "npm-access-token", "pypi-upload-token", "huggingface-access-token",
        )
    },
}  # fmt: skip

#: phần mở rộng của tệp dữ liệu và tài liệu (luật `phone`, `account-number`); mã nguồn và test thì không: test của bộ che PII đầy số giả
DATA_EXTS = frozenset(
    {".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".txt", ".sql", ".yaml", ".yml", ".xml", ".md"}
)
#: tệp khóa phiên bản: đầy mã băm và số phiên bản, không phải dữ liệu mẫu
LOCK_NAMES = frozenset(
    {"package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "uv.lock"}
)
#: mã nguồn: không áp dạng chữ "password: ..." (trong mã, `password: str` là khai báo kiểu)
CODE_EXTS = frozenset(
    {".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".sh", ".ps1", ".psm1", ".bat", ".cmd", ".go", ".rs",
     ".java", ".kt", ".cs", ".rb", ".php", ".sql"}
)  # fmt: skip
#: không đọc: ảnh, PDF, nén, phông chữ (tệp nhị phân khác bị bỏ khi có byte NUL)
BINARY_EXTS = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tif", ".tiff", ".pdf", ".zip", ".gz", ".tgz", ".bz2",
     ".xz", ".7z", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp4", ".mov", ".webm", ".mp3", ".wav", ".parquet",
     ".pkl", ".npy", ".npz", ".onnx", ".bin", ".so", ".dll", ".exe", ".pyc"}
)  # fmt: skip
#: tệp lớn hơn thế này bị bỏ qua (không có tệp văn bản nào trong repo lớn tới vậy)
MAX_BYTES = 20_000_000


class ScanError(Exception):
    """Cấu hình sai hoặc git lỗi; `main` in thông điệp và trả mã thoát 2."""


@dataclass(frozen=True)
class Finding:
    """Một phát hiện. Không giữ nguyên giá trị: chỉ bản đã che."""

    rule: str
    path: str
    line: int
    masked: str
    commit: str | None = None


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    allowed: int = 0  # số phát hiện bị bỏ theo danh sách cho phép trong cấu hình
    files: int = 0  # số tệp đã đọc (chế độ lịch sử: số commit)


@dataclass(frozen=True)
class Hit:
    """Kết quả nội bộ của một luật trên một dòng (có giá trị thật, không bao giờ in ra)."""

    rule: str
    start: int
    end: int
    value: str
    match: str


# ======================================================================================================================
# Che giá trị
# ======================================================================================================================


def mask(value: str, rule: str | None = None) -> str:
    """Che một giá trị trước khi in: email giữ chữ đầu và miền (`n***@gmail.com`); chuỗi từ 12 ký tự giữ 2 đầu 2 cuối, từ 8 ký tự
    giữ 1 đầu 1 cuối, ngắn hơn thì che hết."""
    if rule == "email" and "@" in value:
        local, _, domain = value.rpartition("@")
        return f"{local[:1]}***@{domain}"
    n = len(value)
    keep = 2 if n >= 12 else 1 if n >= 8 else 0
    if not keep:
        return "*" * n
    return value[:keep] + "*" * (n - 2 * keep) + value[-keep:]


# ======================================================================================================================
# Luật
# ======================================================================================================================

_SEP = r"(?::|%3[Aa])"  # dấu ':' của ARN, cả dạng mã hóa URL
_ACCOUNT_ID_RES = (
    # arn:aws:iam::<id>:role/x, arn%3Aaws%3Abedrock-agentcore%3A<region>%3A<id>%3Aruntime
    re.compile(rf"\barn{_SEP}aws[a-z-]*{_SEP}[\w.-]*{_SEP}[\w-]*{_SEP}(\d{{12}})(?!\d)", re.I),
    # account: '<id>', CDK_DEFAULT_ACCOUNT=<id>, "AccountId": "<id>", Account ID <id> (không nhận ACCOUNT_LIMIT = <số>)
    re.compile(
        r"(?<![\w])[\w-]*?account(?:[ _-]?id)?[\"'\]]?\s*(?:[:=]|=>)?\s*[\"'`]?(\d{12})(?![\w])",
        re.I,
    ),
    # tài khoản AWS: <id>, AWS account <id>
    re.compile(r"\baws\b[^\d\n]{0,30}?(?<![\w])(\d{12})(?![\w])", re.I),
    # <id>.dkr.ecr.<region>.amazonaws.com, bucket-<id>.s3.<region>.amazonaws.com, <id>.signin.aws.amazon.com
    re.compile(
        r"(?<![\w.-])(?:[\w-]*-)?(\d{12})(?:-[\w-]*)?(?:\.[\w-]+)*\.(?:amazonaws\.com(?:\.cn)?|amazon\.com)(?![\w-])",
        re.I,
    ),
    # https://sqs.<region>.amazonaws.com/<id>/queue
    re.compile(r"amazonaws\.com(?:\.cn)?/(\d{12})(?![\w])", re.I),
    # cdk-hnb659fds-assets-<id>-ap-southeast-1, tên-<id>-<region>
    re.compile(
        r"(?<![\w])[\w.-]*?-(\d{12})-(?:us|eu|ap|sa|ca|me|af|il|mx|cn)(?:-gov)?-[a-z]+-\d(?![\w])",
        re.I,
    ),
    # s3://bucket-<id>/...
    re.compile(r"\bs3://[\w.-]*?(?<!\d)(\d{12})(?!\d)", re.I),
)

_ACCESS_KEY_RE = re.compile(r"(?<![A-Za-z0-9])((?:AKIA|ASIA|ABIA|ACCA)[A-Z0-9]{16})(?![A-Za-z0-9])")
_AWS_SECRET_RE = re.compile(
    r"(?:aws_?secret(?:_?access)?(?:_?key)?|secret_?access_?key)[\"'\]]?\s*(?::=|=>|[:=])\s*[\"'`]?([A-Za-z0-9/+]{40})(?![A-Za-z0-9/+=])",
    re.I,
)
_PEM_RE = re.compile("-" * 5 + r"BEGIN[ A-Z0-9]*PRIVATE KEY(?: BLOCK)?" + "-" * 5)
_TOKEN_RES = tuple(
    re.compile(p)
    for p in (
        r"(?<![\w])gh[pousr]_[A-Za-z0-9]{36,255}(?![\w])",
        r"(?<![\w])github_pat_[A-Za-z0-9_]{82}(?![\w])",
        r"(?<![\w-])glpat-[A-Za-z0-9_-]{20}(?![\w-])",
        r"(?<![\w-])xox[abposre]-[0-9A-Za-z-]{10,}(?![\w-])",
        r"hooks\.slack\.com/services/T[A-Z0-9]{6,}/B[A-Z0-9]{6,}/[A-Za-z0-9]{16,}",
        r"(?<![\w-])AIza[0-9A-Za-z_-]{35}(?![\w-])",
        r"(?<![\w])(?:sk|rk)_live_[0-9A-Za-z]{24,}(?![\w])",
        r"(?<![\w-])sk-ant-[A-Za-z0-9_-]{32,}(?![\w-])",
        r"(?<![\w-])sk-proj-[A-Za-z0-9_-]{32,}(?![\w-])",
        r"(?<![\w-])sk-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}(?![\w-])",
        r"(?<![\w])npm_[A-Za-z0-9]{36}(?![\w])",
        r"(?<![\w-])pypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{50,}(?![\w-])",
        r"(?<![\w])hf_[A-Za-z0-9]{34}(?![\w])",
    )
)
_JWT_RE = re.compile(
    r"(?<![\w-])eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?![\w-])"
)

# Gán: khóa, dấu gán (không phải so sánh ==, !=, <=, >=), tiền tố chuỗi Python tùy chọn, rồi một chuỗi trong nháy.
_ASSIGN = (
    r"[\"'\]]?\s*(?::=|=>|(?<![=!<>])=(?!=)|:)\s*(?:[rbuRBU]{1,2}(?=[\"'`]))?([\"'`])(.*?)(?<!\\)\1"
)
_GENERIC_KEYS = (
    r"secret|token|api[_-]?key|apikey|access[_-]?key|auth[_-]?key|signing[_-]?key|private[_-]?key|credentials?"
    r"|hmac[_-]?key|encryption[_-]?key|session[_-]?key"
)
_GENERIC_RE = re.compile(rf"(?<![\w.-])[\w.-]*?(?:{_GENERIC_KEYS}){_ASSIGN}", re.I)
_GENERIC_BARE_RE = re.compile(  # KEY=giá-trị không nháy, cả dòng (env, ini, yaml)
    rf"^\s*(?:export\s+)?[\w.-]*?(?:{_GENERIC_KEYS})\s*[:=]\s*([^\s\"'`#]+)\s*$", re.I
)
_PW_KEYS = r"password|passwd|passphrase|pass_?word|pwd|mat_?khau"
_PW_ASSIGN_RE = re.compile(rf"(?<![\w.-])[\w.-]*?(?:{_PW_KEYS}){_ASSIGN}", re.I)
_PW_URL_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@\"'`]+:([^\s/@\"'`]+)@[\w.\[\]-]", re.I)
_PW_TEXT_RE = re.compile(
    r"(?<![\w])(?:m(?:ật|ât|ạt|at)\s+kh(?:ẩu|âu|au)|password|passwd|pwd)\s*(?:\(\w+\)\s*)?(?:là|la|:|=)\s*[`\"']?([^\s`\"',;)]{6,})",
    re.I,
)
#: giá trị giữ chỗ, không phải mật khẩu/secret (so chữ thường)
_PLACEHOLDERS = frozenset(
    {"password", "passwd", "pass", "secret", "token", "changeme", "change-me", "redacted", "hidden", "none", "null",
     "string", "str", "example", "your-password", "your_password", "yourpassword", "mypassword", "placeholder", "todo",
     "xxx", "dummy", "test", "admin"}
)  # fmt: skip
_ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]*")
_CONCAT_AFTER = re.compile(r"\s*(?:\+|\.\s*(?:format|join)\b)")
_DYNAMIC = ("{", "}", "$", "<", ">", "%(", "%s", "\\(")

_EMAIL_RE = re.compile(
    r"(?<![\w.%+-])([A-Za-z0-9][A-Za-z0-9._%+-]*)@((?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,})(?![\w-])"
)
_EXAMPLE_DOMAINS = ("example.com", "example.net", "example.org")
#: phần userinfo của URL (`ssh://git@host`, `postgres://user:pass@host`), không phải địa chỉ thư
_URL_USERINFO = re.compile(r"://(?:[^\s/@:]*:)?$")
_RESERVED_TLDS = frozenset({"example", "invalid", "test", "localhost"})
_FILE_TLDS = frozenset(
    {"png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "js", "mjs", "ts", "tsx", "jsx", "css", "json", "py", "md", "txt",
     "pdf", "csv", "html", "map", "zip"}
)  # fmt: skip

# Số điện thoại Việt Nam. Sau đầu số (0, +84): di động 9 số đầu [35789] viết liền, 3-3-3 hoặc 2-3-4; cố định 10 số đầu 2.
_PHONE_RE = re.compile(
    r"(?<![\w.+/])(?:\+84[ .-]?|\(\+84\)[ ]?|0)"
    r"(?:[35789]\d(?:\d{7}|\d([ .-])\d{3}\1\d{3}|([ .-])\d{3}\2\d{4})"
    r"|2\d(?:\d{8}|([ .-])\d{4}\3\d{4}|\d([ .-])\d{3,4}\4\d{4}))"
    r"(?!\w)(?!\.\d)"
)
# Hình dạng số tài khoản của yofina_core.pii (_DIGIT_RUN), nâng sàn lên 8 chữ số.
_ACCOUNT_RUN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?<![A-Za-z0-9][./:])\d(?:[ \-]?\d){7,}(?![A-Za-z0-9])(?![./:][A-Za-z0-9])"
)
#: từ khóa tài khoản ngay trước dãy số (so trên chữ đã bỏ dấu, chữ thường)
_ACCOUNT_LEAD = re.compile(
    r"(?:\b(?:stk|so tk|tk|so tai khoan|tai khoan|account(?:[ _-]?(?:no|number|id))?|acct|acc[ _-]?no|a/c|debit|credit|"
    r"so the)|[\w]+_(?:account|acct|stk))\b[\W_]{0,4}$"
)
#: ... trừ khi đó là số dư, hạn mức, số tiền của tài khoản
_AMOUNT_LEAD = re.compile(r"\b(?:so du|balance|han muc|limit|amount|so tien)\b")


def _entropy(s: str) -> float:
    counts = Counter(s)
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in counts.values())


def _dynamic(value: str) -> bool:
    return any(t in value for t in _DYNAMIC)


def _placeholder(value: str) -> bool:
    v = value.strip().lower()
    return (
        not v
        or v in _PLACEHOLDERS
        or set(v) <= set(".*x-_#•?")
        or v.startswith(("your", "<", "["))
        or "example" in v
    )


def _password_value(value: str) -> bool:
    """Chuỗi có thể là mật khẩu: không lấy từ biến, không phải chữ giữ chỗ hay tên biến môi trường, không có khoảng trắng (chuỗi có
    khoảng trắng là nhãn giao diện, câu mô tả)."""
    return not (
        _dynamic(value)
        or _placeholder(value)
        or _ENV_NAME.fullmatch(value)
        or len(value) < 4
        or any(c.isspace() for c in value)
    )


def _secret_value(value: str) -> bool:
    """Chuỗi giống một secret thật: từ 16 ký tự, có cả chữ và số, độ ngẫu nhiên Shannon từ 3,5 bit/ký tự, không phải biểu thức,
    đường dẫn, URL hay tên định danh viết hoa."""
    return (
        len(value) >= 16
        and not _dynamic(value)
        and not _placeholder(value)
        and not any(c.isspace() for c in value)
        and "://" not in value
        and not _ENV_NAME.fullmatch(value)
        and any(c.isdigit() for c in value)
        and any(c.isalpha() for c in value)
        and _entropy(value) >= 3.5
    )


def _email_allowed(domain: str) -> bool:
    d = domain.lower()
    tld = d.rsplit(".", 1)[-1]
    return (
        tld in _RESERVED_TLDS
        or tld in _FILE_TLDS
        or any(d == e or d.endswith("." + e) for e in _EXAMPLE_DOMAINS)
    )


def _is_data_file(path: str) -> bool:
    p = PurePosixPath(path)
    return p.suffix.lower() in DATA_EXTS and p.name not in LOCK_NAMES


def _is_code_file(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in CODE_EXTS


def _hits(line: str, *, data: bool, code: bool) -> list[Hit]:
    """Mọi phát hiện trên một dòng, luật riêng trước luật chung; vùng giá trị đã bị một luật bắt thì luật sau không bắt lại."""
    out: list[Hit] = []

    def add(rule: str, m: re.Match[str], group: int = 0) -> None:
        s, e = m.span(group)
        if any(s < h.end and h.start < e for h in out):
            return
        out.append(Hit(rule, s, e, m.group(group), m.group(0)))

    if "PRIVATE KEY" in line:
        for m in _PEM_RE.finditer(line):
            add("private-key", m)
    for m in _ACCESS_KEY_RE.finditer(line):
        if not m.group(1).endswith("EXAMPLE"):  # khóa ví dụ trong tài liệu AWS
            add("aws-access-key-id", m, 1)
    for m in _AWS_SECRET_RE.finditer(line):
        if "EXAMPLE" not in m.group(1):
            add("aws-secret-access-key", m, 1)
    for rx in _TOKEN_RES:
        for m in rx.finditer(line):
            add("token", m)
    if "eyJ" in line:
        for m in _JWT_RE.finditer(line):
            add("jwt", m)
    for rx in _ACCOUNT_ID_RES:
        for m in rx.finditer(line):
            add("aws-account-id", m, 1)
    for m in _PW_URL_RE.finditer(line):  # trước email: "user:mật-khẩu@host" không phải địa chỉ thư
        if _password_value(m.group(1)):
            add("password", m, 1)
    if "@" in line:
        for m in _EMAIL_RE.finditer(line):
            if not _email_allowed(m.group(2)) and not _URL_USERINFO.search(line, 0, m.start()):
                add("email", m)
    for m in _PW_ASSIGN_RE.finditer(line):
        # chuỗi nối thêm phần sinh lúc chạy ("Aa1!" + secrets.token_urlsafe(18)) không phải mật khẩu gán cứng
        if _password_value(m.group(2)) and not _CONCAT_AFTER.match(line, m.end()):
            add("password", m, 2)
    if not code:
        for m in _PW_TEXT_RE.finditer(line):
            v = m.group(1)
            if (
                _password_value(v)
                and any(c.isalpha() for c in v)
                and any(not c.isalpha() for c in v)
            ):
                add("password", m, 1)
    for m in _GENERIC_RE.finditer(line):
        if _secret_value(m.group(2)):
            add("generic-secret", m, 2)
    if not code:
        m = _GENERIC_BARE_RE.match(line)
        if m and _secret_value(m.group(1)):
            add("generic-secret", m, 1)
    if data:
        for m in _PHONE_RE.finditer(line):
            add("phone", m)
        for m in _ACCOUNT_RUN_RE.finditer(line):
            if pii.is_epoch_at(line, m.start(), m.end()):
                continue
            before = pii.fold(line[max(0, m.start() - 40) : m.start()]) + (
                " " if line[max(0, m.start() - 1) : m.start()].isspace() else ""
            )
            if _ACCOUNT_LEAD.search(before) and not _AMOUNT_LEAD.search(before[-25:]):
                add("account-number", m)
    return out


# ======================================================================================================================
# Danh sách cho phép
# ======================================================================================================================


def _norm(rule: str, value: str) -> str:
    if rule in {"phone", "account-number", "aws-account-id"}:
        digits = re.sub(r"\D", "", value)
        if rule == "phone" and value.lstrip("(").startswith("+84"):
            digits = "0" + digits[2:]
        return digits
    if rule == "email":
        return value.lower()
    return value


@dataclass(frozen=True)
class Allow:
    """Một mục cho phép. `source` là `scan_repo` (bảng `[[scan_repo.allow]]`) hoặc `gitleaks` (`[[allowlists]]`)."""

    description: str
    source: str
    rules: frozenset[str] | None  # None: mọi luật
    values: tuple[str, ...] = ()
    regexes: tuple[re.Pattern[str], ...] = ()
    email_domains: frozenset[str] = frozenset()
    paths: tuple[re.Pattern[str], ...] = ()
    regex_target: str = "secret"
    stopwords: tuple[str, ...] = ()
    commits: frozenset[str] = frozenset()
    condition: str = "OR"

    def matches(self, hit: Hit, path: str, line: str, commit: str | None) -> bool:
        if self.rules is not None and hit.rule not in self.rules:
            return False
        if self.source == "scan_repo":
            value_ok = (
                _norm(hit.rule, hit.value) in {_norm(hit.rule, v) for v in self.values}
                or any(r.search(hit.value) for r in self.regexes)
                or (
                    hit.rule == "email"
                    and hit.value.rpartition("@")[2].lower() in self.email_domains
                )
            )
            return value_ok and (not self.paths or any(r.search(path) for r in self.paths))
        # gitleaks: mỗi tiêu chí khai thì phải khớp (AND) hoặc chỉ cần một tiêu chí khớp (OR)
        target = {"secret": hit.value, "match": hit.match, "line": line}.get(
            self.regex_target, hit.value
        )
        checks: list[bool] = []
        if self.commits:
            checks.append(commit is not None and any(commit.startswith(c) for c in self.commits))
        if self.paths:
            checks.append(any(r.search(path) for r in self.paths))
        if self.regexes:
            checks.append(any(r.search(target) for r in self.regexes))
        if self.stopwords:
            checks.append(any(w in hit.value.lower() for w in self.stopwords))
        if not checks:
            return False
        return all(checks) if self.condition == "AND" else any(checks)


@dataclass(frozen=True)
class Config:
    allow: tuple[Allow, ...] = ()
    origin: str | None = None

    def allowed(self, hit: Hit, path: str, line: str, commit: str | None = None) -> bool:
        if path == CONFIG_NAME and self._declared(hit):
            return True  # chính tệp danh sách cho phép phải ghi giá trị nó cho phép
        return any(a.matches(hit, path, line, commit) for a in self.allow)

    def _declared(self, hit: Hit) -> bool:
        value = _norm(hit.rule, hit.value)
        return any(
            a.source == "scan_repo"
            and a.rules is not None
            and hit.rule in a.rules
            and value in {_norm(hit.rule, v) for v in a.values}
            for a in self.allow
        )


_SCAN_REPO_FIELDS = frozenset(
    {"description", "rules", "values", "regexes", "email_domains", "paths"}
)


def _str_list(entry: dict, key: str, where: str) -> list[str]:
    raw = entry.get(key, [])
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        raise ScanError(f"{where}: `{key}` phải là danh sách chuỗi")
    return raw


def _compile(patterns: Iterable[str], where: str) -> tuple[re.Pattern[str], ...]:
    out = []
    for p in patterns:
        try:
            out.append(re.compile(p))
        except re.error as exc:
            raise ScanError(f"{where}: regex sai {p!r}: {exc}") from exc
    return tuple(out)


def _description(entry: dict, where: str) -> str:
    desc = entry.get("description")
    if not isinstance(desc, str) or not desc.strip():
        raise ScanError(f"{where}: thiếu `description` (lý do cho phép)")
    return desc.strip()


def _scan_repo_allow(entry: dict, where: str) -> Allow:
    if not isinstance(entry, dict):
        raise ScanError(f"{where}: mỗi mục phải là một bảng")
    unknown = set(entry) - _SCAN_REPO_FIELDS
    if unknown:
        raise ScanError(f"{where}: khóa lạ {sorted(unknown)}")
    desc = _description(entry, where)
    rules = _str_list(entry, "rules", where)
    if not rules:
        raise ScanError(f"{where}: thiếu `rules`")
    bad = sorted(set(rules) - set(RULES))
    if bad:
        raise ScanError(f"{where}: luật không tồn tại {bad}; có: {', '.join(RULES)}")
    values = _str_list(entry, "values", where)
    regexes = _str_list(entry, "regexes", where)
    domains = _str_list(entry, "email_domains", where)
    if not (values or regexes or domains):
        raise ScanError(
            f"{where}: cần ít nhất một trong `values`, `regexes`, `email_domains` (chỉ `paths` là bỏ qua cả tệp, không cho)"
        )
    return Allow(
        description=desc,
        source="scan_repo",
        rules=frozenset(rules),
        values=tuple(values),
        regexes=_compile(regexes, where),
        email_domains=frozenset(d.lower() for d in domains),
        paths=_compile(_str_list(entry, "paths", where), where),
    )


def _gitleaks_allow(entry: dict, where: str) -> Allow:
    if not isinstance(entry, dict):
        raise ScanError(f"{where}: mỗi mục phải là một bảng")
    desc = _description(entry, where)
    targets = _str_list(entry, "targetRules", where)
    rules: frozenset[str] | None = None
    if targets:
        rules = frozenset(r for t in targets for r in GITLEAKS_RULES.get(t, ()))
    condition = str(entry.get("condition", "OR")).upper()
    if condition not in {"OR", "AND"}:
        raise ScanError(f"{where}: `condition` phải là OR hoặc AND")
    target = str(entry.get("regexTarget", "secret"))
    if target not in {"secret", "match", "line"}:
        raise ScanError(f"{where}: `regexTarget` phải là secret, match hoặc line")
    return Allow(
        description=desc,
        source="gitleaks",
        rules=rules,
        regexes=_compile(_str_list(entry, "regexes", where), where),
        paths=_compile(_str_list(entry, "paths", where), where),
        regex_target=target,
        stopwords=tuple(w.lower() for w in _str_list(entry, "stopwords", where)),
        commits=frozenset(_str_list(entry, "commits", where)),
        condition=condition,
    )


def parse_config(text: str, origin: str) -> Config:
    """Đọc danh sách cho phép từ nội dung TOML (định dạng `.gitleaks.toml`, xem docstring module)."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ScanError(f"{origin}: TOML sai: {exc}") from exc
    allow: list[Allow] = []
    legacy = data.get("allowlist")
    if isinstance(legacy, dict):
        allow.append(_gitleaks_allow(legacy, f"{origin} [allowlist]"))
    for i, entry in enumerate(data.get("allowlists", []) or []):
        allow.append(_gitleaks_allow(entry, f"{origin} [[allowlists]] #{i + 1}"))
    own = data.get("scan_repo", {})
    if not isinstance(own, dict) or set(own) - {"allow"}:
        raise ScanError(f"{origin}: bảng `scan_repo` chỉ có `allow`")
    for i, entry in enumerate(own.get("allow", []) or []):
        allow.append(_scan_repo_allow(entry, f"{origin} [[scan_repo.allow]] #{i + 1}"))
    return Config(tuple(allow), origin)


def load_config(path: Path | None) -> Config:
    """`None`: chỉ luật dựng sẵn, không có danh sách cho phép. Tệp không tồn tại: `ScanError`."""
    if path is None:
        return Config()
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ScanError(f"Không đọc được tệp cấu hình {path}: {exc}") from exc
    return parse_config(text, str(path))


# ======================================================================================================================
# Quét
# ======================================================================================================================


def _decode(data: bytes) -> str | None:
    if len(data) > MAX_BYTES or b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def _scan_lines(
    path: str,
    lines: Iterable[tuple[int, str]],
    cfg: Config,
    res: ScanResult,
    commit: str | None = None,
) -> None:
    data, code = _is_data_file(path), _is_code_file(path)
    for no, line in lines:
        for hit in _hits(line, data=data, code=code):
            if cfg.allowed(hit, path, line, commit):
                res.allowed += 1
                continue
            res.findings.append(Finding(hit.rule, path, no, mask(hit.value, hit.rule), commit))


def _scan_blob(path: str, data: bytes, cfg: Config, res: ScanResult) -> None:
    if PurePosixPath(path).suffix.lower() in BINARY_EXTS:
        return
    text = _decode(data)
    if text is None:
        return
    res.files += 1
    _scan_lines(path, enumerate(text.splitlines(), start=1), cfg, res)


def scan_files(root: Path, rel_paths: Iterable[str], cfg: Config) -> ScanResult:
    """Quét các tệp `rel_paths` (đường dẫn POSIX tính từ `root`) đang nằm trên đĩa; tệp đã xóa thì bỏ qua."""
    res = ScanResult()
    for rel in rel_paths:
        p = Path(root) / rel
        if not p.is_file() or p.is_symlink():
            continue
        if p.stat().st_size > MAX_BYTES:
            continue
        _scan_blob(rel, p.read_bytes(), cfg, res)
    return res


def _git(root: Path, *args: str) -> bytes:
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args], cwd=root, capture_output=True
        )
    except OSError as exc:
        raise ScanError(f"Không chạy được git: {exc}") from exc
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", "replace").strip()
        raise ScanError(f"git {' '.join(args[:2])} lỗi: {msg}")
    return proc.stdout


def _toplevel(repo: Path) -> Path:
    return Path(_git(Path(repo), "rev-parse", "--show-toplevel").decode("utf-8").strip()).resolve()


def _commit(root: Path, ref: str) -> str:
    return (
        _git(root, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
        .decode("ascii")
        .strip()
    )


def scan_worktree(repo: Path, cfg: Config) -> ScanResult:
    """Quét các tệp git theo dõi (`git ls-files`), lấy nội dung trên đĩa (gồm cả sửa chưa commit); tệp chưa theo dõi bị bỏ."""
    root = _toplevel(repo)
    rels = [r for r in _git(root, "ls-files", "-z").decode("utf-8").split("\0") if r]
    return scan_files(root, rels, cfg)


def scan_ref(repo: Path, ref: str, cfg: Config) -> ScanResult:
    """Quét nội dung đã commit của `ref` qua `git archive` (đúng những gì make_submission_zip nén)."""
    root = _toplevel(repo)
    commit = _commit(root, ref)
    tar_bytes = _git(root, "-c", "core.autocrlf=false", "archive", "--format=tar", commit)
    res = ScanResult()
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as tar:
        for member in tar:
            if not member.isfile() or member.size > MAX_BYTES:
                continue
            f = tar.extractfile(member)
            if f is not None:
                _scan_blob(member.name, f.read(), cfg, res)
    return res


def _read_ref_config(root: Path, commit: str) -> Config:
    proc = subprocess.run(["git", "show", f"{commit}:{CONFIG_NAME}"], cwd=root, capture_output=True)
    if proc.returncode != 0:
        return Config()  # commit không có tệp cấu hình
    return parse_config(proc.stdout.decode("utf-8"), f"{commit[:12]}:{CONFIG_NAME}")


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _unquote(path: str) -> str:
    """Đường dẫn trong `git diff` có ký tự lạ thì nằm trong nháy kép với thoát kiểu C."""
    if len(path) >= 2 and path[0] == path[-1] == '"':
        raw = path[1:-1].encode("latin-1", "backslashreplace").decode("unicode_escape")
        return raw.encode("latin-1", "replace").decode("utf-8", "replace")
    return path


def _added_lines(root: Path, ref: str) -> Iterator[tuple[str, str, int, str]]:
    """(commit, đường dẫn, số dòng mới, nội dung) cho mọi dòng được thêm trong lịch sử của `ref`. Commit gộp không có diff riêng
    (nội dung đến từ commit cha, đã được quét)."""
    cmd = [
        "git", "-c", "core.quotepath=false", "log", "-p", "-U0", "--full-history", "--find-renames", "--no-color",
        "--no-ext-diff", "--no-textconv", "--format=%x00%H", ref, "--",
    ]  # fmt: skip
    try:
        proc = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        raise ScanError(f"Không chạy được git: {exc}") from exc
    assert proc.stdout is not None
    commit = ""
    path: str | None = None
    line_no = 0
    for raw in proc.stdout:
        text = raw.decode("utf-8", errors="replace").rstrip("\n").rstrip("\r")
        if text.startswith("\0"):
            commit, path = text[1:].strip(), None
        elif text.startswith("diff --git "):
            path = None
        elif text.startswith("+++ "):
            target = text[4:]
            path = None if target == "/dev/null" else _unquote(target)
            if path and path.startswith(("b/", '"b/')):
                path = path[2:]
        elif text.startswith("@@"):
            m = _HUNK.match(text)
            line_no = int(m.group(1)) if m else 0
        elif text.startswith("+") and path is not None:
            yield commit, path, line_no, text[1:]
            line_no += 1
    proc.stdout.close()
    err = proc.stderr.read().decode("utf-8", "replace").strip() if proc.stderr else ""
    if proc.wait() != 0:
        raise ScanError(f"git log lỗi: {err}")


def scan_history(repo: Path, cfg: Config, ref: str = "HEAD") -> ScanResult:
    """Mọi dòng được thêm trong lịch sử của `ref` (mặc định HEAD, như job `secrets` của CI). Mỗi phát hiện ghi commit đã thêm dòng
    đó và số dòng trong tệp ở commit ấy. Chỉ báo cáo."""
    root = _toplevel(repo)
    _commit(root, ref)
    res = ScanResult()
    commits: set[str] = set()
    for commit, path, no, line in _added_lines(root, ref):
        commits.add(commit)
        suffix = PurePosixPath(path).suffix.lower()
        if suffix in BINARY_EXTS:
            continue
        _scan_lines(path, [(no, line)], cfg, res, commit)
    res.files = len(commits)
    return res


# ======================================================================================================================
# Dòng lệnh
# ======================================================================================================================


def _summary(findings: Sequence[Finding]) -> dict[str, int]:
    return dict(sorted(Counter(f.rule for f in findings).items()))


def _print_text(mode: str, res: ScanResult, ref: str | None) -> None:
    for f in res.findings:
        where = f"{f.commit[:10]} " if f.commit else ""
        print(f"{where}{f.path}:{f.line}: {f.rule}: {f.masked}")
    what = {
        "worktree": "tệp (cây làm việc)",
        "ref": f"tệp ở {ref}",
        "history": "commit có dòng thêm",
    }[mode]
    counts = ", ".join(f"{k} {v}" for k, v in _summary(res.findings).items()) or "không có"
    print(
        f"{len(res.findings)} phát hiện ({counts}) trong {res.files} {what}; "
        f"{res.allowed} bỏ qua theo danh sách cho phép."
    )


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument(
        "--ref",
        default=None,
        help="quét nội dung đã commit của commit/nhánh/tag này thay cho cây làm việc",
    )
    ap.add_argument(
        "--history",
        action="store_true",
        help="liệt kê phát hiện trong mọi dòng được thêm ở lịch sử của HEAD (hoặc --ref)",
    )
    ap.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    ap.add_argument(
        "--config",
        type=Path,
        default=None,
        help=f"tệp danh sách cho phép (mặc định {CONFIG_NAME} ở gốc repo; với --ref là tệp của commit đó)",
    )
    ap.add_argument(
        "--repo", type=Path, default=REPO, help="repo cần quét (mặc định repo chứa script)"
    )
    args = ap.parse_args(argv)

    mode = "history" if args.history else "ref" if args.ref else "worktree"
    try:
        root = _toplevel(args.repo)
        commit = _commit(root, args.ref) if args.ref else None
        if args.config is not None:
            cfg = load_config(args.config)
        elif mode == "ref":
            cfg = _read_ref_config(root, commit or "HEAD")
        else:
            default = root / CONFIG_NAME
            cfg = load_config(default) if default.is_file() else Config()
        if mode == "history":
            res = scan_history(root, cfg, args.ref or "HEAD")
        elif mode == "ref":
            res = scan_ref(root, commit or "HEAD", cfg)
        else:
            res = scan_worktree(root, cfg)
    except ScanError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2

    if args.json:
        out = {
            "mode": mode,
            "ref": commit,
            "config": cfg.origin,
            "files" if mode != "history" else "commits": res.files,
            "allowed": res.allowed,
            "summary": _summary(res.findings),
            "findings": [
                {k: v for k, v in asdict(f).items() if v is not None} for f in res.findings
            ],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        _print_text(mode, res, args.ref)
    if mode == "history":
        return 0
    return 1 if res.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
