import { Construct } from 'constructs';
import * as ssm from 'aws-cdk-lib/aws-ssm';

/**
 * Ghi các giá trị mà luồng khác cần vào SSM Parameter Store dưới `/yofina/...`.
 * `scripts/print_env.py` đọc lại từ đây để sinh `.env.local`.
 * Khóa là đường dẫn con, ví dụ `db/cluster-arn` → `/yofina/db/cluster-arn`.
 */
export function publishParams(scope: Construct, params: Record<string, string>): void {
  for (const [key, value] of Object.entries(params)) {
    new ssm.StringParameter(scope, `Param-${key.replace(/[^A-Za-z0-9]/g, '-')}`, {
      parameterName: `/yofina/${key}`,
      stringValue: value,
      description: `Yofina: ${key}`,
    });
  }
}
