"""Mọi lời gọi Bedrock đi qua module này (luồng D cài ở phase 1; chưa có mã ở bước 0).

Sẽ làm ba việc (docs/plan/master-plan.md, mục "Model và giới hạn"):
- giới hạn tốc độ mỗi model (mặc định 8 request/phút cho Claude 4.x);
- trần lượt gọi mỗi ngày đếm bằng DynamoDB `yofina-usage`; chạm trần thì ném lỗi có kiểu
  `ModelBudgetExceeded` (ứng với `ErrorCode.MODEL_BUDGET_EXCEEDED`) để luồng rẽ sang thẻ số
  liệu tất định;
- chuỗi dự phòng bắt cả `ThrottlingException` lẫn `AccessDeniedException`; ghi token vào log.

Model id, trần và tốc độ lấy từ `yofina_core.config`. Model giả chỉ dùng trong unit test và
không được import từ mã sản phẩm.
"""
