// Khối mẫu (dữ liệu hư cấu). Dùng cho: trang demo, mock server SSE, scripts/check-blocks.ts.
import { makeForecast, jarBalance } from '../lib/forecast-data.ts'

export function forecastBlock(jarId = 'an_uong', withScenario = false) {
  const f = makeForecast(jarId, withScenario)
  return {
    type: 'forecast_timeline',
    v: 1,
    id: `ft:${jarId}`,
    trace_id: 'tr_8f2c',
    fallback_text: f.runout.date_p50
      ? `Hũ ${f.jar_name} dự kiến cạn ngày ${f.runout.date_p50.slice(8)}/${f.runout.date_p50.slice(5, 7)}, trước kỳ lương.`
      : `Hũ ${f.jar_name} đủ tới kỳ lương.`,
    data: f,
  }
}

export function jarSummaryBlock(jarId = 'an_uong') {
  const names: Record<string, string> = { an_uong: 'Ăn uống', di_lai: 'Đi lại', giai_tri: 'Giải trí' }
  const status = jarId === 'an_uong' ? 'short' : jarId === 'giai_tri' ? 'tight' : 'enough'
  const label = { short: 'Cạn sớm 6 ngày', tight: 'Sát, cạn sớm 2 ngày', enough: 'Đủ tới kỳ lương' }[status]
  return {
    type: 'jar_summary',
    v: 1,
    id: `js:${jarId}`,
    fallback_text: `Hũ ${names[jarId]}: ${label}.`,
    data: {
      jar_id: jarId,
      name: names[jarId],
      balance_vnd: jarBalance(jarId),
      plan_vnd: 4_000_000,
      forecast_level_vnd: status === 'short' ? 300_000 : status === 'tight' ? 700_000 : 1_100_000,
      status,
      status_label: label,
    },
  }
}

export function affordabilityBlock() {
  return {
    type: 'affordability_card',
    v: 1,
    id: 'af:tai_nghe',
    trace_id: 'tr_8f2d',
    fallback_text: 'Mua tai nghe 1,2 triệu bằng Ví Trả Sau: sát, tổng chi phí thật 1.290.000 ₫.',
    data: {
      verdict: 'tight',
      item_label: 'Tai nghe không dây',
      pay_with_label: 'Hũ Giải trí',
      cost_lines: [
        { label: 'Giá sản phẩm', amount_vnd: 1_200_000 },
        { label: 'Phí vận chuyển', amount_vnd: 30_000 },
        { label: 'Phí trả chậm dự kiến', amount_vnd: 60_000 },
      ],
      total_real_cost_vnd: 1_290_000,
      gap: { jar_id: 'giai_tri', amount_vnd: 390_000, when: '2026-12-03' },
      runout_shift_days: -4,
      rules: [
        { id: 'r1', passed: true, label: 'Không vay để chi tiêu hằng ngày' },
        { id: 'r2', passed: false, label: 'Hũ Giải trí còn đủ tới kỳ lương' },
      ],
    },
  }
}

export function confirmBlock() {
  return {
    type: 'confirm',
    v: 1,
    id: 'cf:move_300k',
    trace_id: 'tr_8f2e',
    fallback_text: 'Chuyển 300.000 ₫ từ hũ Giải trí sang hũ Ăn uống. Cần bạn xác nhận.',
    data: {
      interrupt_id: 'int_01',
      action_kind: 'move_between_jars',
      summary: 'Chuyển 300.000 ₫ từ hũ Giải trí sang hũ Ăn uống',
      jars: [
        { jar_id: 'giai_tri', jar_name: 'Giải trí', before_vnd: 900_000, after_vnd: 600_000 },
        { jar_id: 'an_uong', jar_name: 'Ăn uống', before_vnd: 1_900_000, after_vnd: 2_200_000 },
      ],
      runout_before: '2026-11-29',
      runout_after: '2026-12-01',
      reversible: true,
      approve_label: 'Xác nhận chuyển 300.000 ₫',
    },
  }
}

/** Khối lạ: type không có trong registry. */
export function unknownBlock() {
  return { type: 'hologram_3d', v: 1, id: 'x:1', fallback_text: 'Khối mới chưa được app hỗ trợ: dự báo 3D cho hũ Ăn uống.', data: { foo: 1 } }
}

/** Khối sai schema: số dư là chuỗi, thiếu trường bắt buộc. */
export function brokenBlock() {
  return { type: 'jar_summary', v: 1, id: 'js:broken', fallback_text: 'Hũ Ăn uống: số liệu không đọc được.', data: { jar_id: 'an_uong', name: 'Ăn uống', balance_vnd: '1.900.000' } }
}

export function sampleBlocks() {
  return [
    jarSummaryBlock('an_uong'),
    forecastBlock('an_uong', true),
    affordabilityBlock(),
    confirmBlock(),
    unknownBlock(),
    brokenBlock(),
  ] as unknown[]
}
