import { App } from 'aws-cdk-lib';

/**
 * Cấu hình hạ tầng. Mọi giá trị đều có mặc định hợp lý và đổi được bằng context
 * (`cdk deploy -c budgetUsd=150`) hoặc `cdk.context.json` (không commit).
 * Không giá trị nào phụ thuộc tài khoản được gắn cứng: account lấy từ credential
 * (`CDK_DEFAULT_ACCOUNT`), email cảnh báo đi qua context lúc deploy.
 */
export interface YofinaConfig {
  /** Region triển khai, đặt tường minh (không dựa vào mặc định của CLI). */
  readonly region: string;
  /** Tiền tố tên tài nguyên. */
  readonly prefix: string;
  /** Ngân sách tháng (USD) của AWS Budgets. */
  readonly budgetUsd: number;
  /** Ngưỡng cảnh báo thực tế, theo % ngân sách. */
  readonly budgetThresholds: number[];
  /** `account`: cả tài khoản; `tag`: chỉ chi phí gắn tag project=yofina (cần bật cost allocation tag). */
  readonly budgetScope: 'account' | 'tag';
  /** Email nhận cảnh báo; không có thì bỏ subscription. KHÔNG ghi vào repo. */
  readonly alertEmail?: string;
  /** Phiên bản Aurora PostgreSQL (dòng 17.x). */
  readonly dbEngineVersion: string;
  readonly dbMinAcu: number;
  readonly dbMaxAcu: number;
  readonly dbName: string;
  /** Thời gian sống access token Cognito (phút). */
  readonly accessTokenMinutes: number;
  /** Số ngày giữ log của Lambda. */
  readonly logRetentionDays: number;
}

function num(app: App, key: string, dflt: number): number {
  const v = app.node.tryGetContext(key);
  if (v === undefined || v === null || v === '') return dflt;
  const n = Number(v);
  if (!Number.isFinite(n)) throw new Error(`context ${key} phải là số, nhận được: ${v}`);
  return n;
}

function str(app: App, key: string, dflt: string): string {
  const v = app.node.tryGetContext(key);
  return v === undefined || v === null || v === '' ? dflt : String(v);
}

export function loadConfig(app: App): YofinaConfig {
  const scope = str(app, 'budgetScope', 'account');
  if (scope !== 'account' && scope !== 'tag') throw new Error('context budgetScope phải là account hoặc tag');
  const email = str(app, 'alertEmail', '');
  const thresholds = str(app, 'budgetThresholds', '50,80,100')
    .split(',')
    .map((s) => Number(s.trim()));
  if (thresholds.some((t) => !Number.isFinite(t) || t <= 0)) throw new Error('context budgetThresholds không hợp lệ');
  return {
    region: str(app, 'region', 'ap-southeast-1'),
    prefix: 'yofina',
    budgetUsd: num(app, 'budgetUsd', 100),
    budgetThresholds: thresholds,
    budgetScope: scope,
    alertEmail: email || undefined,
    dbEngineVersion: str(app, 'dbEngineVersion', '17.11'),
    dbMinAcu: num(app, 'dbMinAcu', 0.5),
    dbMaxAcu: num(app, 'dbMaxAcu', 2),
    dbName: str(app, 'dbName', 'yofina'),
    accessTokenMinutes: num(app, 'accessTokenMinutes', 60),
    logRetentionDays: num(app, 'logRetentionDays', 14),
  };
}
