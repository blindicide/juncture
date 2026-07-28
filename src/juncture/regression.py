"""Grouped predictor regressions for policy sensitivity."""

from __future__ import annotations

import pandas as pd
import statsmodels.api as sm


def fit_ols(
    data: pd.DataFrame, outcome: str, predictors: list[str], name: str
) -> dict[str, float | str]:
    usable = data.dropna(subset=[outcome, *predictors])
    if len(usable) <= len(predictors) + 1:
        return {
            "model": name,
            "n": len(usable),
            "r_squared": float("nan"),
            "adjusted_r_squared": float("nan"),
            "rmse": float("nan"),
        }
    fit = sm.OLS(usable[outcome], sm.add_constant(usable[predictors])).fit()
    result: dict[str, float | str] = {
        "model": name,
        "n": len(usable),
        "r_squared": float(fit.rsquared),
        "adjusted_r_squared": float(fit.rsquared_adj),
        "rmse": float((fit.resid**2).mean() ** 0.5),
    }
    for key, value in fit.params.items():
        result[f"coefficient_{key}"] = float(value)
        result[f"standard_error_{key}"] = float(fit.bse[key])
    return result
