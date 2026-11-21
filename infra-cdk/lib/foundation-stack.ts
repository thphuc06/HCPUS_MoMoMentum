import { Aws, Duration, RemovalPolicy, Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as budgets from 'aws-cdk-lib/aws-budgets';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as subs from 'aws-cdk-lib/aws-sns-subscriptions';
import { YofinaConfig } from '../config/config';
import { publishParams } from './ssm-outputs';

export interface FoundationProps extends StackProps {
  readonly cfg: YofinaConfig;
}

/**
 * Nền dùng chung: bucket artifact, SNS cảnh báo, AWS Budgets, hai bảng DynamoDB, secret HMAC.
 * Không có tài nguyên tính tiền theo giờ.
 */
export class FoundationStack extends Stack {
  public readonly artifactBucket: s3.Bucket;
  public readonly alertTopic: sns.Topic;
  public readonly confirmJtiTable: dynamodb.Table;
  public readonly usageTable: dynamodb.Table;
  public readonly confirmHmacSecret: secretsmanager.Secret;

  constructor(scope: Construct, id: string, props: FoundationProps) {
    super(scope, id, props);
    const { cfg } = props;
    const p = cfg.prefix;

    // --- S3 artifact: gói Lambda/Runtime, tệp tạm. Không public, bắt buộc TLS.
    this.artifactBucket = new s3.Bucket(this, 'Artifacts', {
      bucketName: `${p}-artifacts-${Aws.ACCOUNT_ID}-${Aws.REGION}`,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      removalPolicy: RemovalPolicy.RETAIN,
      lifecycleRules: [
        { id: 'abort-incomplete-multipart', abortIncompleteMultipartUploadAfter: Duration.days(7) },
        { id: 'expire-tmp', prefix: 'tmp/', expiration: Duration.days(30) },
        { id: 'expire-builds', prefix: 'builds/', expiration: Duration.days(90) },
      ],
    });

    // --- SNS cảnh báo (Budgets, alarm sau này). Không bật SSE-KMS vì Budgets không publish được vào topic mã hóa.
    this.alertTopic = new sns.Topic(this, 'Alerts', {
      topicName: `${p}-alerts`,
      displayName: 'Yofina alerts',
      enforceSSL: true,
    });
    this.alertTopic.addToResourcePolicy(
      new iam.PolicyStatement({
        sid: 'AWSBudgetsSNSPublishingPermissions',
        effect: iam.Effect.ALLOW,
        principals: [new iam.ServicePrincipal('budgets.amazonaws.com')],
        actions: ['sns:Publish'],
        resources: [this.alertTopic.topicArn],
        conditions: {
          StringEquals: { 'aws:SourceAccount': Aws.ACCOUNT_ID },
          ArnLike: { 'aws:SourceArn': `arn:${Aws.PARTITION}:budgets::${Aws.ACCOUNT_ID}:*` },
        },
      }),
    );
    if (cfg.alertEmail) {
      this.alertTopic.addSubscription(new subs.EmailSubscription(cfg.alertEmail));
    }

    // --- AWS Budgets theo tháng, ngưỡng thực tế gửi SNS.
    const budget = new budgets.CfnBudget(this, 'MonthlyBudget', {
      budget: {
        budgetName: `${p}-monthly`,
        budgetType: 'COST',
        timeUnit: 'MONTHLY',
        budgetLimit: { amount: cfg.budgetUsd, unit: 'USD' },
        ...(cfg.budgetScope === 'tag' ? { costFilters: { TagKeyValue: ['user:project$yofina'] } } : {}),
      },
      notificationsWithSubscribers: cfg.budgetThresholds.map((threshold) => ({
        notification: {
          notificationType: 'ACTUAL',
          comparisonOperator: 'GREATER_THAN',
          threshold,
          thresholdType: 'PERCENTAGE',
        },
        subscribers: [{ subscriptionType: 'SNS', address: this.alertTopic.topicArn }],
      })),
    });
    const topicPolicy = this.alertTopic.node.tryFindChild('Policy');
    if (topicPolicy) budget.node.addDependency(topicPolicy);

    // --- DynamoDB: token xác nhận dùng một lần (khóa jti, TTL) và đếm lượt gọi model theo ngày.
    this.confirmJtiTable = new dynamodb.Table(this, 'ConfirmJti', {
      tableName: `${p}-confirm-jti`,
      partitionKey: { name: 'jti', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'ttl',
      removalPolicy: RemovalPolicy.DESTROY,
    });
    // day = ngày (YYYY-MM-DD), model = nhóm model; thuộc tính `count` tăng bằng ADD nguyên tử.
    this.usageTable = new dynamodb.Table(this, 'Usage', {
      tableName: `${p}-usage`,
      partitionKey: { name: 'day', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'model', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'ttl',
      removalPolicy: RemovalPolicy.RETAIN,
    });

    // --- Secret HMAC ký token xác nhận; giá trị sinh ngẫu nhiên, không bao giờ nằm trong repo.
    this.confirmHmacSecret = new secretsmanager.Secret(this, 'ConfirmHmac', {
      secretName: `${p}-confirm-hmac`,
      description: 'Khoa HMAC ky token xac nhan ghi (Yofina)',
      generateSecretString: { passwordLength: 64, excludePunctuation: true },
    });

    publishParams(this, {
      's3/artifact-bucket': this.artifactBucket.bucketName,
      'sns/alert-topic-arn': this.alertTopic.topicArn,
      'dynamodb/confirm-jti-table': this.confirmJtiTable.tableName,
      'dynamodb/usage-table': this.usageTable.tableName,
      'secrets/confirm-hmac-arn': this.confirmHmacSecret.secretArn,
    });
  }
}
