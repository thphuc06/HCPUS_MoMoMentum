### Hiệu chỉnh
| Loại chuỗi | đơn vị (origin x hũ) | rho | level_sigma | phủ 7/14/30 ngày: rho=0, sigma=0 | rho=0,3, sigma=0 | đã chọn |
|---|---|---|---|---|---|---|
| dense | 1201 | 0,00 | 0,25 | 0,74 / 0,70 / 0,62 | 0,82 / 0,77 / 0,71 | 0,82 / 0,81 / 0,80 |
| sparse | 3119 | 0,00 | 0,00 | 0,89 / 0,87 / 0,82 | 0,89 / 0,87 / 0,82 | 0,89 / 0,87 / 0,82 |
| cold_start | 720 | 0,80 | 0,80 | 0,51 / 0,42 / 0,37 | 0,63 / 0,53 / 0,47 | 0,91 / 0,81 / 0,75 |

### Theo ngày
| Họ | Nhóm | n | pinball hurdle thô / SN | pinball sản phẩm (ACI) / SN | trước gãy | sau gãy | phủ ngày SN | phủ ngày hurdle thô | phủ ngày sản phẩm |
|---|---|---|---|---|---|---|---|---|---|
| (i) hurdle-lognormal | hũ dày | 1093 | 0,72 | 0,73 | 0,68 | 0,76 | 0,76 | 0,81 | 0,80 |
| (i) hurdle-lognormal | hũ thưa | 2147 | 0,56 | 0,57 | 0,62 | 0,55 | 0,86 | 0,93 | 0,91 |
| (i) hurdle-lognormal | mọi hũ chi tiêu | 3240 | 0,61 | 0,62 | 0,64 | 0,62 | 0,83 | 0,89 | 0,87 |
| (ii) phiên mua + giỏ hàng | hũ dày | 723 | 0,74 | 0,75 | 0,71 | 0,78 | 0,77 | 0,84 | 0,79 |
| (ii) phiên mua + giỏ hàng | hũ thưa | 2517 | 0,57 | 0,57 | 0,57 | 0,59 | 0,90 | 0,95 | 0,94 |
| (ii) phiên mua + giỏ hàng | mọi hũ chi tiêu | 3240 | 0,60 | 0,60 | 0,59 | 0,63 | 0,87 | 0,93 | 0,91 |
| gộp hai họ | hũ dày | 1816 | 0,72 | 0,74 | 0,69 | 0,77 | 0,76 | 0,82 | 0,80 |
| gộp hai họ | hũ thưa | 4664 | 0,56 | 0,57 | 0,59 | 0,57 | 0,88 | 0,94 | 0,93 |
| gộp hai họ | mọi hũ chi tiêu | 6480 | 0,61 | 0,61 | 0,62 | 0,63 | 0,85 | 0,91 | 0,89 |

### Theo tổng cộng dồn, SAU hiệu chỉnh
| Họ | Nhóm | n | phủ số dư 7 ngày | phủ số dư 14 ngày | phủ số dư 30 ngày | rộng 30 ngày / chi TB |
|---|---|---|---|---|---|---|
| (i) hurdle-lognormal | hũ dày | 1093 | 0,81 | 0,81 | 0,79 | 0,87 |
| (i) hurdle-lognormal | hũ thưa | 2147 | 0,86 | 0,84 | 0,78 | 244876,98 |
| (i) hurdle-lognormal | hũ nghĩa vụ | 540 | 0,83 | 0,80 | 0,81 | - |
| (ii) phiên mua + giỏ hàng | hũ dày | 723 | 0,81 | 0,81 | 0,82 | 0,86 |
| (ii) phiên mua + giỏ hàng | hũ thưa | 2517 | 0,88 | 0,86 | 0,81 | 376086,92 |
| (ii) phiên mua + giỏ hàng | hũ nghĩa vụ | 540 | 0,80 | 0,75 | 0,70 | - |
| gộp hai họ | hũ dày | 1816 | 0,81 | 0,81 | 0,80 | 0,87 |
| gộp hai họ | hũ thưa | 4664 | 0,88 | 0,85 | 0,80 | 315686,46 |
| gộp hai họ | hũ nghĩa vụ | 1080 | 0,82 | 0,77 | 0,76 | - |

### Theo tổng cộng dồn, TRƯỚC hiệu chỉnh
| Họ | Nhóm | n | phủ số dư 7 ngày | phủ số dư 14 ngày | phủ số dư 30 ngày | rộng 30 ngày / chi TB |
|---|---|---|---|---|---|---|
| (i) hurdle-lognormal | hũ dày | 1093 | 0,80 | 0,75 | 0,64 | 0,67 |
| (i) hurdle-lognormal | hũ thưa | 2147 | 0,86 | 0,84 | 0,78 | 244876,98 |
| (i) hurdle-lognormal | hũ nghĩa vụ | 540 | 0,83 | 0,80 | 0,81 | - |
| (ii) phiên mua + giỏ hàng | hũ dày | 723 | 0,83 | 0,80 | 0,76 | 0,73 |
| (ii) phiên mua + giỏ hàng | hũ thưa | 2517 | 0,88 | 0,86 | 0,81 | 376086,92 |
| (ii) phiên mua + giỏ hàng | hũ nghĩa vụ | 540 | 0,80 | 0,75 | 0,70 | - |
| gộp hai họ | hũ dày | 1816 | 0,81 | 0,77 | 0,69 | 0,70 |
| gộp hai họ | hũ thưa | 4664 | 0,88 | 0,85 | 0,80 | 315686,46 |
| gộp hai họ | hũ nghĩa vụ | 1080 | 0,82 | 0,77 | 0,76 | - |

