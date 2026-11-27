import React from "react";
import { c } from "./theme";

// Khung điện thoại chung chung, không logo hay tên ứng dụng thật nào.
// Mặc định khung 430×880 (Story); YofinaDemo truyền kích thước theo tỉ lệ viewport 390×844 của app và tắt tai thỏ.
export const Phone: React.FC<{
  children: React.ReactNode;
  style?: React.CSSProperties;
  width?: number;
  height?: number;
  bezel?: number;
  radius?: number;
  notch?: boolean;
  screenBackground?: string;
}> = ({
  children,
  style,
  width = 430,
  height = 880,
  bezel = 16,
  radius = 64,
  notch = true,
  screenBackground = c.paper,
}) => (
  <div
    style={{
      width,
      height,
      borderRadius: radius,
      background: "#0b0910",
      padding: bezel, // khi render, width/height là kích thước khung ngoài (box-sizing border-box), màn = trừ 2 × bezel
      boxShadow: "0 40px 120px rgba(200,32,126,0.35), 0 0 0 2px #2c2236",
      ...style,
    }}
  >
    <div
      style={{
        width: "100%",
        height: "100%",
        borderRadius: radius - bezel + 2,
        overflow: "hidden",
        background: screenBackground,
        position: "relative",
      }}
    >
      {notch && (
        <div
          style={{
            position: "absolute",
            top: 14,
            left: "50%",
            translate: "-50% 0",
            width: 120,
            height: 32,
            borderRadius: 20,
            background: "#0b0910",
            zIndex: 5,
          }}
        />
      )}
      {children}
    </div>
  </div>
);
