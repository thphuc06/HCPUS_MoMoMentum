"""Tiện ích dùng chung cho các script trong scripts/ (không chạy trực tiếp).

Region đặt tường minh; mọi tên tài nguyên đọc từ SSM `/yofina/...` do CDK ghi, không gắn cứng trong script.
"""

from __future__ import annotations

import sys

import boto3

for _stream in (sys.stdout, sys.stderr):  # console Windows mặc định cp1252
    _stream.reconfigure(encoding="utf-8", errors="replace")

REGION = "ap-southeast-1"
SSM_PREFIX = "/yofina/"


def session() -> boto3.Session:
    return boto3.Session(region_name=REGION)


def ssm_param(name: str, *, sess: boto3.Session | None = None) -> str:
    """Đọc `/yofina/<name>` (name không có tiền tố)."""
    sess = sess or session()
    return sess.client("ssm").get_parameter(Name=SSM_PREFIX + name, WithDecryption=True)[
        "Parameter"
    ]["Value"]


def ssm_all(*, sess: boto3.Session | None = None) -> dict[str, str]:
    """Mọi tham số dưới /yofina/, khóa bỏ tiền tố. Trừ alert-email (không dùng cho môi trường)."""
    sess = sess or session()
    out: dict[str, str] = {}
    pager = sess.client("ssm").get_paginator("get_parameters_by_path")
    for page in pager.paginate(Path=SSM_PREFIX, Recursive=True, WithDecryption=True):
        for p in page["Parameters"]:
            key = p["Name"][len(SSM_PREFIX) :]
            if key != "alert-email":
                out[key] = p["Value"]
    return out
