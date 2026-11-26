"""Bộ eval trên ví demo 8 hũ (issue #34, #39): tên và mã hũ suy từ bộ sinh, ca không hỏi hũ đã bỏ, bộ chấm cho hành vi mới (hỏi hũ khi
lập lộ trình, đích ở hũ Dự phòng, khoản đến hạn trước lương ở hũ Nghĩa vụ, hũ nào sắp cạn, hũ của dòng nạp, thông báo thay bản đề xuất)
và chế độ liệt kê ca. Không gọi Runtime, REST hay model."""

from __future__ import annotations

import json
import re
import sys

import pytest
from test_evals import ROOT, evals_run, run_with, sse

SUITES = ("golden", "adversarial")


def _run(text: str = "", blocks=(), tools=(), account: str | None = None) -> dict:
    run = evals_run.collect(sse(text, blocks=blocks, tools=tools))
    if account is not None:
        run["account"] = account
    return run


def all_cases() -> list[tuple[str, dict]]:
    paths = sorted(p for d in SUITES for p in (ROOT / "evals" / d).glob("phase*.jsonl"))
    return [(f"{p.parent.name}/{p.stem}", c) for p in paths for c in evals_run.load(p)]


def by_id(case_id: str) -> dict:
    return next(c for _, c in all_cases() if c["id"] == case_id)


def case_texts(case: dict) -> list[str]:
    texts = [case["question"], *(h["content"] for h in case.get("history") or [])]
    texts += [m["content"] for s in case.get("prior_sessions") or [] for m in s]
    return texts + [it["text"] for it in case.get("seed_memory") or []]


# --- ví demo suy từ bộ sinh --------------------------------------------------------------------------
def test_vi_demo_cua_tai_khoan_eval_suy_tu_bo_sinh():
    jars = evals_run.demo_wallet_jars("minh")
    assert [j["code"] for j in jars] == [
        "chi_hang_ngay", "nghia_vu", "du_phong", "an_uong", "di_lai", "giai_tri", "muc_tieu", "dau_tu",
    ]  # fmt: skip
    by = {j["code"]: j for j in jars}
    assert (by["muc_tieu"]["name"], by["muc_tieu"]["purpose"]) == (
        "Du lịch",
        "goal",
    )  # tên của hũ nguồn, không phải "Mục tiêu"
    assert by["du_phong"]["purpose"] == "buffer" and by["dau_tu"]["purpose"] == "long_term"
    assert by["nghia_vu"]["kind"] == "obligation" and by["chi_hang_ngay"]["kind"] == "spending"
    assert not {"hoa_don", "du_lich"} & by.keys()
    assert evals_run.demo_wallet_jars("giamkhao1") == jars  # giám khảo là persona minh
    assert "muc_tieu" not in {
        j["code"] for j in evals_run.demo_wallet_jars("lan")
    }  # lan không có hũ mục tiêu
    assert evals_run.demo_wallet_jars("khong-co") == []


def test_ten_hu_tren_vi_demo_khong_doc_ma_nhu_chu():
    assert evals_run.jar_phrases("muc_tieu") == {"Du lịch"}
    assert evals_run.jar_phrases("giai_tri") == {"Giải trí"}
    assert evals_run.jar_phrases("du_lich") == {
        "du lich"
    }  # mã không có trên ví demo: đọc mã như chữ như trước
    assert evals_run.answer_mentions_jar(_run("Phần dư nên để vào hũ Du lịch."), "muc_tieu")
    # "mục tiêu" là chữ thường gặp: mã `muc_tieu` không được khớp nó
    assert not evals_run.answer_mentions_jar(
        _run("Để dành cho mục tiêu dài hạn ở hũ Dự phòng."), "muc_tieu"
    )
    act = run_with({"type": "confirm_action", "data": {"params": {"to_jar": "muc_tieu"}}})
    assert evals_run.answer_mentions_jar(act, "muc_tieu")
    # tên hũ đọc từ kết quả tool của lượt cũng tính (tài khoản đổi tên hũ)
    renamed = _run(
        "Để vào hũ Đi Đà Lạt nhé.",
        tools=[
            ("ledger___get_jar_balances", {}, {"jars": [{"code": "muc_tieu", "name": "Đi Đà Lạt"}]})
        ],
    )
    assert evals_run.answer_mentions_jar(renamed, "muc_tieu")


