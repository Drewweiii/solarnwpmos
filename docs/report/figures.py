"""Every figure in the report, generated from the project's own equations.

Nothing here is drawn by hand or copied from a textbook plot. Each figure runs
the same mathematics the running system runs - the shading formula out of
`nongfab_features.shading`, the Erbs split and Hay-Davies transposition out of
`nongfab_features.poa`, the least-squares fit out of
`nongfab_forecast.pv_conversion`, the bisection IRR out of `nongfab_financial`
- at Nong Fab's real coordinates. A figure that disagreed with the deployed
system would be worse than no figure, so they are computed rather than drawn.

Run:  python3 docs/report/figures.py
Out:  docs/report/figures/*.svg   (vector, so equations and axes stay crisp in
                                   the PDF at any zoom)
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# Thai has to be registered explicitly. matplotlib's bundled DejaVu Sans has no
# Thai glyphs at all, and its fallback is a dummy box - so every Thai label
# silently renders as a row of squares while the script still exits 0. Caught by
# looking at the output rather than by any error.
#
# IBM Plex Sans Thai (SIL OFL, drawn with the Bangkok foundry Cadson Demak) is
# vendored under fonts/ rather than relied on from the system, so the figures
# render identically on any machine that rebuilds this report.
from matplotlib import font_manager  # noqa: E402

_THAI_FAMILY = "DejaVu Sans"
for _ttf in sorted((HERE / "fonts").glob("*.ttf")):
    font_manager.fontManager.addfont(str(_ttf))
    _THAI_FAMILY = font_manager.FontProperties(fname=str(_ttf)).get_name()

# Nong Fab, Rayong. The same constants nongfab_features.clearsky uses.
LAT, LON = 12.71, 101.15
TZ_OFFSET_H = 7  # ICT

# One visual language across every figure, so the report reads as one document.
C_PRIMARY = "#2563eb"
C_ACCENT = "#aa3bff"
C_WARM = "#f59e0b"
C_GREEN = "#16a34a"
C_RED = "#dc2626"
C_GREY = "#64748b"

plt.rcParams.update(
    {
        # Thai body text and Latin/greek both come from this family; math stays
        # on matplotlib's own mathtext fonts, which is what makes the symbols in
        # $...$ match the KaTeX equations in the surrounding report.
        # A FALLBACK CHAIN, not one family. IBM Plex Sans Thai covers Thai and
        # Latin but has no Greek, so a bare δ or β in a plain-text label came
        # out as a box - the same silent substitution that hid the missing Thai
        # a moment earlier. DejaVu Sans behind it supplies the Greek.
        "font.family": [_THAI_FAMILY, "DejaVu Sans"],
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 9,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "grid.linestyle": "-",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 120,
        "savefig.bbox": "tight",
        "legend.frameon": False,
    }
)


def save(fig, name: str) -> None:
    path = OUT / f"{name}.svg"
    fig.savefig(path, format="svg")
    plt.close(fig)
    print(f"  wrote {path.relative_to(Path(__file__).resolve().parent.parent.parent)}")


# ---------------------------------------------------------------------------
# 1. Solar geometry: declination and the sun path actually used at this site.
# ---------------------------------------------------------------------------
def solar_declination_deg(day_of_year: np.ndarray) -> np.ndarray:
    """Cooper's approximation, the standard first-order declination model."""
    return 23.45 * np.sin(np.deg2rad(360 * (284 + day_of_year) / 365))


def sun_position_pvlib(date_str: str):
    """Elevation and azimuth from pvlib - the same library, at the same
    coordinates, that `nongfab_features.clearsky` uses in production.

    An earlier version of this figure derived azimuth by hand from
    cos A = (sin δ − sin α sin φ)/(cos α cos φ). That identity is exact but
    numerically useless near the zenith: cos α → 0 makes the quotient blow past
    ±1, the clip to [−1, 1] then saturates, and the June curve came out flat-
    topped and smeared across every azimuth. At 12.71°N the sun passes within
    11° of the zenith at midsummer, so this site sits exactly where that
    breaks. Caught by looking at the plot, not by any exception.
    """
    import pandas as pd
    import pvlib

    times = pd.date_range(f"{date_str} 00:00", periods=24 * 12, freq="5min", tz="Asia/Bangkok")
    sp = pvlib.solarposition.get_solarposition(times, LAT, LON)
    return sp["apparent_elevation"].to_numpy(), sp["azimuth"].to_numpy()


