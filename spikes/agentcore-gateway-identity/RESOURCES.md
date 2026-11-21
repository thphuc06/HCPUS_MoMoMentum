# RESOURCES - tài nguyên AWS tạo bởi spike agentcore-gateway-identity

Region: `ap-southeast-1`. Tiền tố `yofina-spike-gw-`, tag `project=yofina-spike`. Không có account ID/secret/token trong file này.

| Thời điểm (UTC) | Loại | Tên / ID | Lệnh xóa |
|---|---|---|---|
| 01:54:56 | IAM role | `yofina-spike-gw-lambda-role` | `aws iam delete-role-policy --role-name yofina-spike-gw-lambda-role --policy-name inline && aws iam delete-role --role-name yofina-spike-gw-lambda-role` |
| 01:54:57 | IAM role | `yofina-spike-gw-gateway-role` | `aws iam delete-role-policy --role-name yofina-spike-gw-gateway-role --policy-name inline && aws iam delete-role --role-name yofina-spike-gw-gateway-role` |
| 01:55:17 | DynamoDB table | `yofina-spike-gw-jti` | `aws dynamodb delete-table --table-name yofina-spike-gw-jti --region ap-southeast-1` |
| 01:55:38 | Cognito user pool | `ap-southeast-1_x6HpVYWXT` | `aws cognito-idp delete-user-pool --user-pool-id ap-southeast-1_x6HpVYWXT --region ap-southeast-1` |
| 01:55:38 | Cognito app client | `7ag4skcm5h4gk47k0738d9jpn1` | `(xóa cùng user pool)` |
| 01:55:39 | Cognito user | `user-a` | `(xóa cùng user pool)` |
| 01:55:39 | Cognito user | `user-b` | `(xóa cùng user pool)` |
| 01:55:40 | Lambda function | `yofina-spike-gw-ledger` | `aws lambda delete-function --function-name yofina-spike-gw-ledger --region ap-southeast-1` |
| 01:55:44 | Lambda function | `yofina-spike-gw-interceptor` | `aws lambda delete-function --function-name yofina-spike-gw-interceptor --region ap-southeast-1` |
| 01:55:45 | Lambda function | `yofina-spike-gw-confirm` | `aws lambda delete-function --function-name yofina-spike-gw-confirm --region ap-southeast-1` |
| 01:56:00 | CloudWatch log groups (tự tạo khi Lambda chạy) | `/aws/lambda/yofina-spike-gw-ledger`, `-interceptor`, `-confirm` | `aws logs delete-log-group --log-group-name /aws/lambda/<tên> --region ap-southeast-1` |
| 01:56:38 | AgentCore Gateway | `yofina-spike-gw-plain-je4stj7vk8` | `aws bedrock-agentcore-control delete-gateway --gateway-identifier yofina-spike-gw-plain-je4stj7vk8 --region ap-southeast-1  (xóa target trước)` |
| 01:56:42 | Gateway target | `yofina-spike-gw-plain-je4stj7vk8/MQ9KHKBSSK (ledger)` | `xóa cùng gateway (delete-gateway-target trước)` |
| 01:57:03 | AgentCore Gateway | `yofina-spike-gw-main-bf1swg20zx` | `aws bedrock-agentcore-control delete-gateway --gateway-identifier yofina-spike-gw-main-bf1swg20zx --region ap-southeast-1  (xóa target trước)` |
| 01:57:07 | Gateway target | `yofina-spike-gw-main-bf1swg20zx/17Q2GDMPCR (ledger)` | `xóa cùng gateway (delete-gateway-target trước)` |
| 01:57:44 | Policy engine | `yofina_spike_gw_pe-e2xte218_5` | `aws bedrock-agentcore-control delete-policy-engine --policy-engine-id yofina_spike_gw_pe-e2xte218_5 --region ap-southeast-1  (xóa policy trước)` |
| 01:57:50 | Policy | `yofina_spike_gw_pe-e2xte218_5/read_own_balances-b_gmrp01h9 (read_own_balances)` | `xóa trước policy engine (delete-policy)` |
| 01:58:06 | Policy | `yofina_spike_gw_pe-e2xte218_5/write_confirmed_within_limit-fwnymdqweq (write_confirmed_within_limit)` | `xóa trước policy engine (delete-policy)` |
| 02:01:45 | Gateway target | `yofina-spike-gw-plain-je4stj7vk8/COBW09BJZN (aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)` | `xóa cùng gateway (delete-gateway-target trước)` |
| 02:01:51 | Gateway target | `yofina-spike-gw-plain-je4stj7vk8/FGVZ3KOOMY (a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a)` | `xóa cùng gateway (delete-gateway-target trước)` |
| 02:01:57 | Gateway target | `yofina-spike-gw-plain-je4stj7vk8/CDAXQ7TFH8 (tt)` | `xóa cùng gateway (delete-gateway-target trước)` |
| 02:02:03 | Gateway target | `yofina-spike-gw-plain-je4stj7vk8/L4ZGSYWNY3 (tt)` | `xóa cùng gateway (delete-gateway-target trước)` |
| 02:02:09 | Gateway target | `yofina-spike-gw-plain-je4stj7vk8/YOLYP120RB (tt)` | `xóa cùng gateway (delete-gateway-target trước)` |
| 02:02:14 | Gateway target | `yofina-spike-gw-plain-je4stj7vk8/IOSJW37BKA (tt)` | `xóa cùng gateway (delete-gateway-target trước)` |
| 02:02:22 | Gateway target | `yofina-spike-gw-plain-je4stj7vk8/L9NPJ4C98Q (tt)` | `xóa cùng gateway (delete-gateway-target trước)` |
| 02:02:28 | Gateway target | `yofina-spike-gw-plain-je4stj7vk8/CAGEI0MASU (tt)` | `xóa cùng gateway (delete-gateway-target trước)` |
| 02:03:15 | Gateway target | `yofina-spike-gw-main-bf1swg20zx/MVW8VWKYFB (ledgerx)` | `xóa cùng gateway (delete-gateway-target trước)` |
| 02:03:18 | Policy | `yofina_spike_gw_pe-e2xte218_5/read_hidden_any_authenticated-vf_zcfg4q4 (read_hidden_any_authenticated)` | `xóa trước policy engine (delete-policy)` |
| 02:04:00 | Policy | `yofina_spike_gw_pe-e2xte218_5/read_hidden_any_authenticated-looqhb5vka (read_hidden_any_authenticated)` | `xóa trước policy engine (delete-policy)` |
| 02:06:45 | AgentCore Gateway | `yofina-spike-gw-sem-iqbhgcywl5` | `aws bedrock-agentcore-control delete-gateway --gateway-identifier yofina-spike-gw-sem-iqbhgcywl5 --region ap-southeast-1  (xóa target trước)` |
| 02:06:48 | Gateway target | `yofina-spike-gw-sem-iqbhgcywl5/UAOZBNHYOA (ledger)` | `xóa cùng gateway (delete-gateway-target trước)` |
| 02:06:52 | Gateway target | `yofina-spike-gw-sem-iqbhgcywl5/EXRXG6WI8D (planner)` | `xóa cùng gateway (delete-gateway-target trước)` |
| 02:07:42 | Policy | `yofina_spike_gw_pe-e2xte218_5/forbid_username_user_b-2am3zyh9mt (forbid_username_user_b)` | `xóa trước policy engine (delete-policy)` |
| 02:08:24 | Policy | `yofina_spike_gw_pe-e2xte218_5/forbid_if_has_sub_tag-h1axbfhj5k (forbid_if_has_sub_tag)` | `xóa trước policy engine (delete-policy)` |

## Kết quả dọn (2026-11-21 02:11:34 UTC)

Đã xóa sạch, liệt kê lại không còn tài nguyên tiền tố `yofina-spike-gw-`.

Ghi chú dọn: trong lúc thử còn tạo thêm (và đã xóa ngay) vài target tạm để đo giới hạn tên (probe_limits.py) và 2 policy tạm (forbid_username_user_b, forbid_if_has_sub_tag) + 1 policy CREATE_FAILED (read_hidden_any_authenticated, bản đầu); `teardown.py` xóa theo tiền tố nên đã quét hết. Đã kiểm lại độc lập bằng AWS CLI (list-gateways, list-policy-engines, list-workload-identities, Lambda, IAM role, Cognito pool, DynamoDB): không còn gì tiền tố `yofina-spike-gw-`. Tài nguyên của spike khác (runtime `yofina_spike_rt_*`, pool `yofina-spike-rt-pool`) không bị đụng tới. Không bật Transaction Search, không tạo log delivery, không đổi cấu hình tài khoản.
