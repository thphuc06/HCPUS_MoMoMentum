"""Mục 8: phân bổ lương vào hũ bằng scipy.optimize.linprog (HiGHS). Đơn vị k VND.
Biến: x (tiền vào hũ), s (thiếu mục tiêu mềm), e (thiếu nghĩa vụ cứng - elastic), dp/dm (|x - x_prev| tuyến tính hóa)."""
import time
import numpy as np, scipy
from scipy.optimize import linprog

JARS = ["nghia_vu", "an_uong", "di_chuyen", "giai_tri", "mua_sam", "du_lich", "du_phong"]
HARD = np.array([3980.0, 2000.0, 450.0, 0, 0, 0, 0])        # nghĩa vụ (trọ 2.800 + trả sau 450 + net/điện/nước/điện thoại 730), thiết yếu ăn uống từ P50 dự báo, di chuyển
GOAL = np.array([0, 0, 0, 600.0, 500.0, 900.0, 1000.0])    # nhu cầu đóng góp mục tiêu mỗi kỳ
W = np.array([0, 0, 0, 1.0, 1.0, 2.0, 3.0])                 # phạt thiếu mục tiêu: dự phòng > du lịch > giải trí = mua sắm
M = 1e6


def allocate(I, hard, goal, w, x_prev=None, eps=0.01, hard_as_bounds=False, integer_step=None, method="highs", Mj=None):
    n = len(hard)
    Mv = np.full(n, M) if Mj is None else np.asarray(Mj, float)
    # biến: x(n) s(n) e(n) dp(n) dm(n)
    nv = 5 * n
    c = np.r_[np.zeros(n), w, Mv, np.full(n, eps), np.full(n, eps)] if x_prev is not None else np.r_[np.zeros(n), w, Mv, np.zeros(2 * n)]
    A_eq = [np.r_[np.ones(n), np.zeros(4 * n)]]; b_eq = [I]
    A_ub, b_ub = [], []
    bounds = [(hard[j] if hard_as_bounds else 0, None) for j in range(n)] + [(0, None)] * (4 * n)
    for j in range(n):
        if not hard_as_bounds and hard[j] > 0:
            r = np.zeros(nv); r[j] = -1; r[2 * n + j] = -1; A_ub.append(r); b_ub.append(-hard[j])      # x + e >= L
        if goal[j] > 0:
            r = np.zeros(nv); r[j] = -1; r[n + j] = -1; A_ub.append(r); b_ub.append(-goal[j])          # x + s >= T
        if x_prev is not None:
            r = np.zeros(nv); r[j] = 1; r[3 * n + j] = -1; r[4 * n + j] = 1                           # x - xprev = dp - dm
            A_eq.append(r); b_eq.append(x_prev[j])
    integrality = None
    if integer_step:
        integrality = np.r_[np.ones(n), np.zeros(4 * n)]
    res = linprog(c, A_ub=np.array(A_ub) if A_ub else None, b_ub=b_ub if b_ub else None, A_eq=np.array(A_eq), b_eq=b_eq, bounds=bounds, method=method, integrality=integrality)
    return res, n


def show(title, res, n):
    print(f"\n{title}\n  status={res.status} ({res.message[:60]})")
    if res.status == 0:
        x, s, e = res.x[:n], res.x[n:2 * n], res.x[2 * n:3 * n]
        print("  x   :", dict(zip(JARS, x.round(0))))
        print(f"  thiếu mục tiêu mềm Σs = {s.sum():.0f} {dict((j, round(v)) for j, v in zip(JARS, s) if v > 1e-6)}")
        print(f"  thiếu nghĩa vụ cứng Σe = {e.sum():.0f} {dict((j, round(v)) for j, v in zip(JARS, e) if v > 1e-6)}")
        print(f"  mục tiêu = {res.fun:.1f}")


