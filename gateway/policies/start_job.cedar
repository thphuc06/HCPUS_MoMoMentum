// Lớp phụ của Cedar cho tool đọc `start_job` (target `ingest`): user_id phải khớp người dùng đã đăng nhập.
// Tool không tạo job, không ghi gì (tệp chỉ tải lên từ màn hình). Interceptor đã ghi đè user_id từ JWT nên điều kiện này luôn
// đúng; nó là bảo hiểm cấu hình (spike Gateway §3b).
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"ingest___start_job",
  resource == AgentCore::Gateway::"${GATEWAY_ARN}"
) when {
  context.input has user_id && context.input.user_id == principal.id
};