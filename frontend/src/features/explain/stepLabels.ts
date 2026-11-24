import { toolLabel, hasToolLabel } from '@/chat/errors'

/**
 * Nhãn tiếng Việt cho các bước của bản ghi lượt (`step_timings`). Bước không phải tool do agent đặt tên (`Turn.step`, `turn.py`; chặng
 * lộ trình là `roadmap_<JobStage>`); bước gọi tool có dạng `<target>___<tool>` và dùng nhãn tiến độ của tool. Mọi bước agent có thể ghi
 * phải có nhãn ở đây (test `tests/unit/agent/test_tool_labels.py` quét mã agent).
 */
export const STEP_LABELS: Record<string, string> = {
  router: 'Hiểu câu hỏi',
  guardrail_in: 'Lọc nội dung đầu vào',
  guardrail_out: 'Lọc nội dung đầu ra',
  orchestrator: 'Dựng kịch bản',
  bundle: 'Gộp các khoản đang cân nhắc',
  tools: 'Đọc dữ liệu cho kịch bản',
  analyst: 'Phân tích và đề xuất phương án',
  verifier: 'Kiểm chứng số liệu và luật',
  composer: 'Soạn câu trả lời',
  roadmap_context: 'Lộ trình: đọc bối cảnh',
  roadmap_draft: 'Lộ trình: phác thảo các bước',
  roadmap_allocate: 'Lộ trình: phân bổ tiền',
  roadmap_suitability: 'Lộ trình: kiểm luật từng bước',
  roadmap_save: 'Lộ trình: lưu bản mới',
}

/** Nhãn của một bước; bước lạ (bản ghi cũ hoặc mới hơn giao diện) thì giữ mã. */
export function stepLabel(step: string): string {
  if (step.includes('___')) return hasToolLabel(step) ? toolLabel(step, 'done') : step
  return STEP_LABELS[step] ?? step
}