def test_ban_ghi_bo_nho_nhac_hu_theo_ten_tren_vi_demo():
    pref = {"kind": "preference", "text": "Tháng này ưu tiên để dành cho hũ Du lịch"}
    vague = {"kind": "preference", "text": "Ưu tiên một mục tiêu tiết kiệm"}
    assert evals_run.expected_preference_seen({"records": [pref]}, ["muc_tieu"])
    assert not evals_run.expected_preference_seen({"records": [vague]}, ["muc_tieu"])
    assert evals_run.expected_records_seen(
        {"records": [pref]}, [{"kind": "preference", "jar": "muc_tieu"}]
    )
    assert not evals_run.expected_records_seen(
        {"records": [vague]}, [{"kind": "preference", "jar": "muc_tieu"}]
    )


def test_ca_khong_hoi_hu_da_bo_va_ma_hu_cua_ca_co_tren_vi_demo():
    codes = {j["code"] for j in evals_run.demo_wallet_jars("minh")}
    for name, c in all_cases():
        for t in case_texts(c):
            assert " hu hoa don " not in f" {evals_run._fold(t)} ", (
                name,
                c["id"],
            )  # hũ Hóa đơn đã gộp vào Nghĩa vụ
        refs = set(c.get("expect_memory_used", [])) | set(c.get("forbid_option_source_jars", []))
        refs |= {e["jar"] for e in c.get("expect_memory_records", []) if e.get("jar")}
        refs |= set(c.get("forbid_runout_jars", [])) | {
            e["jar"] for e in c.get("expect_ingest_jars", [])
        }
        assert refs <= codes, (name, c["id"], refs - codes)


def test_ca_doi_khang_hoi_lo_trinh_nguoi_khac_khong_hoi_chinh_tai_khoan_chay_eval():
    """Bẫy `leak-1`: hỏi về chính `minh` khi chạy bằng `minh` (hay giám khảo, cũng là persona `minh`) thì bộ chấm không bắt được gì."""
    case = by_id("roadmap-other-user")
    assert evals_run.other_users("minh") & set(evals_run._fold(case["question"]).split())
    assert not re.search(
        r"(?<!\w)minh(?!\w)", case["question"].lower()
    )  # "mình" là người hỏi, không phải tài khoản minh


# --- ca mới -------------------------------------------------------------------------------------------
NEW_CASES = {
    "lookup-runout-overview": "forbid_runout_jars",
    "whatif-bnpl-due-before-payday": "expect_obligation_window",
    "roadmap-goal-ask-jar": "expect_clarify_slot",
    "roadmap-buffer-goal": "expect_roadmap_goal",
    "ingest-food-jar": "expect_ingest_jars",
}


@pytest.mark.parametrize(("case_id", "key"), sorted(NEW_CASES.items()))
def test_ca_moi_cho_hanh_vi_moi_co_bo_cham_va_ghi_so_luot_chat(case_id, key):
    c = by_id(case_id)
    assert key in c and set(c) <= evals_run.CASE_KEYS, case_id
    assert "lượt chat" in c["note"], case_id
    assert evals_run.case_plan(c)["turns"] == 1, case_id


def test_ca_lap_lai_lo_trinh_cham_thong_bao_thay_ban_theo_ban_dang_cho():
    c = by_id("roadmap-regenerate-after-spending-change")
    assert c.get("expect_replaced_notice") is True and "notice" not in c["blocks_must"]


# --- bộ chấm: hỏi lại hũ ------------------------------------------------------------------------------
JARS_TOOL = (
    "ledger___get_jar_balances",
    {},
    {"jars": [
        {"code": "du_phong", "name": "Dự phòng", "kind": "saving", "purpose": "buffer"},
        {"code": "muc_tieu", "name": "Du lịch", "kind": "saving", "purpose": "goal"},
        {"code": "an_uong", "name": "Ăn uống", "kind": "spending"},
    ]},
)  # fmt: skip


