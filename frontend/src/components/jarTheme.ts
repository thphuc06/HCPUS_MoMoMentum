import { Bus, Gamepad2, Headphones, Landmark, Plane, Receipt, Shield, Umbrella, Utensils, Wallet } from 'lucide-react'
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
}

export function jarColor(colorKey: string): string {
  return `var(${COLOR_VAR[colorKey] ?? '--jar-nghia-vu'})`
}

export function jarIconFor(iconKey: string): LucideIcon {
  return ICONS[iconKey] ?? Wallet
}
