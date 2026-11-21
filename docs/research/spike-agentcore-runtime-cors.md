# Spike: AgentCore Runtime + Cognito JWT + AG-UI qua SSE, gọi thẳng từ trình duyệt

Ngày chạy: **2026-11-21**, Region `ap-southeast-1`, tài khoản AWS thật (đăng nhập root, không tạo access key). Code, script và kết quả thô: `spikes/agentcore-runtime-cors/` (`README.md` cách chạy lại, `out/` số liệu). Danh sách tài nguyên và trạng thái dọn: `spikes/agentcore-runtime-cors/RESOURCES.md` (tóm tắt ở mục 8).

Quy ước: **[Chạy]** là điều đã chạy và quan sát trong spike này; **[Suy luận]** là suy ra từ kết quả, chưa kiểm trực tiếp; **[TL]** là tài liệu AWS đọc ngày hôm nay.

## 0. Kết luận một đoạn

**Trình duyệt gọi thẳng endpoint InvokeAgentRuntime bằng `fetch` + `Authorization: Bearer <Cognito access token>` và đọc SSE AG-UI được, không cần proxy.** Chính dịch vụ AgentCore trả preflight `OPTIONS` và gắn `Access-Control-Allow-Origin: *` vào mọi phản hồi (kể cả 401/403); `CORSMiddleware` trong app không có tác dụng. Bằng chứng: Edge 158 và Chrome 157 thật (headless, qua Playwright) từ `http://localhost:5173` nhận 200, đọc từng event SSE đến dần (cách nhau ~0,5 s đúng như app phát), và đọc được cả thân 401. Điểm cần chú ý cho Yofina nằm ở chỗ khác: cold start 1,8 đến 3,9 s, `Bearer` phải viết hoa, ID token không qua với `allowedClients`, session pinning chỉ có ở platform V2.

## 1. Deploy không có Docker; AG-UI có chạy với CodeZip không

**Cách thử [Chạy].** Docker không chạy trên máy; dùng direct code deployment (zip lên S3), không qua CodeBuild.

```bash
# wheel ARM64 cài ngay trên Windows x86 (không cần QEMU/Docker)
uv pip install --python-platform aarch64-manylinux2014 --python-version 3.13 \
  --only-binary=:all: --target=build/pkg -r pyproject.toml     # 73 MB giải nén
python make_zip.py                                              # 30,9 MB nén, quyền 644/755
aws s3api create-bucket --bucket yofina-spike-rt-code-<suffix> --region ap-southeast-1 \
    --create-bucket-configuration LocationConstraint=ap-southeast-1
aws s3 cp build/deployment_package.zip s3://<bucket>/v1/deployment_package.zip --region ap-southeast-1
aws bedrock-agentcore-control create-agent-runtime --region ap-southeast-1 --cli-input-json file://create.json
```

`create.json` (rút gọn): `agentRuntimeArtifact.codeConfiguration {code.s3{bucket,prefix}, runtime: PYTHON_3_13, entryPoint: ["main.py"]}`, `protocolConfiguration.serverProtocol: AGUI`, `authorizerConfiguration.customJWTAuthorizer {discoveryUrl, allowedClients}`, `requestHeaderConfiguration.requestHeaderAllowlist`, `networkConfiguration.networkMode: PUBLIC`, `roleArn` (role thực thi tin `bedrock-agentcore.amazonaws.com`, quyền `bedrock:InvokeModel*` cho Haiku 4.5 + inference profile, `s3:GetObject` trên bucket, logs, X-Ray).

