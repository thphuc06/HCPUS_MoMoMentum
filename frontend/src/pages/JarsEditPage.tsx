import { useNavigate } from 'react-router'
import { ScreenHeader } from '@/components/ScreenHeader'
import { ErrorState } from '@/components/StateViews'
import { Skeleton } from '@/components/ui/skeleton'
import { useApiResource } from '@/api/resource'
import { useOverview } from '@/api/OverviewProvider'
import { JarSplitEditor } from '@/features/jars/JarSplitEditor'

// "Thêm hoặc sửa hũ" (nút + ở Figma C2): chỉnh tên, tỷ lệ chia lương, thêm hũ từ mẫu. Lưu bằng `save_jars`.
export function JarsEditPage() {
  const navigate = useNavigate()
  const ov = useOverview()
  const templates = useApiResource((api) => api.listJarTemplates(), [])
  const loading = ov.status === 'loading' || templates.status === 'loading'
  return (
    <>
      <ScreenHeader title="Thêm hoặc sửa hũ" backTo="/jars" />
      <div className="px-4 pb-10">
        {loading && <Skeleton className="h-[360px] w-full rounded-card" role="status" aria-label="Đang tải hũ" />}
        {ov.status === 'error' && !ov.data && <ErrorState error={ov.error} title="Chưa tải được hũ" onRetry={() => void ov.reload()} />}
        {templates.status === 'error' && <ErrorState error={templates.error} title="Chưa tải được hũ mẫu" onRetry={() => void templates.reload()} />}
        {ov.data && templates.data && (
          <>
            <p className="mb-3 text-small text-ink-2">Sửa tên và tỷ lệ chia lương. Hũ còn tiền thì chưa bỏ được. Tổng các hũ phải đúng 100%.</p>
            <JarSplitEditor jars={ov.data.jars} templates={templates.data.templates} submitLabel="Lưu các hũ" onSaved={() => navigate('/jars', { replace: true })} />
          </>
        )}
      </div>
    </>
  )
}
