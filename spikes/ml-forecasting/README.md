# Spike ML / thống kê / tối ưu (chạy local trên CPU)

Kết quả và kết luận: [docs/research/spike-ml-forecasting.md](../../docs/research/spike-ml-forecasting.md). Thư mục này chỉ chứa mã và số thô.
Dữ liệu là **tổng hợp** (persona Minh), nên mọi "model A thắng B" chỉ đúng với bộ sinh trong `gen_data.py`.

## Cách chạy lại (Windows, PowerShell hoặc Git Bash, Python 3.13, uv)

```bash
cd spikes/ml-forecasting
export UV_CACHE_DIR=$PWD/.uv-cache          # cache uv nằm trong thư mục này để xóa gọn
export HF_HOME=$PWD/.hf-cache               # cache model Hugging Face, cũng xóa được

# 1) môi trường chính (torch CPU-only; torch phải cài trước từ index CPU)
uv venv --python 3.13 .venv
uv pip install --python .venv/Scripts/python.exe torch --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv/Scripts/python.exe "statsforecast==2.1.1" chronos-forecasting ruptures river pyod tabulate
#    (hoặc: uv pip install --python .venv/Scripts/python.exe -r requirements-main.txt --extra-index-url https://download.pytorch.org/whl/cpu)

# 2) môi trường tối thiểu chỉ có StatsForecast, để đo kích thước/thời gian import (mục 2)
uv venv --python 3.13 .venv-sf
uv pip install --python .venv-sf/Scripts/python.exe "statsforecast==2.1.1"

# 3) tải model Chronos-2 (478 MB) và small (112 MB) một lần
.venv/Scripts/python.exe -c "from huggingface_hub import snapshot_download as d; d('amazon/chronos-2'); d('autogluon/chronos-2-small')"

export PYTHONIOENCODING=utf-8 HF_HUB_OFFLINE=1
.venv/Scripts/python.exe gen_data.py              # mục 1: data/minh_daily.csv, data/truth.json
.venv-sf/Scripts/python.exe s2_statsforecast.py   # mục 2: dùng .venv-sf
.venv/Scripts/python.exe s4_chronos_probe.py amazon/chronos-2          # mục 4: đo tải/RAM/tốc độ (chạy riêng từng model để RAM đỉnh đúng)
.venv/Scripts/python.exe s4_chronos_probe.py autogluon/chronos-2-small
.venv/Scripts/python.exe s3_backtest.py           # mục 3+4: 31 origin x 12 model -> results/backtest_forecasts.pkl (~45 s)
.venv/Scripts/python.exe s3_metrics.py            # pinball, độ phủ, rho PIT -> results/s3_metrics.md
.venv/Scripts/python.exe s3c_extra.py             # quét rho cho tổng 30 ngày, so sánh từng cặp model
.venv/Scripts/python.exe s5_aci.py                # mục 5: ACI
.venv/Scripts/python.exe s6_mc.py                 # mục 6: Monte Carlo + thời gian
.venv/Scripts/python.exe s7_change.py             # mục 7: ruptures, river, PyOD ECOD
.venv/Scripts/python.exe s8_lp.py                 # mục 8: linprog
.venv/Scripts/python.exe s9_short_history.py      # bổ sung: độ dài lịch sử tối thiểu
.venv/Scripts/python.exe s10_seeds.py             # bổ sung: lặp trên 4 seed khác của bộ sinh
```

PuLP được thử riêng trong một venv dùng một lần (`uv venv .venv-pulp; uv pip install pulp`, rồi `pulp[highs]`), đã xóa sau khi thử.

## File

| File | Việc |
|---|---|
| `gen_data.py` | Bộ sinh dữ liệu: 7 hũ, 365 ngày, seed `20261121`, nhãn sự thật trong `data/truth.json` |
| `common.py`, `forecasters.py` | Hàm dùng chung (pinball, lấy mẫu từ bảng phân vị, ACI score, bảng phân vị từ StatsForecast/Hurdle/Chronos-2) |
| `s2_*` ... `s10_*` | Mỗi mục một script, in bảng ra stdout; bản chụp ở `results/` |
| `results/` | Đầu ra thô (`.txt`, `.md`, `.json`, `.csv`, `.pkl`) |
| `requirements-*.txt` | Phiên bản thực cài được (`uv pip freeze`) |

Kết quả có thể lệch nhẹ ở cột thời gian (tùy máy). Phần còn lại tất định theo seed (đã kiểm: chạy lại backtest cho bảng phân vị y hệt từng bit).
