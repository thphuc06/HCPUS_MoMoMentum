# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3[crt]>=1.43,<2"]
# ///
"""Kiểm Data API bằng secret của role `yofina_app` (không phải master): chạy một câu SQL, in kết quả.

uv run scripts/db_check.py                      # SELECT 1, current_user
uv run scripts/db_check.py "SELECT count(*) FROM jars"
"""

from __future__ import annotations

import sys
import time

from _yofina import session, ssm_param
from botocore.exceptions import ClientError


def main() -> int:
    sql = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "SELECT 1 AS one, current_user AS who, current_database() AS db"
    )
    sess = session()
    rds = sess.client("rds-data")
    kwargs = dict(
        resourceArn=ssm_param("db/cluster-arn", sess=sess),
        secretArn=ssm_param("db/app-secret-arn", sess=sess),
        database=ssm_param("db/name", sess=sess),
        sql=sql,
        includeResultMetadata=True,
    )
    for attempt in range(30):
        try:
            r = rds.execute_statement(**kwargs)
            break
        except ClientError as e:
            if e.response["Error"]["Code"] != "DatabaseResumingException" or attempt == 29:
                raise
            time.sleep(2)
    cols = [c["name"] for c in r.get("columnMetadata", [])]
    print(cols)
    for row in r["records"]:
        print([next(iter(v.values())) if v else None for v in row])
    return 0


if __name__ == "__main__":
    sys.exit(main())
