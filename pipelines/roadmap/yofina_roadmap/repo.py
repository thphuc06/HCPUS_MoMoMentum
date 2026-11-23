"""Quản lý vòng đời roadmap_jobs qua Data API dưới RLS."""

from __future__ import annotations

from yofina_core.db import DataApi, Row
from yofina_core.errors import ErrorCode
from yofina_core.roadmap import JobStage, Roadmap
from yofina_roadmap.events import RoadmapEvent

_JOB_COLUMNS = "id, status, trigger, based_on_version, behavior_flag_id, alternative_id, note"


class JobBusy(RuntimeError):
    """Một lần giao khác đang xử lý job, hoặc người dùng có job sống khác."""


class RoadmapRepo:
    def __init__(self, db: DataApi, running_lease_seconds: int) -> None:
        self._db = db
        self._running_lease_seconds = running_lease_seconds

    def claim(self, event: RoadmapEvent) -> Row | None:
        """Tạo nếu cần, rồi nhận đúng một job queued trong cùng transaction."""
        uid = event.user_id
        with self._db.transaction(uid) as tx:
            tx.execute(
                """
                UPDATE roadmap_jobs
                SET status = 'failed', error_code = :code, error_message = :message,
                    finished_at = now(), updated_at = now()
                WHERE user_id = :uid AND status = 'running'
                  AND coalesce(started_at, updated_at)
                      <= now() - make_interval(secs => CAST(:lease AS double precision))
                """,
                {
                    "uid": uid,
                    "lease": self._running_lease_seconds,
                    "code": ErrorCode.INTERNAL_ERROR.value,
                    "message": "Lần sinh lại đã hết thời gian xử lý.",
                },
            )
            if event.job_id is not None:
                # app_get_roadmap_job phục vụ REST và không trả cột note.
                jobs = tx.execute(
                    f"""
                    SELECT {_JOB_COLUMNS} FROM roadmap_jobs
                    WHERE user_id = :uid AND id = CAST(:job_id AS uuid) LIMIT 1
                    """,
                    {"uid": uid, "job_id": event.job_id},
                )
            else:
                jobs = tx.execute(
                    f"""
                    INSERT INTO roadmap_jobs (user_id, trigger, dedupe_key, behavior_flag_id)
                    VALUES (:uid, :trigger, :event_id, CAST(:flag_id AS uuid))
                    ON CONFLICT DO NOTHING
                    RETURNING {_JOB_COLUMNS}
                    """,
                    {
                        "uid": uid,
                        "trigger": event.trigger,
                        "event_id": event.event_id,
                        "flag_id": event.behavior_flag_id,
                    },
                )
                if not jobs:
                    jobs = tx.execute(
                        f"""
                        SELECT {_JOB_COLUMNS} FROM roadmap_jobs
                        WHERE user_id = :uid AND dedupe_key = :event_id LIMIT 1
                        """,
                        {"uid": uid, "event_id": event.event_id},
                    )
                    if not jobs:
                        # Chỉ mục một job sống chặn INSERT của một sự kiện khác.
                        raise JobBusy()
            if not jobs or jobs[0]["status"] in ("done", "failed"):
                return None
            claimed = tx.execute(
                f"""
                UPDATE roadmap_jobs
                SET status = 'running', started_at = now(), updated_at = now()
                WHERE user_id = :uid AND id = CAST(:job_id AS uuid) AND status = 'queued'
                RETURNING {_JOB_COLUMNS}
                """,
                {"uid": uid, "job_id": jobs[0]["id"]},
            )
            if not claimed:
                raise JobBusy()
            return claimed[0]

    def stage(self, uid: str, job_id: str, stage: JobStage, progress: int) -> None:
        with self._db.transaction(uid) as tx:
            tx.execute(
                """
                UPDATE roadmap_jobs SET stage = :stage, progress = :progress, updated_at = now()
                WHERE user_id = :uid AND id = CAST(:job_id AS uuid) AND status = 'running'
                """,
                {"uid": uid, "job_id": job_id, "stage": stage, "progress": progress},
            )

    def done(self, uid: str, job_id: str, roadmap: Roadmap) -> None:
        with self._db.transaction(uid) as tx:
            tx.execute(
                """
                UPDATE roadmap_jobs
                SET status = 'done', progress = 100, roadmap_id = CAST(:roadmap_id AS uuid),
                    version = :version, based_on_version = :based_on_version,
                    finished_at = now(), updated_at = now()
                WHERE user_id = :uid AND id = CAST(:job_id AS uuid) AND status = 'running'
                """,
                {
                    "uid": uid,
                    "job_id": job_id,
                    "roadmap_id": roadmap.roadmap_id,
                    "version": roadmap.version,
                    "based_on_version": roadmap.based_on_version,
                },
            )

    def failed(self, uid: str, job_id: str, code: ErrorCode, message: str) -> None:
        with self._db.transaction(uid) as tx:
            tx.execute(
                """
                UPDATE roadmap_jobs
                SET status = 'failed', error_code = :code, error_message = :message,
                    finished_at = now(), updated_at = now()
                WHERE user_id = :uid AND id = CAST(:job_id AS uuid) AND status = 'running'
                """,
                {"uid": uid, "job_id": job_id, "code": code.value, "message": message[:280]},
            )
