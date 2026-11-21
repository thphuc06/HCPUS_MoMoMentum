# Spike: AgentCore Runtime + Cognito JWT + AG-UI qua SSE, gọi thẳng từ trình duyệt

Kết quả và kết luận: `docs/research/spike-agentcore-runtime-cors.md`. Tài nguyên AWS đã tạo và trạng thái dọn: `RESOURCES.md`.
Spike chạy ngày 2026-11-21, Region `ap-southeast-1`, trên tài khoản thật. **Mọi tài nguyên đã xóa sau khi đo** nên muốn chạy lại phải tạo lại từ đầu theo các bước dưới.

## Thành phần

| File | Việc |
|---|---|
| `agent/main.py` | App FastAPI cổng 8080: `POST /invocations` (AG-UI, SSE), `GET /ping`. `forwardedProps.mode`: `fake` (mặc định, event giả có `CUSTOM spike.info`) hoặc `llm` (Strands + Bedrock Haiku 4.5 + 1 tool). Biến môi trường `SPIKE_CORS=on` bật `CORSMiddleware` trong app |
| `agent/pyproject.toml` | Phụ thuộc ghim (ag-ui-strands 1.0.4, strands-agents 1.65.0...) |
| `agent/opentelemetry-instrument` | Launcher POSIX cho bản có OTel (uv trên Windows sinh `.exe`, vô dụng trên Linux) |
| `make_zip.py` | Đóng gói `build/pkg` + `main.py` thành zip với quyền 644/755, bỏ `__pycache__` |
| `update_rt.py` | `UpdateAgentRuntime` từ `create.json` với vài ghi đè (zip, cors, audience, entry OTel, env) |
| `common_client.py`, `q4_timing.py`, `q5_sessions.py` | Client httpx: đo độ trễ cold/warm, thử session id |
| `web/index.html`, `web/run_browser.mjs`, `web/scen_*.json` | Trang `http://localhost:5173` + Playwright (`playwright-core`, kênh `msedge` hoặc `chrome` có sẵn, không tải chromium) |
| `out/` | Kết quả thô (JSON/txt). Không chứa token hay mật khẩu |

## Chạy lại (tóm tắt lệnh đã dùng)

Điều kiện: AWS CLI đã đăng nhập, `uv`, Python 3.13, Node. Mọi lệnh đặt `--region ap-southeast-1`. Trên Git Bash đặt `MSYS_NO_PATHCONV=1` khi truyền tên log group bắt đầu bằng `/aws/...`, và dùng `cygpath -m` cho đường dẫn `file://`.

```bash
# 1. Gói deploy không cần Docker: wheel ARM64 cài từ Windows
cd agent && uv pip install --python-platform aarch64-manylinux2014 --python-version 3.13 \
  --only-binary=:all: --target=../build/pkg -r pyproject.toml && cd ..
python make_zip.py deployment_package.zip

# 2. S3 bucket + upload
aws s3api create-bucket --bucket yofina-spike-rt-code-<suffix> --region ap-southeast-1 \
  --create-bucket-configuration LocationConstraint=ap-southeast-1
aws s3 cp build/deployment_package.zip s3://yofina-spike-rt-code-<suffix>/v1/deployment_package.zip --region ap-southeast-1

# 3. IAM role thực thi (tin bedrock-agentcore.amazonaws.com; quyền bedrock:InvokeModel*, s3:GetObject, logs, xray)
# 4. Cognito: create-user-pool, create-user-pool-client (ALLOW_USER_PASSWORD_AUTH), admin-create-user,
#    admin-set-user-password --permanent, initiate-auth -> AccessToken
# 5. Runtime (CodeZip + AGUI + JWT). aws CLI 2.35.5 chưa biết platformVersion nên bản V2 phải tạo bằng boto3.
aws bedrock-agentcore-control create-agent-runtime --region ap-southeast-1 --cli-input-json file://create.json
#   create.json: agentRuntimeArtifact.codeConfiguration {code.s3{bucket,prefix}, runtime PYTHON_3_13, entryPoint ["main.py"]},
#   protocolConfiguration.serverProtocol AGUI, authorizerConfiguration.customJWTAuthorizer {discoveryUrl, allowedClients},
#   requestHeaderConfiguration.requestHeaderAllowlist [...], networkConfiguration PUBLIC, roleArn

# 6. Gọi
#   URL = https://bedrock-agentcore.ap-southeast-1.amazonaws.com/runtimes/<ARN url-encode>/invocations?qualifier=DEFAULT
#   Header: Authorization: Bearer <access token>, X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: <33..256 ký tự>
export SPIKE_STATE=<file KEY=VALUE: ACC, RT, ...> SPIKE_TOKENS=<json {"a": access, "i": id}>
python q4_timing.py 5 out/q4.json          # dùng python có httpx
python q5_sessions.py

# 7. Trình duyệt thật
cd web && npm install
RT_URL=<URL> TOKEN_FILE=<json tokens> BROWSER_CHANNEL=msedge node run_browser.mjs scen_v1.json ../out/browser.json
```

Dọn: xem cột "Lệnh xóa" trong `RESOURCES.md` (xóa runtime trước, rồi log group, S3, IAM role, Cognito pool).
