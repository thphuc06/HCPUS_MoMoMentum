#!/usr/bin/env node
import { App, Tags } from 'aws-cdk-lib';
import { loadConfig } from '../config/config';
import { DataStack } from '../lib/data-stack';
import { FoundationStack } from '../lib/foundation-stack';
import { FrontendStack } from '../lib/frontend-stack';
import { IdentityStack } from '../lib/identity-stack';

const app = new App();
const cfg = loadConfig(app);

// Account lấy từ credential hiện tại (CDK_DEFAULT_ACCOUNT); region đặt tường minh, không dựa vào mặc định của CLI.
const env = { account: process.env.CDK_DEFAULT_ACCOUNT, region: cfg.region };

new FoundationStack(app, 'YofinaFoundation', { env, cfg, terminationProtection: true });
new DataStack(app, 'YofinaData', { env, cfg, terminationProtection: true });
new IdentityStack(app, 'YofinaIdentity', { env, cfg, terminationProtection: true });
new FrontendStack(app, 'YofinaFrontend', { env, cfg });

Tags.of(app).add('project', 'yofina');
