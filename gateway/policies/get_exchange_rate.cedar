// Lớp phụ của Cedar cho tool đọc `get_exchange_rate` (target `knowledge`): user_id phải khớp người dùng đã đăng nhập.
// Tool chỉ đọc bảng tỷ giá công bố (không có dữ liệu của người dùng), nhưng dùng ngày mô phỏng của chính user_id đó khi vắng `date`.
// Interceptor đã ghi đè user_id từ JWT nên điều kiện này luôn đúng; nó là bảo hiểm cấu hình (spike Gateway §3b).
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"knowledge___get_exchange_rate",
  resource == AgentCore::Gateway::"${GATEWAY_ARN}"
) when {
  context.input has user_id && context.input.user_id == principal.id
};
