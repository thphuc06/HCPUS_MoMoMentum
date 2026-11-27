# Lời dẫn video demo (bản 3: đã duyệt 27/11, sửa theo lượt quay thật, xem `public/rec/REPORT.md`)

Giọng: Amazon Polly, engine `generative`, voice `Tiffany` (en-US), Region `ap-southeast-1`. Mỗi câu một tệp âm thanh; độ dài cảnh theo độ dài lời.
Phụ đề tiếng Anh in vào hình theo từng câu. Sản phẩm trả sau gọi chung là "buy now, pay later" (không dùng tên sản phẩm thật).
Số trong ngoặc vuông [..] lấy lại từ màn hình của lượt quay thật trước khi tạo giọng (không đọc số khác màn hình).
Đoạn chờ agent tua nhanh, gắn nhãn "real agent · sped up".

Phủ F1–F7: F1 cảnh 1; F7 cảnh 1; F3 cảnh 2; F2 cảnh 3; quyết định + xác nhận trước khi ghi cảnh 3; F4 cảnh 4; F5 dựng từ mục tiêu cảnh 5; F5 tự đổi + F6 sao kê cảnh 6; F6 ảnh + che PII cảnh 7; minh bạch + batch đêm cảnh 8; sơ đồ hệ thống cảnh 9.

Khoảng 400 từ cộng 55 từ của sơ đồ (cảnh 9, mới); độ dài thật đo từ tệp giọng ở `public/voice/manifest.json`.
Quy ước cho script `scripts/tts.mjs`: mỗi tiêu đề `## <số> · …` là một cảnh; mỗi câu là một lần gọi Polly (câu ngắn dưới 4 từ gộp với câu sau trên cùng dòng); dòng bắt đầu bằng `>` là ghi chú, không đọc; dấu `[` `]` bị bỏ khi đọc.

## 0 · Mở đầu (dựng, ~12 s)
Minh is twenty-two. Small spends, all week. Coffee. Lunch. A ride home.
His food jar has [three hundred eighty thousand] left, and payday is [fourteen] days away.
Is that enough?

## 1 · Nhìn trước và bản tin chủ động — F1, F7 (~20 s)
This is the real app, running on AWS.
For every jar, Yofina simulates thousands of possible next weeks.
It warns Minh that his food jar runs dry on [November twenty-third], [twelve] days before payday.
And it already knows his habits, so it suggests one thing to do next.

## 2 · Kiểm tra trước khi chi — F3 (~12 s)
Before he pays, Minh can just ask. Is a coffee okay?
A deterministic engine answers in seconds. His food jar is already [short] before payday, but his entertainment jar can cover it.

## 3 · Hỏi "nếu thì" và quyết định — F2 (~30 s)
Bigger question. New headphones, [one point two million], on buy now, pay later.
The agent turns his words into a scenario, and the forecast engine does the math.
The bill lands on payday, and his obligations jar comes up about [one point one seven million] short.
Yofina lays out options. Its pick: wait. Or top up from the emergency fund, with a reminder to keep it for emergencies.
He taps one. Nothing moves until he confirms.

## 4 · Cú sốc và điểm chống chịu — F4 (~15 s)
What if he lost his job for two months?
His resilience score drops from [twenty-nine] to [twelve]. He could hold out for [twenty-six] days.

## 5 · Dựng lộ trình từ mục tiêu — F5 (~30 s)
Minh wants to save [five million] before Tet.
Yofina checks that he wants a new plan, picks a jar, and builds it in stages.
Every step has a reason, and a linear optimizer keeps essentials covered.
Safety rules check each step before he ever sees it.
He decides whether to adopt it.

## 6 · Lộ trình tự đổi khi hành vi lệch — F5, F6 (~30 s)
Then, two weeks of eating out. Minh uploads his bank statement.
[Thirty-two] transactions land in the food jar, confirmed in one tap.
Yofina detects a real change in his spending, and proposes a new version of his plan on its own.
He compares it with the old one, and sees why each step changed.
Ask it which stock to buy, and it politely says no. That's outside its lane.

## 7 · Ảnh chứng từ và che thông tin cá nhân — F6 (~15 s)
He can also snap a receipt.
Before anything is saved, personal details like the payee's name are masked.

## 8 · Minh bạch và nhịp đêm (~12 s)
Every answer can be explained, down to each rule checked and each model call.
And every night at two a.m., forecasts refresh for everyone, automatically.

## 9 · Sơ đồ hệ thống (dựng, ~24 s)
> Phần lời mới 27/11, chủ dự án đã duyệt 27/11. Sơ đồ chỉ vẽ thành phần có trong `docs/architecture/overview.md` và `infra-cdk/lib/`; dòng bắt đầu bằng `>` không được đọc.
Under the hood, Cognito signs him in, and a Strands agent runs on AgentCore Runtime, with Memory and Bedrock.
Its harness routes, plans, checks numbers and masks personal data.
Each tool call passes Gateway and a Cedar policy, then Lambda runs Monte Carlo and LP over Aurora.
It all runs on new data, every night, and on demand.

## 10 · Kết (dựng, ~6 s)
Yofina Foresight.
See which jar runs dry, before it does.
