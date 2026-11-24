// Lớp phụ của Cedar cho tool ghi `confirm_rows` (target `ingest`, ADR-0002). KHÔNG chặn lời gọi thiếu confirm_token: agent gọi
// tool này không token để nhận NEEDS_CONFIRMATION (không ghi); việc kiểm token (chữ ký HMAC, hạn, người, tool, hash tham số, jti dùng
// một lần) nằm ở Lambda yofina-ingest-api, cùng luồng với POST /ingest/actions. Dòng nạp không đổi số dư hũ nên không có hạn mức;
// Cedar chỉ ép user_id khớp người dùng và, nếu có confirm_token, dạng "phần.phần".
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"ingest___confirm_rows",
  resource == AgentCore::Gateway::"${GATEWAY_ARN}"
) when {
  context.input has user_id && context.input.user_id == principal.id &&
  (if context.input has confirm_token then context.input.confirm_token like "*.*" else true)
};