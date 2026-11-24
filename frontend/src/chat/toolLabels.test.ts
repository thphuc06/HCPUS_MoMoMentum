import { describe, expect, it } from 'vitest'
import { hasToolLabel, toolLabel } from './errors'
import { stepLabel } from '@/features/explain/stepLabels'

// Mọi tool trong hợp đồng Gateway có nhãn tiến độ riêng: thẻ "Yofina đã làm" ở lượt lập lộ trình (đi cảnh 24/11) không còn dòng "Đã xử lý".
const files = import.meta.glob('../../../contracts/tools/*.json', { eager: true, import: 'default' }) as Record<string, unknown>
const TARGETS = ['ledger', 'forecast', 'planner', 'knowledge', 'ingest', 'audit']
const tools = Object.entries(files)
  .filter(([path]) => !path.endsWith('.results.schema.json'))
  .flatMap(([path, list]) => {
    const target = TARGETS.find((t) => path.endsWith(`/${t}.json`)) ?? 'ledger'
    return (list as { name: string }[]).map((t) => `${target}___${t.name}`)
  })

describe('nhãn tiến độ của tool', () => {
  it('đọc được hợp đồng tool, có cả tool phase 4-5', () => {
    expect(tools).toEqual(
      expect.arrayContaining([
        'planner___get_roadmap',
        'planner___optimize_allocation',
        'planner___save_roadmap',
        'forecast___stress_test',
        'forecast___get_resilience_score',
        'forecast___get_behavior_profile',
        'ingest___get_job_status',
        'ingest___start_job',
        'ingest___confirm_rows',
      ]),
    )
  })

  it.each(tools)('%s có nhãn riêng, không rơi về "Đã xử lý"', (name) => {
    expect(hasToolLabel(name)).toBe(true)
    expect(toolLabel(name, 'done')).not.toBe('Đã xử lý')
    expect(toolLabel(name, 'running')).not.toBe('Đang xử lý…')
  })

  it('tool lạ vẫn có nhãn chung', () => {
    expect(toolLabel('ledger___tool_moi', 'done')).toBe('Đã xử lý')
  })
})

describe('nhãn bước của bản ghi lượt', () => {
  it('chặng lộ trình và bước của agent ra chữ tiếng Việt', () => {
    expect(stepLabel('roadmap_draft')).toBe('Lộ trình: phác thảo các bước')
    expect(stepLabel('router')).toBe('Hiểu câu hỏi')
    expect(stepLabel('planner___save_roadmap')).toBe('Đã lưu bản lộ trình')
  })

  it('bước lạ giữ mã', () => {
    expect(stepLabel('buoc_moi')).toBe('buoc_moi')
    expect(stepLabel('ledger___tool_moi')).toBe('ledger___tool_moi')
  })
})
