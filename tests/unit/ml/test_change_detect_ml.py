"""`yofina_ml.change`: z bền MAD, CUSUM tự viết, PELT (ruptures) và các quy tắc xác nhận; cấu hình có nguồn; hiệu chỉnh được khóa."""

from __future__ import annotations

import json
import math
from dataclasses import replace
from datetime import date

import numpy as np
import pytest

from yofina_ml import change as ch

P = ch.load_params()


def weekly_to_daily(weeks, *, per_day_noise=0.0, seed=0):
    """Chuỗi tuần -> chuỗi ngày (mỗi tuần chia đều 7 ngày, có thể thêm nhiễu theo ngày)."""
    rng = np.random.default_rng(seed)
    out = []
    for w in weeks:
        base = np.full(7, w / 7.0)
        if per_day_noise:
            base = base * np.exp(rng.normal(0, per_day_noise, 7))
            base = base * (w / base.sum())
        out.extend(base)
    return np.asarray(out)


def noisy_weeks(level, n, *, cv=0.15, seed=0):
    rng = np.random.default_rng(seed)
    return np.maximum(level * (1 + cv * rng.standard_normal(n)), 1000.0)


def series_of(weeks, **kw):
    return ch.prepare_weekly(weekly_to_daily(weeks, **kw), P)


# --- cấu hình có nguồn --------------------------------------------------------------------------------------
def test_moi_tham_so_co_gia_tri_don_vi_ghi_chu_va_nguon():
    raw = ch.load_raw()
    assert raw["params"]
    for name, spec in raw["params"].items():
        assert set(spec) == {"value", "unit", "note", "source"}, name
        assert spec["note"].strip() and spec["source"].strip() and spec["unit"].strip(), name


def test_tham_so_khop_dataclass_va_khoa_la_bi_tu_choi():
    assert set(P.to_dict()) - {"version"} == set(ch.load_raw()["params"])
    assert P.version == ch.load_raw()["version"]
    with pytest.raises(ValueError, match="lạ"):
        ch.load_params(overrides={"khong_co_tham_so_nay": 1})


def test_hieu_chinh_da_ghi_va_khop_tham_so_hien_tai():
    """Đổi tham số mà không chạy lại hiệu chỉnh thì số đo ghi trong file không còn đúng: bắt ngay."""
    cal = ch.load_raw()["calibration"]
    assert cal["status"] == "da_hieu_chinh"
    snap = cal["params_snapshot"]
    now = P.to_dict()
    assert {k: now[k] for k in snap} == snap
    for det in ("confirm_pelt", "suspect_cusum"):
        block = cal[det]
        assert block["series_eligible"] > 0 and block["obs_jar_years"] > 0
        assert block["fa_per_jar_year"] is not None and block["delay_days_median"] is not None
        out = ch.calibration_for(det)
        assert out["synthetic_only"] is True and out["fa_per_jar_year"] == block["fa_per_jar_year"]
    assert ch.calibration_for("khong_co") == {}


# --- 1. z bền MAD: khoản lớn một lần ------------------------------------------------------------------
def test_z_ben_danh_dau_khoan_lon_mot_lan_va_chi_danh_dau():
    rng = np.random.default_rng(1)
    daily = np.where(rng.random(120) < 0.9, rng.normal(60_000, 8_000, 120), 0).clip(0)
    daily[70] = 1_800_000  # sửa laptop
    z = ch.robust_z(daily)
    assert ch.flag_one_offs(daily, P) == [70]
    assert (
        z[70] > P.one_off_z and z[daily == 0].max() == 0.0
    )  # ngày không chi không bao giờ bất thường
    assert np.all(z[(daily > 0) & (np.arange(120) != 70)] < P.one_off_z)
    clipped = ch.winsorize_daily(daily, P)
    assert (
        clipped[70] < daily[70] / 4 and np.array_equal(np.delete(clipped, 70), np.delete(daily, 70))
    ) or clipped[70] < 1_000_000
    assert clipped.max() <= np.median(daily[daily > 0]) + 6 * 1.4826 * np.median(
        np.abs(daily[daily > 0] - np.median(daily[daily > 0]))
    )


def test_z_ben_chuoi_hang_so_khong_co_bat_thuong():
    assert not ch.flag_one_offs([50_000] * 30, P)
    assert not ch.flag_one_offs([0] * 30, P)
    np.testing.assert_array_equal(ch.winsorize_daily([50_000] * 5, P), [50_000] * 5)


