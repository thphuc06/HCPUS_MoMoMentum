"""Phần GHI của phân hũ tự động, dùng chung giữa Lambda `yofina-classify` và Lambda ledger (`assign_jar`).

Nguyên tắc (ADR-0002, phase 4 luồng B): số dư hũ chỉ đổi bằng đường ghi sẵn có của ledger. Ở đây KHÔNG có câu SQL cập nhật số dư tự
viết: `write_auto_assign` dùng lại đúng các đoạn SQL của `WalletRepo.write_assign_jar` (`SQL_LOCK_TX`, `SQL_LOCK_TWO_JARS`, `_ASSIGN_HEAD`,
`_ASSIGN_TAIL`: khóa dòng, khóa hai hũ, đổi hũ của dòng sổ cái, cộng trừ số dư, ghi audit) rồi sửa nhãn phân loại trong CÙNG
transaction (cột `classified_by`, `classification_confidence`, `needs_review`, `suggested_jars` mà `yofina_app` được UPDATE). Vì sao
không gọi thẳng `write_assign_jar`: nó coi mọi lần gán là lời người dùng (đặt `classified_by = 'user'`, ghi luật `once`) và từ chối gán
cùng hũ, còn phân loại tự động phải ghi đúng bước đã gán, độ tin cậy, và không ghi luật.

Ba nhóm hàm:
- `write_auto_assign`, `write_ask_suggestions`, `upsert_review_ask`: Lambda phân loại.
- `write_confirm_same_jar`: "đúng rồi" cho mục "Xem lại" (`assign_jar` với chính hũ hiện tại; không chuyển tiền).
- `assign_context`, `record_assignment_feedback`: sau khi người dùng gán hũ, ghi nhãn k-NN, đếm lần sửa, nâng ngưỡng tự gán của người nhận
  và đóng câu hỏi gộp. Chạy sau commit của thao tác gán, KHÔNG BAO GIỜ làm hỏng nó (lỗi chỉ ghi log).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from yofina_core.db import DataApi
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.params import fold_text
from yofina_ledger.classify_config import ClassifyThresholds
from yofina_ledger.repo_wallet import (
    _ASSIGN_HEAD,
    _ASSIGN_RULE_MERCHANT_ALWAYS,
    _ASSIGN_RULE_PAYEE_ALWAYS,
    _ASSIGN_TAIL,
    SQL_LOCK_TWO_JARS,
    SQL_LOCK_TX,
    WriteResult,
    _vnd,
)

log = logging.getLogger("yofina.ledger.classify")

#: Bước tự động đã gán hũ (khác `user`, `seed`): sửa lại một dòng thuộc nhóm này là "sửa" theo nghĩa đếm lần sửa của người nhận.
AUTO_CLASSIFIED_BY = ("type_map", "rule", "embedding", "llm")
EVENT_TYPE_AUTO = "auto_classify"
TOOL_AUTO = "classify"


class AlreadyResolved(Exception):
    """Dòng sổ cái không còn ở hũ Chưa phân loại (người dùng đã tự gán, hoặc lần giao lại của sự kiện): không phải lỗi."""


@dataclass(frozen=True)
class AutoAssignResult:
    transaction_id: str
    from_jar: str
    to_jar: str
    amount_vnd: int
    kind: str
    funding_source: str
    deltas: dict[str, int]
    balances: dict[str, int]
    moves_money: bool


def write_auto_assign(
    db: DataApi,
    user_id: str,
    *,
    transaction_id: str,
    target_jar: str,
    classified_by: str,
    confidence: float,
    needs_review: bool,
    trace_id: str,
    audit_params: Mapping[str, Any],
    suggested: Sequence[str] = (),
    embedding: tuple[str, str, str] | None = None,
    rule_hit: tuple[str, str] | None = None,
) -> AutoAssignResult:
    """Gán một dòng đang ở Chưa phân loại vào `target_jar` (một transaction, số dư đổi qua SQL của `write_assign_jar`).

    `suggested` = hũ thay thế (tối đa 2) để "Xem lại" đổi bằng một chạm. `embedding` = (text_norm, model, vector-dạng-chuỗi) ghi vào
    `tx_embeddings` cùng transaction. `rule_hit` = (loại, khóa) của luật đã
    khớp để tăng `hit_count`. Ném `AlreadyResolved` nếu dòng không còn ở Chưa phân loại; `INSUFFICIENT_FUNDS` nếu hũ đích không đủ số
    dư (người gọi chuyển sang hỏi gộp)."""
    with db.transaction(user_id) as t:
        rows = t.execute(SQL_LOCK_TX, {"uid": user_id, "id": transaction_id})
        if not rows:
            raise YofinaError(ErrorCode.TRANSACTION_NOT_FOUND, "Không tìm thấy giao dịch.")
        row = rows[0]
        source = row["jar_code"]
        if row["kind"] == "transfer" or (row["kind"] == "income" and row["tx_type"] == "salary"):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Dòng này không phân loại hũ được.")
        jars = {
            j["code"]: j
            for j in t.execute(SQL_LOCK_TWO_JARS, {"uid": user_id, "a": source, "b": target_jar})
        }
        src, dst = jars.get(source), jars.get(target_jar)
        if src is None or dst is None:
            raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ.")
        if src["system_role"] != "unclassified":
            raise AlreadyResolved(transaction_id)
        if dst["kind"] == "system":
            raise YofinaError(ErrorCode.JAR_PROTECTED, "Không gán vào hũ hệ thống.")
        signed = _vnd(row["amount_vnd"])
        moves = row["funding_source"] == "jar"
        deltas: dict[str, int] = {}
        if moves:
            deltas = {source: -signed, target_jar: signed}
            if _vnd(dst["balance_vnd"]) + deltas[target_jar] < 0:
                raise YofinaError(ErrorCode.INSUFFICIENT_FUNDS, f"Hũ {dst['name']} không đủ số dư.")
        params: dict[str, Any] = {
            "uid": user_id,
            "id": transaction_id,
            "to_jar": target_jar,
            "deltas": [{"code": c, "delta": d} for c, d in deltas.items()],
            "trace_id": trace_id,
            "event_type": EVENT_TYPE_AUTO,
            "tool": TOOL_AUTO,
            "params": dict(audit_params),
            "details": {"classified_by": classified_by, "confidence": round(confidence, 3)},
        }
        out = t.execute(_ASSIGN_HEAD + _ASSIGN_TAIL, params)
        if not out or not out[0].get("tx_id"):
            raise YofinaError(ErrorCode.INTERNAL_ERROR, "Không gán được hũ.")
        t.execute(
            "UPDATE transactions SET classified_by = :cb, classification_confidence = CAST(:conf AS numeric), "
            "needs_review = :nr, suggested_jars = CAST(:sj AS text[]) WHERE user_id = :uid AND id = CAST(:id AS uuid)",
            {
                "uid": user_id,
                "id": transaction_id,
                "cb": classified_by,
                "conf": f"{confidence:.3f}",
                "nr": needs_review,
                "sj": pg_array(suggested),
            },
        )
        if embedding is not None:
            _insert_embedding(t, user_id, transaction_id, *embedding)
        if rule_hit is not None:
            _bump_rule(t, user_id, *rule_hit)
        balances = {c: _vnd(jars[c]["balance_vnd"]) + d for c, d in deltas.items()}
    return AutoAssignResult(
        transaction_id=transaction_id,
        from_jar=source,
        to_jar=target_jar,
        amount_vnd=abs(signed),
        kind=row["kind"],
        funding_source=row["funding_source"],
        deltas=deltas,
        balances=balances,
        moves_money=moves,
    )


def write_ask_suggestions(
    db: DataApi,
    user_id: str,
    *,
    transaction_id: str,
    suggested: Sequence[str],
    confidence: float | None,
    ask_date: date,
    embedding: tuple[str, str, str] | None = None,
) -> tuple[int, int]:
    """Giao dịch ở lại Chưa phân loại: ghi gợi ý (tối đa 2 mã hũ), độ tin cậy của gợi ý đầu, và lưu embedding; rồi mở hoặc cập nhật câu
    hỏi gộp của `ask_date`. Trả (số giao dịch đang chờ, tổng tiền)."""
    with db.transaction(user_id) as t:
        t.execute(
            "UPDATE transactions SET suggested_jars = CAST(:sj AS text[]), "
            "classification_confidence = CAST(:conf AS numeric), needs_review = true "
            "WHERE user_id = :uid AND id = CAST(:id AS uuid)",
            {
                "uid": user_id,
                "id": transaction_id,
                "sj": pg_array(suggested),
                "conf": None if confidence is None else f"{confidence:.3f}",
            },
        )
        if embedding is not None:
            _insert_embedding(t, user_id, transaction_id, *embedding)
        return upsert_review_ask(t, user_id, ask_date)


def vector_literal(vec: Sequence[float]) -> str:
    """Chuỗi pgvector `[x,y,...]` (cách truyền được Data API chấp nhận qua CAST, spike Aurora §3)."""
    return "[" + ",".join(f"{x:.6g}" for x in vec) + "]"


def pg_array(codes: Sequence[str]) -> str | None:
    """Mã hũ (chữ thường, số, gạch dưới theo CHECK của jars.code) thành literal mảng Postgres; rỗng thì NULL. Tối đa 2 phần tử."""
    clean = [c for c in codes[:2] if c and all(ch.isalnum() or ch == "_" for ch in c)]
    return "{" + ",".join(clean) + "}" if clean else None


def upsert_review_ask(t: Any, user_id: str, ask_date: date) -> tuple[int, int]:
    """Mở câu hỏi gộp của `ask_date` (một dòng mỗi ngày, DB bảo đảm bằng UNIQUE) và cập nhật số mục, tổng tiền từ tập đang chờ thật.

    `skipped` giữ nguyên (người dùng đã để sau: hôm nay không hỏi lại); `answered` mở lại khi lại có mục mới."""
    pending = t.execute(_SQL_PENDING, {"uid": user_id})[0]
    n, total = int(pending["n"]), _vnd(pending["total"])
    t.execute(
        "INSERT INTO review_asks (user_id, ask_date, status, item_count, pending_total_vnd) "
        "VALUES (:uid, CAST(:d AS date), 'open', :n, CAST(:total AS numeric)) "
        "ON CONFLICT (user_id, ask_date) DO UPDATE SET item_count = EXCLUDED.item_count, "
        "pending_total_vnd = EXCLUDED.pending_total_vnd, "
        "status = CASE WHEN review_asks.status = 'answered' THEN 'open' ELSE review_asks.status END, "
        "resolved_at = CASE WHEN review_asks.status = 'answered' THEN NULL ELSE review_asks.resolved_at END",
        {"uid": user_id, "d": ask_date, "n": n, "total": total},
    )
    return n, total


_SQL_PENDING = (
    "SELECT count(*) AS n, coalesce(sum(abs(t.amount_vnd)), 0) AS total FROM transactions t "
    "JOIN jars j ON j.user_id = t.user_id AND j.code = t.jar_code "
    "WHERE t.user_id = :uid AND t.kind <> 'transfer' AND j.system_role = 'unclassified'"
)


def _insert_embedding(
    t: Any, user_id: str, tx_id: str, text_norm: str, model: str, vector: str
) -> None:
    t.execute(
        "INSERT INTO tx_embeddings (transaction_id, user_id, text_norm, model, embedding) "
        "VALUES (CAST(:id AS uuid), :uid, :txt, :model, CAST(:vec AS vector)) ON CONFLICT (transaction_id) DO NOTHING",
        {"uid": user_id, "id": tx_id, "txt": text_norm, "model": model, "vec": vector},
    )


def _bump_rule(t: Any, user_id: str, match_type: str, key: str) -> None:
    col = "payee_id = CAST(:k AS uuid)" if match_type == "payee" else "merchant_key = :k"
    t.execute(
        "UPDATE category_rules SET hit_count = hit_count + 1, last_used_at = now() "
        f"WHERE user_id = :uid AND scope = 'always' AND match_type = :mt AND {col}",
        {"uid": user_id, "mt": match_type, "k": key},
    )


# --- "đúng rồi": gán CÙNG hũ hiện tại ---------------------------------------------------------------------------
_CONFIRM_HEAD = (
    "WITH utx AS (UPDATE transactions SET classified_by = 'user', needs_review = false, "
    "classification_confidence = NULL, suggested_jars = NULL WHERE user_id = :uid AND id = CAST(:id AS uuid) "
    "RETURNING id), "
)


def is_confirm_same_jar(tx: Mapping[str, Any], norm: Mapping[str, Any]) -> bool:
    """`assign_jar` với chính hũ hiện tại của một mục đang chờ xem lại (`needs_review`): xác nhận, không chuyển tiền."""
    return bool(tx.get("needs_review")) and tx.get("jar_code") == norm.get("jar")


def write_confirm_same_jar(
    repo: Any,
    user_id: str,
    *,
    norm: Mapping[str, Any],
    now: datetime,
    app_date: date,
    audit: Mapping[str, Any],
    claim: Any,
    tool: str,
) -> WriteResult:
    """Xác nhận hũ hiện tại: xóa cờ cần xem lại, `classified_by` thành user, không đổi số dư. `remember` always vẫn lưu luật.

    `repo` là `LedgerRepo` (cần `db` và `_claim` để ghi biên nhận của đề nghị cùng transaction)."""
    tid, jar = norm["transaction_id"], norm["jar"]
    with repo.db.transaction(user_id) as t:
        rows = t.execute(SQL_LOCK_TX, {"uid": user_id, "id": tid})
        if not rows:
            raise YofinaError(ErrorCode.TRANSACTION_NOT_FOUND, "Không tìm thấy giao dịch.")
        row = rows[0]
        if row["jar_code"] != jar:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Giao dịch không còn ở hũ này.")
        jars = t.execute(SQL_LOCK_TWO_JARS, {"uid": user_id, "a": jar, "b": jar})
        if not jars:
            raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ.")
        remember = norm.get("remember", "once")
        payee_id = str(row["payee_id"]) if row["payee_id"] else None
        merchant_key = fold_text(row["merchant"])[:120] if row["merchant"] else None
        rule = ""
        if remember == "always":
            if payee_id:
                rule = _ASSIGN_RULE_PAYEE_ALWAYS
            elif merchant_key:
                rule = _ASSIGN_RULE_MERCHANT_ALWAYS
            else:
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID,
                    "Giao dịch này không có người nhận hay đối tác để nhớ thành luật.",
                )
        params: dict[str, Any] = {
            "uid": user_id,
            "id": tid,
            "to_jar": jar,
            "trace_id": audit["trace_id"],
            "event_type": audit["event_type"],
            "tool": tool,
            "params": audit["params"],
            "details": audit["details"],
        }
        if rule:
            params["payee_id" if payee_id else "merchant_key"] = payee_id or merchant_key
        out = t.execute(_CONFIRM_HEAD + rule + _ASSIGN_TAIL, params)
        if not out or not out[0].get("tx_id"):
            raise YofinaError(ErrorCode.INTERNAL_ERROR, "Không xác nhận được hũ.")
        signed = _vnd(row["amount_vnd"])
        jar_row = jars[0]
        result = WriteResult(
            tool=tool,
            reference_id=tid,
            occurred_at=now,
            app_date=app_date,
            jars_after=[
                {"code": jar, "name": jar_row["name"], "balance_vnd": _vnd(jar_row["balance_vnd"])}
            ],
            deltas={},
            facts={
                "from_jar": jar,
                "from_jar_name": jar_row["name"],
                "to_jar": jar,
                "to_jar_name": jar_row["name"],
                "amount_vnd": abs(signed),
                "kind": row["kind"],
                "moves_money": False,
                "funding_source": row["funding_source"],
                "remember": remember if rule else "once",
                "rule_saved": bool(rule),
                "confirmed_same_jar": True,
            },
        )
        repo._claim(t, user_id, claim, result)
    return result


# --- sau khi người dùng gán hũ: nhãn, đếm sửa, ngưỡng riêng, đóng câu hỏi ---------------------------------------------
@dataclass(frozen=True)
class AssignContext:
    """Trạng thái của dòng TRƯỚC khi gán (sau khi gán `classified_by` đã thành user nên phải đọc trước)."""

    classified_by: str | None
    jar_code: str | None
    jar_system_role: str | None
    payee_id: str | None
    merchant: str | None


def assign_context(db: DataApi, user_id: str, transaction_id: str) -> AssignContext | None:
    """Đọc nhãn phân loại hiện tại của dòng. None nếu không đọc được (không chặn việc gán)."""
    try:
        with db.transaction(user_id) as t:
            rows = t.execute(
                "SELECT t.classified_by, t.jar_code, j.system_role, t.payee_id, t.merchant FROM transactions t "
                "LEFT JOIN jars j ON j.user_id = t.user_id AND j.code = t.jar_code "
                "WHERE t.user_id = :uid AND t.id = CAST(:id AS uuid)",
                {"uid": user_id, "id": transaction_id},
            )
    except Exception:
        log.warning("assign_context_failed", exc_info=True)
        return None
    if not rows:
        return None
    r = rows[0]
    return AssignContext(
        r["classified_by"],
        r["jar_code"],
        r["system_role"],
        str(r["payee_id"]) if r["payee_id"] else None,
        r["merchant"],
    )


def is_correction(before: AssignContext | None, target_jar: str) -> bool:
    """Sửa một lần gán TỰ ĐỘNG sang hũ khác (không tính trả lời câu hỏi gộp, không tính xác nhận cùng hũ)."""
    return (
        before is not None
        and before.classified_by in AUTO_CLASSIFIED_BY
        and before.jar_system_role != "unclassified"
        and before.jar_code != target_jar
    )


def record_assignment_feedback(
    db: DataApi,
    user_id: str,
    *,
    transaction_id: str,
    target_jar: str,
    before: AssignContext | None,
    thresholds: ClassifyThresholds,
) -> dict[str, Any]:
    """Hậu quả của một lần người dùng gán hũ (hoặc xác nhận cùng hũ), trong MỘT transaction. Không ném ngoại lệ: lỗi thì log, trả `{}`.

    1. Nhãn k-NN: nếu giao dịch đã có embedding (bước 2 đã chạy), nhãn `user` (chuỗi đã chuẩn hóa -> hũ) vào `tx_embeddings_labeled`.
       Chưa có embedding (giao dịch được gán ở bước bảng tra hay luật, hoặc dòng seed) thì không có nhãn: luật `always` (nếu chọn) vẫn có.
    2. Đếm lần sửa của người nhận và nâng ngưỡng tự gán riêng (chỉ khi là SỬA một lần gán tự động sang hũ khác).
    3. Đóng câu hỏi gộp đang mở nếu không còn giao dịch nào ở Chưa phân loại.
    """
    out: dict[str, Any] = {}
    try:
        with db.transaction(user_id) as t:
            labeled = t.execute(
                "INSERT INTO tx_embeddings_labeled (user_id, text_norm, jar_code, source, transaction_id, model, embedding) "
                "SELECT e.user_id, e.text_norm, :jar, 'user', e.transaction_id, e.model, e.embedding "
                "FROM tx_embeddings e WHERE e.user_id = :uid AND e.transaction_id = CAST(:id AS uuid) "
                "ON CONFLICT (user_id, text_norm, jar_code) DO UPDATE SET created_at = now(), source = 'user', "
                "transaction_id = EXCLUDED.transaction_id, model = EXCLUDED.model, embedding = EXCLUDED.embedding "
                "RETURNING id",
                {"uid": user_id, "id": transaction_id, "jar": target_jar},
            )
            out["label_saved"] = bool(labeled)
            if before is not None and is_correction(before, target_jar) and before.payee_id:
                rows = t.execute(
                    "UPDATE payees SET correction_count = correction_count + 1, auto_min_confidence = CASE "
                    "WHEN correction_count + 1 >= :min_n THEN LEAST(CAST(:cap AS numeric), "
                    "COALESCE(auto_min_confidence, CAST(:base AS numeric)) + CAST(:step AS numeric)) "
                    "ELSE auto_min_confidence END "
                    "WHERE user_id = :uid AND id = CAST(:pid AS uuid) RETURNING correction_count, auto_min_confidence",
                    {
                        "uid": user_id,
                        "pid": before.payee_id,
                        "min_n": thresholds.correction_min_count,
                        "cap": f"{thresholds.auto_min_confidence_cap:.3f}",
                        "base": f"{thresholds.auto_min_confidence:.3f}",
                        "step": f"{thresholds.auto_min_confidence_step:.3f}",
                    },
                )
                if rows:
                    out["correction_count"] = int(rows[0]["correction_count"])
                    amc = rows[0]["auto_min_confidence"]
                    out["auto_min_confidence"] = None if amc is None else float(amc)
            closed = t.execute(
                "UPDATE review_asks SET status = 'answered', resolved_at = now() WHERE user_id = :uid AND status = 'open' "
                "AND NOT EXISTS (SELECT 1 FROM transactions t JOIN jars j ON j.user_id = t.user_id AND j.code = t.jar_code "
                "WHERE t.user_id = :uid AND t.kind <> 'transfer' AND j.system_role = 'unclassified') RETURNING id",
                {"uid": user_id},
            )
            out["ask_closed"] = len(closed)
    except Exception:
        log.warning(
            json.dumps({"msg": "assign_feedback_failed", "tx": transaction_id}), exc_info=True
        )
        return {}
    return out
