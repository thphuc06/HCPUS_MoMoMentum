// Sinh định danh phía client: id hội thoại (cũng là session id của Runtime) và traceparent (W3C).

function randomHex(bytes: number): string {
  const buf = new Uint8Array(bytes)
  crypto.getRandomValues(buf)
  return Array.from(buf, (b) => b.toString(16).padStart(2, '0')).join('')
}

export function newUuid(): string {
  return crypto.randomUUID()
}

/** UUID v4 dài 36 ký tự, thỏa yêu cầu session id của Runtime (33 đến 256 ký tự). */
export function newConversationId(): string {
  return newUuid()
}

export type Traceparent = { header: string; traceId: string }

/** `00-<32 hex>-<16 hex>-01`; trace-id và parent-id không được toàn số 0. */
export function newTraceparent(): Traceparent {
  let traceId = randomHex(16)
  while (/^0+$/.test(traceId)) traceId = randomHex(16)
  let spanId = randomHex(8)
  while (/^0+$/.test(spanId)) spanId = randomHex(8)
  return { header: `00-${traceId}-${spanId}-01`, traceId }
}
