# AI-log — nhật ký thay đổi của AI

Nơi AI agent ghi lại **mỗi lần thêm/sửa/xóa** gì trong project, để người và agent sau biết đã có gì, vì sao, dựa trên nguồn nào. AI-log là **lịch sử** (chỉ thêm, không sửa lại entry cũ); trạng thái hiện tại nằm ở [../../HANDOFF.md](../../HANDOFF.md).

## Quy ước

- Một file mỗi tháng: `YYYY-MM.md` (ví dụ [2026-11.md](2026-11.md)). Sang tháng mới thì tạo file mới.
- **Entry mới nhất ở trên cùng** của file.
- Mỗi lần làm việc có thay đổi file/thư mục là một entry (gộp nhiều thay đổi cùng một yêu cầu vào một entry).
- Mỗi entry gồm: ngày giờ, ai/agent nào (model), yêu cầu là gì, đã thay đổi gì (file/thư mục), lý do, nguồn tài liệu đã tra (link), việc còn dở/lưu ý.
- Chỉ ghi thao tác tạo/sửa/xóa; đọc và tra cứu thì ghi vào mục "Nguồn đã tra". Thao tác lên tài nguyên AWS thật (nếu được phép) cũng ghi vào đây.
- Không ghi bí mật, account ID, token, thông tin cá nhân.
- Dùng giờ địa phương kèm múi giờ (hiện tại +07:00).

## Template (copy xuống đầu file tháng, ngay dưới dòng tiêu đề)

```markdown
## YYYY-MM-DD HH:MM (+07) — Tiêu đề ngắn

- **Ai/agent**: tên agent (model, ví dụ Claude Sonnet 5.5) / tên người
- **Yêu cầu**: ...
- **Đã thay đổi**:
  - `đường/dẫn/file` — tạo mới | sửa | xóa: nội dung ngắn gọn
- **Lý do**: ...
- **Nguồn đã tra**:
  - [Tên](https://...) — điều rút ra
- **Còn dở / lưu ý**: ...
```

---
