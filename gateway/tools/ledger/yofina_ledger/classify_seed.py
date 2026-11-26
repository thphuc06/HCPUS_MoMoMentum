"""Nhãn k-NN seed của persona (`tx_embeddings_labeled`, nguồn `seed`): nạp khi đặt lại demo (nhiệm vụ N4, phase 4 luồng B).

Dữ liệu ở `data/personas/classify_labels/<persona>.json` do `evals/classification/build_seed_labels.py` sinh bằng Bedrock THẬT (vai `embedding`):
mỗi nhãn là một chuỗi giao dịch đã chuẩn hóa (bỏ dấu, chữ thường, mở rộng viết tắt) cùng hũ, kèm vector 1024 chiều dạng float16 little-endian rồi
base64 (2 KB mỗi vector thay vì 10 KB chữ). Nạp KHÔNG gọi Bedrock: Lambda ledger không có quyền Bedrock, và đặt lại phải nhanh.

Hàm `apply_seed_labels(db, user_id, persona)` KHÔNG tự chạy khi đặt lại: người điều phối gọi nó SAU transaction đặt lại (bảng nhãn có khóa ngoại
tới `jars`, nên đặt lại xóa nhãn cùng hũ). Nhãn vào hũ của ví theo cùng quy tắc với bước loại giao dịch của phân loại (`label_jar_pairs`); nhãn
không có hũ nào nhận thì bị bỏ qua.
"""

from __future__ import annotations

import base64
import json
import logging
import struct
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from importlib import resources
from typing import Any

from yofina_core.db import DataApi
from yofina_core.wallet import EMBEDDING_DIMENSIONS, transaction_jar
from yofina_ledger.classify_write import vector_literal

log = logging.getLogger("yofina.ledger.classify_seed")

LABELS_DIR = "classify_labels"
ENCODING = "float16-base64-le"
INSERT_CHUNK = 40


@dataclass(frozen=True)
class SeedLabel:
    text_norm: str
    jar_code: str
    embedding_b64: str


@dataclass(frozen=True)
class SeedSet:
    persona: str
    model: str
    labels: tuple[SeedLabel, ...]


def encode_vector(vec: Sequence[float]) -> str:
    """float -> float16 little-endian -> base64 (độ chính xác khoảng 3 chữ số thập phân, đủ cho cosine)."""
    if len(vec) != EMBEDDING_DIMENSIONS:
        raise ValueError(f"vector phải có {EMBEDDING_DIMENSIONS} chiều, nhận {len(vec)}")
    return base64.b64encode(struct.pack(f"<{len(vec)}e", *vec)).decode("ascii")


def decode_vector(b64: str) -> list[float]:
    raw = base64.b64decode(b64)
    if len(raw) != EMBEDDING_DIMENSIONS * 2:
        raise ValueError("vector seed sai kích thước")
    return list(struct.unpack(f"<{EMBEDDING_DIMENSIONS}e", raw))


def load_seed_set(persona: str) -> SeedSet | None:
    """Đọc file nhãn của persona; không có file thì None (persona chưa có nhãn seed)."""
    ref = resources.files("personas").joinpath(LABELS_DIR, f"{persona}.json")
    if not ref.is_file():
        return None
    data: dict[str, Any] = json.loads(ref.read_text(encoding="utf-8"))
    if data.get("encoding") != ENCODING or int(data.get("dimensions", 0)) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"{persona}.json: encoding hoặc số chiều không khớp ({ENCODING}, {EMBEDDING_DIMENSIONS})"
        )
    return SeedSet(
        persona=str(data["persona"]),
        model=str(data["model"]),
        labels=tuple(
            SeedLabel(str(x["text_norm"]), str(x["jar_code"]), str(x["embedding"]))
            for x in data["labels"]
        ),
    )


def label_jar_pairs(seed: SeedSet, jar_codes: Iterable[str]) -> list[tuple[SeedLabel, str]]:
    """Nhãn seed và hũ của ví nhận nó. Mã hũ của nhãn là nhóm của bộ bảy hũ (`an_uong`, `hoa_don`, `du_lich`...): hũ của ví đi
    cùng quy tắc với bước loại giao dịch của phân loại (`yofina_core.wallet.transaction_jar`, issue #39): hũ riêng khớp nhóm thắng
    (kể cả hũ mà ánh xạ bộ hũ cũ gộp nhóm vào, như Hóa đơn vào Nghĩa vụ), không có thì hũ chung (Chi hằng ngày, Nghĩa vụ). Nhãn
    không có hũ nào nhận thì bỏ."""
    codes = set(jar_codes)
    return [
        (lab, code)
        for lab in seed.labels
        if (code := transaction_jar(lab.jar_code, codes)) is not None
    ]


def apply_seed_labels(db: DataApi, user_id: str, persona: str) -> int:
    """Thay toàn bộ nhãn `seed` của người dùng bằng nhãn của persona (nhãn do người dùng sửa, nguồn `user`, giữ nguyên), mỗi nhãn
    vào hũ của ví theo `label_jar_pairs`.

    Một transaction. Trả số nhãn đã nạp (0 nếu persona không có file nhãn)."""
    seed = load_seed_set(persona)
    if seed is None:
        return 0
    with db.transaction(user_id) as t:
        jars = {
            r["code"]
            for r in t.execute(
                "SELECT code FROM jars WHERE user_id = :uid LIMIT 40", {"uid": user_id}
            )
        }
        t.execute(
            "DELETE FROM tx_embeddings_labeled WHERE user_id = :uid AND source = 'seed'",
            {"uid": user_id},
        )
        rows = [
            {
                "uid": user_id,
                "txt": lab.text_norm,
                "jar": code,
                "model": seed.model,
                "vec": vector_literal(decode_vector(lab.embedding_b64)),
            }
            for lab, code in label_jar_pairs(seed, jars)
        ]
        sql = (
            "INSERT INTO tx_embeddings_labeled (user_id, text_norm, jar_code, source, model, embedding) "
            "VALUES (:uid, :txt, :jar, 'seed', :model, CAST(:vec AS vector)) "
            "ON CONFLICT (user_id, text_norm, jar_code) DO NOTHING"
        )
        for i in range(0, len(rows), INSERT_CHUNK):
            t.batch(sql, rows[i : i + INSERT_CHUNK])
    log.info(json.dumps({"msg": "seed_labels_applied", "persona": persona, "labels": len(rows)}))
    return len(rows)
