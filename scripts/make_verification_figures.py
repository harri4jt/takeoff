"""Generate verification figures (PNG) for the slides into output/verification/.

    python scripts/make_verification_figures.py

1. RK4 / RK45 vs exact solution          5. analytic ground roll vs simulated
2. RK4 log-log error vs step size        6. BFL crossing chart (synthetic aircraft)
3. secant error vs iteration             7. PASS/FAIL summary of every check
4. our RK vs scipy DOP853 (Van der Pol)

scipy is used here ONLY as an independent reference (it is a test-only dependency).
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import yaml
from scipy.integrate import solve_ivp

from bfl import compute_bfl, load_config, sweep_v1
from bfl.dynamics import SegmentParams
from bfl.integrators import Event, integrate
from bfl.model import build_model
from bfl.phases import airspeed_event, run_segment
from bfl.plotting import AEO, GO, INK, MUTED, STOP, bfl_chart, style
from bfl.rootfind import observed_order, safeguarded_secant, secant
from bfl.units import G0_FTPS2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "verification"
GOLDEN = (1 + math.sqrt(5)) / 2
checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, value: str) -> None:
    checks.append((name, bool(ok), value))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {value}")


def osc(t, y):
    return np.array([y[1], -4.0 * y[0]])


def vdp(t, y, mu=0.5):
    return np.array([y[1], mu * (1 - y[0] ** 2) * y[1] - y[0]])


# ------------------------------------------------------------------------------------
def fig1_exact() -> None:
    T = 6.0
    rk4 = integrate(osc, 0, [1.0, 0.0], T, method="rk4", dt=0.25)
    rk45 = integrate(osc, 0, [1.0, 0.0], T, method="rk45", rtol=1e-6, atol=1e-8)
    tt = np.linspace(0, T, 600)
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    a.plot(tt, np.cos(2 * tt), color=INK, lw=1.5, label="exact cos 2t")
    a.plot(rk4.t, rk4.y[:, 0], "o", color=GO, ms=6, label="RK4, dt = 0.25")
    a.plot(
        rk45.t,
        rk45.y[:, 0],
        "s",
        color=STOP,
        ms=5,
        mfc="none",
        mew=1.5,
        label=f"RK45 adaptive ({rk45.n_steps} steps)",
    )
    a.set(title="Harmonic oscillator y'' = -4y", xlabel="t", ylabel="y")
    a.legend(loc="lower left")
    e4 = np.abs(rk4.y[:, 0] - np.cos(2 * rk4.t))
    e45 = np.abs(rk45.y[:, 0] - np.cos(2 * rk45.t))
    b.semilogy(rk4.t[1:], e4[1:], "-o", color=GO, ms=4, label="RK4")
    b.semilogy(rk45.t[1:], e45[1:], "-s", color=STOP, ms=4, label="RK45")
    b.set(title="Pointwise error |y - exact|", xlabel="t", ylabel="error")
    b.legend()
    fig.savefig(OUT / "1_rk_vs_exact.png")
    plt.close(fig)
    # quantitative check at tight settings
    errs = []
    for m in ("rk4", "rk45"):
        s = integrate(osc, 0, [1.0, 0.0], T, method=m, dt=1e-3, rtol=1e-10, atol=1e-12)
        errs.append(np.max(np.abs(s.y[:, 0] - np.cos(2 * s.t))))
    check(
        "RK4 & RK45 match exact oscillator",
        max(errs) < 1e-8,
        f"max err RK4 {errs[0]:.1e}, RK45 {errs[1]:.1e}",
    )


def fig2_order() -> None:
    dts = np.array([0.2 / 2**k for k in range(7)])
    errs = np.array(
        [
            abs(integrate(osc, 0, [1.0, 0.0], 2.0, method="rk4", dt=d).y[-1, 0] - math.cos(4.0))
            for d in dts
        ]
    )
    slope, icpt = np.polyfit(np.log(dts), np.log(errs), 1)
    fig, ax = plt.subplots(figsize=(6.5, 4.5), constrained_layout=True)
    ax.loglog(dts, errs, "o-", color=GO, ms=7, label=f"RK4 (fitted slope {slope:.2f})")
    ax.loglog(
        dts, errs[0] * (dts / dts[0]) ** 4, "--", color=MUTED, lw=1.5, label="reference slope 4"
    )
    ax.set(
        title="RK4 observed order of accuracy",
        xlabel="step size dt",
        ylabel="global error at t = 2",
    )
    ax.legend()
    fig.savefig(OUT / "2_rk4_order.png")
    plt.close(fig)
    ratio = errs[3] / errs[4]
    check(
        "RK4 observed order ~ 4",
        abs(slope - 4) < 0.3,
        f"slope {slope:.3f}; error ratio per halving {ratio:.1f}",
    )

    rtols = [1e-4, 1e-6, 1e-8, 1e-10]
    e45 = []
    for r in rtols:
        s = integrate(osc, 0, [1.0, 0.0], 10.0, method="rk45", rtol=r, atol=r * 1e-2)
        e45.append(np.max(np.abs(s.y[:, 0] - np.cos(2 * s.t))))
    check(
        "RK45 error decreases with rtol",
        all(a > b for a, b in zip(e45, e45[1:], strict=False)),
        ", ".join(f"{r:.0e}->{e:.1e}" for r, e in zip(rtols, e45, strict=True)),
    )

    t_star = math.log(0.3) / -0.7
    worst = 0.0
    for d in (0.1, 0.03, 0.0071):
        ev = Event(lambda t, y: y[0] - 0.3, "lvl", -1)
        s = integrate(lambda t, y: -0.7 * y, 0, [1.0], 10.0, method="rk4", dt=d, events=[ev])
        worst = max(worst, abs(s.t[-1] - t_star))
    check(
        "Event time independent of step size",
        worst < 1e-6,
        f"max |t_event - t*| = {worst:.1e} s over dt in (0.1, 0.03, 0.0071)",
    )


def fig3_secant() -> None:
    fig, ax = plt.subplots(figsize=(6.5, 4.5), constrained_layout=True)
    cases = [
        ("x² − 2", lambda x: x * x - 2, 1.0, 2.0, math.sqrt(2), GO),
        ("cos x − x", lambda x: math.cos(x) - x, 0.0, 1.0, 0.7390851332151607, STOP),
    ]
    orders = []
    for lab, f, a, b, root, c in cases:
        r = secant(f, a, b, xtol=0.0, maxiter=12)
        e = [abs(x - root) for x in r.x_history]
        e = [v for v in e if v > 1e-15]
        p = observed_order([v for v in e if v > 1e-13])
        orders.append(p[-1])
        ax.semilogy(range(len(e)), e, "o-", color=c, ms=6, label=f"{lab}: observed p = {p[-1]:.3f}")
    r = safeguarded_secant(math.atan, -3.0, 5.0, xtol=1e-14)
    e = [abs(x) for x in r.x_history if abs(x) > 1e-15]
    ax.semilogy(range(len(e)), e, "s--", color=AEO, ms=5, label="atan x, safeguarded")
    ax.set(
        title=f"Secant convergence (theory p = {GOLDEN:.3f})",
        xlabel="iterate k",
        ylabel="|x_k − root|",
    )
    ax.legend()
    fig.savefig(OUT / "3_secant_convergence.png")
    plt.close(fig)
    check(
        "Secant observed order ~ 1.618",
        all(abs(p - GOLDEN) < 0.15 for p in orders),
        ", ".join(f"{p:.3f}" for p in orders),
    )
    plain = secant(math.atan, 2.0, 3.0, maxiter=30)
    check(
        "Safeguard rescues divergent secant (atan)",
        r.converged and abs(r.root) < 1e-12 and not (plain.converged and abs(plain.root) < 1e-6),
        f"safeguarded root {r.root:.1e} in {r.iterations} its; plain secant: {plain.message}",
    )


def fig4_scipy() -> None:
    T = 15.0
    s4 = integrate(vdp, 0, [2.0, 0.0], T, method="rk4", dt=2e-3)
    s45 = integrate(vdp, 0, [2.0, 0.0], T, method="rk45", rtol=1e-10, atol=1e-12)
    r4 = solve_ivp(vdp, (0, T), [2.0, 0.0], "DOP853", rtol=1e-12, atol=1e-14, t_eval=s4.t)
    r45 = solve_ivp(vdp, (0, T), [2.0, 0.0], "DOP853", rtol=1e-12, atol=1e-14, t_eval=s45.t)
    e4 = np.max(np.abs(s4.y - r4.y.T), axis=1)
    e45 = np.max(np.abs(s45.y - r45.y.T), axis=1)
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    a.plot(r4.y[0], r4.y[1], color=INK, lw=4, alpha=0.25, label="scipy DOP853 (rtol 1e-12)")
    a.plot(s4.y[:, 0], s4.y[:, 1], color=GO, lw=1.5, label="our RK4")
    a.set(title="Van der Pol (μ = 0.5) phase portrait", xlabel="y", ylabel="y'")
    a.legend(loc="lower right")
    b.semilogy(s4.t, e4 + 1e-17, color=GO, label="RK4, dt = 2e-3")
    b.semilogy(s45.t, e45 + 1e-17, color=STOP, label="RK45, rtol = 1e-10")
    b.set(title="Difference from scipy", xlabel="t", ylabel="max |Δy|")
    b.legend()
    fig.savefig(OUT / "4_rk_vs_scipy.png")
    plt.close(fig)
    check(
        "Our RK agrees with scipy DOP853",
        max(e4.max(), e45.max()) < 1e-7,
        f"RK4 {e4.max():.1e}, RK45 {e45.max():.1e}",
    )


def fig5_ground_roll() -> None:
    CL, CD, T1, S, W, mu = 0.6, 0.06, 30000.0, 2000.0, 150000.0, 0.03
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "aero_takeoff.csv").write_text(f"alpha_deg,CL,CD\n-20,{CL},{CD}\n30,{CL},{CD}\n")
        (d / "aircraft.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "analytic",
                    "synthetic": True,
                    "geometry": {"wing_area_ft2": S},
                    "weight": {"default_weight_lbf": W},
                    "engines": {
                        "n_engines": 2,
                        "thrust_mode": "constant",
                        "thrust_per_engine_lbf": T1,
                        "idle_thrust_per_engine_lbf": 0.0,
                    },
                    "attitude": {"theta_tailstrike_deg": 12.0},
                    "aero": {"configurations": {"takeoff": "aero_takeoff.csv"}},
                }
            )
        )
        cfg = load_config(d, overrides={"environment.mu_roll": mu})
        vm = build_model(cfg)
    m = W / G0_FTPS2
    A = 2 * T1 - mu * m * G0_FTPS2
    B = 0.5 * vm.rho * S * (CD - mu * CL)
    p = SegmentParams(vm, "aeo_roll", 2, mu=mu)
    seg = run_segment(
        "ground", p, 0.0, [0.0, 0.0], 500.0, [airspeed_event("ground", p, 260.0, "v")], cfg.solver
    )
    v = seg.sol.y[:, 1]
    x_num = seg.sol.y[:, 0]
    x_ex = m / (2 * B) * np.log(A / (A - B * v**2))
    rel = np.max(np.abs(x_num[1:] - x_ex[1:]) / x_ex[1:])
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    vv = np.linspace(0, 260, 200)
    a.plot(
        m / (2 * B) * np.log(A / (A - B * vv**2)),
        vv,
        color=INK,
        lw=4,
        alpha=0.25,
        label="closed form x(V)",
    )
    a.plot(x_num, v, color=GO, lw=1.5, label="RK4 simulation")
    a.set(
        title="Ground roll, constant T, CL, CD, μ",
        xlabel="distance x [ft]",
        ylabel="ground speed V [ft/s]",
    )
    a.legend(loc="lower right")
    b.semilogy(v[1:], np.abs(x_num[1:] - x_ex[1:]) / x_ex[1:] + 1e-17, color=GO)
    b.set(title="Relative error", xlabel="V [ft/s]", ylabel="|x_num − x_exact| / x_exact")
    fig.savefig(OUT / "5_analytic_ground_roll.png")
    plt.close(fig)
    check("Analytic ground roll", rel < 1e-8, f"max relative error {rel:.1e}")


def fig6_and_physics() -> None:
    cfg = load_config("generic_widebody_synthetic")
    res = compute_bfl(cfg)
    sw = sweep_v1(cfg, n=21)
    ax = bfl_chart(sw, res)
    ax.set_title("BFL crossing chart, generic widebody (SYNTHETIC data)")
    ax.figure.savefig(OUT / "6_bfl_crossing.png", bbox_inches="tight")
    plt.close(ax.figure)

    check(
        "Balance at solved V1",
        abs(res.d_go_ft - res.d_stop_ft) < cfg.solver.v1_tol_ft,
        f"|d_go − d_stop| = {abs(res.d_go_ft - res.d_stop_ft):.2e} ft "
        f"in {len(res.v1_solver_history)} evaluations",
    )
    check(
        "Sweep monotonic (go ↓, stop ↑)",
        bool(np.all(np.diff(sw.d_go_ft) < 0) and np.all(np.diff(sw.d_stop_ft) > 0)),
        f"{len(sw)} V1 values",
    )
    fine = compute_bfl(cfg.with_updates({"solver.dt_s": 0.005}))
    rel = abs(fine.bfl_ft - res.bfl_ft) / res.bfl_ft
    check("Step-size independence (dt 0.01 → 0.005)", rel < 1e-3, f"ΔBFL/BFL = {rel:.1e}")

    base = res.bfl_ft
    for label, upd, sign in [
        ("μ_brake 0.30 → 0.40 shortens", {"environment.mu_brake": 0.40}, -1),
        ("Drag chute shortens", {"procedure.chute_enabled": True}, -1),
        ("15 kt headwind shortens", {"environment.headwind_kts": 15.0}, -1),
        ("ΔCD_eo 0.004 → 0.010 lengthens", {"aircraft.aero.delta_CD_engine_out": 0.01}, 1),
        ("100 °F day lengthens", {"environment.temperature_F": 100.0}, 1),
        ("5000 ft elevation lengthens", {"environment.elevation_ft": 5000.0}, 1),
        ("+75,000 lbf weight lengthens", {"environment.weight_lbf": 850000.0}, 1),
    ]:
        b = compute_bfl(cfg.with_updates(upd)).bfl_ft
        check(label, (b - base) * sign > 0, f"{base:,.0f} → {b:,.0f} ft")
    v1 = [res.v1_kts]
    flat = sweep_v1(cfg, v1).iloc[0]
    up = sweep_v1(cfg.with_updates({"environment.runway_slope_deg": 1.0}), v1).iloc[0]
    check(
        "1° uphill: longer go, shorter stop (V1→rest)",
        up.d_go_ft > flat.d_go_ft and up.stop_after_v1_ft < flat.stop_after_v1_ft,
        f"go {flat.d_go_ft:,.0f}→{up.d_go_ft:,.0f}; stop after V1 "
        f"{flat.stop_after_v1_ft:,.0f}→{up.stop_after_v1_ft:,.0f} ft",
    )
    tb = compute_bfl(
        cfg.with_updates(
            {
                "environment.weight_lbf": 850000.0,
                "aircraft.attitude.theta_tailstrike_deg": 14.0,
                "multipliers.k_CD": 1.4,
                "procedure.k_VR": 1.01,
            }
        )
    )
    check(
        "Touchback guard raises VR",
        len(tb.vr_adjustments) > 0,
        f"k_VR 1.01 → {tb.k_VR:.2f} after {len(tb.vr_adjustments)} retries",
    )


def fig7_summary() -> None:
    n = len(checks)
    fig, ax = plt.subplots(figsize=(11, 0.42 * n + 1.0))
    ax.axis("off")
    npass = sum(ok for _, ok, _ in checks)
    ax.set_title(f"Verification summary: {npass}/{n} checks pass", loc="left", fontsize=13)
    for i, (name, ok, val) in enumerate(checks):
        y = 1 - (i + 0.5) / n
        ax.text(
            0.0,
            y,
            "PASS" if ok else "FAIL",
            color="#008300" if ok else "#e34948",
            fontweight="bold",
            va="center",
            transform=ax.transAxes,
        )
        ax.text(0.07, y, name, va="center", color=INK, transform=ax.transAxes)
        ax.text(0.47, y, val, va="center", color=MUTED, transform=ax.transAxes, fontsize=9)
    fig.savefig(OUT / "7_summary.png", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    style()
    fig1_exact()
    fig2_order()
    fig3_secant()
    fig4_scipy()
    fig5_ground_roll()
    fig6_and_physics()
    fig7_summary()
    npass = sum(ok for _, ok, _ in checks)
    print(f"\n{npass}/{len(checks)} checks pass; figures in {OUT}")


if __name__ == "__main__":
    main()
