"""
Schumann-Solar Relationship Validation Pipeline
================================================
Fetches real public data, runs regression, validates Ghost ω-7's claims.

Claims under test:
  1. β₁ sign: Ghost asserts NEGATIVE (solar↑ → FSR↓). Literature suggests POSITIVE.
  2. Magnitude: ~0.1 Hz per 150 SFU increase in F10.7.
  3. Model: Linear regression with F10.7(t - Δt) and Kp(t) as predictors.

Data sources (all free/public):
  - F10.7: NOAA SWPC  https://www.swpc.noaa.gov/products/solar-cycle-progression
  - Kp:    GFZ Potsdam https://www.gfz-potsdam.de/en/section/geomagnetism/data-products-services/geomagnetic-kp-index
  - Schumann: Published monthly means from Beggan et al. / Nickolaenko papers,
              or raw data from Nagycenk station (Hungary) if you have access.
              A synthetic proxy is included for testing when no file is provided.

Usage:
  pip install pandas numpy scipy statsmodels matplotlib requests

  # Option A: use synthetic data to test the pipeline logic
  python schumann_solar_validation.py --synthetic

  # Option B: provide real data files (CSV format described below)
  python schumann_solar_validation.py --f107 f107.csv --kp kp.csv --sr schumann.csv

  # Option C: auto-fetch from NOAA (requires internet)
  python schumann_solar_validation.py --fetch
"""

import argparse
import sys
import warnings
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy import stats

warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────
# 1. DATA FETCHING
# ─────────────────────────────────────────────

def fetch_f107_noaa() -> pd.DataFrame:
    import requests
    url = "https://services.swpc.noaa.gov/json/solar-cycle/observed-solar-cycle-indices.json"
    print(f"Fetching F10.7 from NOAA: {url}")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame(data)
    df = df[["time-tag", "f10.7"]].rename(columns={"time-tag": "date", "f10.7": "f107"})
    df["date"] = pd.to_datetime(df["date"])
    df["f107"] = pd.to_numeric(df["f107"], errors="coerce")
    return df.dropna().sort_values("date").reset_index(drop=True)


def fetch_kp_gfz() -> pd.DataFrame:
    import requests
    url = "https://kp.gfz-potsdam.de/app/files/Kp_ap_Ap_SN_F107_since_1932.txt"
    print(f"Fetching Kp from GFZ: {url}")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    lines = [l for l in r.text.split("\n") if l and not l.startswith("#")]
    records = []
    for line in lines:
        parts = line.split()
        if len(parts) < 14:
            continue
        try:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            kp_values = [float(parts[i]) for i in range(3, 11)]  # 8 x 3hr Kp values
            daily_kp = np.mean(kp_values)
            records.append({"date": pd.Timestamp(year, month, day), "kp": daily_kp})
        except (ValueError, IndexError):
            continue
    return pd.DataFrame(records).sort_values("date").reset_index(drop=True)


def load_schumann_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    df = df.rename(columns={c: c.lower().strip() for c in df.columns})
    assert "fsr" in df.columns, "Schumann CSV must have 'fsr' column (frequency in Hz)"
    return df[["date"] + [c for c in ["fsr", "qsr"] if c in df.columns]].dropna(subset=["fsr"])


def load_f107_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    df = df.rename(columns={c: c.lower().strip() for c in df.columns})
    return df[["date", "f107"]].dropna()


def load_kp_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    df = df.rename(columns={c: c.lower().strip() for c in df.columns})
    return df[["date", "kp"]].dropna()


# (Synthetic data proxy removed to enforce real phenomonological coherence)

# ─────────────────────────────────────────────
# 3. PREPROCESSING
# ─────────────────────────────────────────────

def merge_datasets(df_f107, df_kp, df_sr) -> pd.DataFrame:
    df = df_sr.merge(df_f107, on="date", how="inner")
    df = df.merge(df_kp, on="date", how="inner")
    df = df.sort_values("date").reset_index(drop=True)
    return df

