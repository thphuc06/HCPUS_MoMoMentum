// Thu nhỏ ảnh ngay trên máy người dùng trước khi tải lên màn Nạp dữ liệu.
//
// Ảnh chụp bằng máy ảnh điện thoại thường 4 đến 12 MB, vượt giới hạn ảnh của server (3,75 MB, theo giới hạn ảnh của Bedrock).
// Model đọc ảnh cũng tự thu ảnh về cạnh dài khoảng 1.568 px (Claude Sonnet 4.6) hoặc 2.576 px (Claude 4.7 trở lên) trước khi đọc
// (https://platform.claude.com/docs/en/build-with-claude/vision), nên gửi ảnh gốc không đọc rõ hơn, chỉ tải chậm hơn và bị từ chối.
// Vẽ lại qua canvas còn bỏ EXIF (gồm vị trí GPS) khỏi tệp gửi đi.

/** Cạnh dài tối đa sau khi thu nhỏ: đủ cho mức đọc cao nhất của model hiện có. */
export const IMAGE_MAX_EDGE_PX = 2560
/** Ảnh nhỏ hơn mức này và đúng định dạng thì giữ nguyên (ảnh chụp màn hình sao kê giữ nét). */
export const KEEP_ORIGINAL_BELOW_BYTES = 1_500_000
/** Các mức chất lượng JPEG thử lần lượt tới khi vừa giới hạn. */
export const JPEG_QUALITIES = [0.85, 0.75, 0.65] as const
/** Mỗi lần vẫn quá lớn ở chất lượng thấp nhất thì thu cạnh dài thêm theo hệ số này (tối đa ba lần). */
const EDGE_STEP = 0.8
const MAX_EDGE_ROUNDS = 3

export type DecodedImage = { width: number; height: number; source: CanvasImageSource; close?: () => void }

export type ImageCodec = {
  /** Giải mã tệp, xoay theo EXIF. Ném lỗi nếu trình duyệt không đọc được định dạng (ví dụ HEIC trên Chrome). */
  decode: (file: Blob) => Promise<DecodedImage>
  /** Vẽ ảnh ở kích thước cho trước rồi mã hóa JPEG với chất lượng cho trước. */
  encodeJpeg: (img: DecodedImage, width: number, height: number, quality: number) => Promise<Blob>
}

const browserCodec: ImageCodec = {
  async decode(file) {
    const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' })
    return { width: bmp.width, height: bmp.height, source: bmp, close: () => bmp.close() }
  },
  async encodeJpeg(img, width, height, quality) {
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('canvas 2d không dùng được')
    ctx.fillStyle = '#ffffff' // ảnh PNG có nền trong suốt: JPEG không có kênh alpha
    ctx.fillRect(0, 0, width, height)
    ctx.imageSmoothingQuality = 'high'
    ctx.drawImage(img.source, 0, 0, width, height)
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality))
    if (!blob) throw new Error('không mã hóa được JPEG')
    return blob
  },
}

function fitWithin(width: number, height: number, maxEdge: number): { width: number; height: number } {
  const scale = Math.min(1, maxEdge / Math.max(width, height))
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) }
}

function jpegName(name: string): string {
  const base = name.replace(/\.[^./\\]+$/, '')
  return `${base || 'anh'}.jpg`
}

/**
 * Ảnh sẵn sàng để tải lên: giữ nguyên nếu đã nhỏ và đúng định dạng; không thì thu cạnh dài về `IMAGE_MAX_EDGE_PX` và lưu JPEG,
 * giảm chất lượng rồi kích thước tới khi nhỏ hơn `maxBytes`. Không đọc được ảnh thì trả tệp gốc (bước kiểm tra sau báo lỗi rõ ràng);
 * nén xong vẫn quá lớn thì trả bản nhỏ nhất đã có (server vẫn kiểm lại).
 */
export async function prepareImage(
  file: File,
  maxBytes: number,
  allowedTypes: readonly string[],
  codec: ImageCodec = browserCodec,
): Promise<File> {
  if (file.size > 0 && file.size <= Math.min(KEEP_ORIGINAL_BELOW_BYTES, maxBytes) && allowedTypes.includes(file.type)) return file
  let img: DecodedImage
  try {
    img = await codec.decode(file)
  } catch {
    return file
  }
  try {
    const target = Math.floor(maxBytes * 0.95)
    let edge = Math.min(IMAGE_MAX_EDGE_PX, Math.max(img.width, img.height))
    let smallest: Blob | null = null
    for (let round = 0; round < MAX_EDGE_ROUNDS; round++) {
      const size = fitWithin(img.width, img.height, edge)
      for (const q of JPEG_QUALITIES) {
        const blob = await codec.encodeJpeg(img, size.width, size.height, q)
        if (!smallest || blob.size < smallest.size) smallest = blob
        if (blob.size <= target) return new File([blob], jpegName(file.name), { type: 'image/jpeg', lastModified: file.lastModified })
      }
      edge = Math.round(edge * EDGE_STEP)
    }
    return smallest ? new File([smallest], jpegName(file.name), { type: 'image/jpeg', lastModified: file.lastModified }) : file
  } catch {
    return file
  } finally {
    img.close?.()
  }
}
