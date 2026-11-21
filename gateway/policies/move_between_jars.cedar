// Lớp phụ của Cedar cho tool ghi (ADR-0002). KHÔNG chặn lời gọi thiếu confirm_token: agent gọi tool này
// không token để nhận NEEDS_CONFIRMATION (không ghi). Việc kiểm token (chữ ký, hạn, jti) nằm ở Lambda.
// Cedar ở đây ép: (1) user_id khớp người dùng; (2) hạn mức một lần chuyển, cùng giá trị với cấu hình
// của Lambda (`moveMaxAmountVnd`, ${MOVE_MAX_AMOUNT_VND} do CDK thay); (3) nếu có confirm_token thì phải
// có dạng "phần.phần" (chặn token rác sớm; không kiểm được chữ ký). Dạng `!(has) || truy cập` bị bộ kiểm
// kiểu của Cedar từ chối ("unable to guarantee safety of access to optional attribute"); `if has then ... else true` thì qua.
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"ledger___move_between_jars",
  resource == AgentCore::Gateway::"${GATEWAY_ARN}"
) when {
  context.input has user_id && context.input.user_id == principal.id &&
  context.input.amount_vnd <= ${MOVE_MAX_AMOUNT_VND} &&
  (if context.input has confirm_token then context.input.confirm_token like "*.*" else true)
};
