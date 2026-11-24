# Trực quan hóa chi tiêu trên điện thoại

Ngày 2026-11-24. Trả lời câu hỏi của chủ dự án: giao diện có thể thêm biểu đồ dựa trên chi tiêu của người dùng để họ dễ theo dõi không. Có, và phần lớn dữ liệu đã có sẵn. Tài liệu này chỉ bàn **biểu đồ chi tiêu**; bảng màu và bố cục chung nằm ở `ui-design-review.md` (worker khác đang viết), và biểu đồ dự báo 30 ngày đã có ở [ForecastBlock](../../frontend/src/features/forecast/ForecastBlock.tsx).

Bản minh họa tĩnh khổ 390 px, sáng và tối, bằng số thật của persona `minh`: [spending-visualization-preview.html](spending-visualization-preview.html) (mở thẳng bằng trình duyệt, không cần build).

**Tóm tắt.** Năm biểu đồ đáng làm nhất cho buổi demo:

| # | Câu hỏi | Biểu đồ | Dữ liệu | Cần đổi hợp đồng? |
|---|---|---|---|---|
| B1 | Kỳ lương này tiêu vào đâu, so với kỳ trước thế nào | Thanh ngang theo hũ, vạch "kỳ trước cùng thời điểm" | `ledger___get_cashflow_summary` (đã có cho agent) | Có: thêm `GET /cashflow` (bản REST của tool), tùy chọn tách nghĩa vụ và Trả sau |
| B2 | Hũ nào sắp cạn | Đường băng từng hũ tới kỳ lương | `GET /overview` (`jars[].status`, `runout_date`, `next_payday`) | Không |
| B3 | Cuối tuần mình có tiêu nhiều không | Thanh tỷ lệ "phần chi" so với "phần số ngày" trong thẻ nhận xét | `GET /profile/behavior`, bằng chứng `weekend_share` + `weekend_day_share` | Không (P0); thêm dãy 7 ngày ở P1 |
| B4 | Đã dùng Trả sau bao nhiêu | Thanh hạn mức đã dùng, khoản đến hạn so với hũ Nghĩa vụ | `GET /credit-line`, `GET /obligations`, `GET /overview` | Không |
| B5 | Tháng này so với tháng trước | Đường lũy kế kỳ này và kỳ trước theo ngày của kỳ | Chưa có chuỗi theo ngày | Có: thêm `daily[]` vào `GET /cashflow` |

**Đã làm (25/11, nhánh `p5/viz-p1`, chưa deploy)**: B1, B5, B7 ở đầu màn Hoạt động, dữ liệu từ route mới `GET /cashflow` (bản REST của `get_cashflow_summary`, cùng hàm SQL; `gateway/tools/ledger/yofina_ledger/cashflow_rest.py`). Khác đề xuất: không có tham số `from`/`to` hay `compare_previous` (server luôn trả kỳ lương hiện tại và kỳ trước cùng số ngày); phần tách nghĩa vụ và Trả sau cộng từ `app_list_transactions` vì đợt này không thêm hàm DB (mục "Biểu đồ chi tiêu" của contracts/README.md); chạm một hũ ở B1 mở Chi tiết hũ thay vì lọc danh sách; chưa có chip "Ẩn khoản cố định" và thẻ thu gọn ở Tổng quan (§10 của ui-design-review.md: Hoạt động là nhà). Ảnh `activity-cashflow-*`, `activity-theongay-cashflow-*` ở [ui-round1/](ui-round1/).

## 1. Hiện trạng

### 1.1 Dữ liệu đã có

| Nguồn | Trường dùng được cho biểu đồ | Ghi chú |
|---|---|---|
| `GET /overview` (`OverviewResponse`) | `jars[]`: `balance_vnd`, `split_percent`, `status` (ok/tight/short), `runout_date`, `p_shortfall`, `confidence_band`, `forecast_floor_vnd`; `next_payday` (`date`, `days_until`, `expected_vnd`); `credit_line`; `obligations_due`; `balance` (tổng, Tiền vào khác, Chưa phân loại) | Một lần gọi, đã có `useOverview()` dùng chung |
| `GET /transactions` | Từng giao dịch: `app_date`, `occurred_at`, `kind`, `jar`, `amount_vnd`, `merchant`, `tx_type`, `funding_source` (jar, credit, external), `obligation_id` | Tối đa 50 dòng mỗi trang, con trỏ. Đủ cho danh sách, không nên dùng để cộng dồn trên máy khách (mục 1.3) |
| Tool `ledger___get_cashflow_summary(from_date, to_date)` | `salary_income_vnd`, `other_income_vnd`, `spent_vnd`, `by_jar[]` (`spent_vnd`, `tx_count`), `unclassified_pending_vnd` | **Chỉ agent gọi được**, không có route REST. SQL `app_get_cashflow_summary` (migration 0050) tính cả dòng trả nghĩa vụ và dòng Trả sau, bỏ chuyển hũ và chi ngoài ví |
| `GET /forecasts/{jar}` và tool `forecast___get_forecast` | P10/P50/P90 từng ngày, mốc nghĩa vụ và lương, ngày cạn, xác suất hụt hoặc nhóm tin cậy | Đã vẽ bằng ForecastBlock |
| `GET /obligations`, tool `ledger___get_obligations` | `amount_vnd`, `amount_min_vnd`/`amount_max_vnd`, `fee_vnd`, `principal_vnd`, `due_date`, `pay_jar`, `kind` (bnpl, rent, bill...) | |
| `GET /credit-line` | `limit_vnd`, `outstanding_vnd`, `available_vnd`, `due_day`, `fees[]` có nguồn | |
| `GET /profile/behavior`, tool `forecast___get_behavior_profile` (phase 5) | `features`: `avg_daily_spend_vnd`, `first_week_after_payday_share`, `weekend_share`, `evening_share`, `top_weekday`, `bnpl_purchases_per_month`, `bnpl_share`; `insights[].evidence[]` (key, label, value, unit, kỳ) | Batch đêm ([ml/yofina_ml/behavior.py](../../ml/yofina_ml/behavior.py)) phát kèm cả **mốc so sánh**: `first_week_day_share`, `weekend_day_share` |
| `GET /resilience` | Điểm 0 đến 100, bốn thành phần | Đã có ResilienceGauge, ScoreRow; ngoài phạm vi tài liệu này |
| `GET /roadmap` | Mục tiêu (`target_vnd`, `projected_date`, `on_track`) | Ngoài phạm vi |

### 1.2 Biểu đồ đang có trong frontend

