// Test construct YofinaGuardrail: `npm test` (node:test + tsx, không cần AWS).
import { describe, it } from 'node:test';
import * as assert from 'node:assert/strict';
import { App, Stack } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { APAC_GUARDRAIL_DESTINATION_REGIONS, YofinaGuardrail } from '../lib/guardrail';

const ENV = { account: '111111111111', region: 'ap-southeast-1' }; // account giả của test

describe('YofinaGuardrail', () => {
  it('ARN hồ sơ có đủ mọi vùng đích APAC (thiếu vùng thì ApplyGuardrail bị AccessDenied khi bị chuyển vùng)', () => {
    const stack = new Stack(new App(), 'T', { env: ENV });
    const g = new YofinaGuardrail(stack, 'G');
    const regions = g.profileDestinationArns.map((arn) => arn.split(':')[3]);
    for (const r of APAC_GUARDRAIL_DESTINATION_REGIONS) assert.ok(regions.includes(r), `thiếu vùng ${r}`);
    assert.ok(regions.includes('ap-south-1'));
    assert.equal(new Set(regions).size, regions.length, 'không lặp vùng');
    for (const arn of g.profileDestinationArns) {
      // phân vùng là token CDK (aws trong ap-southeast-1); phần còn lại là chữ cố định
      assert.match(arn, /^arn:.+:bedrock:[a-z0-9-]+:111111111111:guardrail-profile\/apac\.guardrail\.v1:0$/);
    }
    assert.ok(g.profileDestinationArns.includes(g.profileArn));
  });

  it('MISCONDUCT mặc định LOW, các bộ lọc khác giữ HIGH, PROMPT_ATTACK chỉ ở đầu vào', () => {
    const stack = new Stack(new App(), 'T', { env: ENV });
    new YofinaGuardrail(stack, 'G');
    const t = Template.fromStack(stack).findResources('AWS::Bedrock::Guardrail');
    const filters = (Object.values(t)[0] as any).Properties.ContentPolicyConfig.FiltersConfig as any[];
    const by = Object.fromEntries(filters.map((f) => [f.Type, f]));
    assert.equal(by.MISCONDUCT.InputStrength, 'LOW');
    for (const k of ['HATE', 'INSULTS', 'SEXUAL', 'VIOLENCE']) assert.equal(by[k].InputStrength, 'HIGH', k);
    assert.equal(by.PROMPT_ATTACK.InputStrength, 'HIGH');
    assert.equal(by.PROMPT_ATTACK.OutputStrength, 'NONE');
  });

  it('đổi cấu hình thì Description của version đổi (CloudFormation tạo version mới)', () => {
    const desc = (props?: ConstructorParameters<typeof YofinaGuardrail>[2]) => {
      const stack = new Stack(new App(), 'T', { env: ENV });
      new YofinaGuardrail(stack, 'G', props);
      const v = Template.fromStack(stack).findResources('AWS::Bedrock::GuardrailVersion');
      return (Object.values(v)[0] as any).Properties.Description as string;
    };
    assert.equal(desc(), desc(), 'cùng cấu hình thì cùng Description');
    assert.notEqual(desc(), desc({ filterStrengths: { MISCONDUCT: 'HIGH' } }));
    assert.ok(desc().length <= 200);
  });

  it('vùng đích truyền vào thì vẫn gồm vùng của stack', () => {
    const stack = new Stack(new App(), 'T', { env: ENV });
    const g = new YofinaGuardrail(stack, 'G', { profileDestinationRegions: ['ap-northeast-1'] });
    const regions = g.profileDestinationArns.map((arn) => arn.split(':')[3]);
    assert.deepEqual(regions.sort(), ['ap-northeast-1', 'ap-southeast-1']);
  });
});