### Chuyển hiệu chỉnh giữa hai họ (phủ số dư 30 ngày)
```json
{
 "hurdle_lognormal -> shopping_sessions": {
  "calibration": {
   "dense": {
    "rho": 0.1,
    "level_sigma": 0.25,
    "probability_ok": false
   },
   "sparse": {
    "rho": 0.0,
    "level_sigma": 0.25,
    "probability_ok": false
   }
  },
  "cov_cum30": {
   "dense": 0.8284518828451883,
   "sparse": 0.8252080856123662
  }
 },
 "shopping_sessions -> hurdle_lognormal": {
  "calibration": {
   "dense": {
    "rho": 0.0,
    "level_sigma": 0.2,
    "probability_ok": false
   },
   "sparse": {
    "rho": 0.0,
    "level_sigma": 0.0,
    "probability_ok": false
   }
  },
  "cov_cum30": {
   "dense": 0.7555555555555555,
   "sparse": 0.7888888888888889
  }
 }
}
```

Xác suất hụt, hũ dày: n = 4035, Brier = 0,161 (chỉ dùng tần suất chung: 0,250), xác suất dự báo TB = 0,428, tần suất thật = 0,480

| khoảng p dự báo | n | p dự báo TB | tần suất thật |
|---|---|---|---|
| 0.0-0.1 | 699 | 0,045 | 0,096 |
| 0.1-0.3 | 1006 | 0,193 | 0,239 |
| 0.3-0.5 | 711 | 0,399 | 0,447 |
| 0.5-0.7 | 638 | 0,598 | 0,674 |
| 0.7-0.9 | 633 | 0,801 | 0,861 |
| 0.9-1.0 | 348 | 0,947 | 0,963 |

Xác suất hụt, hũ thưa: n = 7235, Brier = 0,162 (chỉ dùng tần suất chung: 0,220), xác suất dự báo TB = 0,358, tần suất thật = 0,326

| khoảng p dự báo | n | p dự báo TB | tần suất thật |
|---|---|---|---|
| 0.0-0.1 | 895 | 0,049 | 0,049 |
| 0.1-0.3 | 2467 | 0,202 | 0,141 |
| 0.3-0.5 | 1999 | 0,393 | 0,356 |
| 0.5-0.7 | 1171 | 0,589 | 0,588 |
| 0.7-0.9 | 580 | 0,785 | 0,786 |
| 0.9-1.0 | 123 | 0,942 | 0,919 |

### Độ dài lịch sử
| L (ngày lịch sử) | hurdle theo lịch | seasonal naive | luật khởi đầu lạnh |
|---|---|---|---|
| 7 | 0,70 / 0,91 | 1,00 / 0,77 | 0,67 / 0,94 |
| 14 | 0,69 / 0,92 | 1,00 / 0,79 | 0,64 / 0,94 |
| 21 | 0,66 / 0,92 | 1,00 / 0,82 | 0,66 / 0,94 |
| 30 | 0,64 / 0,91 | 1,00 / 0,83 | 0,67 / 0,94 |
| 45 | 0,63 / 0,91 | 1,00 / 0,84 | 0,67 / 0,94 |
| 60 | 0,62 / 0,91 | 1,00 / 0,85 | 0,68 / 0,94 |
| 90 | 0,61 / 0,91 | 1,00 / 0,85 | 0,67 / 0,94 |

### Ablation hurdle
| Biến thể hurdle | (i) hurdle-lognormal | (ii) phiên mua + giỏ hàng | gộp hai họ |
|---|---|---|---|
| mặc định (nửa đời 180 ngày, co ô về xác suất chung kappa=20, số tiền = hệ số ô x phần dư chung) | 0,64 | 0,63 | 0,63 |
| như spike: Beta(1,2) riêng từng ô, số tiền chung, không giảm trọng số | 0,65 | 0,64 | 0,64 |
| số tiền theo lưới riêng từng ô khi đủ 15 mẫu (cách cũ) | 0,64 | 0,63 | 0,64 |
| không co ô (Beta(1,2) riêng từng ô) | 0,65 | 0,65 | 0,65 |
| nửa đời 45 ngày | 0,64 | 0,63 | 0,64 |
| nửa đời 90 ngày | 0,64 | 0,63 | 0,63 |
| không giảm trọng số theo tuổi | 0,64 | 0,63 | 0,63 |
| cửa sổ 90 ngày | 0,64 | 0,63 | 0,64 |
| không dùng lịch (xác suất và số tiền chung mọi ô) | 0,64 | 0,65 | 0,64 |

### Thời gian chạy
```json
{
 "machine": "Intel64 Family 6 Model 183 Stepping 1, GenuineIntel",
 "python": "3.13.9",
 "numpy": "2.5.5",
 "forecast_user_2000_ms_median": 61.5,
 "forecast_user_2000_ms_max": 70.4,
 "update_forecast_2jars_2000_ms": 9.8,
 "forecast_user_5000_ms_median": 145.2,
 "forecast_user_5000_ms_max": 151.1,
 "update_forecast_2jars_5000_ms": 32.5,
 "forecast_user_10000_ms_median": 265.8,
 "forecast_user_10000_ms_max": 285.6,
 "update_forecast_2jars_10000_ms": 62.7,
 "jars": 7,
 "history_days": 250
}
```
