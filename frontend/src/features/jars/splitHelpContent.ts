import type { JarTemplate } from '@/api/schemas'
import { formatPercent } from '@/lib/format'

/**
 * Lời của tấm trợ giúp "Chia hũ sao cho hợp lý" (nút "?" cạnh tiêu đề phần chia tỷ lệ, issue #39). Sửa lời ở tệp này, không
 * rải trong JSX. Đây là HƯỚNG DẪN CHUNG, không phải lời khuyên cho riêng ai, không nói sản phẩm đầu tư cụ thể (BC-03).
 *
 * Số không chép cứng: tỷ lệ mặc định lấy từ `GET /jar-templates` (`is_default`, `default_split_percent`; server đã áp bộ hũ
 * onboarding đang bật, kể cả công tắc quay lui bộ bảy). Thiếu dữ liệu thì nói định tính. Mức sàn Dự phòng
 * (`buffer_min_split_percent`) không có trong phản hồi nào mà hai màn này đọc, nên chỉ nói "mức sàn".
 *
 * Từng ý đã đối chiếu với mã và quy tắc (docs/ba/02-business-rules.md, docs/plan/default-six-jars-rollout.md):
 * - Hũ mặc định theo mục đích, tổng 100%: BR-04, B2a; `jar_templates.is_default` (migration 0059); trình sửa chỉ cho lưu khi đủ 100%.
 * - Nghĩa vụ theo số thật: `split_proposal.py` (tổng nghĩa vụ đã khai quy về tháng ÷ lương đã khai, làm tròn lên; theo năm
 *   chia 12, theo tuần nhân 52/12). Đề xuất chỉ có ở bước 3 của onboarding (`POST /jars/split-proposal`), màn sửa hũ không có,
 *   nên lời ở màn sửa hũ không hứa đề xuất.
 * - Dự phòng trước, mục tiêu sau: BR-42, BR-65 (hướng dẫn chung). Phần chắc chắn của sản phẩm: đề xuất tỷ lệ theo số khai không
 *   hạ Dự phòng dưới `min(sàn, tỷ lệ đang đặt)` (`build_proposal`). Lộ trình do agent soạn không có ràng buộc này, nên lời chỉ
 *   nói về "đề xuất tỷ lệ theo số khai".
 * - Quỹ dồn: BR-66; bước 3 tính tỷ lệ một lần khi khai (tự tính lại mỗi kỳ chưa làm). Màn sửa hũ chỉ có ô "Số tiền dự kiến",
 *   "Ngày dự kiến", không tự tính tỷ lệ.
 * - Tách hũ để theo dõi: dự báo chạy theo từng hũ; hũ thưa không nêu ngày cạn (#25), nên lời nói "dự báo riêng" chứ không hứa
 *   ngày cạn. Bộ phát hiện đổi nhịp chi (PELT, batch đêm) chạy trên mọi hũ chi tiêu nhưng bỏ qua hũ thiếu tuần hoặc quá thưa
 *   (`yofina_ml.change`, `min_weeks_total`), nên lời nói "khi đã có vài tuần giao dịch". Xác nhận đổi nhịp thì sinh bản lộ trình
 *   đề xuất mới (không có thông báo riêng), nên lời nói "đề xuất lại lộ trình", không hứa "báo".
 * - Tỷ lệ gợi ý là điểm bắt đầu: tỷ lệ mặc định là giả định thử nghiệm (rollout "Cấu hình hũ"); gợi ý chỉnh theo lịch sử (BR-80..82)
 *   chưa làm, nên lời chỉ khuyên người dùng tự xem lại. Đổi tỷ lệ chỉ có hiệu lực sau khi xác nhận (BR-45, `SaveJarsReview`).
 *
 * Căn cứ của hướng dẫn chung (chỉ ghi ở đây, không hiện trên giao diện): quỹ khẩn cấp cho khoản không dự tính trước
 * (CFPB, "An essential guide to building an emergency fund"); lên lịch hóa đơn theo ngày lương (CFPB bill calendar); mặc định
 * thường được giữ nguyên nên chỉ là điểm bắt đầu (Madrian và Shea 2001). Không nguồn nào chứng minh một tỷ lệ hay số hũ là tối ưu.
 */

/** Nơi mở tấm trợ giúp: bước chia hũ của onboarding (có bước kê khai ngay sau) hay màn "Thêm hoặc sửa hũ". */
export type SplitHelpPlace = 'onboarding' | 'edit'

export type SplitHelpTip = {
  id: 'defaults' | 'obligation' | 'buffer' | 'sinking' | 'track' | 'few' | 'review'
  /** Ý chính, một dòng. */
  lead: string
  /** Một hoặc hai câu ngắn. */
  text: string
  /** Dòng số lấy từ dữ liệu server (chỉ có khi có dữ liệu). */
  data?: string
}

