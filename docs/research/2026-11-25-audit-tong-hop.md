# Kiểm toán toàn dự án 25/11: tổng hợp

Người điều phối: Kiro CLI (Claude Opus 5.5), gom kết quả của 9 subagent chạy song song ngày 2026-11-25. Mỗi subagent chỉ đọc, ghi đúng một file ghi chú; không sửa code, không deploy, không chạy eval đầy đủ. Một số subagent chạy thử offline (backtest, test grader bằng Python cục bộ) và gọi AWS chỉ đọc (Service Quotas, CloudWatch, Step Functions, SNS).

## Câu hỏi

Sau 5 phase, còn gì bị bỏ sót, làm chưa tới hoặc làm sai khiến sản phẩm chưa đạt hiệu năng tốt nhất và chưa gây ấn tượng với ban giám khảo? Việc nào nên làm trước hạn nộp?

## Kết luận ngắn

1. **Hạn nộp thật là 23:59:59 ngày 03/12/2026, không phải 10/12.** Vòng sơ loại 20/11–3/12 (`techday.momo.vn/content/content.en.json`, mục `rules.steps`); sau hạn không được đổi mã nguồn, slide, sản phẩm đang chạy (FAQ "Can we submit multiple times?"); sản phẩm phải dùng được tới hết 11/12; top 5 công bố 08/12; chung kết trực tiếp 11/12. Lịch phase 6 hiện tại (RC 4/12, nộp 10/12) nằm sau hạn. [đã đọc tài liệu]
2. **Ban giám khảo là kỹ sư và nhà nghiên cứu** (CTO, Head of AI & Data, Research Scientist, các lead AI Engineering của MoMo). Tiêu chí (thể lệ Điều 18): Sáng tạo; Chất lượng và độ hoàn thiện; Tiềm năng tác động. Không công bố trọng số. Vì vậy bằng chứng đo được phải chịu được người đọc `evals/run.py`.
3. Tính năng F1–F7 đều đã có và đã deploy; không có tính năng MVP nào rỗng. Rủi ro lớn nằm ở **độ tin của số đo** (bộ chấm eval tự xác nhận số do model viết, mỗi ca chạy một lần, xác suất hũ thưa chưa hiệu chỉnh ở 47 ngày lịch sử), **độ trễ what-if** (74% thời gian là một lời gọi Analyst Sonnet 4.6 viết khoảng 2.000 token), và **bộ nộp bài** (thiếu tờ A4 1 trang, khai báo tài sản có sẵn, slide bị khóa từ 3/12).
4. Kỹ thuật ML đủ tốt cho cuộc thi (hurdle hơn seasonal naive khoảng 36–40% pinball); không nên thêm model mới. Cần báo số thật thà hơn, không cần model mạnh hơn.

## Nguồn: 9 ghi chú chi tiết

| Ghi chú | Phạm vi | Mã phát hiện |
|---|---|---|
| [2026-11-25-audit-phase-1-2.md](2026-11-25-audit-phase-1-2.md) | Phase 1–2 so với file plan | P12-01…09 |
| [2026-11-25-audit-phase-3.md](2026-11-25-audit-phase-3.md) | Phase 3 | P3-01…06 |
| [2026-11-25-audit-phase-4.md](2026-11-25-audit-phase-4.md) | Phase 4 | P4-01…08 |
| [2026-11-25-audit-phase-5.md](2026-11-25-audit-phase-5.md) | Phase 5 và luồng K | P5-01…12 |
| [2026-11-25-audit-proposal-vs-product.md](2026-11-25-audit-proposal-vs-product.md) | Proposal F1–F7, FR/NFR, kiến trúc so với code | PV-01…12 |
| [2026-11-25-audit-ml-forecasting.md](2026-11-25-audit-ml-forecasting.md) | Dự báo, hiệu chỉnh, K5, LP | ML-01…12 |
| [2026-11-25-audit-agent-aws-latency.md](2026-11-25-audit-agent-aws-latency.md) | Độ trễ, chi phí, quota Bedrock, AgentCore | AG-01…12 |
| [2026-11-25-audit-evals-safety.md](2026-11-25-audit-evals-safety.md) | Phương pháp eval, an toàn, bảo mật | EV-01…12 |
| [2026-11-25-audit-demo-judge.md](2026-11-25-audit-demo-judge.md) | Thể lệ, câu chuyện demo, kinh doanh, bộ nộp | DJ-01…12 |

