import { useInRouterContext, useNavigate } from 'react-router'
import { Button } from '@/components/ui/button'
import { useChatLauncher } from '@/chat/launcher'
import { CoverageChange, mostAffectedJar } from '@/features/ingest/CoverageChange'
import { IngestReviewList } from '@/features/ingest/IngestReview'
import type { CoverageChangeBlock, IngestReviewBlock } from '@/contracts/blocks'
import type { BlockViewProps } from './views'

// Hai khối của phase 5 (F6): ingest_review, coverage_change. Cùng component với màn Nạp dữ liệu (/ingest), nên chat và màn
// hình luôn cùng số. Trong chat chỉ XEM: duyệt và chốt làm ở màn Nạp dữ liệu (cần chọn dòng, đổi hũ, xác nhận bằng token).

function OpenIngestButton({ jobId, label }: { jobId: string; label: string }) {
  const navigate = useNavigate()
  const launcher = useChatLauncher()
  return (
    <Button
      type="button"
      variant="soft"
      className="mt-3 w-full"
      onClick={() => {
        launcher.close()
        navigate(`/ingest?job=${encodeURIComponent(jobId)}`)
      }}
    >
      {label}
    </Button>
  )
}

export function IngestReviewView({ block }: BlockViewProps<IngestReviewBlock>) {
  const d = block.data
  const inRouter = useInRouterContext()
  const footer = d.status === 'review' && inRouter ? <OpenIngestButton jobId={d.job_id} label="Mở để duyệt và cập nhật dự báo" /> : null
  return <IngestReviewList data={d} footer={footer} />
}

function ForecastLink({ code }: { code: string }) {
  const navigate = useNavigate()
  const launcher = useChatLauncher()
  return (
    <Button
      type="button"
      onClick={() => {
        launcher.close()
        navigate(`/jars/${encodeURIComponent(code)}`)
      }}
    >
      Xem dự báo cập nhật
    </Button>
  )
}

export function CoverageChangeView({ block }: BlockViewProps<CoverageChangeBlock>) {
  const inRouter = useInRouterContext()
  const code = mostAffectedJar(block.data)
  return <CoverageChange data={block.data} actions={inRouter && code ? <ForecastLink code={code} /> : undefined} />
}
