// Lớp phụ của Cedar cho tool đọc: chỉ cho phép khi user_id trong lời gọi khớp người dùng đã đăng nhập.
// Interceptor đã ghi đè user_id từ JWT nên điều kiện này luôn đúng; nó là bảo hiểm cấu hình (spike Gateway §3b).
// ${GATEWAY_ARN} do infra-cdk/lib/agent-stack.ts thay lúc deploy; dòng chú thích bị bỏ trước khi gửi.
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"ledger___get_jar_balances",
  resource == AgentCore::Gateway::"${GATEWAY_ARN}"
) when {
  context.input has user_id && context.input.user_id == principal.id
};
