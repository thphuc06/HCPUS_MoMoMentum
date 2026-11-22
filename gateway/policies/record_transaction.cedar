// Lớp phụ của Cedar cho tool ghi `record_transaction` (ADR-0002). KHÔNG chặn lời gọi thiếu confirm_token: agent gọi tool
// này không token để nhận NEEDS_CONFIRMATION (không ghi). Việc kiểm token (chữ ký, hạn, jti) nằm ở Lambda.
// Cedar ở đây ép: (1) user_id khớp người dùng; (2) hạn mức một giao dịch, cùng giá trị với cấu hình của Lambda
// (`transactionMaxAmountVnd`, ${TRANSACTION_MAX_AMOUNT_VND} do CDK thay); (3) nếu có confirm_token thì phải có dạng
// "phần.phần" (chặn token rác sớm; không kiểm được chữ ký). Dạng `if has then ... else true` thay cho `!(has) || ...`
// vì bộ kiểm kiểu của Cedar từ chối truy cập thuộc tính tùy chọn theo dạng sau.
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"ledger___record_transaction",
  resource == AgentCore::Gateway::"${GATEWAY_ARN}"
) when {
  context.input has user_id && context.input.user_id == principal.id &&
  context.input.amount_vnd <= ${TRANSACTION_MAX_AMOUNT_VND} &&
  (if context.input has confirm_token then context.input.confirm_token like "*.*" else true)
};
