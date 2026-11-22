import * as path from 'path';
import { Duration, RemovalPolicy, Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { YofinaConfig } from '../config/config';
import { publishParams } from './ssm-outputs';

export interface DataProps extends StackProps {
  readonly cfg: YofinaConfig;
}

/**
 * Aurora PostgreSQL Serverless v2 (Data API), VPC chỉ có subnet isolated (0 NAT, 0 VPC endpoint),
 * secret master và secret của role `yofina_app`, Lambda migrator.
 * Lambda nghiệp vụ nằm NGOÀI VPC và gọi Aurora qua Data API, nên không cần đường ra Internet.
 */
export class DataStack extends Stack {
  public readonly cluster: rds.DatabaseCluster;
  public readonly appSecret: secretsmanager.Secret;
  public readonly migrator: lambda.Function;

  constructor(scope: Construct, id: string, props: DataProps) {
    super(scope, id, props);
    const { cfg } = props;
    const p = cfg.prefix;

    const vpc = new ec2.Vpc(this, 'Vpc', {
      vpcName: `${p}-vpc`,
      ipAddresses: ec2.IpAddresses.cidr('10.40.0.0/16'),
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [{ name: 'isolated', subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 }],
    });

    const [major] = cfg.dbEngineVersion.split('.');
    this.cluster = new rds.DatabaseCluster(this, 'Cluster', {
      clusterIdentifier: `${p}-db`,
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.of(cfg.dbEngineVersion, major),
      }),
      writer: rds.ClusterInstance.serverlessV2('writer', { publiclyAccessible: false }),
      serverlessV2MinCapacity: cfg.dbMinAcu,
      serverlessV2MaxCapacity: cfg.dbMaxAcu,
      ...(cfg.dbMinAcu === 0 ? { serverlessV2AutoPauseDuration: Duration.seconds(cfg.dbAutoPauseSeconds) } : {}),
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      credentials: rds.Credentials.fromGeneratedSecret('yofina_admin', { secretName: `${p}-db-master` }),
      defaultDatabaseName: cfg.dbName,
      enableDataApi: true,
      storageEncrypted: true,
      deletionProtection: true,
      removalPolicy: RemovalPolicy.SNAPSHOT,
      backup: { retention: Duration.days(1) },
    });
    const masterSecret = this.cluster.secret;
    if (!masterSecret) throw new Error('Cluster thiếu secret master');

    // Secret riêng cho role yofina_app (non-owner, NOBYPASSRLS). Data API dùng secret nào là quyết định role nào.
    // Mật khẩu chỉ gồm chữ và số để migrator ghép vào câu lệnh an toàn.
    this.appSecret = new secretsmanager.Secret(this, 'AppSecret', {
      secretName: `${p}-db-app`,
      description: 'Role yofina_app cua Aurora (Data API)',
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ username: 'yofina_app' }),
        generateStringKey: 'password',
        passwordLength: 32,
        excludePunctuation: true,
      },
    });

    this.migrator = new lambda.Function(this, 'Migrator', {
      functionName: `${p}-migrator`,
      description: 'Tao/doi mat khau role yofina_app va chay db/migrations qua Data API',
      runtime: lambda.Runtime.PYTHON_3_13,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '..', 'lambdas', 'migrator'), {
        exclude: ['test_*.py', '__pycache__', '*.pyc'],
      }),
      memorySize: 256,
      timeout: Duration.minutes(15),
      logGroup: new logs.LogGroup(this, 'MigratorLogs', {
        logGroupName: `/aws/lambda/${p}-migrator`,
        retention: cfg.logRetentionDays as logs.RetentionDays,
        removalPolicy: RemovalPolicy.DESTROY,
      }),
      environment: {
        CLUSTER_ARN: this.cluster.clusterArn,
        DB_NAME: cfg.dbName,
        MASTER_SECRET_ARN: masterSecret.secretArn,
        APP_SECRET_ARN: this.appSecret.secretArn,
        APP_ROLE: 'yofina_app',
      },
    });
    this.cluster.grantDataApiAccess(this.migrator);
    masterSecret.grantRead(this.migrator);
    this.appSecret.grantRead(this.migrator);

    publishParams(this, {
      'db/cluster-arn': this.cluster.clusterArn,
      'db/name': cfg.dbName,
      'db/app-secret-arn': this.appSecret.secretArn,
      'db/migrator-function': this.migrator.functionName,
    });
  }
}
