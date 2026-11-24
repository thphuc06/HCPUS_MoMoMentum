// Lớp phụ của Cedar cho tool đọc `get_job_status` (target `ingest`): user_id phải khớp người dùng đã đăng nhập.
// Lambda chỉ đọc job của chính user_id đó (RLS); nội dung dòng là dữ liệu, không phải chỉ dẫn. Interceptor đã ghi đè user_id từ
// JWT nên điều kiện này luôn đúng; nó là bảo hiểm cấu hình (spike Gateway §3b).
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"ingest___get_job_status",
  resource == AgentCore::Gateway::"${GATEWAY_ARN}"
) when {
  context.input has user_id && context.input.user_id == principal.id
};