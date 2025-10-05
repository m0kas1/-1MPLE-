# queueapp/stats_eta.py
import math
from typing import List, Dict
import numpy as np
import scipy.stats


def estimate_service_time(
    sample: List[float],
    prior_M: float,
    prior_n: float = 3.0,
    min_samples_for_confidence: int = 5,
    alpha: float = 0.05,
) -> Dict[str, object]:
    """
    Оценка среднего времени обслуживания одного человека и доверительного интервала.
    Возвращает dict с keys: mean_est, se, ci (low, high), p_le_prior, n, sample_mean, sample_sd
    """
    sample = [float(x) for x in sample] if sample else []
    n = len(sample)

    # No data -> use prior with large uncertainty
    if n == 0:
        mean_est = float(prior_M)
        se = max(1.0, prior_M * 0.35)
        df = 1
        t_crit = scipy.stats.t.ppf(1 - alpha / 2, df)
        ci_low, ci_high = mean_est - t_crit * se, mean_est + t_crit * se
        return {
            "mean_est": mean_est,
            "se": se,
            "ci": (max(0.0, ci_low), ci_high),
            "p_le_prior": 0.5,
            "n": n,
            "sample_mean": None,
            "sample_sd": None,
        }

    sample_mean = float(np.mean(sample))
    sample_sd = float(np.std(sample, ddof=1)) if n > 1 else 0.0

    # Standard error of the sample mean (fallback if single element)
    se_sample = sample_sd / math.sqrt(n) if n > 1 else (sample_mean * 0.25 or 1.0)

    # Shrinkage / Bayesian-like blend: weight sample_mean and prior_M
    mean_est = (n * sample_mean + prior_n * prior_M) / (n + prior_n)

    # Effective SE reduced by prior weight
    se_effective = se_sample * math.sqrt(n / (n + prior_n))

    # If very small sample, inflate SE to be conservative
    if n < min_samples_for_confidence:
        multiplier = math.sqrt(min_samples_for_confidence / max(n, 1))
        se_effective *= multiplier

    # t-based CI
    df = max(n - 1, 1)
    t_crit = scipy.stats.t.ppf(1 - alpha / 2, df)
    ci_low = max(0.0, mean_est - t_crit * se_effective)
    ci_high = mean_est + t_crit * se_effective

    # Probability that true mean <= prior_M (use t-cdf approx)
    z = (prior_M - mean_est) / se_effective if se_effective > 0 else float('inf') if prior_M > mean_est else -float('inf')
    p_le_prior = float(scipy.stats.t.cdf(z, df))

    return {
        "mean_est": float(mean_est),
        "se": float(se_effective),
        "ci": (float(ci_low), float(ci_high)),
        "p_le_prior": p_le_prior,
        "n": n,
        "sample_mean": float(sample_mean),
        "sample_sd": float(sample_sd) if n > 1 else None,
    }


def eta_for_position(estimate: Dict[str, object], position: int) -> Dict[str, object]:
    mean = estimate["mean_est"]
    ci_low, ci_high = estimate["ci"]
    return {
        "eta_mean": float(mean * position),
        "eta_ci": (float(ci_low * position), float(ci_high * position)),
        "position": position,
        "n": estimate["n"],
    }
