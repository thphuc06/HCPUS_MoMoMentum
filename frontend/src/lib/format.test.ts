import { describe, expect, it } from 'vitest'
import {
  formatAppDate,
  formatCountdown,
  formatDateTime,
  formatPercent,
  formatRatioPercent,
  formatSignedVnd,
  formatVnd,
  formatVndAxis,
  formatVndNumber,
  formatVndShort,
  greetingForHour,
  greetingNow,
  vndInWords,
} from './format'
import { addDays, diffDays, formatDayMonth, isIsoDate } from './dates'

const NBSP = ' '

describe('định dạng tiền VND (Intl vi-VN)', () => {
  it('thẻ: chấm nhóm nghìn, NBSP rồi ₫', () => {
    expect(formatVnd(1200000)).toBe(`1.200.000${NBSP}₫`)
    expect(formatVnd(0)).toBe(`0${NBSP}₫`)
    expect(formatVnd(8260000)).toBe(`8.260.000${NBSP}₫`)
    expect(formatVnd(380000)).toBe(`380.000${NBSP}₫`)
  })
  it('số âm dùng dấu trừ Unicode', () => {
    expect(formatVnd(-120000)).toBe(`−120.000${NBSP}₫`)
  })
  it('chỉ phần số', () => {
    expect(formatVndNumber(1234567)).toBe('1.234.567')
  })
  it('dạng ngắn cho câu hỏi và lời giải thích', () => {
    expect(formatVndShort(1200000)).toBe('1,2 triệu')
    expect(formatVndShort(950000)).toBe('950 nghìn')
    expect(formatVndShort(2700000)).toBe('2,7 triệu')
    expect(formatVndShort(1500000000)).toBe('1,5 tỷ')
    expect(formatVndShort(500)).toBe('500')
  })
})

describe('ngày giờ', () => {
  it('ngày mô phỏng không lệch múi giờ', () => {
    expect(formatAppDate('2026-11-21')).toBe('21/11/2026')
    expect(formatAppDate('khong-phai-ngay')).toBe('khong-phai-ngay')
  })
  it('thời điểm thật hiện theo giờ Việt Nam (UTC+7)', () => {
    expect(formatDateTime('2026-11-21T02:14:00Z')).toBe('21/11 09:14')
    expect(formatDateTime('2026-11-21T17:30:00Z')).toBe('22/11 00:30')
  })
  it('đếm ngược mm:ss, không âm', () => {
    expect(formatCountdown(299_000)).toBe('04:59')
    expect(formatCountdown(61_000)).toBe('01:01')
    expect(formatCountdown(-5)).toBe('00:00')
  })
  it('lời chào theo giờ', () => {
    expect(greetingForHour(0)).toBe('Chào buổi tối') // 0 giờ đêm không phải buổi sáng
    expect(greetingForHour(1)).toBe('Chào buổi tối')
    expect(greetingForHour(4)).toBe('Chào buổi tối')
    expect(greetingForHour(5)).toBe('Chào buổi sáng')
    expect(greetingForHour(7)).toBe('Chào buổi sáng')
    expect(greetingForHour(12)).toBe('Chào buổi trưa')
    expect(greetingForHour(16)).toBe('Chào buổi chiều')
    expect(greetingForHour(21)).toBe('Chào buổi tối')
  })
  it('lời chào theo giờ của thiết bị (giờ địa phương của Date)', () => {
    expect(greetingNow(new Date(2026, 10, 22, 1, 0))).toBe('Chào buổi tối')
    expect(greetingNow(new Date(2026, 10, 22, 8, 30))).toBe('Chào buổi sáng')
    expect(greetingNow(new Date(2026, 10, 22, 15, 0))).toBe('Chào buổi chiều')
  })
})

describe('định dạng bổ sung của phase 2', () => {
  it('vndInWords: đọc số tiền bằng chữ', () => {
    expect(vndInWords(250000)).toBe('hai trăm năm mươi nghìn đồng')
    expect(vndInWords(1200000)).toBe('một triệu hai trăm nghìn đồng')
    expect(vndInWords(105)).toBe('một trăm lẻ năm đồng')
    expect(vndInWords(21)).toBe('hai mươi mốt đồng')
    expect(vndInWords(15)).toBe('mười lăm đồng')
    expect(vndInWords(24)).toBe('hai mươi tư đồng')
    expect(vndInWords(1000005)).toBe('một triệu không trăm lẻ năm đồng')
    expect(vndInWords(2500000000)).toBe('hai tỷ năm trăm triệu đồng')
    expect(vndInWords(0)).toBe('không đồng')
  })

  it('formatVndAxis: nhãn trục gọn', () => {
    expect(formatVndAxis(0)).toBe('0')
    expect(formatVndAxis(1500000)).toBe('1,5tr')
    expect(formatVndAxis(-1000000)).toBe('−1tr')
    expect(formatVndAxis(500000)).toBe('500k')
  })

  it('formatSignedVnd: dấu rõ ràng cho tiền vào và ra', () => {
    expect(formatSignedVnd(-65000)).toBe(`−65.000${NBSP}₫`)
    expect(formatSignedVnd(9000000)).toBe(`+9.000.000${NBSP}₫`)
  })

  it('formatRatioPercent và formatPercent', () => {
    expect(formatRatioPercent(0.71)).toBe('71%')
    expect(formatRatioPercent(0.006)).toBe('1%')
    expect(formatPercent(31)).toBe('31%')
    expect(formatPercent(12.5)).toBe('12,5%')
  })
})

describe('dates', () => {
  it('addDays, diffDays và formatDayMonth theo lịch (không lệch múi giờ)', () => {
    expect(addDays('2026-11-21', 14)).toBe('2026-12-05')
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
    expect(diffDays('2026-11-21', '2026-12-05')).toBe(14)
    expect(diffDays('2026-12-05', '2026-11-21')).toBe(-14)
    expect(formatDayMonth('2026-11-23')).toBe('23/11')
    expect(isIsoDate('2026-13-45')).toBe(false)
  })
})
