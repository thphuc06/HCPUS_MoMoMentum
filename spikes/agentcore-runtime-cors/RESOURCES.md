# Manifest tài nguyên AWS: spike agentcore-runtime-cors

Region: `ap-southeast-1` (mọi lệnh đặt tường minh). Tiền tố `yofina-spike-rt-` (Runtime chỉ cho phép `[a-zA-Z][a-zA-Z0-9_]*` nên dùng `yofina_spike_rt_`). Tag `project=yofina-spike` khi dịch vụ cho phép.
Không ghi account ID, secret, mật khẩu, token. `<ACCOUNT>` là chỗ giữ chỗ.

| # | Loại | Tên / ID | Tạo lúc | Lệnh xóa | Trạng thái |
|---|---|---|---|---|---|
| 1 | S3 bucket | `yofina-spike-rt-code-c62514f9` | 01:54Z | `aws s3 rb s3://yofina-spike-rt-code-c62514f9 --force --region ap-southeast-1` | ĐÃ XÓA 02:26Z |
| 3 | Cognito user pool | `ap-southeast-1_hMhN54emb` (`yofina-spike-rt-pool`) | 01:54Z | `aws cognito-idp delete-user-pool --user-pool-id ap-southeast-1_hMhN54emb --region ap-southeast-1` (xóa pool kéo theo client và user) | ĐÃ XÓA 02:26Z |
| 4 | Cognito app clients | `74l77tduats870badl4hk91a69` (`yofina-spike-rt-client`), `3k9t0igp5f66mmm48ocoo8a6jo` (`yofina-spike-rt-client-other`, dùng thử client không được phép) | 01:54Z | xóa cùng user pool (dòng 3) | ĐÃ XÓA 02:26Z |
| 5 | Cognito user | `spike-user` trong pool dòng 3 (mật khẩu ngẫu nhiên, không lưu trong repo) | 01:54Z | xóa cùng user pool | ĐÃ XÓA 02:26Z |
| 2 | IAM role | `yofina-spike-rt-exec` (+ inline policy `yofina-spike-rt-exec-policy`) | 01:54Z | `aws iam delete-role-policy --role-name yofina-spike-rt-exec --policy-name yofina-spike-rt-exec-policy; aws iam delete-role --role-name yofina-spike-rt-exec` | ĐÃ XÓA 02:26Z |
| 6 | AgentCore Runtime (protocol AGUI, CodeZip PYTHON_3_13) + endpoint DEFAULT + workload identity tự sinh | `yofina_spike_rt_agui-QNA2Io3ZJS` | 01:55Z | `aws bedrock-agentcore-control delete-agent-runtime --agent-runtime-id yofina_spike_rt_agui-QNA2Io3ZJS --region ap-southeast-1` | ĐÃ XÓA 02:26Z |
| 7 | CloudWatch log group (runtime tự tạo khi chạy) | `/aws/bedrock-agentcore/runtimes/yofina_spike_rt_agui-QNA2Io3ZJS-DEFAULT` | khi gọi lần đầu | `aws logs delete-log-group --log-group-name <tên> --region ap-southeast-1` | ĐÃ XÓA 02:22Z |
| 5b | Cognito user thứ hai | `spike-user-b` trong pool dòng 3 (thử session pinning giữa hai người dùng) | 01:59Z | xóa cùng user pool | ĐÃ XÓA 02:26Z |
| 6b | AgentCore Runtime thứ hai (platformVersion V2, cùng zip) + endpoint DEFAULT + workload identity | `yofina_spike_rt_agui_v2-qjC4IG8sis` | 02:01Z | `aws bedrock-agentcore-control delete-agent-runtime --agent-runtime-id yofina_spike_rt_agui_v2-qjC4IG8sis --region ap-southeast-1` | ĐÃ XÓA 02:26Z |
| 7b | CloudWatch log group runtime V2 | `/aws/bedrock-agentcore/runtimes/yofina_spike_rt_agui_v2-qjC4IG8sis-DEFAULT` | khi gọi | `aws logs delete-log-group --log-group-name <tên> --region ap-southeast-1` | ĐÃ XÓA 02:22Z |

Ghi chú: dòng 6, 6b: workload identity tự sinh của runtime biến mất cùng runtime (xác nhận bằng `list-workload-identities`). Log group runtime (dòng 7, 7b) do runtime tự tạo khi chạy, đã xóa bằng `aws logs delete-log-group` (trên Git Bash đặt `MSYS_NO_PATHCONV=1`). Runtime V1 xóa xong sau ~5 phút, V2 sau ~5 phút (trạng thái `DELETING` rồi biến mất khỏi `list-agent-runtimes`).

## Kết quả dọn (2026-11-21, ~02:26Z)

Thứ tự: xóa runtime (2) -> log group (2) -> Cognito user pool -> S3 bucket (`rb --force`) -> IAM role. Liệt kê lại sau khi xóa, Region `ap-southeast-1`:

| Kiểm tra | Kết quả |
|---|---|
| `list-agent-runtimes` lọc tên `yofina_spike_rt*` | 0 mục |
| `list-workload-identities` lọc `yofina_spike_rt` | rỗng |
| `describe-log-groups` tiền tố `/aws/bedrock-agentcore/runtimes/yofina_spike` | rỗng |
| `list-buckets` tiền tố `yofina-spike-rt` / `head-bucket` | rỗng / 404 |
| `iam get-role yofina-spike-rt-exec` | `NoSuchEntity` |
| `cognito-idp list-user-pools` tiền tố `yofina-spike-rt` | rỗng |

**Không còn tài nguyên sót.** Không tạo/đổi gì ngoài danh sách trên: không bật Transaction Search, không bootstrap CDK, không tạo access key. Service-linked role `AWSServiceRoleForBedrockAgentCoreRuntimeIdentity` (nếu được tạo/đã có trong tài khoản) là của dịch vụ, không phải do spike dựng nên giữ nguyên.