def fig_declination():
    doy = np.arange(1, 366)
    fig, ax = plt.subplots(figsize=(6.2, 2.6))
    ax.plot(doy, solar_declination_deg(doy), color=C_PRIMARY, lw=1.8)
    ax.axhline(0, color=C_GREY, lw=0.8, ls="--")
    ax.axhline(LAT, color=C_ACCENT, lw=1.0, ls=":")
    # The sun passes overhead twice a year at 12.71 N - the reason this site's
    # seasonal yield curve is double-humped rather than a single summer peak.
    crossings = doy[np.abs(solar_declination_deg(doy) - LAT) < 0.35]
    for c in crossings:
        ax.axvline(c, color=C_ACCENT, lw=0.7, alpha=0.5)
    ax.annotate(
        f"δ = φ = {LAT}°  (sun overhead)",
        xy=(crossings[0] if len(crossings) else 110, LAT),
        xytext=(150, 19.5),
        color=C_ACCENT,
        fontsize=8,
    )
    ax.set_xlabel("วันที่ของปี  (day of year, n)")
    ax.set_ylabel("δ  (องศา)")
    ax.set_title("Solar declination ตลอดปี — สูตร Cooper")
    ax.set_xlim(1, 365)
    save(fig, "01-declination")


def fig_sun_paths():
    """A POLAR sun-path diagram, which is both the conventional presentation and
    the only one that is correct here.

    On a linear azimuth axis this figure was wrong twice over. At 12.71°N the
    midsummer sun culminates NORTH of the zenith (δ = 23.4° > φ = 12.7°), so its
    track runs ENE → due north → WNW and crosses the 0°/360° seam. A linear plot
    joins those two ends with a straight horizontal line at ~79°, which reads as
    "the sun sits at 79° all day" - a claim about this site that is simply
    false. Polar coordinates have no seam, so the crossing draws correctly and
    the north-passing is visible rather than hidden.
    """
    fig = plt.figure(figsize=(5.4, 5.0))
    ax = fig.add_subplot(projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)  # compass sense: N -> E -> S -> W

    for date_str, label, color in [
        ("2026-06-21", "21 มิ.ย. (ครีษมายัน)", C_WARM),
        ("2026-03-21", "21 มี.ค. (วิษุวัต)", C_PRIMARY),
        ("2026-12-21", "21 ธ.ค. (เหมายัน)", C_ACCENT),
    ]:
        elev, az = sun_position_pvlib(date_str)
        m = elev > 0
        # Radius is zenith angle, so the centre is overhead and the rim is the
        # horizon - the standard convention.
        ax.plot(np.deg2rad(az[m]), 90 - elev[m], color=color, lw=2, label=label)

    ax.set_rlim(0, 90)
    ax.set_rgrids([15, 30, 45, 60, 75, 90], labels=["75°", "60°", "45°", "30°", "15°", "0°"], fontsize=7)
    ax.set_thetagrids([0, 45, 90, 135, 180, 225, 270, 315],
                      labels=["N", "NE", "E", "SE", "S", "SW", "W", "NW"], fontsize=8)
    ax.plot([0], [0], "+", color=C_GREY, ms=10)
    # Offset well off the radial tick column, which runs up the NE diagonal.
    ax.text(np.deg2rad(200), 14, "จุดเหนือศีรษะ\n(zenith)", fontsize=7, color=C_GREY, ha="center")
    ax.set_title(
        f"แผนภาพเส้นทางดวงอาทิตย์ (polar)\nหนองแฟบ {LAT}°N — วงในคือมุมเงยสูง",
        fontsize=10,
        pad=16,
    )
    # Pushed clear of the "S" compass label, which sits at the bottom rim.
    ax.legend(fontsize=7.5, loc="lower center", bbox_to_anchor=(0.5, -0.30))
    ax.grid(alpha=0.3)
    save(fig, "02-sun-paths")