def clarify(slot: str, *labels: str) -> dict:
    chips = [{"id": f"c{i}", "label": x, "value": f"Hũ {x}"} for i, x in enumerate(labels)]
    return {
        "type": "clarify",
        "id": "clarify:t",
        "data": {"question": "Mục tiêu này thuộc hũ nào?", "slot": slot, "chips": chips},
    }


def test_hoi_lai_hu_dat_khi_dung_o_va_chip_la_hu_that():
    case = {"id": "x", "question": "q", "expect_clarify_slot": "jar"}
    ok = _run(blocks=[clarify("jar", "Dự phòng", "Du lịch")], tools=[JARS_TOOL])
    assert evals_run.clarify_slot(ok, case) == {
        "ok": True,
        "fails": [],
        "slot": "jar",
        "chips": ["Dự phòng", "Du lịch"],
    }
    # chip theo tên hũ của ví demo (bộ sinh) cũng nhận khi lượt không có kết quả đọc hũ
    assert evals_run.clarify_slot(_run(blocks=[clarify("jar", "Dự phòng")]), case)["ok"]
    assert evals_run.clarify_slot(_run(blocks=[clarify("amount")], tools=[JARS_TOOL]), case)[
        "fails"
    ] == ["sai_thong_tin_hoi", "khong_co_chip_hu"]
    assert evals_run.clarify_slot(
        _run(blocks=[clarify("jar", "Hóa đơn")], tools=[JARS_TOOL]), case
    )["fails"] == ["chip_khong_phai_hu"]
    assert evals_run.clarify_slot(_run(tools=[JARS_TOOL]), case)["fails"] == ["thieu_khoi_clarify"]
    s = evals_run.score(ok, case, "golden")
    assert (
        s["clarify_slot"]["ok"]
        and evals_run.summarize([{"case": case, "score": s}], "golden")["clarify_slot"] == "1/1"
    )


# --- bộ chấm: mục tiêu lộ trình ở hũ Dự phòng --------------------------------------------------------
def roadmap(*goals: dict) -> dict:
    return {
        "type": "roadmap",
        "id": "roadmap:t:v3",
        "data": {"version": 3, "status": "proposed", "goals": list(goals), "phases": []},
    }


def goal(
    code: str, target: int, *, purpose: str | None = None, target_date: str | None = "2027-04-30"
) -> dict:
    jar = {"code": code, "name": code, "color_key": "blue", "icon_key": "shield"} | (
        {"purpose": purpose} if purpose else {}
    )
    return {
        "jar": jar,
        "target_vnd": target,
        "target_date": target_date,
        "on_track": True,
        "shortfall_vnd": 0,
        "monthly_needed_vnd": 1,
    }


def test_muc_tieu_lo_trinh_o_hu_du_phong():
    case = {
        "id": "x",
        "question": "q",
        "expect_roadmap_goal": {"purpose": "buffer", "target_vnd": 6_000_000},
    }
    assert evals_run.roadmap_goal(
        _run(blocks=[roadmap(goal("du_phong", 6_000_000, purpose="buffer"))]), case
    )["ok"]
    # khối không mang purpose: nhận hũ theo mã có mục đích đó trên ví (kết quả tool, ví demo)
    assert evals_run.roadmap_goal(_run(blocks=[roadmap(goal("du_phong", 6_000_000))]), case)["ok"]
    moved = _run(blocks=[roadmap(goal("muc_tieu", 6_000_000, purpose="goal"))], tools=[JARS_TOOL])
    assert evals_run.roadmap_goal(moved, case)["fails"] == [
        "khong_co_muc_tieu_o_hu"
    ]  # đẩy mục tiêu sang hũ khác
    wrong = _run(blocks=[roadmap(goal("du_phong", 3_000_000, purpose="buffer"))])
    assert evals_run.roadmap_goal(wrong, case)["fails"] == ["sai_so_tien_muc_tieu"]
    no_date = _run(
        blocks=[roadmap(goal("du_phong", 6_000_000, purpose="buffer", target_date=None))]
    )
    assert evals_run.roadmap_goal(no_date, case)["fails"] == ["thieu_han_muc_tieu"]
    assert evals_run.roadmap_goal(_run(), case)["fails"] == ["thieu_khoi_roadmap"]
    assert "roadmap_goal" in evals_run.score(_run(), case, "golden")


