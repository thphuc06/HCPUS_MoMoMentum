#!/usr/bin/env node
import { App, Tags } from 'aws-cdk-lib';
import { loadConfig } from '../config/config';
import { AgentStack, loadAgentConfig } from '../lib/agent-stack';
import { DataStack } from '../lib/data-stack';
import { FoundationStack } from '../lib/foundation-stack';
import { loadForecastConfig } from '../lib/forecast-pipeline';
import { FrontendStack } from '../lib/frontend-stack';
import { IdentityStack } from '../lib/identity-stack';
import { ToolsStack, loadToolsConfig } from '../lib/tools-stack';

const app = new App();
const cfg = loadConfig(app);

// Account lấy từ credential hiện tại (CDK_DEFAULT_ACCOUNT); region đặt tường minh, không dựa vào mặc định của CLI.
const env = { account: process.env.CDK_DEFAULT_ACCOUNT, region: cfg.region };

new FoundationStack(app, 'YofinaFoundation', { env, cfg, terminationProtection: true });
new DataStack(app, 'YofinaData', { env, cfg, terminationProtection: true });
new IdentityStack(app, 'YofinaIdentity', { env, cfg, terminationProtection: true });
new FrontendStack(app, 'YofinaFrontend', { env, cfg });
const toolsCfg = loadToolsConfig(app);
new ToolsStack(app, 'YofinaTools', { env, cfg, tools: toolsCfg, forecast: loadForecastConfig(app) });
new AgentStack(app, 'YofinaAgent', { env, cfg, tools: toolsCfg, agent: loadAgentConfig(app) });

Tags.of(app).add('project', 'yofina');
