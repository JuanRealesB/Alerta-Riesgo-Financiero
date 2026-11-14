"""Genera los archivos que lee la página estática (docs/data/*.json)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .modelo import puntuar

INDICADORES_FICHA = ["razon_corriente", "endeudamiento", "roa", "margen_operacional", "cobertura_intereses",
                     "crecimiento_ingresos"]


def _r(x, nd=3):
    if x is None or (isinstance(x, float) and not np.isfinite(x)) or pd.isna(x):
        return None
    return round(float(x), nd)


def _txt(x):
    if x is None or pd.isna(x):
        return ""
    return str(x).strip()


def exportar(df: pd.DataFrame, modelo: dict, cfg: dict, destino: Path, demo: bool = False) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    anio = int(df["anio"].max())
    actual = df[df["anio"] == anio].copy().reset_index(drop=True)

    prob, crudo, contrib = puntuar(modelo, actual)
    sana = (actual["dificultad"] == 0).values
    # El modelo se entrenó con empresas sin dificultad: a las que ya la tienen no se les asigna probabilidad
    actual["prob"] = np.where(sana, prob, np.nan)
    actual["pct"] = np.nan
    actual.loc[sana, "pct"] = pd.Series(crudo[sana]).rank(pct=True).values

    s = cfg["semaforo"]
    actual["sem"] = np.select(
        [~sana, actual["pct"] >= s["rojo_desde_percentil"], actual["pct"] >= s["amarillo_desde_percentil"]],
        ["dificultad", "rojo", "amarillo"], default="verde")
    actual["motivo"] = np.select(
        [~sana & (actual["patrimonio"] <= 0), ~sana], ["patrimonio_negativo", "perdida_sin_cobertura"], default="")

    dic = {k: sorted(actual[k].fillna("").astype(str).str.strip().str.title().unique().tolist()) if k == "ciudad"
           else sorted(actual[k].fillna("").astype(str).unique().tolist()) for k in ("sector", "region", "departamento", "ciudad")}
    dic["variable"] = list(contrib.columns)
    idx = {k: {v: i for i, v in enumerate(vals)} for k, vals in dic.items()}

    def _cod(k, v):
        v = _txt(v)
        return idx[k][v.title() if k == "ciudad" else v]

    filas = []
    for i, e in actual.iterrows():
        sube, baja = [], []
        if sana[i]:
            c = contrib.iloc[i]
            for lista, serie in ((sube, c[c > 0].sort_values(ascending=False).head(3)),
                                 (baja, c[c < 0].sort_values().head(2))):
                for v, x in serie.items():
                    valor = _cod(v, e[v]) if v in ("sector", "region") else _r(e[v], 3)
                    lista.append([idx["variable"][v], valor, _r(x, 3)])
        filas.append([
            _txt(e["nit"]),
            _txt(e.get("razon_social")) or f"NIT {_txt(e['nit'])}",
            _cod("departamento", e.get("departamento")), _cod("ciudad", e.get("ciudad")),
            _cod("sector", e["sector"]), _cod("region", e["region"]),
            _r(e["prob"], 3), _r(e["pct"], 3), e["sem"], e["motivo"],
            _r(e["altman_z"], 2), e["altman_zona"],
            *[_r(e[v], 3) for v in INDICADORES_FICHA],
            _r(e["ingresos"], 0), _r(e["activo_total"], 0),
            sube, baja,
        ])
    filas.sort(key=lambda f: (f[9] == "", -(f[6] or 0), f[10] if f[10] is not None else 99))  # en dificultad primero, luego por probabilidad
    campos = ["nit", "nombre", "departamento", "ciudad", "sector", "region", "prob", "pct", "sem", "motivo",
              "z", "zona", *INDICADORES_FICHA, "ingresos", "activos", "sube", "baja"]
    with open(destino / "empresas.json", "w", encoding="utf-8") as f:
        json.dump({"campos": campos, "diccionarios": dic, "filas": filas}, f, ensure_ascii=False, separators=(",", ":"))

    def _agrupar(col):
        g = actual.groupby(col)
        t = pd.DataFrame({
            "n": g.size(),
            "dificultad": g["sem"].apply(lambda x: int((x == "dificultad").sum())),
            "rojo": g["sem"].apply(lambda x: int((x == "rojo").sum())),
            "amarillo": g["sem"].apply(lambda x: int((x == "amarillo").sum())),
            "verde": g["sem"].apply(lambda x: int((x == "verde").sum())),
            "prob_media": g["prob"].mean().astype(float).round(4),
        }).reset_index().rename(columns={col: "nombre"})
        t["pct_alerta"] = ((t["rojo"] + t["dificultad"]) / t["n"]).round(4)
        return t.sort_values("pct_alerta", ascending=False).to_dict(orient="records")

    medianas = (actual.groupby("sector")[INDICADORES_FICHA].median().round(4)
                .apply(lambda r: {k: _r(v, 4) for k, v in r.items()}, axis=1).to_dict())
    medianas["Todas"] = {k: _r(v, 4) for k, v in actual[INDICADORES_FICHA].median().items()}

    resumen = {
        "meta": {
            "anio_puntuado": anio,
            "generado": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "n_empresas": int(len(actual)),
            "unidad": cfg.get("unidad_valor", ""),
            "demo": bool(demo),
            "fuente": "Superintendencia de Sociedades, Estados Financieros NIIF (datos.gov.co)",
            "licencia": "CC BY-SA 4.0",
            "umbrales": s,
            "autoria": cfg.get("autoria", {}),
            "repositorio": cfg.get("repositorio", ""),
        },
        "semaforo": {k: int((actual["sem"] == k).sum()) for k in ("dificultad", "rojo", "amarillo", "verde")},
        "en_dificultad_actual": int((~sana).sum()),
        "modelo": modelo["resumen"],
        "por_sector": _agrupar("sector"),
        "por_region": _agrupar("region"),
        "medianas_sector": medianas,
    }
    with open(destino / "resumen.json", "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=1)
    print(f"  {len(filas):,} empresas exportadas a {destino}")
