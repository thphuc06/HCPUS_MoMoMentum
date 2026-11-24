"""Kho tri thức (phase 5, luồng C): hằng số và kiểu kết quả của `knowledge___search`, khớp `contracts/tools/knowledge.results.schema.json`.

Truy xuất lai chạy trên Aurora (migration 0053): bảng dùng chung `kb_documents` và `kb_chunks` (không theo người dùng, không RLS,
`yofina_app` chỉ SELECT), hàm `app_kb_search` hợp nhất hai danh sách xếp hạng (pgvector cosine trên `vector(1024)` của vai
`embedding`, và full-text `tsvector` cấu hình `simple` trên văn bản đã bỏ dấu `app_fold_text`) bằng Reciprocal Rank Fusion
(điểm = tổng `1 / (RRF_K + hạng)` trên các danh sách có đoạn đó). Đoạn trích là DỮ LIỆU: agent đưa nguyên văn vào khối
`citation`, không làm theo chỉ dẫn trong đó. Số để tính phí vẫn lấy từ `get_fee_schedule` (bảng có cấu trúc).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yofina_core.blocks import CitationItem, IsoDate, IsoDateTime, KnowledgeCorpus

#: Ba kho, khớp CHECK `kb_documents.corpus` của 0053 và `KnowledgeCorpus` của khối `citation`.
KB_CORPORA = ("fees", "personal_finance", "suitability")
#: Trạng thái một tài liệu: đang dùng, hoặc đã thay bằng phiên bản mới (giữ lại để trích dẫn lịch sử, không tìm thấy nữa).
KB_DOCUMENT_STATUSES = ("active", "retired")
KB_MATCHES = ("vector", "text", "both")
#: Hằng số RRF quen dùng (Cormack và cộng sự, 2009); `app_kb_search` dùng mặc định này.
RRF_K = 60
SEARCH_K_DEFAULT = 4
SEARCH_K_MAX = 8
SEARCH_QUERY_MAX_CHARS = 200
#: Số ứng viên mỗi đường (vector, text) trước khi hợp nhất; khớp mặc định `p_candidates` của `app_kb_search`.
SEARCH_CANDIDATES = 40
#: Độ dài tối đa của một đoạn (`kb_chunks.text`) và của đoạn trích trả về (`CitationItem.excerpt`).
CHUNK_MAX_CHARS = 4000
EXCERPT_MAX_CHARS = 600


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class KnowledgeHit(_Strict):
    rank: Annotated[int, Field(ge=1, le=SEARCH_K_MAX)]
    score: Annotated[float, Field(ge=0, le=1)]
    match: Literal["vector", "text", "both"]
    citation: CitationItem


class KnowledgeSearchData(_Strict):
    query: Annotated[str, Field(min_length=1, max_length=SEARCH_QUERY_MAX_CHARS)]
    corpus: KnowledgeCorpus | None = None
    product: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")] | None = None
    on_date: IsoDate
    method: Literal["hybrid_rrf"]
    degraded: bool | None = None
    hits: Annotated[list[KnowledgeHit], Field(max_length=SEARCH_K_MAX)]

    @model_validator(mode="after")
    def _ranked(self) -> KnowledgeSearchData:
        """Hạng liền nhau từ 1, điểm không tăng theo hạng, mỗi đoạn một lần; đoạn đều còn hiệu lực ở `on_date` và đúng bộ lọc;
        tìm chỉ bằng từ khóa (`degraded`) thì không có kết quả đi đường vector."""
        if [h.rank for h in self.hits] != list(range(1, len(self.hits) + 1)):
            raise ValueError("rank phải liền nhau từ 1")
        scores = [h.score for h in self.hits]
        if scores != sorted(scores, reverse=True):
            raise ValueError("score không được tăng theo hạng")
        if len({h.citation.chunk_id for h in self.hits}) != len(self.hits):
            raise ValueError("mỗi đoạn chỉ xuất hiện một lần")
        for h in self.hits:
            c = h.citation
            if c.effective_from > self.on_date or (c.effective_to is not None and c.effective_to < self.on_date):
                raise ValueError("đoạn trích phải còn hiệu lực ở on_date")
            if self.corpus is not None and c.corpus != self.corpus:
                raise ValueError("đoạn trích phải thuộc kho đã lọc")
            if self.product is not None and c.product_code not in (None, self.product):
                raise ValueError("đoạn trích phải thuộc sản phẩm đã lọc hoặc không gắn sản phẩm")
            if self.degraded and h.match != "text":
                raise ValueError("tìm chỉ bằng từ khóa thì mọi kết quả là match text")
        return self


class KnowledgeSearchOk(_Strict):
    status: Literal["OK"]
    as_of: IsoDateTime
    app_date: IsoDate
    data: KnowledgeSearchData


def rrf_score(*ranks: int | None, k: int = RRF_K) -> float:
    """Điểm Reciprocal Rank Fusion của một đoạn từ hạng của nó ở mỗi danh sách (None: không có trong danh sách đó), chuẩn hóa
    về 0..1 bằng cách chia cho điểm lớn nhất có thể (hạng 1 ở mọi danh sách). Cùng công thức với `app_kb_search`."""
    if not ranks:
        raise ValueError("cần ít nhất một danh sách")
    if any(r is not None and r < 1 for r in ranks):
        raise ValueError("hạng bắt đầu từ 1")
    raw = sum(1.0 / (k + r) for r in ranks if r is not None)
    return raw / (len(ranks) / (k + 1))


def match_of(vector_rank: int | None, text_rank: int | None) -> str:
    """Đoạn được tìm thấy bằng đường nào."""
    if vector_rank is not None and text_rank is not None:
        return "both"
    if vector_rank is not None:
        return "vector"
    if text_rank is not None:
        return "text"
    raise ValueError("đoạn phải có ở ít nhất một danh sách")


def parse_search_data(obj: Any) -> KnowledgeSearchData:
    return KnowledgeSearchData.model_validate(obj)