# ---------------------------------------------------------------------------
# 2. Erbs decomposition - the piecewise diffuse fraction the code relies on.
# ---------------------------------------------------------------------------
def erbs_diffuse_fraction(kt: np.ndarray) -> np.ndarray:
    """Erbs (1982), exactly the piecewise form pvlib implements."""
    kt = np.asarray(kt, dtype=float)
    out = np.empty_like(kt)
    a = kt <= 0.22
    b = (kt > 0.22) & (kt <= 0.80)
    c = kt > 0.80
    out[a] = 1.0 - 0.09 * kt[a]
    out[b] = 0.9511 - 0.1604 * kt[b] + 4.388 * kt[b] ** 2 - 16.638 * kt[b] ** 3 + 12.336 * kt[b] ** 4
    out[c] = 0.165
    return out


def fig_erbs():
    kt = np.linspace(0, 1, 500)
    fd = erbs_diffuse_fraction(kt)
    fig, ax = plt.subplots(figsize=(6.2, 2.9))
    ax.plot(kt, fd, color=C_PRIMARY, lw=2)
    for x in (0.22, 0.80):
        ax.axvline(x, color=C_GREY, lw=0.8, ls="--")
    ax.fill_betweenx([0, 1.05], 0, 0.22, color=C_GREY, alpha=0.07)
    ax.fill_betweenx([0, 1.05], 0.80, 1.0, color=C_WARM, alpha=0.07)
    ax.text(0.10, 0.35, "ฟ้าปิด\novercast", ha="center", fontsize=8, color=C_GREY)
    ax.text(0.51, 0.72, "ฟ้าบางส่วน\npartly cloudy", ha="center", fontsize=8, color=C_PRIMARY)
    ax.text(0.90, 0.35, "ฟ้าใส\nclear", ha="center", fontsize=8, color=C_WARM)
    ax.set_xlabel(r"clearness index  $k_t = GHI / I_0\cos\theta_z$")
    ax.set_ylabel(r"diffuse fraction  $DHI/GHI$")
    ax.set_title("Erbs decomposition — แยกรังสีตรงออกจากรังสีกระจาย")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.05)
    save(fig, "03-erbs")


# ---------------------------------------------------------------------------
# 3. Row-to-row self-shading - the project's own analytical formula.
# ---------------------------------------------------------------------------
def row_shaded_fraction(tilt_deg, azimuth_deg, row_pitch_m, slant_m, elev_deg, az_deg):
    """Transcribed from nongfab_features.shading.row_shaded_fraction."""
    if elev_deg <= 0:
        return 1.0
    tilt = math.radians(tilt_deg)
    d_az = math.radians(az_deg - azimuth_deg)
    behind = math.cos(d_az)
    if behind <= 0:
        return 0.0
    elev = math.radians(elev_deg)
    base = slant_m * math.cos(tilt)
    height = slant_m * math.sin(tilt)
    shadow_h = height / math.tan(elev) * behind
    overhang = (base - row_pitch_m) + shadow_h
    if overhang <= 0 or base <= 0:
        return 0.0
    return max(0.0, min(1.0, overhang / base))


