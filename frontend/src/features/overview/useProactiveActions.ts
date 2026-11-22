import { useCallback } from 'react'
import { useNavigate } from 'react-router'
import { useChatLauncher } from '@/chat/launcher'
import { muteKind, nudgeKey, snoozeCard } from '@/lib/nudgePrefs'
import type { ProactiveCardData } from '@/contracts/blocks'

export type ProactiveAction = ProactiveCardData['actions'][number]

/**
 * Ý nghĩa các nút của thẻ chủ động (contracts: ProactiveAction.kind). Dùng ở Tổng quan và khi thẻ xuất hiện trong chat.
 * "Hỏi vì sao" mở chat và gửi câu `prompt` do server dựng; "Để sau" ẩn việc trong ngày mô phỏng; "Ít nhắc loại này"
 * ẩn cả loại: hai thứ này chỉ lưu phía giao diện ở phase 2.
 */
export function useProactiveActions(card: ProactiveCardData, appDate: string, onHide?: () => void) {
  const navigate = useNavigate()
  const chat = useChatLauncher()
  return useCallback(
    (a: ProactiveAction) => {
      const jar = a.jar_code ?? card.jar_code
      switch (a.kind) {
        case 'open_forecast':
          chat.close()
          navigate(jar ? `/jars/${jar}` : '/jars')
          break
        case 'ask_why':
          chat.open(a.prompt ?? `Vì sao: ${card.title}`)
          break
        case 'confirm_salary':
          chat.close()
          navigate('/salary')
          break
        case 'review_unclassified':
          chat.close()
          navigate('/activity?review=1')
          break
        case 'open_obligations':
          chat.close()
          navigate('/obligations')
          break
        case 'snooze':
          snoozeCard(nudgeKey(card.kind, card.jar_code), appDate)
          onHide?.()
          break
        case 'mute_kind':
          muteKind(card.kind)
          onHide?.()
          break
      }
    },
    [card, appDate, chat, navigate, onHide],
  )
}
