import { describe, expect, it, vi } from 'vitest'
import { IMAGE_MAX_EDGE_PX, prepareImage, type ImageCodec } from './compress'

const TYPES = ['image/png', 'image/jpeg', 'image/webp'] as const
const LIMIT = 3_750_000

function fileOf(size: number, type: string, name = 'anh.jpg'): File {
  return new File([new Uint8Array(size)], name, { type })
}

/** Codec giả: ảnh `w`x`h`; kích thước JPEG tỉ lệ với số điểm ảnh và chất lượng (đủ để kiểm vòng lặp, không cần canvas). */
function fakeCodec(w: number, h: number, bytesPerPixelAtQ1 = 1.2) {
  const encodes: Array<{ width: number; height: number; quality: number }> = []
  const close = vi.fn()
  const codec: ImageCodec = {
    decode: async () => ({ width: w, height: h, source: {} as CanvasImageSource, close }),
    encodeJpeg: async (_img, width, height, quality) => {
      encodes.push({ width, height, quality })
      return new Blob([new Uint8Array(Math.round(width * height * bytesPerPixelAtQ1 * quality))], { type: 'image/jpeg' })
    },
  }
  return { codec, encodes, close }
}

describe('prepareImage', () => {
  it('ảnh nhỏ đúng định dạng giữ nguyên, không giải mã', async () => {
    const decode = vi.fn()
    const f = fileOf(900_000, 'image/png', 'saoke.png')
    const out = await prepareImage(f, LIMIT, TYPES, { decode, encodeJpeg: vi.fn() } as unknown as ImageCodec)
    expect(out).toBe(f)
    expect(decode).not.toHaveBeenCalled()
  })

  it('ảnh máy ảnh 12 MP 6 MB: thu cạnh dài về 2560 px, JPEG, nhỏ hơn giới hạn, đúng tỉ lệ', async () => {
    const { codec, encodes, close } = fakeCodec(4000, 3000)
    const out = await prepareImage(fileOf(6_000_000, 'image/jpeg', 'IMG_1234.JPG'), LIMIT, TYPES, codec)
    expect(out.type).toBe('image/jpeg')
    expect(out.name).toBe('IMG_1234.jpg')
    expect(out.size).toBeLessThanOrEqual(LIMIT)
    expect(encodes[0]).toEqual({ width: IMAGE_MAX_EDGE_PX, height: 1920, quality: 0.85 })
    expect(close).toHaveBeenCalled()
  })

  it('ảnh dọc rất dài (sao kê cuộn): cạnh dài là chiều cao', async () => {
    const { codec, encodes } = fakeCodec(1080, 8000)
    await prepareImage(fileOf(5_000_000, 'image/png', 'dai.png'), LIMIT, TYPES, codec)
    expect(encodes[0]!.height).toBe(IMAGE_MAX_EDGE_PX)
    expect(encodes[0]!.width).toBe(Math.round(1080 * (IMAGE_MAX_EDGE_PX / 8000)))
  })

  it('vẫn quá lớn thì hạ chất lượng rồi thu nhỏ thêm tới khi vừa', async () => {
    const { codec, encodes } = fakeCodec(4000, 3000, 1.6)
    const out = await prepareImage(fileOf(9_000_000, 'image/jpeg'), LIMIT, TYPES, codec)
    expect(out.size).toBeLessThanOrEqual(LIMIT * 0.95)
    expect(encodes.map((e) => e.quality).slice(0, 3)).toEqual([0.85, 0.75, 0.65])
    expect(encodes.length).toBeGreaterThan(1)
  })

  it('ảnh nhỏ nhưng định dạng khác (HEIC) đọc được thì đổi sang JPEG', async () => {
    const { codec } = fakeCodec(1200, 900)
    const out = await prepareImage(fileOf(800_000, 'image/heic', 'a.heic'), LIMIT, TYPES, codec)
    expect(out.type).toBe('image/jpeg')
    expect(out.name).toBe('a.jpg')
  })

  it('trình duyệt không đọc được ảnh thì trả tệp gốc (bước kiểm tra sau báo lỗi rõ ràng)', async () => {
    const f = fileOf(6_000_000, 'image/heic', 'a.heic')
    const codec: ImageCodec = { decode: async () => Promise.reject(new Error('không hỗ trợ')), encodeJpeg: vi.fn() }
    expect(await prepareImage(f, LIMIT, TYPES, codec)).toBe(f)
  })
})
