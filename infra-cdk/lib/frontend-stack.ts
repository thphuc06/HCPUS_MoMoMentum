import { CfnOutput, Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as amplify from 'aws-cdk-lib/aws-amplify';
import { YofinaConfig } from '../config/config';
import { publishParams } from './ssm-outputs';

export interface FrontendProps extends StackProps {
  readonly cfg: YofinaConfig;
}

/**
 * Content-Security-Policy cho SPA. Nguồn lấy từ code frontend (fetch, @ag-ui/client, amazon-cognito-identity-js,
 * presigned POST) và bản build của Vite. Dùng wildcard theo miền dịch vụ AWS trong vùng của cấu hình, không gắn
 * id tài nguyên hay account: đổi API, Runtime hay bucket thì CSP vẫn đúng. Thêm nguồn mới cho frontend thì sửa ở đây.
 */
export function contentSecurityPolicy(region: string): string {
  const directives: Array<[string, string[]]> = [
    ['default-src', ["'self'"]],
    // Bundle Vite chỉ có <script type="module" src="/assets/..."> cùng nguồn, không có script inline hay eval.
    ['script-src', ["'self'"]],
    // CSS build ở /assets; 'unsafe-inline' vì thư viện UI (Base UI, Recharts) có thể chèn <style>/thuộc tính style.
    ['style-src', ["'self'", "'unsafe-inline'"]],
    // favicon.svg và ảnh SVG nhỏ Vite nhúng thành data URI; blob: cho ảnh tạo trong trình duyệt.
    ['img-src', ["'self'", 'data:', 'blob:']],
    // @fontsource Plus Jakarta Sans đóng gói trong /assets; tệp font nhỏ bị Vite nhúng thành data:font/woff2.
    ['font-src', ["'self'", 'data:']],
    [
      'connect-src',
      [
        "'self'",
        // Cognito User Pool: đăng nhập SRP và làm mới token (amazon-cognito-identity-js gọi thẳng endpoint vùng).
        `https://cognito-idp.${region}.amazonaws.com`,
        // AgentCore Runtime: POST /runtimes/.../invocations trả SSE (VITE_AGENT_RUNTIME_URL).
        `https://bedrock-agentcore.${region}.amazonaws.com`,
        // HTTP API yofina-api (VITE_API_URL = apiEndpoint mặc định <api-id>.execute-api.<vùng>).
        `https://*.execute-api.${region}.amazonaws.com`,
        // Presigned POST tải ảnh/CSV lên bucket ingest: boto3 trả URL virtual-host theo vùng; miền toàn cục
        // giữ lại phòng khi URL ký không kèm vùng.
        `https://*.s3.${region}.amazonaws.com`,
        'https://*.s3.amazonaws.com',
      ],
    ],
    ['object-src', ["'none'"]],
    ['base-uri', ["'self'"]],
    ['form-action', ["'self'"]],
    // Chống clickjacking: không trang nào được nhúng app vào iframe.
    ['frame-ancestors', ["'none'"]],
  ];
  return directives.map(([name, sources]) => `${name} ${sources.join(' ')}`).join('; ');
}

/**
 * Amplify Hosting cho SPA, deploy thủ công bằng zip (không nối GitHub): `scripts/deploy_frontend.py`.
 * Đổi customHeaders thì phải deploy lại bản zip thì header mới có hiệu lực (Amplify chỉ áp khi deploy).
 */
export class FrontendStack extends Stack {
  public readonly app: amplify.CfnApp;
  public readonly branchName = 'main';

  constructor(scope: Construct, id: string, props: FrontendProps) {
    super(scope, id, props);
    const { cfg } = props;

    this.app = new amplify.CfnApp(this, 'Web', {
      name: `${cfg.prefix}-web`,
      description: 'Yofina Foresight web app (SPA, deploy thu cong bang zip)',
      platform: 'WEB',
      // Mọi đường dẫn không phải tệp tĩnh trả index.html (React Router). csv, pdf: tệp mẫu cho giám khảo ở /samples/ (#22, #36).
      customRules: [
        {
          source: '</^[^.]+$|\\.(?!(css|csv|gif|ico|jpg|jpeg|js|pdf|png|txt|svg|woff|woff2|ttf|map|json|webp|webmanifest|xml)$)([^.]+$)/>',
          target: '/index.html',
          status: '200',
        },
      ],
      customHeaders: [
        'customHeaders:',
        '  - pattern: "**/*"',
        '    headers:',
        '      - key: X-Content-Type-Options',
        '        value: nosniff',
        '      - key: Referrer-Policy',
        '        value: strict-origin-when-cross-origin',
        '      - key: Strict-Transport-Security',
        '        value: max-age=31536000; includeSubDomains',
        '      - key: Content-Security-Policy',
        // Chuỗi JSON cũng là chuỗi YAML nháy kép hợp lệ (giá trị có ' và ; nên không để dạng trần).
        `        value: ${JSON.stringify(contentSecurityPolicy(cfg.region))}`,
        '',
      ].join('\n'),
    });

    const branch = new amplify.CfnBranch(this, 'MainBranch', {
      appId: this.app.attrAppId,
      branchName: this.branchName,
      stage: 'PRODUCTION',
      enableAutoBuild: false,
      enablePerformanceMode: false,
    });

    const url = `https://${this.branchName}.${this.app.attrDefaultDomain}`;
    publishParams(this, {
      'frontend/amplify-app-id': this.app.attrAppId,
      'frontend/amplify-branch': branch.branchName,
      'frontend/amplify-url': url,
    });
    new CfnOutput(this, 'AmplifyUrl', { value: url });
  }
}
