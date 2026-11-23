import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { useApi } from '@/api/ApiProvider'
import { ApiError, ErrorCode } from '@/api/errors'
import type { RegenerateRoadmapRequest, RoadmapJob } from '@/api/roadmapSchemas'
import { ScreenHeader } from '@/components/ScreenHeader'
import { EmptyState, ErrorState, ListSkeleton } from '@/components/StateViews'
import { Button, buttonVariants } from '@/components/ui/button'
import type { RoadmapStep } from '@/contracts/blocks'
import { Roadmap } from '@/features/roadmap/Roadmap'
import { EditStepDrawer, ExecuteStepDrawer, RejectStepDialog } from '@/features/roadmap/RoadmapStepDialogs'
import { useRoadmap } from '@/features/roadmap/useRoadmap'
import { useRoadmapJob } from '@/features/roadmap/useRoadmapJob'
import { useRoadmapVersions } from '@/features/roadmap/useRoadmapVersions'
import { useRoadmapMutation, useStepDecision } from '@/features/roadmap/useStepDecision'

const STAGE_LABEL: Record<NonNullable<RoadmapJob['stage']>, string> = {
  context: 'Đang đọc tình hình hiện tại',
  draft: 'Đang soạn các bước',
  allocate: 'Đang tính cách phân bổ',
  suitability: 'Đang kiểm tra mức độ phù hợp',
  save: 'Đang lưu lộ trình',
}

type StepDialog = { kind: 'reject' | 'edit' | 'execute'; step: RoadmapStep; version: number }

function failedJobError(job: RoadmapJob) {
  const code = ErrorCode.safeParse(job.error_code)
  const error = new ApiError(code.success ? code.data : 'INTERNAL_ERROR', 0)
  if (job.error_message) error.message = job.error_message
  return error
}