- Thư viện: `recharts` 3.11.0 ([frontend/package.json](../../frontend/package.json)), dùng ở đúng một chỗ: [ForecastChart.tsx](../../frontend/src/features/forecast/ForecastChart.tsx), tải lười (`lazy`) vì Recharts cùng d3 và redux toolkit nặng khoảng 118 KB gzip (đo ở [spike-frontend-stack.md](spike-frontend-stack.md) §8).
- Biểu đồ tự vẽ không dùng thư viện: [MiniTimeline](../../frontend/src/components/MiniTimeline.tsx) (thanh hôm nay tới kỳ lương, điểm cạn), [ResilienceGauge](../../frontend/src/features/resilience/ResilienceGauge.tsx) (cung SVG), [JarGlass](../../frontend/src/components/JarGlass.tsx) (hũ thủy tinh có vạch dự báo). Cả ba có `role="img"` và `aria-label` dựng từ số server trả.
- ForecastBlock đặt sẵn các mẫu nên dùng lại: dòng đọc số `aria-live="polite"`, thanh kéo `input type="range"` cao 44 px để chọn ngày (thay cho rê chuột), chú giải bằng chữ, vùng hụt gạch chéo (không chỉ màu), câu tóm tắt dựng từ số server.
- Chưa có biểu đồ nào về **chi tiêu đã qua**. Màn Hoạt động (`ActivityPage`) chỉ là danh sách giao dịch có lọc theo hũ (`?jar=`). Nhận xét hành vi ở Hồ sơ (`BehaviorInsightCard`) hiện bằng chứng dạng bảng số.

### 1.3 Khoảng trống của hợp đồng

1. **Không có route REST cho tổng chi theo hũ.** Màn hình muốn vẽ "tiêu vào đâu" chỉ có hai đường: cộng `GET /transactions` trên máy khách (nhiều trang, phải tự loại chuyển hũ, khoản trả nghĩa vụ, dòng ngoài ví; trái quy ước "giao diện chỉ vẽ số server trả" mà ForecastBlock ghi rõ), hoặc thêm `GET /cashflow` gọi cùng `cashflow_result` của Lambda ledger (đúng nguyên tắc "một mã, hai đường vào" của OpenAPI). Chọn cách thứ hai.
2. **`CashflowJar` không tách phần cố định và phần Trả sau.** Hũ Hóa đơn của `minh` kỳ này chi 2.435.000 ₫, trong đó 2.320.000 ₫ là tiền thuê phòng, Internet và cước điện thoại. Không tách thì biểu đồ nói "Hóa đơn tốn nhiều" trong khi đó là khoản cố định.
3. **Không có chuỗi chi theo ngày**, nên không vẽ được lũy kế "so với kỳ trước" hay cột theo ngày trong kỳ.
4. **Hồ sơ hành vi chỉ có tỷ lệ gộp**, không có trung bình từng thứ trong tuần hay theo khung giờ, dù batch đã tính `avg_by_weekday` (biến cục bộ trong `compute_profile`). Cột `behavior_profiles.features` là jsonb (migration 0053) nên thêm khóa không cần migration, nhưng bảng có CHECK giới hạn kích thước `features + insights + segment`: dãy 7 số và 4 số vẫn rất nhỏ.
5. **Chi ngoài ví bị loại khỏi `spent_vnd`** (`funding_source <> 'external'`), SQL chỉ trả tổng `external` không theo hũ. Với persona `vy` (cảnh 5), biểu đồ theo hũ sẽ thiếu phần đã nạp từ sao kê. Cần `external_spent_vnd` theo hũ nếu muốn cảnh 5 thấy biểu đồ đổi sau khi nạp.

### 1.4 Số thật của persona `minh` (đã đo)

Chạy `generate("minh", anchor=2026-11-21)` của [data/personas/generator.py](../../data/personas/generator.py) rồi `compute_profile` của batch hành vi trên đúng sổ cái đó (166 dòng, 47 ngày từ 05/10). Hôm nay 21/11 là ngày thứ 17 của kỳ lương 05/11, chưa có giao dịch trong ngày. Bản minh họa HTML dùng đúng các số này.

| Chỉ số | Kỳ này 05/11–21/11 | Kỳ trước cùng thời điểm 05/10–21/10 |
|---|---|---|
| Tổng chi theo định nghĩa `get_cashflow_summary` (gồm nghĩa vụ, Trả sau) | 6.908.000 ₫ | 3.767.000 ₫ |
| Ăn uống | 2.738.000 ₫ (64 giao dịch) | 1.025.000 ₫ |
| Hóa đơn (trong đó cố định) | 2.435.000 ₫ (2.320.000 ₫) | 2.333.000 ₫ (2.320.000 ₫) |
| Giải trí (trong đó Trả sau, cố định) | 1.245.000 ₫ (967.000 ₫, Netflix 180.000 ₫) | 180.000 ₫ (Netflix) |
| Đi lại | 310.000 ₫ | 229.000 ₫ |
| Chưa phân loại | 180.000 ₫ | 0 ₫ |
| Chi thường ngày lũy kế (bỏ nghĩa vụ) | 4.408.000 ₫ | 1.267.000 ₫ |

Hồ sơ hành vi tính lại trên sổ cái này (khác fixture `BehaviorProfileResponse.minh.json`, vốn là số minh họa): cuối tuần chiếm 37% chi tiêu dù chỉ 26% số ngày; 7 ngày đầu sau lương chiếm 40% dù chỉ 30% số ngày (tuần đầu kỳ 05/11 chi 2.069.000 ₫); buổi tối 35%; Trả sau 2 lần, 967.000 ₫, 14% chi tiêu. Trung bình mỗi ngày: thứ Hai 251.429 ₫ (trong đó 138.143 ₫ là Trả sau), thứ Ba 89.286, thứ Tư 83.000, thứ Năm 90.000, thứ Sáu 94.857, thứ Bảy 203.167, Chủ nhật 212.667; cả kỳ 143.723 ₫ mỗi ngày.

Hai điều biểu đồ sẽ làm lộ ra trước giám khảo, chủ dự án nên biết trước:

- **Kỳ này chi thường ngày gấp khoảng 3,5 lần kỳ trước cùng thời điểm** (4,41 triệu so với 1,27 triệu). Lý do nằm ở spec: `recent_share` 0,58 dồn phần lớn chi tiêu vào kỳ gần nhất, và hũ Ăn uống bắt đầu kỳ trước từ số dư 0. Biểu đồ B1 và B5 sẽ vẽ đúng như vậy. Nếu muốn câu chuyện "tăng vừa phải" thì phải hiệu chỉnh spec (khóa băm persona trong `tests/unit/persona_digest.py` sẽ đổi), việc đó ngoài phạm vi tài liệu này.
- **`top_weekday` thật là thứ Hai**, không phải thứ Bảy như fixture, vì hai lần mua Trả sau (520.000 ₫ ngày 09/11, 447.000 ₫ ngày 16/11) đều rơi vào thứ Hai. Biểu đồ theo thứ phải tách phần Trả sau, nếu không người xem sẽ hiểu sai.