def fig_shading_curve():
    elevs = np.linspace(2, 80, 400)
    fig, ax = plt.subplots(figsize=(6.2, 3.0))
    for pitch, color in [(3.0, C_RED), (4.0, C_WARM), (5.0, C_GREEN)]:
        y = [row_shaded_fraction(15, 180, pitch, 2.1, e, 180) * 100 for e in elevs]
        ax.plot(elevs, y, color=color, lw=1.8, label=f"row pitch = {pitch:.1f} m")
    ax.set_xlabel("มุมเงยดวงอาทิตย์  (solar elevation, องศา)")
    ax.set_ylabel("สัดส่วนที่ถูกบัง  (%)")
    ax.set_title("เงาแถวหน้าบังแถวหลัง — tilt 15°, slant 2.1 m, ดวงอาทิตย์ตรงหน้าแถว")
    ax.legend(fontsize=8)
    ax.set_xlim(2, 80)
    save(fig, "04-shading-elevation")


def fig_shading_geometry():
    """The cross-section the formula is derived from."""
    fig, ax = plt.subplots(figsize=(6.2, 2.8))
    tilt = math.radians(20)
    slant = 2.1
    pitch = 3.6
    base = slant * math.cos(tilt)
    height = slant * math.sin(tilt)
    elev = math.radians(22)

    for x0 in (0.0, pitch):
        ax.plot([x0, x0 + base], [0, height], color=C_PRIMARY, lw=3, solid_capstyle="round")
        ax.plot([x0, x0], [0, 0], "o", color=C_PRIMARY, ms=3)

    shadow_h = height / math.tan(elev)
    ax.plot([base, base + shadow_h], [height, 0], color=C_WARM, lw=1.4, ls="--")
    ax.annotate("", xy=(base + shadow_h, -0.12), xytext=(pitch, -0.12),
                arrowprops=dict(arrowstyle="<->", color=C_RED, lw=1.2))
    ax.text((pitch + base + shadow_h) / 2, -0.34, "ส่วนที่ถูกบัง\n$x_s$", ha="center", color=C_RED, fontsize=8)

    ax.annotate("", xy=(0, -0.62), xytext=(pitch, -0.62),
                arrowprops=dict(arrowstyle="<->", color=C_GREY, lw=1.0))
    ax.text(pitch / 2, -0.82, "row pitch  $p$", ha="center", color=C_GREY, fontsize=8)
    ax.plot([base + slant * 0.9 * math.cos(elev)], [0], alpha=0)
    ax.annotate("รังสีดวงอาทิตย์", xy=(base + 0.35, height - 0.25), xytext=(base + 1.5, height + 0.55),
                arrowprops=dict(arrowstyle="->", color=C_WARM, lw=1.0), color=C_WARM, fontsize=8)
    ax.text(base / 2 - 0.25, height / 2 + 0.12, r"$L$", color=C_PRIMARY, fontsize=10)
    ax.text(base + 0.05, height / 2, r"$L\sin\beta$", color=C_GREY, fontsize=8)

    ax.set_xlim(-0.6, pitch + base + 1.2)
    ax.set_ylim(-1.05, height + 1.0)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("ภาคตัดขวางที่ใช้ derive สูตรเงา (fixed-tilt, แถวขนานซ้ำ)")
    save(fig, "05-shading-geometry")


