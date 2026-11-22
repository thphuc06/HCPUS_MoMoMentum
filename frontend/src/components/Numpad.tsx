import { Delete } from 'lucide-react'

// Figma Numpad (14:450): 3×4, hàng cuối "000", "0", xóa. Phím cao >= 52 px (vùng chạm >= 44 px).
const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '000', '0', 'del'] as const

export function Numpad({ onDigit, onDelete }: { onDigit: (d: string) => void; onDelete: () => void }) {
  return (
    <div className="grid grid-cols-3 gap-y-1 px-4" role="group" aria-label="Bàn phím số">
      {KEYS.map((k) =>
        k === 'del' ? (
          <button key={k} type="button" aria-label="Xóa chữ số cuối" onClick={onDelete} className="grid h-14 place-items-center text-ink active:bg-surface-2 rounded-2xl">
            <Delete className="size-6" aria-hidden />
          </button>
        ) : (
          <button key={k} type="button" onClick={() => onDigit(k)} className="h-14 rounded-2xl text-title font-semibold text-ink active:bg-surface-2">
            {k}
          </button>
        ),
      )}
    </div>
  )
}
