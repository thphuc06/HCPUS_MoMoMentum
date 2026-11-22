// Lớp phụ của Cedar cho tool đọc `get_fee_schedule` (target `knowledge`): user_id phải khớp người dùng đã đăng nhập.
// Interceptor đã ghi đè user_id từ JWT nên điều kiện này luôn đúng; nó là bảo hiểm cấu hình (spike Gateway §3b).
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"knowledge___get_fee_schedule",
  resource == AgentCore::Gateway::"${GATEWAY_ARN}"
) when {
  context.input has user_id && context.input.user_id == principal.id
};
