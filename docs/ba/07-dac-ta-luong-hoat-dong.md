# Đặc tả luồng hoạt động của ứng dụng

> Viết ngày 24/11/2026, đối chiếu với code trên nhánh `main`: `agent/`, `gateway/tools/ledger/`, `pipelines/forecast/`, `contracts/`, ADR-0002, ADR-0003.
> Mục đích: hiểu ứng dụng vận hành ra sao từ đầu tới cuối, và có sẵn nguyên liệu để vẽ diagram. Mỗi luồng có một sơ đồ **Mermaid**. GitHub và VS Code (có extension Markdown Preview Mermaid) hiển thị được trực tiếp; dán vào [mermaid.live](https://mermaid.live) để sửa hoặc xuất PNG/SVG.

**Trạng thái mỗi luồng:**
- **Đang chạy**: đã code và deploy (phase 1–2).
- **Thiết kế**: có trong plan, chưa code (phase 3–5); vẽ theo proposal §10 và file phase.

**Mã quy tắc** (BR-xx, FR-x) trỏ về [02-business-rules.md](02-business-rules.md) và [03-functional-requirements.md](03-functional-requirements.md).

## 1. Bức tranh tổng thể

### 1.1 Các tác nhân

| Tác nhân | Vai trò |
|---|---|
| Người dùng / giám khảo | Dùng web app trên điện thoại; là người **duy nhất** được phép duyệt mọi thay đổi số dư |
| Agent (AI) | Hiểu câu hỏi, gọi tool, viết câu trả lời ngắn, **đề nghị** hành động. Không tự tính số, không tự ghi |
| Engine tất định | Sổ cái, dự báo, Monte Carlo, kiểm tra số dư, luật nghiệp vụ. Mọi con số đến từ đây |
| Job nền | Pipeline sự kiện (sau mỗi giao dịch) và batch đêm (02:00) |
| Đội vận hành (`ops`) | Xem trace (phase 5) |

### 1.2 Ba đường vào hệ thống

Ứng dụng có **ba đường vào**. Đây là điểm cần nắm trước khi vẽ bất kỳ luồng nào:

| Đường | Ai khởi động | Đi qua | Dùng cho |
|---|---|---|---|
| **A. Màn hình (REST)** | Người dùng bấm trên giao diện | API Gateway HTTP API (JWT) → Lambda `ledger` → Aurora | Xem số dư, hũ, dự báo; **mọi thao tác ghi** (luôn qua xác nhận) |
| **B. Chat (agent)** | Người dùng gõ câu hỏi | AgentCore Runtime (agent) → AgentCore Gateway (interceptor + Cedar) → Lambda tool → Aurora | Hỏi đáp; agent **chỉ đọc và đề nghị**. Ghi thật vẫn quay về đường A |
| **C. Nền (không có người)** | Sự kiện giao dịch, lịch 02:00 | EventBridge → SQS → Lambda; Scheduler → Step Functions → Lambda | Tính lại dự báo; về sau thêm phân loại, điểm chống chịu, bản tin |

```mermaid
flowchart LR
    U(["Người dùng<br/>web mobile"])
    subgraph FE["Frontend - Amplify, React SPA"]
        SCR["Màn hình<br/>Tổng quan, Hũ, Chuyển tiền, Nghĩa vụ"]
        CHAT["Màn chat<br/>AG-UI qua SSE"]
    end
    COG["Cognito<br/>access token JWT"]
    subgraph A["Đường A - REST"]
        API["API Gateway HTTP API<br/>JWT authorizer"]
        LED["Lambda ledger<br/>sổ cái, xác nhận, xem trước"]
    end
    subgraph B["Đường B - Agent"]
        RT["AgentCore Runtime<br/>agent Strands"]
        GW["AgentCore Gateway<br/>interceptor + Cedar"]
        LLM["Bedrock<br/>model nhỏ, model lớn"]
    end
    subgraph C["Đường C - Nền"]
        BUS["EventBridge yofina-bus"]
        SQS["SQS + DLQ"]
        EVT["Lambda on-transaction"]
        SCH["Scheduler 02:00 -> Step Functions"]
        BATCH["Lambda forecast-batch<br/>dự báo + Monte Carlo"]
    end
    DB[("Aurora PostgreSQL<br/>RLS theo người dùng")]
    DDB[("DynamoDB<br/>jti token, idempotency, đếm lượt model")]

    U --> SCR & CHAT
    SCR -- đăng nhập --> COG
    SCR -- "Bearer token" --> API --> LED --> DB
    CHAT -- "Bearer token" --> RT
    RT --> LLM
    RT -- "MCP tool call" --> GW --> LED
    GW --> FTOOL["Lambda forecast tool"] --> DB
    LED -- "transaction.recorded" --> BUS --> SQS --> EVT --> BATCH
    SCH --> BATCH --> DB
    LED --- DDB
    EVT --- DDB
    RT --- DDB
```

### 1.3 Ba lớp bảo vệ danh tính (áp dụng cho mọi luồng có dữ liệu người dùng)

1. **JWT**: Runtime và HTTP API chỉ nhận access token Cognito hợp lệ.
2. **Interceptor của Gateway** ghi đè `user_id` bằng `sub` trong token. Agent không tự điền được `user_id` của người khác.
3. **Cedar** kiểm `user_id == principal.id` và hạn mức số tiền; **Aurora RLS** lọc theo người dùng ở tầng DB.

## 2. Danh mục luồng

| Mã | Luồng | Đường | Trạng thái | FR |
|---|---|---|---|---|
| L01 | Đăng nhập, mở phiên, làm nóng agent | A, B | Đang chạy | — |
| L02 | Onboarding tài khoản trắng | A | Đang chạy; 26/11 kiểm trên app với tài khoản tạm: 3 hũ mặc định 42/33/25, kê khai trọ và điện ra đề xuất 36/39/25 | FR1 |
| L03 | Xem Tổng quan và Chi tiết hũ (đọc, độ tươi dự báo) | A | Đang chạy | FR1, FR3 |
| L04 | **Ghi từ màn hình: xem trước → xác nhận → thực hiện** | A | Đang chạy | FR1, FR12 |
| L05 | Một lượt chat (router → tool → khối UI → câu trả lời) | B | Đang chạy | FR3, FR12 |
| L06 | **Agent đề nghị chuyển hũ, người dùng duyệt** | B → A | Đang chạy | FR12 |
| L07 | Lương về và chia lương | A | Đang chạy | FR1 |
| L08 | Mua bằng trả sau, sinh nghĩa vụ | A | Đang chạy | FR4 |
| L09 | Tính lại dự báo sau giao dịch (sự kiện) | C | Đang chạy | FR3 |
| L10 | Batch đêm | C | Đang chạy: dự báo, hồ sơ hành vi, điểm gãy và sinh lại lộ trình, bản tin | FR3, FR8, FR10, FR13 |
| L11 | Suy giảm khi AI lỗi hoặc chạm trần | B | Đang chạy | NFR-15 |
| L12 | Đặt lại dữ liệu demo | A | Đang chạy | — |
| L13 | Hỏi "nếu thì" (harness đầy đủ, có Verifier) | B | Đang chạy (phase 3, đóng 23/11) | FR5 |
| L14 | Kiểm tra trước khi quẹt | A, B | Đang chạy (phase 3); dải "sát" hẹp (C-02) | FR6 |
| L15 | Phân hũ tự động và hỏi gộp | C | Đang chạy (phase 4, đóng 24/11) | FR2 |
| L16 | Sinh và sinh lại lộ trình | B, C | Đang chạy (phase 4); lập được trong chat | FR8 |
| L17 | Nạp ảnh và CSV | A, C | Đã deploy (phase 5, chưa đóng); có quy đổi ngoại tệ | FR9 |
| L18 | Nhắc chủ động và bản tin | C | Đã deploy (phase 5, chưa đóng) | FR13 |
| L19 | **Chia tiền dư theo thứ tự ưu tiên, trích quỹ dồn, theo dõi hũ đệm** | A, C | Một phần 26/11: thứ tự bù khi đề xuất tỷ lệ (BR-65), khoản Quỹ dồn tính một lần khi kê khai (BR-66), bộ tối ưu giữ phần chia của hũ đệm chưa tới đích tự tính (BR-64 một phần); hiện đích và khóa mềm hũ đệm (BR-64), cổng hũ dài hạn (BR-68), mốc Quỹ dồn hoãn; giữ phần chia Quỹ dồn có khoản sắp cần: issue #44 | FR3, FR7, FR8 |
| L20 | **Gợi ý chuyển giai đoạn sống** | C → A | Hoãn 26/11 (BR-70, BR-71) | FR8 |

## 3. Các luồng đang chạy

### L01 — Đăng nhập, mở phiên, làm nóng

1. Người dùng đăng nhập Cognito (tự đăng ký đã tắt; dùng tài khoản demo) và nhận access token.
2. Frontend gọi `GET /overview` để dựng Tổng quan (xem L03).
3. Khi mở màn chat, frontend tạo `conversation_id` (UUID, dùng làm session id của Runtime) và gửi một lượt **làm nóng** (`forwardedProps.warmup`). Lượt này không gọi model hay tool, chỉ để microVM khởi động trước, vì phiên lạnh mất khoảng 2 giây tới event đầu, còn phiên ấm khoảng 0,3 giây.
4. Runtime V2 **ghim phiên theo người dùng**: người khác dùng session id này sẽ bị từ chối (403). Hai request cùng phiên chạy song song bị từ chối (409).

### L02 — Onboarding tài khoản trắng

```mermaid
flowchart TD
    S([Đăng nhập lần đầu]) --> P{Đã có hồ sơ?}
    P -- Có --> OV[Tổng quan]
    P -- Chưa --> O1["O1: nhập lương thực nhận<br/>và ngày nhận (bắt buộc)"]
    O1 --> CF["Xác nhận (L04)<br/>tool update_profile"]
    CF --> CR["Server tạo hồ sơ, 2 hũ hệ thống<br/>và 3 hũ mặc định: Chi hằng ngày,<br/>Nghĩa vụ, Dự phòng (từ 26/11)"]
    CR --> FC["Tính dự báo lần đầu<br/>nhãn: ước lượng ban đầu"]
    FC --> O2["O2: chia lương vào các hũ (bỏ qua được)<br/>sửa tỷ lệ, tổng = 100%, save_jars"]
    O2 --> O3["O3: Chi phí cố định (bỏ qua được)<br/>khai nghĩa vụ, khoản biết trước"]
    O3 --> SP["POST /jars/split-proposal<br/>thẻ đề xuất tỷ lệ, duyệt qua save_jars (L04)"]
    SP --> OV
```

- Quy tắc: BR-01 (chỉ hai trường bắt buộc), BR-04, BR-05, BR-29, BR-78 (tỷ lệ Nghĩa vụ theo số đã khai). Bỏ qua O3 thì giữ 42/33/25 và thẻ hũ ghi "chưa có số khai". Câu hỏi giai đoạn sống (BR-70) **hoãn 26/11**. Bộ 7 hũ cũ chỉ còn là hũ tự thêm (cuối [B2a](02-business-rules.md#b2a-cơ-cấu-hũ-theo-mục-đích-và-giai-đoạn-sống-đề-xuất-2411)).
- Onboarding cũng là một thao tác ghi, nên vẫn đi qua xác nhận bằng token.

### L03 — Xem màn hình (đọc) và độ tươi của dự báo

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant FE as Frontend
    participant API as HTTP API + ledger
    participant DB as Aurora
    participant FB as Lambda forecast-batch

    U->>FE: Mở Tổng quan
    FE->>API: GET /overview
    API->>DB: app_get_overview (1 lệnh gọi)
    DB-->>API: hồ sơ, hũ, tóm tắt dự báo, hạn mức,<br/>nghĩa vụ sắp đến hạn, lương chờ, giao dịch gần đây
    alt Dự báo đã cũ (quá 1 giờ hoặc đã sang ngày mô phỏng khác)
        API-)FB: Kích hoạt tính lại ở nền (không chờ)
        API-->>FE: Dữ liệu + forecast.stale = true
        FE->>API: Đọc lại có giới hạn tới khi có bản mới
    else Còn tươi
        API-->>FE: Dữ liệu (p95 khoảng 17 ms phía Lambda)
    end
    U->>FE: Mở Chi tiết hũ Ăn uống
    FE->>API: GET /forecasts/an_uong
    alt Dự báo đã cũ
        API->>FB: Tính lại đồng bộ (1–2 giây)
        FB->>DB: Ghi forecasts, forecast_runs
        API-->>FE: Dự báo mới
    else Còn tươi
        API-->>FE: Dự báo: dải P10–P90, P50, ngày cạn,<br/>trạng thái, nhãn tin cậy
    end
```

- Vì sao hai màn xử lý khác nhau: Tổng quan phải nhanh nên chỉ kích hoạt tính ở nền; Chi tiết hũ chỉ xem một hũ, nên chờ 1–2 giây để có số mới là chấp nhận được.
- **Ngày nghiệp vụ** luôn là ngày mô phỏng của tài khoản (`app_today`, ADR-0003), không phải ngày thật.

### L04 — Ghi từ màn hình: xem trước → xác nhận → thực hiện (luồng lõi)

Mọi thao tác làm đổi số dư hoặc hồ sơ đều đi qua luồng này: chi tiêu, chuyển tiền, chuyển hũ, mua trả sau, chia lương, sửa hồ sơ, sửa hũ, khai nghĩa vụ, gán hũ.

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant FE as Frontend
    participant L as ledger (REST)
    participant J as DynamoDB jti
    participant DB as Aurora
    participant BUS as EventBridge

    U->>FE: Nhập số tiền, chọn hũ, bấm "Tiếp tục"
    FE->>L: POST /confirmations {tool, params}
    L->>L: Chuẩn hóa tham số, kiểm nghiệp vụ<br/>(hũ tồn tại, đủ số dư, hạn mức, trần)
    alt Vi phạm nghiệp vụ
        L-->>FE: Lỗi 422 kèm lý do, nút bị khóa
    else Hợp lệ
        L-->>FE: Token ký HMAC (hạn 2 phút) + bản xem trước<br/>số dư trước/sau, phí, hạn mức còn lại
    end
    FE->>U: Màn "Xem lại" hiển thị bản xem trước
    U->>FE: Bấm "Xác nhận"
    FE->>L: POST /actions {tool, params, confirm_token}
    L->>L: Kiểm chữ ký, hạn, tool, sub, hash tham số
    L->>J: Ghi jti (có điều kiện: chưa từng dùng)
    alt Token sai, hết hạn, đã dùng, tham số bị đổi
        L-->>FE: 403/409 TOKEN_INVALID, TOKEN_EXPIRED,<br/>TOKEN_REUSED, PARAMS_MISMATCH
    else Hợp lệ
        L->>DB: 1 transaction: sổ cái + audit_events
        L-)BUS: transaction.recorded (sau commit)
        L-->>FE: Khối receipt (biên nhận)
        FE->>U: Biên nhận, số dư đổi ngay
        FE->>L: Đọc lại dự báo tới khi theo kịp (tối đa 60 giây)
    end
```

Điểm then chốt:
- **Token gắn chặt với đúng tham số đã hiển thị.** Đổi một đồng sau khi xem trước thì hash lệch và bị từ chối (`PARAMS_MISMATCH`).
- **Token chỉ dùng được một lần**, vì `jti` được ghi có điều kiện vào DynamoDB.
- **Bản xem trước do server tính.** Frontend không tự tính phí hay số dư (BR-47).
- **Không có AI trên đường ghi.**

### L05 — Một lượt chat

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant FE as Frontend (AG-UI)
    participant RT as Agent (Runtime)
    participant R as Router (model nhỏ)
    participant GW as Gateway<br/>interceptor + Cedar
    participant T as Lambda tool
    participant W as Writer (model nhỏ)

    U->>FE: "Hũ ăn uống còn trụ được bao lâu?"
    FE->>RT: POST /invocations (toàn bộ messages, traceparent)
    RT-->>FE: RUN_STARTED
    RT->>R: Phân loại ý định (JSON ép tool)
    R-->>RT: forecast_lookup, jar_text = "ăn uống"
    RT->>GW: ledger___get_jar_balances
    GW->>GW: Ghi đè user_id = sub, Cedar kiểm
    GW->>T: Gọi Lambda
    T-->>RT: Danh sách hũ (để ánh xạ "ăn uống" -> an_uong)
    RT->>GW: forecast___get_forecast {jar: an_uong}
    GW->>T: Gọi Lambda
    T-->>RT: Dữ liệu dự báo
    RT-->>FE: ACTIVITY_SNAPSHOT: khối forecast_timeline<br/>(số do code dựng, AI không chạm)
    RT->>W: Bản gọn (trạng thái, ngày cạn, số ngày tới lương)
    W-->>RT: 1–2 câu
    RT->>RT: Kiểm số trong câu có căn cứ trong bản gọn
    RT-->>FE: TEXT_MESSAGE (câu trả lời)
    RT->>GW: ledger___save_turn (lưu khối để phát lại)
    RT-->>FE: RUN_FINISHED {trace_id, intent, degraded, model_calls, tool_calls}
```

**Các ý định router hiện hỗ trợ:**

| Ý định | Tool gọi | Khối UI | Lượt model tối đa |
|---|---|---|---|
| `balance_lookup` | `get_jar_balances` | `jar_summary` | 2 |
| `transactions_lookup` | `get_jar_balances` + `query_transactions` | danh sách giao dịch | 2 |
| `forecast_lookup` | `get_jar_balances` + `get_forecast` | `forecast_timeline` | 2 |
| `move_between_jars` | `get_jar_balances` + `move_between_jars` **không token** | `confirm` (xem L06) | 2 |
| `out_of_scope` | không | `notice` + câu nói rõ giới hạn | 1 |
| `chitchat` | không | câu trả lời | 1 |

**Giới hạn mỗi lượt:** 60 giây, 4 lượt gọi model, 4 tool call. Khối UI luôn đến **trước** văn bản.

### L06 — Agent đề nghị, người dùng duyệt (human-in-the-loop)

Đây là luồng thể hiện rõ nhất cơ chế **con người duyệt trước khi hành động** (xem [mục 6](#6-cơ-chế-vận-hành-có-phải-human-in-the-loop-không)).

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant FE as Frontend
    participant RT as Agent
    participant GW as Gateway + ledger tool
    participant L as ledger (REST)

    U->>FE: "Chuyển 200 nghìn từ Giải trí sang Ăn uống"
    FE->>RT: Lượt chat
    RT->>GW: move_between_jars {from, to, amount} KHÔNG có token
    GW-->>RT: NEEDS_CONFIRMATION + tham số chuẩn hóa,<br/>params_hash, xem trước, hạn đề nghị
    RT-->>FE: Khối confirm (đúng thứ sẽ được ký)
    RT-->>FE: "Bạn bấm Xác nhận để chuyển nhé"
    Note over RT: Lượt của agent KẾT THÚC tại đây.<br/>Agent không chờ, không giữ quyền ghi.
    alt Người dùng bấm "Xác nhận"
        U->>FE: Bấm
        FE->>L: POST /confirmations (kèm confirm_block_id)
        L-->>FE: Token
        FE->>L: POST /actions + token
        L-->>FE: receipt
        FE->>RT: Lượt sau kèm dòng hệ thống "đã chuyển"
    else Người dùng bấm "Không"
        U->>FE: Bấm
        FE->>L: POST /confirmations/cancel
        L-->>FE: Đề nghị: cancelled
    else Để quá hạn
        Note over L: Đề nghị hết hạn, server từ chối cấp token.<br/>Người dùng phải hỏi lại.
    end
```

**Vòng đời của một đề nghị:**

```mermaid
stateDiagram-v2
    [*] --> pending: Agent tạo khối confirm
    pending --> done: Người dùng xác nhận, POST /actions thành công
    pending --> cancelled: Người dùng bấm Không
    pending --> expired: Quá expires_at
    done --> [*]
    cancelled --> [*]
    expired --> [*]
    note right of done: Gửi lại cùng đề nghị thì 409 ALREADY_APPLIED
```

### L07 — Lương về và chia lương

```mermaid
flowchart TD
    IN["Tiền vào loại lương<br/>record_transaction, tx_type = salary"] --> OI["Ghi vào hũ Tiền vào khác"]
    OI --> SE["Tạo sự kiện lương: pending<br/>tính độ lệch so với lương đã khai"]
    SE --> DEV{"Lệch vượt ngưỡng?"}
    DEV -- Có --> ASK["Hỏi: cập nhật lương đã khai?"]
    DEV -- Không --> CARD
    ASK --> CARD["Thẻ 'Lương đã về' trên Tổng quan"]
    CARD --> D{"Người dùng chọn<br/>(qua L04)"}
    D -- "Chia vào hũ" --> SP["Chia theo tỷ lệ, làm tròn xuống,<br/>dư vào hũ tỷ lệ lớn nhất"]
    D -- "Giữ ở Tiền vào khác" --> KEEP["Trạng thái: kept_other"]
    SP --> CONF["Trạng thái: confirmed<br/>phát salary.confirmed"]
    CONF --> FC["Tính lại dự báo (L09)"]
```

- Quy tắc: BR-10 đến BR-13. Tiền vào không phải lương chỉ nằm ở Tiền vào khác và **không tính là thu nhập**.
- *Đề xuất 24/11:* chia lương vẫn theo tỷ lệ (BR-11). Khi có tiền dư ngoài tỷ lệ (lương cao hơn khai, hũ chi theo kỳ còn thừa cuối kỳ), phần dư đi theo thứ tự BR-65, xem L19.

### L08 — Mua bằng trả sau, sinh nghĩa vụ

```mermaid
flowchart TD
    B["Chi tiêu, nguồn = Trả sau (mô phỏng)"] --> LIM{"Dư nợ + gốc<br/>vượt hạn mức?"}
    LIM -- Có --> REJ["Từ chối: CREDIT_LIMIT_EXCEEDED"]
    LIM -- Không --> OB{"Đã có nghĩa vụ trả sau<br/>cho kỳ đến hạn này?"}
    OB -- Chưa --> NEW["Tạo nghĩa vụ: gốc + phí 33.000 ₫<br/>hạn = ngày 5 kế tiếp"]
    OB -- Có --> ADD["Cộng dồn gốc vào nghĩa vụ đó<br/>(phí chỉ tính 1 lần)"]
    NEW & ADD --> NOJ["Số dư hũ KHÔNG đổi,<br/>hạn mức còn lại giảm theo gốc"]
    NOJ --> MK["Mốc 'Phải trả dd/mm' trên dòng thời gian dự báo"]
    MK --> PAY["Đến hạn: trả từ hũ trả<br/>-> nghĩa vụ chuyển 'đã trả'"]
```

- Quy tắc: BR-22 đến BR-26. Bản xem trước ở bước "Xem lại" hiện "Phải trả ngày dd/mm: trước → sau" và "Hạn mức còn lại: trước → sau".
- Hũ trả (26/11, issue #39, `resolve_obligation_pay_jar`): hũ đã lưu, hũ người dùng chọn, hũ Nghĩa vụ, rồi hũ `obligation` đầu tiên. Ví không có hũ nào như vậy thì phải chọn hũ trả trước khi mua (agent và màn chuyển tiền hỏi; C-07). Ví demo của `minh` dùng ngày đến hạn 5 như mọi ví; khoản đến hạn đúng ngày lương tính là trước lương, trả bằng số dư trước khi lương về (BR-22, chốt 26/11).

### L09 — Tính lại dự báo sau giao dịch (sự kiện)

```mermaid
sequenceDiagram
    autonumber
    participant L as ledger
    participant BUS as EventBridge yofina-bus
    participant Q as SQS yofina-forecast-events<br/>(+ DLQ có alarm)
    participant E as Lambda on-transaction
    participant ID as DynamoDB idempotency
    participant F as Engine dự báo
    participant DB as Aurora

    L-)BUS: transaction.recorded {event_id, user, jar}
    BUS->>Q: Đẩy vào hàng đợi
    Q->>E: Gom lô theo người dùng
    E->>ID: Đã xử lý event_id này chưa?
    alt Đã xử lý (gửi trùng)
        E-->>Q: Bỏ qua, không tính lần hai
    else Chưa
        E->>F: Đường nhanh: chạy lại Monte Carlo cho hũ liên quan<br/>với số dư mới (không đủ điều kiện thì chạy đầy đủ)
        F->>DB: Ghi forecasts, forecast_runs (1 transaction)
        F-)BUS: forecast.updated
    end
```

- Số đo: giao dịch 200.000 ₫ thì Chi tiết hũ có dự báo mới sau khoảng **3 giây** (mục tiêu dưới 60 giây).
- Lỗi xử lý thì vào DLQ và bật alarm.

### L10 — Batch đêm

```mermaid
flowchart LR
    SCH["EventBridge Scheduler<br/>02:00 giờ VN"] --> SF["Step Functions yofina-nightly"]
    SF --> LU["list_users"]
    LU --> MAP["Map, song song 3"]
    MAP --> RU["run_user: đọc lịch sử + lịch lương + nghĩa vụ<br/>-> dự báo + ACI + Monte Carlo"]
    RU --> CHK{"Kết quả đúng hợp đồng?"}
    CHK -- Không --> SKIP["Không ghi, ghi log lỗi,<br/>người khác vẫn chạy tiếp"]
    CHK -- Có --> W["Ghi forecasts, forecast_runs,<br/>giữ 6 lần chạy gần nhất"]
    W --> SUM["summarize"]
```

- Hiện batch chỉ làm dự báo. Phase 4–5 thêm vào cùng batch: điểm chống chịu, hồ sơ hành vi, phát hiện điểm gãy và sinh lại lộ trình, cổng nhắc và bản tin.
- Số đo: 6 tài khoản, khoảng 4 giây mỗi lần chạy.

### L11 — Suy giảm khi AI lỗi hoặc chạm trần

```mermaid
flowchart TD
    Q["Câu hỏi"] --> R{"Router model nhỏ<br/>trả lời được?"}
    R -- Có --> INT["Ý định"]
    R -- "Lỗi, chậm, chạm trần ngày" --> FB["Bộ phân loại luật dự phòng<br/>(từ khóa chung, không theo câu mẫu)"]
    FB --> INT
    INT --> TOOL["Gọi tool: số liệu vẫn là thật"]
    TOOL --> BLK["Khối số liệu vẫn hiện"]
    BLK --> WR{"Writer viết được câu?"}
    WR -- Có --> TXT["Câu trả lời"]
    WR -- Không --> NOT["Khối notice: chế độ rút gọn"]
    TXT & NOT --> FIN["RUN_FINISHED, degraded = true/false"]
```

- Nguyên tắc: **AI có thể vắng, nhưng số không bao giờ sai hay biến mất**. Model đi theo chuỗi dự phòng khi bị giới hạn tốc độ hoặc từ chối truy cập. Chạm trần ngày thì không rơi sang model khác mà rơi về thẻ số liệu tất định.

### L12 — Đặt lại dữ liệu demo

1. Người dùng vào Hồ sơ và bấm "Đặt lại dữ liệu", gọi `POST /demo/reset`.
2. Server chỉ xóa dữ liệu của **chính người gọi**, rồi sinh lại persona theo seed, nạp vào bộ hũ demo (từ 26/11: Chi hằng ngày, Nghĩa vụ, Dự phòng cộng hũ tự thêm Ăn uống, Đi lại, Giải trí, Du lịch, Đầu tư; `minh` 8 hũ), không vào bộ mặc định của onboarding (BR-62).
3. Ngày mô phỏng quay về ngày neo 21/11/2026; dự báo được tính đồng bộ ngay.
4. Mất khoảng 6 giây. Trả `forecast_ready: true` để mở app là có số.

## 4. Các luồng phase 3–5 (viết lúc còn là thiết kế; nay đã chạy, xem trạng thái ở mục 2)

### L13 — Hỏi "nếu thì" (harness đầy đủ)

```mermaid
flowchart TD
    Q["'Nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao'"] --> L0["L0 Cổng vào: JWT, guardrail,<br/>chặn prompt injection"]
    L0 --> L1{"L1 Router"}
    L1 -- "Ngoài phạm vi" --> OOS["Nói rõ giới hạn + gợi ý việc làm được"]
    L1 -- "Tra cứu đơn giản" --> FAST["Đường nhanh 1 tool (L05)"]
    L1 -- "What-if" --> PAR{"Đủ tham số?"}
    PAR -- Thiếu --> ASK1["Hỏi lại ĐÚNG MỘT câu"] --> PAR
    PAR -- Đủ --> L2["L2 Planner dựng ScenarioSpec"]
    L2 --> TOOLS["Song song: get_forecast,<br/>get_obligations, get_fee_schedule"]
    TOOLS --> SIM["run_scenario: Monte Carlo trên dự báo<br/>+ lịch nghĩa vụ"]
    SIM --> CONF{"Độ tin cậy thấp?"}
    CONF -- Có --> WARN["Gắn cảnh báo, mời nạp thêm dữ liệu"]
    CONF -- Không --> AN
    WARN --> AN["L3 Analyst: diễn giải + 2–3 phương án"]
    AN --> VER{"L4 Verifier: số khớp tool?<br/>Đạt luật phù hợp?"}
    VER -- "Sai, còn lượt (tối đa 2)" --> AN
    VER -- "Sai, hết lượt" --> DET["Chỉ trả thẻ số liệu tất định"]
    VER -- Đạt --> COMP["L5 Composer: khối trước, văn bản sau,<br/>nhãn AI, trace_id, bảng Vì sao"]
    COMP --> ACT{"Người dùng chọn phương án<br/>có đổi số dư?"}
    ACT -- Có --> HITL["L06: đề nghị -> xác nhận -> token"]
    ACT -- Không --> MEM["Ghi bộ nhớ + trace"]
    HITL --> MEM
```

Giới hạn: mỗi lượt tối đa 4 lượt gọi model (1 router + 2 planner + 1 diễn giải); trọn câu p95 dưới 8 giây.

### L14 — Kiểm tra trước khi quẹt

```mermaid
flowchart TD
    IN["Nhập số tiền và nguồn ở màn chuyển tiền"] --> AC["affordability_check (engine tất định)<br/>số dư hũ, dự báo P50/P90, nghĩa vụ sắp đến hạn"]
    AC --> SRC{"Nguồn trả?"}
    SRC -- "Tiền trong hũ" --> J{"Kết quả"}
    J -- Đủ --> G["Thẻ XANH"]
    J -- "Cạn sớm N ngày" --> Y["Thẻ VÀNG"]
    J -- "Hụt M đồng trước kỳ lương" --> RD["Thẻ ĐỎ"]
    SRC -- "Trả sau" --> TC["Tổng chi phí thật = gốc + phí (+ phạt nếu trễ)<br/>mô phỏng tháng sau: hũ nào hụt"]
    TC --> DTI{"Nghĩa vụ / thu nhập vượt ngưỡng?"}
    DTI -- Có --> RD2["Thẻ ĐỎ + 'không khuyến khích'"]
    DTI -- Không --> YG["Thẻ VÀNG/XANH + ngày đến hạn"]
    G & Y & RD & RD2 & YG --> EXP{"Model nhỏ viết 2 câu<br/>trong 2 giây?"}
    EXP -- Được --> OPT["Thẻ + giải thích + phương án:<br/>hoãn, đổi hũ, chia nhỏ, trả ngay"]
    EXP -- "Lỗi hoặc chậm" --> ONLY["Chỉ thẻ số liệu"]
    OPT & ONLY --> CH{"Người dùng chọn"}
    CH -- "Vẫn trả" --> L04["L04 xác nhận -> ghi -> L09"]
    CH -- "Phương án khác" --> L06b["Đề nghị -> xác nhận"]
    CH -- "Bỏ qua" --> FBK["Ghi phản hồi, bỏ qua nhiều lần thì giảm nhắc"]
```

### L15 — Phân hũ tự động và hỏi gộp

```mermaid
flowchart TD
    TX["Giao dịch chi chưa có hũ"] --> S0{"Bước 0: loại giao dịch rõ?<br/>(hóa đơn, nạp ĐT, QR cửa hàng)"}
    S0 -- Có --> ASG["Gán hũ"]
    S0 -- Không --> S1{"Bước 1: có luật<br/>của người dùng?"}
    S1 -- Có --> ASG
    S1 -- Không --> S2["Bước 2: tìm giao dịch tương tự<br/>đã có nhãn (embedding)"]
    S2 --> S3["Bước 3: model nhỏ<br/>(lời nhắn, số tiền, giờ, tín hiệu lặp lại)"]
    S3 --> CONF{"Độ tin cậy"}
    CONF -- "≥ 0,9" --> ASG
    CONF -- "0,6 đến < 0,9" --> REV["Gán + đưa vào 'Xem lại'"]
    CONF -- "< 0,6" --> WORTH{"Đáng hỏi?<br/>(đủ lớn hoặc sẽ lặp lại)"}
    WORTH -- Không --> OTHER["Hũ 'Khác', không hỏi<br/>(không làm, #28)"]
    WORTH -- Có --> UNC["Chưa phân loại -> hỏi gộp 1 lần/ngày,<br/>mỗi khoản 2 gợi ý"]
    REV & UNC --> FIX["Người dùng sửa:<br/>'chỉ lần này' hoặc 'luôn luôn cho người này'"]
    FIX --> RULE["Tạo luật -> lần sau đi thẳng bước 1"]
    ASG & REV --> UPD["Cập nhật số dư hũ -> L09"]
```

- Bước 0 chọn hũ theo `yofina_core.wallet.transaction_jar` (26/11): ví có hũ riêng khớp loại giao dịch thì hũ riêng nhận (ví demo: Ăn uống, Đi lại, Giải trí, Du lịch); không có thì vào Chi hằng ngày (khoản chi) hoặc Nghĩa vụ (hóa đơn, thuê bao). Bốn loại `bnpl_purchase`, `transfer_person`, `qr_other`, `other_expense` không có hũ mặc định nên đi tiếp sang bước 1–3 trên mọi ví ([đo ví 3 hũ](../research/2026-11-26-do-vi-ba-hu.md)).
- Nhánh hũ "Khác": **không làm** (chủ dự án chốt 26/11, issue #28 đóng; BR-18). Khoản nhỏ một lần đi theo ngưỡng tin cậy như mọi khoản.

### L16 — Sinh và sinh lại lộ trình

```mermaid
flowchart TD
    TRG["Kích hoạt: onboarding xong, lệch dự báo kéo dài 2 tuần,<br/>đổi mục tiêu/thu nhập, người dùng yêu cầu"] --> CTX["Gom ngữ cảnh: mục tiêu, dự báo, nghĩa vụ,<br/>hồ sơ hành vi, điểm yếu chống chịu, sở thích"]
    CTX --> RA["Roadmap Agent phác thảo giai đoạn"]
    RA --> LP{"optimize_allocation (LP)<br/>có nghiệm?"}
    LP -- Không --> RLX["Nới ràng buộc mềm 1 lần"] --> LP2{"Có nghiệm?"}
    LP2 -- Không --> HONEST["Nói thẳng chưa khả thi + 2 lựa chọn"]
    LP2 -- Có --> SUI
    LP -- Có --> SUI{"Cổng luật phù hợp"}
    SUI -- "Vi phạm, còn lượt" --> RA
    SUI -- "Vi phạm, hết lượt" --> DROP["Bỏ hành động vi phạm"] --> OUT
    SUI -- Đạt --> OUT["Lộ trình + lý do từng bước"]
    OUT --> REVIEW{"Người dùng duyệt TỪNG BƯỚC"}
    REVIEW -- "Chấp nhận bước có đổi số dư" --> L06c["L06: xác nhận -> token"]
    REVIEW -- Sửa --> VER["Lưu phiên bản mới, không sinh lại toàn bộ"]
    REVIEW -- "Từ chối hết" --> WHY["Hỏi 1 câu lý do -> bộ nhớ"]
```

Khoản chi lớn đơn lẻ (ngoại lai) **không** kích hoạt sinh lại lộ trình; chỉ điều chỉnh dự báo của kỳ này.

### L17 — Nạp ảnh và CSV

```mermaid
flowchart TD
    UP["Đồng ý nguồn -> tải tệp"] --> S3["S3 + SQS -> job nền, hiện tiến độ"]
    S3 --> TYPE{"Loại tệp"}
    TYPE -- Ảnh --> VIS["Model đọc ảnh -> JSON"]
    TYPE -- CSV --> CSV["Parser + model ánh xạ tên cột"]
    TYPE -- Khác --> ERR["Lỗi rõ, gợi ý định dạng"]
    VIS & CSV --> NORM["Chuẩn hóa + CHE thông tin định danh<br/>(nội dung tệp chỉ là dữ liệu)"]
    NORM --> DUP["Chống trùng với sổ cái"]
    DUP --> CLS["Phân loại 3 bước (L15)"]
    CLS --> RC{"Độ tin cậy từng dòng"}
    RC -- Cao --> ADD["Thêm vào sổ cái"]
    RC -- Thấp --> QUEUE["Hàng chờ: người dùng duyệt từng dòng"]
    ADD & QUEUE --> COV["Cập nhật điểm độ phủ -> tính lại dự báo"]
```

### L18 — Nhắc chủ động

- **Đang chạy**: thẻ chủ động trên Tổng quan chỉ nêu **một việc** (hũ rủi ro nhất, nghĩa vụ đến hạn trong 3 ngày, lương chờ xác nhận), có "Hỏi vì sao", "Để sau", "Ít nhắc loại này".
- **Thiết kế**: sau batch đêm, cổng nhắc kiểm hai điều: giá trị có đủ lớn không, và hôm nay đã nhắc chưa. Nếu qua cả hai thì gửi một bản tin, nếu không thì im lặng. Tối đa một lần mỗi ngày (BR-60).

### L19 — Chia tiền dư, trích quỹ dồn, theo dõi hũ đệm (đề xuất 24/11)

**Trạng thái 26/11:** một phần, xem dòng L19 ở mục 2 và BR-64 đến BR-68 ở [02 B2a](02-business-rules.md#b2a-cơ-cấu-hũ-theo-mục-đích-và-giai-đoạn-sống-đề-xuất-2411). Sơ đồ dưới là thiết kế đầy đủ.

```mermaid
flowchart TD
    S["Có tiền dư<br/>(lương cao hơn khai, cuối kỳ hũ chi còn thừa)"] --> O{"Nghĩa vụ đến hạn<br/>đã đủ tiền?"}
    O -- Chưa --> O1["Gợi ý bù hũ nghĩa vụ"]
    O -- Rồi --> B{"Hũ đệm đạt<br/>N tháng chi thiết yếu?"}
    B -- Chưa --> B1["Gợi ý nạp hũ đệm<br/>(không gợi ý mục tiêu, dài hạn)"]
    B -- Rồi --> K{"Quỹ dồn có ngày cần gần<br/>đang chậm tiến độ?"}
    K -- Có --> K1["Gợi ý trích theo kỳ<br/>= còn thiếu / số kỳ lương còn lại"]
    K -- Không --> G["Gợi ý cho hũ mục tiêu,<br/>rồi hũ dài hạn (nếu không có nợ quá hạn)"]
    O1 & B1 & K1 & G --> P["Bản xem trước, xác nhận (L04)"]
    P --> FC["Tính lại dự báo theo loại hũ (BR-73)"]
    W["Rút tiền khỏi hũ đệm"] --> WP["Xem trước kèm ảnh hưởng tới<br/>Điểm chống chịu, số ngày trụ được"] --> P
```

- Quy tắc: BR-63 đến BR-68, BR-73. Mọi bước chỉ là **gợi ý**; tiền chỉ di chuyển sau xác nhận (BC-04, BR-45).
- Ngày cần của quỹ dồn hiện thành mốc trên dòng thời gian dự báo, giống nghĩa vụ (BR-66).
- Hũ đệm và dài hạn **không tính là tiền có thể chi** trong L14 (BR-68).

### L20 — Gợi ý chuyển giai đoạn sống (đề xuất 24/11)

**Trạng thái 26/11:** hoãn cùng BR-70, BR-71 (mọi tài khoản mới nhận cùng 3 hũ mặc định).

```mermaid
flowchart TD
    N["Batch đêm (L10)"] --> SIG{"Có tín hiệu?<br/>lương tăng ổn định 2 kỳ,<br/>hũ đệm đạt mục tiêu,<br/>hết nghĩa vụ vay"}
    SIG -- Không --> X["Không làm gì"]
    SIG -- Có --> C["Thẻ gợi ý: so bộ hũ hiện tại<br/>với bộ của giai đoạn kế tiếp"]
    C --> U{"Người dùng"}
    U -- "Để sau, Ít nhắc" --> X
    U -- "Xem thay đổi" --> D["Từng thay đổi tỷ lệ, từng hũ mới:<br/>xem trước, xác nhận (L04)"]
```

- Quy tắc: BR-70, BR-71, BR-60 (tối đa một nhắc mỗi ngày). Hệ thống **không bao giờ tự đổi giai đoạn**.

## 5. Máy trạng thái của các đối tượng chính

**Sự kiện lương:**

```mermaid
stateDiagram-v2
    [*] --> pending: Lương về
    pending --> confirmed: Người dùng chọn chia vào hũ
    pending --> kept_other: Người dùng chọn giữ ở Tiền vào khác
    confirmed --> [*]
    kept_other --> [*]
```

**Nghĩa vụ:**

```mermaid
stateDiagram-v2
    [*] --> active: Người dùng khai, hoặc mua trả sau
    active --> active: Mua trả sau thêm cùng kỳ (cộng dồn)
    active --> active: Trả khoản lặp (dời hạn sang kỳ sau)
    active --> paid: Trả khoản một lần
    active --> deleted: Người dùng xóa (qua xác nhận)
    paid --> [*]
    deleted --> [*]
```

**Phân loại giao dịch (thiết kế, phase 4):**

```mermaid
stateDiagram-v2
    [*] --> chua_phan_loai: Chi chưa rõ hũ
    [*] --> da_gan: Tự gán (tin cậy cao) hoặc người dùng chọn hũ lúc trả
    chua_phan_loai --> da_gan: Người dùng trả lời hỏi gộp
    [*] --> xem_lai: Tin cậy trung bình
    xem_lai --> da_gan: Người dùng giữ nguyên hoặc sửa
    da_gan --> da_gan: Người dùng sửa -> tạo luật
```

## 6. Cơ chế vận hành có phải human-in-the-loop không?

**Trả lời ngắn: có, nhưng không phải ở mọi chỗ.** Yofina dùng **ba mức tham gia của con người** tùy theo rủi ro của từng quyết định. Đây là thiết kế có chủ đích, không phải "mọi thứ đều hỏi người dùng".

| Mức | Nghĩa | Ở đâu trong Yofina |
|---|---|---|
| **Human-in-the-loop** (con người duyệt **trước** khi hệ thống hành động) | Hệ thống dừng lại; không có xác nhận thì không làm | **Mọi thay đổi số dư và hồ sơ** (L04, L06): chuyển hũ, chi tiêu, trả sau, chia lương, sửa hồ sơ. Duyệt **từng bước** lộ trình (L16). Dòng nạp tin cậy thấp (L17). Khoản phân loại tin cậy thấp đáng hỏi (L15) |
| **Human-on-the-loop** (hệ thống tự làm, con người giám sát và sửa được) | Làm trước, người dùng xem lại và sửa sau | Phân loại tin cậy trung bình: tự gán + danh sách "Xem lại" (L15). Thẻ chủ động và bản tin, có "Ít nhắc loại này" (L18). Lộ trình tự sinh lại nhưng chờ duyệt (L16). Đội `ops` xem trace (FR15) |
| **Human-out-of-the-loop** (tự động hoàn toàn) | Không cần con người, vì không đổi tiền và có thể kiểm lại | Dự báo đêm và theo sự kiện (L09, L10); router chọn ý định; phân loại tin cậy cao; Verifier kiểm số và luật; chuyển sang chế độ suy giảm (L11) |

### 6.1 Khác gì với cách làm human-in-the-loop thông thường

Cách phổ biến trong framework agent là **interrupt/resume**: agent dừng giữa lượt, chờ người duyệt, rồi chạy tiếp. Phiên agent phải giữ nguyên trong lúc chờ. Yofina **không làm vậy** (ADR-0002), mà tách việc duyệt ra khỏi agent:

| | Interrupt/resume thông thường | Cách của Yofina |
|---|---|---|
| Agent khi chờ duyệt | Treo giữa lượt, giữ phiên | **Kết thúc lượt** ngay sau khi đưa đề nghị |
| Ai thực hiện việc ghi | Agent, sau khi được duyệt | **Server** (REST `ledger`), sau khi kiểm token |
| Bằng chứng người dùng đã duyệt | Cờ `approved` gửi lại cho agent | **Token ký HMAC dùng một lần**, gắn với người dùng, đúng tham số và hạn 2 phút |
| AI có thể tự duyệt không | Có rủi ro (prompt injection điền cờ) | **Không**: AI không bao giờ cầm token, và không nằm trên đường ghi |
| Đã kiểm | — | 13 ca tấn công bị chặn (bịa token, dùng lại, đổi tham số, token người khác, hết hạn…) |

Một câu để nói với giám khảo: **"AI đề xuất, con người quyết định, máy chủ thực thi, và AI không thể tự duyệt cho chính mình."**

### 6.2 Vòng phản hồi từ con người (human feedback loop)

Ngoài việc duyệt, người dùng còn **dạy** hệ thống qua các vòng sau:
- Sửa phân loại tạo thành luật ("luôn luôn cho người này"), lần sau tự đúng (L15).
- Bấm "Ít nhắc loại này" hoặc bỏ qua cảnh báo nhiều lần làm giảm tần suất nhắc (L14, L18).
- Từ chối lộ trình: hệ thống hỏi một câu lý do và ghi vào bộ nhớ (L16).
- Sở thích nói trong chat được ghi vào bộ nhớ dài hạn (FR10).

## 7. Gợi ý bộ diagram nên vẽ

| # | Diagram | Loại | Lấy từ | Dùng cho |
|---|---|---|---|---|
| 1 | Kiến trúc tổng thể 3 đường vào | Context / container (C4 mức 1–2) | Mục 1.2 | Slide kiến trúc |
| 2 | Xác nhận trước khi ghi | Sequence | L04 + L06 | Slide "an toàn", giải thích HITL |
| 3 | Một lượt chat, khối số trước văn bản | Sequence | L05 | Slide "AI không bịa số" |
| 4 | Ba mức tham gia của con người | Bảng hoặc phổ 3 mức | Mục 6 | Slide HITL |
| 5 | Ba nhịp chạy: đồng bộ, sự kiện, đêm | Swimlane | L05, L09, L10 | Slide vận hành |
| 6 | Hỏi "nếu thì" với Verifier | Flowchart | L13 | Slide harness |
| 7 | Kiểm tra trước khi quẹt | Flowchart | L14 | Slide tính năng F3 |
| 8 | Phân hũ 4 bước + 3 mức tin cậy | Flowchart | L15 | Slide phân loại |
| 9 | Vòng đời đề nghị, lương, nghĩa vụ | State | Mục 5 | Tài liệu kỹ thuật |
| 10 | Hành trình người dùng theo 6 cảnh demo | User journey | [demo-script](../plan/demo-script.md) | Video, slide mở đầu |