## Phát hiện đã gộp (xếp theo ưu tiên)

Cột "Theo dõi ở": mục của [phase 6](../plan/phases/phase-6-danh-gia-dong-goi.md), việc T-0x của [ba/13](../ba/13-tien-do-technical.md), hoặc "mới". Tác động: theo giám khảo. Công: S dưới nửa ngày, M 1–2 ngày.

### Nhóm 0: lịch và việc hành chính (làm ngay)

| ID | Việc | Gộp từ | Tác động | Công | Theo dõi ở |
|---|---|---|---|---|---|
| AU-01 | Lập lại lịch phase 6 theo hạn 03/12: freeze, RC, eval cuối, bộ nộp đều trước 3/12 | DJ-01, DJ-03, DJ-04 | H | S | mới (mục 8 đang tới 10/12) |
| AU-02 | Gửi câu hỏi cho BTC trước 23:59 27/11 (đổi ACU, đổi mật khẩu, đặt lại dữ liệu demo sau hạn có tính là sửa sản phẩm không; video nộp tệp MP4 hay link; thời lượng thuyết trình; khai proposal Swinburne là tài sản có sẵn). Kiểm đội đã đăng ký và có mã đội (đăng ký đóng 27/11) | DJ quyết định 2–3, Q14 | H | S | Q14 (chưa hỏi) |
| AU-03 | Xin tăng quota Bedrock (Sonnet 4.6 đang 10 RPM cho cả tài khoản, chưa từng xin; 9 lần throttle ngày 23/11) | AG-04 | H | S | rủi ro phase 6, C3, J4; việc xin quota: mới |
| AU-04 | SNS `yofina-alerts` có 0 người nhận: 16 alarm và cảnh báo ngân sách không tới ai. Đăng ký một email, xác nhận, thêm kiểm vào preflight J1 | P12-02 | M | S | mới |

### Nhóm 1: độ tin của số đo và lỗi giám khảo dễ thấy

| ID | Việc | Gộp từ | Tác động | Công | Theo dõi ở |
|---|---|---|---|---|---|
| AU-05 | Sửa bộ chấm eval: `NumericGrounding` coi số trong khối do model viết (`options`, `reasoning`) là có căn cứ (số bịa 9.999.000 ₫ vẫn đạt); grader đối kháng yếu (regex mã cổ phiếu sót "Bitcoin", `forbid_other_user_data` chỉ xem `user_id` trong tham số tool, `leak-1` hỏi dữ liệu của chính `minh`); `kind` kịch bản không được chấm | P5-01, EV-01, EV-04, P3-01 | H | S | một phần (K "Còn lại") |
| AU-06 | Báo số đo đáng tin: chạy đối kháng và khoảng 10 ca golden trên đường demo 3 lần, báo pass^3 kèm khoảng Wilson; độ trễ phiên ấm và lạnh tách riêng; thời điểm chữ đầu và khối đầu theo ý định (NFR-01 đang tính tới `RUN_STARTED`); p95 kiểm tra trước khi chi qua chat | EV-02, AG-07, PV-08, P3-03 | H | S (+$1,5–2) | mới |
| AU-07 | Ca đối kháng còn thiếu: tiếng Việt không dấu (0/150 câu), chèn chỉ dẫn qua ghi chú giao dịch đã duyệt (chữ từ tệp nạp vào prompt writer và số trong đó được tính là có căn cứ), moi system prompt. Sửa luôn lỗ hổng căn cứ số của chữ từ tệp nạp | EV-03, P5-08 | H | S | một phần (H1) |
| AU-08 | Lập luận luồng K nhất quán với kết quả: cảnh 2 lập luận nói dùng Giải trí 760.000 ₫ để mua 1.200.000 ₫ và trích luật đã loại phương án đó; lộ trình nói hũ nguồn khác bản đã lưu. Giới hạn 2–3 bước, thêm công tắc SSM tắt lập luận | P5-02, PV-06, P5-04, AG-01 | H | S–M | một phần (K "Còn lại") |
| AU-09 | Xác suất hụt trên hũ thưa khi lịch sử dưới khoảng 60 ngày: độ phủ đo được 0,64–0,69 (cổng 0,75–0,85) mà vẫn hiện %. Chặn % theo độ dài lịch sử, hiện nhãn Cao/Vừa/Thấp; đưa số đo ở 47 ngày vào `backtest-final.md` | P12-03, ML-03 | H | S | mới |
| AU-10 | K5 (báo trước ≥ 7 ngày, ≥ 70% đúng): kế hoạch H2 không đo được vì persona dựng lịch sử lùi từ ngày neo; đo trên kịch bản cho 0,57 với hũ dày (±3 ngày). "12 ngày trước kỳ lương" là khoảng tới ngày lương, không phải số ngày báo trước. Chốt định nghĩa cho slide | ML-01, ML-02, DJ-12 | H | S | H2 (cách đo: mới) |
| AU-11 | Nợ Trả sau biến mất khỏi dự báo trên tài khoản không có hũ Nghĩa vụ (`lan`, `khoa`, `giamkhao3`) trong khi what-if và kiểm tra trước khi chi trừ vào hũ chi tiêu: hai màn lệch số | P12-04 | M | S | mới |
| AU-12 | Tài liệu cũ và lệch không có ADR: README gốc ghi "chưa có code sản phẩm", CLAUDE.md ghi "giai đoạn scaffold"; cột trạng thái FR ở requirements.md; NFR-11 ghi công cho ACI dù dải hiển thị từ Monte Carlo; PELT/CUSUM không nối vào cửa sổ dự báo; khoảng 10 điểm lệch proposal chưa có ADR. Viết ADR-0004 "Lệch so với proposal" | PV-10, PV-11, PV-12, ML-05, ML-06, P12-09 | M | S | một phần (I1, I2, I6) |

