/**
 * Dữ liệu dựng của composition YofinaDemo. Giai đoạn 2 (ghép đoạn quay thật) CHỈ sửa tệp này, không sửa component.
 *
 * Đơn vị và quy ước
 * - Thời gian trong cảnh app (`clip.*`, `labels`, `voiceAt`, `nightly.at`) là GIÂY CỦA CLIP NGUỒN (cùng đồng hồ với
 *   `public/rec/scene-<n>.events.json`). Hệ thống tự đổi sang thời gian ra sau khi cắt và tua. Khi chưa có clip, giây nguồn
 *   coi như giây của cảnh.
 * - Toạ độ (`box`, `taps`) là CSS px trên viewport 390×844 của app (clip 780×1688 là DPR 2, chia đôi pixel của clip).
 * - Độ dài mỗi cảnh = lời đọc (public/voice/manifest.json, sinh bởi scripts/tts.mjs) + đệm; clip ngắn hơn thì đứng hình
 *   ở khung cuối, dài hơn thì bị cắt ở cuối cảnh. Muốn cảnh dài hơn lời: `minSeconds` hoặc `holdClip: true`.
 * - Số tiền hiện trên hình dạng `380.000 ₫` (hàm `vnd` ở theme.ts).
 */

export type Box = { x: number; y: number; w: number; h: number };
export type Range = { from: number; to: number };

export type ClipEdit = {
  /** Đường dẫn trong public/, ví dụ "rec/scene-1.mp4". Tệp chưa có thì cảnh hiện ô chờ. */
  src: string;
  /** Các đoạn GIỮ LẠI theo thứ tự (giây nguồn); bỏ trống = từ 0 tới hết cảnh. Phần giữa các đoạn bị cắt. */
  keep?: Range[];
  /** Đoạn tua nhanh (giây nguồn, nằm trong `keep`), hiện nhãn "real agent · sped up ×rate". */
  speed?: (Range & { rate: number })[];
  /** Vòng chạm tại (x, y) CSS px ở giây nguồn `t`. */
  taps?: { t: number; x: number; y: number }[];
  /**
   * Spotlight lên phần tử (CSS px, giây nguồn): tối phần ngoài hộp, khung hồng quanh hộp; màn app không bao giờ zoom.
   * Mỗi lúc chỉ một spotlight; giữ ≥ 1,5 s; đặt lúc màn đứng yên (ngoài đoạn cuộn). `to` bỏ trống = tới hết cảnh.
   * `pad` mặc định 7 px.
   */
  spotlights?: { from: number; to?: number; box: Box; pad?: number }[];
};

/** Nhãn dịch cho chữ tiếng Việt trên màn app, hiện ở cột trái. */
export type Label = { vi: string; en: string; from?: number; to?: number };

/** Thẻ "every night at 2 a.m." của cảnh 8, dựng từ public/rec/nightly.json ở giai đoạn 2. */
export type NightlyStats = {
  /** Số lần chạy gần nhất đã xét (rec/nightly.json), thành công, thất bại. */
  runs: number;
  succeeded: number;
  failed: number;
  /** Lần chạy theo lịch gần nhất, dạng hiển thị ("27/11 02:00"), và thời lượng (giây). */
  latest: string;
  latestSeconds: number;
};

export type AppScene = {
  kind: "app";
  /** Số cảnh, khớp tiêu đề `## <số> ·` trong narration.md. */
  id: string;
  features: string[];
  title: string;
  clip: ClipEdit;
  labels?: Label[];
  /** Giây nguồn để bắt đầu từng câu lời (theo thứ tự câu trong manifest); bỏ trống = đọc liền nhau. */
  voiceAt?: (number | null)[];
  minSeconds?: number;
  /** true: cảnh dài ít nhất bằng clip đã cắt và tua. */
  holdClip?: boolean;
  /** Chỉ cảnh 8: thẻ batch đêm; `stats: null` là chưa có số (giai đoạn 1). */
  nightly?: { at?: number; stats: NightlyStats | null };
};

