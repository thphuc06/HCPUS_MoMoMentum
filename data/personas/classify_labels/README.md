# data/personas/classify_labels/

Nhãn k-NN **seed** của persona (`tx_embeddings_labeled`, nguồn `seed`) cho phân hũ tự động (F2, phase 4 luồng B, nhiệm vụ N4).

| Tệp | Nội dung |
|---|---|
| `base_vocabulary.json` | Từ vựng gốc dùng chung (tên cửa hàng và dịch vụ phổ biến theo hũ mặc định). Dữ liệu soạn tay |
| `<persona>.json` | (SINH RA, chưa có: cần Bedrock) nhãn của persona = cửa hàng trong `specs/<persona>.json` cộng từ vựng gốc của các hũ persona có; mỗi nhãn là chuỗi đã chuẩn hóa, mã hũ và vector 1024 chiều (float16 little-endian, base64) |

Sinh bằng `uv run python evals/classification/build_seed_labels.py` (gọi embedding THẬT). Nạp vào Aurora bằng `yofina_ledger.classify_seed.apply_seed_labels(db, user_id, persona)` SAU khi đặt lại demo (bảng nhãn có khóa ngoại tới hũ nên đặt lại xóa nhãn cùng hũ); chưa có file thì hàm trả 0 và không lỗi. Nạp KHÔNG gọi Bedrock. Mã hũ của nhãn là nhóm của bộ bảy hũ; nhãn vào hũ của ví theo cùng quy tắc với bước loại giao dịch (`classify_seed.label_jar_pairs` qua `yofina_core.wallet.transaction_jar`, issue #39): hũ riêng khớp nhóm thắng (kể cả Hóa đơn vào Nghĩa vụ, Du lịch vào hũ goal), không có thì hũ chung Chi hằng ngày hoặc Nghĩa vụ; ví demo có cả Chi hằng ngày lẫn Ăn uống thì nhãn ăn uống vào Ăn uống. Hũ Chi hằng ngày của ví demo chưa có nhãn seed riêng (cần Bedrock để nhúng); phân loại khoản lặt vặt mới dựa vào lịch sử đối tác và nhãn người dùng sửa.
