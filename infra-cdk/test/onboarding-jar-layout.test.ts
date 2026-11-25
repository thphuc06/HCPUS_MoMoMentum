// Công tắc quay lui bộ hũ onboarding (#39): context `onboardingJarLayout` (mặc định `catalogue`, quay lui `legacy`) thành biến môi
// trường `YOFINA_ONBOARDING_JAR_LAYOUT` của Lambda ledger (`yofina_ledger.jar_layout.onboarding_override`).
// `npm test` (node:test + tsx, không cần AWS, zip rỗng trong thư mục tạm).
import { after, before, describe, it } from 'node:test';
import * as assert from 'node:assert/strict';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { App } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { loadConfig } from '../config/config';
import { loadForecastConfig } from '../lib/forecast-pipeline';
import { loadToolsConfig, ONBOARDING_JAR_LAYOUTS, ToolsStack } from '../lib/tools-stack';

const ENV = { account: '111111111111', region: 'ap-southeast-1' }; // account giả của test
const EMPTY_ZIP = Buffer.from([0x50, 0x4b, 0x05, 0x06, ...new Array(18).fill(0)]);
const REPO = path.resolve(__dirname, '..', '..');

describe('công tắc quay lui YOFINA_ONBOARDING_JAR_LAYOUT', () => {
  let tmp: string;
  let context: Record<string, string>;

  before(() => {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'yofina-layout-test-'));
    for (const name of ['ledger-arm64.zip', 'forecast-arm64.zip']) fs.writeFileSync(path.join(tmp, name), EMPTY_ZIP);
    context = { ledgerZip: path.join(tmp, 'ledger-arm64.zip'), forecastZip: path.join(tmp, 'forecast-arm64.zip') };
  });

  after(() => fs.rmSync(tmp, { recursive: true, force: true }));

  function ledgerEnv(extra: Record<string, string>): Record<string, unknown> {
    const app = new App({ context: { ...context, ...extra } });
    const stack = new ToolsStack(app, 'YofinaTools', {
      env: ENV,
      cfg: loadConfig(app),
      tools: loadToolsConfig(app),
      forecast: loadForecastConfig(app),
    });
    const fns = Template.fromStack(stack).findResources('AWS::Lambda::Function', {
      Properties: { FunctionName: 'yofina-ledger' },
    }) as Record<string, { Properties: { Environment: { Variables: Record<string, unknown> } } }>;
    const [fn] = Object.values(fns);
    assert.ok(fn, 'không có Lambda yofina-ledger');
    return fn.Properties.Environment.Variables;
  }

  it('hai giá trị khớp jar_layout.py của ledger', () => {
    const src = fs.readFileSync(path.join(REPO, 'gateway', 'tools', 'ledger', 'yofina_ledger', 'jar_layout.py'), 'utf8');
    assert.deepEqual([...ONBOARDING_JAR_LAYOUTS], ['catalogue', 'legacy']);
    for (const v of ONBOARDING_JAR_LAYOUTS) assert.match(src, new RegExp(`'${v}'`));
  });

  it('mặc định catalogue: Lambda ledger nhận YOFINA_ONBOARDING_JAR_LAYOUT=catalogue', () => {
    assert.equal(loadToolsConfig(new App()).onboardingJarLayout, 'catalogue');
    assert.equal(ledgerEnv({}).YOFINA_ONBOARDING_JAR_LAYOUT, 'catalogue');
  });

  it('-c onboardingJarLayout=legacy: Lambda ledger nhận legacy, các biến khác không đổi', () => {
    const base = ledgerEnv({});
    const legacy = ledgerEnv({ onboardingJarLayout: 'legacy' });
    assert.equal(legacy.YOFINA_ONBOARDING_JAR_LAYOUT, 'legacy');
    const strip = (v: Record<string, unknown>) =>
      JSON.stringify(Object.fromEntries(Object.entries(v).filter(([k]) => k !== 'YOFINA_ONBOARDING_JAR_LAYOUT')));
    assert.equal(strip(legacy), strip(base));
  });

  it('giá trị lạ bị từ chối lúc synth (không để Lambda lỗi lúc tạo tài khoản)', () => {
    assert.throws(() => loadToolsConfig(new App({ context: { onboardingJarLayout: 'seven' } })), /onboardingJarLayout/);
  });
});
