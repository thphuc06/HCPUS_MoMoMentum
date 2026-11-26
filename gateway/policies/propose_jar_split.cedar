// Lớp phụ của Cedar cho tool đọc: chỉ cho phép khi user_id trong lời gọi khớp người dùng đã đăng nhập.
// Interceptor đã ghi đè user_id từ JWT; ${GATEWAY_ARN} do infra-cdk/lib/agent-stack.ts thay lúc deploy.
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"ledger___propose_jar_split",
  resource == AgentCore::Gateway::"${GATEWAY_ARN}"
) when {
  context.input has user_id && context.input.user_id == principal.id
};