# ---------------------------------------------------------------------------
# 4. Least squares - the actual P = beta*I + gamma*T + c fit.
# ---------------------------------------------------------------------------
def fig_least_squares():
    """Fit the real model on synthetic-but-physical data and show the residuals.

    The DATA here is generated, and labelled as such on the figure - this site
    has no generation meter, so no real (I, T, P) history exists to fit. The
    METHOD is the deployed one: build the design matrix, solve by lstsq.
    """
    rng = np.random.default_rng(20260731)
    n = 220
    irr = rng.uniform(50, 1050, n)
    temp = 26 + 0.012 * irr + rng.normal(0, 1.6, n)
    capacity = 429.0
    beta_true = capacity / 1000.0
    gamma_true = capacity * (-0.30 / 100.0)
    c_true = -gamma_true * 25.0
    power = beta_true * irr + gamma_true * temp + c_true + rng.normal(0, 6.0, n)

    A = np.column_stack([irr, temp, np.ones(n)])
    (beta, gamma, c), *_ = np.linalg.lstsq(A, power, rcond=None)
    pred = A @ np.array([beta, gamma, c])
    resid = power - pred
    cond = np.linalg.cond(A)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.6, 2.9))
    ax1.scatter(irr, power, s=7, color=C_PRIMARY, alpha=0.45, label="ข้อมูล (จำลอง)")
    order = np.argsort(irr)
    ax1.plot(irr[order], pred[order], color=C_RED, lw=1.6, label="OLS fit")
    ax1.set_xlabel(r"$I$  (W/m²)")
    ax1.set_ylabel(r"$P$  (kW)")
    ax1.set_title("การถดถอย $P=\\beta I+\\gamma T+c$")
    ax1.legend(fontsize=7)

    ax2.scatter(pred, resid, s=7, color=C_GREEN, alpha=0.5)
    ax2.axhline(0, color=C_GREY, lw=1)
    ax2.set_xlabel(r"$\hat{P}$  (kW)")
    ax2.set_ylabel("residual (kW)")
    ax2.set_title(f"เศษเหลือ — RMSE {np.sqrt((resid**2).mean()):.2f} kW")

    fig.text(
        0.5, -0.10,
        f"$\\hat\\beta$={beta:.4f} kW/(W/m²)   $\\hat\\gamma$={gamma:.4f} kW/°C   "
        f"$\\hat{{c}}$={c:.2f} kW   cond($A$)={cond:.1f}",
        ha="center", fontsize=8,
    )
    save(fig, "06-least-squares")
    return beta, gamma, c, cond


# ---------------------------------------------------------------------------
# 5. Ridge regression - what the bias-correction stage actually solves.
# ---------------------------------------------------------------------------
def fig_ridge_path():
    """Coefficient shrinkage against lambda, on a deliberately collinear design.

    Collinear because that is the real situation: irradiance, clear-sky
    irradiance and the cloud index all move together, which is exactly when
    ordinary least squares becomes unstable and the ridge penalty earns its
    place.
    """
    rng = np.random.default_rng(7)
    n = 160
    x1 = rng.normal(0, 1, n)
    x2 = x1 + rng.normal(0, 0.06, n)  # ~collinear with x1
    x3 = rng.normal(0, 1, n)
    A = np.column_stack([x1, x2, x3])
    y = 2.0 * x1 - 1.0 * x2 + 0.5 * x3 + rng.normal(0, 0.4, n)

    lams = np.logspace(-4, 3, 120)
    coefs = []
    G = A.T @ A
    rhs = A.T @ y
    for lam in lams:
        coefs.append(np.linalg.solve(G + lam * np.eye(3), rhs))
    coefs = np.array(coefs)

    fig, ax = plt.subplots(figsize=(6.2, 2.9))
    for j, (lab, col) in enumerate([("$w_1$ (GHI)", C_PRIMARY), ("$w_2$ (GHI clear-sky)", C_ACCENT), ("$w_3$ (อิสระ)", C_GREEN)]):
        ax.plot(lams, coefs[:, j], color=col, lw=1.8, label=lab)
    ax.axvline(1.0, color=C_RED, lw=1.0, ls="--")
    ax.text(1.15, ax.get_ylim()[1] * 0.82, r"$\lambda=1$ (ค่าที่ระบบใช้)", color=C_RED, fontsize=8)
    ax.set_xscale("log")
    ax.set_xlabel(r"$\lambda$  (ridge penalty)")
    ax.set_ylabel("ค่าสัมประสิทธิ์")
    ax.set_title("Ridge path — ตัวแปรที่สัมพันธ์กันสูงถูกดึงเข้าหากัน")
    ax.legend(fontsize=8)
    save(fig, "07-ridge-path")


