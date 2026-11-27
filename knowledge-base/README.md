# knowledge-base/

Proposal §7, §9 từng dành thư mục này cho ba kho RAG (Bedrock Knowledge Bases) (biểu phí và điều khoản sản phẩm công khai có ngày hiệu lực; kiến thức tài chính cá nhân; bộ luật suitability kèm giải thích), hybrid search + rerank.

**RAG đã cắt ngày 24/11** (chủ dự án; [ADR-0004](../docs/decisions/0004-lech-so-voi-proposal.md) dòng 1): mọi con số lấy từ bảng có cấu trúc và không cảnh demo nào cần tìm trong tài liệu. Thư mục chỉ còn README này.

- Biểu phí: bảng có cấu trúc `fee_schedules` (`db/seed/fee_schedules.sql`), đọc qua tool `knowledge___get_fee_schedule`; câu hỏi về phí kèm khối `citation` dựng từ nguồn của chính bảng biểu phí (`agent/src/yofina_agent/fee_citation.py`). Tool: [../gateway/tools/knowledge/](../gateway/tools/knowledge/README.md).
- Luật suitability nằm ở `gateway/tools/planner/rules/*.yaml`, không ở kho tài liệu.
- Không có batch tuần đồng bộ kho tri thức (batch tuần cũng đã cắt, [../pipelines/](../pipelines/README.md)).
- Embedding tiếng Việt chỉ dùng cho bước phân loại giao dịch (pgvector), không dùng để tìm tài liệu: [spike-bedrock-models.md](../docs/research/spike-bedrock-models.md) mục 6.
- Biểu phí Ví Trả Sau thật hay mô phỏng: chốt 21/11 là sản phẩm mô phỏng, lấy biểu phí công khai làm ví dụ ([../docs/requirements/open-questions.md](../docs/requirements/open-questions.md)).