### Nhóm 2: độ trễ và độ bền trên đường demo

| ID | Việc | Gộp từ | Tác động | Công | Theo dõi ở |
|---|---|---|---|---|---|
| AU-13 | Lượt bị throttle hoặc bị bộ giới hạn bỏ qua vẫn tính vào trần 4 lời gọi mỗi lượt, nên khi Sonnet throttle thì Analyst bị chặn trước khi kịp rẽ sang Kimi. Hạ `rate_limit_max_wait_seconds` 20 → 4 s trong khung chấm | AG-03 | H | S | mới |
| AU-14 | Gói giảm độ trễ what-if ít rủi ro: ghi lượt sau `RUN_FINISHED` và khóa `_ensure` (hai phiên MCP khi gọi song song); chạy song song các lời gọi độc lập (khoảng 1,5–2 s); cờ "hũ nguồn đủ tiền" tính bằng mã để tránh vòng sửa Verifier (+5,5–6 s mỗi lần); rút ngắn output Analyst. Ước tính what-if ấm còn 14–16 s, khối đầu 2,5–3 s (chưa đo) | AG-05, P5-03, AG-08, AG-09, AG-01 | H | S mỗi việc | một phần (C1, D2) |
| AU-15 | Orchestrator Sonnet chạy trước 3 tool đọc nên khối đầu chờ; dùng `deterministic_spec` trước khi router đã đủ tham số, hoặc chuyển sang Nova 2 Lite, Sonnet làm dự phòng. Đo bằng 9 ca golden what-if `--only` (khoảng $0,4) | PV-02, AG quyết định 2 | H | M | mới (D1/D2 chưa nêu nguyên nhân này) |
| AU-16 | Thẻ tiến độ ghi "Yofina đã làm" với mọi dấu tích trong khi Analyst còn chạy khoảng 16 s: trông như đã xong hoặc bị treo | DJ-07 | H | S | một phần (D2c) |
| AU-17 | Step Functions `yofina-nightly` hỏng 24/11 02:00 vì Aurora ngủ: bước `ListUsers` không retry, `list_users` ném `YofinaError` thay vì `DatabaseUnavailable` | P12-01 | M | S | một phần (C2) |
| AU-18 | Prompt caching cho Sonnet (tiết kiệm khoảng $0,008 mỗi what-if), tắt theo model vì Kimi K3 trả `ValidationException` | AG-06, PV-05 | L | S | mới |

### Nhóm 3: câu chuyện demo, kinh doanh, bộ nộp

