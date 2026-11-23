import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ERROR_MESSAGES } from '@/api/errors'
import { RoadmapDiffResponse, RoadmapResponse } from '@/api/roadmapSchemas'
import { restFixture, validBlock } from '@/test/fixtures'
import { backend, bodyOf, callsTo, json, mountApp } from '@/test/mountApp'

const diff = RoadmapDiffResponse.parse(restFixture('RoadmapDiffResponse.v2_v3'))
const proposed = RoadmapResponse.parse(restFixture('RoadmapResponse.minh_v3'))
const active = RoadmapResponse.parse(validBlock('roadmap.active_edited'))
const versions = restFixture('RoadmapVersionsResponse.minh')
const path = `/roadmap/versions/${diff.data.to_version}/decision`

describe('so với bản cũ', () => {
  afterEach(() => vi.unstubAllGlobals())

  it.each([
    ['adopt', 'Dùng bản mới', 'active', 'Đang dùng'],
    ['keep_previous', 'Giữ bản cũ', 'discarded', 'Đã bỏ'],
  ] as const)('gửi %s và hiển thị khối server trả về', async (decision, button, status, label) => {
    const user = userEvent.setup()
    const block = { ...proposed, data: { ...proposed.data, status } }
    const { calls } = mountApp(backend({
      'GET /roadmap': active,
      'GET /roadmap/versions': versions,
      'GET /roadmap/diff': diff,
      [`POST ${path}`]: block,
    }), '/roadmap')
    await user.click(await screen.findByRole('link', { name: 'Có phiên bản mới' }))
    expect(await screen.findByRole('heading', { name: 'So sánh lộ trình · Bản 2 → 3' })).toBeVisible()
    expect(screen.getByText(diff.data.reason.text)).toBeVisible()
    await user.click(screen.getByRole('button', { name: button }))
    expect(await screen.findByRole('heading', { name: 'Lộ trình · Phiên bản 3' })).toBeVisible()
    expect(screen.getByText(label)).toBeVisible()
    expect(callsTo(calls, 'POST', path).map(bodyOf)).toEqual([restFixture(`RoadmapVersionDecisionRequest.${decision}`)])
  })

  it('tắt cả hai nút khi can_adopt=false', async () => {
    const { calls } = mountApp(backend({
      'GET /roadmap/diff': { ...diff, data: { ...diff.data, can_adopt: false, to_status: 'active' } },
    }), '/roadmap/compare')
    expect(await screen.findByRole('button', { name: 'Dùng bản mới' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Giữ bản cũ' })).toBeDisabled()
    expect(callsTo(calls, 'POST', path)).toHaveLength(0)
  })

  it('tải lại diff và báo phiên bản đã thay đổi khi có xung đột', async () => {
    let current = diff
    const { calls } = mountApp(backend({
      'GET /roadmap/diff': () => current,
      [`POST ${path}`]: () => {
        current = { ...diff, data: { ...diff.data, can_adopt: false, to_status: 'active' } }
        return json(409, { error: { code: 'ROADMAP_VERSION_CONFLICT' } })
      },
    }), '/roadmap/compare')
    await userEvent.click(await screen.findByRole('button', { name: 'Dùng bản mới' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(ERROR_MESSAGES.ROADMAP_VERSION_CONFLICT)
    expect(await screen.findByText('Bản mới hiện không thể chọn.')).toBeVisible()
    expect(callsTo(calls, 'GET', '/roadmap/diff')).toHaveLength(2)
  })
})
