"""Dựng bảng markdown và ghi `calibration/default.py` từ kết quả backtest."""

from __future__ import annotations

import pprint
from pathlib import Path
from typing import Any

from yofina_ml.backtest.common import CUM_HORIZONS

FAMILY_LABEL = {
    "hurdle_lognormal": "(i) hurdle-lognormal",
    "shopping_sessions": "(ii) phiên mua + giỏ hàng",
    "all": "gộp hai họ",
}
BUCKET_LABEL = {
    "dense": "hũ dày",
    "sparse": "hũ thưa",
    "spending": "mọi hũ chi tiêu",
    "obligation": "hũ nghĩa vụ",
}


def n2(x: float | None, digits: int = 2) -> str:
    return "-" if x is None else f"{x:.{digits}f}".replace(".", ",")


def table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def render_daily(summary: dict[str, Any]) -> str:
    rows = []
    for fam, blocks in summary["by_family"].items():
        for bucket in ("dense", "sparse", "spending"):
            c = blocks.get(bucket)
            if not c:
                continue
            a = c["all"]
            pre, post = c.get("pre_break"), c.get("post_break")
            rows.append(
                [
                    FAMILY_LABEL[fam],
                    BUCKET_LABEL[bucket],
                    str(c["n"]),
                    n2(a["rel_pl_hurdle_raw"]),
                    n2(a["rel_pl_product"]),
                    n2(pre["rel_pl_product"]) if pre else "-",
                    n2(post["rel_pl_product"]) if post else "-",
                    n2(a["cov_daily_sn"]),
                    n2(a["cov_daily_raw"]),
                    n2(a["cov_daily_product"]),
                ]
            )
    return table(
        [
            "Họ",
            "Nhóm",
            "n",
            "pinball hurdle thô / SN",
            "pinball sản phẩm (ACI) / SN",
            "trước gãy",
            "sau gãy",
            "phủ ngày SN",
            "phủ ngày hurdle thô",
            "phủ ngày sản phẩm",
        ],
        rows,
    )


def render_cum(summary: dict[str, Any]) -> str:
    rows = []
    for fam, blocks in summary["by_family"].items():
        for bucket in ("dense", "sparse", "obligation"):
            c = blocks.get(bucket)
            if not c:
                continue
            a = c["all"]
            rows.append(
                [FAMILY_LABEL[fam], BUCKET_LABEL[bucket], str(c["n"])]
                + [n2(a[f"cov_cum{h}"]) for h in CUM_HORIZONS]
                + [n2(a["width_cum30"]) if bucket != "obligation" else "-"]
            )
    return table(
        ["Họ", "Nhóm", "n"]
        + [f"phủ số dư {h} ngày" for h in CUM_HORIZONS]
        + ["rộng 30 ngày / chi TB"],
        rows,
    )


def render_calibration(cal: dict[str, Any]) -> str:
    rows = []
    for kind, v in cal["kinds"].items():
        rows.append(
            [
                kind,
                str(cal["units"][kind]),
                n2(v["rho"]),
                n2(v["level_sigma"]),
                " / ".join(n2(x) for x in v["cov_before_rho0"]),
                " / ".join(n2(x) for x in v["cov_before_rho0_3"]),
                " / ".join(n2(x) for x in v["cov_after"]),
            ]
        )
    return table(
        [
            "Loại chuỗi",
            "đơn vị (origin x hũ)",
            "rho",
            "level_sigma",
            "phủ 7/14/30 ngày: rho=0, sigma=0",
            "rho=0,3, sigma=0",
            "đã chọn",
        ],
        rows,
    )


def render_reliability(rel: dict[str, Any], title: str) -> str:
    if not rel:
        return f"{title}: không có dữ liệu."
    rows = [[t["bin"], str(t["n"]), n2(t["mean_p"], 3), n2(t["freq"], 3)] for t in rel["table"]]
    head = (
        f"{title}: n = {rel['n']}, Brier = {n2(rel['brier'], 3)} "
        f"(chỉ dùng tần suất chung: {n2(rel['brier_climatology'], 3)}), "
        f"xác suất dự báo TB = {n2(rel['mean_p'], 3)}, tần suất thật = {n2(rel['event_rate'], 3)}"
    )
    return head + "\n\n" + table(["khoảng p dự báo", "n", "p dự báo TB", "tần suất thật"], rows)


def render_short(short: dict[int, dict[str, dict[str, float]]]) -> str:
    models = ["hurdle_calendar", "seasonal_naive", "cold_start_rules"]
    rows = []
    for length in sorted(short):
        rows.append(
            [str(length)]
            + [
                f"{n2(short[length][m]['rel_pl'])} / {n2(short[length][m]['cov_daily'])}"
                for m in models
            ]
        )
    return table(
        ["L (ngày lịch sử)", "hurdle theo lịch", "seasonal naive", "luật khởi đầu lạnh"], rows
    )


def render_ablation(ab: dict[str, dict[str, float]]) -> str:
    fams = [
        f for f in ("hurdle_lognormal", "shopping_sessions", "all") if f in next(iter(ab.values()))
    ]
    rows = [[name] + [n2(v[f]) for f in fams] for name, v in ab.items()]
    return table(["Biến thể hurdle"] + [FAMILY_LABEL[f] for f in fams], rows)


def render_sf(sf: dict[str, dict[str, float]]) -> str:
    rows = [[name, n2(v["rel_pl"]), n2(v["cov_daily"])] for name, v in sf.items()]
    return table(["Mô hình", "pinball / seasonal naive (numpy)", "phủ ngày P10-P90"], rows)


def write_default_calibration(path: Path, payload: dict[str, Any]) -> None:
    head = (
        '"""Hiệu chỉnh mặc định do backtest sinh ra. KHÔNG SỬA TAY: chạy `uv run scripts/ml_backtest.py --write-calibration`.\n\n'
        "Số đo và phương pháp ở docs/research/backtest-phase-2.md.\n"
        '"""\n\n'
    )
    body = pprint.pformat(payload, sort_dicts=False, width=100)
    path.write_text(head + f"CALIBRATION = {body}\n", encoding="utf-8")
