"""Grouped predictor regressions for policy sensitivity."""

from __future__ import annotations

import numpy as np
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


def fit_grouped_ols(
    data: pd.DataFrame, outcome: str, predictors: list[str], name: str, group: str
) -> dict[str, float | str]:
    """OLS with HC3 uncertainty and disjoint leave-group-out validation."""
    usable = data.dropna(subset=[outcome, *predictors, group])
    if len(usable) <= len(predictors) + 1:
        return {
            "model": name,
            "n": len(usable),
            "r_squared": float("nan"),
            "cv_rmse": float("nan"),
            "uncertainty": "HC3",
            "folding": f"leave-{group}-out",
            "validation_group": group,
            "n_folds": int(usable[group].nunique()),
            "train_test_groups_disjoint": True,
        }
    design = sm.add_constant(usable[predictors])
    fit = sm.OLS(usable[outcome], design).fit(cov_type="HC3")
    predictions = pd.Series(index=usable.index, dtype=float)
    fold_groups = list(usable.groupby(group, sort=True))
    for _, held_out in fold_groups:
        train = usable.drop(index=held_out.index)
        if len(train) <= len(predictors) + 1:
            continue
        fold = sm.OLS(train[outcome], sm.add_constant(train[predictors], has_constant="add")).fit()
        predictions.loc[held_out.index] = fold.predict(sm.add_constant(held_out[predictors], has_constant="add"))
    cv_errors = (usable[outcome] - predictions).dropna()
    result: dict[str, float | str] = {
        "model": name, "n": len(usable), "r_squared": float(fit.rsquared),
        "adjusted_r_squared": float(fit.rsquared_adj),
        "cv_rmse": float(np.sqrt(np.mean(cv_errors**2))) if len(cv_errors) else float("nan"),
        "uncertainty": "HC3",
        "folding": f"leave-{group}-out",
        "validation_group": group,
        "n_folds": len(fold_groups),
        "train_test_groups_disjoint": True,
    }
    for key, value in fit.params.items():
        result[f"coefficient_{key}"] = float(value)
        result[f"hc3_standard_error_{key}"] = float(fit.bse[key])
    return result