export type SplitHelpContent = {
  title: string
  /** Câu dưới tiêu đề, cũng là mô tả của hộp thoại cho trình đọc màn hình. */
  note: string
  tips: SplitHelpTip[]
  more: { label: string; items: string[] }
}

export const SPLIT_HELP_TRIGGER_LABEL = 'Cách chia hũ hợp lý'
export const SPLIT_HELP_CLOSE_LABEL = 'Đóng'
export const SPLIT_HELP_LIST_LABEL = 'Gợi ý chia hũ'

/** "Mặc định: Chi hằng ngày 42% · Nghĩa vụ 33% · Dự phòng 25%" từ mẫu hũ mặc định, theo thứ tự server trả; không có thì undefined. */
function defaultsLine(templates: readonly JarTemplate[] | undefined): string | undefined {
  const defaults = (templates ?? []).filter((t) => t.is_default)
  if (defaults.length === 0) return undefined
  return `Mặc định: ${defaults.map((t) => `${t.name} ${formatPercent(t.default_split_percent)}`).join(' · ')}`
}

export function splitHelpContent({ place, templates }: { place: SplitHelpPlace; templates?: readonly JarTemplate[] }): SplitHelpContent {
  const onboarding = place === 'onboarding'
  const data = defaultsLine(templates)
  return {
    title: 'Chia hũ sao cho hợp lý',
    note: 'Hướng dẫn chung, không phải lời khuyên cho riêng bạn.',
    tips: [
      {
        id: 'defaults',
        lead: 'Bắt đầu từ hũ mặc định theo mục đích',
        text: 'Tiền tiêu hằng ngày; khoản phải trả (nhà, hóa đơn, nợ, Trả sau); dự phòng. Tổng các hũ luôn là 100%.',
        ...(data ? { data } : {}),
      },
      {
        id: 'obligation',
        lead: 'Đặt hũ Nghĩa vụ theo số thật',
        text: onboarding
          ? 'Cộng các khoản phải trả mỗi tháng rồi chia cho lương. Khai các khoản ở bước 3, Yofina đề xuất tỷ lệ.'
          : 'Cộng các khoản phải trả mỗi tháng rồi chia cho lương.',
      },
      {
        id: 'buffer',
        lead: 'Dự phòng trước, mục tiêu sau',
        text: 'Giữ khoản đệm cho việc bất ngờ trước khi dồn cho mục tiêu khác. Khi đề xuất tỷ lệ theo số khai, Yofina không hạ Dự phòng dưới mức sàn.',
      },
      {
        id: 'sinking',
        lead: 'Khoản biết trước thì chia nhỏ',
        text: onboarding
          ? 'Tết, học phí, bảo hiểm năm: để dần mỗi kỳ lương vào Quỹ dồn. Khai ở bước 3, Yofina tính phần mỗi kỳ.'
          : 'Tết, học phí, bảo hiểm năm: để dần mỗi kỳ lương vào Quỹ dồn. Ghi số tiền và ngày dự kiến ở hũ Quỹ dồn.',
      },
      {
        id: 'track',
        lead: 'Muốn theo dõi sát thì tách hũ riêng',
        text: 'Ví dụ ăn uống, đi lại, giải trí. Hũ riêng có dự báo riêng; khi đã có vài tuần giao dịch, Yofina đề xuất lại lộ trình khi nhịp chi của hũ đổi.',
      },
      {
        id: 'few',
        lead: 'Không cần nhiều hũ',
        text: 'Mỗi hũ thêm là một tỷ lệ phải quyết. Chỉ thêm khi thật sự cần.',
      },
      {
        id: 'review',
        lead: 'Tỷ lệ gợi ý chỉ là điểm bắt đầu',
        text: 'Xem lại sau vài kỳ lương theo chi tiêu thật. Tỷ lệ mới chỉ có hiệu lực sau khi bạn xác nhận.',
      },
    ],
    more: {
      label: 'Xem thêm',
      items: [
        onboarding
          ? 'Tỷ lệ Nghĩa vụ đề xuất = các khoản đã khai quy về tháng ÷ lương đã khai, làm tròn lên.'
          : 'Tỷ lệ Nghĩa vụ ≈ các khoản phải trả quy về tháng ÷ lương.',
        'Quy về tháng: khoản trả theo năm chia 12, theo tuần nhân 52 rồi chia 12.',
        'Quỹ dồn mỗi kỳ = số còn thiếu ÷ số kỳ lương còn lại trước ngày cần.',
        ...(onboarding ? ['Phần tăng thêm lấy trước từ hũ chi không thiết yếu; hũ chi thiết yếu bị đụng sau cùng.'] : []),
        'Có lương đang chờ chia thì bạn chọn áp tỷ lệ mới cho kỳ này hay từ kỳ sau.',
      ],
    },
  }
}