# --- bộ chấm: khoản đến hạn trước lương ở hũ Nghĩa vụ (what-if Trả sau) ---------------------------------
def due(d: str, label: str, amount: int, kind: str = "obligation") -> dict:
    return {"date": d, "kind": kind, "label": label, "amount_vnd": amount}


def whatif_blocks(
    items: list[dict],
    *,
    due_date: str = "2026-12-05",
    total: int = 1_900_000,
    jar: str = "nghia_vu",
) -> list[dict]:
    timeline = {
        "type": "forecast_timeline",
        "id": f"forecast_timeline:t:{jar}:what_if",
        "data": {
            "jar": {"code": jar, "name": "Nghĩa vụ"},
            "payday": {"date": "2026-12-05", "days_until": 14},
            "compare": {
                "after": {"status": "short", "obligations_before_payday": {"items": items}}
            },
        },
    }
    impact = {
        "type": "obligation_impact",
        "id": "obligation_impact:t:x",
        "data": {
            "cost": {"due_date": due_date, "total_due_vnd": total},
            "at_due": [{"jar": {"code": "nghia_vu"}}],
        },
    }
    return [timeline, impact]


def test_what_if_tra_sau_liet_ke_khoan_den_han_truoc_luong_o_hu_nghia_vu():
    """Cửa sổ "trước lương" của bộ chấm là quy tắc chung `yofina_core.schedule.due_before_payday` (chốt 26/11, BR-22, phương án B):
    khoản đến hạn ĐÚNG ngày lương (Trả sau 05/12 của ví demo, lương 05/12) phải có trong danh sách; trước đó bộ chấm đòi `< payday`
    nên khoản này bị coi là "từ ngày lương" và không được có."""
    case = {"id": "x", "question": "q", "expect_obligation_window": True}
    good = [due("2026-11-26", "Tiền điện", 375_000), due("2026-12-05", "Trả sau", 1_900_000)]
    res = evals_run.obligation_window(_run(blocks=whatif_blocks(good)), case)
    assert res["ok"] and res["items"] == [["2026-11-26", 375_000], ["2026-12-05", 1_900_000]], res
    missing_bnpl = evals_run.obligation_window(_run(blocks=whatif_blocks(good[:1])), case)
    assert missing_bnpl["fails"] == ["thieu_khoan_tra_sau"]
    late = [*good, due("2026-12-06", "Tiền nhà", 2_000_000)]
    assert evals_run.obligation_window(_run(blocks=whatif_blocks(late)), case)["fails"] == [
        "khoan_sau_ngay_luong"
    ]
    unsorted = list(reversed(good))
    assert evals_run.obligation_window(_run(blocks=whatif_blocks(unsorted)), case)["fails"] == [
        "khong_theo_ngay"
    ]
    # khoản Trả sau đến hạn trước ngày lương cũng phải có
    early = [good[0], due("2026-12-03", "Trả sau", 1_900_000)]
    assert evals_run.obligation_window(_run(blocks=whatif_blocks(early, due_date="2026-12-03")), case)["ok"]
    # khoản Trả sau đến hạn SAU ngày lương thì không được nằm trong danh sách trước lương
    after_payday = whatif_blocks([good[0]], due_date="2026-12-06")
    assert evals_run.obligation_window(_run(blocks=after_payday), case)["ok"]
    listed_late = whatif_blocks([good[0], due("2026-12-06", "Trả sau", 1_900_000)], due_date="2026-12-06")
    assert evals_run.obligation_window(_run(blocks=listed_late), case)["fails"] == ["khoan_sau_ngay_luong"]
    other_jar = whatif_blocks(good, jar="an_uong")
    assert evals_run.obligation_window(_run(blocks=other_jar), case)["fails"] == ["sai_hu_tra"]
    assert evals_run.obligation_window(_run(blocks=whatif_blocks([])), case)["fails"] == [
        "danh_sach_rong"
    ]
    assert evals_run.obligation_window(_run(), case)["fails"] == ["thieu_danh_sach_den_han"]
    assert "obligation_window" in evals_run.score(_run(), case, "golden")


