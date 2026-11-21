import { CfnOutput, Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as amplify from 'aws-cdk-lib/aws-amplify';
import { YofinaConfig } from '../config/config';
import { publishParams } from './ssm-outputs';

export interface FrontendProps extends StackProps {
  readonly cfg: YofinaConfig;
}

/**
 * Amplify Hosting cho SPA, deploy thủ công bằng zip (không nối GitHub): `scripts/deploy_frontend.py`.
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
      // Mọi đường dẫn không phải tệp tĩnh trả index.html (React Router).
      customRules: [
        {
          source: '</^[^.]+$|\\.(?!(css|gif|ico|jpg|jpeg|js|png|txt|svg|woff|woff2|ttf|map|json|webp|webmanifest|xml)$)([^.]+$)/>',
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
