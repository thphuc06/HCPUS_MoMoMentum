"""REST thật: một đề nghị (khối `confirm`) chỉ được thực hiện MỘT lần và server giữ trạng thái của nó.

Lỗi gốc đã gặp khi tự kiểm phase 1: tải lại trang thì khối `confirm` đã bấm hiện lại như chưa bấm, nút vẫn bấm
được và bấm lần nữa chuyển tiền lần hai; biên nhận mất. Sửa: `POST /confirmations` và `POST /actions` nhận
`conversation_id` + `confirm_block_id`; `GET /conversations/{id}` trả `resolutions` (pending, done kèm receipt,
expired); đề nghị đã thực hiện thì 409 ALREADY_APPLIED (migration 0004).
"""

from __future__ import annotations

import time
import uuid

import pytest

from yofina_core.blocks import parse_block
from yofina_core.confirm import params_hash

TOOL = "move_between_jars"
MOVE = {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100_000}

pytestmark = pytest.mark.usefixtures("fresh")


def balances(api, who):
    status, body = api(who, "GET", "/jars")
    assert status == 200, body
    return {j["code"]: j["balance_vnd"] for j in body["jars"]}


class Offer:
    """Một cuộc hội thoại có một khối `confirm` đã được agent lưu (đường Gateway: save_turn)."""

    def __init__(self, invoke, subs, who="minh", params=MOVE, expires_in=600):
        self.who = who
        self.params = params
        self.conv = f"it-resolutions-{uuid.uuid4()}"
        self.trace = uuid.uuid4().hex
        preview = invoke(TOOL, {"user_id": subs[who], **params})
        assert preview["status"] == "NEEDS_CONFIRMATION", preview
        data = dict(preview["data"])
        if expires_in is not None:  # đề nghị đã hết hạn: dựng lại khối với hạn trong quá khứ
            data["expires_at"] = _iso(time.time() + expires_in)
        self.block = {
            "v": 1,
            "id": f"confirm:{self.trace}:{data['params_hash'][:12]}",
            "type": "confirm",
            "trace_id": self.trace,
            "fallback_text": "Chuyển 100.000 ₫ từ Giải trí sang Ăn uống. Cần bạn xác nhận trên ứng dụng.",
            "source": {
                "tool": "ledger___move_between_jars",
                "as_of": preview["as_of"],
                "app_date": preview["app_date"],
            },
            "data": data,
        }
        assert parse_block(self.block).type == "confirm"
        saved = invoke(
            "save_turn",
            {
                "user_id": subs[who],
                "conversation_id": self.conv,
                "trace_id": self.trace,
                "user_text": "chuyển 100 nghìn từ Giải trí sang Ăn uống",
                "assistant_text": "Chưa có khoản tiền nào được chuyển. Bạn bấm Xác nhận trên thẻ.",
                "blocks": [{"seq": 0, "block": self.block}],
            },
        )
        assert saved["status"] == "OK", saved

    @property
    def ref(self):
        return {"conversation_id": self.conv, "confirm_block_id": self.block["id"]}

    def confirmation(self, api, who=None, **extra):
        return api(
            who or self.who,
            "POST",
            "/confirmations",
            {"tool": TOOL, "params": self.params, **extra},
        )

    def act(self, api, token, who=None, **extra):
        body = {"tool": TOOL, "params": self.params, **extra}
        if token is not None:
            body["confirm_token"] = token
        return api(who or self.who, "POST", "/actions", body)

    def resolution(self, api, who=None):
        status, body = api(who or self.who, "GET", f"/conversations/{self.conv}")
        assert status == 200, body
        (turn,) = body["turns"]
        assert turn["blocks"] == [self.block]  # khối confirm vẫn nguyên văn
        (res,) = turn["resolutions"]
        assert res["block_id"] == self.block["id"]
        return res, body


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def code(body):
    return body["error"]["code"]


