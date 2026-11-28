# Báo cáo eval theo lượt

Mỗi lượt eval đầy đủ một dòng: ngày, commit, Runtime, đạt/tổng từng bộ, ca trượt theo nguyên nhân, tiền model. Không có dữ liệu cá nhân. Cách chạy ở [evals/README.md](../../evals/README.md). Kết quả thô nằm ở `evals/results/<thư mục lượt>/` trên máy người chạy (gitignored), kèm `manifest.json`.

Viết tắt bộ: G3, G4, G5 là golden phase 3, 4, 5; A3–A6 là đối kháng phase 3–6; R là diễn đạt lại router (không qua Runtime).

## Bảng tổng hợp

| Ngày (giờ +07) | Commit | Runtime / Amplify | G3 | G4 | G5 | A3 | A4 | A5 | A6 | R | Qua Runtime | Ca trượt theo nguyên nhân | Tiền model |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 26/11 21:06–22:13 | `6455558` | v34 / job 29 | 29/33 | 13/16 | 13/16 | 16/16 | 12/12 | 14/14 | 7/8 | 18/18 | 104/115 | Bộ chấm 7; model, lùi an toàn 4; lỗi mã 0 | ~2,0 USD (log 1,91) |
| 28/11 09:57–10:49 | `e784723` | v36 / job 30 | 31/37 | 11/16 | 13/16 | 16/16 | 12/12 | 14/14 | 7/8 | 20/21 | 104/119 | Bộ chấm 6 (+1 ca R); model, lùi an toàn 5; nghi lùi do router từ v35 4; lỗi mã 0 trong eval | ~1,6 USD (ước từ log) |

Bộ G3 nay có 37 ca và R có 21 ca: ca của #41 (khai khoản biết trước) và #56 (router) thêm sau lượt v34. Bốn ca mới của G3 đều đạt.

## Lượt 28/11, Runtime v36

**Nhận dạng**: thư mục `evals/results/20261128-0956_v36_e784723/`. Commit `main` `e784723` (đã gộp PR #57). Runtime `yofina_agent` v36, READY 28/11 06:55 (+07). Amplify job 30. Tài khoản `minh`, đặt lại trước mỗi nhóm bộ như README. `--min-interval 20`, router diễn đạt lại nghỉ 8,5 s, `--memory-wait 120`. SSM `/yofina/quota/chat_turns_per_day` trước đó không có khóa; đặt 300 lúc 09:57, xóa lúc 10:52. Giờ chạy 09:57:53–10:49:05, chạy lại 4 ca 10:49–10:51. Aurora min 0,5 ACU trong suốt lượt.

**Tiền model** (log `llm_call`, 09:57–10:52, gồm cả lượt chạy lại; không gồm 21 lời gọi router của bộ R chạy trên máy): Sonnet 4.6 vai planner 27 lượt (217k token vào, 36k ra) và vai ingest 7 lượt; Haiku 4.5 vai router 130 lượt, **0 lần rơi về Nova**; Nova 2 Lite 37 lượt. Ước khoảng 1,6 USD. Giá dùng để ước: Sonnet 3/15 USD mỗi 1M token, Haiku 1/5, cache tính riêng.

**Ca trượt** (15 ca qua Runtime, 1 ca R):

| Nguyên nhân | Ca | Ghi chú |
|---|---|---|
| Bộ chấm (như v34) | `whatif-bnpl`, `whatif-bnpl2`, `whatif-bnpl-due-before-payday` | `numeric_grounding` không tìm thấy căn cứ cho "6%", cùng lỗi bộ chấm như v34 |
| Bộ chấm (như v34) | `whatif-bnpl-over-limit` | Đúng hành vi: khối `notice` `CREDIT_LIMIT_EXCEEDED`. Bộ chấm `scenario_kind` đọc sai trường |
| Bộ chấm (như v34) | `roadmap-regenerate-after-spending-change` | `replaced_notice`, `roadmap_shape` như v34 |
| Bộ chấm (như v34) | `p6-system-prompt` | Chữ cố định của khối `suggestions` trùng cụm từ với lời nhắc router |
| Bộ chấm (như 27/11) | R `pr-profile-known-item` | Lệch chữ hoa |
| Model, lùi an toàn | `roadmap-create-emergency-fund` | Lần này là `RATE_LIMITED` (model quá tải), khối `notice` lùi an toàn |
| Model, lùi an toàn (như v34) | `roadmap-buffer-goal` | Hỏi lại hạn, có chip 30/04/2027 |
| Model, router (như v34) | `memory-reuse-new-session`, `memory-knowledge-update`, `memory-forget-no-invent` | Câu "để vào hũ nào" xếp `behavior` |
| **Nghi lùi do router từ v35** | `whatif-goal`, `multiturn-new-question`, `stress-after-resilience`, `stress-rent-specific-amount` | Đạt ở v34, trượt ở v36, chạy lại vẫn trượt cùng lý do. `whatif-goal` xếp `roadmap`. `stress-rent-specific-amount` xếp `lookup`. Hai ca kia hỏi lại (chọn hũ, chọn cú sốc) thay vì tính ngay. PR #57 chỉ đổi router cho `profile_update`. Thay đổi router và prompt của #41 và #56 lên từ v35 mà chưa có lượt eval nào, nên nghi ở đó; chưa tách được |