# --- chuỗi tuần ---------------------------------------------------------------------------------------------
def test_tuan_cat_lui_tu_ngay_cuoi_va_bo_tuan_dau_chua_co_chi():
    daily = np.arange(1, 25, dtype=float)  # 24 ngày: 3 tuần đủ, 3 ngày đầu bị bỏ
    w = ch.weekly_totals(daily)
    assert list(w) == [sum(range(4, 11)), sum(range(11, 18)), sum(range(18, 25))]
    assert ch.weekly_totals([1.0] * 6).size == 0
    s = ch.prepare_weekly(np.r_[np.zeros(14), np.full(42, 80_000.0)], P)  # hai tuần đầu chưa chi
    assert s.n_weeks == 6 and s.skipped is None and s.raw[0] > 0


def test_hu_khong_du_dieu_kien_bi_bo_qua_voi_ly_do():
    assert ch.prepare_weekly(np.full(35, 80_000.0), P).skipped == ch.SKIP_INSUFFICIENT  # 5 tuần
    assert ch.prepare_weekly(np.zeros(60), P).skipped == ch.SKIP_NO_SPEND
    sparse = np.zeros(70)
    sparse[::10] = 300_000  # 1 ngày chi trong 10
    assert ch.prepare_weekly(sparse, P).skipped == ch.SKIP_SPARSE
    s = ch.prepare_weekly(np.full(70, 80_000.0), P)
    assert s.skipped is None and ch.detect_confirmed(replace(s, skipped=ch.SKIP_SPARSE), P) is None
    assert ch.detect_suspect(replace(s, skipped=ch.SKIP_SPARSE), P) is None


def test_ngay_cua_tuan_dau_doan_moi():
    last = date(2026, 11, 20)  # hôm qua
    assert ch.week_start_date(last, 6, 5) == date(2026, 11, 14)  # tuần mới nhất: 14/11 đến 20/11
    assert ch.week_start_date(last, 6, 4) == date(2026, 11, 7)
    assert ch.week_start_date(last, 6, 0) == date(2026, 10, 10)


# --- 2. CUSUM tự viết -----------------------------------------------------------------------------------------
def reference_cusum(z, k):
    sp = sn = 0.0
    up, dn = [], []
    for x in z:
        sp = max(0.0, sp + x - k)
        sn = max(0.0, sn - x - k)
        up.append(sp)
        dn.append(sn)
    return up, dn


def test_cusum_khop_ban_tham_chieu_va_phat_hien_buoc_nhay():
    z = np.r_[np.zeros(10), np.full(6, 2.0), np.full(4, -2.0)]
    up, dn = ch.cusum(z, 0.5)
    ref_up, ref_dn = reference_cusum(z, 0.5)
    np.testing.assert_allclose(up, ref_up)
    np.testing.assert_allclose(dn, ref_dn)
    assert up[15] == pytest.approx(6 * 1.5) and up[10:16].min() > 0 and dn[-1] > 0
    assert (up[:10] == 0).all() and (dn[:10] == 0).all()


def test_cusum_nghi_buoc_nhay_len_nhung_khong_nghi_chuoi_phang():
    weeks = [*list(noisy_weeks(500000, 8, seed=1)), 1300000, 1250000]
    sus = ch.detect_suspect(series_of(weeks), P)
    assert sus is not None and sus.direction == "up"
    assert sus.start_index == 8 and sus.weeks_in_alarm == 2
    assert sus.old_weekly_vnd == pytest.approx(500_000, rel=0.15)
    assert sus.new_weekly_vnd == pytest.approx(1_275_000, rel=0.01) and sus.statistic > P.cusum_h
    assert ch.detect_suspect(series_of(noisy_weeks(500_000, 20, seed=2)), P) is None


def test_cusum_nghi_buoc_nhay_xuong():
    weeks = [*list(noisy_weeks(900000, 8, seed=3)), 200000, 180000, 220000, 190000]
    sus = ch.detect_suspect(series_of(weeks), P)
    assert sus is not None and sus.direction == "down" and sus.new_weekly_vnd < sus.old_weekly_vnd


# --- 3. PELT (ruptures) ----------------------------------------------------------------------------------------
def optimal_partition(y, pen, min_size):
    """Phân đoạn tối ưu theo chi phí l2 (tổng bình phương lệch khỏi trung bình đoạn) + pen mỗi điểm gãy, quy hoạch động O(n^2)."""
    n = len(y)

    def cost(a, b):
        seg = y[a:b]
        return float(((seg - seg.mean()) ** 2).sum())

    best = [math.inf] * (n + 1)
    prev = [0] * (n + 1)
    best[0] = -pen
    for t in range(min_size, n + 1):
        for s in range(0, t - min_size + 1):
            if best[s] == math.inf or (s != 0 and s < min_size):
                continue
            c = best[s] + cost(s, t) + pen
            if c < best[t]:
                best[t], prev[t] = c, s
    out, t = [], n
    while t > 0:
        out.append(t)
        t = prev[t]
    return sorted(out)[:-1]