def test_xac_nhan_kem_de_nghi_thi_doc_lai_thay_done_va_receipt(api, invoke, subs, schema_validator):
    offer = Offer(invoke, subs)
    res, body = offer.resolution(api)
    schema_validator.openapi("ConversationResponse", body)
    assert res == {"block_id": offer.block["id"], "status": "pending"}

    before = balances(api, "minh")
    status, conf = offer.confirmation(api, **offer.ref)
    assert status == 200, conf
    status, receipt = offer.act(api, conf["confirm_token"], **offer.ref)
    assert status == 200, receipt
    assert parse_block(receipt).type == "receipt"
    after = balances(api, "minh")
    assert after["giai_tri"] == before["giai_tri"] - 100_000

    res, body = offer.resolution(api)  # như tải lại trang
    schema_validator.openapi("ConversationResponse", body)
    assert res["status"] == "done"
    assert (
        res["receipt"] == receipt
    )  # đúng khối POST /actions đã trả, lưu cùng transaction với sổ cái
    assert res["resolved_at"].endswith("Z")


def test_thuc_hien_lan_hai_voi_token_moi_hop_le_bi_already_applied_va_khong_ghi(api, invoke, subs):
    offer = Offer(invoke, subs)
    _, conf = offer.confirmation(api, **offer.ref)
    assert offer.act(api, conf["confirm_token"], **offer.ref)[0] == 200
    after_first = balances(api, "minh")

    # token mới, hợp lệ, lấy bằng REST trực tiếp (không kèm đề nghị) rồi dùng với đề nghị cũ
    status, fresh_conf = offer.confirmation(api)
    assert status == 200, fresh_conf
    status, body = offer.act(api, fresh_conf["confirm_token"], **offer.ref)
    assert (status, code(body)) == (409, "ALREADY_APPLIED")
    assert balances(api, "minh") == after_first  # số dư không đổi lần hai

    # cấp token mới cho chính đề nghị đó cũng bị từ chối, không có token trong thân trả lời
    status, body = offer.confirmation(api, **offer.ref)
    assert (status, code(body)) == (409, "ALREADY_APPLIED")
    assert "confirm_token" not in body
    assert balances(api, "minh") == after_first

    # token chưa bị tiêu: vẫn dùng được cho thao tác không kèm đề nghị (hành vi cũ giữ nguyên)
    assert offer.act(api, fresh_conf["confirm_token"])[0] == 200
    assert balances(api, "minh")["giai_tri"] == after_first["giai_tri"] - 100_000


def test_hai_yeu_cau_song_song_cung_de_nghi_chi_mot_ghi(api, invoke, subs):
    import threading

    offer = Offer(invoke, subs)
    tokens = [offer.confirmation(api, **offer.ref)[1]["confirm_token"] for _ in range(2)]
    before = balances(api, "minh")
    results: list[tuple[int, dict]] = []

    def go(tok):
        results.append(offer.act(api, tok, **offer.ref))

    threads = [threading.Thread(target=go, args=(t,)) for t in tokens]
    for t in threads:
        t.start()
    for t in threads:
        t.join(90)
    statuses = sorted(s for s, _ in results)
    assert statuses == [200, 409], results
    loser = next(b for s, b in results if s == 409)
    assert code(loser) == "ALREADY_APPLIED"
    assert balances(api, "minh")["giai_tri"] == before["giai_tri"] - 100_000  # đúng một lần