print("scipy", scipy.__version__)
# Ca 1: có nghiệm, thu nhập 9.000
r, n = allocate(9000.0, HARD, GOAL, W); show("CA 1: I=9.000 (có nghiệm; mục tiêu mềm thiếu một phần vì HARD=6.430, GOAL=3.000, còn 2.570)", r, n)
# Ca 1b: ổn định lộ trình: x_prev = nghiệm kỳ trước, kỳ này nghĩa vụ trọ tăng 300
xprev = r.x[:n].copy()
H2 = HARD.copy(); H2[0] += 300
r1b, n = allocate(9000.0, H2, GOAL, W, x_prev=xprev); show("CA 1b: trọ +300, có phạt thay đổi so với kỳ trước (eps=0,01)", r1b, n)
print("  thay đổi so với kỳ trước:", dict(zip(JARS, (r1b.x[:n] - xprev).round(0))))
# Ca 1c: mục tiêu không khả thi, nới mềm bằng cách giãn kỳ hạn (T giảm một nửa)
r1c, n = allocate(9000.0, HARD, GOAL * 0.5, W); show("CA 1c: giãn kỳ hạn mục tiêu (T x 0,5) -> hết thiếu mềm", r1c, n)
# Ca 2: vô nghiệm theo nghĩa cứng. 2a: sàn đặt bằng bounds (cách ngây thơ); 2b: elastic
r2a, n = allocate(5500.0, HARD, GOAL, W, hard_as_bounds=True); show("CA 2a: I=5.500, sàn cứng đặt qua `bounds` (HARD=6.430 > I)", r2a, n)
r2b, n = allocate(5500.0, HARD, GOAL, W); show("CA 2b: I=5.500, sàn cứng qua x+e>=L (elastic) -> luôn có nghiệm và báo mức thiếu", r2b, n)
# Ca 2c: phạt elastic khác nhau theo ưu tiên (trọ/nghĩa vụ 1e6 > ăn uống 1e5 > di chuyển 1e4) -> phần thiếu rơi vào hũ ưu tiên thấp trước
r2c, n = allocate(5500.0, HARD, GOAL, W, Mj=[1e6, 1e5, 1e4, 1, 1, 1, 1]); show("CA 2c: như 2b nhưng M theo ưu tiên", r2c, n)
# Ca 3: vô nghiệm kiểu mâu thuẫn tuyệt đối (tổng cố định I < 0 không xảy ra); kiểm tra I rất nhỏ
r3, n = allocate(0.0, HARD, GOAL, W); show("CA 3: I=0", r3, n)
# MILP bước 10k (x là bội số của 1 đơn vị; ở đây ép x nguyên theo đơn vị k VND để thử thời gian)
r4, n = allocate(9000.0, HARD, GOAL, W, integer_step=True); show("CA 4: x nguyên (integrality=1 trên x, đơn vị k VND)", r4, n)

# thời gian giải
def bench(fn, k=300):
    ts = []
    fn()
    for _ in range(k):
        a = time.perf_counter(); fn(); ts.append((time.perf_counter() - a) * 1000)
    return np.median(ts), np.percentile(ts, 95)
print("\nThời gian giải (ms, median / p95, 300 lần, 7 hũ, 35 biến):")
for lab, fn in [("ca 1 highs", lambda: allocate(9000.0, HARD, GOAL, W)),
                ("ca 1b có x_prev", lambda: allocate(9000.0, H2, GOAL, W, x_prev=xprev)),
                ("ca 2b elastic", lambda: allocate(5500.0, HARD, GOAL, W)),
                ("ca 2a vô nghiệm (bounds)", lambda: allocate(5500.0, HARD, GOAL, W, hard_as_bounds=True)),
                ("ca 4 MILP nguyên", lambda: allocate(9000.0, HARD, GOAL, W, integer_step=True)),
                ("highs-ds", lambda: allocate(9000.0, HARD, GOAL, W, method="highs-ds")),
                ("highs-ipm", lambda: allocate(9000.0, HARD, GOAL, W, method="highs-ipm"))]:
    m, p95 = bench(fn); print(f"  {lab:28s} {m:6.2f} / {p95:6.2f}")
t0 = time.perf_counter(); import scipy.optimize; print("import scipy.optimize: %.0f ms (đã nạp)" % ((time.perf_counter() - t0) * 1000))
