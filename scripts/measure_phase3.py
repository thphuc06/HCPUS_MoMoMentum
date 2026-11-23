# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3[crt]>=1.43,<2", "pycognito>=2024.5", "httpx>=0.27"]
# ///
"""Đo số liệu tiêu chí 9 của phase 3 TỪ MÁY NÀY (qua Internet tới Runtime và API Gateway), trên môi trường thật.

    uv run scripts/measure_phase3.py                      # 10 lượt mỗi loại, giãn 17 giây giữa các lượt gọi model
    uv run scripts/measure_phase3.py --turns 5 --pace 20 --who minh
    uv run scripts/measure_phase3.py --same-session       # what-if dùng lại MỘT phiên (không khởi động lạnh microVM)

Đo:
  1. what-if qua chat (Runtime `yofina_agent`): 1 lượt khởi động (lạnh, ghi riêng) rồi N lượt đo; thời điểm sự kiện đầu,
     khối đầu (`ACTIVITY_SNAPSHOT`), chữ đầu (`TEXT_MESSAGE_CONTENT`), tổng tới `RUN_FINISHED`; `model_calls` và `degraded`
     lấy từ `RUN_FINISHED.result`.
  2. kiểm tra trước khi quẹt qua chat ("Chuyển 250 nghìn ... có ổn không"): thời điểm khối `affordability_card` và tổng.
  3. `POST /affordability` REST, phiên ấm (1 lượt làm nóng không tính).
  4. `ApplyGuardrail` gọi thẳng bằng boto3 (nguồn INPUT, câu tiếng Việt bình thường): p50/p95 ms, so với ngưỡng 400 ms.
  5. `step_timings` của từng lượt chat (đọc `GET /traces/{trace_id}`): router, guardrail_in, orchestrator, tools, analyst,
     verifier, composer... p50/p95 mỗi bước. Đây là số phía trong Region; số từ máy này còn gồm độ trễ mạng.

Mặc định mỗi lượt chat dùng một session id riêng (đúng cách frontend mở cuộc chat mới); AgentCore cấp một microVM theo session,
nên lượt đầu của mỗi phiên có thể gồm cả khởi động lạnh microVM: so sánh `t_first_event` với `--same-session` để tách phần đó.
Kết quả thô lưu ở `evals/results/phase3-measure-<ngày>.json` (thư mục không vào git). Không in hay ghi mật khẩu/token. Mọi lượt
what-if ghi dữ liệu dẫn xuất (bảng scenarios); không chuyển tiền thật, không cần đặt lại tài khoản.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests" / "integration"))

from _demo_auth import api_url, call_api, demo_accounts, login_access_token  # noqa: E402
from _yofina import session, ssm_param  # noqa: E402
from agentcore_helpers import invoke_agent, new_session_id, runtime_url  # noqa: E402

WHATIF_QS = [
    "Nếu mua tai nghe 500 nghìn từ hũ Giải trí thì sao",
    "Nếu mua tai nghe 450 nghìn từ hũ Giải trí thì sao",
    "Nếu mua loa bluetooth 600 nghìn từ hũ Giải trí thì sao",
]
AFFORD_Q = "Chuyển 250 nghìn từ hũ Hóa đơn cho người nhận demo có ổn không"
GUARDRAIL_TEXTS = [
    "Nếu mua tai nghe 500 nghìn từ hũ Giải trí thì sao",
    "Hũ Ăn uống của tôi còn đủ dùng tới cuối tháng không",
    "Tháng này tôi tiêu nhiều nhất ở hũ nào",
    "Chuyển 250 nghìn từ hũ Hóa đơn cho người nhận demo có ổn không",
    "Cho tôi xem dự báo hũ Di chuyển trong hai tuần tới",
    "Nếu mua điện thoại 8 triệu bằng Ví Trả Sau thì sao",
    "Lương về ngày 5 thì tôi nên chia các hũ thế nào",
    "Tôi muốn tiết kiệm thêm 2 triệu mỗi tháng thì cần cắt hũ nào",
    "Khoản nợ nhỏ của tôi bao giờ đến hạn trả",
    "Hôm nay tôi đã chi bao nhiêu cho ăn uống",
]


def pct(xs: list[float], p: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, round(p / 100 * (len(s) - 1)))]


def stats_of(xs: list[float]) -> dict[str, float] | None:
    if not xs:
        return None
    return {
        "n": len(xs),
        "min": round(min(xs)),
        "p50": round(pct(xs, 50)),
        "p95": round(pct(xs, 95)),
        "max": round(max(xs)),
        "mean": round(statistics.mean(xs)),
    }


def line(name: str, st: dict[str, float] | None, unit: str = "ms") -> str:
    if st is None:
        return f"{name:42s} (không có mẫu)"
    return (
        f"{name:42s} n={st['n']:3d} min={st['min']:6.0f} p50={st['p50']:6.0f} "
        f"p95={st['p95']:6.0f} max={st['max']:6.0f} mean={st['mean']:6.0f} {unit}"
    )


class Tokens:
    """Access token Cognito; đăng nhập lại khi cũ hơn 40 phút (token sống 1 giờ)."""

    def __init__(self, who: str, sess) -> None:
        self.who, self.sess = who, sess
        self.accounts = demo_accounts(sess)
        self._tok, self._t = "", 0.0

    def get(self) -> str:
        if not self._tok or time.time() - self._t > 40 * 60:
            self._tok = login_access_token(self.who, sess=self.sess, accounts=self.accounts)
            self._t = time.time()
        return self._tok


def first_t(run, event_type: str, block_type: str | None = None) -> float | None:
    for e in run.events:
        if e.get("type") != event_type:
            continue
        if block_type is None or e.get("content", {}).get("type") == block_type:
            return e["_t"]
    return None


def fetch_trace(base: str, tokens: Tokens, trace_id: str) -> dict | None:
    for _ in range(4):
        status, body, _ms = call_api(base, "GET", f"/traces/{trace_id}", tokens.get(), timeout=30)
        if status == 200 and isinstance(body, dict):
            return body.get("detail")
        time.sleep(2)
    return None


def chat_turn(url: str, base: str, tokens: Tokens, text: str, *, sid: str | None, want: str | None):
    """Một lượt chat. `want`: loại khối cần tìm thời điểm (ngoài khối đầu bất kỳ)."""
    run = invoke_agent(url, tokens.get(), text, session_id=sid or new_session_id(), timeout=170)
    fin = run.finished or {}
    res = fin.get("result", {}) if isinstance(fin, dict) else {}
    rec = {
        "question": text,
        "http_status": run.status,
        "t_first_event_ms": None if run.t_first_event is None else round(run.t_first_event * 1000),
        "t_first_block_ms": _ms(first_t(run, "ACTIVITY_SNAPSHOT")),
        "t_first_text_ms": _ms(first_t(run, "TEXT_MESSAGE_CONTENT")),
        "t_want_block_ms": _ms(first_t(run, "ACTIVITY_SNAPSHOT", want)) if want else None,
        "total_ms": round(run.total * 1000),
        "block_timeline": [
            {"type": e["content"].get("type"), "t_ms": round(e["_t"] * 1000)}
            for e in run.events
            if e.get("type") == "ACTIVITY_SNAPSHOT"
        ],
        "finished": run.finished is not None,
        "intent": res.get("intent"),
        "degraded": res.get("degraded"),
        "model_calls": res.get("model_calls"),
        "tool_calls": res.get("tool_calls"),
        "verifier_rounds": res.get("verifier_rounds"),
        "trace_id": res.get("trace_id"),
    }
    if res.get("trace_id"):
        detail = fetch_trace(base, tokens, res["trace_id"])
        if detail:
            rec["server_duration_ms"] = detail.get("duration_ms")
            rec["step_timings"] = detail.get("step_timings")
            rec["token_usage"] = detail.get("token_usage")
    return rec


def _ms(sec: float | None) -> int | None:
    return None if sec is None else round(sec * 1000)


def summarize_chat(recs: list[dict], key_block: str | None) -> dict:
    ok = [r for r in recs if r["http_status"] == 200 and r["finished"]]
    out = {
        "n_total": len(recs),
        "n_ok": len(ok),
        "n_degraded": sum(1 for r in ok if r["degraded"]),
        "model_calls_max": max((r["model_calls"] or 0 for r in ok), default=None),
        "model_calls_all": [r["model_calls"] for r in ok],
        "first_event_ms": stats_of(
            [r["t_first_event_ms"] for r in ok if r["t_first_event_ms"] is not None]
        ),
        "first_block_ms": stats_of(
            [r["t_first_block_ms"] for r in ok if r["t_first_block_ms"] is not None]
        ),
        "first_text_ms": stats_of(
            [r["t_first_text_ms"] for r in ok if r["t_first_text_ms"] is not None]
        ),
        "total_ms": stats_of([r["total_ms"] for r in ok]),
        "server_duration_ms": stats_of(
            [r["server_duration_ms"] for r in ok if r.get("server_duration_ms")]
        ),
    }
    if key_block:
        out[f"{key_block}_ms"] = stats_of(
            [r["t_want_block_ms"] for r in ok if r["t_want_block_ms"] is not None]
        )
    steps: dict[str, list[float]] = {}
    for r in ok:
        for s in r.get("step_timings") or []:
            steps.setdefault(s["step"], []).append(float(s["ms"]))
    out["steps_ms"] = {k: stats_of(v) for k, v in steps.items()}
    return out


def print_chat(title: str, summ: dict, key_block: str | None) -> None:
    print(
        f"\n== {title} (ok {summ['n_ok']}/{summ['n_total']}, degraded {summ['n_degraded']}, "
        f"model_calls lớn nhất {summ['model_calls_max']}, từng lượt {summ['model_calls_all']})"
    )
    print(line("sự kiện đầu (RUN_STARTED)", summ["first_event_ms"]))
    print(line("khối đầu tiên", summ["first_block_ms"]))
    if key_block:
        print(line(f"khối {key_block}", summ[f"{key_block}_ms"]))
    print(line("chữ đầu tiên", summ["first_text_ms"]))
    print(line("tổng tới RUN_FINISHED", summ["total_ms"]))
    print(line("duration_ms phía server (trace)", summ["server_duration_ms"]))
    for name, st in summ["steps_ms"].items():
        print(line(f"  bước {name}", st))


def run_chat_series(label, url, base, tokens, questions, n, pace, *, want, same_session):
    shared_sid = new_session_id() if same_session else None
    print(f"\n[{label}] khởi động (lạnh, không tính)...", flush=True)
    cold = chat_turn(url, base, tokens, questions[0], sid=shared_sid, want=want)
    print(
        f"  lạnh: sự kiện đầu {cold['t_first_event_ms']} ms, khối đầu {cold['t_first_block_ms']} ms, "
        f"tổng {cold['total_ms']} ms, model_calls {cold['model_calls']}, degraded {cold['degraded']}",
        flush=True,
    )
    recs = []
    for i in range(n):
        time.sleep(pace)
        r = chat_turn(url, base, tokens, questions[i % len(questions)], sid=shared_sid, want=want)
        recs.append(r)
        print(
            f"  #{i + 1:2d}: sự kiện đầu {r['t_first_event_ms']} ms, khối đầu {r['t_first_block_ms']} ms, "
            f"chữ đầu {r['t_first_text_ms']} ms, tổng {r['total_ms']} ms, model_calls {r['model_calls']}, "
            f"degraded {r['degraded']}, http {r['http_status']}",
            flush=True,
        )
    return cold, recs


def measure_guardrail(sess, n: int) -> dict:
    gid = ssm_param("guardrail/id", sess=sess)
    ver = ssm_param("guardrail/version", sess=sess)
    client = sess.client("bedrock-runtime")

    def call(text: str) -> tuple[float, str]:
        t0 = time.perf_counter()
        resp = client.apply_guardrail(
            guardrailIdentifier=gid,
            guardrailVersion=ver,
            source="INPUT",
            content=[{"text": {"text": text}}],
        )
        return (time.perf_counter() - t0) * 1000, resp.get("action", "?")

    call(GUARDRAIL_TEXTS[0])  # làm nóng kết nối
    ms, actions = [], []
    for i in range(n):
        t, a = call(GUARDRAIL_TEXTS[i % len(GUARDRAIL_TEXTS)])
        ms.append(t)
        actions.append(a)
    return {"samples_ms": [round(x) for x in ms], "actions": actions, "stats": stats_of(ms)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", default="minh")
    ap.add_argument("--turns", type=int, default=10, help="số lượt đo mỗi loại chat và REST")
    ap.add_argument("--guardrail-calls", type=int, default=20)
    ap.add_argument("--pace", type=float, default=17.0, help="giây giữa các lượt gọi model")
    ap.add_argument(
        "--same-session", action="store_true", help="dùng lại một session id cho cả chuỗi lượt chat"
    )
    ap.add_argument(
        "--skip",
        default="",
        help="bỏ qua: whatif,afford_chat,rest,guardrail (phân tách bằng dấu phẩy)",
    )
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}

    sess = session()
    base = api_url(sess)
    url = runtime_url(ssm_param("agent/runtime-arn", sess=sess))
    tokens = Tokens(args.who, sess)
    today = dt.date.today().isoformat()
    result: dict = {
        "date": today,
        "measured_from": "máy phát triển qua Internet (độ trễ mạng gồm trong mọi số, trừ step_timings và ApplyGuardrail trong lượt)",
        "who": args.who,
        "pace_s": args.pace,
        "same_session": args.same_session,
        "turns": args.turns,
        "targets": {"affordability_ms": 2000, "guardrail_ms": 400, "model_calls_max": 4},
    }

    if "whatif" not in skip:
        cold, recs = run_chat_series(
            "what-if",
            url,
            base,
            tokens,
            WHATIF_QS,
            args.turns,
            args.pace,
            want=None,
            same_session=args.same_session,
        )
        summ = summarize_chat(recs, None)
        print_chat("what-if qua chat (đã làm nóng)", summ, None)
        result["whatif"] = {"cold": cold, "runs": recs, "summary": summ}

    if "afford_chat" not in skip:
        time.sleep(args.pace)
        cold, recs = run_chat_series(
            "affordability qua chat",
            url,
            base,
            tokens,
            [AFFORD_Q],
            args.turns,
            args.pace,
            want="affordability_card",
            same_session=args.same_session,
        )
        summ = summarize_chat(recs, "affordability_card")
        print_chat("kiểm tra trước khi quẹt qua chat", summ, "affordability_card")
        result["affordability_chat"] = {"cold": cold, "runs": recs, "summary": summ}

    if "rest" not in skip:
        tok = tokens.get()
        _s, _b, cold_ms = call_api(
            base, "POST", "/affordability", tok, {"amount_vnd": 250_000}, timeout=60
        )
        ms, codes = [], []
        for i in range(args.turns):
            status, _body, t = call_api(
                base,
                "POST",
                "/affordability",
                tok,
                {"amount_vnd": 100_000 + i * 10_000},
                timeout=60,
            )
            ms.append(t)
            codes.append(status)
        st = stats_of(ms)
        print("\n== POST /affordability REST (phiên ấm)")
        print(f"  lượt làm nóng: {cold_ms:.0f} ms; mã HTTP: {sorted(set(codes))}")
        print(line("POST /affordability", st))
        result["affordability_rest"] = {
            "warmup_ms": round(cold_ms),
            "samples_ms": [round(x) for x in ms],
            "http_statuses": codes,
            "stats": st,
        }

    if "guardrail" not in skip:
        g = measure_guardrail(sess, args.guardrail_calls)
        print(
            f"\n== ApplyGuardrail trực tiếp từ máy này (INPUT; hành động: {sorted(set(g['actions']))})"
        )
        print(line("apply_guardrail", g["stats"]))
        result["guardrail_direct"] = g
        in_turn = [
            s["ms"]
            for key in ("whatif", "affordability_chat")
            if key in result
            for r in result[key]["runs"]
            for s in (r.get("step_timings") or [])
            if s["step"] == "guardrail_in"
        ]
        result["guardrail_in_turn_ms"] = stats_of([float(x) for x in in_turn])
        print(line("guardrail_in trong lượt (step_timings)", result["guardrail_in_turn_ms"]))

    out = (
        Path(args.out) if args.out else REPO / "evals" / "results" / f"phase3-measure-{today}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nkết quả thô: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