# --- bộ chấm: hũ nào sắp cạn ---------------------------------------------------------------------------
def forecast_tool(code: str, name: str, runout=None) -> tuple[str, dict, dict]:
    return (
        "forecast___get_forecast",
        {"jar": code},
        {"jar": name, "status": "đủ", "runout": runout},
    )


OVERVIEW_TOOLS = [
    forecast_tool(
        "an_uong", "Ăn uống", {"date_text": "23/11", "days_from_today": 2, "days_before_payday": 12}
    ),
    forecast_tool("chi_hang_ngay", "Chi hằng ngày"),
    forecast_tool("dau_tu", "Đầu tư"),
]


def test_hu_nao_sap_can_khong_neu_hu_khong_can():
    case = {"id": "x", "question": "q", "forbid_runout_jars": ["dau_tu", "chi_hang_ngay"]}
    text = "Hũ Ăn uống dự kiến cạn ngày 23/11, sớm 12 ngày so với kỳ lương 05/12. Các hũ còn lại đủ tới kỳ lương."
    assert evals_run.runout_claims(_run(text, tools=OVERVIEW_TOOLS), case)["ok"]
    # phủ định không phải lời nói cạn
    calm = text + " Hũ Đầu tư không có khoản chi nên không cạn."
    assert evals_run.runout_claims(_run(calm, tools=OVERVIEW_TOOLS), case)["ok"]
    said = evals_run.runout_claims(
        _run("Hũ Chi hằng ngày, Đầu tư có thể cạn trước ngày lương.", tools=OVERVIEW_TOOLS), case
    )
    assert said["fails"] == ["noi_sap_can:dau_tu", "noi_sap_can:chi_hang_ngay"]
    may = [
        *OVERVIEW_TOOLS[:2],
        forecast_tool("dau_tu", "Đầu tư", {"may_run_out_before_payday": True}),
    ]
    assert evals_run.runout_claims(_run(text, tools=may), case)["fails"] == [
        "du_bao_sap_can:dau_tu"
    ]
    skipped = evals_run.runout_claims(_run(text, tools=OVERVIEW_TOOLS[:2]), case)
    assert skipped["fails"] == [
        "khong_co_du_bao:dau_tu"
    ]  # không dự báo hũ đó thì không biết lượt nói đúng không
    chart = {
        "type": "forecast_timeline",
        "id": "f",
        "data": {"jar": {"code": "dau_tu"}, "status": "short", "runout_date": "2026-11-30"},
    }
    assert evals_run.runout_claims(_run(text, tools=OVERVIEW_TOOLS, blocks=[chart]), case)[
        "fails"
    ] == ["bieu_do_sap_can:dau_tu"]
    assert "runout_claims" in evals_run.score(_run(text, tools=OVERVIEW_TOOLS), case, "golden")


# --- bộ chấm: hũ đề xuất của dòng nạp -------------------------------------------------------------------
def test_dong_nap_an_uong_vao_hu_an_uong_tren_vi_demo():
    case = {
        "id": "x",
        "question": "q",
        "expect_ingest_jars": [{"amount_vnd": 45_000, "jar": "an_uong"}],
    }

    def with_rows(*rows: dict) -> dict:
        return {
            **run_with(),
            "upload": {"job": {"status": "review", "review": {"data": {"rows": list(rows)}}}},
        }

    row = {"row_id": "r1", "kind": "expense", "amount_vnd": 45_000, "review_status": "pending"}
    assert evals_run.ingest_jars(with_rows({**row, "suggested_jar": {"code": "an_uong"}}), case)[
        "ok"
    ]
    wrong = evals_run.ingest_jars(
        with_rows({**row, "suggested_jar": {"code": "chi_hang_ngay"}}), case
    )
    assert wrong["fails"] == ["sai_hu:45000"] and wrong["got"] == {"45000": ["chi_hang_ngay"]}
    assert evals_run.ingest_jars(with_rows(row), case)["fails"] == [
        "sai_hu:45000"
    ]  # chưa xếp được hũ
    assert evals_run.ingest_jars(with_rows(), case)["fails"] == ["khong_co_dong:45000"]
    assert "ingest_jars" in evals_run.score(with_rows(), case, "golden")