@pytest.mark.parametrize("seed", range(8))
def test_pelt_khop_quy_hoach_dong_tham_chieu(seed):
    rng = np.random.default_rng(seed)
    levels = rng.choice([300_000.0, 600_000.0, 1_000_000.0], size=3)
    sizes = rng.integers(3, 9, size=3)
    y = np.concatenate(
        [rng.normal(lv, 60_000, int(sz)) for lv, sz in zip(levels, sizes, strict=True)]
    )
    for c in (1.0, 3.0, 8.0):
        p = replace(P, pelt_penalty_c=c)
        pen = ch.pelt_penalty(y, p)
        assert ch.pelt_breakpoints(y, p) == optimal_partition(y, pen, p.pelt_min_size_weeks)


def test_penalty_co_cong_thuc_cua_spike_va_ln_n_ref_co_dinh():
    y = np.array(
        [500_000, 520_000, 480_000, 510_000, 505_000, 495_000, 1_200_000, 1_250_000], float
    )
    sigma = ch.noise_sigma(y, P, tail=P.pelt_min_size_weeks)
    assert ch.pelt_penalty(y, P) == pytest.approx(
        P.pelt_penalty_c * sigma**2 * math.log(P.pelt_penalty_n_ref)
    )
    assert ch.pelt_penalty(y[:6], replace(P, sigma_floor_ratio=0.0)) > 0
    # sigma bền: một bước nhảy chỉ làm hỏng MỘT sai phân nên không kéo sigma
    flat = np.array([500, 520, 480, 510, 505, 495, 500, 515], float) * 1000
    assert ch.noise_sigma(y, replace(P, sigma_floor_ratio=0.0)) < 3 * ch.noise_sigma(
        flat, replace(P, sigma_floor_ratio=0.0)
    )


def test_pelt_chuoi_qua_ngan_khong_co_diem_gay():
    assert ch.pelt_breakpoints([1.0, 2.0, 3.0], P) == []


# --- xác nhận ---------------------------------------------------------------------------------------------------
def test_xac_nhan_muc_moi_giu_ba_tuan():
    weeks = [*list(noisy_weeks(500000, 9, seed=4)), 1200000, 1300000, 1250000]
    hit = ch.detect_confirmed(series_of(weeks), P)
    assert hit is not None
    assert (hit.direction, hit.change_index, hit.weeks_held) == ("up", 9, 3)
    assert hit.old_weekly_vnd == pytest.approx(500_000, rel=0.1)
    assert hit.new_weekly_vnd == pytest.approx(1_250_000, rel=0.02)
    assert hit.n_breakpoints >= 1 and hit.penalty > 0
    assert hit.to_detail()["detector"] == "pelt" and hit.to_detail()["cost"] == "l2"


def test_xac_nhan_muc_moi_giam():
    weeks = [*list(noisy_weeks(1000000, 8, seed=5)), 250000, 220000, 240000, 230000]
    hit = ch.detect_confirmed(series_of(weeks), P)
    assert hit is not None and hit.direction == "down" and hit.weeks_held == 4
    assert hit.new_weekly_vnd < hit.old_weekly_vnd


def test_mot_khoan_lon_don_le_khong_xac_nhan_doi_hanh_vi():
    """Tiêu chí 3 của phase 4: một khoản lớn đơn lẻ không làm sinh lại lộ trình, ở bất kỳ tuần nào của chuỗi."""
    base = weekly_to_daily(noisy_weeks(550_000, 14, cv=0.12, seed=6), per_day_noise=0.4, seed=7)
    for day in (3, 20, 41, 60, 83, 90, 96):  # khoản lớn rơi giữa chuỗi, cuối chuỗi, đầu chuỗi
        daily = base.copy()
        daily[day] += 9_000_000  # lớn gấp 16 lần mức chi tuần
        s = ch.prepare_weekly(daily, P)
        assert day in s.one_off_days or daily[day] > 0
        assert ch.detect_confirmed(s, P) is None, day
        assert ch.detect_suspect(s, P) is None, day