**Quan sát [Chạy].**
- API **chấp nhận** tổ hợp `codeConfiguration` + `serverProtocol: AGUI`; runtime V1 lên `READY` sau ~15 giây; gọi được ngay. Tài liệu AG-UI ghi "container", nhưng thực tế CodeZip chạy tốt: **không buộc container ARM64**. App là FastAPI tự chạy `uvicorn` trên 8080 (`/invocations`, `/ping`) trong `main.py`, đúng hợp đồng.
- Gói phụ thuộc đã chạy: `ag-ui-protocol 1.0.0`, `ag-ui-strands 1.0.4`, `strands-agents 1.65.0`, `fastapi 0.165.0`, `uvicorn 0.54.0`, `boto3 1.44.9` (bản mới nhất, **không** theo dải ghim cũ trong tài liệu AWS). Chạy được cả chế độ giả (không LLM) lẫn Strands + Bedrock Haiku 4.5 + 1 tool tất định (sự kiện: `RUN_STARTED`, `STATE_SNAPSHOT`, `MESSAGES_SNAPSHOT`, `TOOL_CALL_START/END/RESULT`, `RAW`, `TEXT_MESSAGE_*`, `RUN_FINISHED`).
- Bẫy gặp [Chạy]: (a) `aws` CLI 2.35.5 chưa có `--platform-version` (boto3 1.44.9 có `platformVersion`) nên runtime V2 phải tạo bằng boto3; (b) `uv --target` trên Windows sinh launcher `.exe` trong `bin/`, vô dụng trên Linux, phải loại khỏi zip (với OTel đã tự thêm script POSIX `bin/opentelemetry-instrument`, runtime chạy được); (c) tên Runtime chỉ cho `[a-zA-Z][a-zA-Z0-9_]*` nên `yofina_spike_rt_...` thay vì dấu gạch nối; (d) `StrandsAgent(agent=<callable>)` chỉ dành cho Graph/Swarm, truyền factory cho Agent đơn ném `TypeError` (ngay lúc đầu luồng); khi lỗi ném **giữa luồng** sau khi đã trả header, client nhận **HTTP 200 với thân rỗng, không có `RUN_ERROR`**: UI phải xử lý luồng rỗng/đứt như lỗi.
- Phần `agentcore` CLI [Chạy một phần]: cài `@aws/agentcore` 1.2.0 vào thư mục tạm (không cài toàn cục); `agentcore add runtime --protocol AGUI --build-config '{"build":"CodeZip"}'` được CLI chấp nhận và ghi `agentcore.json` (`build: CodeZip`, `protocol: AGUI`, `runtimeVersion` mặc định `PYTHON_3_14`). **Không chạy `agentcore deploy`** vì nó dùng CDK (cần bootstrap, tạo thêm bucket/role: đổi cấu hình tài khoản ngoài phạm vi cho phép). `agentcore create` trên đường dẫn dài báo lỗi MAX_PATH Windows (123 ký tự) và gợi ý `--skip-install`.
- CodeBuild/container: **không thử**.

**Kết luận.** Với dự án: dùng CodeZip, build wheel ARM64 từ Windows bằng `uv`, không cần Docker. Đưa lệnh trên vào `infra-cdk` (CDK `AgentRuntimeArtifact.fromS3`) hoặc script.

## 2. JWT Cognito

**Cách thử [Chạy].** User pool `yofina-spike-rt-pool`, hai app client (không secret, `ALLOW_USER_PASSWORD_AUTH`), user thử qua `admin-create-user` + `admin-set-user-password --permanent`, lấy token bằng `initiate-auth`. Authorizer của Runtime: `discoveryUrl = https://cognito-idp.ap-southeast-1.amazonaws.com/<pool>/.well-known/openid-configuration`.

**Token Cognito [Chạy].** Access token có `client_id`, `token_use=access`, `scope`, **không có `aud`**; ID token có `aud`, `token_use=id`, **không có `client_id`**.

| Cấu hình authorizer | Access token (client đúng) | ID token (client đúng) | Token của client khác |
|---|---|---|---|
| `allowedClients=[client]` | **200** | 401 `Claim 'client_id' value mismatch with configuration.` | 401 cùng thông điệp |
| `allowedAudience=[client]` | 401 | **200** | 401 |
| cả hai cùng đặt | 401 | 401 | 401 |

