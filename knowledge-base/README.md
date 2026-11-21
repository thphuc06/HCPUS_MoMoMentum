# knowledge-base/

Nguồn cho RAG (Bedrock Knowledge Bases), proposal §7, §9: ba kho — (1) biểu phí và điều khoản sản phẩm công khai có ngày hiệu lực; (2) kiến thức tài chính cá nhân; (3) bộ luật suitability kèm giải thích. Hybrid search + rerank, chia đoạn theo điều khoản, lọc metadata theo sản phẩm và ngày hiệu lực.

- Biểu phí dùng cho phép tính nằm ở bảng có cấu trúc (`knowledge.get_fee_schedule`), không qua RAG.
- Đồng bộ kho tri thức chạy trong batch tuần ([../pipelines/](../pipelines/README.md)). Tool: [../gateway/tools/knowledge/](../gateway/tools/knowledge/README.md).
- Embedding tiếng Việt đã thử trên chuỗi giao dịch (chuẩn hóa chuỗi trước khi nhúng; ngưỡng cosine tuyệt đối không dùng chung giữa các model): [spike-bedrock-models.md](../docs/research/spike-bedrock-models.md) mục 6; chưa thử Knowledge Bases.
- Chưa chốt: demo dùng biểu phí Ví Trả Sau thật hay mô phỏng ([../docs/requirements/open-questions.md](../docs/requirements/open-questions.md)).