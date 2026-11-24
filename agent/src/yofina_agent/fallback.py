"""Bộ phân loại dự phòng dựa trên luật (SUY GIẢM CÓ KIỂM SOÁT, không phải đường chính).

Chỉ dùng khi router bằng LLM không gọi được (chạm trần lượt gọi, mọi model lỗi, JSON hỏng).
Mục đích duy nhất: vẫn nhận ra mấy ý định mà agent có tool tất định cho, để người dùng nhận được
thẻ số liệu thật từ tool thay vì luồng rỗng. Không phải nhánh riêng cho câu nào: luật chỉ dựa trên
từ khóa chung và nhãn cú sốc trong cấu hình. Tên hũ vẫn được ánh xạ bằng dữ liệu tool.
Câu không khớp luật nào trả `None`: agent hiện thông báo "chưa xử lý được" chứ không đoán.

What-if và kiểm tra trước khi chi còn cần hũ nguồn và cách trả để dựng kịch bản bằng mã (`whatif.deterministic_spec`) và để thẻ
kiểm tra có "hũ trả": luật tách cụm tên hũ sau "hũ" hoặc "từ/trong" (chỉ là chữ người dùng gõ; ánh xạ ra mã hũ vẫn bằng dữ liệu tool),
nhận "Trả sau"/BNPL, và tên món sau "mua"/"cho". Thiếu dữ kiện thì để trống cho luồng chính hỏi lại, không đoán.
"""

from __future__ import annotations

import re

from yofina_agent.schemas import IntentParams, IntentResult
from yofina_agent.textutil import goal_date_phrase, match_shock_id, normalize, parse_amount_vnd

_BALANCE = ("so du", "con bao nhieu", "con lai bao nhieu", "cac hu", "hu cua minh", "tong tien")
_TRANSACTIONS = ("giao dich", "lich su", "da tieu", "chi tieu gan day", "chi gan day", "vua tieu")
_OBLIGATIONS = ("den han", "sap den han", "khoan phai tra", "no cua minh", "nghia vu")
_FORECAST = (
    "du bao",
    "tru duoc",
    "bao lau",
    "het tien",
    "can tien",
    "du toi ky luong",
    "du den ky luong",
    "sap can",
    "bi hut",
)
_FORECAST_WHEN = re.compile(r"\b(?:khi nao|bao gio)\b.*\b(?:can|het)\b")  # "khi nào hũ X cạn"
_WHAT_IF = re.compile(
    r"\b(?:neu|gia su)\b.*\b(?:thi sao|thi the nao|se ra sao)\b|\bthi sao\b|\bgia su\b"
)
_AFFORD = ("co on khong", "du tien", "kiem tra", "tra duoc khong", "co nen chi", "quet")
_CREDIT = ("tra sau", "bnpl", "mua truoc tra sau")
_MOVE_VERB = ("chuyen", "dieu chuyen", "rut tu", "doi tien")
_RESILIENCE = ("diem chong chiu",)
_ROADMAP = ("lo trinh",)
_ROADMAP_OUT_OF_SCOPE = ("dau tu", "lo trinh vay", "tu van vay", "nen vay", "vay tien")
_AMOUNT_TOKEN = re.compile(r"\d[\d.,]*\s*(?:k|nghin|ngan|trieu|tr|ty|ti|d|dong|vnd)?\b")
_INVEST = (  # ngoài phạm vi sản phẩm: không dựng kịch bản hay thẻ kiểm tra cho khoản đầu tư
    "co phieu",
    "chung khoan",
    "crypto",
    "bitcoin",
    "tien ma hoa",
    "tien so",
    "forex",
    "quy dau tu",
    "chung chi quy",
)
#: Từ kết thúc một cụm tên hũ hoặc tên món (lời nối, từ hỏi, từ chỉ thời gian, đại từ, chỗ trả tiền khác hũ)
_PHRASE_STOP = frozenset(
    {
        "cho",
        "de",
        "thi",
        "sao",
        "co",
        "nhe",
        "nha",
        "duoc",
        "khong",
        "ko",
        "gium",
        "giup",
        "vao",
        "sang",
        "den",
        "qua",
        "voi",
        "roi",
        "la",
        "ma",
        "nua",
        "bang",
        "mua",
        "tra",
        "va",
        "hay",
        "hoac",
        "neu",
        "se",
        "thoi",
        "luon",
        "tu",
        "trong",
        "hu",
        "thang",
        "tuan",
        "ngay",
        "mai",
        "nay",
        "sau",
        "truoc",
        "hom",
        "luc",
        "khi",
        "gio",
        "cua",
        "minh",
        "toi",
        "em",
    }
)
_JAR_AFTER_HU = re.compile(r"\bhu\s+(?P<rest>.+)$")
_JAR_AFTER_FROM = re.compile(r"\b(?:tu|trong)\s+(?P<rest>.+)$")
_PUNCT = ",.;:!?\"'()"
_FROM_TO = re.compile(r"\b(?:tu|rut tu)\s+(?P<src>.+?)\s+(?:sang|vao|den|qua)\s+(?P<dst>.+)$")
_TO_FROM = re.compile(r"\b(?:sang|vao|den|qua)\s+(?P<dst>.+?)\s+tu\s+(?P<src>.+)$")


