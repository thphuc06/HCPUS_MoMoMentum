import { createCn } from 'cn/config'

// `cn` (tương thích tailwind-merge) cần biết các tên chữ/bo góc/bóng tự đặt ở index.css (@theme); nếu không,
// `text-subtitle` bị coi là MÀU chữ và xóa mất `text-primary-foreground` đứng trước nó.
export const cn = createCn({
  extend: {
    classGroups: {
      'font-size': [{ text: ['display', 'amount', 'title', 'section', 'subtitle', 'body', 'small', 'note'] }],
      rounded: [{ rounded: ['card', 'sheet'] }],
      shadow: [{ shadow: ['card', 'sheet'] }],
    },
  },
})
