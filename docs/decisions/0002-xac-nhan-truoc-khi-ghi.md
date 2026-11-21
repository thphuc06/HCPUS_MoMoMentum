# ADR-0002: Xác nhận trước khi ghi bằng token dùng một lần do server cấp

- **Trạng thái**: Đã chốt
- **Ngày**: 2026-11-21
- **Người/agent quyết định**: chủ dự án (duyệt kế hoạch tổng, [master-plan mục 2](../plan/master-plan.md#xác-nhận-trước-khi-ghi)); Claude Sonnet 5.5 viết ADR
- **Liên quan**: proposal §9 (Cedar cho tool ghi), FR12; [open-questions](../requirements/open-questions.md) (cơ chế xác nhận đã tick); [spike Gateway §5](../research/spike-agentcore-gateway-identity.md), [spike Strands §2.7, §3.2](../research/spike-strands-agui-local.md); [contracts/README.md](../../contracts/README.md)

## Bối cảnh

Mọi thay đổi số dư phải do người dùng xác nhận (FR12). Proposal §9 để Cedar cho phép tool ghi khi tham số có cờ xác nhận. Spike Gateway cho thấy cờ đó do LLM điền (kể cả bị prompt injection điều khiển), còn Cedar chỉ so sánh chuỗi, số, boolean: không kiểm được chữ ký, hạn dùng hay tính duy nhất. Spike Strands thử interrupt của AG-UI qua `FileSessionManager` cục bộ, nhưng chưa qua Runtime thật hay `AgentCoreMemorySessionManager`, và chưa ghép với token.

## Các lựa chọn đã cân nhắc

1. **Cờ `user_confirmed` do LLM điền, Cedar kiểm** (proposal) — giả mạo được; không chấp nhận.
2. **Interrupt/resume của AG-UI, LLM chuyển tiếp token xác nhận** — đã chạy cục bộ, nhưng phụ thuộc resume qua Runtime với session bền (chưa thử) và đưa token qua ngữ cảnh LLM.
3. **Token dùng một lần do server cấp; người dùng bấm nút thì UI tự gọi REST cấp token rồi gọi REST ghi** — LLM không nằm trên đường ghi.

## Quyết định

Chọn lựa chọn 3, tool ghi vẫn kiểm cùng token ở Gateway làm lớp thứ hai:

1. **Không có cờ xác nhận do LLM điền.** Agent chỉ tạo khối `confirm`.
2. Tool ghi (`ledger___move_between_jars`) được gọi **không có `confirm_token` thì không ghi**: trả `NEEDS_CONFIRMATION` kèm tham số đã chuẩn hóa, `params_hash`, bản xem trước số dư hai hũ và hạn của đề nghị. Agent dựng khối `confirm` từ kết quả đó (`build_confirm`); khối chứa đúng thứ sẽ được ký.
3. Người dùng bấm nút → frontend gọi `POST /confirmations` (HTTP API, JWT Cognito) → server xác thực, ghim `user_id = sub` từ JWT, chuẩn hóa lại tham số, kiểm nghiệp vụ, ký HMAC-SHA256 trên `{sub, tool, h = params_hash, exp, jti}`. Hạn token (mặc định đề xuất 2 phút) và secret ký lấy từ cấu hình và Secrets Manager, không gắn cứng.
4. Frontend gọi `POST /actions` kèm token → Lambda `ledger` kiểm chữ ký, hạn, tool, `sub`, hash tham số, và `jti` chưa dùng (`PutItem` có điều kiện vào DynamoDB `yofina-confirm-jti`, có TTL), rồi ghi trong một transaction, ghi `audit_events` và trả khối `receipt`. Mã lỗi: `NEEDS_CONFIRMATION`, `TOKEN_INVALID`, `TOKEN_EXPIRED`, `TOKEN_REUSED`, `PARAMS_MISMATCH` ([openapi.yaml](../../contracts/rest/openapi.yaml)).
5. Sau khi ghi, frontend chèn một dòng hệ thống vào hội thoại để agent biết việc đã làm. Hỏi lại một câu (màn H5) chỉ là một lượt hội thoại thường.
6. **Cách băm**: `params_hash = sha256(canonical_json({"tool", "params"}))` với `params` đã chuẩn hóa (chỉ `from_jar`, `to_jar`, `amount_vnd`; mã hũ chữ thường; tiền là số nguyên) và JSON chuẩn hóa là khóa sắp xếp, không khoảng trắng, UTF-8. `user_id` không nằm trong hash; ràng buộc người dùng nằm ở `sub` trong token. Cài ở `yofina_core.confirm`.
7. **Cedar giữ làm lớp phụ** cho đường qua Gateway: `has user_id && user_id == principal.id`, `amount_vnd <=` hạn mức, `has confirm_token`. Gateway không có đường ghi nào khác ngoài token này.
8. Interrupt/resume của AG-UI vẫn được thử ở phase 1 (mục "Chưa thử") nhưng luồng xác nhận **không phụ thuộc** vào nó.

## Hệ quả

- Dễ hơn: bằng chứng xác nhận không giả mạo được (13 ca của spike: tự điền cờ, bịa token, ký sai khóa, đổi tham số, replay, dùng token người khác, hết hạn đều bị từ chối); không cần resume qua Runtime; đường ghi không tốn lượt gọi model và không bị quota 10 request/phút làm chậm.
- Khó hơn: có thêm một đường vào Lambda `ledger` (HTTP API) và một bảng DynamoDB; frontend phải biết hai bước gọi; mã lỗi token phải khớp ở ba nơi (REST, kết quả tool, `notice`), nên có test so khớp.
- Phải làm: cài cấp/kiểm token ở `yofina_core.confirm` và đưa 13 ca của spike thành unit test (luồng B); test tấn công token ở mức tích hợp (tiêu chí hoàn thành 3 của phase 1); xoay khóa HMAC bằng hai khóa hợp lệ song song khi cần (chưa làm).
- Lệch proposal §9: Cedar không còn là cơ chế xác nhận.

## Nguồn đã tra

- [spike Gateway](../research/spike-agentcore-gateway-identity.md) §5 — 13 ca token; Cedar không kiểm được chữ ký.
- [spike Strands](../research/spike-strands-agui-local.md) §2.7, §3.2 — interrupt cục bộ chạy, chưa qua Runtime.
- [Phase 1](../plan/phases/phase-1-nen-va-lat-doc.md) — luồng B, C, D, E cài từng phần của cơ chế này.