def test_nguoi_khac_khong_dung_duoc_confirm_block_id_cua_minh(api, invoke, subs):
    # số tiền nhỏ: hũ Giải trí của lan chỉ có 190.000 ₫ nên phải đủ cho hai lần cấp token
    small = {**MOVE, "amount_vnd": 40_000}
    offer = Offer(invoke, subs, "minh", params=small)
    before_minh = balances(api, "minh")
    # lan cầm confirm_block_id của minh: thao tác chỉ chạy trên dữ liệu của lan và không đánh dấu đề nghị của minh
    status, conf = offer.confirmation(api, "lan", **offer.ref)
    assert status == 200, conf
    before_lan = balances(api, "lan")
    status, receipt = offer.act(api, conf["confirm_token"], "lan", **offer.ref)
    assert status == 200, receipt
    assert balances(api, "minh") == before_minh
    assert balances(api, "lan")["giai_tri"] == before_lan["giai_tri"] - 40_000
    assert offer.resolution(api, "minh")[0]["status"] == "pending"
    status, body = api("lan", "GET", f"/conversations/{offer.conv}")
    assert status == 200 and body["turns"] == []  # lan không thấy hội thoại của minh

    # token của người khác vẫn bị từ chối dù đề nghị đúng
    status, conf_lan = offer.confirmation(api, "lan")
    assert status == 200, conf_lan
    status, body = offer.act(api, conf_lan["confirm_token"], "minh", **offer.ref)
    assert (status, code(body)) == (403, "TOKEN_INVALID")
    assert balances(api, "minh") == before_minh

    # minh vẫn thực hiện được đề nghị của chính mình
    _, conf_minh = offer.confirmation(api, **offer.ref)
    assert offer.act(api, conf_minh["confirm_token"], **offer.ref)[0] == 200
    assert offer.resolution(api, "minh")[0]["status"] == "done"


def test_id_khoi_khong_khop_tham_so_hoac_sai_dinh_dang_bi_tu_choi(api, invoke, subs):
    offer = Offer(invoke, subs)
    other = {**MOVE, "amount_vnd": 5_000}
    assert params_hash(TOOL, other)[:12] != params_hash(TOOL, MOVE)[:12]
    before = balances(api, "minh")
    _, conf = api("minh", "POST", "/confirmations", {"tool": TOOL, "params": other})
    status, body = api(
        "minh",
        "POST",
        "/actions",
        {"tool": TOOL, "params": other, "confirm_token": conf["confirm_token"], **offer.ref},
    )
    assert (status, code(body)) == (
        409,
        "PARAMS_MISMATCH",
    )  # khối là đề nghị 100.000, tham số là 5.000
    for bad in (
        {"conversation_id": offer.conv},  # thiếu một trong hai
        {"confirm_block_id": offer.block["id"]},
        {"conversation_id": offer.conv, "confirm_block_id": "khong-phai-id-khoi"},
    ):
        status, body = offer.confirmation(api, **bad)
        assert (status, code(body)) == (400, "PARAMS_INVALID"), bad
    assert balances(api, "minh") == before


def test_het_han_thi_expired_va_khong_gui_de_nghi_thi_hanh_vi_cu(api, invoke, subs):
    offer = Offer(invoke, subs, expires_in=-60)
    assert offer.resolution(api)[0] == {"block_id": offer.block["id"], "status": "expired"}
    # không gửi conversation_id/confirm_block_id: chuyển hai lần được như trước (REST trực tiếp)
    before = balances(api, "minh")
    for _ in range(2):
        _, conf = offer.confirmation(api)
        assert offer.act(api, conf["confirm_token"])[0] == 200
    assert balances(api, "minh")["giai_tri"] == before["giai_tri"] - 200_000
    # và việc đó không làm đổi trạng thái của đề nghị
    assert offer.resolution(api)[0]["status"] == "expired"


def test_dat_lai_demo_xoa_trang_thai_de_nghi(api, invoke, subs):
    offer = Offer(invoke, subs)
    _, conf = offer.confirmation(api, **offer.ref)
    assert offer.act(api, conf["confirm_token"], **offer.ref)[0] == 200
    assert api("minh", "POST", "/demo/reset", timeout=60)[0] == 200
    status, body = api("minh", "GET", f"/conversations/{offer.conv}")
    assert status == 200 and body["turns"] == []
    # cùng id đề nghị dùng lại được sau khi đặt lại (bảng đã được dọn)
    status, conf = offer.confirmation(api, **offer.ref)
    assert status == 200, conf
