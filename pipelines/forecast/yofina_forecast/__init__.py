"""Pipeline dự báo của Yofina (phase 2, luồng C): dựng đầu vào từ Aurora, chạy `yofina_ml`, ghi kết quả, phát sự kiện.

Một lõi dùng chung cho batch đêm, đường sự kiện, đặt lại demo và tool `forecast___get_forecast`:
`Pipeline.run_user` (xem `runner.py`). Các Lambda ở thư mục cha chỉ là lớp vỏ mỏng.
"""