export type IntroScene = {
  kind: "intro";
  id: string;
  /** Số dư hũ Ăn uống và số ngày tới lương hiện trên hình (khớp lời cảnh 0). */
  balance: number;
  paydayDays: number;
  spends: { label: string; amount: number }[];
};
export type ArchScene = { kind: "arch"; id: string };
export type EndScene = { kind: "end"; id: string; title: string; tagline: string };
export type SceneData = IntroScene | AppScene | ArchScene | EndScene;

export const FEATURE_NAMES: Record<string, string> = {
  F1: "Jar forecast",
  F2: "What-if",
  F3: "Check before paying",
  F4: "Resilience & shocks",
  F5: "Adaptive plan",
  F6: "Bring outside data",
  F7: "Proactive brief",
};

const rec = (n: number | string) => `rec/scene-${n}.mp4`;
const tapAt = (t: number, b: Box) => ({ t, x: b.x + b.w / 2, y: b.y + b.h / 2 });

// Giai đoạn 2, bản quay 2 (27/11, cuộn từng bước 30 fps). Mốc lấy từ public/rec/scene-<n>.events.json; hộp spotlight đo
// trên khung hình lúc màn đứng yên. Quy tắc: không tua, không cắt giữa đoạn cuộn {type:"scroll", stepped:true} (kiểm bằng
// scripts/check-edit.mjs); chỉ tua lúc chờ agent, và chỉ kéo chậm (rate < 1) lúc màn đứng yên. Không zoom màn app.
export const SCENES: SceneData[] = [
  {
    kind: "intro",
    id: "0",
    balance: 380000,
    paydayDays: 14,
    spends: [
      { label: "Morning coffee", amount: 45000 },
      { label: "Lunch", amount: 55000 },
      { label: "Ride home", amount: 38000 },
      { label: "Milk tea", amount: 42000 },
      { label: "Dinner with Huy", amount: 200000 },
    ],
  },
  {
    kind: "app",
    id: "1",
    features: ["F1", "F7"],
    title: "Which jar runs dry,\nand when",
    clip: {
      src: rec(1),
      // Tổng quan, cuộn tới thẻ hũ cạn rồi giữ thẻ (màn đứng yên, kéo chậm cho đủ hai câu); Hồ sơ: nhận xét hành vi.
      keep: [
        { from: 1.5, to: 9.267 },
        { from: 34.6, to: 40.8 },
      ],
      speed: [{ from: 4.4, to: 9.2, rate: 0.44 }],
      spotlights: [
        { from: 6.8, to: 9.2, box: { x: 24, y: 2, w: 346, h: 166 } },
        { from: 38.0, box: { x: 16, y: 205, w: 358, h: 245 } },
      ],
    },
    labels: [
      { vi: "Hũ Ăn uống dự kiến cạn ngày 23/11", en: "Food jar expected to run dry on 23/11", from: 1.5, to: 9.267 },
      { vi: "12 ngày hũ trống trước kỳ lương", en: "12 empty days before payday", from: 4.3, to: 9.267 },
      { vi: "Cạn 23/11 · Lương 05/12", en: "Dry 23/11 · Payday 05/12", from: 4.3, to: 9.267 },
      { vi: "Nhận xét hành vi", en: "Spending habits", from: 34.6 },
      { vi: "Việc nên làm", en: "Suggested next step", from: 34.6 },
    ],
  },
  {
    kind: "app",
    id: "2",
    features: ["F3"],
    title: "Ask before\nyou pay",
    clip: {
      src: rec(2),
      // Hết đoạn thì đứng ở khung cuối: thẻ "Dùng tiền hũ Giải trí · Đủ" và dòng "Hụt: hũ Ăn uống…".
      keep: [{ from: 4.0, to: 15.4 }],
      speed: [{ from: 9.2, to: 11.7, rate: 2 }],
      taps: [tapAt(6.6, { x: 16, y: 780, w: 302, h: 52 }), tapAt(9.1, { x: 326, y: 782, w: 48, h: 48 })],
      spotlights: [
        { from: 13.4, to: 14.9, box: { x: 12, y: 670, w: 350, h: 50 } },
        { from: 14.9, box: { x: 34, y: 225, w: 322, h: 72 } },
      ],
    },
    labels: [
      { vi: "cafe 55k có ổn không", en: "is a 55k coffee okay?", from: 7.1, to: 11.8 },
      { vi: "Hụt", en: "Short", from: 11.8 },
      { vi: "Dùng tiền hũ Giải trí", en: "Use the entertainment jar", from: 11.8 },
      { vi: "Đủ", en: "Enough", from: 11.8 },
    ],
  },
  {
    kind: "app",
    id: "3",
    features: ["F2"],
    title: "What if…\nthen decide",
    clip: {
      src: rec(3),
      // Gõ, chờ, thẻ tác động; tua chờ phương án; bỏ cuộn ngược 31–45 s; phương án gợi ý (giữ, kéo chậm), một đoạn cuộn
      // trọn tới "Chuyển bù từ Dự phòng"; từ 67,0 (đầu đoạn cuộn): thẻ phương án, chọn, thẻ xác nhận, "Không", "Đã hủy".
      keep: [
        { from: 1.0, to: 29.4 },
        { from: 59.633, to: 63.667 },
        { from: 67.0, to: 74.4 },
      ],
      speed: [
        { from: 18.4, to: 29.4, rate: 10 },
        { from: 59.633, to: 60.767, rate: 0.6 },
      ],
      spotlights: [
        { from: 12.4, to: 18.4, box: { x: 28, y: 340, w: 334, h: 100 } },
        { from: 59.633, to: 60.767, box: { x: 32, y: 540, w: 326, h: 180 } },
        { from: 68.3, to: 69.8, box: { x: 32, y: 172, w: 326, h: 225 } },
        { from: 71.2, to: 73.45, box: { x: 16, y: 344, w: 358, h: 390 } },
      ],
      taps: [
        tapAt(2.6, { x: 16, y: 780, w: 302, h: 52 }),
        tapAt(6.4, { x: 326, y: 782, w: 48, h: 48 }),
        tapAt(69.8, { x: 45, y: 341, w: 68, h: 44 }),
        tapAt(73.5, { x: 34, y: 668, w: 322, h: 48 }),
      ],
    },
    labels: [
      { vi: "Ví Trả Sau", en: "Buy now, pay later", from: 3.0, to: 11.8 },
      { vi: "Hũ Nghĩa vụ · Hụt 1.167.673 ₫", en: "Obligations jar · short 1.167.673 ₫", from: 11.8, to: 59.6 },
      { vi: "Hoãn mua, chờ hũ đủ tiền · Gợi ý", en: "Wait until the jar has enough · Suggested", from: 59.6, to: 67.0 },
      { vi: "Chuyển bù từ Dự phòng vào Giải trí · Sát", en: "Top up from the emergency fund · Tight", from: 62.0 },
      { vi: "Dự phòng 2.700.000 → 2.260.000 ₫", en: "Emergency fund 2.700.000 → 2.260.000 ₫", from: 71.2 },
      { vi: "Đã hủy. Chưa có gì được ghi.", en: "Cancelled. Nothing was written.", from: 73.9 },
    ],
  },
  {
    kind: "app",
    id: "4",
    features: ["F4"],
    title: "A shock test,\nscored",
    clip: {
      src: rec(4),
      keep: [{ from: 5.6, to: 14.6 }],
      taps: [tapAt(7.9, { x: 16, y: 564.6, w: 358, h: 48 })],
      spotlights: [
        { from: 10.0, to: 12.25, box: { x: 100, y: 165, w: 200, h: 115 } },
        { from: 12.25, box: { x: 24, y: 330, w: 345, h: 80 } },
      ],
    },
    labels: [
      { vi: "Điểm chống chịu", en: "Resilience score" },
      { vi: "Mất việc 2 tháng", en: "Lose job for 2 months" },
      { vi: "Trụ được 26 ngày", en: "Holds out 26 days", from: 9.5 },
      { vi: "Yếu", en: "Weak", from: 9.5 },
    ],
  },
  {
    kind: "app",
    id: "5",
    features: ["F5"],
    title: "A plan built\nfrom a goal",
    clip: {
      src: rec(5),
      // Gõ, hỏi lại, chạm "Lập bản mới"; tua chờ lộ trình (34 s); tóm tắt và hai đoạn cuộn lên đầu lộ trình (trọn), giữ
      // đầu lộ trình (kéo chậm) để màn so sánh hiện sau câu "Safety rules…"; từ cuối đoạn cuộn 73,6–75,0: chạm "Dùng bản
      // mới", cuộn về đầu, "Đã dùng".
      keep: [
        { from: 7.2, to: 57.8 },
        { from: 75.0, to: 79.6 },
      ],
      speed: [
        { from: 10.4, to: 13.3, rate: 2 },
        { from: 16.3, to: 50.1, rate: 40 },
        { from: 56.1, to: 57.8, rate: 0.6 },
        { from: 75.6, to: 76.9, rate: 3 },
      ],
      taps: [
        tapAt(10.3, { x: 326, y: 782, w: 48, h: 48 }),
        tapAt(15.8, { x: 32, y: 503, w: 109.3, h: 44 }),
        tapAt(75.3, { x: 16, y: 672, w: 119.9, h: 44 }),
      ],
      spotlights: [
        { from: 13.4, to: 15.8, box: { x: 16, y: 367, w: 358, h: 224 } },
        { from: 50.2, to: 52.0, box: { x: 12, y: 600, w: 366, h: 80 } },
        { from: 56.1, to: 57.8, box: { x: 24, y: 190, w: 340, h: 80 } },
      ],
    },
    labels: [
      { vi: "Mình muốn để dành 5 triệu trước Tết", en: "I want to save 5 million before Tet", from: 8.0, to: 13.4 },
      { vi: "Lập bản mới hay xem bản đang dùng?", en: "New plan, or view the current one?", from: 13.4, to: 50.1 },
      { vi: "3 giai đoạn, 4 bước", en: "3 stages, 4 steps", from: 50.1 },
      { vi: "Khả thi sau điều chỉnh", en: "Feasible after adjustment", from: 56.2 },
      { vi: "Dùng bản mới", en: "Adopt the new plan", from: 75.0 },
    ],
  },
  {
    kind: "app",
    id: "6",
    features: ["F5", "F6"],
    title: "The plan adapts\non its own",
    clip: {
      src: rec(6),
      // Không spotlight vào dòng lý do do model viết có số mục tiêu lệch (màn so sánh, y khoảng 350–395).
      keep: [
        { from: 9.2, to: 32.667 },
        { from: 52.2, to: 54.6 },
        { from: 56.2, to: 57.4 },
        { from: 66.3, to: 90.4 },
        { from: 94.3, to: 96.367 },
        { from: 111.6, to: 113.4 },
        { from: 120.4, to: 125.6 },
      ],
      speed: [
        { from: 14.4, to: 16.7, rate: 6 },
        { from: 17.2, to: 31.3, rate: 40 },
        { from: 31.4, to: 32.667, rate: 0.7 },
        { from: 66.3, to: 87.7, rate: 15 },
        { from: 122.2, to: 124.6, rate: 2 },
      ],
      taps: [
        tapAt(9.4, { x: 32, y: 690, w: 326, h: 44 }),
        tapAt(11.9, { x: 32, y: 282, w: 326, h: 56 }),
        tapAt(16.8, { x: 34, y: 610, w: 322, h: 48 }),
        tapAt(54.1, { x: 16, y: 626, w: 358, h: 48 }),
        tapAt(90.2, { x: 16, y: 404.6, w: 358, h: 144 }),
        tapAt(123.1, { x: 326, y: 782, w: 48, h: 48 }),
      ],
      spotlights: [
        { from: 31.4, to: 32.667, box: { x: 16, y: 80, w: 358, h: 180 } },
        { from: 52.3, to: 54.05, box: { x: 30, y: 375, w: 330, h: 115 } },
        { from: 87.8, to: 90.2, box: { x: 16, y: 404.6, w: 358, h: 144 } },
        { from: 94.3, to: 96.367, box: { x: 16, y: 88, w: 358, h: 105 } },
        { from: 111.6, to: 113.4, box: { x: 20, y: 445, w: 350, h: 100 } },
        { from: 124.7, box: { x: 16, y: 245, w: 358, h: 120 } },
      ],
    },
    labels: [
      { vi: "Tải sao kê CSV", en: "Upload CSV statement", from: 9.2, to: 31.4 },
      { vi: "Đọc được 32 dòng · Ăn uống", en: "32 rows read · Food jar", from: 31.4, to: 66.3 },
      { vi: "Xác nhận thêm 32 dòng", en: "Confirm adding 32 rows", from: 52.2, to: 66.3 },
      { vi: "Có phiên bản mới", en: "New version available", from: 66.3, to: 120.4 },
      { vi: "So với bản cũ · Vì sao có bản này?", en: "Compare with previous · Why this version?", from: 94.3, to: 120.4 },
      { vi: "Ngoài phạm vi hiện tại", en: "Outside current scope", from: 124.7 },
    ],
    voiceAt: [null, null, 31.45, null, null, null, null],
  },
  {
    kind: "app",
    id: "7",
    features: ["F6"],
    title: "Receipt in,\npersonal data out",
    clip: {
      src: rec(7),
      keep: [{ from: 5.6, to: 24.0 }],
      speed: [
        { from: 8.3, to: 10.85, rate: 3 },
        { from: 11.7, to: 20.2, rate: 12 },
      ],
      taps: [
        tapAt(5.8, { x: 32, y: 216, w: 326, h: 56 }),
        tapAt(9.9, { x: 34, y: 556, w: 20, h: 20 }),
        tapAt(10.9, { x: 34, y: 610, w: 322, h: 48 }),
      ],
      spotlights: [{ from: 20.6, box: { x: 20, y: 128, w: 350, h: 112 } }],
    },
    labels: [
      { vi: "Chọn ảnh có sẵn", en: "Pick an existing photo", from: 5.6, to: 11.7 },
      { vi: "…tên người khác được che trước khi lưu", en: "…other people's names are masked before saving", from: 8.4, to: 20.2 },
      { vi: "Đã che: tên", en: "Masked: name", from: 20.3 },
      { vi: "Đã che 1 thông tin cá nhân", en: "1 personal detail masked", from: 20.3 },
    ],
  },
  {
    kind: "app",
    id: "8",
    features: [],
    title: "Explainable,\nrefreshed nightly",
    clip: {
      src: rec(8),
      keep: [{ from: 1.0, to: 12.6 }],
      taps: [tapAt(1.3, { x: 283.4, y: 268, w: 74.6, h: 44 }), tapAt(4.6, { x: 28, y: 776, w: 125.5, h: 44 })],
      spotlights: [{ from: 8.1, box: { x: 16, y: 270, w: 358, h: 130 } }],
    },
    labels: [
      { vi: "Vì sao · Luật đã kiểm · Đạt", en: "Why · Rules checked · Passed", from: 1.0, to: 4.6 },
      { vi: "Chi tiết kỹ thuật · Lượt gọi mô hình", en: "Technical details · Model calls", from: 4.6 },
    ],
    // rec/nightly.json: 10 lần chạy gần nhất (có cả lần chạy tay), 9 thành công, 1 thất bại (24/11 02:00).
    nightly: { stats: { runs: 10, succeeded: 9, failed: 1, latest: "27/11 02:00", latestSeconds: 32.5 } },
  },
  { kind: "arch", id: "9" },
  { kind: "end", id: "10", title: "Yofina Foresight", tagline: "See which jar runs dry, before it does." },
];
