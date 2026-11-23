import { createHash } from 'crypto';
import { Construct } from 'constructs';
import { Stack } from 'aws-cdk-lib';
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import { publishParams } from './ssm-outputs';

/**
 * Cấu hình của Bedrock Guardrail `yofina-guardrail` (phase 3, luồng B, lớp L0 của harness).
 * Giá trị đổi được bằng cách sửa file này hoặc truyền vào construct; không giá trị nào phụ thuộc tài khoản
 * (ARN hồ sơ guardrail được dựng từ `Stack.of(this)` lúc deploy).
 */
export interface YofinaGuardrailProps {
  /** Tên guardrail (chỉ `[0-9a-zA-Z-_]`, tối đa 50 ký tự). */
  readonly name?: string;
  /** Id hồ sơ guardrail cho suy luận liên vùng của bậc STANDARD (ap-southeast-1 dùng hồ sơ APAC). */
  readonly guardrailProfileId?: string;
  /**
   * Vùng đích mà hồ sơ có thể chuyển lời gọi tới (bảng "APAC Guardrail v1:0", nguồn ap-southeast-1):
   * https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-cross-region-support.html
   * IAM phải cho phép `ApplyGuardrail` trên hồ sơ ở MỌI vùng này, thiếu vùng nào thì lời gọi bị chuyển sang đó sẽ AccessDenied.
   */
  readonly profileDestinationRegions?: readonly string[];
  /** Mức lọc nội dung đầu vào (cuộc tấn công prompt chỉ lọc ở đầu vào, đầu ra luôn NONE theo yêu cầu của dịch vụ). */
  readonly contentStrength?: FilterStrength;
  /**
   * Mức riêng cho từng loại bộ lọc (ghi đè `contentStrength`). Mặc định MISCONDUCT = LOW: ở HIGH, câu nghiệp vụ "Chuyển 250 nghìn cho
   * người nhận demo có ổn không" bị chấm MISCONDUCT độ tin cậy MEDIUM và chặn nhầm (đo bằng ApplyGuardrail 23/11). LOW chỉ chặn độ tin cậy HIGH
   * (https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-content-filters-overview.html). Ví điện tử nói về chuyển tiền suốt;
   * ghi không xác nhận đã bị chặn bằng token và Cedar ở lớp sau, không dựa vào bộ lọc này.
   */
  readonly filterStrengths?: Partial<Record<ContentFilterType, FilterStrength>>;
  /** Thông điệp trả khi chặn đầu vào; agent không dùng chữ này mà dựng khối `notice` riêng. */
  readonly blockedInputMessaging?: string;
  readonly blockedOutputsMessaging?: string;
}

/**
 * Guardrail (lọc vào và ra) cho agent. Chủ đề cấm: khuyên mã chứng khoán, quỹ hay tài sản đầu tư cụ thể (proposal §9).
 * Bậc STANDARD vì bậc CLASSIC chỉ hỗ trợ tiếng Anh, Pháp, Tây Ban Nha; STANDARD hỗ trợ tiếng Việt và có ở ap-southeast-1.
 * Agent gọi `bedrock-runtime:ApplyGuardrail` (không gắn vào lời gọi model) nên lọc được cả câu hỏi lẫn câu trả lời
 * của tầng Python. Id và version xuất ra SSM `/yofina/guardrail/id` và `/yofina/guardrail/version`.
 *
 * Quyền cần thêm cho vai `yofina-agent-runtime` (người điều phối nối ở stack): `bedrock:ApplyGuardrail` trên
 * `guardrailArn` và trên hồ sơ ở mọi vùng đích (`applyResourceArns`), theo
 * https://docs.aws.amazon.com/bedrock/latest/userguide/guardrail-profiles-permissions.html
 */
export type FilterStrength = 'NONE' | 'LOW' | 'MEDIUM' | 'HIGH';
export type ContentFilterType = 'HATE' | 'INSULTS' | 'SEXUAL' | 'VIOLENCE' | 'MISCONDUCT';
export const DEFAULT_FILTER_STRENGTHS: Partial<Record<ContentFilterType, FilterStrength>> = { MISCONDUCT: 'LOW' };

export const APAC_GUARDRAIL_DESTINATION_REGIONS = [
  'ap-south-1',
  'ap-northeast-3',
  'ap-northeast-2',
  'ap-southeast-1',
  'ap-southeast-2',
  'ap-northeast-1',
] as const;

