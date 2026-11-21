import { useState, type ReactNode } from 'react'
import { FrameContext } from './FrameContext'

/** Khung điện thoại mobile-first (390 px); trên màn rộng căn giữa thành khung 844 px. Xem .phone-frame trong index.css. */
export function PhoneFrame({ children }: { children: ReactNode }) {
  const [frame, setFrame] = useState<HTMLElement | null>(null)
  return (
    <div className="phone-stage">
      <div ref={setFrame} className="phone-frame" data-testid="phone-frame">
        <FrameContext.Provider value={frame}>{children}</FrameContext.Provider>
      </div>
    </div>
  )
}
