// Lớp phụ của Cedar cho tool GHI `save_roadmap` (target `planner`, phase 4). Tool này ghi một phiên bản lộ trình nhưng KHÔNG đổi số
// dư nên KHÔNG qua token xác nhận (như `record_turn` và `POST /feedback`; hành động đổi tiền trong từng bước vẫn qua luồng token
// riêng): Cedar chỉ ép user_id khớp người dùng. Việc kiểm luật suitability và phiên bản nằm ở Lambda.
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"planner___save_roadmap",
  resource == AgentCore::Gateway::"${GATEWAY_ARN}"
) when {
  context.input has user_id && context.input.user_id == principal.id
};
