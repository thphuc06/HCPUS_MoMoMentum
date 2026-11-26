"""Bộ quét bí mật và thông tin không được lộ trong repo public (B2 phase 6, issue #36): `scripts/scan_repo.py`.

Mỗi loại mẫu có ca phát hiện đúng và ca không được báo nhầm, chạy trên tệp giả trong `tmp_path`. Giá trị giả trong test này được
GHÉP LÚC CHẠY (`_j(...)`) để chính tệp test không khớp mẫu của bộ quét hay gitleaks (job `secrets` của CI quét cả tệp này).
Test chế độ `--ref`, `--history` và bộ quét mặc định của `make_submission_zip.py` dựng repo git tạm (cần `git` trên PATH, như CI).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def tool():
    mod = _load("scan_repo")
    yield mod
    sys.modules.pop("scan_repo", None)


@pytest.fixture(scope="module")
def zipper():
    mod = _load("make_submission_zip")
    yield mod
    sys.modules.pop("make_submission_zip", None)


def _j(*parts: str) -> str:
    return "".join(parts)


# Giá trị giả, ghép lúc chạy. Không cái nào là thật.
ACCT = _j("5309", "1742", "8861")  # account ID AWS giả 12 chữ số
AKIA = _j("AK", "IA", "Q7ZK", "M2XW", "R4TB", "N6PJ")
ASIA = _j("AS", "IA", "Y3LD", "H5VC", "W2QS", "K7MF")
AWS_DOC_KEY = _j("AK", "IA", "IOSF", "ODNN", "7EXA", "MPLE")  # khóa ví dụ trong tài liệu AWS
SECRET40 = _j("Zr8Kq2", "Lw9Px4", "Tn7Vb1", "Hs6Mc3", "Jd5Gf0", "Ya2Ue8", "Xi4o")
PEM = _j("-----BEGIN ", "RSA PRIVATE", " KEY-----")
GH_TOKEN = _j("gh", "p_", "A1b2C3d4E5" * 3, "F6g7H8")
SLACK = _j("xo", "xb-", "2840", "1937", "5521", "-", "Qm7Rt2Lx9Kw4Zp8N")
JWT = _j("ey", "JhbGciOiJIUzI1NiJ9", ".", "ey", "JzdWIiOiJ1LTk4NzYifQ", ".", "Qm7Rt2Lx9Kw4Zp8Nv3Hy")
GENERIC = _j("Zr8Kq2Lw", "9Px4Tn7V", "b1Hs6Mc3")
PW = _j("Xk9#", "mQ2v", "L7r")
PW_URL = _j("Xk9", "mQ2v", "L7r")
EMAIL = _j("nguyen.van.an", "@", "gmail", ".com")
PHONE = _j("0973", " 518", " 246")
PHONE_INTL = _j("+84", " 973", " 518", " 246")
ACC_NO = _j("0071", "0004", "56789")
DEBIT_ACC = _j("4071", "2953")
SOURCE_ACC = _j("2049", "3715", "86")
CDK_FAKE = "1" * 12
HASH = "a" + ACCT + "f" * 51  # sha256 hex có đoạn 12 chữ số liền
AMOUNT12 = "120" + "0" * 9  # số tiền 12 chữ số


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")


def _scan(tool, root: Path, files: dict[str, str], config=None):
    _write(root, files)
    cfg = config if config is not None else tool.load_config(None)
    return tool.scan_files(root, sorted(files), cfg).findings


def _rules(findings) -> list[tuple[str, str, int]]:
    return sorted((f.rule, f.path, f.line) for f in findings)


# --------------------------------------------------------------------------------------------------------------------
# Từng loại mẫu: phát hiện đúng
# --------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel,text",
    [
        ("infra/a.py", f'ROLE = "arn:aws:iam::{ACCT}:role/yofina-deploy"\n'),
        ("infra/b.ts", f"const env = {{ account: '{ACCT}', region: 'ap-southeast-1' }};\n"),
        ("infra/c.sh", f"export CDK_DEFAULT_ACCOUNT={ACCT}\n"),
        ("docs/d.md", f"Ảnh: `{ACCT}.dkr.ecr.ap-southeast-1.amazonaws.com/yofina:latest`\n"),
        ("docs/e.md", f"https://sqs.ap-southeast-1.amazonaws.com/{ACCT}/yofina-events\n"),
        ("docs/f.md", f"bucket cdk-hnb659fds-assets-{ACCT}-ap-southeast-1\n"),
        (
            "web/g.ts",
            f"const u = 'runtimes/arn%3Aaws%3Abedrock-agentcore%3Aap-southeast-1%3A{ACCT}%3Aruntime'\n",
        ),
    ],
)
def test_bat_account_id_aws_trong_ngu_canh_aws(tool, tmp_path, rel, text):
    found = _scan(tool, tmp_path, {rel: text})

    assert [(f.rule, f.line) for f in found] == [("aws-account-id", 1)]
    assert ACCT not in found[0].masked


def test_khoa_truy_cap_aws_akia_va_asia(tool, tmp_path):
    found = _scan(
        tool,
        tmp_path,
        {
            "a.py": f'KEY_ID = "{AKIA}"\n',
            "b.env.example": f"X={ASIA}\n",
            "c.md": f"`{AWS_DOC_KEY}`\n",
        },
    )

    assert _rules(found) == [
        ("aws-access-key-id", "a.py", 1),
        ("aws-access-key-id", "b.env.example", 1),
    ]


def test_secret_aws_khoa_rieng_pem_va_token_pho_bien(tool, tmp_path):
    found = _scan(
        tool,
        tmp_path,
        {
            "creds.ini": f"[default]\naws_secret_access_key = {SECRET40}\n",
            "k.txt": f"{PEM}\nMIIEpAIBAAKCAQEA\n",
            "ci.yml": f"env:\n  GH: {GH_TOKEN}\n  SLACK: {SLACK}\n",
            "t.py": f'HEADERS = {{"Authorization": "Bearer {JWT}"}}\n',
        },
    )

    assert _rules(found) == [
        ("aws-secret-access-key", "creds.ini", 2),
        ("jwt", "t.py", 1),
        ("private-key", "k.txt", 1),
        ("token", "ci.yml", 2),
        ("token", "ci.yml", 3),
    ]


def test_secret_gan_cung_co_do_ngau_nhien_cao(tool, tmp_path):
    found = _scan(
        tool,
        tmp_path,
        {
            "a.py": f'client_secret = "{GENERIC}"\n',
            "b.py": 'SECRET_NAME = "yofina-demo-accounts"\nTOKEN_INVALID = "TOKEN_INVALID"\n'
            'api_key = f"{prefix}-{suffix}-0123456789"\n',
        },
    )

    assert _rules(found) == [("generic-secret", "a.py", 1)]


def test_mat_khau_gan_cung(tool, tmp_path):
    found = _scan(
        tool,
        tmp_path,
        {
            "a.py": f'DB_PASSWORD = "{PW}"\n',
            "b.py": f'URI = "postgresql://yofina_app:{PW_URL}@db.internal:5432/yofina"\n',
            "c.md": f"Mật khẩu: {PW_URL}\n",
            "ok.ts": "type Props = { password: string }\nconst p = process.env.YOFINA_PASSWORD\n"
            "const t = { password: '...' }\n",
            "ok.py": 'password = os.environ["DB_PASSWORD"]\nPW = "${DB_PASSWORD}"\nlabel = {"password": "password"}\n'
            'URI = f"postgresql://app:{pw}@{host}/db"\n'
            'password = "Aa1!" + secrets.token_urlsafe(18)\nLABELS = {"password": "Mật khẩu của bạn"}\n',
        },
    )

    assert _rules(found) == [
        ("password", "a.py", 1),
        ("password", "b.py", 1),
        ("password", "c.md", 1),
    ]
    assert all(PW not in f.masked and PW_URL not in f.masked for f in found)


def test_email_that_bi_bat_mien_vi_du_thi_khong(tool, tmp_path):
    found = _scan(
        tool,
        tmp_path,
        {
            "a.md": f"Liên hệ {EMAIL}\n",
            "ok.md": "minh@demo.yofina.example, user@example.com, a@mail.example.org, x@y.invalid, "
            "dev@host.test, icon@2x.png\n",
        },
    )

    assert _rules(found) == [("email", "a.md", 1)]
    assert found[0].masked == "n***@gmail.com"


def test_so_dien_thoai_va_so_tai_khoan_trong_du_lieu_mau(tool, tmp_path):
    found = _scan(
        tool,
        tmp_path,
        {
            "data/a.json": f'{{"phone": "{PHONE}", "source_account": "{SOURCE_ACC}"}}\n',
            "data/b.csv": f"ngay,noi dung,so tien\n21/11/2026,CK den STK {ACC_NO} {PHONE_INTL},50000\n",
            "evals/c.json": f'{{"note": "dong \'Transfer Debit-{DEBIT_ACC}\' 50.000 khong cham"}}\n',
        },
    )

    assert _rules(found) == [
        ("account-number", "data/a.json", 1),
        ("account-number", "data/b.csv", 2),
        ("account-number", "evals/c.json", 1),
        ("phone", "data/a.json", 1),
        ("phone", "data/b.csv", 2),
    ]
    assert all(v not in f.masked for f in found for v in (PHONE, SOURCE_ACC, ACC_NO, DEBIT_ACC))


# --------------------------------------------------------------------------------------------------------------------
# Ca không được báo nhầm
# --------------------------------------------------------------------------------------------------------------------


def test_account_gia_cua_test_cdk_duoc_cho_phep_theo_cau_hinh_repo(tool, tmp_path):
    cfg = tool.load_config(REPO / ".gitleaks.toml")
    text = f"const env = {{ account: '{CDK_FAKE}', region: 'ap-southeast-1' }};\n"

    found = _scan(
        tool, tmp_path, {"infra-cdk/test/x.test.ts": text, "infra-cdk/lib/x.ts": text}, cfg
    )

    # Mục cho phép khớp đúng giá trị VÀ thư mục test CDK; cùng giá trị trong mã stack vẫn bị báo.
    assert _rules(found) == [("aws-account-id", "infra-cdk/lib/x.ts", 1)]


def test_hash_sha256_khong_phai_account_id_hay_so_tai_khoan(tool, tmp_path):
    real_hash = hashlib.sha256(b"yofina").hexdigest()
    found = _scan(
        tool,
        tmp_path,
        {
            "data/h.json": f'{{"sha256": "{HASH}", "other": "{real_hash}"}}\n',
            "uv.lock": f'sdist = {{ url = "https://files.example.org/{ACCT}/x.tar.gz", hash = "sha256:{HASH}" }}\n',
            "a.py": f'DIGEST = "sha256:{HASH}"\n',
        },
    )

    assert found == []


def test_so_tien_12_chu_so_khong_bi_bao(tool, tmp_path):
    found = _scan(
        tool,
        tmp_path,
        {
            "data/a.json": f'{{"amount_vnd": {AMOUNT12}, "text": "Mua nha {AMOUNT12} dong"}}\n',
            "data/b.csv": f"ngay,noi dung,so tien\n21/11/2026,Mua nha,{AMOUNT12}\n22/11/2026,Hoan,-{AMOUNT12}\n",
            "c.py": f"AMOUNT = {AMOUNT12}\nACCOUNT_LIMIT = {AMOUNT12}\n",
        },
    )

    assert found == []


def test_ngay_uuid_dau_thoi_gian_va_so_trong_ma_khong_bi_bao(tool, tmp_path):
    found = _scan(
        tool,
        tmp_path,
        {
            "data/a.json": '{"date": "2026-11-21", "id": "0a1b2c3d-1111-4222-8333-444455556666", '
            '"note": "timestamp 1795505552861 (ms)", "seed": 20261121, "model": "claude-haiku-4-5-20251001"}\n',
            "tests/test_x.py": f'PHONE = "{PHONE}"\nSTK = "stk {ACC_NO}"\n',  # mã test, không phải dữ liệu mẫu
        },
    )

    assert found == []


# --------------------------------------------------------------------------------------------------------------------
# Cấu hình danh sách cho phép
# --------------------------------------------------------------------------------------------------------------------


def _cfg(tool, tmp_path: Path, toml: str):
    p = tmp_path / "cfg.toml"
    p.write_text(toml, encoding="utf-8")
    return tool.load_config(p)


def test_muc_cho_phep_theo_gia_tri_va_duong_dan(tool, tmp_path):
    cfg = _cfg(
        tool,
        tmp_path,
        f"""
