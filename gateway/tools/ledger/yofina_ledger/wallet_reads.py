"""Phía ĐỌC của ví mô phỏng: Tổng quan, chi tiết hũ, giao dịch, nghĩa vụ, hạn mức, lương, dự báo, dòng tiền.

Mixin của `LedgerService`: dùng `self.repo`, `self.settings`, `self.ref` (bảng tra), `self.now()`, `self._app_date()`.
Mọi con số đi từ Aurora (hàm `app_*`), không số nào nằm trong mã. REST và tool Gateway gọi cùng các hàm này.
"""

from __future__ import annotations

import base64
import json
from datetime import date, datetime, timedelta
from typing import Any

from yofina_core.blocks import (
    ForecastTimelineBlock,
    ProactiveCardBlock,
    block_to_wire,
    build_forecast_timeline,
    format_instant,
    new_trace_id,
)
from yofina_core.clock import latest_payday, next_payday
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.params import JAR_CODE_RE, UUID_RE
from yofina_core.schedule import build_timeline_events
from yofina_ledger import convert
from yofina_ledger.proactive import choose_proactive_card

CURSOR_MAX = 200
SALARY_EVENT_LABEL = "Lương về"


def encode_cursor(occurred_at: datetime, tx_id: str) -> str:
    raw = json.dumps([format_instant(occurred_at), str(tx_id)], separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    """Con trỏ mờ -> (occurred_at, id). Sai định dạng thì PARAMS_INVALID."""
    try:
        if not isinstance(cursor, str) or not 1 <= len(cursor) <= CURSOR_MAX:
            raise ValueError
        arr = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        at, tid = arr
        moment = convert.to_instant(at)
        if moment is None or not UUID_RE.fullmatch(str(tid)):
            raise ValueError
        return moment, str(tid)
    except (ValueError, TypeError, json.JSONDecodeError):
        raise YofinaError(ErrorCode.PARAMS_INVALID, "Con trỏ trang không hợp lệ.") from None


def _opt_date(name: str, raw: Any) -> date | None:
    if raw in (None, ""):
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        raise YofinaError(ErrorCode.PARAMS_INVALID, f"{name} phải có dạng YYYY-MM-DD.") from None


def _opt_limit(raw: Any, default: int, maximum: int) -> int:
    if raw in (None, ""):
        return default
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise YofinaError(ErrorCode.PARAMS_INVALID, "limit phải là số nguyên.") from None
    return max(1, min(n, maximum))


class WalletReads:
    """Mixin: các hàm đọc. Thuộc tính dùng: repo, settings, ref, now(), _app_date()."""

    # --- hồ sơ ---------------------------------------------------------------------------------------------
    def _profile(self, row: dict[str, Any] | None, name_hint: str | None) -> dict[str, Any]:
        """`Profile` của hợp đồng. `onboarded` khi có cả lương và ngày nhận (hai thứ bắt buộc duy nhất)."""
        name = (row or {}).get("display_name") or name_hint or self.settings.default_display_name
        out: dict[str, Any] = {"display_name": name, "onboarded": False}
        if row:
            if row.get("monthly_salary_vnd") is not None:
                out["monthly_salary_vnd"] = convert.vnd(row["monthly_salary_vnd"])
            if row.get("payday_day") is not None:
                out["payday_day"] = int(row["payday_day"])
            if row.get("risk_tolerance"):
                out["risk_tolerance"] = row["risk_tolerance"]
            out["onboarded"] = "monthly_salary_vnd" in out and "payday_day" in out
        return out

    def profile_response(self, user_id: str, *, name_hint: str | None = None) -> dict[str, Any]:
        now = self.now()
        row = self.repo.user_row(user_id)
        offset = int(row["clock_offset_days"]) if row else 0
        return {
            "app_date": self._app_date(offset, now).isoformat(),
            "as_of": format_instant(now),
            "profile": self._profile(row, name_hint),
        }

    # --- Tổng quan -----------------------------------------------------------------------------------------
    def overview_response(
        self, user_id: str, *, trace_id: str | None = None, name_hint: str | None = None
    ) -> dict[str, Any]:
        """Mọi thứ Tổng quan cần trong MỘT lệnh gọi Aurora (`app_get_overview`)."""
        trace = trace_id or new_trace_id()
        now = self.now()
        data = self.repo.overview(user_id, now, self.settings.app_timezone)
        today = convert.to_date(data["app_date"])
        assert today is not None
        profile = self._profile(data.get("profile"), name_hint)
        forecasts = {f["jar_code"]: f for f in data.get("forecasts", [])}
        all_jars = data.get("jars", [])
        user_jars = [j for j in all_jars if j["kind"] != "system"]
        system_jars = [j for j in all_jars if j["kind"] == "system"]

        def full(j: dict[str, Any]) -> dict[str, Any]:
            return convert.jar_full_json(
                j, forecasts.get(j["code"]) if j["kind"] != "system" else None
            )

        jars_total = sum(convert.vnd(j["balance_vnd"]) for j in user_jars)
        by_role = {j.get("system_role"): convert.vnd(j["balance_vnd"]) for j in system_jars}
        other = by_role.get("other_income", 0)
        unclassified = by_role.get("unclassified", 0)

        next_pay = None
        if profile.get("onboarded"):
            payday_day = profile["payday_day"]
            nxt = next_payday(payday_day, today)
            latest = latest_payday(payday_day, today)
            event = data.get("salary_event")
            confirmed = convert.to_date(data.get("confirmed_period"))
            state = (
                "confirmed"
                if confirmed == latest
                else "pending_confirmation"
                if event
                else "expected"
            )
            next_pay = {
                "date": nxt.isoformat(),
                "days_until": (nxt - today).days,
                "expected_vnd": profile["monthly_salary_vnd"],
                "state": state,
            }
            if state == "pending_confirmation" and event:
                next_pay["salary_event_id"] = str(event["id"])

        meta = self._forecast_meta(list(forecasts.values()), today, now)
        fc = getattr(self, "forecast", None)
        if fc is not None and profile.get("onboarded") and (meta is None or meta["stale"]):
            # Tổng quan không chờ tính lại (giữ p95 thấp): kích hoạt nền, lần đọc sau sẽ thấy số mới; lần này trả `stale: true`.
            fc.request(user_id, "read")
        card: ProactiveCardBlock | None = None
        if profile.get("onboarded"):
            card = choose_proactive_card(
                today=today,
                jars=user_jars,
                forecasts=forecasts,
                salary_event=data.get("salary_event"),
                obligations_due=data.get("obligations_due", []),
                review_count=int(data.get("review_count") or 0),
                obligation_days=self.settings.proactive_obligation_days,
                trace_id=trace,
                as_of=now,
                source_tool="rest:GET /overview",
            )
        credit = None
        if data.get("credit_line"):
            credit = convert.credit_line_json(
                data["credit_line"],
                self.ref.product_label(data["credit_line"]["product_code"], today),
            )
        return {
            "app_date": today.isoformat(),
            "as_of": format_instant(now),
            "profile": profile,
            "balance": {
                "total_vnd": jars_total + other + unclassified,
                "jars_total_vnd": jars_total,
                "other_income_vnd": other,
                "unclassified_vnd": unclassified,
            },
            "jars": [full(j) for j in user_jars],
            "system_jars": [full(j) for j in system_jars],
            "next_payday": next_pay,
            "forecast": meta,
            "proactive_card": block_to_wire(card) if card else None,
            "credit_line": credit,
            "obligations_due": [
                convert.obligation_json(o) for o in data.get("obligations_due", [])
            ],
            "recent_transactions": [
                convert.tx_json(t) for t in data.get("recent_transactions", [])
            ],
            "needs_review_count": int(data.get("review_count") or 0),
        }

    def _forecast_meta(
        self, summaries: list[dict[str, Any]], today: date, now: datetime
    ) -> dict[str, Any] | None:
        """Chất lượng lần chạy dự báo mới nhất (theo `computed_at`). Tổng quan không chờ tính lại dự báo (chỉ kích hoạt nền)."""
        if not summaries:
            return None
        latest = max(summaries, key=lambda s: (str(s["computed_at"]), str(s["run_id"])))
        computed = convert.to_instant(latest["computed_at"])
        assert computed is not None
        meta: dict[str, Any] = {
            "computed_at": format_instant(computed),
            "run_app_date": convert.to_date(latest["run_app_date"]).isoformat(),  # type: ignore[union-attr]
            "stale": self._is_stale(latest, today, computed, now),
            "is_initial_estimate": bool(latest["is_initial_estimate"]),
            "confidence_band": latest["confidence_label"],
            "history_days": int(latest["history_days"]),
            "model": latest["model"],
        }
        if latest.get("data_coverage") is not None:
            meta["coverage"] = float(latest["data_coverage"])
        return meta

    def _is_stale(
        self, summary: dict[str, Any], today: date, computed: datetime, now: datetime
    ) -> bool:
        """Cũ khi ngày mô phỏng đã sang ngày khác so với lần chạy, hoặc quá hạn độ tươi (cấu hình)."""
        if convert.to_date(summary["run_app_date"]) != today:
            return True
        return (now - computed) > timedelta(seconds=self.settings.forecast_freshness_seconds)

    # --- chi tiết hũ ---------------------------------------------------------------------------------------
    def jar_detail_response(self, user_id: str, jar_code: str) -> dict[str, Any]:
        if not JAR_CODE_RE.fullmatch(str(jar_code)):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Mã hũ không hợp lệ.")
        now = self.now()
        data = self.repo.jar_detail(user_id, jar_code, now, self.settings.app_timezone)
        today = convert.to_date(data["app_date"])
        assert today is not None
        jar = data.get("jar")
        if not jar:
            raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ này.")
        f = data.get("forecast")
        meta = None
        if f:
            computed = convert.to_instant(f["computed_at"])
            assert computed is not None
            meta = self._forecast_meta([f], today, now)
        return {
            "app_date": today.isoformat(),
            "as_of": format_instant(now),
            "jar": convert.jar_full_json(jar, f if jar["kind"] != "system" else None),
            "forecast": meta,
            "recent_transactions": [
                convert.tx_json(t) for t in data.get("recent_transactions", [])
            ],
            "obligations": [convert.obligation_json(o) for o in data.get("obligations", [])],
        }

    # --- giao dịch -----------------------------------------------------------------------------------------
    def transactions_response(
        self,
        user_id: str,
        *,
        jar: Any = None,
        kind: Any = None,
        tx_type: Any = None,
        from_date: Any = None,
        to_date: Any = None,
        needs_review: Any = None,
        limit: Any = None,
        cursor: Any = None,
    ) -> dict[str, Any]:
        """Danh sách giao dịch, mới nhất trước, lọc và phân trang con trỏ (LIMIT cứng ở hàm SQL)."""
        s = self.settings
        jar_code = None
        if jar not in (None, ""):
            jar_code = str(jar).strip().lower()
            if not JAR_CODE_RE.fullmatch(jar_code):
                raise YofinaError(ErrorCode.PARAMS_INVALID, "Mã hũ không hợp lệ.")
        if kind not in (None, "") and kind not in ("expense", "income", "transfer"):
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, "kind phải là expense, income hoặc transfer."
            )
        if tx_type not in (None, "") and not isinstance(tx_type, str):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "tx_type phải là chuỗi.")
        review: bool | None = None
        if needs_review not in (None, ""):
            text = str(needs_review).lower()
            if text not in ("true", "false", "1", "0"):
                raise YofinaError(ErrorCode.PARAMS_INVALID, "needs_review phải là true hoặc false.")
            review = text in ("true", "1")
        n = _opt_limit(limit, s.transactions_default_limit, s.transactions_max_limit)
        cur = decode_cursor(cursor) if cursor not in (None, "") else None
        now = self.now()
        rows = self.repo.list_transactions(
            user_id,
            jar=jar_code,
            from_date=_opt_date("from", from_date),
            to_date=_opt_date("to", to_date),
            kind=kind or None,
            tx_type=(tx_type or None),
            needs_review=review,
            cursor=cur,
            limit=n + 1,
        )
        has_more = len(rows) > n
        page = rows[:n]
        out: dict[str, Any] = {
            "app_date": self._app_date(self.repo.clock_offset(user_id), now).isoformat(),
            "as_of": format_instant(now),
            "transactions": [convert.tx_json(r) for r in page],
        }
        if has_more and page:
            out["next_cursor"] = encode_cursor(page[-1]["occurred_at"], str(page[-1]["id"]))
        return out

    # --- nghĩa vụ, hạn mức, lương ----------------------------------------------------------------------------
    def obligations_response(
        self,
        user_id: str,
        *,
        status: Any = None,
        within_days: Any = None,
        limit: Any = None,
        include_credit_line: bool = False,
    ) -> dict[str, Any]:
        st = "active" if status in (None, "") else str(status)
        if st not in ("active", "paid", "cancelled", "all"):
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, "status phải là active, paid, cancelled hoặc all."
            )
        now = self.now()
        offset = self.repo.clock_offset(user_id)
        today = self._app_date(offset, now)
        due_before = None
        if within_days not in (None, ""):
            try:
                days = int(within_days)
            except (TypeError, ValueError):
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID, "within_days phải là số nguyên."
                ) from None
            if not 0 <= days <= 400:
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID, "within_days phải trong khoảng 0 đến 400."
                )
            due_before = today + timedelta(days=days)
        rows = self.repo.list_obligations(
            user_id, status=st, due_before=due_before, limit=_opt_limit(limit, 50, 100)
        )
        obs = [convert.obligation_json(r) for r in rows]
        out: dict[str, Any] = {
            "app_date": today.isoformat(),
            "obligations": obs,
            "total_due_vnd": sum(o["amount_vnd"] for o in obs if o["status"] == "active"),
        }
        if (
            include_credit_line
        ):  # dạng của tool: kèm hạn mức và `as_of` (REST `ObligationsResponse` không có `as_of`)
            out["as_of"] = format_instant(now)
            line = self.repo.credit_line(user_id)
            if line:
                out["credit_line"] = convert.credit_line_json(
                    line, self.ref.product_label(line["product_code"], today)
                )
        return out

    def credit_line_response(self, user_id: str) -> dict[str, Any]:
        now = self.now()
        today = self._app_date(self.repo.clock_offset(user_id), now)
        line = self.repo.credit_line(user_id)
        fees = []
        if line:
            for f in self.ref.active_fees(line["product_code"], today):
                item: dict[str, Any] = {
                    "fee_type": f.fee_type,
                    "period": f.period,
                    "condition_code": f.condition_code,
                    "source_name": f.source_name,
                    "source_url": f.source_url,
                    "effective_from": f.effective_from.isoformat(),
                }
                if f.amount_vnd is not None:
                    item["amount_vnd"] = f.amount_vnd
                if f.rate_percent is not None:
                    item["rate_percent"] = float(f.rate_percent)
                if f.condition_note:
                    item["condition_note"] = f.condition_note
                fees.append(item)
        return {
            "app_date": today.isoformat(),
            "credit_line": (
                convert.credit_line_json(line, self.ref.product_label(line["product_code"], today))
                if line
                else None
            ),
            "fees": fees,
        }

    def salary_events_response(self, user_id: str, *, status: Any = None) -> dict[str, Any]:
        st = "pending" if status in (None, "") else str(status)
        if st not in ("pending", "confirmed", "kept_other", "all"):
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, "status phải là pending, confirmed, kept_other hoặc all."
            )
        rows = self.repo.salary_events(user_id, st)
        return {"salary_events": [convert.salary_event_json(r) for r in rows]}

    def payees_response(self, user_id: str) -> dict[str, Any]:
        return {"payees": [convert.payee_json(r) for r in self.repo.list_payees(user_id)]}

    def tx_types_response(self) -> dict[str, Any]:
        out = []
        for info in self.ref.tx_types().values():  # đã theo sort_order của bảng tra
            if not info.is_selectable or info.direction == "internal":
                continue
            item: dict[str, Any] = {
                "tx_type": info.tx_type,
                "label": info.label,
                "direction": info.direction,
                "is_person_transfer": info.is_person_transfer,
            }
            if info.default_jar_code:
                item["default_jar"] = info.default_jar_code
            if info.system_role:
                item["system_role"] = info.system_role
            out.append(item)
        return {"tx_types": out}

    def jar_templates_response(self) -> dict[str, Any]:
        return {
            "templates": [
                {
                    "code": t.code,
                    "name": t.name,
                    "color_key": t.color_key,
                    "icon_key": t.icon_key,
                    "kind": t.kind,
                    "default_split_percent": convert.percent(t.default_split_percent),
                    "is_default": t.is_default,
                }
                for t in self.ref.templates()
            ]
        }

    # --- dòng tiền và chưa phân loại (tool của agent) -----------------------------------------------------
    def cashflow_result(
        self, user_id: str, *, from_date: Any = None, to_date: Any = None
    ) -> dict[str, Any]:
        now = self.now()
        row = self.repo.user_row(user_id)
        offset = int(row["clock_offset_days"]) if row else 0
        today = self._app_date(offset, now)
        start = _opt_date("from_date", from_date)
        end = _opt_date("to_date", to_date)
        if start is None and end is None:
            payday = row["payday_day"] if row else None
            start = latest_payday(int(payday), today) if payday else today.replace(day=1)
            end = today
        else:
            start = start or end
            end = end or today
        assert start is not None and end is not None
        if start > end:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "from_date không được sau to_date.")
        raw = self.repo.cashflow(user_id, start, end)
        names = {j["code"]: j["name"] for j in self.repo.jar_view(user_id).jars}
        by_jar = [
            {
                "jar": r["jar_code"],
                "name": names.get(r["jar_code"], r["jar_code"]),
                "spent_vnd": convert.vnd(r["spent_vnd"]),
                "tx_count": int(r["tx_count"]),
            }
            for r in raw.get("by_jar", [])
            if r.get("jar_code")
        ]
        salary = sum(
            convert.vnd(r["amount_vnd"])
            for r in raw.get("income_by_type", [])
            if r["tx_type"] == "salary"
        )
        other = sum(
            convert.vnd(r["amount_vnd"])
            for r in raw.get("income_by_type", [])
            if r["tx_type"] != "salary"
        )
        stats = self.repo.review_stats(user_id)
        return {
            "status": "OK",
            "as_of": format_instant(now),
            "app_date": today.isoformat(),
            "data": {
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
                "salary_income_vnd": salary,
                "other_income_vnd": other,
                "spent_vnd": sum(j["spent_vnd"] for j in by_jar),
                "by_jar": by_jar,
                "unclassified_pending_vnd": convert.vnd(stats["pending_total"]),
            },
        }

    def unclassified_result(self, user_id: str, *, limit: Any = None) -> dict[str, Any]:
        now = self.now()
        n = _opt_limit(limit, 20, 50)
        rows = self.repo.unclassified(user_id, n)
        view = self.repo.jar_view(user_id)
        names = {j["code"]: j["name"] for j in view.jars if j.get("kind") != "system"}
        tx_types = self.ref.tx_types()
        items = []
        for r in rows:
            suggested = list(r.get("suggested_jars") or [])
            if (
                not suggested
            ):  # chưa có gợi ý do phân loại (phase 4): lấy hũ chuẩn của loại giao dịch
                info = tx_types.get(r.get("tx_type") or "")
                if info and info.default_jar_code in names:
                    suggested = [info.default_jar_code]
            items.append(
                {
                    "transaction": convert.tx_json(r),
                    "suggested_jars": [
                        {"code": c, "name": names[c]} for c in suggested[:2] if c in names
                    ],
                }
            )
        stats = self.repo.review_stats(user_id)
        return {
            "status": "OK",
            "as_of": format_instant(now),
            "app_date": self._app_date(view.clock_offset_days or 0, now).isoformat(),
            "data": {
                "items": items,
                "count": int(stats["review_count"]),
                "pending_total_vnd": convert.vnd(stats["pending_total"]),
            },
        }

    # --- dự báo (chỉ đọc bảng; việc tính là của pipeline) --------------------------------------------------
    def forecast_block_or_none(
        self, user_id: str, jar_code: str, *, trace_id: str, source_tool: str
    ) -> ForecastTimelineBlock | None:
        """Khối `forecast_timeline` của một hũ từ lần chạy dự báo MỚI NHẤT có chứa hũ; mốc nghĩa vụ và lương ghép lúc
        đọc. None khi hũ chưa có dự báo nào (người gọi quyết định tính ngay hay báo chưa sẵn sàng). Hũ không có, hũ hệ
        thống, hồ sơ chưa khai vẫn là lỗi."""
        if not JAR_CODE_RE.fullmatch(str(jar_code)):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Mã hũ không hợp lệ.")
        now = self.now()
        view = self.repo.jar_view(user_id)
        jar = view.jar(jar_code)
        if jar is None:
            raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ này.")
        profile = self.repo.user_row(user_id)
        if not profile or profile["monthly_salary_vnd"] is None or profile["payday_day"] is None:
            raise YofinaError(
                ErrorCode.PROFILE_INCOMPLETE, "Bạn chưa khai lương và ngày nhận lương."
            )
        today = self._app_date(view.clock_offset_days or 0, now)
        if jar.get("kind") == "system":
            raise YofinaError(ErrorCode.FORECAST_UNAVAILABLE, "Hũ hệ thống không có dự báo.")
        summaries = self.repo.forecast_summaries(user_id, jar_code)
        if not summaries:
            return None
        summary = summaries[0]
        series = self.repo.forecast_series(user_id, jar_code)
        if not series:
            return None
        obligations = self.repo.list_obligations(user_id, status="active", limit=100)
        user_jars = [j for j in view.jars if j.get("kind") != "system"]
        default_pay_jar = next(
            (j["code"] for j in user_jars if j.get("kind") == "obligation"), None
        )
        origin = convert.to_date(summary["run_app_date"])
        assert origin is not None
        events = build_timeline_events(
            jar_code=jar_code,
            obligations=obligations,
            origin=origin,
            horizon_days=int(summary["horizon_days"]),
            default_pay_jar=default_pay_jar,
            salary_vnd=convert.vnd(profile["monthly_salary_vnd"]),
            payday_day=int(profile["payday_day"]),
            split_shares=[(j["code"], j["split_percent"]) for j in user_jars],
            salary_label=SALARY_EVENT_LABEL,
        )
        computed = convert.to_instant(summary["computed_at"])
        assert computed is not None
        stale = self._is_stale(summary, today, computed, now)
        return build_forecast_timeline(
            jar={
                "code": jar["code"],
                "name": jar["name"],
                "color_key": jar["color_key"],
                "icon_key": jar["icon_key"],
            },
            summary=summary,
            days=series,
            events=[
                {
                    "date": e.date,
                    "kind": e.kind,
                    "label": e.label,
                    "amount_vnd": e.amount_vnd,
                    "amount_max_vnd": e.amount_max_vnd,
                }
                for e in events
            ],
            stale=stale,
            trace_id=trace_id,
            source_tool=source_tool,
            as_of=now,
            app_date=today,
        )

    def forecast_block(
        self, user_id: str, jar_code: str, *, trace_id: str, source_tool: str
    ) -> ForecastTimelineBlock:
        """Như `forecast_block_or_none` nhưng chưa có dự báo thì FORECAST_UNAVAILABLE (503)."""
        block = self.forecast_block_or_none(
            user_id, jar_code, trace_id=trace_id, source_tool=source_tool
        )
        if block is None:
            raise YofinaError(
                ErrorCode.FORECAST_UNAVAILABLE,
                "Chưa có dự báo cho hũ này. Dự báo được tính mỗi đêm và khi có giao dịch, thử lại sau ít phút.",
            )
        return block

    def forecast_response(self, user_id: str, jar_code: str, *, trace_id: str) -> dict[str, Any]:
        """`GET /forecasts/{jar_code}`. Chưa có dự báo hoặc quá hạn độ tươi thì TÍNH LẠI ĐỒNG BỘ trước khi trả (gọi Lambda
        `yofina-forecast-batch`); không tính được mà còn bản cũ thì trả bản cũ với `stale: true`.

        Chọn đồng bộ cho endpoint này (khác `GET /overview` chỉ kích hoạt nền) vì đây là màn xem MỘT hũ: chờ thêm một, hai giây
        để thấy số mới là chấp nhận được, còn Tổng quan phải nhanh (p95 dưới 300 ms)."""
        source = "rest:GET /forecasts/{jar_code}"
        block = self.forecast_block_or_none(
            user_id, jar_code, trace_id=trace_id, source_tool=source
        )
        fc = getattr(self, "forecast", None)
        if fc is not None and (block is None or block.data.stale) and fc.compute(user_id, "read"):
            fresh = self.forecast_block_or_none(
                user_id, jar_code, trace_id=trace_id, source_tool=source
            )
            block = fresh or block
        if block is None:
            raise YofinaError(
                ErrorCode.FORECAST_UNAVAILABLE,
                "Chưa có dự báo cho hũ này. Dự báo được tính mỗi đêm và khi có giao dịch, thử lại sau ít phút.",
            )
        return block_to_wire(block)
