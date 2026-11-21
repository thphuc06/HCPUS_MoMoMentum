# Spike: gọi model Bedrock thật

Kết quả và phân tích: [docs/research/spike-bedrock-models.md](../../docs/research/spike-bedrock-models.md). Thư mục này chỉ chứa script và dữ liệu thô. Chỉ gọi model (Converse/InvokeModel) và API đọc; không tạo/sửa/xóa tài nguyên AWS. Dữ liệu thử hoàn toàn hư cấu.

## Chuẩn bị

```powershell
cd c:\moMo\spikes\bedrock-models
uv venv .venv
uv pip install --python .venv\Scripts\python.exe boto3 "botocore[crt]" pillow numpy
$env:PYTHONUTF8 = "1"        # in tiếng Việt ra console Windows
```

`botocore[crt]` cần khi đăng nhập bằng `aws login`. Credential và region lấy từ AWS CLI đã đăng nhập; mỗi script nhận region qua tham số.

## Chạy (mỗi lệnh dùng `.venv\Scripts\python.exe`)

| Script | Việc | Ví dụ |
|---|---|---|
| `00_discover.py` | Liệt kê model, inference profile | `00_discover.py ap-southeast-1` |
| `01_quota_zero.py`, `01b_other_models.py` | Mục 1: lỗi khi quota = 0 (không retry) | `01_quota_zero.py us-east-1` |
| `02_latency.py` | Mục 2: TTFT và tổng, 3 lần | `02_latency.py ap-southeast-1 haiku45,sonnet46` |
| `07_quotas.py`, `07b_join.py` | Quota theo model (Service Quotas) ghép với danh sách model | `07_quotas.py us-east-1` rồi `07b_join.py` |
| `08_probe.py` | Thăm dò mọi ứng viên: tiếng Việt, tool, structured output | `08_probe.py us-east-1 us` (nhóm `ap` hoặc `us`) |
| `03_tooluse.py` | Mục 3: `IntentResult` 5 câu, ép tool và `outputConfig` | `03_tooluse.py us-east-1 qwen.qwen3-next-80b-a3b` |
| `04_caching.py` | Mục 4: `cachePoint`, JSON `{"model": [số đoạn mục tiêu]}` | `04_caching.py ap-southeast-1 '{"haiku45":[2695]}'` |
| `05_make_images.py`, `05_images.py` | Mục 5: tạo 3 ảnh giả lập, trích JSON, chấm | `05_images.py ap-southeast-1 sonnet46` |
| `06_embeddings.py`, `06b_nova_embed.py` | Mục 6: 43 chuỗi, cosine và 1-NN | `06_embeddings.py` |
| `10_flow.py` | Mô phỏng một lượt what-if (router + planner 2 vòng + diễn giải) | `10_flow.py ap-southeast-1` |
| `12_prices.py` | Tra giá (Price List API) | `12_prices.py AmazonBedrock` |
| `11_report_tables.py` | In bảng markdown từ file JSON | |

Tên ngắn model (`haiku45`, `sonnet46`, `nova2lite`, ...) khai báo trong `common.py`; cũng truyền thẳng được model ID/profile ID.

## Lưu ý khi chạy lại

- Quota Claude 4.x chỉ 10 RPM mỗi model và dùng chung với người/agent khác: script nghỉ giữa các lần gọi và retry khi `ThrottlingException`. Đừng chạy song song nhiều script trên cùng một model Claude.
- Quota = 0 trả `AccessDeniedException` (không phải throttling), vì vậy script không retry lỗi này.
- Kimi K3 không nhận tham số `temperature`.
- File `results_*.json` ghi đè khi chạy lại cùng tham số; bản cũ có hậu tố `_run1`.
- Chi phí cả spike dưới khoảng 0,3 USD (ước tính, xem mục 10 của tài liệu kết quả).
