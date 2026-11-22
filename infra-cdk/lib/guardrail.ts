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
  /** Mức lọc nội dung đầu vào (cuộc tấn công prompt chỉ lọc ở đầu vào, đầu ra luôn NONE theo yêu cầu của dịch vụ). */
  readonly contentStrength?: 'LOW' | 'MEDIUM' | 'HIGH';
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
 * `guardrailArn` và trên hồ sơ `arn:aws:bedrock:<region>:<account>:guardrail-profile/<guardrailProfileId>`.
 */
export class YofinaGuardrail extends Construct {
  readonly guardrailId: string;
  readonly guardrailArn: string;
  readonly version: string;
  readonly profileArn: string;

  constructor(scope: Construct, id: string, props: YofinaGuardrailProps = {}) {
    super(scope, id);
    const stack = Stack.of(this);
    const strength = props.contentStrength ?? 'HIGH';
    const profileId = props.guardrailProfileId ?? 'apac.guardrail.v1:0';
    this.profileArn = `arn:${stack.partition}:bedrock:${stack.region}:${stack.account}:guardrail-profile/${profileId}`;

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
            inputStrength: strength,
            outputStrength: strength,
          })),
          // PROMPT_ATTACK chỉ có ý nghĩa ở đầu vào; đầu ra bắt buộc NONE.
          { type: 'PROMPT_ATTACK', inputStrength: strength, outputStrength: 'NONE' },
        ],
      },
      tags: [{ key: 'project', value: 'yofina' }],
    });

    const version = new bedrock.CfnGuardrailVersion(this, 'Version', {
      guardrailIdentifier: guardrail.attrGuardrailId,
      description: 'Phiên bản cố định cho agent (Runtime dùng số version, không dùng DRAFT)',
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