## 2. Nguyên tắc rút ra từ nguồn

- **Chọn biểu đồ theo quan hệ cần thấy, không theo loại dữ liệu.** FT Visual Vocabulary chia theo quan hệ (so sánh độ lớn, phần của tổng thể, thay đổi theo thời gian, phân bố) ([GitHub FT chart-doctor](https://github.com/Financial-Times/chart-doctor/blob/main/visual-vocabulary/README.md); hướng dẫn của [data.europa.eu](https://data.europa.eu/apps/data-visualisation-guide/choosing-charts-the-message)). Áp vào đây: "tiêu vào đâu" là so sánh độ lớn giữa các hũ, nên dùng thanh; "so với kỳ trước" là thay đổi theo thời gian, nên dùng đường.
- **Bánh và donut chỉ hợp khi ít phần.** Datawrapper khuyên quá năm phần thì gộp hoặc chuyển sang thanh ([pie](https://www.datawrapper.de/academy/customizing-your-pie-chart), [donut](https://www.datawrapper.de/academy/customizing-your-donut-chart)). Minh có 7 hũ cộng Chưa phân loại, nên không dùng donut cho B1. NN/g cũng chỉ ra vị trí và độ dài được đọc chính xác hơn góc và diện tích ([dashboards và thuộc tính tiền chú ý](https://www.nngroup.com/articles/dashboards-preattentive/)).
- **App quản lý chi tiêu làm gì.** YNAB có "Spending Breakdown" (tỷ lệ theo danh mục) và "Income vs Spending" sáu tháng trên điện thoại ([Spending Breakdown](https://support.ynab.com/en_us/spending-breakdown-H1H7YxmD0), [Income v Expense](https://support.ynab.com/en_us/income-v-expense-Byu1BYWRq)). Copilot vẽ đường chi lũy kế trong tháng so với đường chấm của tháng trước, kèm con số "nhiều hơn hay ít hơn tháng trước nếu tháng kết thúc hôm nay" ([Copilot help](https://help.copilot.money/en/articles/6282850-optional-budgeting)), và chạm vào một cột để mở chi tiết theo danh mục ([Cash Flow tab](https://help.copilot.money/en/articles/9682232-cash-flow-tab-overview)). Monarch có Sankey dòng tiền và treemap danh mục, nhưng đó là báo cáo trên web ([Monarch blog](https://www.monarch.com/blog/visualize-your-cash-flow-like-never-before)). Kết luận: trên điện thoại, mẫu phổ biến và dễ đọc nhất là thanh theo danh mục cộng đường lũy kế so tháng trước; Sankey và treemap không hợp màn 390 px. Trong nước, Money Lover nhấn vào "biết tiền đi đâu" bằng báo cáo theo danh mục ([App Store](https://apps.apple.com/us/app/money-lover-s%E1%BB%95-thu-chi/id486312413?l=vi&platform=ipad)).
- **Điện thoại: con số quan trọng đọc trước, chi tiết sau một lần chạm.** Một biểu đồ thu nhỏ khác với một biểu đồ thiết kế lại cho điện thoại; giữ câu hỏi chính trong tầm nhìn và đặt thao tác sau nút chạm thấy được ([Semiotic, mobile data viz](https://semiotic.nteract.io/examples/mobile-data-visualization/); [Horak và cộng sự, Responsive Visualization Design for Mobile Devices](https://vcg.informatik.uni-rostock.de/~ct/publications/Horak21ResponsiveMobileVis.pdf)). Áp vào đây: mỗi thẻ mở bằng một câu kết luận có số, nhãn ghi thẳng trên thanh thay cho chú giải, rê chuột thay bằng chạm và thanh kéo.
- **Khả năng tiếp cận.** W3C coi biểu đồ là "ảnh phức tạp": cần câu tóm tắt ngắn và một bản tương đương đầy đủ (bảng hoặc danh sách) ([WAI complex images](https://www.w3.org/WAI/tutorials/images/complex/)). Thành phần đồ họa cần để hiểu (thanh, đường) phải có tương phản ít nhất 3:1 với nền ([WCAG 1.4.11](https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html)); hai màu liền nhau dưới 3:1 thì thêm viền ([G209](https://www.w3.org/WAI/WCAG22/Techniques/general/G209)). Chartability gom 50 phép kiểm, 14 phép quan trọng ([Chartability](https://chartability.fizz.studio/), [bản kiểm trung cấp của data.europa.eu](https://data.europa.eu/apps/data-visualisation-guide/intermediate-accessibility-audit-with-chartability)). Apple coi biểu đồ tài chính là nơi phải hỗ trợ trình đọc màn hình (audio graph) ([WWDC21 Bring accessibility to charts](https://developer.apple.com/la/videos/play/wwdc2021/10122/)).

Nội dung từ các nguồn trên đã được diễn đạt lại để tuân thủ giới hạn trích dẫn.

### 2.1 Quy tắc chung cho mọi biểu đồ dưới đây

1. **Số đến từ server, giao diện chỉ vẽ.** Tỷ lệ chiều dài thanh là trình bày, được tính ở giao diện; tổng, chênh lệch, câu kết luận do server hoặc code dựng (như `forecastSummary`). Không có số nào gắn cứng trong mã (bundle check đã chặn số dư persona).
2. **Câu kết luận trước, biểu đồ sau.** Câu đó cũng là `aria-label` hoặc `figcaption`.
3. **Không chỉ dựa vào màu.** Trạng thái luôn có biểu tượng và chữ (Đủ, Sát, Hụt như `StatusChip`); phần Trả sau dùng chấm, phần cố định dùng gạch chéo, giống vùng hụt của ForecastChart.
4. **Nhãn trực tiếp, không chú giải rời** khi có thể; nếu có chú giải thì bằng chữ, đặt dưới biểu đồ.
5. **Bản tương đương cho trình đọc màn hình**: danh sách `<ul>` có chữ (thanh ngang tự nhiên đã là danh sách) hoặc bảng `sr-only`. Phần đồ họa `aria-hidden`.
6. **Chạm, không rê.** Vùng chạm cao ít nhất 44 px (`min-h-11` như nút trong repo), thanh kéo `range` cho biểu đồ theo ngày, dòng đọc số `aria-live="polite"`.
7. **Tương phản 3:1 của nét và thanh.** Đã tính trên `#FFFFFF`: màu hũ Đi lại `#2FA3D6` chỉ đạt 2,86 và Du lịch `#1FA6A0` đạt 2,99, nét "sát" `#E39A00` đạt 2,36. Ở chế độ sáng, ba màu này cần viền đậm hơn 1 px hoặc tông đậm hơn khi tô thanh; chế độ tối đều trên 6. (Đề xuất sửa bảng màu là việc của `ui-design-review.md`; ở đây chỉ nêu ràng buộc cho biểu đồ.)
8. **`prefers-reduced-motion`**: không chạy hiệu ứng mọc thanh khi người dùng tắt chuyển động.
9. **Kỳ lương là đơn vị thời gian mặc định**, không phải tháng dương lịch, vì ngân sách hũ chia theo lương (ngày 5). Nhãn ghi rõ "Kỳ lương 05/11 đến nay".

## 3. Đề xuất biểu đồ

Mỗi đề xuất ghi: câu hỏi, loại biểu đồ, dữ liệu, màn, tương tác, thiếu dữ liệu, khả năng tiếp cận.

### B1. Kỳ lương này tiêu vào đâu (kèm so với kỳ trước)

> Đã làm 25/11 (`p5/viz-p1`), xem ghi chú dưới bảng tóm tắt.

- **Câu hỏi**: "Tháng này tiêu vào đâu?", "Hũ nào tốn hơn kỳ trước?"
- **Loại**: thanh ngang theo hũ, sắp giảm dần. Mỗi thanh chia ba phần: chi thường (màu hũ, đặc), Trả sau (chấm), cố định từ nghĩa vụ (gạch chéo xám). Một vạch đứng mảnh trên mỗi thanh là mức của kỳ trước tính tới cùng ngày của kỳ. Bên phải: số tiền và chênh lệch bằng chữ ("+1,71 triệu so với kỳ trước"). Hũ Chưa phân loại là thanh xám cuối danh sách, có nút "Xếp hũ".
- **Dữ liệu**: `get_cashflow_summary(from=ngày lương gần nhất, to=hôm nay)` và lần gọi thứ hai cho kỳ trước cùng số ngày. Cần thêm vào hợp đồng:
  - `GET /cashflow?from=&to=` (`x-lambda: ledger`, trả đúng `GetCashflowSummaryOk.data`), gọi `service.cashflow_result` sẵn có.
  - Trường tùy chọn của `CashflowJar` (không tăng `v`): `obligation_vnd` (dòng có `obligation_id`), `credit_vnd` (dòng `funding_source = credit`), `external_spent_vnd` (dòng ngoài ví, nếu muốn cảnh 5 thấy).
  - Tùy chọn `compare_previous=true` để server trả luôn `previous: {from_date, to_date, spent_vnd, by_jar[]}` cùng số ngày, khỏi gọi hai lần và khỏi để giao diện tự tính khoảng ngày kỳ trước.
  - Tên hiển thị, `color_key`, `icon_key` lấy từ `useJarLookup()` (đã có).
- **Màn**: đầu màn Hoạt động (`/activity`), thay cho phần trống phía trên danh sách. Một thẻ thu gọn (ba hũ đầu và tổng) ở Tổng quan dưới thẻ chủ động, bấm vào mở Hoạt động.
- **Tương tác**: chạm một thanh lọc danh sách bên dưới theo hũ (`?jar=` mà ActivityPage đã hỗ trợ). Chip "Ẩn khoản cố định" bỏ phần gạch chéo để thấy chi thường ngày. Không kéo.
- **Thiếu dữ liệu**: chưa có kỳ trước (persona `khoa`, 18 ngày): ẩn vạch so sánh, ghi "Chưa có kỳ trước để so". Kỳ chưa có giao dịch chi: `EmptyState` "Kỳ này bạn chưa chi gì". Có Chưa phân loại: thanh xám luôn hiện, vì bỏ đi sẽ làm tổng lệch với tổng ví. Lỗi tải: `ErrorState` có nút thử lại, như các màn khác.
- **Khả năng tiếp cận**: `<figure>` có `figcaption` "Kỳ lương 05/11 đến nay bạn đã chi 6.908.000 ₫, nhiều nhất ở Ăn uống 2.738.000 ₫". Mỗi hũ là một `<li>` có chữ đầy đủ ("Ăn uống 2.738.000 ₫, kỳ trước 1.025.000 ₫, tăng 1.713.000 ₫"). Ba phần của thanh khác nhau bằng hoa văn, phần nào cũng có chữ trong dòng chi tiết.

### B2. Hũ nào sắp cạn trước kỳ lương

- **Câu hỏi**: "Hũ nào sắp cạn?", "Còn mấy ngày nữa thì hết?"
- **Loại**: đường băng (một thanh ngang mỗi hũ, trục là các ngày từ hôm nay tới kỳ lương). Đoạn còn tiền tô màu đủ; từ ngày cạn tới kỳ lương là đoạn hụt gạch chéo có chấm tròn ở ngày cạn; hũ sát có viền và biểu tượng cảnh báo. Mốc nghĩa vụ sắp đến (tiền điện 26/11, Trả sau 05/12) là vạch nhỏ trên đúng hũ trả. Đây là bản nhiều hũ của `MiniTimeline` sẵn có.
- **Dữ liệu**: `GET /overview`: `jars[].status`, `runout_date`, `balance_vnd`, `kind`; `next_payday.date`; `obligations_due[]` (`due_date`, `pay_jar`, `amount_vnd`, `amount_min_vnd`/`amount_max_vnd`). Không cần đổi hợp đồng. Chỉ hiện hũ `spending` và `obligation`; hũ `saving` không "cạn" theo nghĩa này.
- **Màn**: đầu tab Dự báo (`/foresight`), nơi hũ đã được xếp theo mức cần chú ý (`SEVERITY`). Bản rút gọn (chỉ hũ hụt và sát) ở Tổng quan.
- **Tương tác**: chạm một hàng mở Chi tiết hũ (`/jars/:code`) với ForecastBlock đầy đủ. Không kéo (chi tiết từng ngày đã có ở ForecastBlock).
- **Thiếu dữ liệu**: dự báo `stale` thì chip "Số liệu cũ" ở đầu thẻ (cờ `forecast.stale` của Overview); `is_initial_estimate` thì chip "Ước lượng ban đầu"; hũ chưa có dự báo (`status` vắng) thì hàng xám "Chưa có dự báo" thay vì vẽ đầy. Tài khoản trắng (`jars` rỗng): không hiện thẻ.
- **Khả năng tiếp cận**: mỗi hàng là `<li>` với chữ "Ăn uống: hụt, dự kiến cạn 23/11, 12 ngày trước kỳ lương 05/12". Màu đủ, sát, hụt luôn kèm biểu tượng (dấu tích, tam giác, mũi tên xuống) và chữ.

### B3. Cuối tuần mình có tiêu nhiều không (và chi dồn sau ngày lương)

- **Câu hỏi**: "Cuối tuần mình tiêu nhiều không?", "Mình có tiêu hết tiền ngay khi lương về không?"
- **Loại**: hai thanh tỷ lệ chồng nhau trong thẻ nhận xét: thanh trên là phần chi (37%), thanh dưới là phần số ngày (26%) làm mốc "nếu chi đều". Khoảng chênh được ghi bằng chữ ("nhiều hơn 11 điểm phần trăm"). Cùng mẫu cho nhịp lương (40% chi trong 30% số ngày) và buổi tối.
- **Dữ liệu**: `GET /profile/behavior` và khối `behavior_insight`. Batch đêm đã phát cặp bằng chứng `weekend_share` / `weekend_day_share` và `first_week_share` / `first_week_day_share` (đơn vị `percent`). P0 không đổi hợp đồng: giao diện ghép cặp theo bảng khóa cố định trong `features/behavior/format.ts`. P1 thêm trường tùy chọn `compare_key` vào `BehaviorEvidence` (mục 4.1) để khỏi phụ thuộc quy ước đặt tên.
- **Màn**: Hồ sơ, mục "Nhận xét hành vi" (`BehaviorSection`), và trong chat (cùng `BehaviorInsightCard`).
- **Tương tác**: không cần; bấm "Thực hiện" của việc cần làm đi luồng xác nhận sẵn có.
- **Thiếu dữ liệu**: `ready` sai thì thanh tiến độ "đã có 12 trong 21 ngày cần" từ `history_days` và `min_history_days`, kèm `headline` của server ("Cần thêm 9 ngày..."). Nhận xét không có cặp bằng chứng phù hợp thì giữ bảng số như hiện nay.
- **Khả năng tiếp cận**: hai thanh là `role="img"` với nhãn "Phần chi cuối tuần 37%, phần số ngày cuối tuần 26%"; bảng bằng chứng hiện có vẫn giữ nguyên bên dưới làm bản tương đương.

### B4. Chi theo thứ trong tuần (bản đầy đủ của B3)

- **Câu hỏi**: "Thứ mấy mình tiêu nhiều nhất?"
- **Loại**: 7 cột (T2 đến CN), chiều cao là trung bình chi mỗi ngày đó; phần Trả sau chồng trên cột bằng hoa văn chấm; đường ngang mảnh là trung bình mỗi ngày của cả kỳ (143.723 ₫). Cột T7, CN có nhãn "Cuối tuần" bên dưới, không tô màu khác.
- **Dữ liệu**: cần thêm vào `BehaviorFeatures` (tùy chọn, không tăng `v`): `weekday_avg_vnd` (mảng 7 số nguyên, ISO thứ Hai trước) và `weekday_credit_avg_vnd` (phần Trả sau). Batch đã tính `avg_by_weekday` trong [behavior.py](../../ml/yofina_ml/behavior.py); thêm phần Trả sau là một phép lọc. Để vẽ trong chat cần đưa dãy này vào nhận xét (`BehaviorInsight.series`, mục 4.1), vì `BehaviorInsightData` không mang `features`.
- **Màn**: Hồ sơ, mở rộng thẻ nhận xét `weekday_pattern`; trong chat khi người dùng hỏi "thứ mấy mình tiêu nhiều".
- **Tương tác**: chạm cột đọc số vào dòng `aria-live` ("Thứ Hai: trung bình 251.429 ₫, trong đó Trả sau 138.143 ₫"). Phím mũi tên khi cột có tiêu điểm.
- **Thiếu dữ liệu**: thứ nào chưa có ngày nào trong cửa sổ thì cột rỗng có chữ "chưa có"; hồ sơ chưa sẵn sàng như B3.
- **Khả năng tiếp cận**: bảng `sr-only` 7 hàng (thứ, trung bình, phần Trả sau). Lý do thứ Hai cao (Trả sau) phải hiện bằng chữ dưới biểu đồ, không để người xem tự suy từ hoa văn.

### B5. So với kỳ trước (đường lũy kế)

> Đã làm 25/11 (`p5/viz-p1`), xem ghi chú dưới bảng tóm tắt.

- **Câu hỏi**: "Tháng này mình tiêu nhiều hơn tháng trước không?", "Nếu cứ thế này thì cuối kỳ hết bao nhiêu?"
- **Loại**: hai đường lũy kế theo ngày của kỳ lương (ngày 1 là ngày lương): kỳ này đường đậm màu nhấn, kỳ trước đường đứt xám kéo hết kỳ. Mặc định là chi thường ngày (bỏ nghĩa vụ cố định) để tiền nhà ngày 6 không lấn cả biểu đồ. Điểm cuối kỳ này có nhãn số. Mẫu này giống Copilot.
- **Dữ liệu**: cần thêm `daily[]` vào `GET /cashflow` (`{date, spent_vnd, obligation_vnd}`, tối đa 62 phần tử, có cho cả `previous`). Server cộng dồn hay giao diện cộng dồn từ `daily` đều được; đề xuất server trả cả `cumulative_vnd` để giao diện không tự cộng tiền.
- **Màn**: Hoạt động, ngay dưới B1 (chuyển qua lại bằng hai chip "Theo hũ" và "Theo ngày" để không dài màn).
- **Tương tác**: chạm hoặc kéo thanh `range` dưới biểu đồ chọn ngày của kỳ; dòng đọc số "Ngày 9 của kỳ: kỳ này 2.436.000 ₫, kỳ trước 760.000 ₫". Dùng lại cách làm của ForecastBlock (`activeX`, `onActiveChange`).
- **Thiếu dữ liệu**: không có kỳ trước thì chỉ vẽ một đường và ghi rõ; kỳ mới bắt đầu (ngày 1 đến 2) thì ẩn biểu đồ, chỉ hiện số.
- **Khả năng tiếp cận**: `figcaption` "Đến ngày 17 của kỳ bạn chi thường ngày 4.408.000 ₫, kỳ trước cùng thời điểm 1.267.000 ₫". Đường kỳ trước khác kỳ này cả về nét (đứt) lẫn màu. Recharts 3 bật `accessibilityLayer` mặc định (Tab vào biểu đồ, phím mũi tên đi từng điểm) ([release v3.0.0](https://github.com/recharts/recharts/releases/tag/v3.0.0)); với VoiceOver người dùng phải tắt QuickNav ([wiki Recharts](https://github.com/recharts/recharts/wiki/Recharts-and-accessibility)), nên thanh `range` vẫn là đường chính.

### B6. Đã dùng Trả sau bao nhiêu

- **Câu hỏi**: "Đã dùng Trả sau bao nhiêu?", "Đến hạn có đủ tiền trả không?"
- **Loại**: một thanh hạn mức (đã dùng 967.000 trên 5.000.000 ₫, còn 4.033.000 ₫), bên dưới hai thanh so sánh ngày đến hạn 05/12: "phải trả 1.000.000 ₫ (gốc 967.000 + phí 33.000)" và "hũ Nghĩa vụ đang có 1.000.000 ₫". Một dòng chữ từ hồ sơ hành vi: "47 ngày qua 2 lần, 14% chi tiêu".
- **Dữ liệu**: `GET /credit-line` (`limit_vnd`, `outstanding_vnd`, `available_vnd`, `fees`), `GET /obligations` khoản `kind = bnpl` (`amount_vnd`, `principal_vnd`, `fee_vnd`, `due_date`, `pay_jar`), số dư hũ trả từ `GET /overview`, `features.bnpl_share` và bằng chứng `bnpl_count`. Không đổi hợp đồng.
- **Màn**: màn Nghĩa vụ (`ObligationsPage`), thay dải ba số trong thẻ `credit-line` hiện có; thẻ nhỏ ở Tổng quan khi có dư nợ.
- **Tương tác**: chạm thẻ mở danh sách khoản Trả sau; nếu hũ trả không đủ thì nút "Chuyển thêm vào hũ Nghĩa vụ" đi luồng `move_between_jars` có xác nhận.
- **Thiếu dữ liệu**: không có hạn mức (`CreditLineResponse.none`): không hiện thẻ. Có hạn mức nhưng chưa dùng: thanh rỗng, chữ "Chưa dùng Trả sau". `suspended`: chip "Tạm khóa".
- **Khả năng tiếp cận**: `<meter>` hoặc `role="img"` với nhãn đủ ba số; trạng thái đủ hay thiếu khi đến hạn bằng chữ và biểu tượng. Từ trên giao diện là "Trả sau (mô phỏng)" như `product_label` (bundle check cấm chữ "Ví Trả Sau").

### B7. Thu và chi của kỳ

> Đã làm 25/11 (`p5/viz-p1`), xem ghi chú dưới bảng tóm tắt.

- **Câu hỏi**: "Lương về bao nhiêu, đã tiêu bao nhiêu, còn bao nhiêu?"
- **Loại**: một thanh chồng ngang: lương 9.000.000 ₫ là cả thanh, phần đã chi 6.908.000 ₫, phần còn lại; dòng phụ "Tiền vào khác 350.000 ₫ (không tính là thu nhập)" để khớp quy ước của hợp đồng.
- **Dữ liệu**: `GET /cashflow` (B1): `salary_income_vnd`, `other_income_vnd`, `spent_vnd`. Phần "còn lại" do server trả (thêm `net_vnd` tùy chọn), không để giao diện trừ.
- **Màn**: Hoạt động, trên B1; hoặc trong thẻ số dư ở Tổng quan.
- **Tương tác**: không.
- **Thiếu dữ liệu**: kỳ chưa có lương (lương chờ xác nhận) thì ghi "Lương kỳ này chưa xác nhận" và chỉ vẽ phần đã chi.
- **Khả năng tiếp cận**: câu tóm tắt đủ ba số; thanh `aria-hidden`.

### B8. Giờ nào mình hay tiêu

- **Câu hỏi**: "Mình hay tiêu vào buổi tối không?"
- **Loại**: 4 thanh ngang theo khung giờ (sáng 5 đến 11, trưa 11 đến 14, chiều 14 đến 18, tối 18 đến 23), có mốc phần số giờ như B3. Tránh biểu đồ tròn 24 giờ: khó đọc trên 390 px.
- **Dữ liệu**: hiện chỉ có `evening_share` (35%). Cần thêm `features.hour_bucket_share` (4 tỷ lệ). Chỉ tính giao dịch trong ví, vì dòng ngoài ví không có giờ thật (đã ghi trong schema).
- **Màn**: Hồ sơ, thẻ nhận xét `time_of_day`.
- **Tương tác**, **thiếu dữ liệu**, **khả năng tiếp cận**: như B3.

### B9. Tiêu nhiều nhất ở đâu

- **Câu hỏi**: "Mình tiêu nhiều nhất ở quán nào?"
- **Loại**: danh sách năm nơi chi nhiều nhất, mỗi dòng có thanh mảnh (Cơm tấm Cô Ba 542.000 ₫, Lazada 520.000 ₫ bằng Trả sau, Tiki 447.000 ₫ bằng Trả sau, GrabFood 431.000 ₫, Gong Cha 400.000 ₫ kỳ này).
- **Dữ liệu**: cần thêm `by_merchant[]` (tối đa 5: `merchant`, `spent_vnd`, `tx_count`, `credit_vnd`) vào `GET /cashflow`, có lọc theo `jar`. Không cộng trên máy khách.
- **Màn**: sheet mở khi chạm một thanh ở B1 (trước khi lọc danh sách).
- **Thiếu dữ liệu**: dòng không có `merchant` gộp thành "Khác".
- **Khả năng tiếp cận**: danh sách thật, thanh `aria-hidden`.

## 4. Biểu đồ trong chat

Nguyên tắc của hợp đồng: thêm trường tùy chọn thì không tăng `v`; Zod phía đọc bỏ trường lạ nên frontend cũ vẫn chạy; khối lạ hiện `fallback_text` ([contracts/README.md](../../contracts/README.md)). Vì vậy:

### 4.1 Mở rộng `behavior_insight` (không phá hợp đồng)

- **P0, chỉ đổi giao diện**: `BehaviorInsightCard` vẽ thanh tỷ lệ cho cặp bằng chứng `percent` đã biết (`weekend_share` với `weekend_day_share`, `first_week_share` với `first_week_day_share`). Không cặp thì giữ bảng. Thẻ ở chat và ở Hồ sơ cùng đổi vì dùng chung component.
- **P1, thêm hai trường tùy chọn** vào `behavior_insight.schema.json`:

```json
"BehaviorEvidence": {
  "properties": {
    "compare_key": {
      "description": "Tùy chọn. key của bằng chứng khác trong CÙNG nhận xét dùng làm mốc so (ví dụ weekend_share so với weekend_day_share). Cùng đơn vị. Pydantic kiểm key tồn tại.",
      "type": "string", "pattern": "^[a-z][a-z0-9_]{0,31}$"
    }
  }
},
"BehaviorInsight": {
  "properties": {
    "series": {
      "description": "Tùy chọn. Dãy số do code dựng để vẽ (không dùng để kiểm số của headline).",
      "type": "object", "required": ["kind", "points"], "additionalProperties": false,
      "properties": {
        "kind": { "enum": ["weekday_avg", "hour_bucket"] },
        "points": {
          "type": "array", "minItems": 1, "maxItems": 7,
          "items": {
            "type": "object", "required": ["x", "value_vnd"], "additionalProperties": false,
            "properties": {
              "x": { "type": "integer", "minimum": 1, "maximum": 7 },
              "value_vnd": { "$ref": "envelope.schema.json#/$defs/Vnd" },
              "credit_vnd": { "$ref": "envelope.schema.json#/$defs/Vnd" }
            }
          }
        }
      }
    }
  }
}
```

  `series` không tham gia NumericGrounding: câu `headline` vẫn chỉ được dùng số trong `evidence`. Giới hạn `maxItems` 6 của `evidence` giữ nguyên.

### 4.2 Không mở rộng `jar_summary`

`jar_summary` là **số dư hiện tại** (nguồn `get_jar_balances`). Thêm "đã chi kỳ này" vào đó trộn hai nguồn và hai nghĩa vào một khối, và làm hai nơi đọc cùng khối hiểu khác nhau. Việc làm được mà không đổi hợp đồng: vẽ `jar_summary` thành thanh số dư ngang (thay danh sách số) ở P2.

### 4.3 Khối mới `spending_breakdown` (P1)

Câu "tháng này tiêu vào đâu" trong chat hiện chỉ trả lời bằng chữ, dù agent đã có `get_cashflow_summary`. Đề xuất khối mới, dựng bằng code từ kết quả tool (LLM không viết số), cùng component với B1:

```json
{
  "v": 1,
  "id": "spending_breakdown:{trace_id}:{from_date}:{to_date}",
  "type": "spending_breakdown",
  "trace_id": "...",
  "fallback_text": "Kỳ lương 05/11 đến 21/11 bạn đã chi 6.908.000 ₫, nhiều nhất ở Ăn uống 2.738.000 ₫.",
  "source": { "tool": "ledger___get_cashflow_summary", "as_of": "...", "app_date": "2026-11-21" },
  "data": {
    "headline": "Kỳ này bạn đã chi 6.908.000 ₫, nhiều hơn kỳ trước cùng thời điểm 3.141.000 ₫.",
    "period": { "from_date": "2026-11-05", "to_date": "2026-11-21", "kind": "pay_period", "day_index": 17 },
    "spent_vnd": 6908000,
    "salary_income_vnd": 9000000,
    "other_income_vnd": 350000,
    "unclassified_pending_vnd": 180000,
    "by_jar": [
      { "jar": "an_uong", "name": "Ăn uống", "color_key": "violet", "icon_key": "utensils",
        "spent_vnd": 2738000, "tx_count": 64, "obligation_vnd": 0, "credit_vnd": 0, "previous_spent_vnd": 1025000 }
    ],
    "previous": { "from_date": "2026-10-05", "to_date": "2026-10-21", "spent_vnd": 3767000 },
    "daily": [ { "date": "2026-11-05", "spent_vnd": 155000, "obligation_vnd": 0 } ]
  }
}
```

Ràng buộc đề xuất: `by_jar` tối đa 20 (bằng `jar_summary`), `daily` tối đa 62, mọi tiền là `Vnd` số nguyên, `period.kind` thuộc `pay_period` hoặc `custom`, `previous` và `previous_spent_vnd` cùng có hoặc cùng vắng (Pydantic kiểm), `headline` do mẫu câu của code điền. Việc cần làm: thêm schema vào `contracts/blocks/` và `block.schema.json`, model và `build_spending_breakdown` trong `libs/yofina_core/src/yofina_core/blocks.py`, fixture `valid/` và `invalid/`, sinh lại Zod (`scripts/gen_contracts.mjs`, thêm vào `REGISTERED_BY_FRONTEND` cùng lúc đăng ký view trong `frontend/src/blocks/registry.tsx`). Frontend cũ gặp khối này hiện `fallback_text`.

## 5. Chọn thư viện

| Lựa chọn | Kích thước gzip | Vẽ bằng | Khả năng tiếp cận | Hợp với |
|---|---|---|---|---|
| HTML, CSS và SVG tự vẽ | 0 KB thêm | DOM, SVG | Tốt nhất: danh sách, bảng, `meter` là phần tử thật; repo đã có tiền lệ (MiniTimeline, ResilienceGauge, JarGlass) | B1, B2, B3, B6, B7, B8, B9 |
| **Recharts 3.11 (đang dùng)** | khoảng 118 KB, đã tải lười trong chunk của ForecastChart (đo ở spike) | SVG | `accessibilityLayer` bật mặc định từ v3 (Tab, phím mũi tên); `title`/`desc`; VoiceOver cần tắt QuickNav | B4, B5 (trục, đường, chồng cột, chọn điểm) |
| visx (`@visx/xychart`) | khoảng 49 KB theo [ApexCharts, State of JS charting 2026](https://apexcharts.com/blog/state-of-javascript-charting-2026/) (chưa đo trong repo) | SVG | Tự làm hết | Không cần: Recharts đã làm được |
| Chart.js | không đo; canvas | Canvas | Phải tự gắn ARIA và nội dung dự phòng trong thẻ canvas ([tài liệu Chart.js](https://chartjs.org/docs/latest/general/accessibility.html)) | Không |
| uPlot | khoảng 22 KB theo [PR nicegui](https://github.com/zauberzeug/nicegui/pull/5917/changes) | Canvas | Yếu, chỉ chuỗi thời gian | Không |
| ECharts bản tối giản | khoảng 135 KB theo [Strapi](https://strapi.io/blog/chart-libraries) | Canvas hoặc SVG | Có mô tả tự động | Không: nặng hơn và thêm một thư viện thứ hai |

**Quyết định đề xuất: không thêm thư viện.** Biểu đồ dạng thanh và tỷ lệ vẽ bằng HTML và CSS (chạy ngay trong chunk đầu, không chờ chunk Recharts, đọc tốt bằng trình đọc màn hình). Chỉ B4 và B5 dùng Recharts, đặt trong một chunk tải lười như ForecastChart (`lazy(() => import('./SpendingTrendChart'))`), Vite gom chung phần Recharts nên không tốn thêm 118 KB lần nữa. Lưu ý từ spike: đã có CSS ẩn khung focus `.recharts-surface:focus`; khi bật điều hướng bàn phím thì đổi thành `:focus:not(:focus-visible)` để người dùng bàn phím vẫn thấy tiêu điểm.

## 6. Ưu tiên cho buổi demo

Công tính bằng người-ngày của một người đã quen repo, gồm test (Vitest cho frontend; pytest hợp đồng cho phần schema). Việc chạm AWS thật (thêm route HTTP API, deploy Lambda ledger, chạy lại batch hành vi) phải hỏi chủ dự án trước theo CLAUDE.md.

### P0: làm được ngay, không đổi hợp đồng (khoảng 2 ngày)

| Việc | File, component | Công |
|---|---|---|
| B2 đường băng các hũ | Mới `frontend/src/features/spending/JarRunway.tsx` (mở rộng ý của `components/MiniTimeline.tsx`); dùng ở `pages/ForesightPage.tsx` (đầu danh sách) và bản rút gọn ở `pages/OverviewPage.tsx` | 0,75 |
| B3 thanh tỷ lệ trong thẻ nhận xét | Mới `frontend/src/features/behavior/EvidenceBars.tsx`; sửa `features/behavior/BehaviorInsightCard.tsx`, `features/behavior/format.ts` (bảng cặp khóa); tự có ở `features/profile/BehaviorSection.tsx` và khối chat `blocks/phase5Views.tsx` | 0,5 |
| B6 Trả sau đã dùng | Mới `frontend/src/features/spending/CreditUsage.tsx`; thay dải số trong `pages/ObligationsPage.tsx`; thẻ nhỏ ở `pages/OverviewPage.tsx` | 0,5 |
| Kiểm tương phản ba màu yếu khi tô thanh (viền 1 px) | `frontend/src/index.css` (biến `--chart-*` hoặc lớp viền), phối hợp với `ui-design-review.md` | 0,25 |

### P1: cần mở rộng hợp đồng tương thích ngược (khoảng 5,5 ngày)

| Việc | File, component | Công |
|---|---|---|
| `GET /cashflow` (bản REST của tool) kèm `obligation_vnd`, `credit_vnd`, `previous`, `daily[]` | `contracts/rest/openapi.yaml`, `contracts/tools/ledger.results.schema.json` (`CashflowJar`, `GetCashflowSummaryOk`), fixture `contracts/fixtures/rest/CashflowResponse.*.json`; SQL mới hoặc bản thay `app_get_cashflow_summary` (migration mới trong `db/migrations/`); `gateway/tools/ledger/yofina_ledger/rest_api.py`, `wallet_reads.py`, `repo_wallet.py`; route trong `infra-cdk/lib/tools-stack.ts`; `frontend/src/api/client.ts`, `api/schemas.ts`; test `tests/unit/test_contracts_rest.py` | 2 |
| B1 chi theo hũ và B7 thu chi kỳ | Mới `frontend/src/features/spending/SpendingByJar.tsx`, `PeriodCashflow.tsx`; sửa `pages/ActivityPage.tsx`; thẻ thu gọn ở `pages/OverviewPage.tsx` | 1 |
| B5 lũy kế so với kỳ trước | Mới `frontend/src/features/spending/SpendingTrendChart.tsx` (Recharts, tải lười) và `SpendingTrend.tsx` (câu tóm tắt, thanh kéo, dòng đọc số); ở `pages/ActivityPage.tsx` | 1 |
| B4 theo thứ trong tuần | `ml/yofina_ml/behavior.py` (`weekday_avg_vnd`, `weekday_credit_avg_vnd`, `series`), `pipelines/forecast/yofina_forecast/behavior.py` nếu cần nối; `contracts/blocks/behavior_insight.schema.json` (`BehaviorFeatures`, `compare_key`, `series`), `libs/yofina_core/src/yofina_core/blocks.py` (`BehaviorFeatures`, `BehaviorEvidence`, `BehaviorInsight`); sinh lại `frontend/src/contracts/blocks.ts`; mới `features/behavior/WeekdayBars.tsx` | 1,5 |

### P2: sau demo (khoảng 4,5 ngày)

| Việc | File, component | Công |
|---|---|---|
| Khối chat `spending_breakdown` | `contracts/blocks/spending_breakdown.schema.json`, `block.schema.json`, `libs/yofina_core/src/yofina_core/blocks.py`, nối trong agent (nơi bọc kết quả tool thành khối), `scripts/gen_contracts.mjs`, `frontend/src/blocks/registry.tsx` và view dùng lại `SpendingByJar` | 2 |
| B8 khung giờ | `ml/yofina_ml/behavior.py` (`hour_bucket_share`), schema như B4, view trong `features/behavior/` | 1 |
| B9 nơi chi nhiều nhất | `by_merchant[]` trong `GET /cashflow` (SQL, ledger, schema), sheet trong `features/spending/` | 1 |
| `jar_summary` vẽ thành thanh số dư | `blocks/views.tsx` (view `JarSummaryView`) | 0,5 |

Nếu chỉ còn một ngày trước demo: làm P0 (B2, B3, B6). Ba biểu đồ này trả lời "hũ nào sắp cạn", "cuối tuần có tiêu nhiều không", "đã dùng Trả sau bao nhiêu" bằng dữ liệu đang chạy trên AWS, không cần deploy backend. "Tiêu vào đâu" và "so với tháng trước" cần `GET /cashflow`, tức một lần deploy ledger và một route mới.

## 7. Bản minh họa

[spending-visualization-preview.html](spending-visualization-preview.html): hai khung 390 px (sáng, tối) với bốn thẻ B1, B2, B3 (dạng thẻ nhận xét, cũng là hình dạng trong chat), B6, vẽ bằng HTML và CSS thuần như đề xuất ở mục 5, bảng màu theo biến của `frontend/src/index.css`. Mỗi thẻ có câu kết luận, nhãn trực tiếp, hoa văn cho Trả sau và khoản cố định, bản tương đương cho trình đọc màn hình. Số là của persona `minh` (mục 1.4) và chỉ nằm trong tài liệu, không được đưa vào mã frontend.

## 8. Câu hỏi còn mở

1. Mặc định B1 có gồm khoản cố định không? Đề xuất: gồm (khớp `spent_vnd` của server và tổng ví), có chip ẩn. B5 thì mặc định bỏ.
2. Cảnh 5 (persona `vy`) có cần biểu đồ đổi sau khi nạp sao kê không? Nếu có thì `external_spent_vnd` theo hũ phải vào P1.
3. Có hiệu chỉnh spec `minh` để kỳ này không gấp 3,5 lần kỳ trước không (mục 1.4)?