def test_khoan_lon_o_hai_tuan_cuoi_cung_khong_xac_nhan():
    """Khoản lớn nằm trong đoạn 2 tuần cuối kèm một tuần bình thường: quy tắc giữ mức (mỗi tuần phía mức mới) chặn."""
    weeks = [*list(noisy_weeks(500000, 10, cv=0.1, seed=8)), 500000, 500000]
    daily = weekly_to_daily(weeks)
    daily[-9] += 4_000_000  # một ngày của tuần kế cuối
    s = ch.prepare_weekly(daily, P)
    assert ch.detect_confirmed(s, P) is None


def test_quy_tac_giu_muc_chan_mot_tuan_vot_cao_kem_mot_tuan_binh_thuong():
    s = series_of([*list(noisy_weeks(500000, 8, cv=0.05, seed=9)), 1800000, 520000])
    loose = replace(
        P, pelt_penalty_c=0.01, sigma_floor_ratio=0.0
    )  # penalty gần 0: PELT chắc chắn tách ra một điểm gãy
    assert ch.pelt_breakpoints(s.clean, loose)
    assert ch.detect_confirmed(s, loose) is None  # nhưng quy tắc giữ mức từ chối
    # đối chứng: hai tuần cùng cao thì được (cùng tham số)
    s2 = series_of([*list(noisy_weeks(500000, 8, cv=0.05, seed=9)), 1100000, 1100000])
    assert ch.detect_confirmed(s2, loose) is not None


def test_diem_gay_cu_hon_cua_so_khong_con_la_tin_moi():
    n_new = P.max_weeks_since_break + 1
    weeks = list(noisy_weeks(500_000, 8, seed=10)) + list(noisy_weeks(1_300_000, n_new, seed=11))
    assert ch.detect_confirmed(series_of(weeks), P) is None
    weeks = list(noisy_weeks(500_000, 8, seed=10)) + list(
        noisy_weeks(1_300_000, n_new - 1, seed=11)
    )
    assert ch.detect_confirmed(series_of(weeks), P) is not None


def test_thay_doi_nho_hon_nguong_tuong_doi_hoac_tuyet_doi_khong_xac_nhan():
    small_rel = [*list(noisy_weeks(1000000, 10, cv=0.01, seed=12)), 1150000, 1150000, 1150000]
    assert ch.detect_confirmed(series_of(small_rel), P) is None  # +15% < 30%
    small_abs = [*list(noisy_weeks(20000, 10, cv=0.01, seed=13)), 60000, 60000, 60000]
    assert ch.detect_confirmed(series_of(small_abs), P) is None  # +200% nhưng chỉ 40.000 đồng/tuần


def test_chuoi_phang_nhieu_khong_bao_dong_gia():
    hits = 0
    for seed in range(40):
        s = series_of(noisy_weeks(600_000, 30, cv=0.15, seed=100 + seed))
        hits += ch.detect_confirmed(s, P) is not None
    assert hits == 0


def test_bo_phat_hien_khong_doi_chuoi_vao():
    daily = weekly_to_daily([*list(noisy_weeks(500000, 8, seed=14)), 1200000, 1200000])
    before = daily.copy()
    s = ch.prepare_weekly(daily, P)
    ch.detect_confirmed(s, P)
    ch.detect_suspect(s, P)
    np.testing.assert_array_equal(daily, before)


# --- persona demo ---------------------------------------------------------------------------------------------
def persona_weekly(name):
    from yofina_ml.backtest.change_calibration import persona_daily_spend

    return {jar: ch.prepare_weekly(d, P) for jar, d in persona_daily_spend(name).items()}


def test_minh_an_uong_du_17_tuan_va_khong_co_diem_gay_cai_san():
    """`minh` có 120 ngày lịch sử (issue #8): Ăn uống đủ 17 tuần để phân tích nhưng KHÔNG có điểm gãy cài sẵn (cảnh 4 tự tạo
    thay đổi lúc chạy); các hũ khác thưa nên không được phân tích."""
    series = persona_weekly("minh")
    an = series["an_uong"]
    assert an.skipped is None and an.n_weeks == 17
    assert ch.detect_confirmed(an, P) is None
    assert ch.detect_suspect(an, P) is None
    for jar, s in series.items():
        if jar != "an_uong":
            assert s.skipped in (ch.SKIP_SPARSE, ch.SKIP_INSUFFICIENT), jar


def test_lan_va_khoa_khong_co_diem_gay_va_khoa_chua_du_lich_su():
    assert all(ch.detect_confirmed(s, P) is None for s in persona_weekly("lan").values())
    assert all(s.skipped == ch.SKIP_INSUFFICIENT for s in persona_weekly("khoa").values())


def test_calibration_json_hop_le():
    json.loads(ch.DEFAULTS_FILE.read_text(encoding="utf-8"))
