# data/personas/classify_labels/

Nhãn k-NN **seed** của persona (`tx_embeddings_labeled`, nguồn `seed`) cho phân hũ tự động (F2, phase 4 luồng B, nhiệm vụ N4).

| Tệp | Nội dung |
|---|---|
| `base_vocabulary.json` | Từ vựng gốc dùng chung (tên cửa hàng và dịch vụ phổ biến theo hũ mặc định). Dữ liệu soạn tay |
| `<persona>.json` | (SINH RA, chưa có: cần Bedrock) nhãn của persona = cửa hàng trong `specs/<persona>.json` cộng từ vựng gốc của các hũ persona có; mỗi nhãn là chuỗi đã chuẩn hóa, mã hũ và vector 1024 chiều (float16 little-endian, base64) |

Sinh bằng `uv run python evals/classification/build_seed_labels.py` (gọi embedding THẬT). Nạp vào Aurora bằng `yofina_ledger.classify_seed.apply_seed_labels(db, user_id, persona)` SAU khi đặt lại demo (bảng nhãn có khóa ngoại tới hũ nên đặt lại xóa nhãn cùng hũ); chưa có file thì hàm trả 0 và không lỗi. Nạp KHÔNG gọi Bedrock.