| ID | Việc | Gộp từ | Tác động | Công | Theo dõi ở |
|---|---|---|---|---|---|
| AU-19 | Bộ nộp theo đúng đề: tờ hướng dẫn PDF 1 trang A4 (link, tài khoản); `.zip` mã nguồn với README khai cách chạy, công nghệ, tài sản có sẵn (proposal Swinburne), thư viện mã nguồn mở, công cụ AI (Claude Code, Kiro CLI, model Bedrock), nguồn dữ liệu (25 ảnh web, biểu phí Trả sau, tỷ giá Vietcombank); slide ≤ 10 trang khóa từ lúc nộp | DJ-02, DJ-03 | H | S–M | một phần (I1, I4) |
| AU-20 | Cảnh 4: chiếu bản lộ trình sinh lại do lệch hành vi (đã seed) và màn So với bản cũ thay vì dựng lộ trình trong chat; nói rõ là dữ liệu seed trong README và video, thêm clip 20–30 s đường chạy thật trên `lan`; tính lại số lý do của `minh` (520k → 810k) từ ledger | DJ-05, PV-01, P4-04 | H | S | một phần (E1) |
| AU-21 | Video: câu vấn đề có số trong 15 s đầu; số lấy từ engine (33 → 13, trụ 31 ngày) thay số minh họa của proposal (58 → 34); nhãn "tua nhanh" ở đoạn cắt chờ; phần dựng Remotion ≤ 15 s | DJ-06 | H | S | một phần (I3) |
| AU-22 | Kinh tế đơn vị: một what-if khoảng 1.578 ₫ trong khi phí nền 1.500 ₫ mỗi người dùng mỗi tháng. Cần chi phí AI mỗi người dùng hoạt động mỗi tháng; trang "Yofina trong MoMo" (điểm vào, dữ liệu MoMo cấp, cách thay bằng model của MoMo); cách nói "AI là thành phần cốt lõi"; kết bài bằng "AI đề xuất, con người quyết định" | DJ-08, DJ-09, DJ-10 | H | S | một phần (I5) |
| AU-23 | Cảnh 5 (nạp ảnh) yếu nhất và chưa từng đi trên `giamkhao1`; repo chỉ có tệp mẫu cho `vy`. Làm chứng từ mẫu cho `minh`, rút cảnh còn khoảng 15 s | P5-05, DJ-11 | H | S | một phần (A1) |
| AU-24 | Tài khoản demo: `giamkhao1` thuộc nhóm `ops` xem được trace mọi tài khoản; `giamkhao3` là persona `vy` chưa từng được eval và không có lộ trình seed nhưng đang là tài khoản dự phòng ở J4; đổi mật khẩu trước khi xuất tờ hướng dẫn | EV-09, PV-09, EV-06, DJ quyết định 6 | M | S | một phần (J2, J4) |

### Nhóm 4: việc nhỏ

| ID | Việc | Gộp từ | Tác động | Công | Theo dõi ở |
|---|---|---|---|---|---|
| AU-25 | CI tối thiểu chạy offline: unit, vitest, CDK, quét bí mật (proposal §14 ghi GitHub Actions là MVP) | PV-04, EV-07 | M | S | mới |
| AU-26 | Chữ và số trên giao diện: thẻ chủ động còn "Xác suất hụt khoảng 100%", làm tròn 1% thay vì bước 5%; tài khoản 0 ₫ vẫn "dự kiến cạn"; kỳ lộ trình bắt đầu hôm nay thay vì ngày lương (sửa trong `allocation.py` bằng `next_payday`); So với bản cũ ghi mã thô | P12-07, P12-08, ML-10, P4-02, P4-01 | M | S | một phần (E1, E5) |
| AU-27 | Kiểm tra trước khi chi lấy ngưỡng cạn từ giá trị mặc định trong mã thay vì cấu hình; dải vàng không bao giờ hiện vì hai ngưỡng bằng 0. Sửa cùng T-02 sau khi BA chốt C-02 | P3-02, PV-07 | M | S | T-02 |
| AU-28 | Bảo mật nhanh: header CSP và `frame-ancestors 'none'` trên Amplify; che tên người sau "chị/anh" trong bộ nhớ | P12-05, P5-12 | L–M | S | mới |
| AU-29 | Đo trước khi quyết: độ dao động OCR r08, r15 (3 lần, khoảng $0,1); ca `memory-whatif-protect-jar` với bộ nhớ seed đúng; các kiểm chỉ làm được trên trình duyệt (giờ yên tĩnh của nudge, mở trace từ "Vì sao", màn Chi tiết hũ) gộp vào A1 | P5-07, P5-06, P5-11 | M | S | một phần (A1, A4) |
| AU-30 | Bằng chứng eval trong repo: bản tóm tắt kết quả kèm phiên bản Runtime và model id (`evals/results/` đang bị gitignore); 20 câu giữ riêng do Học viết, nửa không dấu, chỉ chạy router | EV-08, EV-05 | M | S | một phần (H4) |
| AU-31 | Báo số phân loại cả hai mặt: 92% đúng trên dòng đã gán và khoảng 60% dòng cần người dùng chạm (17,4% phải hỏi, 43,1% vào Xem lại) | P4-03, PV-03 | M | S | E7, T-03 |

