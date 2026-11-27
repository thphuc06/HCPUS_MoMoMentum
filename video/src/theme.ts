import { loadFont } from "@remotion/google-fonts/BeVietnamPro";

const { fontFamily } = loadFont("normal", {
  weights: ["400", "600", "800"],
  subsets: ["vietnamese", "latin"],
});

export const font = fontFamily;

// Cùng tông với frontend/src/index.css (brand-primary, brand-deep, brand-vivid)
export const c = {
  brand: "#c8207e",
  brandDeep: "#a50064",
  brandVivid: "#d82d8b",
  night: "#14101c",
  nightSoft: "#231a30",
  paper: "#fff7fb",
  ink: "#1d1424",
  muted: "#8a7b93",
  danger: "#e5484d",
  ok: "#2f9e6b",
  blue: "#3050c8",
};

export const vnd = (n: number) =>
  `${Math.round(n).toLocaleString("vi-VN").replace(/,/g, ".")} ₫`;
