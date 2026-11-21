import { createContext, useContext } from 'react'

/** Phần tử khung điện thoại: nơi sheet và hộp thoại được portal vào để bám theo khung (không tràn ra viewport). */
export const FrameContext = createContext<HTMLElement | null>(null)

export function usePhoneFrame(): HTMLElement | null {
  return useContext(FrameContext)
}