Đã đổi cấu hình bằng `update-agent-runtime` (tạo version mới, ~10 giây, áp dụng cho phiên mới). **Dùng `allowedClients` + access token** (khớp `agentcore.md`); đừng đặt cả hai với Cognito.

**Lỗi khi token sai/thiếu [Chạy]** (thân luôn là một event SSE `RUN_ERROR`, `Content-Type: text/event-stream`; header `x-amzn-ErrorType` cho biết loại):

| Tình huống | HTTP | `code` / thông điệp | `x-amzn-ErrorType` |
|---|---|---|---|
| Không có `Authorization` | 401 | `UNAUTHORIZED` "Missing Authentication Token" + `WWW-Authenticate: Bearer resource_metadata="https://bedrock-agentcore.<region>.amazonaws.com/runtimes/<ARN>/invocations/.well-known/oauth-protected-resource?qualifier=DEFAULT"` | `MissingAuthenticationTokenException` |
| Token rác `Bearer abc.def.ghi` | 403 | `ACCESS_DENIED` "OAuth authorization failed: Failed to parse token" | `AccessDeniedException` |
| Sai client / sai loại token | 401 | `UNAUTHORIZED` "Claim 'client_id' value mismatch with configuration." | `UnrecognizedClientException` |
| Scheme `Basic ...` hoặc **`bearer` viết thường** | 403 | `ACCESS_DENIED` "Invalid key=value pair (missing equal-sign) in Authorization header..." | `IncompleteSignatureException` |
| Token hết hạn (client đặt access token sống 5 phút, gọi lại sau khi hết) | 401 | `UNAUTHORIZED` | `UnrecognizedClientException` |

Cả các lỗi này đều có `Access-Control-Allow-Origin: *`, nên JS trong trình duyệt đọc được status và thân (xem S2 mục 3). Số liệu: `out/q2_auth_errors_allowedClients.txt`, `out/q2_audience_config.txt`, `out/q2_expired_token.txt`.

**Header Authorization tới app [Chạy].** Khi đã khai `Authorization` trong `requestHeaderAllowlist`, app nhận nguyên header (đã được dịch vụ kiểm chữ ký); app còn nhận thêm `WorkloadAccessToken` do dịch vụ gắn (ghi log phải che).

## 3. CORS: câu hỏi quan trọng nhất

**Cách thử [Chạy].** (1) `curl` mô phỏng preflight và POST có `Origin`; (2) trang tĩnh `http://localhost:5173` (`web/index.html`) gọi `fetch` POST + `ReadableStream`, chạy bằng Playwright `playwright-core` với Edge 158 (`channel: msedge`) và Chrome 157 (`channel: chrome`) có sẵn, headless, không tải chromium; (3) so hai cấu hình app: `SPIKE_CORS=off` và `SPIKE_CORS=on` (`CORSMiddleware` cho `http://localhost:*`, cho phép đủ header).

**Preflight, không có `CORSMiddleware` [Chạy]:**
```
OPTIONS /runtimes/<ARN>/invocations?qualifier=DEFAULT   (Origin: http://localhost:5173,
        Access-Control-Request-Method: POST, Access-Control-Request-Headers: authorization,content-type,x-amzn-bedrock-agentcore-runtime-session-id)
HTTP/1.1 200 OK        (không cần Authorization)
Access-Control-Allow-Origin: *
Access-Control-Allow-Headers: authorization,content-type,x-amzn-bedrock-agentcore-runtime-session-id
Access-Control-Allow-Methods: POST
Access-Control-Max-Age: 172800
Access-Control-Expose-Headers: smithy-protocol,baggage,WWW-Authenticate,Date,Mcp-Session-Id,X-Amzn-Trace-Id,X-Amzn-Bedrock-AgentCore-Runtime-Session-Id,Mcp-Protocol-Version,tracestate,x-amzn-ErrorMessage,traceparent,x-amzn-RequestId,x-amzn-ErrorType
```
- `Allow-Headers` **phản chiếu** đúng danh sách được hỏi, kể cả `x-yofina-test`, `traceparent`, `x-amzn-trace-id`, `x-amz-date`, `x-weird-header-123`: **mọi header tùy biến đều qua preflight**. `Allow-Methods` cũng phản chiếu method được hỏi (POST, GET, PUT đều 200). Origin lạ (`https://example.com`) cũng nhận `*`. Preflight tới một Runtime **không tồn tại** vẫn 200: CORS là xử lý ở tầng dịch vụ, không phụ thuộc runtime hay authorizer.
- `OPTIONS` **không có** `Origin` trả 404 `UnknownOperationException` (không ảnh hưởng trình duyệt).
- Phản hồi `POST` thật (200, 401, 403) đều có `Access-Control-Allow-Origin: *` và danh sách `Expose-Headers` trên.

