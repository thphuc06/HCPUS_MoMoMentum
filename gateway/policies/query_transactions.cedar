// Lớp phụ của Cedar cho tool đọc giao dịch: user_id phải khớp người dùng đã đăng nhập.
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"ledger___query_transactions",
  resource == AgentCore::Gateway::"${GATEWAY_ARN}"
) when {
  context.input has user_id && context.input.user_id == principal.id
};
