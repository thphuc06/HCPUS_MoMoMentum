// Lớp phụ của Cedar cho tool lưu lượt hội thoại: user_id phải khớp người dùng đã đăng nhập.
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"ledger___save_turn",
  resource == AgentCore::Gateway::"${GATEWAY_ARN}"
) when {
  context.input has user_id && context.input.user_id == principal.id
};