# ---------------------------------------------------------------------------
# 6. Pinball loss - the objective the interval heads are trained on.
# ---------------------------------------------------------------------------
def fig_pinball():
    u = np.linspace(-3, 3, 400)
    fig, ax = plt.subplots(figsize=(6.2, 2.7))
    for tau, col, lab in [(0.05, C_PRIMARY, r"$\tau=0.05$ (P5)"), (0.5, C_GREY, r"$\tau=0.50$"), (0.95, C_ACCENT, r"$\tau=0.95$ (P95)")]:
        loss = np.where(u >= 0, tau * u, (tau - 1) * u)
        ax.plot(u, loss, color=col, lw=1.8, label=lab)
    ax.axvline(0, color=C_GREY, lw=0.8, ls=":")
    ax.set_xlabel(r"$u = y - \hat{q}_\tau$")
    ax.set_ylabel(r"$\rho_\tau(u)$")
    ax.set_title("Pinball (quantile) loss — ลงโทษไม่สมมาตร จึงได้ quantile ที่ต้องการ")
    ax.legend(fontsize=8)
    save(fig, "08-pinball")


# ---------------------------------------------------------------------------
# 7. IRR by bisection - the actual solver, with its iterates.
# ---------------------------------------------------------------------------
def fig_irr_bisection():
    capex = 429.0 * 30000.0
    annual = 850109.0 * 2.5368
    lifetime = 25
    degrade = 0.0055
    flows = [-capex] + [annual * (1 - degrade) ** t for t in range(lifetime)]

    def npv(rate):
        return sum(cf / (1 + rate) ** t for t, cf in enumerate(flows))

    rates = np.linspace(-0.05, 0.20, 400)
    vals = np.array([npv(r) for r in rates]) / 1e6

    low, high = -0.5, 10.0
    iterates = []
    for _ in range(14):
        mid = (low + high) / 2
        iterates.append(mid)
        if (npv(mid) > 0) == (npv(low) > 0):
            low = mid
        else:
            high = mid

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.6, 2.8))
    ax1.plot(rates * 100, vals, color=C_PRIMARY, lw=1.8)
    ax1.axhline(0, color=C_GREY, lw=1)
    root = iterates[-1] * 100
    ax1.axvline(root, color=C_RED, lw=1.2, ls="--")
    ax1.plot([root], [0], "o", color=C_RED, ms=5)
    ax1.text(root + 0.6, vals.max() * 0.5, f"IRR ≈ {root:.2f}%", color=C_RED, fontsize=8)
    ax1.set_xlabel("discount rate (%)")
    ax1.set_ylabel("NPV (ล้านบาท)")
    ax1.set_title(r"NPV$(r)$ ลดทางเดียว → รากเดียว")

    ax2.semilogy(range(1, len(iterates) + 1), np.abs(np.array(iterates) - iterates[-1]) + 1e-12,
                 "o-", color=C_ACCENT, ms=3.5, lw=1.2)
    ax2.set_xlabel("รอบการวนซ้ำ (iteration)")
    ax2.set_ylabel(r"$|r_k - r^*|$")
    ax2.set_title("Bisection ลู่เข้าเชิงเส้น — ครึ่งช่วงทุกรอบ")
    save(fig, "09-irr-bisection")
    return root


