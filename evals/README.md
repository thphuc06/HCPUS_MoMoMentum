# evals/

Đánh giá chất lượng agent (proposal §9 Observability và đánh giá, §6 KPI, §15 tuần 3).

- Bộ câu chuẩn có quỹ đạo tool mong đợi (đánh giá offline, chạy mỗi lần đổi prompt/model); bộ 50 câu đối kháng cho đội rủi ro.
- Evaluator tự viết bằng code: `NumericGrounding` (mọi số có trong kết quả tool), `SchemaValidity` (JSON đúng schema), `SuitabilityCompliance` (không gợi ý vi phạm). AgentCore Evaluations (Correctness, Helpfulness, GoalSuccessRate) cho đánh giá online (phần mở rộng).
- Backtest dự báo (pinball loss so với seasonal naive, độ phủ khoảng 80%) chạy ở [../pipelines/](../pipelines/README.md) batch tuần. Khung backtest đã thử và lưu ý độ phủ tổng 30 ngày phủ thiếu: [spike-ml-forecasting.md](../docs/research/spike-ml-forecasting.md).
- Claude 4.x chỉ 10 request/phút mỗi model: chạy bộ đánh giá lớn cần Nova hoặc `us-east-1` (quota rộng hơn), không chạy chung xô với demo ([spike-bedrock-models.md](../docs/research/spike-bedrock-models.md) mục 9).