# --- bộ chấm: thông báo thay bản đề xuất đang chờ ------------------------------------------------------
def latest(status: str, version: int) -> tuple[str, dict, dict]:
    return ("planner___get_roadmap", {"which": "latest"}, {"version": version, "status": status})


def replaced(version: int) -> dict:
    msg = f"Bản này thay bản đề xuất phiên bản {version} (lý do: bạn yêu cầu) đang chờ bạn chọn."
    return {
        "type": "notice",
        "id": "n",
        "data": {"kind": "info", "title": "t", "message": msg, "code": "ROADMAP_PROPOSAL_REPLACED"},
    }


def test_thong_bao_thay_ban_khi_va_chi_khi_co_ban_de_xuat_dang_cho():
    case = {"id": "x", "question": "q", "expect_replaced_notice": True}
    assert evals_run.replaced_notice(
        _run(tools=[latest("proposed", 3)], blocks=[replaced(3)]), case
    )["ok"]
    assert evals_run.replaced_notice(_run(tools=[latest("proposed", 3)]), case)["fails"] == [
        "thieu_thong_bao_thay_ban"
    ]
    assert evals_run.replaced_notice(
        _run(tools=[latest("proposed", 3)], blocks=[replaced(2)]), case
    )["fails"] == ["thong_bao_sai_phien_ban"]
    # sau "Đặt lại dữ liệu" bản mới nhất là v2 đang dùng: không có gì để thay
    assert evals_run.replaced_notice(_run(tools=[latest("active", 2)]), case)["ok"]
    assert evals_run.replaced_notice(_run(tools=[latest("active", 2)], blocks=[replaced(2)]), case)[
        "fails"
    ] == ["thong_bao_thay_ban_khi_khong_co_ban_cho"]
    not_found = (
        "planner___get_roadmap",
        {"which": "latest"},
        {"status": "ERROR", "code": "ROADMAP_NOT_FOUND"},
    )
    assert evals_run.replaced_notice(_run(tools=[not_found]), case)["ok"]
    assert evals_run.replaced_notice(_run(), case)["fails"] == ["khong_doc_ban_moi_nhat"]


# --- liệt kê ca (không gọi gì) ---------------------------------------------------------------------------
def test_ke_hoach_ca_dem_luot_chat_lan_nap_va_lan_goi_judge():
    assert evals_run.case_plan({"id": "a", "question": "q", "history": [{"role": "user", "content": "x"}]}) == {
        "id": "a", "turns": 1, "uploads": 0, "judge_calls": 0,
    }  # fmt: skip
    mem = by_id("memory-knowledge-update")
    assert evals_run.case_plan(mem)["turns"] == 2  # một phiên trước, một câu chính
    assert evals_run.case_plan(by_id("ingest-coverage"))["uploads"] == 1
    assert evals_run.case_plan(by_id("memory-forget-no-invent"))["judge_calls"] == 1


def test_che_do_liet_ke_khong_goi_aws(monkeypatch, capsys):
    import _yofina  # scripts/ đã nằm trong sys.path khi nạp run.py

    def boom(*a, **k):
        raise AssertionError("chế độ liệt kê không được tạo phiên AWS")

    monkeypatch.setattr(_yofina, "session", boom)
    monkeypatch.setattr(sys, "argv", ["run.py", "golden", "--phase", "5", "--list"])
    assert evals_run.main() == 0
    out = capsys.readouterr().out
    lines = [json.loads(x) for x in out.splitlines() if x.startswith("{")]
    cases = evals_run.load(ROOT / "evals" / "golden" / "phase5.jsonl")
    assert [r["id"] for r in lines[:-1]] == [c["id"] for c in cases]
    total = lines[-1]
    assert total["cases"] == len(cases) and total["turns"] == sum(r["turns"] for r in lines[:-1])
