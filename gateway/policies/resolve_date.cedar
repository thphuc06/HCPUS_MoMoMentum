// Lớp phụ của Cedar cho tool đọc `resolve_date` (target `knowledge`): user_id phải khớp người dùng đã đăng nhập.
// Tool chỉ tính ngày từ đặc tả (không ghi gì), nhưng dùng ngày mô phỏng và ngày lương của chính user_id đó.
// Interceptor đã ghi đè user_id từ JWT nên điều kiện này luôn đúng; nó là bảo hiểm cấu hình (spike Gateway §3b).
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"knowledge___resolve_date",
  resource == AgentCore::Gateway::"${GATEWAY_ARN}"
) when {
  context.input has user_id && context.input.user_id == principal.id
};
