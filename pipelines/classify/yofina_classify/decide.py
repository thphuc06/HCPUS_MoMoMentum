"""Quyết định thuần (không I/O): biến bằng chứng của từng bước thành hũ, độ tin cậy và mức tin cậy.

Hai bước đầu là **quyết định tuyệt đối** (không trộn): luật 'luôn luôn' của người dùng, rồi bảng tra loại giao dịch. Hai bước sau là **bằng chứng
xác suất** trộn bằng noisy-or: embedding (khớp chính xác, rồi k-NN) và model nhỏ (cộng tín hiệu hành vi). Mọi hệ số đọc từ `ClassifyThresholds`
(`classify_defaults.json`), không số nào gắn cứng ở đây.

- `knn_evidence`: từ các nhãn gần nhất, mỗi hũ lấy độ giống cao nhất (chỉ nhãn có độ giống từ `knn_min_similarity`); xác suất đúng của hũ dẫn đầu
  là hồi quy logistic (Platt) trên (độ giống, biên so với hũ thứ hai). Hệ số do `evals/classification/calibrate.py` ước lượng.
- `fuse`: điểm một hũ = 1 trừ tích (1 trừ p) của các bằng chứng cho hũ đó; độ tin cậy = điểm × (1 trừ `conflict_weight` × điểm cao nhất của hũ khác).
- `tier_of`: ba mức tin cậy (`wallet.CLASSIFICATION_TIERS`).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from yofina_classify.model import Evidence, ExactLabel, Neighbor, Verdict
from yofina_ledger.classify_config import ClassifyThresholds

CLASSIFIED_BY_OF = {
    "type_map": "type_map",
    "rule": "rule",
    "embedding": "embedding",
    "llm": "llm",
    # tín hiệu lặp lại cùng người nhận là một phần của bước model nhỏ (mô tả phase 4): `classified_by` không có giá trị riêng cho nó
    "history": "llm",
}


def sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def tier_of(confidence: float, auto_min: float, review_min: float) -> str:
    if confidence >= auto_min:
        return "auto"
    if confidence >= review_min:
        return "review"
    return "ask"


def knn_features(
    neighbors: Sequence[Neighbor], th: ClassifyThresholds
) -> list[tuple[str, float, float]]:
    """(hũ, độ giống cao nhất, biên) theo thứ tự giảm dần, chỉ hũ có nhãn từ `knn_min_similarity`.

    Biên của hũ dẫn đầu = độ giống của nó trừ độ giống của hũ thứ hai (không có hũ thứ hai thì trừ `knn_min_similarity`); của hũ thứ hai = độ
    giống của nó trừ độ giống của hũ dẫn đầu (âm)."""
    best: dict[str, float] = {}
    for n in neighbors:
        if n.similarity >= th.knn_min_similarity and n.similarity > best.get(n.jar_code, -1.0):
            best[n.jar_code] = n.similarity
    ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
    out: list[tuple[str, float, float]] = []
    for i, (jar, sim) in enumerate(ranked[:2]):
        if i == 0:
            margin = sim - (ranked[1][1] if len(ranked) > 1 else th.knn_min_similarity)
        else:
            margin = sim - ranked[0][1]
        out.append((jar, sim, margin))
    return out


def knn_evidence(neighbors: Sequence[Neighbor], th: ClassifyThresholds) -> list[Evidence]:
    ev: list[Evidence] = []
    for jar, sim, margin in knn_features(neighbors, th):
        p = sigmoid(th.knn_cal_intercept + th.knn_cal_w_sim * sim + th.knn_cal_w_margin * margin)
        ev.append(
            Evidence(jar, p, "embedding", f"knn sim={sim:.3f} margin={margin:.3f}", (sim, margin))
        )
    return ev


def exact_evidence(labels: Sequence[ExactLabel], th: ClassifyThresholds) -> list[Evidence]:
    """Chuỗi đã chuẩn hóa trùng đúng nhãn. Nhãn mới nhất thắng; nhãn cũ hơn cho hũ khác là bằng chứng yếu (nửa mức) để kéo tụt độ tin cậy."""
    ev: list[Evidence] = []
    seen: set[str] = set()
    for lab in sorted(labels, key=lambda x: x.rank):
        if lab.jar_code in seen:
            continue
        base = th.exact_match_confidence + (
            th.exact_match_user_bonus if lab.source == "user" else 0.0
        )
        p = min(base, 0.999) if not seen else min(base, 0.999) * 0.5
        ev.append(Evidence(lab.jar_code, p, "embedding", f"exact source={lab.source}"))
        seen.add(lab.jar_code)
    return ev


def history_evidence(history: dict[str, int], th: ClassifyThresholds) -> list[Evidence]:
    """Tín hiệu lặp lại: đủ `history_min_count` giao dịch trước cùng người nhận (hoặc đối tác) thì hũ phổ biến nhất có xác suất Laplace
    (k+1)/(n+2), có trần `history_max_confidence` (một mình nó không bao giờ tới mức tự gán)."""
    n = sum(history.values())
    if n < th.history_min_count or n == 0:
        return []
    jar, k = max(history.items(), key=lambda kv: kv[1])
    p = min((k + 1) / (n + 2), th.history_max_confidence)
    return [Evidence(jar, p, "history", f"{k}/{n} giao dịch trước")]


def llm_evidence(v: Verdict | None, th: ClassifyThresholds) -> list[Evidence]:
    if v is None or v.jar_code is None:
        return []
    p = sigmoid(th.llm_cal_intercept + th.llm_cal_slope * max(0.0, min(1.0, v.confidence)))
    ev = [Evidence(v.jar_code, p, "llm", f"model báo {v.confidence:.2f}", (v.confidence,))]
    if v.runner_up and v.runner_up != v.jar_code:
        ev.append(Evidence(v.runner_up, p * 0.3, "llm", "hũ thay thế của model"))
    return ev


def fuse(evidence: Sequence[Evidence], th: ClassifyThresholds) -> list[tuple[str, float]]:
    """Hũ ứng viên (giảm dần) và độ tin cậy sau khi trộn (xem docstring module)."""
    miss: dict[str, float] = {}
    for e in evidence:
        miss[e.jar] = miss.get(e.jar, 1.0) * (1.0 - max(0.0, min(1.0, e.p)))
    score = {jar: 1.0 - m for jar, m in miss.items()}
    out: list[tuple[str, float]] = []
    for jar, s in score.items():
        other = max((v for k, v in score.items() if k != jar), default=0.0)
        out.append((jar, s * (1.0 - th.conflict_weight * other)))
    out.sort(key=lambda kv: kv[1], reverse=True)
    return out


def dominant_source(evidence: Sequence[Evidence], jar: str) -> str:
    """Nguồn có xác suất cao nhất cho hũ thắng, đổi sang giá trị `classified_by`."""
    best = max((e for e in evidence if e.jar == jar), key=lambda e: e.p, default=None)
    return CLASSIFIED_BY_OF[best.source] if best else "llm"
