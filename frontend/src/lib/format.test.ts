import { describe, expect, it } from 'vitest'
import { formatAppDate, formatCountdown, formatDateTime, formatVnd, formatVndNumber, formatVndShort, greetingForHour } from './format'

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
    expect(greetingForHour(7)).toBe('Chào buổi sáng')
    expect(greetingForHour(12)).toBe('Chào buổi trưa')
    expect(greetingForHour(16)).toBe('Chào buổi chiều')
    expect(greetingForHour(21)).toBe('Chào buổi tối')
  })
})