[[scan_repo.allow]]
description = "Số điện thoại hư cấu của persona."
rules = ["phone"]
values = ["{PHONE.replace(" ", "")}"]
paths = ['''^data/''']

[[scan_repo.allow]]
description = "Miền thư nội bộ giả."
rules = ["email"]
email_domains = ["gmail.com"]
""",
    )
    files = {
        "data/a.json": f'{{"phone": "{PHONE}"}}\n',
        "evals/b.json": f'{{"phone": "{PHONE}"}}\n',
        "c.md": EMAIL,
    }

    _write(tmp_path, files)
    res = tool.scan_files(tmp_path, sorted(files), cfg)

    assert _rules(res.findings) == [("phone", "evals/b.json", 1)]
    assert res.allowed == 2


def test_doc_allowlist_cua_gitleaks_de_khong_lap_hai_nguon(tool, tmp_path):
    cfg = _cfg(
        tool,
        tmp_path,
        f"""
[[allowlists]]
description = "secret giả trong fixture"
targetRules = ["generic-api-key"]
regexes = ['''^{GENERIC[:8]}''']

[[allowlists]]
description = "JWT giả trong một tệp test"
targetRules = ["jwt"]
condition = "AND"
paths = ['''^tests/''']
regexTarget = "line"
regexes = ['''Bearer ''']
""",
    )
    files = {
        "a.py": f'client_secret = "{GENERIC}"\n',
        "tests/t.py": f'H = "Bearer {JWT}"\n',
        "src/t.py": f'H = "Bearer {JWT}"\n',
    }

    found = _scan(tool, tmp_path, files, cfg)

    assert _rules(found) == [("jwt", "src/t.py", 1)]


def test_tep_cau_hinh_duoc_ghi_gia_tri_no_cho_phep(tool, tmp_path):
    """`.gitleaks.toml` phải chép giá trị nó cho phép (và lý do có thể nhắc lại giá trị), dù `paths` của mục trỏ nơi khác."""
    toml = f"""