**`CORSMiddleware` trong app vô hiệu [Chạy].** Với `SPIKE_CORS=on`: preflight vẫn y hệt (do dịch vụ trả); app **không bao giờ thấy** header `Origin` (và `Referer`, `Access-Control-Request-*`: nằm trong danh sách header bị cấm chuyển tiếp của tài liệu); header phản hồi do app đặt (`X-Spike-Marker`, `Cache-Control`) **không tới client**. Kết luận: không cần và không thể chỉnh CORS từ code agent.

**Trình duyệt thật [Chạy], `out/q3_browser_*.json`** (Edge 158 và Chrome 157, origin `http://localhost:5173`):

| Kịch bản | Kết quả |
|---|---|
| S1 POST + `Authorization: Bearer` + `Content-Type: application/json` + session id | 200, đọc SSE đến dần (V1 ví dụ: 4462 ms RUN_STARTED, rồi chunk ở 4942, 5444, 5940, 6434 ms) |
| S2 không `Authorization` | `fetch` không lỗi, `status=401`, đọc được `RUN_ERROR UNAUTHORIZED` và header `www-authenticate`, `x-amzn-errortype` |
| S3 thêm `X-Yofina-Test`, `traceparent`, `X-Amzn-Trace-Id`, `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Foo`, `Accept` | 200 (preflight cho phép hết) |
| S4 `credentials: 'include'` | **Bị chặn**: "The value of the 'Access-Control-Allow-Origin' header ... must not be the wildcard '*' when the request's credentials mode is 'include'". Không sao vì Bearer đi bằng header, không cần cookie |

Header phản hồi đọc được từ JS: `content-type`, `date`, `x-amzn-bedrock-agentcore-runtime-session-id`, `x-amzn-requestid` (và `www-authenticate`, `x-amzn-errortype` khi lỗi). Preflight được trình duyệt cache (`Max-Age` 172800, Chromium giới hạn ~2 giờ): các lần gọi sau trong cùng phiên không tốn thêm một round trip.

**Header nào tới được app [Chạy]** (`out/q3_header_forwarding.txt`): chỉ header có tên trong `requestHeaderAllowlist` (ở đây `Authorization`, `X-Yofina-Test`, `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Foo`); `X-Not-Listed` bị bỏ; header tiền tố `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Bar` **không khai trong allowlist cũng bị bỏ** (tài liệu nói "luôn qua" là sai). `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` tới app (kèm `baggage: session.id=...`). `traceparent` và `X-Amzn-Trace-Id` do client gửi được chuyển tiếp (mục 6) mà không cần khai allowlist.

**Kết luận cho kiến trúc Yofina.** Frontend gọi thẳng Runtime được. Lớp trung gian (API Gateway/Lambda Function URL/CloudFront) **không cần vì CORS**. Chỉ cần lớp đó nếu muốn lý do khác: giấu ARN của Runtime (URL chứa account ID và tên runtime), WAF/giới hạn tần suất, chèn bước xác nhận ghi do server kiểm soát, domain riêng. Phương án proxy chỉ mô tả, không dựng.

## 4. Streaming thật và độ trễ