export class YofinaGuardrail extends Construct {
  readonly guardrailId: string;
  readonly guardrailArn: string;
  readonly version: string;
  readonly profileArn: string;
  /** Hồ sơ guardrail ở từng vùng đích (gồm cả vùng của stack). */
  readonly profileDestinationArns: string[];

  constructor(scope: Construct, id: string, props: YofinaGuardrailProps = {}) {
    super(scope, id);
    const stack = Stack.of(this);
    const strength = props.contentStrength ?? 'HIGH';
    const profileId = props.guardrailProfileId ?? 'apac.guardrail.v1:0';
    const profileArnIn = (region: string) =>
      `arn:${stack.partition}:bedrock:${region}:${stack.account}:guardrail-profile/${profileId}`;
    this.profileArn = profileArnIn(stack.region);
    const regions = new Set<string>([stack.region, ...(props.profileDestinationRegions ?? APAC_GUARDRAIL_DESTINATION_REGIONS)]);
    this.profileDestinationArns = [...regions].map(profileArnIn);

    const strengths = { ...DEFAULT_FILTER_STRENGTHS, ...(props.filterStrengths ?? {}) };
    const strengthOf = (type: ContentFilterType): FilterStrength => strengths[type] ?? strength;

    const guardrail = new bedrock.CfnGuardrail(this, 'Guardrail', {
      name: props.name ?? 'yofina-guardrail',
      description: 'Yofina: chặn khuyên mã chứng khoán/quỹ cụ thể và prompt injection',
      blockedInputMessaging: props.blockedInputMessaging ?? 'Yofina không hỗ trợ nội dung này.',
      blockedOutputsMessaging: props.blockedOutputsMessaging ?? 'Yofina không thể đưa ra nội dung này.',
      crossRegionConfig: { guardrailProfileArn: this.profileArn },
      topicPolicyConfig: {
        topicsTierConfig: { tierName: 'STANDARD' },
        topicsConfig: [
          {
            name: 'specific-investment-advice',
            type: 'DENY',
            definition:
              'Khuyên mua, bán hoặc nắm giữ một mã cổ phiếu, chứng chỉ quỹ, trái phiếu, tiền mã hóa hoặc sản phẩm đầu tư cụ thể; ' +
              'dự đoán giá hoặc lợi nhuận của chúng; chọn mã nào nên mua. Không gồm việc giải thích khái niệm chung hay mô phỏng chi tiêu của chính người dùng.',
            examples: [
              'Nên mua cổ phiếu nào bây giờ?',
              'Mã VNM có nên mua không, giá sẽ lên bao nhiêu?',
              'Cho mình danh sách quỹ ETF đáng đầu tư nhất.',
              'Nên dồn tiền vào bitcoin hay vàng?',
              'Which stock should I buy this week?',
            ],
          },
        ],
      },
      contentPolicyConfig: {
        contentFiltersTierConfig: { tierName: 'STANDARD' },
        filtersConfig: [
          ...(['HATE', 'INSULTS', 'SEXUAL', 'VIOLENCE', 'MISCONDUCT'] as const).map((type) => ({
            type,
            inputStrength: strengthOf(type),
            outputStrength: strengthOf(type),
          })),
          // PROMPT_ATTACK chỉ có ý nghĩa ở đầu vào; đầu ra bắt buộc NONE.
          { type: 'PROMPT_ATTACK', inputStrength: strength, outputStrength: 'NONE' },
        ],
      },
      tags: [{ key: 'project', value: 'yofina' }],
    });

    // Version là ảnh chụp cấu hình lúc tạo; đổi cấu hình mà giữ nguyên version thì Runtime vẫn dùng bản cũ. Description đổi thì
    // CloudFormation thay version (Update requires: Replacement), nên gắn mã băm của cấu hình vào Description.
    const configHash = createHash('sha256')
      .update(
        JSON.stringify({
          topics: guardrail.topicPolicyConfig,
          content: guardrail.contentPolicyConfig,
          inMsg: guardrail.blockedInputMessaging,
          outMsg: guardrail.blockedOutputsMessaging,
        }),
      )
      .digest('hex')
      .slice(0, 12);
    const version = new bedrock.CfnGuardrailVersion(this, 'Version', {
      guardrailIdentifier: guardrail.attrGuardrailId,
      description: `Phiên bản cố định cho agent (Runtime dùng số version, không dùng DRAFT); cấu hình ${configHash}`,
    });

    this.guardrailId = guardrail.attrGuardrailId;
    this.guardrailArn = guardrail.attrGuardrailArn;
    this.version = version.attrVersion;

    publishParams(this, {
      'guardrail/id': this.guardrailId,
      'guardrail/version': this.version,
    });
  }
}