## Ghi là giới hạn đã biết (không sửa trước hạn)

P3-04 (phương án mất hành động khi `_prepare_action` lỗi), P3-05 (Verifier 2 vòng so với trần 4 lời gọi: giữ trần 4), P3-06 (chưa có dòng phạt trễ hạn Trả sau), P4-05 (lộ trình không tự cập nhật số khi dự báo đổi nhẹ; có thể thêm nhãn "Số tính ngày …"), P4-06 (không hỏi lý do khi "Giữ bản cũ"), P4-07 (đã có E2), P4-08 (log Lambda sinh lại), P5-09 (chứng từ ngoại tệ trùng qua ảnh khác), P5-10 (không có lập luận ở kiểm tra trước khi chi; lộ trình không dùng bộ nhớ), P12-06 (`lan` có 47 ngày lịch sử), ML-04 (dải 80% lệch một phía nếu không làm CQR), EV-11 (lịch sử chat từ trình duyệt không qua Guardrail), EV-12 (judge bộ nhớ chưa đối chiếu nhãn người), AG-10 (chi phí bộ nhớ Runtime của phiên eval), AG-11 (trace thiếu model và token từng bước).

## Không làm (có lý do trong ghi chú nguồn)

Chronos-2 (cần SageMaker); ACI theo từng người dùng, AgACI, conformal PID (ML-11: với T = 47 không bảo đảm gì); Automated Reasoning checks (chỉ phát hiện, không chặn, AWS không ghi hỗ trợ tiếng Việt); nhận thêm chủ đề "Chống lừa đảo" (FR14 chưa làm); WAF; lập luận cho kiểm tra trước khi chi (giữ NFR-02); latency-optimized inference, Priority/Flex tier, Reserved throughput (không có cho Sonnet 4.6 ở Singapore hoặc cần cam kết dài, AG-12); ngày cạn theo trung bình (ML-11).

## Việc có thể làm nếu còn thời gian (cần chủ dự án duyệt)

ML-07 + ML-08: CQR bất đối xứng cho dải hũ dày (đuôi 15,5/3,9 → 8,8/7,4 khi đo offline) và hiệu chỉnh `p_shortfall` bằng PAV; ML-09: hũ thưa hiện "có thể cạn trước ngày lương" thay vì ngày cụ thể; PV-03: hũ "Khác" 0% (chạy `evals/classification` offline trước).

## Điều chưa chắc

- Ngày hạn lấy từ trang chính thức (`content.en.json`: vòng sơ loại kết thúc `2026-12-03`) và bản tóm thể lệ PDF của subagent DJ; tệp PDF không đọc trực tiếp được bằng công cụ của người điều phối.
- Ước tính độ trễ sau AU-14 và AU-15 là tính trên giấy từ log, chưa đo.
- Chưa chạy được unit test trên máy này (không có `uv`, không có `.venv`); các phát hiện dựa trên đọc mã, test cục bộ bằng Python Anaconda và log AWS.
- Phát hiện về giao diện dựa trên ảnh `dev:mock` và mã, chưa đi trên bản deploy.

## Nguồn đã tra

- https://techday.momo.vn/content/content.en.json (lịch, FAQ, ban giám khảo), truy cập 2026-11-25
- https://techday.momo.vn/content/exam.json (đề, yêu cầu sản phẩm, thành phần bài nộp), truy cập 2026-11-25
- 9 ghi chú ở bảng trên và nguồn ghi trong từng ghi chú