**Cách thử [Chạy].** App chế độ giả phát event cách nhau `delay` giây; client httpx và trình duyệt ghi mốc thời gian từng event. "Cold" = mỗi lần dùng session id mới (microVM mới); "warm" = lặp cùng session. Ba cấu hình: V1 CodeZip (không OTel), V2 CodeZip (`platformVersion=V2`), V1 + OTel (`opentelemetry-instrument`).

**Không bị đệm [Chạy].** Event đến đúng nhịp phát: trong trình duyệt chunk cách nhau ~0,5 s khi app phát cách nhau 0,5 s; với khoảng nghỉ **45 s** giữa hai chunk (V2), event tới ở 3,1 s, 48,1 s, 93,1 s (không bị cắt vì idle, không gộp). Các event phát liền nhau (RUN_STARTED, CUSTOM, TEXT_MESSAGE_START) tới cùng một mốc chỉ vì chúng được ghi cùng lúc.

**Thời gian tới event đầu (giây, từ lúc gửi request), httpx từ máy phát triển:**

| Cấu hình | Cold (5 mẫu) | Cold trung vị | Warm (25 mẫu) |
|---|---|---|---|
| V1 CodeZip | 2,60 2,55 2,68 3,60 3,65 | **2,68** | trung vị 0,30 (0,24 đến 0,35) |
| V2 CodeZip | 2,65 2,69 2,51 1,79 1,76 | **2,51** | trung vị 0,32 (0,26 đến 1,06) |
| V1 + OTel (3 mẫu) | 6,39 5,06 5,18 | **5,18** | trung vị 0,30 |

Trình duyệt (Edge, gồm cả preflight ở lần gọi đầu): V1 cold 3,58 / 3,47 / 2,47 s, cùng session lần đầu 2,45 s, ấm 0,20 đến 0,24 s; V2 cold 1,92 / 1,72 / 1,96 s, lần đầu cùng session 1,69 s, ấm 0,23 đến 0,26 s. Chrome cho kết quả tương tự (V2: tổng 3,9 s cho luồng 4 chunk × 0,5 s, tức ~1,9 s tới event đầu). Chế độ LLM (Haiku 4.5 + tool, V1): event đầu 5,5 s ở lần đầu (cold ~2,6 s cộng nạp thư viện Strands và tạo agent), tool ở 6,06 s, chữ đầu ở 6,55 s, xong 6,8 s; lượt hai cùng phiên: event đầu 0,33 s, xong 0,97 s.

**Đọc kết quả.** (1) Phiên lạnh tốn 1,8 đến 3,9 s trước event đầu, cả V1 lẫn V2: **không đạt mục tiêu "ký tự đầu dưới 1,5 giây" khi phiên lạnh**; V2 nhỉnh hơn (trong trình duyệt 1,7 đến 2,0 s so với 2,5 đến 3,6 s của V1) nhưng 5 mẫu chưa đủ để khẳng định. Phần cố định ~0,2 đến 0,3 s là thời gian mạng tới Singapore + TLS từ máy này. (2) Phiên ấm ~0,3 s là đạt. (3) Bật OTel (ADOT) làm cold start V1 tăng ~2,5 s; chưa đo V2 + OTel (V2 chụp snapshot nên có thể khác). (4) Hệ quả: cân nhắc "làm nóng" phiên khi người dùng mở màn hình chat (gọi một request nhẹ với session id sẽ dùng), và hiện giao diện tiến độ cho lượt đầu.

## 5. Phiên

**Cách thử [Chạy]** (`q5_sessions.py`, `out/q5_sessions_*.txt`): app đếm số lần gọi và pid trong bộ nhớ tiến trình.

