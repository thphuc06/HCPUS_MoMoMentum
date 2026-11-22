// Lớp phụ của Cedar cho tool ghi `schedule_nudge` (ADR-0002, target `planner`). KHÔNG chặn lời gọi thiếu confirm_token: agent gọi
// tool này không token để nhận NEEDS_CONFIRMATION (không ghi); việc kiểm token nằm ở Lambda. Không có số tiền nên không có hạn mức;
// Cedar chỉ ép user_id khớp người dùng và, nếu có confirm_token, dạng "phần.phần".
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"planner___schedule_nudge",
  resource == AgentCore::Gateway::"${GATEWAY_ARN}"
) when {
  context.input has user_id && context.input.user_id == principal.id &&
  (if context.input has confirm_token then context.input.confirm_token like "*.*" else true)
};
