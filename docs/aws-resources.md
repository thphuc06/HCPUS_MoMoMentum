# Tài nguyên AWS của dự án

Danh sách mọi tài nguyên dự án tạo trên AWS, Region `ap-southeast-1`. Quy ước: tên có tiền tố `yofina-`, tag `project=yofina` (CDK gắn ở mức app). **Không ghi account ID, ARN đầy đủ, secret hay email vào file này** (repo public). Cập nhật mỗi khi tạo, đổi hoặc xóa tài nguyên; đối chiếu với tài khoản khi đóng mỗi phase.

Không thuộc dự án, không được đụng: cluster Aurora và Cognito user pool có tên bắt đầu bằng `jars-dev`, các stack `Jars*`, stack `CDKToolkit`.

"Tính tiền khi nhàn rỗi": Có = có phí dù không dùng; Không = chỉ trả khi dùng (hoặc miễn phí ở mức dự án này).

## Do CDK tạo (app `infra-cdk/`)

### Stack `YofinaFoundation` (phase 1, termination protection)

| Tên | Loại | Phase | Tính tiền khi nhàn rỗi | Ghi chú |
|---|---|---|---|---|
| `yofina-artifacts-<account-id>-ap-southeast-1` | S3 bucket | 1 | Không (vài xu theo dung lượng) | Chặn public, `enforceSSL`, SSE-S3, lifecycle: xóa `tmp/` sau 30 ngày, `builds/` sau 90 ngày; RETAIN |
| `yofina-alerts` | SNS topic | 1 | Không | Cho Budgets publish; có một subscription email (chờ người nhận bấm link xác nhận) |
| `yofina-monthly` | AWS Budgets | 1 | Không | 100 USD/tháng, ngưỡng thực tế 50/80/100% gửi SNS; phạm vi cả tài khoản (`budgetScope=account`) |
| `yofina-confirm-jti` | DynamoDB | 1 | Không (on-demand) | Khóa `jti` (S), TTL `ttl`; token xác nhận dùng một lần |
| `yofina-usage` | DynamoDB | 1 | Không (on-demand) | Khóa `day` (S) + `model` (S), thuộc tính `count`, TTL `ttl`; đếm lượt gọi model theo ngày; RETAIN |
| `yofina-confirm-hmac` | Secrets Manager | 1 | Có (0,40 USD/tháng) | Khóa HMAC ký token xác nhận, sinh ngẫu nhiên |
| `/yofina/s3/…`, `sns/…`, `dynamodb/…`, `secrets/…` | SSM Parameter (String, standard) | 1 | Không | Giá trị cho luồng khác; xem [infra-cdk/README.md](../infra-cdk/README.md) |

### Stack `YofinaData` (phase 1, termination protection)

| Tên | Loại | Phase | Tính tiền khi nhàn rỗi | Ghi chú |
|---|---|---|---|---|
| `yofina-db` | Aurora PostgreSQL 17.11 cluster | 1 | Có (cùng với instance, xem dưới) | Serverless v2, Data API, mã hóa lưu trữ, deletion protection, backup 1 ngày, không public; DB `yofina` |
| `yofina-db` writer instance | Aurora serverless v2 instance | 1 | **Có: 0,5 ACU liên tục, khoảng 73 USD/tháng** | min 0,5, max 2 ACU; khoản lớn nhất của dự án |
| `yofina-vpc` | VPC + 2 subnet isolated, route table, security group, DB subnet group | 1 | Không | 0 NAT Gateway, 0 VPC endpoint, không Internet Gateway |
| `yofina-db-master` | Secrets Manager | 1 | Có (0,40 USD/tháng) | Do RDS/CDK sinh, chỉ migrator đọc; user `yofina_admin` |
| `yofina-db-app` | Secrets Manager | 1 | Có (0,40 USD/tháng) | Role `yofina_app` (non-owner, NOBYPASSRLS); mọi tool dùng secret này |
| `yofina-migrator` | Lambda (Python 3.13, arm64, ngoài VPC) + IAM role + log group (14 ngày) | 1 | Không | Tạo/đổi mật khẩu `yofina_app`, chạy `db/migrations/*.sql` qua Data API |
| `/yofina/db/…` | SSM Parameter | 1 | Không | cluster ARN, tên DB, ARN secret app, tên hàm migrator |

### Stack `YofinaIdentity` (phase 1, termination protection)

| Tên | Loại | Phase | Tính tiền khi nhàn rỗi | Ghi chú |
|---|---|---|---|---|
| `yofina-users` | Cognito user pool | 1 | Không (10.000 MAU đầu miễn phí) | Tắt tự đăng ký, đăng nhập bằng email, deletion protection, RETAIN |
| `yofina-web` | Cognito app client | 1 | Không | Công khai, không secret, SRP, access token 60 phút |
| `ops` | Cognito group | 1 | Không | |
| `/yofina/auth/…` | SSM Parameter | 1 | Không | user pool id, client id, discovery URL |

### Stack `YofinaFrontend` (phase 1)

| Tên | Loại | Phase | Tính tiền khi nhàn rỗi | Ghi chú |
|---|---|---|---|---|
| `yofina-web` | Amplify Hosting app + branch `main` | 1 | Không (theo băng thông/dung lượng) | Deploy thủ công bằng zip; rewrite SPA; header bảo mật cơ bản. URL: `https://main.dcrwn4u7vqklo.amplifyapp.com` (đang là trang thử hạ tầng) |
| `/yofina/frontend/…` | SSM Parameter | 1 | Không | app id, branch, URL |

## Không do CDK tạo

| Tên | Loại | Cách tạo | Phase | Tính tiền khi nhàn rỗi | Ghi chú |
|---|---|---|---|---|---|
| `yofina-demo-accounts` | Secrets Manager | `scripts/create_demo_users.py` | 1 | Có (0,40 USD/tháng) | JSON mật khẩu của 6 tài khoản demo (`minh`, `lan`, `khoa`, `giamkhao1`–`3`); 6 user tương ứng trong `yofina-users` |
| `/yofina/alert-email` | SSM Parameter (SecureString) | CLI, 2026-11-21 | 1 | Không | Email nhận cảnh báo ngân sách; chỉ `scripts/cdk.py` đọc; không ghi vào repo |
| `yofina-deployer` | IAM user (không access key) | CLI bằng phiên root, 2026-11-21 | 1 | Không | Gắn `AdministratorAccess` và inline policy `yofina-deny-jars-dev` (Deny RDS, Data API, Cognito, CloudFormation lên tài nguyên `jars-dev*` / stack `Jars*`). Chưa dùng: phase 1 deploy bằng phiên root của CLI (quyết định chủ dự án 2026-11-21) |

Có sẵn trong tài khoản, không do dự án tạo: stack `CDKToolkit` (bootstrap CDK, qualifier mặc định, version 32) ở `ap-southeast-1`. Dự án **dùng lại, không chạy lại bootstrap và không sửa**. Các stack `Jars*` thuộc dự án khác, không đụng.