- **Độ dài session id**: 1, 10, 32 ký tự → 400 `VALIDATION_ERROR`; **33 đến 256 ký tự → 200**; 257 → 400. Ký tự khoảng trắng, `/`, `:`, `_`, `-` đều được và được trả nguyên văn trong header phản hồi. Header: `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` (không phân biệt hoa/thường). **Không gửi header** → dịch vụ sinh UUID và trả trong header cùng tên (client phải giữ lại để dùng lượt sau).
- **Trạng thái trong bộ nhớ tiến trình**: cùng session, gọi lại 4 lần: cùng pid, bộ đếm 1, 2, 3, 4; session khác: tiến trình/bộ đếm riêng. Vậy trạng thái RAM **được giữ** trong phiên (đến khi hết idle/`StopRuntimeSession`; không đo hết idle 300 s). Riêng Strands `Agent` trong tiến trình với `ag-ui-strands`: lượt hai chỉ gửi tin nhắn mới thì model **không nhớ** lượt một ("lần đầu chúng ta trò chuyện"); khi client gửi lại toàn bộ `messages` (đúng ngữ nghĩa AG-UI) thì nhớ ("Lan"). Frontend phải gửi lại lịch sử, hoặc dùng session manager/Memory.
- **V1 và V2 khác nhau [Chạy]**:

| Hành vi | V1 | V2 |
|---|---|---|
| Hai request song song cùng session | cả hai chạy (cùng tiến trình, bộ đếm 1 và 2) | request thứ hai: **409 `SESSION_BUSY`** sau 0,28 s |
| Người dùng B (token khác, cùng pool) dùng session của A | **được** (cùng microVM, đọc/ghi chung bộ đếm) | **403 `ACCESS_DENIED`** (session pinning theo `sub`) |
| B mở session mới; A quay lại session cũ | được | được |
| Tạo/cập nhật runtime | ~15 / ~10 giây | **~5 phút** |
| pid/uptime trong app | pid nhỏ (~340), uptime từ 0,2 s | pid 1, uptime 300 s trở lên (tiến trình đã khởi động trước lúc chụp snapshot) |

**Kết luận.** Dùng platform V2 nếu cần chặn người dùng khác chiếm session (V1 chỉ tách theo session id, ai biết id là vào được). Trên V2, UI phải xử lý 409 `SESSION_BUSY` (chặn gửi song song cùng thread/session, thử lại với backoff). Sinh session id phía client: UUID v4 (36 ký tự) thỏa ≥33. Lưu ý V2 chụp snapshot nên khởi tạo ở mức module (boto3 client, `time`, bộ đếm) chạy trước phiên: viết code theo `runtime-v2-optimize` [TL].

## 6. Trace và observability

**Đã thử [Chạy].**
- **Log**: stdout của app (JSON một dòng mỗi request) và traceback nằm ở log group `/aws/bedrock-agentcore/runtimes/<runtimeId>-DEFAULT`, stream `YYYY/MM/DD/[runtime-logs-<uuid>]<uuid>`; tự tạo ở lần gọi đầu; lọc được theo session id/trace id bằng `filter-log-events`.
- **Lấy trace id từ client**: phản hồi **không** trả trace id (header phản hồi không có `traceparent`/`X-Amzn-Trace-Id`; `Expose-Headers` có tên chúng nhưng giá trị không được gắn). Ngược lại, client **chọn được** trace id: gửi `traceparent: 00-<trace-id>-<span>-01` thì app nhận `traceparent` cùng trace id (dịch vụ đổi parent-id) và `X-Amzn-Trace-Id: Root=1-<8 hex đầu>-<24 hex còn lại>;Parent=...;Sampled=1;Self=...`; chỉ gửi `X-Amzn-Trace-Id: Root=1-67891233-abcdef...` thì `Root` giữ nguyên. Gửi cả hai thì `Root` lấy theo `traceparent`. Vậy mẫu trong `agentcore.md` (client/BFF sinh `traceparent` làm `trace_id`) **dùng được**, kể cả gọi thẳng từ trình duyệt (preflight cho phép `traceparent`).
- **OTel trong app**: `entryPoint ["opentelemetry-instrument","main.py"]` + `aws-opentelemetry-distro~=0.21.0` chạy được trên CodeZip (cần launcher POSIX, mục 1). Cảnh báo `opentelemetry-api==1.45.2` lệch bản 1.44.0 distro mong đợi. Xuất span trả **400 Bad Request** vì tài khoản chưa bật CloudWatch Transaction Search (đích X-Ray là `XRay`, trạng thái ACTIVE).

