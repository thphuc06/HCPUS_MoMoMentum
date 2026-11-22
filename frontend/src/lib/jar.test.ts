import { describe, expect, it } from 'vitest'
import { jarForecastLevel } from './jar'

// Vạch "dự báo" trên hũ: từ `forecast_floor_vnd` do server tính (có thể âm), cùng mức tham chiếu với mực nước.
describe('jarForecastLevel', () => {
  const MAX = 4_000_000

  it('vạch theo số dư dự báo thấp nhất tới kỳ lương so với mức tham chiếu (hũ đầy nhất, hoặc mục tiêu nếu có)', () => {
    expect(jarForecastLevel({ balance_vnd: 2_000_000, forecast_floor_vnd: 1_000_000 }, MAX)).toBeCloseTo(0.25)
    expect(jarForecastLevel({ balance_vnd: 2_000_000, goal_vnd: 8_000_000, forecast_floor_vnd: 2_000_000 }, MAX)).toBeCloseTo(0.25)
    expect(jarForecastLevel({ balance_vnd: 2_000_000, forecast_floor_vnd: 9_000_000 }, MAX)).toBe(1) // không vượt đỉnh hũ
  })

  it('số dư dự báo âm hoặc bằng 0: vẽ như cạn (mức 0), không tràn khỏi hũ', () => {
    expect(jarForecastLevel({ balance_vnd: 380_000, forecast_floor_vnd: -1_047_295, status: 'short' }, MAX)).toBe(0)
    expect(jarForecastLevel({ balance_vnd: 380_000, forecast_floor_vnd: 0 }, MAX)).toBe(0)
  })

  it('server chưa trả số dự báo: chỉ vạch cạn cho hũ báo hụt có ngày cạn, còn lại không vẽ vạch (không bịa)', () => {
    expect(jarForecastLevel({ balance_vnd: 380_000, status: 'short', runout_date: '2026-11-23' }, MAX)).toBe(0)
    expect(jarForecastLevel({ balance_vnd: 380_000, status: 'short' }, MAX)).toBeNull()
    expect(jarForecastLevel({ balance_vnd: 380_000, status: 'ok' }, MAX)).toBeNull()
    expect(jarForecastLevel({ balance_vnd: 380_000 }, MAX)).toBeNull()
  })
})
