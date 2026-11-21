# infra-cdk/

Hạ tầng dạng code bằng AWS CDK: Amplify Hosting, Cognito, AgentCore (Runtime V2 deploy bằng zip, Gateway kèm Lambda interceptor, Policy, Memory, Observability), Lambda tool (kèm Lambda container cho StatsForecast), API Gateway HTTP API + JWT (đề xuất), Aurora PostgreSQL Serverless v2 (Data API, giữ min 0,5 ACU khi demo), DynamoDB (token xác nhận, đề xuất), S3, EventBridge, SQS, Step Functions, KMS, WAF, CloudWatch. SageMaker (Chronos-2) chưa cần vì Chronos-2 đề xuất để ngoài MVP.

- Proposal: §8 (kiến trúc), §14 (hạ tầng dạng code: AWS CDK, khởi đầu từ khung FAST; GitHub Actions cho CI).
- Tự viết CDK theo tài liệu chính thức; `infra-cdk/` của FAST chỉ để tham khảo, không kéo về (quyết định 2026-11-21, khác proposal §14). Xem [../docs/architecture/project-structure.md](../docs/architecture/project-structure.md).
- Chốt Region triển khai và danh tính deploy (không dùng root) trước khi deploy: [../docs/requirements/open-questions.md](../docs/requirements/open-questions.md).
- Skill hữu ích: `aws-core:aws-cdk` ([../docs/references/aws-tooling.md](../docs/references/aws-tooling.md)).
- Đã dựng thử bằng CLI/boto3 (chưa CDK): Runtime zip + V2, Gateway + interceptor + Cedar, Aurora Data API; thứ tự tạo và bẫy: [spike-agentcore-runtime-cors.md](../docs/research/spike-agentcore-runtime-cors.md), [spike-agentcore-gateway-identity.md](../docs/research/spike-agentcore-gateway-identity.md), [spike-aurora-data-api.md](../docs/research/spike-aurora-data-api.md).