**Chưa thử được.** Xem span/trace trong CloudWatch GenAI Observability: cần bật Transaction Search (đổi cấu hình tài khoản, không được phép trong spike này). Do đó vị trí thật của span và cách khớp với `traceparent` từ client chưa xác nhận.

## 7. Khuyến nghị cụ thể cho Yofina

1. **Bỏ bước proxy chỉ vì CORS**; frontend gọi `https://bedrock-agentcore.ap-southeast-1.amazonaws.com/runtimes/<ARN url-encode>/invocations?qualifier=DEFAULT` bằng `fetch` + `Authorization: Bearer <access token>`. Xác nhận lại bằng domain thật (Amplify Hosting) khi có, dù preflight trả `*` cho mọi Origin.
2. Cognito: `allowedClients=[appClient]`, gửi **access token**, đúng chữ `Bearer` hoa. Làm mới token trước khi hết hạn (mặc định 60 phút); token hết hạn giữa một luồng SSE đang chạy chưa thử.
3. Runtime: platform **V2** (pinning + `SESSION_BUSY`), CodeZip từ `uv` ARM64, khai `Authorization` (và các header cần) trong `requestHeaderAllowlist`; trong app đọc `sub` từ `Authorization`, không nhận `user_id` từ payload.
4. UI: sinh session id UUID, giữ ổn định theo cuộc hội thoại; gửi lại toàn bộ `messages`; xử lý `RUN_ERROR`, 401/403/409 và luồng rỗng (lỗi giữa luồng = 200 + thân rỗng); làm nóng phiên khi mở chat; `traceparent` do client sinh.
5. ARN, account ID nằm trong URL phía client: chấp nhận được (bảo vệ bằng JWT), nhưng ghi nhận.

## 8. Chưa thử được / chưa chắc

- CORS từ domain thật (chỉ `localhost`; `curl` với Origin `https://example.com` cho `*`), Firefox/Safari/Edge không-headless; WebSocket `/ws`.
- `agentcore deploy` (CDK) và đường container/CodeBuild; V2 + OTel; interrupt/resume AG-UI qua Runtime (chỉ chạy local ở spike khác); idle timeout thật (đã đặt 300 s, không chờ); token hết hạn giữa luồng; tải/đồng thời; quota Haiku bị chạm hay không (không chạm: chỉ ~8 lượt gọi model).
- Span/trace trong CloudWatch (cần Transaction Search); chi phí thực (Cost Explorer chậm; ước tính theo số phiên ~60 và vài MB S3: dưới 1 USD, chưa kiểm hóa đơn).
- Số mẫu cold start ít (3 đến 5 mỗi cấu hình, một phiên làm việc, từ một máy ở Việt Nam): dùng làm bậc độ lớn.

## 9. Tài nguyên đã tạo và trạng thái dọn

Xem bảng đầy đủ ở `spikes/agentcore-runtime-cors/RESOURCES.md`. Tóm tắt: S3 bucket `yofina-spike-rt-code-*`, IAM role `yofina-spike-rt-exec`, Cognito user pool + 2 client + 2 user, 2 AgentCore Runtime (`yofina_spike_rt_agui` V1, `yofina_spike_rt_agui_v2` V2) kèm endpoint DEFAULT và workload identity tự sinh, 2 log group runtime. Trạng thái dọn: **đã xóa hết và đã liệt kê lại để xác nhận (02:26Z)**: 0 runtime, 0 workload identity, 0 log group, bucket 404, role `NoSuchEntity`, 0 user pool. Không còn gì sót; không bật Transaction Search, không bootstrap CDK, không tạo access key. Thư mục `build/` (gói zip, wheel) và `web/node_modules` đã xóa khỏi spike (tạo lại theo `README.md`).
