"""Mục 5a: tạo 3 ảnh PNG giả lập thông báo chuyển khoản tiếng Việt (HOÀN TOÀN HƯ CẤU) + ground truth."""
import json, os
from PIL import Image, ImageDraw, ImageFont
os.makedirs("images", exist_ok=True)
F = "C:/Windows/Fonts/"
def font(name, size): return ImageFont.truetype(F + name, size)

CASES = [
 dict(file="img1_momo_style.png", theme=(166, 26, 120), title="Chuyển tiền thành công", amount="1.250.000đ", rows=[("Người nhận", "NGUYỄN THỊ HOÀI THƯƠNG"), ("Thời gian", "21/11/2026 - 14:35"), ("Lời nhắn", "tien tro thang 11"), ("Mã giao dịch", "89012345678")],
      truth=dict(amount_vnd=1250000, time="2026-11-21 14:35", counterparty="NGUYỄN THỊ HOÀI THƯƠNG", note="tien tro thang 11")),
 dict(file="img2_bank_style.png", theme=(0, 104, 56), title="Biến động số dư", amount="-85.000 VND", rows=[("Đến", "TRẦN ĐỨC MINH"), ("Lúc", "20/11/2026 12:07:41"), ("Nội dung", "CK tien com trua + ca phe"), ("Số dư", "3.482.100 VND")],
      truth=dict(amount_vnd=85000, time="2026-11-20 12:07", counterparty="TRẦN ĐỨC MINH", note="CK tien com trua + ca phe")),
 dict(file="img3_shopee_style.png", theme=(238, 77, 45), title="Thanh toán thành công", amount="₫2.399.000", rows=[("Thanh toán cho", "Công ty TNHH Điện Máy Hoa Sen"), ("Ngày giờ", "19/11/2026 19:48"), ("Nội dung", "Thanh toán đơn hàng #DH5521 - tai nghe"), ("Phương thức", "Ví Trả Sau")],
      truth=dict(amount_vnd=2399000, time="2026-11-19 19:48", counterparty="Công ty TNHH Điện Máy Hoa Sen", note="Thanh toán đơn hàng #DH5521 - tai nghe")),
]
for c in CASES:
    W, H = 720, 960
    im = Image.new("RGB", (W, H), (245, 245, 247)); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 200], fill=c["theme"])
    d.text((40, 60), c["title"], font=font("segoeuib.ttf", 40), fill="white")
    d.text((40, 125), "Ứng dụng demo - dữ liệu hư cấu", font=font("segoeui.ttf", 24), fill=(235, 235, 235))
    d.rounded_rectangle([30, 230, W - 30, 880], radius=24, fill="white")
    d.text((W // 2, 300), c["amount"], font=font("segoeuib.ttf", 64), fill=c["theme"], anchor="mm")
    y = 400
    for k, v in c["rows"]:
        d.text((60, y), k, font=font("segoeui.ttf", 26), fill=(120, 120, 120))
        d.text((60, y + 34), v, font=font("segoeuib.ttf", 30), fill=(30, 30, 30)); y += 105
    d.line([60, y + 10, W - 60, y + 10], fill=(220, 220, 220), width=2)
    d.text((W // 2, y + 60), "Cảm ơn bạn đã sử dụng dịch vụ", font=font("segoeui.ttf", 24), fill=(150, 150, 150), anchor="mm")
    im.save("images/" + c["file"])
json.dump(CASES, open("images/truth.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
print("ok", [c["file"] for c in CASES])
