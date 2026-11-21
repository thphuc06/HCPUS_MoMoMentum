import type { ComponentType } from 'react'

// Tab chưa làm ở phase này: trạng thái rỗng nói thật, không có số giả.
export function EmptyTabPage({ title, Icon, message }: { title: string; Icon: ComponentType<{ className?: string }>; message: string }) {
  return (
    <>
      <header className="px-4 pt-[max(16px,env(safe-area-inset-top))] pb-4">
        <h1 className="text-title font-bold text-ink">{title}</h1>
      </header>
      <section className="mx-4 flex flex-col items-center rounded-card bg-surface px-6 py-12 text-center shadow-card" data-testid="empty-tab">
        <span className="grid size-16 place-items-center rounded-full bg-tint text-brand-text">
          <Icon className="size-8" aria-hidden />
        </span>
        <h2 className="mt-4 text-subtitle font-semibold text-ink">Sắp có</h2>
        <p className="mt-1 max-w-[260px] text-small text-ink-2">{message}</p>
      </section>
    </>
  )
}
