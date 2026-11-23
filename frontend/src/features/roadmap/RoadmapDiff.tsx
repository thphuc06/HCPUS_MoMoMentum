import { StatusChip } from '@/components/StatusChip'
import type { RoadmapDiffData } from '@/contracts/blocks'

const CHANGE_KIND = {
  added: { kind: 'ok', label: 'Thêm' },
  removed: { kind: 'bad', label: 'Bỏ' },
  changed: { kind: 'warn', label: 'Đổi' },
} as const

export function RoadmapDiff({ data }: { data: RoadmapDiffData }) {
  return (
    <section data-block="roadmap_diff" className="space-y-3 rounded-card bg-surface p-4 shadow-card">
      <header className="space-y-1">
        <h3 className="text-subtitle font-semibold text-ink">So sánh lộ trình · Bản {data.from_version} → {data.to_version}</h3>
        <p className="text-small text-ink">{data.headline}</p>
        <p className="text-small text-ink-2">{data.reason.text}</p>
      </header>
      <ul className="space-y-2">
        {data.changes.map((change) => {
          const status = CHANGE_KIND[change.kind]
          return (
            <li key={change.step_id} className="space-y-1 rounded-xl bg-surface-2 px-3 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-small font-semibold text-ink">{change.title}</p>
                <StatusChip kind={status.kind}>{status.label}</StatusChip>
              </div>
              {change.fields && change.fields.length > 0 && (
                <dl className="text-small text-ink-2">
                  {change.fields.map((field, i) => (
                    <div key={`${field.label}-${i}`} className="flex flex-wrap justify-between gap-x-3">
                      <dt>{field.label}</dt>
                      <dd className="num">{field.before && `${field.before} → `}{field.after}</dd>
                    </div>
                  ))}
                </dl>
              )}
              {change.reason_after && <p className="text-small text-ink-2">{change.reason_after}</p>}
            </li>
          )
        })}
      </ul>
      <p className="text-small text-ink-2">{data.can_adopt ? 'Có thể chọn dùng bản mới.' : 'Bản mới hiện không thể chọn.'}</p>
    </section>
  )
}
