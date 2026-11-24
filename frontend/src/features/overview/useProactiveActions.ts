import { useCallback } from 'react'
import { useNavigate } from 'react-router'
import { useChatLauncher } from '@/chat/launcher'
import type { NudgeOutcome } from '@/api/phase5Schemas'
import { PROFILE_BEHAVIOR_PATH } from '@/features/behavior/format'
import { muteKind, nudgeKey, snoozeCard } from '@/lib/nudgePrefs'
import type { ProactiveCardData } from '@/contracts/blocks'

export type ProactiveAction = ProactiveCardData['actions'][number]

/**
 * Ý nghĩa các nút của thẻ chủ động (contracts: ProactiveAction.kind). Dùng ở Tổng quan và khi thẻ xuất hiện trong chat.
 * "Hỏi vì sao" mở chat và gửi câu `prompt` do server dựng.
 *
 * "Để sau" và "Ít nhắc loại này": thẻ là bản tin của cổng giá trị (`nudge_id`, phase 5) và nơi dùng truyền `onNudgeFeedback`
 * thì gửi `POST /nudges/{id}/feedback` (snoozed, less_like_this) để cổng hạ loại đó ở các ngày sau; các nút làm việc khác ghi
 * `acted`. Thẻ tất định của `GET /overview` (không có `nudge_id`) vẫn chỉ lưu phía giao diện như phase 2.
 */
export function useProactiveActions(
  card: ProactiveCardData,
  appDate: string,
  onHide?: () => void,
  onNudgeFeedback?: (outcome: NudgeOutcome) => void,
) {
  const navigate = useNavigate()
  const chat = useChatLauncher()
  return useCallback(
    (a: ProactiveAction) => {
      const jar = a.jar_code ?? card.jar_code
      const server = card.nudge_id && onNudgeFeedback ? onNudgeFeedback : undefined
      const go = (to: string) => {
        server?.('acted')
        chat.close()
        navigate(to)
      }
      switch (a.kind) {
        case 'open_forecast':
          go(jar ? `/jars/${jar}` : '/jars')
          break
        case 'ask_why':
          server?.('acted')
          chat.open(a.prompt ?? `Vì sao: ${card.title}`)
          break
        case 'confirm_salary':
          go('/salary')
          break
        case 'review_unclassified':
          go('/review')
          break
        case 'open_obligations':
          go('/obligations')
          break
        case 'open_roadmap':
          go('/roadmap')
          break
        case 'open_resilience':
          go('/foresight')
          break
        case 'open_profile':
          go(PROFILE_BEHAVIOR_PATH)
          break
        case 'snooze':
          if (server) server('snoozed')
          else {
            snoozeCard(nudgeKey(card.kind, card.jar_code), appDate)
            onHide?.()
          }
          break
        case 'mute_kind':
          if (server) server('less_like_this')
          else {
            muteKind(card.kind)
            onHide?.()
          }
          break
      }
    },
    [card, appDate, chat, navigate, onHide, onNudgeFeedback],
  )
}