[[scan_repo.allow]]
description = "Địa chỉ giả {EMAIL} và account giả AWS {CDK_FAKE} dùng trong test."
rules = ["email", "aws-account-id"]
values = ["{EMAIL}", "{CDK_FAKE}"]
paths = ['''^tests/''']
"""
    cfg = _cfg(tool, tmp_path, toml)
    files = {".gitleaks.toml": toml, "src/a.md": f"{EMAIL}\n", "docs/.gitleaks.toml": f"{EMAIL}\n"}

    _write(tmp_path, files)
    res = tool.scan_files(tmp_path, sorted(files), cfg)

    assert _rules(res.findings) == [("email", "docs/.gitleaks.toml", 1), ("email", "src/a.md", 1)]
    assert res.allowed == 3


@pytest.mark.parametrize(
    "entry",
    [
        'rules = ["phone"]\nvalues = ["0"]',  # thiếu lý do
        'description = "x"\nrules = ["khong-co"]\nvalues = ["0"]',  # luật không tồn tại
        "description = \"x\"\npaths = ['''^data/''']",  # chỉ đường dẫn: bỏ qua cả tệp, không cho
    ],
)
def test_muc_cho_phep_sai_thi_bao_loi_cau_hinh(tool, tmp_path, entry):
    with pytest.raises(tool.ScanError):
        _cfg(tool, tmp_path, f"[[scan_repo.allow]]\n{entry}\n")


def test_cau_hinh_cua_repo_doc_duoc_va_moi_muc_co_ly_do(tool):
    cfg = tool.load_config(REPO / ".gitleaks.toml")

    assert cfg.allow, "repo phải khai danh sách cho phép trong .gitleaks.toml"
    assert all(len(a.description.strip()) >= 20 for a in cfg.allow)


def test_che_gia_tri(tool):
    assert tool.mask(ACCT) == "53********61"
    assert tool.mask("abc") == "***"
    assert EMAIL not in tool.mask(EMAIL, rule="email")


# --------------------------------------------------------------------------------------------------------------------
# Chế độ quét: cây làm việc, --ref, --history; mã thoát; không in nguyên giá trị
# --------------------------------------------------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    ident = ["-c", "user.name=yofina-test", "-c", "user.email=", "-c", "commit.gpgsign=false"]
    proc = subprocess.run(["git", *ident, *args], cwd=cwd, check=True, capture_output=True)
    return proc.stdout.decode("utf-8").strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Repo tạm: commit 1 thêm khóa AWS vào `cfg/a.py` dòng 3; commit 2 xóa dòng đó."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _write(root, {"cfg/a.py": f'A = 1\nB = 2\nKEY_ID = "{AKIA}"\n', "README.md": "# demo\n"})
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "them")
    _write(root, {"cfg/a.py": "A = 1\nB = 2\n"})
    _git(root, "commit", "-q", "-am", "xoa")
    return root


def test_cay_lam_viec_chi_quet_tep_git_theo_doi(tool, repo):
    _write(repo, {"chua_theo_doi.py": f'K = "{AKIA}"\n'})
    cfg = tool.load_config(None)

    assert tool.scan_worktree(repo, cfg).findings == []

    _write(repo, {"README.md": f"# demo {ASIA}\n"})  # sửa dở tệp đã theo dõi
    assert _rules(tool.scan_worktree(repo, cfg).findings) == [("aws-access-key-id", "README.md", 1)]


def test_ref_quet_noi_dung_cua_commit_khong_phai_cay_lam_viec(tool, repo):
    cfg = tool.load_config(None)
    first = _git(repo, "rev-parse", "HEAD~1")
    _write(repo, {"README.md": f"# demo {ASIA}\n"})  # chưa commit: --ref HEAD không thấy

    assert tool.scan_ref(repo, "HEAD", cfg).findings == []
    assert _rules(tool.scan_ref(repo, first, cfg).findings) == [
        ("aws-access-key-id", "cfg/a.py", 3)
    ]


def test_history_liet_ke_vi_tri_trong_lich_su_va_chi_bao_cao(tool, repo, capsys):
    first = _git(repo, "rev-parse", "HEAD~1")

    res = tool.scan_history(repo, tool.load_config(None))
    assert [(f.rule, f.path, f.line, f.commit) for f in res.findings] == [
        ("aws-access-key-id", "cfg/a.py", 3, first)
    ]

    code = tool.main(["--repo", str(repo), "--history", "--json"])
    out = capsys.readouterr().out
    assert code == 0  # chỉ báo cáo: lịch sử không sửa được bằng một commit mới
    data = json.loads(out)
    assert data["mode"] == "history"
    assert data["findings"][0]["commit"] == first
    assert data["findings"][0]["line"] == 3
    assert AKIA not in out


def test_main_ma_thoat_va_khong_in_nguyen_gia_tri(tool, repo, capsys):
    args = ["--repo", str(repo)]  # repo tạm không có .gitleaks.toml: chỉ luật dựng sẵn
    assert tool.main(args) == 0
    capsys.readouterr()

    _write(repo, {"cfg/b.py": f'DB_PASSWORD = "{PW}"\nOWNER = "{EMAIL}"\n'})
    _git(repo, "add", "-A")
    assert tool.main(args) == 1
    text = capsys.readouterr().out
    assert tool.main([*args, "--json"]) == 1
    data = json.loads(capsys.readouterr().out)

    assert "cfg/b.py:1" in text and "cfg/b.py:2" in text
    assert PW not in text and EMAIL not in text
    assert {f["rule"] for f in data["findings"]} == {"password", "email"}
    assert PW not in json.dumps(data) and EMAIL not in json.dumps(data)


def test_main_cau_hinh_khong_ton_tai_thi_ma_thoat_2(tool, repo, capsys):
    assert tool.main(["--repo", str(repo), "--config", str(repo / "khong-co.toml")]) == 2
    assert "khong-co.toml" in capsys.readouterr().err


# --------------------------------------------------------------------------------------------------------------------
# make_submission_zip.py dùng scan_repo.py làm bộ quét mặc định, quét đúng commit được nén
# --------------------------------------------------------------------------------------------------------------------


def test_bo_quet_mac_dinh_cua_zip_la_scan_repo_tren_commit_duoc_nen(zipper, tmp_path):
    root = tmp_path / "r"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPTS / "scan_repo.py", root / "scripts" / "scan_repo.py")

    cmd = zipper.default_scan_cmd(root, "abc123")

    assert cmd == [sys.executable, str(root / "scripts" / "scan_repo.py"), "--ref", "abc123"]


def test_zip_dung_khi_scan_repo_bao_phat_hien(zipper, repo, tmp_path):
    (repo / "scripts").mkdir()
    shutil.copy(SCRIPTS / "scan_repo.py", repo / "scripts" / "scan_repo.py")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "them scan_repo")
    out = tmp_path / "ngoai" / "x.zip"

    res = zipper.make_submission_zip(repo, out)  # HEAD sạch
    assert res.files == 3

    with zipfile.ZipFile(out) as z:
        assert any(n.endswith("/scripts/scan_repo.py") for n in z.namelist())
    out.unlink()

    with pytest.raises(zipper.SubmissionError):
        zipper.make_submission_zip(repo, out, ref="HEAD~2")  # commit có khóa AWS
    assert list(out.parent.iterdir()) == []  # không zip, không tệp tạm
