import { Duration, RemovalPolicy, Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import { YofinaConfig } from '../config/config';
import { publishParams } from './ssm-outputs';

export interface IdentityProps extends StackProps {
  readonly cfg: YofinaConfig;
}

/**
 * Cognito: tắt tự đăng ký, đăng nhập bằng email, app client công khai cho SPA (SRP), nhóm `ops`.
 * Tài khoản demo tạo bằng `scripts/create_demo_users.py`, không qua CDK.
 */
export class IdentityStack extends Stack {
  public readonly userPool: cognito.UserPool;
  public readonly webClient: cognito.UserPoolClient;

  constructor(scope: Construct, id: string, props: IdentityProps) {
    super(scope, id, props);
    const { cfg } = props;
    const p = cfg.prefix;

    this.userPool = new cognito.UserPool(this, 'Users', {
      userPoolName: `${p}-users`,
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      standardAttributes: { email: { required: true, mutable: true } },
      passwordPolicy: {
        minLength: 12,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
      },
      mfa: cognito.Mfa.OFF,
      accountRecovery: cognito.AccountRecovery.NONE,
      deletionProtection: true,
      removalPolicy: RemovalPolicy.RETAIN,
    });

    this.webClient = this.userPool.addClient('Web', {
      userPoolClientName: `${p}-web`,
      generateSecret: false,
      authFlows: { userSrp: true },
      accessTokenValidity: Duration.minutes(cfg.accessTokenMinutes),
      idTokenValidity: Duration.minutes(cfg.accessTokenMinutes),
      refreshTokenValidity: Duration.days(7),
      enableTokenRevocation: true,
      preventUserExistenceErrors: true,
    });

    new cognito.CfnUserPoolGroup(this, 'OpsGroup', {
      userPoolId: this.userPool.userPoolId,
      groupName: 'ops',
      description: 'Van hanh / giam sat (man hinh trace)',
    });

    publishParams(this, {
      'auth/user-pool-id': this.userPool.userPoolId,
      'auth/client-id': this.webClient.userPoolClientId,
      'auth/discovery-url': `https://cognito-idp.${cfg.region}.amazonaws.com/${this.userPool.userPoolId}/.well-known/openid-configuration`,
    });
  }
}
