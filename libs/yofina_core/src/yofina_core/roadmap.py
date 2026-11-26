"""Hợp đồng của lộ trình và bộ tối ưu phân bổ (phase 4, F5): kiểu dùng chung một nguồn cho bảng `roadmaps` và `roadmap_jobs`,
tool `planner___optimize_allocation`, `planner___save_roadmap`, `planner___get_roadmap`, REST `/roadmap/*` và khối `roadmap`,
`roadmap_diff`.

- `Roadmap`, `RoadmapPhase`, `RoadmapStep` là chính `RoadmapData`, `RoadmapPhase`, `RoadmapStep` của `yofina_core.blocks` (một kiểu cho
  bảng, tool, REST và khối).
- `AllocationPlanData`: kết quả của `optimize_allocation` (khớp `contracts/tools/planner.results.schema.json`).
- `RoadmapDraft`: thứ Roadmap agent gửi cho `save_roadmap` (khớp `contracts/tools/planner.json`): bước CHƯA có trạng thái, id phiên
  bản, hay lý do bằng chữ; Lambda điền (bước luôn ghi ở `pending`, phiên bản tăng dần, `reason.text` do code dựng từ sự kiện).
- `RoadmapJob`, `RoadmapVersionSummary`: lần sinh lại chạy nền (hỏi tiến độ bằng polling) và dòng của danh sách phiên bản.

Chỉ có KIỂU và kiểm bất biến, **không có bộ tối ưu hay agent** (luồng A cài LP, luồng C cài Roadmap agent).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yofina_core.blocks import (
    ActionChange,
    AlternativeKind,
    ForecastBasis,
    ForecastJar,
    GoalProjection,
    IsoDate,
    IsoDateTime,
    JarCode,
    RoadmapAlternative,
    RoadmapCounts,
    RoadmapData,
    RoadmapFeasibility,
    RoadmapPhase,
    RoadmapReasonCode,
    RoadmapStep,
    RoadmapStepAction,
    RoadmapStepKind,
    RoadmapVersion,
    RoadmapVersionStatus,
    RuleId,
    SlugKey,
    Uuid,
    Vnd,
    VndPositive,
)
from yofina_core.wallet import ROADMAP_ACTIVE_REASONS

#: Tên theo file phase: cùng một kiểu với `data` của khối.
Roadmap = RoadmapData

AllocationStatus = Literal["optimal", "relaxed", "infeasible"]
AllocationJarKind = Literal["spending", "saving", "obligation"]
RelaxationKind = Literal["goal_delayed", "discretionary_reduced"]
JobStatus = Literal["queued", "running", "done", "failed"]
JobStage = Literal["context", "draft", "allocate", "suitability", "save"]
JobTrigger = Literal[
    "user_request", "behavior_changed", "goal_changed", "income_changed", "forecast_drift"
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


# --- optimize_allocation -----------------------------------------------------------------------
class AllocationSpend(_Model):
    """Mức chi của một hũ chi (#39, 26/11): DỮ KIỆN cho người lập lộ trình, không phải ràng buộc cứng. `recent_monthly_vnd` là chi trung
    bình của cửa sổ gần nhất (`resilience_window_days` ngày) quy về tháng, không gồm khoản gắn nghĩa vụ; `baseline_monthly_vnd` là mức nền
    bền của chính người dùng (trung vị chi theo tuần trên cửa sổ dài, `yofina_core.spend_baseline`), vắng khi chưa đủ tuần; `keep_floor_vnd`
    là sàn chi gợi ý (tỷ lệ giữ x mức nền bền, hoặc x mức gần đây khi chưa có mức nền; không vượt phần chia hiện tại; bộ tối ưu dùng nó
    làm ràng buộc mềm); `unusually_high` là đợt chi tăng: mức gần đây cao bất thường so với mức nền, hoặc bộ phát hiện đổi hành vi đã xác
    nhận mức chi tăng của hũ. Khi có đợt tăng: `high_since` là ngày bắt đầu (điểm gãy đã xác nhận, hoặc đầu tuần sớm nhất của cửa sổ gần
    đây có chi tuần vượt ngưỡng), `change_confirmed` là bộ phát hiện đổi hành vi đã xác nhận, `runout_date` là ngày dự báo hiện có thấy hũ
    cạn nếu giữ nhịp chi (vắng khi dự báo không thấy hũ cạn hoặc không hiện ngày cạn). Ba trường này tùy chọn (Lambda forecast từ 26/11
    tối)."""

    recent_monthly_vnd: Vnd
    keep_floor_vnd: Vnd
    baseline_monthly_vnd: Vnd | None = None
    unusually_high: bool = False
    high_since: IsoDate | None = None
    change_confirmed: bool = False
    runout_date: IsoDate | None = None


class AllocationLine(_Model):
    """Phân bổ hằng tháng cho một hũ: sàn cứng, mức hiện tại theo tỷ lệ chia, mức đề xuất. `floor_gap_vnd` là phần sàn chưa đạt
    (biến elastic dương của LP); 0 nghĩa là sàn được giữ đủ. `floor_vnd` là sàn CỨNG (nghĩa vụ trả từ hũ, chi thiết yếu); sàn chi theo mức
    chi thật gần đây là sàn mềm, nằm ở `recent_spend` (tùy chọn: chỉ hũ chi của tài khoản đã đủ lịch sử)."""

    jar: ForecastJar
    kind: AllocationJarKind
    is_essential: bool
    floor_vnd: Vnd
    current_monthly_vnd: Vnd
    proposed_monthly_vnd: Vnd
    split_percent_current: Annotated[float, Field(ge=0, le=100)]
    split_percent_proposed: Annotated[float, Field(ge=0, le=100)]
    floor_gap_vnd: Vnd
    recent_spend: AllocationSpend | None = None


class AllocationRelaxation(_Model):
    """Một ràng buộc mềm đã được nới (đúng một vòng nới): lùi hạn mục tiêu hoặc giảm hũ không thiết yếu."""

    kind: RelaxationKind
    jar_code: JarCode
    label: Annotated[str, Field(min_length=1, max_length=60)]
    before: Annotated[str, Field(min_length=1, max_length=80)]
    after: Annotated[str, Field(min_length=1, max_length=120)]


class AllocationSolver(_Model):
    name: Literal["scipy.optimize.linprog"]
    method: Annotated[str, Field(min_length=1, max_length=20)]
    status: Annotated[str, Field(min_length=1, max_length=40)]
    elapsed_ms: Annotated[int, Field(ge=0)]
    relaxation_rounds: Annotated[int, Field(ge=0, le=1)]


class AllocationPlanData(_Model):
    status: AllocationStatus
    headline: Annotated[str, Field(min_length=1, max_length=160)]
    horizon_months: Annotated[int, Field(ge=1, le=24)]
    period_start: IsoDate
    income_monthly_vnd: Vnd
    obligations_monthly_vnd: Vnd
    lines: Annotated[list[AllocationLine], Field(min_length=1, max_length=20)]
    unallocated_vnd: Vnd
    goals: Annotated[list[GoalProjection], Field(max_length=8)]
    relaxations: Annotated[list[AllocationRelaxation], Field(max_length=4)]
    alternatives: Annotated[list[RoadmapAlternative], Field(max_length=2)]
    solver: AllocationSolver
    basis: ForecastBasis

    @model_validator(mode="after")
    def _invariants(self) -> AllocationPlanData:
        """Tiền bảo toàn (tổng phân bổ cộng phần chưa phân bổ bằng thu nhập hằng tháng); `optimal` không nới gì và đạt mọi sàn;
        `relaxed` đã nới đúng một vòng và có ghi lại điều đã nới; `infeasible` đã nới một vòng vẫn không được nên nói thẳng bằng đúng
        hai lựa chọn. Lựa chọn và nới chỉ xuất hiện đúng chỗ."""
        if (
            sum(line.proposed_monthly_vnd for line in self.lines) + self.unallocated_vnd
            != self.income_monthly_vnd
        ):
            raise ValueError(
                "tổng proposed_monthly_vnd cộng unallocated_vnd phải bằng income_monthly_vnd"
            )
        if len({line.jar.code for line in self.lines}) != len(self.lines):
            raise ValueError("mỗi hũ chỉ có một dòng phân bổ")
        if self.status == "optimal":
            if self.relaxations or self.alternatives or self.solver.relaxation_rounds != 0:
                raise ValueError("optimal không nới ràng buộc và không có lựa chọn")
            if any(line.floor_gap_vnd for line in self.lines):
                raise ValueError("optimal phải đạt mọi sàn (floor_gap_vnd bằng 0)")
        elif self.status == "relaxed":
            if not self.relaxations or self.alternatives or self.solver.relaxation_rounds != 1:
                raise ValueError(
                    "relaxed đã nới đúng một vòng, ghi lại điều đã nới, không có lựa chọn"
                )
            if any(line.floor_gap_vnd for line in self.lines):
                raise ValueError("relaxed phải đạt mọi sàn (floor_gap_vnd bằng 0)")
        else:
            if len(self.alternatives) != 2 or self.solver.relaxation_rounds != 1:
                raise ValueError("infeasible đã nới một vòng vẫn không được: đúng hai lựa chọn")
        return self


# --- save_roadmap: bản nháp do agent gửi ----------------------------------------------------------
class RoadmapDraftStep(_Model):
    """Một bước agent soạn. Khác `RoadmapStep` ở chỗ không có `status`, `decided_at`, `edited` (Lambda ghi `pending`)."""

    step_id: SlugKey
    kind: RoadmapStepKind
    title: Annotated[str, Field(min_length=1, max_length=80)]
    reason: Annotated[str, Field(min_length=1, max_length=240)]
    ai_generated: bool | None = None
    amount_vnd: VndPositive | None = None
    jar_code: JarCode | None = None
    to_jar_code: JarCode | None = None
    due_date: IsoDate | None = None
    metrics: Annotated[list[ActionChange], Field(max_length=4)] | None = None
    checked_rules: Annotated[list[RuleId], Field(max_length=8)] | None = None
    action: RoadmapStepAction | None = None


class RoadmapDraftPhase(_Model):
    phase_id: SlugKey
    title: Annotated[str, Field(min_length=1, max_length=60)]
    summary: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    start_date: IsoDate
    end_date: IsoDate
    steps: Annotated[list[RoadmapDraftStep], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def _dates_ordered(self) -> RoadmapDraftPhase:
        if self.end_date < self.start_date:
            raise ValueError("end_date không được trước start_date")
        return self


class RoadmapDraft(_Model):
    """Đầu vào của `planner___save_roadmap`. Phiên bản, id, thời điểm, `reason.text`, `headline`, `counts`, `basis` và
    `rules_version` do Lambda dựng; Lambda còn chạy lại `check_suitability` cho từng bước (vi phạm mức block thì từ chối với
    `ROADMAP_INVALID`) nên agent không thể lưu bước vi phạm."""

    reason_code: RoadmapReasonCode
    based_on_version: RoadmapVersion | None = None
    behavior_flag_id: Uuid | None = None
    feasibility: RoadmapFeasibility
    goals: Annotated[list[GoalProjection], Field(max_length=8)]
    phases: Annotated[list[RoadmapDraftPhase], Field(min_length=1, max_length=5)]
    alternatives: Annotated[list[RoadmapAlternative], Field(max_length=2)]

    @model_validator(mode="after")
    def _invariants(self) -> RoadmapDraft:
        steps = [s for p in self.phases for s in p.steps]
        if len({s.step_id for s in steps}) != len(steps):
            raise ValueError("step_id phải duy nhất trong lộ trình")
        if len({p.phase_id for p in self.phases}) != len(self.phases):
            raise ValueError("phase_id phải duy nhất trong lộ trình")
        starts = [p.start_date for p in self.phases]
        if starts != sorted(starts):
            raise ValueError("giai đoạn phải xếp theo start_date")
        if (self.feasibility == "infeasible") != (len(self.alternatives) == 2):
            raise ValueError(
                "infeasible đi với đúng hai lựa chọn, trường hợp khác không có lựa chọn"
            )
        if self.feasibility == "on_track" and not all(g.on_track for g in self.goals):
            raise ValueError("on_track thì mọi mục tiêu phải kịp")
        if self.feasibility == "infeasible" and all(g.on_track for g in self.goals):
            raise ValueError("infeasible thì phải có ít nhất một mục tiêu không kịp")
        if self.reason_code == "initial" and self.based_on_version is not None:
            raise ValueError("bản đầu tiên không có based_on_version")
        if self.reason_code == "behavior_changed" and self.behavior_flag_id is None:
            raise ValueError("behavior_changed cần behavior_flag_id")
        return self


def status_for_new_version(reason_code: str, has_active: bool) -> RoadmapVersionStatus:
    """Trạng thái của phiên bản mới (quyết định số 8 của phase 4): bản đầu tiên và bản do người dùng tự sửa một bước được dùng NGAY
    (`active`); mọi lần sinh lại khác là `proposed` để người dùng chọn 'Dùng bản mới' hay 'Giữ bản cũ'. Chưa có bản đang dùng thì
    bản nào cũng là `active`."""
    if reason_code in ROADMAP_ACTIVE_REASONS or not has_active:
        return "active"
    return "proposed"


# --- lần sinh lại chạy nền và danh sách phiên bản --------------------------------------------------
class RoadmapJob(_Model):
    """Một lần sinh lại chạy nền (bảng `roadmap_jobs`, REST `GET /roadmap/jobs/{job_id}`). `stage` là bước đang chạy (để hiện tiến
    độ), `progress` 0..100. `done` có `version` và `roadmap_id` của bản vừa lưu; `failed` có `error_code` và `error_message`."""

    job_id: Uuid
    status: JobStatus
    trigger: JobTrigger
    stage: JobStage | None = None
    progress: Annotated[int, Field(ge=0, le=100)]
    requested_at: IsoDateTime
    finished_at: IsoDateTime | None = None
    version: RoadmapVersion | None = None
    roadmap_id: Uuid | None = None
    error_code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]*$")] | None = None
    error_message: Annotated[str, Field(min_length=1, max_length=280)] | None = None

    @model_validator(mode="after")
    def _invariants(self) -> RoadmapJob:
        if (self.status in ("done", "failed")) != (self.finished_at is not None):
            raise ValueError("finished_at có đúng khi status là done hoặc failed")
        if (self.status == "done") != (self.version is not None and self.roadmap_id is not None):
            raise ValueError("done có version và roadmap_id, trạng thái khác thì không")
        if (self.status == "failed") != (
            self.error_code is not None and self.error_message is not None
        ):
            raise ValueError("failed có error_code và error_message, trạng thái khác thì không")
        if self.status == "done" and self.progress != 100:
            raise ValueError("done thì progress bằng 100")
        return self


class RoadmapVersionSummary(_Model):
    """Một dòng của danh sách phiên bản (`GET /roadmap/versions`), không mang các giai đoạn."""

    roadmap_id: Uuid
    version: RoadmapVersion
    status: RoadmapVersionStatus
    reason_code: RoadmapReasonCode
    reason_text: Annotated[str, Field(min_length=1, max_length=160)]
    based_on_version: RoadmapVersion | None = None
    created_at: IsoDateTime
    app_date: IsoDate
    feasibility: RoadmapFeasibility
    counts: RoadmapCounts


__all__ = [
    "AllocationLine",
    "AllocationPlanData",
    "AllocationRelaxation",
    "AllocationSolver",
    "AllocationSpend",
    "AlternativeKind",
    "Roadmap",
    "RoadmapDraft",
    "RoadmapDraftPhase",
    "RoadmapDraftStep",
    "RoadmapJob",
    "RoadmapPhase",
    "RoadmapStep",
    "RoadmapVersionSummary",
    "status_for_new_version",
]
