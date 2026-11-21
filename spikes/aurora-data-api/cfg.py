"""Lấy ARN động (không ghi account ID vào file)."""
import boto3
from bench_core import REGION, Api

CLUSTER_ID = "yofina-spike-db-cluster"
APP_SECRET_NAME = "yofina-spike-db-app"


def arns():
    rds = boto3.client("rds", region_name=REGION)
    sm = boto3.client("secretsmanager", region_name=REGION)
    c = rds.describe_db_clusters(DBClusterIdentifier=CLUSTER_ID)["DBClusters"][0]
    admin = c["MasterUserSecret"]["SecretArn"]
    try:
        app = sm.describe_secret(SecretId=APP_SECRET_NAME)["ARN"]
    except Exception:
        app = None
    return c["DBClusterArn"], admin, app


def apis():
    cl, ad, ap = arns()
    return Api(cl, ad), (Api(cl, ap) if ap else None), (cl, ad, ap)