def _has(norm: str, words: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", norm) for w in words)


def _clean_jar(fragment: str) -> str | None:
    return _AMOUNT_TOKEN.sub(" ", fragment).strip() or None


def _take_words(words: list[str], limit: int) -> list[str]:
    """Các từ đầu của `words` cho tới từ kết thúc cụm, số, hoặc đủ `limit` từ."""
    out: list[str] = []
    for w in words:
        if w in _PHRASE_STOP or w[:1].isdigit():
            break
        out.append(w)
        if len(out) == limit:
            break
    return out


def _jar_phrase(norm: str) -> str | None:
    """Chữ người dùng gõ chỉ hũ trả tiền ("hũ Giải trí", "từ Hóa đơn"), đã bỏ dấu; None nếu không có. Chưa ánh xạ ra mã hũ."""
    for pattern in (_JAR_AFTER_HU, _JAR_AFTER_FROM):
        for m in pattern.finditer(norm):
            if words := _take_words(m["rest"].split(), 4):
                return " ".join(words)
    return None


def _label_after(text: str, markers: tuple[str, ...]) -> str | None:
    """Tên món hoặc người nhận (giữ nguyên chữ gõ) ngay sau từ đánh dấu ("mua tai nghe 500k" -> "tai nghe"); None nếu không có."""
    tokens = text.split()
    norms = [normalize(t) for t in tokens]
    for i, n in enumerate(norms):
        if n not in markers:
            continue
        words: list[str] = []
        for tok, nn in zip(tokens[i + 1 :], norms[i + 1 :], strict=True):
            if not nn:
                continue
            if nn in _PHRASE_STOP or nn[0].isdigit():
                break
            words.append(tok.strip(_PUNCT))
            if len(words) == 5:
                break
        if words:
            return " ".join(words)[:80]
    return None


def _spend_params(
    text: str, norm: str, amount: int | None, credit: bool, markers: tuple[str, ...]
) -> dict[str, object]:
    """Tham số chung của what-if mua hàng và kiểm tra trước khi chi: số tiền, cách trả, hũ trả, tên món."""
    jar = _jar_phrase(norm)  # Trả sau vẫn có thể kèm hũ tính chi tiêu
    return {
        "amount_vnd": amount,
        "funding": "credit" if credit else ("jar" if jar else None),
        "jar_text": jar,
        "label": _label_after(text, markers),
    }


def _roadmap_goal(text: str, amount: int | None) -> dict[str, object] | None:
    """Mục tiêu lộ trình người dùng nói, trích như router: số tiền (amount_vnd), tên hũ (jar_text), cụm chỉ hạn giữ nguyên chữ gõ
    (date_text, đọc bằng `textutil.goal_date_phrase`; handler đổi ra ngày theo ngày mô phỏng). Thiếu một trong ba thì None (không đoán).

    Tên hũ tìm trong câu đã bỏ cụm chỉ hạn, để "hũ Du lịch cuối tháng" không thành hũ "du lich cuoi".
    """
    if amount is None or (date_text := goal_date_phrase(text)) is None:
        return None
    jar = _jar_phrase(normalize(text.replace(date_text, " ", 1)))
    if jar is None:
        return None
    return {"roadmap_action": "create", "amount_vnd": amount, "jar_text": jar, "date_text": date_text}


def _result(intent: str, **params: object) -> IntentResult:
    return IntentResult(
        intent=intent,  # type: ignore[arg-type]
        params=IntentParams(**params),  # type: ignore[arg-type]
        confidence=0.3,  # luật dự phòng: không bao giờ tự tin như model
        needs_clarification=False,
    )


def classify_by_rules(text: str) -> IntentResult | None:
    """Ý định bằng luật khi model không dùng được. Câu không khớp luật nào trả `None`."""
    norm = normalize(text)
    if not norm:
        return None
    if (shock_id := match_shock_id(text)) is not None:
        return _result("stress", shock_id=shock_id)
    amount = parse_amount_vnd(text)
    credit = _has(norm, _CREDIT)
    invest = _has(norm, _INVEST)
    moves = _has(norm, _MOVE_VERB)
    roadmap = _has(norm, _ROADMAP)
    if roadmap and (invest or _has(norm, _ROADMAP_OUT_OF_SCOPE)):
        return _result("out_of_scope")
    # lộ trình có mục tiêu ("gom đủ 1 tỷ trong hũ Du lịch trước cuối tháng này"): xét trước kiểm tra chi tiêu, vì "đủ tiền" cũng khớp luật đó
    if roadmap and not _WHAT_IF.search(norm) and (goal := _roadmap_goal(text, amount)) is not None:
        return _result("roadmap", **goal)
    if _WHAT_IF.search(norm) and not invest:
        if moves and amount is not None and (m := _FROM_TO.search(norm) or _TO_FROM.search(norm)):
            src, dst = (" ".join(_take_words(m[k].split(), 4)) or None for k in ("src", "dst"))
            return _result(
                "what_if",
                scenario_kind="jar_transfer",
                amount_vnd=amount,
                from_jar_text=src,
                to_jar_text=dst,
            )
        p = _spend_params(text, norm, amount, credit, ("mua",))
        kind = "bnpl_purchase" if credit else ("one_time_purchase" if p["jar_text"] else None)
        return _result("what_if", scenario_kind=kind, **p)
    if moves:
        m = _FROM_TO.search(norm) or _TO_FROM.search(norm)
        if m:
            return _result(
                "move",
                from_jar_text=_clean_jar(m["src"]),
                to_jar_text=_clean_jar(m["dst"]),
                amount_vnd=amount,
            )
        if invest:
            return None  # chuyển tiền để đầu tư: ngoài phạm vi, không đoán
        if (
            amount is not None
        ):  # "chuyển 250k cho bạn": không phải chuyển giữa hũ, là kiểm tra trước khi chi
            return _result(
                "affordability", **_spend_params(text, norm, amount, credit, ("mua", "cho"))
            )
        return _result("move")
    if _has(norm, _AFFORD) and amount is not None and not invest:
        return _result("affordability", **_spend_params(text, norm, amount, credit, ("mua", "cho")))
    if _has(norm, _RESILIENCE):
        return _result("resilience")
    if roadmap:
        return _result("roadmap", roadmap_action="view")
    if _has(norm, _FORECAST) or _FORECAST_WHEN.search(norm):
        return _result("lookup", lookup_kind="forecast")
    if _has(norm, _TRANSACTIONS):
        return _result("lookup", lookup_kind="transactions")
    if _has(norm, _OBLIGATIONS):
        return _result("lookup", lookup_kind="obligations")
    if _has(norm, _BALANCE):
        return _result("lookup", lookup_kind="balance")
    return None
