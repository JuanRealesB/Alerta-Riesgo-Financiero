"""Comparación de tres enfoques con validación temporal:
  1. Z'' de Altman con sus coeficientes originales (sin entrenar).
  2. Regresión logística con las cuatro razones de Altman, reestimada con datos colombianos.
  3. XGBoost con todos los indicadores, sector y región, calibrado con el método de Platt.

Explicaciones: contribuciones SHAP exactas de árboles (TreeSHAP) que XGBoost calcula de forma
nativa con pred_contribs=True, agregadas por variable original y por familia de indicadores.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score, roc_curve
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

from .features import FAMILIAS, VARIABLES_MODELO

class Calibrador:
    """Calibración de Platt sobre el log-odds de XGBoost, ajustada con el año de validación.
    Es más estable que la isotónica cuando hay pocos casos en los extremos."""

    def fit(self, crudo: np.ndarray, y: np.ndarray) -> "Calibrador":
        self.lr = LogisticRegression(C=1e4, max_iter=1000).fit(self._logit(crudo), y)
        return self

    @staticmethod
    def _logit(p: np.ndarray) -> np.ndarray:
        p = np.clip(p, 1e-6, 1 - 1e-6)
        return np.log(p / (1 - p)).reshape(-1, 1)

    def predict(self, crudo: np.ndarray) -> np.ndarray:
        return self.lr.predict_proba(self._logit(crudo))[:, 1]


def matriz(df: pd.DataFrame, categorias: dict[str, list[str]]) -> pd.DataFrame:
    X = df[VARIABLES_MODELO].astype(float).copy()
    for col, cats in categorias.items():
        valores = df[col].astype("string").fillna("Sin dato")
        for c in cats:
            X[f"{col}={c}"] = (valores == c).astype(float)
    return X


def _x_altman(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "x1": df["kt_activos"], "x2": df["utilidades_ret_activos"].fillna(0),
        "x3": (df["ebit"] / df["activo_total"]).clip(-2, 2), "x4": df["patrimonio_pasivos"].clip(-5, 20),
    }).astype(float)


def _captura_top(y: np.ndarray, score: np.ndarray, frac: float = 0.10) -> float:
    n = max(1, int(len(score) * frac))
    idx = np.argsort(-score)[:n]
    return float(y[idx].sum() / max(1, y.sum()))


def _roc(y: np.ndarray, score: np.ndarray, puntos: int = 60) -> list[list[float]]:
    fpr, tpr, _ = roc_curve(y, score)
    rejilla = np.linspace(0, 1, puntos)
    return [[round(float(f), 4), round(float(np.interp(f, fpr, tpr)), 4)] for f in rejilla]


def _metricas(nombre: str, y: np.ndarray, score: np.ndarray, prob: np.ndarray | None) -> dict:
    return {
        "modelo": nombre,
        "auc_roc": round(float(roc_auc_score(y, score)), 3),
        "auc_pr": round(float(average_precision_score(y, score)), 3),
        "brier": None if prob is None else round(float(brier_score_loss(y, prob)), 4),
        "captura_top10": round(_captura_top(y, score), 3),
    }


def entrenar(df: pd.DataFrame, cfg: dict) -> dict:
    etiquetado = df[df["y"].notna()].copy()
    anios = sorted(etiquetado["anio"].unique())
    if len(anios) < 3:
        raise ValueError(f"Se necesitan al menos 3 años etiquetados y hay {anios}. Agrega años en config.yaml.")
    anio_prueba, anio_valid = anios[-1], anios[-2]
    tr = etiquetado[etiquetado["anio"] < anio_valid]
    va = etiquetado[etiquetado["anio"] == anio_valid]
    te = etiquetado[etiquetado["anio"] == anio_prueba]

    categorias = {
        "sector": sorted(df["sector"].dropna().unique().tolist()),
        "region": sorted(df["region"].dropna().unique().tolist()),
    }
    Xtr, Xva, Xte = matriz(tr, categorias), matriz(va, categorias), matriz(te, categorias)
    ytr, yva, yte = tr["y"].values.astype(int), va["y"].values.astype(int), te["y"].values.astype(int)

    p = cfg["xgboost"]
    params = {
        "objective": "binary:logistic", "eval_metric": "aucpr", "tree_method": "hist",
        "max_depth": p["max_depth"], "eta": p["eta"], "subsample": p["subsample"],
        "colsample_bytree": p["colsample_bytree"], "min_child_weight": p["min_child_weight"],
        "lambda": p["reg_lambda"], "seed": p["seed"],
    }
    dtr = xgb.DMatrix(Xtr, label=ytr, feature_names=list(Xtr.columns))
    dva = xgb.DMatrix(Xva, label=yva, feature_names=list(Xtr.columns))
    booster = xgb.train(params, dtr, num_boost_round=p["num_boost_round"], evals=[(dva, "valid")],
                        early_stopping_rounds=p["early_stopping_rounds"], verbose_eval=False)
    rango = (0, booster.best_iteration + 1)

    def predecir(X: pd.DataFrame) -> np.ndarray:
        return booster.predict(xgb.DMatrix(X, feature_names=list(Xtr.columns)), iteration_range=rango)

    calibrador = Calibrador().fit(predecir(Xva), yva)
    prob_te = calibrador.predict(predecir(Xte))
    raw_te = predecir(Xte)

    # Regresión logística con las razones de Altman
    logit = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(max_iter=1000))
    logit.fit(_x_altman(tr), ytr)
    prob_logit = logit.predict_proba(_x_altman(te))[:, 1]

    # Altman original: menor Z'' = más riesgo
    z_te = te["altman_z"].astype(float).fillna(te["altman_z"].median()).values
    score_altman = -z_te

    metricas = [
        _metricas("Z'' de Altman (coeficientes originales)", yte, score_altman, None),
        _metricas("Logística con razones de Altman", yte, prob_logit, prob_logit),
        _metricas(f"XGBoost con {len(VARIABLES_MODELO)} indicadores + sector y región", yte, raw_te, prob_te),
    ]
    for m in metricas:
        print(f"  {m['modelo']:<42} AUC {m['auc_roc']:.3f}  AUC-PR {m['auc_pr']:.3f}  top10% {m['captura_top10']:.1%}")

    zona_peligro = (te["altman_zona"] == "Peligro").values
    altman_zonas = {
        "peligro_precision": round(float(yte[zona_peligro].mean()) if zona_peligro.any() else 0.0, 3),
        "peligro_recall": round(float(zona_peligro[yte == 1].mean()) if yte.sum() else 0.0, 3),
        "fraccion_en_peligro": round(float(zona_peligro.mean()), 3),
    }
    # El mismo porcentaje de empresas marcadas, pero elegidas por XGBoost
    k = max(1, int(zona_peligro.sum()))
    top_xgb = np.zeros(len(yte), dtype=bool)
    top_xgb[np.argsort(-raw_te)[:k]] = True
    altman_zonas["xgb_mismo_tamano_precision"] = round(float(yte[top_xgb].mean()), 3)
    altman_zonas["xgb_mismo_tamano_recall"] = round(float(top_xgb[yte == 1].mean()) if yte.sum() else 0.0, 3)

    # Importancia SHAP en el año de prueba, agregada por variable y por familia
    contrib = contribuciones(booster, rango, Xte)
    imp_var = contrib.abs().mean().sort_values(ascending=False)
    imp_fam = imp_var.groupby(lambda v: FAMILIAS.get(v, "Otra")).sum().sort_values(ascending=False)

    return {
        "booster": booster, "rango": rango, "calibrador": calibrador, "columnas": list(Xtr.columns),
        "categorias": categorias,
        "resumen": {
            "anios_entrenamiento": [int(a) for a in sorted(tr["anio"].unique())],
            "anio_validacion": int(anio_valid), "anio_prueba": int(anio_prueba),
            "n_entrenamiento": int(len(tr)), "n_validacion": int(len(va)), "n_prueba": int(len(te)),
            "tasa_base_prueba": round(float(yte.mean()), 4),
            "mejor_iteracion": int(booster.best_iteration),
            "metricas": metricas,
            "altman_zonas": altman_zonas,
            "roc": {
                "altman": _roc(yte, score_altman),
                "logit": _roc(yte, prob_logit),
                "xgboost": _roc(yte, raw_te),
            },
            "importancia_familias": [{"familia": k, "valor": round(float(v), 4)} for k, v in imp_fam.items()],
            "importancia_variables": [{"variable": k, "familia": FAMILIAS.get(k, "Otra"), "valor": round(float(v), 4)}
                                      for k, v in imp_var.items()],
        },
    }


def contribuciones(booster: xgb.Booster, rango: tuple[int, int], X: pd.DataFrame) -> pd.DataFrame:
    """Contribuciones SHAP (log-odds) agregadas a la variable original (sector=..., region=... se suman)."""
    c = booster.predict(xgb.DMatrix(X, feature_names=list(X.columns)), pred_contribs=True, iteration_range=rango)
    cdf = pd.DataFrame(c[:, :-1], columns=X.columns, index=X.index)
    grupos = [col.split("=")[0] for col in cdf.columns]
    return cdf.T.groupby(grupos).sum().T


def puntuar(modelo: dict, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    """Devuelve (probabilidad calibrada, puntaje crudo para ordenar, contribuciones SHAP)."""
    X = matriz(df, modelo["categorias"])[modelo["columnas"]]
    crudo = modelo["booster"].predict(xgb.DMatrix(X, feature_names=modelo["columnas"]), iteration_range=modelo["rango"])
    prob = modelo["calibrador"].predict(crudo)
    return prob, crudo, contribuciones(modelo["booster"], modelo["rango"], X)
