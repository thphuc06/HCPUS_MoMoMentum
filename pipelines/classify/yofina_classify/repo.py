"""Truy cập Aurora của Lambda phân loại: đọc ngữ cảnh người dùng, nhãn k-NN. Phần GHI nằm ở `yofina_ledger.classify_write` (dùng lại đường ghi của ledger).

Đọc: `app_get_transaction` (một lệnh) rồi MỘT transaction với một câu SELECT gom hũ, người nhận, luật, lịch sử và số luật `once` (RLS theo `app.user_id`
do `DataApi.transaction` đặt). Nhãn: hàm `app_find_labeled_exact` và `app_knn_labeled` (migration 0052).
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any
from zoneinfo import ZoneInfo

from yofina_classify.model import (
    ExactLabel,
    JarInfo,
    Neighbor,
    RuleHit,
    TxFacts,
    TypeInfo,
    UserContext,
)
from yofina_core.db import DataApi, Row
from yofina_core.params import fold_text
from yofina_ledger import convert
from yofina_ledger.classify_write import vector_literal

SQL_TX = "SELECT * FROM app_get_transaction(CAST(:uid AS text), CAST(:id AS uuid))"
SQL_TX_TYPES = (
    "SELECT tx_type, label, direction, default_jar_code, system_role, is_person_transfer "
    "FROM tx_type_map ORDER BY sort_order, tx_type LIMIT 100"
)
SQL_CONTEXT = """
SELECT
  (SELECT coalesce(jsonb_agg(jsonb_build_object('code', j.code, 'name', j.name, 'kind', j.kind,
          'system_role', j.system_role, 'balance_vnd', j.balance_vnd) ORDER BY j.sort_order, j.code), '[]'::jsonb)
   FROM (SELECT * FROM jars WHERE user_id = :uid ORDER BY sort_order, code LIMIT 40) j) AS jars,
  (SELECT jsonb_build_object('correction_count', p.correction_count, 'auto_min_confidence', p.auto_min_confidence)
   FROM payees p WHERE p.user_id = :uid AND p.id = CAST(:pid AS uuid)) AS payee,
  (SELECT coalesce(jsonb_agg(jsonb_build_object('match_type', r.match_type, 'payee_id', r.payee_id,
          'merchant_key', r.merchant_key, 'jar_code', r.jar_code) ORDER BY (r.match_type = 'payee') DESC), '[]'::jsonb)
   FROM (SELECT * FROM category_rules WHERE user_id = :uid AND scope = 'always'
         AND ((match_type = 'payee' AND payee_id = CAST(:pid AS uuid))
           OR (match_type = 'merchant' AND merchant_key = CAST(:mkey AS text))) LIMIT 5) r) AS rules,
  (SELECT coalesce(jsonb_object_agg(h.jar_code, h.n), '{}'::jsonb)
   FROM (SELECT t.jar_code, count(*) AS n FROM transactions t
         JOIN jars j ON j.user_id = t.user_id AND j.code = t.jar_code
         WHERE t.user_id = :uid AND t.id <> CAST(:id AS uuid) AND t.kind = 'expense' AND j.system_role IS NULL
           AND ((CAST(:pid AS uuid) IS NOT NULL AND t.payee_id = CAST(:pid AS uuid))
             OR (CAST(:pid AS uuid) IS NULL AND CAST(:mkey AS text) IS NOT NULL
                 AND lower(t.merchant) = lower(CAST(:merchant AS text))))
         GROUP BY t.jar_code LIMIT 40) h) AS history,
  (SELECT count(*) FROM category_rules WHERE user_id = :uid AND scope = 'once'
         AND CAST(:mkey AS text) IS NOT NULL AND merchant_key = CAST(:mkey AS text)) AS merchant_corrections