# ---------------------------------------------------------------------------
# 8. Tilt optimisation - the objective surface the grid search walks.
# ---------------------------------------------------------------------------
def fig_tilt_surface():
    """Relative annual POA against tilt and azimuth, by the same clear-sky
    sampling the optimiser uses: 12 mid-month representative days."""
    import pandas as pd
    import pvlib

    days = pd.to_datetime([f"2026-{m:02d}-15" for m in range(1, 13)])
    times = pd.DatetimeIndex(
        np.concatenate([pd.date_range(d, periods=24, freq="h").values for d in days])
    ).tz_localize("UTC")
    loc = pvlib.location.Location(LAT, LON, tz="UTC")
    cs = loc.get_clearsky(times)
    sp = loc.get_solarposition(times)
    dni_extra = pvlib.irradiance.get_extra_radiation(times)

    tilts = np.arange(0, 41, 2.0)
    azis = np.arange(120, 241, 5.0)
    grid = np.zeros((len(tilts), len(azis)))
    for i, t in enumerate(tilts):
        for j, a in enumerate(azis):
            poa = pvlib.irradiance.get_total_irradiance(
                surface_tilt=t, surface_azimuth=a,
                solar_zenith=sp["apparent_zenith"], solar_azimuth=sp["azimuth"],
                dni=cs["dni"], ghi=cs["ghi"], dhi=cs["dhi"],
                dni_extra=dni_extra, model="haydavies", albedo=0.25,
            )
            grid[i, j] = float(np.nansum(poa["poa_global"]))
    grid = grid / grid.max() * 100

    ii, jj = np.unravel_index(np.argmax(grid), grid.shape)
    fig, ax = plt.subplots(figsize=(6.2, 3.2))
    cs_plot = ax.contourf(azis, tilts, grid, levels=18, cmap="viridis")
    ax.contour(azis, tilts, grid, levels=[97, 98, 99, 99.5], colors="white", linewidths=0.6, alpha=0.7)
    ax.plot([azis[jj]], [tilts[ii]], "*", color="white", ms=15, markeredgecolor="black", markeredgewidth=0.5)
    ax.annotate(f"optimum  β={tilts[ii]:.0f}°, γ={azis[jj]:.0f}°",
                xy=(azis[jj], tilts[ii]), xytext=(azis[jj] + 12, tilts[ii] + 8),
                color="white", fontsize=8,
                arrowprops=dict(arrowstyle="->", color="white", lw=1))
    fig.colorbar(cs_plot, ax=ax, label="POA รายปี (% ของค่าสูงสุด)")
    ax.set_xlabel("azimuth γ (องศา, 180 = ใต้)")
    ax.set_ylabel("tilt β (องศา)")
    ax.set_title(f"พื้นผิวเป้าหมายของการหามุมที่ดีที่สุด ({LAT}°N)")
    save(fig, "10-tilt-surface")
    return float(tilts[ii]), float(azis[jj])


# ---------------------------------------------------------------------------
# 9. Interval calibration - what PICP/PINAW measure.
# ---------------------------------------------------------------------------
def fig_interval_calibration():
    rng = np.random.default_rng(11)
    n = 120
    x = np.arange(n)
    truth = 180 * np.exp(-0.5 * ((x - 60) / 26) ** 2) + rng.normal(0, 7, n)
    truth = np.clip(truth, 0, None)
    center = 180 * np.exp(-0.5 * ((x - 60) / 26) ** 2)
    half = 22 + 0.10 * center

    fig, ax = plt.subplots(figsize=(6.4, 2.9))
    ax.fill_between(x, center - half, center + half, color=C_GREEN, alpha=0.18, label="ช่วง P5–P95")
    ax.plot(x, center, color=C_PRIMARY, lw=1.6, label="ค่าพยากรณ์")
    inside = (truth >= center - half) & (truth <= center + half)
    ax.scatter(x[inside], truth[inside], s=9, color=C_GREY, label="ค่าจริงในช่วง")
    ax.scatter(x[~inside], truth[~inside], s=18, color=C_RED, marker="x", label="ค่าจริงหลุดช่วง")
    picp = inside.mean() * 100
    pinaw = (2 * half).mean() / (truth.max() - truth.min()) * 100
    ax.set_title(f"การสอบเทียบช่วงความเชื่อมั่น — PICP {picp:.1f}% (เป้า 90%), PINAW {pinaw:.1f}%")
    ax.set_xlabel("ลำดับเวลา")
    ax.set_ylabel("กำลังผลิต (kW)")
    ax.legend(fontsize=7, ncol=2)
    save(fig, "11-interval-calibration")