export function RoadmapPage() {
  const api = useApi()
  const roadmap = useRoadmap()
  const versions = useRoadmapVersions()
  const [startedJob, setStartedJob] = useState<RoadmapJob | null>(null)
  const [dialog, setDialog] = useState<StepDialog | null>(null)
  const loadedJob = versions.data?.current_job ?? null
  const poll = useRoadmapJob(startedJob ?? loadedJob)
  const { job } = poll
  const completed = useRef<string | undefined>(undefined)
  const { reload: reloadRoadmap } = roadmap
  const { reload: reloadVersions } = versions
  const reload = useCallback(() => Promise.all([reloadRoadmap(), reloadVersions()]), [reloadRoadmap, reloadVersions])

  useEffect(() => {
    if (job?.status !== 'done' || completed.current === job.job_id) return
    completed.current = job.job_id
    void reload().then(() => setStartedJob((current) => current?.job_id === job.job_id ? null : current))
  }, [job?.status, job?.job_id, reload])

  const step = useStepDecision((block) => {
    roadmap.replace(block)
    setDialog(null)
    void reloadVersions()
  }, () => {
    setDialog(null)
    return reload()
  })
  const regen = useRoadmapMutation(reload)
  const regenerate = (request: RegenerateRoadmapRequest = {}) => {
    step.clearError()
    void regen.run(() => api.regenerateRoadmap(request), (result) => {
      setStartedJob(result)
      poll.retry()
    })
  }

  const missing = roadmap.error?.code === 'ROADMAP_NOT_FOUND'
  const data = missing ? null : roadmap.data?.data
  const empty = !data && (missing || versions.data?.versions.length === 0)
  const loading = !empty && roadmap.status === 'loading'
  const editable = data?.status === 'active' || data?.status === 'proposed'
  const selectedVersion = data && dialog && data.version === dialog.version ? data : null
  const selectedStep = selectedVersion?.phases.flatMap((phase) => phase.steps).find((step) => step.step_id === dialog?.step.step_id)
  const regenerating = regen.working || poll.polling
  const disabled = regenerating || step.working || roadmap.refreshing
  const proposed = versions.data?.proposed_version
  const closeDialog = () => setDialog(null)
  const openDialog = (kind: StepDialog['kind'], target: RoadmapStep, version: number) => {
    step.clearError()
    setDialog({ kind, step: target, version })
  }

  return (
    <>
      <ScreenHeader title="Lộ trình thích ứng" backTo="/foresight" />
      <div className="space-y-3 px-4 pb-8">
        {poll.polling && job && (
          <section role="status" className="space-y-2 rounded-card bg-surface p-4 shadow-card">
            <p className="text-small font-semibold text-ink">
              {job.stage ? STAGE_LABEL[job.stage] : job.status === 'queued' ? 'Đang chờ lập lộ trình' : 'Đang lập lộ trình'}
            </p>
            <div className="flex items-center gap-3">
              <progress aria-label="Tiến độ lập lộ trình" className="min-w-0 flex-1 accent-primary" value={job.progress} max={100} />
              <span className="num text-small text-ink-2">{job.progress}%</span>
            </div>
          </section>
        )}
        {job?.status === 'failed' && (
          <ErrorState error={failedJobError(job)} title="Chưa lập được lộ trình" />
        )}
        {poll.error && <ErrorState error={poll.error} title="Chưa tải được tiến độ" onRetry={poll.retry} />}
        {poll.timedOut && (
          <section className="space-y-2 rounded-card bg-warn-bg p-4">
            <p role="status" className="text-small text-warn-fg">Lộ trình đang mất nhiều thời gian hơn dự kiến.</p>
            <Button type="button" size="sm" variant="soft" onClick={poll.retry} disabled={regen.working}>Kiểm tra tiến độ</Button>
          </section>
        )}
        {regen.error && <ErrorState error={regen.error} title="Chưa gửi được yêu cầu lập lộ trình" />}
        {step.error && !dialog && <ErrorState error={step.error} title="Chưa cập nhật được lộ trình" />}
        {versions.error && <ErrorState error={versions.error} title="Chưa tải được danh sách phiên bản" onRetry={() => void reloadVersions()} />}
        {roadmap.error && !missing && <ErrorState error={roadmap.error} title="Chưa tải được lộ trình" onRetry={() => void reload()} />}
        {loading && <ListSkeleton rows={2} label="Đang tải lộ trình" />}
        {proposed !== undefined && (
          <Link to="/roadmap/compare" className={buttonVariants({ variant: 'soft', size: 'sm', className: 'w-full' })}>
            Có phiên bản mới
          </Link>
        )}
        {empty && (
          <EmptyState
            title="Chưa có lộ trình"
            message="Lập lộ trình để xem các bước phù hợp với mục tiêu của bạn."
            action={<Button type="button" disabled={disabled} onClick={() => regenerate()}>Lập lộ trình</Button>}
          />
        )}
        {data && (
          <>
            <Roadmap
              data={data}
              disabled={disabled || roadmap.status === 'error'}
              onAccept={editable ? (target) => void step.decide(target.step_id, { version: data.version, decision: 'accepted' }) : undefined}
              onReject={editable ? (target) => openDialog('reject', target, data.version) : undefined}
              onEdit={editable ? (target) => openDialog('edit', target, data.version) : undefined}
              onExecute={editable ? (target) => openDialog('execute', target, data.version) : undefined}
              onAlternative={editable ? (option) => regenerate({ alternative_id: option.option_id, based_on_version: data.version }) : undefined}
            />
            <Button type="button" className="w-full" variant="outline" disabled={disabled} onClick={() => regenerate()}>
              Lập lại lộ trình
            </Button>
          </>
        )}
      </div>
      {dialog?.kind === 'reject' && (
        <RejectStepDialog
          step={dialog.step}
          working={step.working}
          error={step.error}
          onClose={closeDialog}
          onReject={(reason) => void step.decide(dialog.step.step_id, { version: dialog.version, decision: 'rejected', reason })}
        />
      )}
      {dialog?.kind === 'edit' && (
        <EditStepDrawer
          step={dialog.step}
          version={dialog.version}
          working={step.working}
          error={step.error}
          onClose={closeDialog}
          onEdit={(request) => void step.edit(dialog.step.step_id, request)}
        />
      )}
      {dialog?.kind === 'execute' && dialog.step.action && (
        <ExecuteStepDrawer
          title={dialog.step.title}
          action={dialog.step.action}
          available={editable && roadmap.status === 'ready' && !roadmap.refreshing && selectedStep?.status === 'accepted'}
          onClose={closeDialog}
        />
      )}
    </>
  )
}
