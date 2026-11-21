# data/

Dữ liệu tổng hợp cho demo, backtest và kiểm thử (proposal §7, §13).

- `personas/`: (phase 1 đã có bản tối thiểu: `minh`, `lan`, `khoa`, 47/47/18 ngày lịch sử; xem [personas/README.md](personas/README.md)) bộ sinh dữ liệu cho 3 persona (persona demo: Minh, 22 tuổi, thu nhập 9 triệu, lương ngày 5, 7 hũ, một hạn mức Ví Trả Sau). Mỗi persona có hồ sơ khai báo (lương, chi phí cố định, khoản vay, mục tiêu) và 12 tháng giao dịch: lương theo kỳ, hóa đơn định kỳ, chi tiêu theo nhịp lương và tuần, khoản trả sau, cú sốc, và một điểm gãy lối sống cài sẵn.
- Hiệu chỉnh persona theo số công khai; demo chỉ dùng dữ liệu tổng hợp, không dữ liệu thật. File dữ liệu lớn không commit (xem `.gitignore`).