# ---------------------------------------------------------------------------
# 10. Loss cascade - the multiplicative derate chain, as a waterfall.
# ---------------------------------------------------------------------------
def fig_loss_waterfall():
    losses = [
        ("Soiling", 2.0), ("Shading", 2.2), ("Mismatch", 2.0),
        ("DC wiring", 2.0), ("Connections", 0.5), ("Availability", 3.0),
        ("Inverter", 2.0),
    ]
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    level = 100.0
    for i, (name, pct) in enumerate(losses):
        drop = level * pct / 100
        ax.bar(i, drop, bottom=level - drop, color=C_RED, alpha=0.75, width=0.62)
        ax.text(i, level + 0.6, f"−{pct:.1f}%", ha="center", fontsize=7.5, color=C_RED)
        level -= drop
    ax.bar(len(losses), level, color=C_GREEN, alpha=0.8, width=0.62)
    ax.text(len(losses), level + 0.6, f"{level:.1f}%", ha="center", fontsize=8, color=C_GREEN, weight="bold")
    ax.set_xticks(range(len(losses) + 1))
    ax.set_xticklabels([n for n, _ in losses] + ["สุทธิ"], rotation=32, ha="right", fontsize=8)
    ax.set_ylabel("พลังงานคงเหลือ (%)")
    ax.set_ylim(80, 101.5)
    ax.set_title(r"ห่วงโซ่การสูญเสียแบบคูณกัน  $\eta=\prod_i (1-\ell_i)$")
    save(fig, "12-loss-waterfall")
    return level


# ---------------------------------------------------------------------------
# 11. P50/P90 exceedance - the inverse-normal-CDF the finance module uses.
# ---------------------------------------------------------------------------
def fig_exceedance():
    from statistics import NormalDist

    p50 = 850109.0
    cv = 0.07
    sigma = p50 * cv
    xs = np.linspace(p50 - 4 * sigma, p50 + 4 * sigma, 500)
    pdf = np.exp(-0.5 * ((xs - p50) / sigma) ** 2) / (sigma * math.sqrt(2 * math.pi))

    fig, ax = plt.subplots(figsize=(6.2, 2.9))
    ax.plot(xs / 1000, pdf * 1000, color=C_PRIMARY, lw=1.8)
    for p, col in [(0.90, C_RED), (0.75, C_WARM), (0.50, C_GREEN)]:
        z = NormalDist().inv_cdf(1 - p)
        v = p50 + z * sigma
        ax.axvline(v / 1000, color=col, lw=1.3, ls="--")
        ax.text(v / 1000, pdf.max() * 1000 * (0.55 + 0.14 * (p == 0.90)),
                f"P{int(p*100)}\n{v/1000:.0f} MWh", ha="center", fontsize=7.5, color=col)
    ax.fill_between(xs / 1000, 0, pdf * 1000,
                    where=(xs >= p50 + NormalDist().inv_cdf(1 - 0.90) * sigma),
                    color=C_GREEN, alpha=0.10)
    ax.set_xlabel("พลังงานรายปี (MWh)")
    ax.set_ylabel("ความหนาแน่นความน่าจะเป็น")
    ax.set_title(r"ระดับ exceedance  $E_p = E_{50} + \Phi^{-1}(1-p)\,\sigma$   (CV = 7%)")
    save(fig, "13-exceedance")


def main():
    print("generating report figures ...")
    fig_declination()
    fig_sun_paths()
    fig_erbs()
    fig_shading_curve()
    fig_shading_geometry()
    ls = fig_least_squares()
    fig_ridge_path()
    fig_pinball()
    irr = fig_irr_bisection()
    tilt = fig_tilt_surface()
    fig_interval_calibration()
    net = fig_loss_waterfall()
    fig_exceedance()
    print()
    print("computed values quoted in the report text:")
    print(f"  OLS fit          beta={ls[0]:.5f}  gamma={ls[1]:.4f}  c={ls[2]:.2f}  cond(A)={ls[3]:.1f}")
    print(f"  IRR (bisection)  {irr:.2f} %")
    print(f"  optimum angles   tilt={tilt[0]:.0f} deg  azimuth={tilt[1]:.0f} deg")
    print(f"  net derate       {net:.2f} % of DC energy survives")


if __name__ == "__main__":
    main()