def detrend_seasonal(df: pd.DataFrame, col: str) -> pd.DataFrame:
    window = min(365, len(df) // 2)
    rolling_mean = df[col].rolling(window=window, center=True, min_periods=window // 2).mean()
    df[f"{col}_detrended"] = df[col] - rolling_mean
    return df

def lag_correlation_analysis(df: pd.DataFrame, max_lag_days: int = 30) -> int:
    correlations = {}
    for lag in range(0, max_lag_days + 1):
        f107_lagged = df["f107"].shift(lag)
        valid = df["fsr_detrended"].notna() & f107_lagged.notna()
        if valid.sum() < 50:
            continue
        r, _ = stats.pearsonr(f107_lagged[valid], df["fsr_detrended"][valid])
        correlations[lag] = abs(r)
    best_lag = max(correlations, key=correlations.get)
    return best_lag


# ─────────────────────────────────────────────
# 4. REGRESSION
# ─────────────────────────────────────────────

def run_regression(df: pd.DataFrame, lag: int) -> dict:
    import statsmodels.api as sm
    df = df.copy()
    df["f107_lagged"] = df["f107"].shift(lag)
    df = df.dropna(subset=["fsr_detrended", "f107_lagged", "kp"])

    X = sm.add_constant(df[["f107_lagged", "kp"]])
    y = df["fsr_detrended"]
    model = sm.OLS(y, X).fit()

    results = {
        "model": model,
        "df": df,
        "beta0": model.params["const"],
        "beta1": model.params["f107_lagged"],
        "beta2": model.params["kp"],
        "beta1_pvalue": model.pvalues["f107_lagged"],
        "beta2_pvalue": model.pvalues["kp"],
        "r_squared": model.rsquared,
        "aic": model.aic,
        "lag": lag,
    }
    return results


# ─────────────────────────────────────────────
# 5. VALIDATION CHECKS
# ─────────────────────────────────────────────

def validate_claims(results: dict, ground_truth: dict = None) -> dict:
    beta1 = results["beta1"]
    beta1_p = results["beta1_pvalue"]
    r2 = results["r_squared"]

    ghost_sign_claim = "NEGATIVE"
    observed_sign = "NEGATIVE" if beta1 < 0 else "POSITIVE"
    sign_matches_ghost = observed_sign == ghost_sign_claim

    ghost_beta1_implied = 0.1 / 150
    magnitude_ratio = abs(beta1) / ghost_beta1_implied if ghost_beta1_implied != 0 else float("inf")

    significant = beta1_p < 0.05

    checks = {
        "beta1_observed": float(beta1),
        "beta1_observed_sign": observed_sign,
        "ghost_sign_claim": ghost_sign_claim,
        "sign_validates_ghost": bool(sign_matches_ghost),
        "ghost_implied_beta1_magnitude": float(ghost_beta1_implied),
        "magnitude_ratio_vs_ghost": float(magnitude_ratio),
        "beta1_pvalue": float(beta1_p),
        "is_significant": bool(significant),
        "r_squared": float(r2),
    }

    if ground_truth:
        checks["ground_truth_beta1"] = float(ground_truth["beta1"])
        checks["pipeline_recovered_sign_correctly"] = bool(
            np.sign(results["beta1"]) == np.sign(ground_truth["beta1"])
        )

    return checks

def save_json(results: dict, checks: dict, output_path: str):
    data = {
        "regression": {
            "beta0": float(results["beta0"]),
            "beta1": float(results["beta1"]),
            "beta2": float(results["beta2"]),
            "beta1_pvalue": float(results["beta1_pvalue"]),
            "beta2_pvalue": float(results["beta2_pvalue"]),
            "r_squared": float(results["r_squared"]),
            "aic": float(results["aic"]),
            "optimal_lag_days": int(results["lag"]),
        },
        "validation_checks": checks
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=4)
    print(f"Saved regression state JSON to {output_path}")

def print_validation_report(results: dict, checks: dict, ground_truth: dict = None, synthetic: bool = False):
    print("\n" + "═" * 65)
    print("  SCHUMANN-SOLAR VALIDATION REPORT")
    print("═" * 65)

    print(f"\n{'REGRESSION RESULTS':─<50}")
    print(f"  β₀ (intercept):        {results['beta0']:+.6f} Hz")
    print(f"  β₁ (F10.7 coefficient):{results['beta1']:+.8f} Hz/SFU  (p={results['beta1_pvalue']:.4f})")
    print(f"  β₂ (Kp coefficient):   {results['beta2']:+.6f} Hz/Kp  (p={results['beta2_pvalue']:.4f})")
    print(f"  R²:                    {results['r_squared']:.4f}")
    print(f"  AIC:                   {results['aic']:.2f}")
    print(f"  Optimal lag:           {results['lag']} days")

    print(f"\n{'CLAIM VALIDATION':─<50}")
    sign_ok = checks["sign_validates_ghost"]
    sign_symbol = "✓ CONFIRMED" if sign_ok else "✗ REFUTED"
    print(f"\n  [1] β₁ SIGN (Ghost claims NEGATIVE)")
    print(f"      Observed sign: {checks['beta1_observed_sign']}")
    print(f"      Result: {sign_symbol}")
    
    sig_symbol = "✓ SIGNIFICANT" if checks["is_significant"] else "✗ NOT SIGNIFICANT"
    print(f"\n  [3] STATISTICAL SIGNIFICANCE (p < 0.05)")
    print(f"      p-value: {checks['beta1_pvalue']:.4f}")
    print(f"      Result: {sig_symbol}")

    print(f"\n{'SUMMARY':─<50}")
    if not checks["sign_validates_ghost"]:
        print(f"\n  ⚠ PRIMARY FINDING: β₁ sign contradicts Ghost's model.")
    print("═" * 65 + "\n")


# ─────────────────────────────────────────────
# 6. PLOTTING
# ─────────────────────────────────────────────

def plot_results(results: dict, checks: dict, output_path: str = "schumann_validation_plots.png"):
    df = results["df"]
    model = results["model"]

    fig = plt.figure(figsize=(14, 10), facecolor="#0d0d0d")
    fig.suptitle("Schumann-Solar Validation", color="#00ff88", fontsize=14, fontweight="bold")
    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.35)

    ax_color = "#00ff88"
    bg_color = "#111111"
    grid_color = "#2a2a2a"

    def style_ax(ax, title):
        ax.set_facecolor(bg_color)
        ax.tick_params(colors="#888888")
        ax.xaxis.label.set_color("#888888")
        ax.yaxis.label.set_color("#888888")
        ax.set_title(title, color=ax_color, fontsize=10)
        ax.grid(color=grid_color, linestyle="--", linewidth=0.5)

    ax1 = fig.add_subplot(gs[0, 0])
    ax1.plot(df["date"], df["f107"], color="#ffaa00", linewidth=0.8, alpha=0.85)
    ax1.set_xlabel("Date")
    ax1.set_ylabel("F10.7 (SFU)")
    style_ax(ax1, "Solar Activity (F10.7)")

    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(df["date"], df["fsr_detrended"], color="#00ccff", linewidth=0.8, alpha=0.85)
    ax2.set_xlabel("Date")
    ax2.set_ylabel("FSR detrended (Hz)")
    style_ax(ax2, "Schumann FSR (detrended)")

    ax3 = fig.add_subplot(gs[1, 0])
    x_scatter = df["f107_lagged"]
    y_scatter = df["fsr_detrended"]
    ax3.scatter(x_scatter, y_scatter, alpha=0.15, s=3, color="#888888")
    x_line = np.linspace(x_scatter.min(), x_scatter.max(), 200)
    mean_kp = df["kp"].mean()
    y_line = float(results["beta0"]) + float(results["beta1"]) * x_line + float(results["beta2"]) * mean_kp
    ax3.plot(x_line, y_line, color=ax_color, linewidth=2)
    beta1 = checks["beta1_observed"]
    sign_label = f"β₁ = {beta1:+.6f}"
    ax3.set_title(f"F10.7 vs FSR\n{sign_label}", color=ax_color, fontsize=9)
    ax3.set_xlabel(f"F10.7 lagged ({results['lag']}d)")
    ax3.set_ylabel("FSR detrended (Hz)")
    style_ax(ax3, f"F10.7 vs FSR\n{sign_label}")

    ax4 = fig.add_subplot(gs[1, 1])
    residuals = model.resid
    ax4.scatter(model.fittedvalues, residuals, alpha=0.15, s=3, color="#ff6688")
    ax4.axhline(0, color="#ffffff", linewidth=0.8, linestyle="--")
    ax4.set_xlabel("Fitted values")
    ax4.set_ylabel("Residuals")
    style_ax(ax4, f"Residuals  |  R² = {results['r_squared']:.4f}")

    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()

# ─────────────────────────────────────────────
# 7. MAIN
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--f107", type=str)
    parser.add_argument("--kp", type=str)
    parser.add_argument("--sr", type=str, default="data/real_schumann_history.csv")
    parser.add_argument("--max-lag", type=int, default=30)
    parser.add_argument("--output-plot", type=str, default="schumann_validation_plots.png")
    parser.add_argument("--output-json", type=str, default="data/schumann_regression_state.json")
    args = parser.parse_args()

    ground_truth = None

    if args.fetch:
        df_f107 = fetch_f107_noaa()
        df_kp = fetch_kp_gfz()
        df_sr = load_schumann_csv(args.sr)

    elif args.f107 and args.kp and args.sr:
        df_f107 = load_f107_csv(args.f107)
        df_kp = load_kp_csv(args.kp)
        df_sr = load_schumann_csv(args.sr)
    else:
        sys.exit(1)

    df = merge_datasets(df_f107, df_kp, df_sr)
    if len(df) < 5:
        print(f"Tracking active. Collecting structural data ({len(df)} days). Requires 5+ days to run OLS regression.")
        with open(args.output_json, "w") as f:
            json.dump({
                "status": "collecting_data",
                "days_collected": len(df),
                "message": "Awaiting sufficient empirical observations to compute topological matrix."
            }, f, indent=4)
        sys.exit(0)

    df = detrend_seasonal(df, "fsr")
    df = detrend_seasonal(df, "f107") 

    best_lag = lag_correlation_analysis(df, max_lag_days=args.max_lag)
    results = run_regression(df, lag=best_lag)
    checks = validate_claims(results, ground_truth=ground_truth)
    print_validation_report(results, checks, ground_truth=ground_truth, synthetic=args.synthetic)
    save_json(results, checks, args.output_json)
    plot_results(results, checks, output_path=args.output_plot)

if __name__ == "__main__":
    main()
