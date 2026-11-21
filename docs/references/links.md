# Tài liệu tham khảo (links)

Nguồn: mục 17 của proposal (truy cập 20/11/2026) và các link trong bảng số liệu mục 2, bảng kỹ thuật mục 11. Các URL được trích trực tiếp từ link nhúng trong [PDF](../proposal/Proposal-Yofina-Foresight.pdf) (ngày 21/11/2026), không đoán. Nhóm theo chủ đề. Muốn biết dùng công cụ nào để tra AWS, xem [aws-tooling.md](aws-tooling.md). Ghi chú tra cứu đáng giữ thì lưu ở [../research/](../research/README.md).

## 1. AWS và AgentCore

- [AgentCore Runtime: how it works](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html) — streaming, WebSocket, xử lý bất đồng bộ tới 8 giờ, giao thức HTTP, MCP, A2A.
- [Handle asynchronous and long running agents](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-long-run.html)
- [AgentCore release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html) — mục AG-UI protocol support.
- [Build generative UI for AI agents on Amazon Bedrock AgentCore with the AG-UI protocol](https://aws.amazon.com/blogs/machine-learning/build-generative-ui-for-ai-agents-on-amazon-bedrock-agentcore-with-the-ag-ui-protocol/) (AWS ML Blog) — proposal ghi bài này có mô tả khung FAST.
- [AgentCore Memory: get started](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-get-started.html)
- [AgentCore Memory: các chiến lược bộ nhớ (harness-memory)](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-memory.html) — đây là link gắn với cụm "các chiến lược bộ nhớ" trong PDF (trang 32).
- [Agentic AI Lens: implement tool authorization (AGENTSEC02-BP01)](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec02-bp01.html) — Gateway, Policy bằng Cedar, tìm tool theo ngữ nghĩa.
- [Propagate user authorization context in AI agents with Amazon Bedrock AgentCore](https://aws.amazon.com/blogs/security/propagate-user-authorization-context-in-ai-agents-with-amazon-bedrock-agentcore/) — JWT authorizer của Runtime.
- [Build reliable AI agents with AgentCore Evaluations](https://aws.amazon.com/blogs/machine-learning/build-reliable-ai-agents-with-amazon-bedrock-agentcore-evaluations/)
- [Build custom code-based evaluators in AgentCore](https://aws.amazon.com/blogs/machine-learning/build-custom-code-based-evaluators-in-amazon-bedrock-agentcore/)
- [Automated Reasoning checks in Bedrock Guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-automated-reasoning-checks.html)
- [Knowledge Bases: search type / test config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html) — hybrid search.
- [S3 Vectors hybrid search](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-hybrid-search.html)
- [How Bedrock Data Automation works](https://docs.aws.amazon.com/bedrock/latest/userguide/bda-how-it-works.html)

## 2. Strands Agents

URL lấy nguyên từ PDF (đuôi `index.md`; nếu không mở được thì thử bỏ `index.md`).

- [Choose a multi-agent pattern](https://strandsagents.com/docs/user-guide/sdk/multi-agent/multi-agent-patterns/index.md)
- [Agents as tools](https://strandsagents.com/docs/learning/multi-agent-patterns-agents-as-tools/index.md)
- [Human in the loop (interventions)](https://strandsagents.com/docs/user-guide/sdk/agents/interventions/human-in-the-loop/index.md)
- [Stream to the browser](https://strandsagents.com/docs/user-guide/sdk/streaming/streaming-to-the-browser-guide/index.md)

## 3. FAST (khung khởi đầu hạ tầng)

Tra cứu ngày 21/11/2026 (bước 2 của việc scaffold), xem [project-structure.md](../architecture/project-structure.md).

- [awslabs/fullstack-solution-template-for-agentcore](https://github.com/awslabs/fullstack-solution-template-for-agentcore) — repo chính thức (Apache-2.0; README tự mô tả là proof-of-value, không phải giải pháp production).
- [Accelerate agentic application development with a full-stack starter template for Amazon Bedrock AgentCore](https://aws.amazon.com/blogs/machine-learning/accelerate-agentic-application-development-with-a-full-stack-starter-template-for-amazon-bedrock-agentcore) (AWS ML Blog) — xuất hiện trong kết quả tìm kiếm, chưa đọc hết nội dung.

## 4. Paper và bài kỹ thuật (mục 11 và 17)

| Chủ đề | Nguồn | Dùng ở |
|---|---|---|
| Chronos-2 | Ansari et al., 2025, [Chronos-2: From Univariate to Universal Forecasting](https://arxiv.org/abs/2510.15821) · [model card](https://huggingface.co/autogluon/chronos-2/blob/main/README.md) | F1 dự báo |
| Adaptive conformal inference | Zaffran et al., 2022, [Adaptive Conformal Predictions for Time Series](https://arxiv.org/abs/2202.07282) | F1 khoảng tin cậy |
| Change point (PELT) | Truong, Oudre, Vayatis, 2018, [ruptures: change point detection in Python](https://arxiv.org/abs/1801.00826) | F5, sự kiện |
| FinHealth Score | Financial Health Network, [FinHealth Score Toolkit](https://finhealthnetwork.org/score/) | F4 điểm chống chịu |
| Mem0 | Chhikara et al., 2025, [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory](https://arxiv.org/abs/2504.19413) | Memory |
| ReasoningBank | Ouyang et al., 2025, [ReasoningBank: Scaling Agent Self-Evolving with Reasoning Memory](https://arxiv.org/abs/2509.25140) | Memory (bài học của agent) |
| Proactive Agent | Lu et al., 2024, [Proactive Agent: Shifting LLM Agents from Reactive Responses to Active Assistance](https://arxiv.org/abs/2410.12361) | F7 |
| ProAct | Hu et al., 2026, [Anticipate and Learn: Unleashing Idle-Time Compute in Proactive Agents](https://arxiv.org/abs/2605.25971) | F7 |
| Building effective agents | Anthropic, [Building effective agents](https://www.anthropic.com/research/building-effective-agents) | L1, L2, L4 |
| Context engineering | Anthropic, [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | Quản lý ngữ cảnh |

Proposal nêu tên nhưng **không có link** (tác giả proposal chưa mở lại trang gốc): Program-of-Thoughts (Chen et al., 2022), Croston và TSB cho chuỗi gián đoạn. Cần tìm nguồn khi dùng, rồi ghi vào [../research/](../research/README.md). Các kỹ thuật khác proposal nhắc nhưng không kèm link (CUSUM, ADWIN, PELT thuật toán, ECOD, contextual bandit, Cedar, AG-UI protocol spec) cũng cần tra khi triển khai.

## 5. Nguồn số liệu bài toán (bảng mục 2)

Ánh xạ link ↔ dòng bảng theo thứ tự link nhúng trong PDF, trang 2; nếu nghi ngờ thì mở PDF đối chiếu.

| Dòng trong bảng mục 2 | Nguồn |
|---|---|
| Hơn 90% muốn quản lý chi tiêu, 8% làm có hệ thống | [MoMo, 14/10/2026 (số nội bộ)](https://www.momo.vn/tai-chinh/blog/app-quan-ly-chi-tieu-5166) |
| Hơn 3 triệu người dùng Quản Lý Chi Tiêu | [CafeF, 05/11/2026](https://cafef.vn/momo-dua-tai-chinh-so-den-gan-hon-voi-nguoi-viet-gop-phan-nang-cao-chat-luong-song-tu-nhung-thay-doi-nho-moi-ngay-188261105224527097.chn) |
| Công cụ hiện chỉ nhìn lại | [MoMo Quản Lý Chi Tiêu](https://www.momo.vn/quan-ly-chi-tieu), [Trung Tâm Tài Chính](https://www.momo.vn/tai-chinh) |
| Nợ nhỏ phổ biến ở người trẻ (64,3%) | [Đời sống & Pháp luật, 08/2026](https://doisongphapluat.nguoiduatin.vn/gen-z-va-lan-song-ua-chuong-dich-vu-mua-truoc-tra-sau-a656681.html), CafeF (link trên) |
| Người dùng nợ nhỏ thiếu nền tảng | [Tạp chí Kinh tế - Tài chính, 09/2026](https://nghiencuu.tapchikinhtetaichinh.vn/hieu-biet-tai-chinh-va-kiem-soat-rui-ro-dich-vu-mua-truoc-tra-sau-cua-gen-z-viet-nam-167509.html) |
| Phí gây bất ngờ (33.000đ/tháng) | [MoMo Ví Trả Sau](https://www.momo.vn/vi-tra-sau), [Threads, 31/03/2026](https://www.threads.com/@loanhquanhthitruong/post/DWjiNXaE-7B/) |
| Áp lực chi phí tăng (62%) | [Dân trí, 18/11/2026 (khảo sát UOB ACSS 2026)](https://dantri.com.vn/kinh-doanh/nguoi-tieu-dung-viet-nam-lac-quan-nhat-asean-uu-tien-tiet-kiem-20261118213710875.htm) |
| Chỉ số sức khỏe tài chính | [MoMo, 09/2026](https://www.momo.vn/tin-tuc/khuyen-mai/suc-khoe-tai-chinh-tap-xoay-so-vuot-bien-co-tai-8999) |
| Hũ khác danh mục và ngân sách của MoMo | [Quản Lý Chi Tiêu](https://www.momo.vn/quan-ly-chi-tieu), [Phân Bổ Lương](https://www.momo.vn/tai-chinh/phan-bo-luong) |
| Phân loại vẫn còn phần làm tay | [MoMo, 11/04/2024](https://www.momo.vn/tin-tuc/thong-bao/tinh-nang-moi-thiet-lap-ngan-sach-de-de-dang-theo-5806), [chương trình khuyến mãi](https://www.momo.vn/tin-tuc/khuyen-mai/lam-nhiem-vu-phan-loai-giao-dich-100-co-qua-0d-6156), [bản tin 09/2025](https://www.momo.vn/tin-tuc/thong-bao/ban-tin-gop-y-va-tinh-nang-moi-thang-9-2025-8004) |

Lưu ý từ proposal: số liệu MoMo 14/10/2026 là nội bộ, không công bố phương pháp; lợi ích cho đối tác cho vay là giả thuyết cần pilot.
