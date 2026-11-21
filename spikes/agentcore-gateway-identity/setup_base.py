"""Dựng nền: IAM role (Lambda, Gateway), DynamoDB jti, Cognito (pool, client, 2 user), 3 Lambda.
Chạy: uv run python setup_base.py   (idempotent ở mức 'tạo nếu chưa có')"""
import io, json, secrets, time, zipfile
from botocore.exceptions import ClientError
from common import *

iam, lam, ddb, cog = client("iam"), client("lambda"), client("dynamodb"), client("cognito-idp")
acct = account()
st = load_state()

LAMBDA_ROLE = PREFIX + "lambda-role"
GW_ROLE = PREFIX + "gateway-role"
TABLE = PREFIX + "jti"
POOL = PREFIX + "pool"
CLIENT = PREFIX + "client"


def trust(svc, extra=None):
    d = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": svc}, "Action": "sts:AssumeRole"}]}
    if extra:
        d["Statement"][0]["Condition"] = extra
    return json.dumps(d)


def role(name, trust_doc, policy):
    try:
        iam.create_role(RoleName=name, AssumeRolePolicyDocument=trust_doc, Tags=tag_list(),
                        Description="yofina spike - xoa sau khi do")
        record("IAM role", name, f"aws iam delete-role-policy --role-name {name} --policy-name inline && aws iam delete-role --role-name {name}")
    except ClientError as e:
        if e.response["Error"]["Code"] != "EntityAlreadyExists":
            raise
    iam.put_role_policy(RoleName=name, PolicyName="inline", PolicyDocument=json.dumps(policy))


def ensure_roles():
    role(LAMBDA_ROLE, trust("lambda.amazonaws.com"), {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
         "Resource": f"arn:aws:logs:{REGION}:{acct}:log-group:/aws/lambda/{PREFIX}*:*"},
        {"Effect": "Allow", "Action": "dynamodb:PutItem", "Resource": f"arn:aws:dynamodb:{REGION}:{acct}:table/{TABLE}"}]})
    role(GW_ROLE, trust("bedrock-agentcore.amazonaws.com",
                        {"StringEquals": {"aws:SourceAccount": acct},
                         "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-agentcore:{REGION}:{acct}:gateway/*"}}),
         {"Version": "2012-10-17", "Statement": [
             {"Effect": "Allow", "Action": "lambda:InvokeFunction",
              "Resource": [f"arn:aws:lambda:{REGION}:{acct}:function:{PREFIX}ledger",
                           f"arn:aws:lambda:{REGION}:{acct}:function:{PREFIX}interceptor"]},
             {"Effect": "Allow", "Action": ["bedrock-agentcore:GetPolicyEngine", "bedrock-agentcore:AuthorizeAction",
                                            "bedrock-agentcore:PartiallyAuthorizeActions"],
              "Resource": [f"arn:aws:bedrock-agentcore:{REGION}:{acct}:policy-engine/*",
                           f"arn:aws:bedrock-agentcore:{REGION}:{acct}:gateway/*"]}]})
    print("roles ok; chờ IAM lan truyền"); time.sleep(12)


def ensure_table():
    try:
        ddb.create_table(TableName=TABLE, BillingMode="PAY_PER_REQUEST",
                         AttributeDefinitions=[{"AttributeName": "jti", "AttributeType": "S"}],
                         KeySchema=[{"AttributeName": "jti", "KeyType": "HASH"}], Tags=tag_list())
        record("DynamoDB table", TABLE, f"aws dynamodb delete-table --table-name {TABLE} --region {REGION}")
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceInUseException":
            raise
    ddb.get_waiter("table_exists").wait(TableName=TABLE)


def ensure_cognito():
    pool_id = st.get("pool_id")
    if not pool_id:
        pool_id = cog.create_user_pool(PoolName=POOL, UserPoolTags=TAGS,
                                       Policies={"PasswordPolicy": {"MinimumLength": 12, "RequireUppercase": True, "RequireLowercase": True,
                                                                    "RequireNumbers": True, "RequireSymbols": True}})["UserPool"]["Id"]
        save_state(pool_id=pool_id)
        record("Cognito user pool", pool_id, f"aws cognito-idp delete-user-pool --user-pool-id {pool_id} --region {REGION}")
    cid = load_state().get("client_id")
    if not cid:
        cid = cog.create_user_pool_client(UserPoolId=pool_id, ClientName=CLIENT, GenerateSecret=False,
                                          ExplicitAuthFlows=["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"])["UserPoolClient"]["ClientId"]
        save_state(client_id=cid)
        record("Cognito app client", cid, "(xóa cùng user pool)")
    for u in ("user-a", "user-b"):
        try:
            cog.admin_create_user(UserPoolId=pool_id, Username=u, MessageAction="SUPPRESS")
            record("Cognito user", u, "(xóa cùng user pool)")
        except ClientError as e:
            if e.response["Error"]["Code"] != "UsernameExistsException":
                raise
    # mật khẩu đặt lại ngẫu nhiên mỗi lần chạy test (không lưu ở đâu cả)


def zip_dir(path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(path / "handler.py", "handler.py")
    return buf.getvalue()


def ensure_lambda(name, folder, env):
    role_arn = f"arn:aws:iam::{acct}:role/{LAMBDA_ROLE}"
    code = zip_dir(HERE / "lambdas" / folder)
    for _ in range(8):
        try:
            lam.create_function(FunctionName=name, Runtime="python3.13", Role=role_arn, Handler="handler.lambda_handler",
                                Code={"ZipFile": code}, Timeout=30, MemorySize=256, Environment={"Variables": env},
                                Tags=TAGS, Architectures=["arm64"])
            record("Lambda function", name, f"aws lambda delete-function --function-name {name} --region {REGION}")
            break
        except ClientError as e:
            c = e.response["Error"]["Code"]
            if c == "ResourceConflictException":
                lam.update_function_code(FunctionName=name, ZipFile=code)
                lam.get_waiter("function_updated").wait(FunctionName=name)
                lam.update_function_configuration(FunctionName=name, Environment={"Variables": env})
                break
            if c == "InvalidParameterValueException":      # role chưa lan truyền
                time.sleep(5); continue
            raise
    lam.get_waiter("function_active_v2").wait(FunctionName=name)


if __name__ == "__main__":
    ensure_roles()
    ensure_table()
    ensure_cognito()
    sec = st.get("_noop")  # secret không lưu local: lấy lại từ Lambda nếu đã có
    try:
        sec = lam.get_function_configuration(FunctionName=PREFIX + "confirm")["Environment"]["Variables"]["CONFIRM_SECRET"]
    except ClientError:
        sec = secrets.token_hex(32)
    ensure_lambda(PREFIX + "ledger", "ledger", {"CONFIRM_SECRET": sec, "JTI_TABLE": TABLE, "REQUIRE_TOKEN": "0"})
    ensure_lambda(PREFIX + "interceptor", "interceptor", {"MODE": "overwrite"})
    ensure_lambda(PREFIX + "confirm", "confirm", {"CONFIRM_SECRET": sec, "TOKEN_TTL": "120"})
    print("base xong:", load_state())