"""
SQL_EXACT = "SELECT * FROM app_find_labeled_exact(CAST(:uid AS text), CAST(:txt AS text))"
SQL_KNN = (
    "SELECT * FROM app_knn_labeled(CAST(:uid AS text), CAST(:vec AS text), CAST(:k AS integer))"
)


class PgLabelIndex:
    """Cổng `LabelIndex` trên Aurora (nhãn của chính người dùng, RLS)."""

    def __init__(self, db: DataApi) -> None:
        self.db = db

    def find_exact(self, user_id: str, text_norm: str) -> list[ExactLabel]:
        rows = self.db.query(SQL_EXACT, {"uid": user_id, "txt": text_norm}, max_rows=5)
        return [ExactLabel(r["jar_code"], r["source"], i) for i, r in enumerate(rows)]

    def knn(self, user_id: str, vector: Sequence[float], k: int) -> list[Neighbor]:
        rows = self.db.query(
            SQL_KNN, {"uid": user_id, "vec": vector_literal(vector), "k": k}, max_rows=20
        )
        return [Neighbor(r["jar_code"], 1.0 - float(r["distance"]), r["source"]) for r in rows]


class ClassifyRepo:
    def __init__(self, db: DataApi, tz: ZoneInfo, *, reference_cache_seconds: int = 300) -> None:
        self.db = db
        self.tz = tz
        self._ttl = reference_cache_seconds
        self._types: tuple[float, dict[str, TypeInfo], set[str]] | None = None

    def _tx_types(self) -> tuple[dict[str, TypeInfo], set[str]]:
        now = time.monotonic()
        if self._types is None or now - self._types[0] > self._ttl:
            rows = self.db.query(SQL_TX_TYPES, max_rows=100)
            types = {
                r["tx_type"]: TypeInfo(
                    r["tx_type"], r["label"], r["direction"], r["default_jar_code"]
                )
                for r in rows
            }
            persons = {r["tx_type"] for r in rows if r.get("is_person_transfer")}
            self._types = (now, types, persons)
        return self._types[1], self._types[2]

    def load(self, user_id: str, transaction_id: str) -> tuple[TxFacts, UserContext] | None:
        rows = self.db.query(SQL_TX, {"uid": user_id, "id": transaction_id}, max_rows=1)
        if not rows:
            return None
        tx: Row = rows[0]
        types, person_types = self._tx_types()
        merchant = tx.get("merchant") or None
        payee_id = str(tx["payee_id"]) if tx.get("payee_id") else None
        mkey = fold_text(merchant)[:120] if merchant else None
        with self.db.transaction(user_id) as t:
            ctx_rows = t.execute(
                SQL_CONTEXT,
                {
                    "uid": user_id,
                    "id": transaction_id,
                    "pid": payee_id,
                    "mkey": mkey,
                    "merchant": merchant,
                },
            )
        c = ctx_rows[0]
        all_jars: list[dict[str, Any]] = c["jars"] or []
        unclassified = {j["code"] for j in all_jars if j.get("system_role") == "unclassified"}
        jars = {
            j["code"]: JarInfo(j["code"], j["name"], j["kind"], convert.vnd(j["balance_vnd"]))
            for j in all_jars
            if j.get("system_role") is None and j.get("kind") != "system"
        }
        rule: RuleHit | None = None
        for r in c["rules"] or []:
            if r["match_type"] == "payee" and r.get("payee_id"):
                rule = RuleHit("payee", str(r["payee_id"]), r["jar_code"])
                break
            if r["match_type"] == "merchant" and r.get("merchant_key"):
                rule = RuleHit("merchant", str(r["merchant_key"]), r["jar_code"])
        payee = c.get("payee") or {}
        amc = payee.get("auto_min_confidence")
        facts = TxFacts(
            transaction_id=str(tx["id"]),
            user_id=user_id,
            kind=tx["kind"],
            amount_vnd=abs(convert.vnd(tx["amount_vnd"])),
            occurred_at=convert.to_instant(tx["occurred_at"]),  # type: ignore[arg-type]
            app_date=convert.to_date(tx["app_date"]),  # type: ignore[arg-type]
            tx_type=tx["tx_type"],
            funding_source=tx["funding_source"],
            counterparty=merchant,
            note=tx.get("note") or None,
            payee_id=payee_id,
            is_person=bool(payee_id) or tx["tx_type"] in person_types,
            jar_code=tx.get("jar_code"),
            in_unclassified=tx.get("jar_code") in unclassified,
        )
        ctx = UserContext(
            jars=jars,
            type_map=types,
            rule=rule,
            payee_auto_min=None if amc is None else float(amc),
            merchant_corrections=int(c["merchant_corrections"] or 0),
            history={k: int(v) for k, v in (c["history"] or {}).items()},
            tz=self.tz,
        )
        return facts, ctx
