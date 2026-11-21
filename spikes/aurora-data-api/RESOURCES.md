# Manifest tài nguyên AWS - spike Aurora Data API

Region: ap-southeast-1. Tag: project=yofina-spike. Tiền tố: yofina-spike-db-. Bắt đầu 2026-11-21.
(Không ghi account ID/secret/mật khẩu.)

| Loại | Tên/ID | Lệnh xóa | Trạng thái |
|---|---|---|---|
| DB subnet group | yofina-spike-db-subnets (subnet của VPC mặc định; subnet group "default" không tồn tại ở Region) | `aws rds delete-db-subnet-group --region ap-southeast-1 --db-subnet-group-name yofina-spike-db-subnets` | ĐÃ XÓA |
| RDS cluster | yofina-spike-db-cluster (aurora-postgresql 18.6, Serverless v2, Data API) | `aws rds delete-db-cluster --region ap-southeast-1 --db-cluster-identifier yofina-spike-db-cluster --skip-final-snapshot --delete-automated-backups` (xóa instance trước) | ĐÃ XÓA |
| Secret quản lý bởi RDS (master) | rds!cluster-... (tự tạo bởi ManageMasterUserPassword, xóa theo cluster) | `aws secretsmanager delete-secret --region ap-southeast-1 --secret-id <name> --force-delete-without-recovery` nếu còn sót | ĐÃ XÓA |
| RDS instance | yofina-spike-db-inst1 (db.serverless) | `aws rds delete-db-instance --region ap-southeast-1 --db-instance-identifier yofina-spike-db-inst1 --skip-final-snapshot` | ĐÃ XÓA |
| IAM role | yofina-spike-db-lambda-role (+ inline policy yofina-spike-db-lambda-policy, + AWSLambdaBasicExecutionRole) | `aws iam detach-role-policy --role-name yofina-spike-db-lambda-role --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole; aws iam delete-role-policy --role-name yofina-spike-db-lambda-role --policy-name yofina-spike-db-lambda-policy; aws iam delete-role --role-name yofina-spike-db-lambda-role` | ĐÃ XÓA |
| Secret (role app) | yofina-spike-db-app | `aws secretsmanager delete-secret --region ap-southeast-1 --secret-id yofina-spike-db-app --force-delete-without-recovery` | ĐÃ XÓA |
| Lambda | yofina-spike-db-bench (python3.13 arm64, 512 MB, ngoài VPC) | `aws lambda delete-function --region ap-southeast-1 --function-name yofina-spike-db-bench` | ĐÃ XÓA |
| CloudWatch log group | /aws/lambda/yofina-spike-db-bench | `MSYS_NO_PATHCONV=1 aws logs delete-log-group --region ap-southeast-1 --log-group-name /aws/lambda/yofina-spike-db-bench` (Git Bash cần MSYS_NO_PATHCONV) | ĐÃ XÓA |

## Kết quả dọn (2026-11-21)

Thứ tự: Lambda, secret app, IAM role (gỡ policy), log group; xóa instance (chờ `deleting` hết), xóa cluster (`--skip-final-snapshot --delete-automated-backups`, chờ `db-cluster-deleted`), xóa DB subnet group.

Kiểm tra lại sau khi xóa (ap-southeast-1):
- RDS cluster/instance: chỉ còn `<cluster có sẵn>` / `<cluster có sẵn>-writer` (tài nguyên có sẵn của người khác, KHÔNG đụng). Không còn gì có tiền tố `yofina-spike`.
- Cluster snapshot và automated backup của `yofina-spike-db-cluster`: không còn.
- DB subnet group: chỉ còn subnet group của stack khác; `yofina-spike-db-subnets` đã xóa.
- Secrets Manager (kể cả đang chờ xóa): secret master `rds!cluster-...` và `yofina-spike-db-app` không còn (chỉ còn secret của stack `<secret có sẵn>` có sẵn).
- Lambda `yofina-spike-*`, IAM role `yofina-spike-*`, log group `/aws/lambda/yofina-spike-*`: không còn.
- Không có gì chưa xóa được. Không tạo VPC/NAT/RDS Proxy/security group/access key. Security group dùng là `default` của VPC mặc định (có sẵn, không đụng).
