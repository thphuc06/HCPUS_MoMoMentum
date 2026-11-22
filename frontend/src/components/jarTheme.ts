import { Bus, CircleHelp, Gamepad2, Headphones, Inbox, Landmark, Plane, Receipt, Shield, Umbrella, Utensils, Wallet, Zap } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

// Khóa màu và biểu tượng hũ do server gửi (contracts: color_key, icon_key). Frontend ánh xạ sang biến màu
// thiết kế (Figma --jar-*) và JarIcon; khóa lạ rơi về màu/biểu tượng trung tính, không làm vỡ giao diện.

const COLOR_VAR: Record<string, string> = {
  violet: '--jar-an-uong',
  sky: '--jar-di-lai',
  brown: '--jar-hoa-don',
  orchid: '--jar-giai-tri',
  teal: '--jar-du-lich',
  blue: '--jar-du-phong',
  slate: '--jar-nghia-vu',
  // Hũ hệ thống (Tiền vào khác, Chưa phân loại): màu trung tính.
  gray: '--text-secondary',
}

const ICONS: Record<string, LucideIcon> = {
  utensils: Utensils,
  bus: Bus,
  receipt: Receipt,
  gamepad: Gamepad2,
  headphones: Headphones,
  plane: Plane,
  shield: Shield,
  umbrella: Umbrella,
  wallet: Wallet,
  landmark: Landmark,
  zap: Zap,
  // Hũ hệ thống: Tiền vào khác (inbox), Chưa phân loại (help).
  inbox: Inbox,
  help: CircleHelp,
}

export function jarColor(colorKey: string): string {
  return `var(${COLOR_VAR[colorKey] ?? '--jar-nghia-vu'})`
}

export function jarIconFor(iconKey: string): LucideIcon {
  return ICONS[iconKey] ?? Wallet
}
