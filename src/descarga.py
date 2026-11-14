"""Descarga de los Estados Financieros NIIF de Supersociedades desde datos.gov.co (API SODA).

Los datasets están en formato largo (una fila por empresa-rubro-periodo) y son muy grandes,
así que se descarga solo lo necesario:
  1. Se consultan los rubros (CONCEPTO) que existen en cada corte anual.
  2. Se eligen los que coinciden con los patrones de src/conceptos.py.
  3. Se descargan solo esas filas, del 31 de diciembre de cada año y del "Periodo Actual".

Cada año queda en data/raw/<dataset>_<año>.parquet para no volver a descargarlo.
Un token de aplicación (variable de entorno SOCRATA_APP_TOKEN) evita límites de velocidad.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import requests

from . import conceptos as C

BASE = "https://www.datos.gov.co/resource/{id}.json"
PAGINA = 50_000
COLUMNAS = "codigo_instancia,nit,punto_entrada,fecha_corte,concepto,periodo,valor"


def _sesion() -> requests.Session:
    s = requests.Session()
    token = os.environ.get("SOCRATA_APP_TOKEN")
    if token:
        s.headers["X-App-Token"] = token
    return s


def _get(s: requests.Session, dataset: str, params: dict, intentos: int = 5) -> list[dict]:
    url = BASE.format(id=dataset)
    for i in range(intentos):
        try:
            r = s.get(url, params=params, timeout=180)
            if r.status_code == 200:
                return r.json()
            msg = f"HTTP {r.status_code}: {r.text[:300]}"
        except requests.RequestException as e:  # red caída, timeout
            msg = str(e)
        espera = 5 * (i + 1)
        print(f"  [reintento {i + 1}/{intentos}] {dataset}: {msg} (esperando {espera}s)")
        time.sleep(espera)
    raise RuntimeError(f"No se pudo consultar {dataset} con {params}")


def _filtro_anio(anio: int) -> str:
    return f"fecha_corte between '{anio}-12-31T00:00:00' and '{anio}-12-31T23:59:59'"


def _sql_lista(valores: list[str]) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in valores)


def descubrir_conceptos(dataset: str, anio: int, s: requests.Session | None = None) -> pd.DataFrame:
    s = s or _sesion()
    datos = _get(s, dataset, {
        "$select": "concepto, count(*) AS n",
        "$where": _filtro_anio(anio),
        "$group": "concepto",
        "$limit": 50_000,
    })
    df = pd.DataFrame(datos)
    if df.empty:
        return pd.DataFrame(columns=["concepto", "n"])
    df["n"] = pd.to_numeric(df["n"], errors="coerce")
    return df.sort_values("n", ascending=False)


def descargar_anio(dataset: str, anio: int, reglas: dict, carpeta: Path, solo_periodo_actual: bool = True,
                   refrescar: bool = False) -> Path:
    destino = carpeta / f"{dataset}_{anio}.parquet"
    if destino.exists() and not refrescar:
        print(f"  {destino.name} ya existe, se reutiliza")
        return destino

    s = _sesion()
    disponibles = descubrir_conceptos(dataset, anio, s)
    reportes = carpeta.parent / "reportes"
    reportes.mkdir(parents=True, exist_ok=True)
    disponibles.to_csv(reportes / f"conceptos_disponibles_{dataset}_{anio}.csv", index=False)
    if disponibles.empty:
        print(f"  {dataset} {anio}: sin datos para ese corte")
        pd.DataFrame(columns=COLUMNAS.split(",")).to_parquet(destino, index=False)
        return destino

    mapa = C.mapear(disponibles["concepto"], reglas)
    elegidos = mapa["concepto"].tolist()
    print(f"  {dataset} {anio}: {len(elegidos)} rubros elegidos de {len(disponibles)} disponibles")
    if not elegidos:
        pd.DataFrame(columns=COLUMNAS.split(",")).to_parquet(destino, index=False)
        return destino

    where = f"{_filtro_anio(anio)} AND concepto in ({_sql_lista(elegidos)})"
    if solo_periodo_actual:
        where += " AND upper(periodo) like '%ACTUAL%'"

    filas: list[dict] = []
    offset = 0
    while True:
        lote = _get(s, dataset, {
            "$select": COLUMNAS,
            "$where": where,
            "$order": ":id",
            "$limit": PAGINA,
            "$offset": offset,
        })
        filas.extend(lote)
        print(f"    {len(filas):,} filas", end="\r")
        if len(lote) < PAGINA:
            break
        offset += PAGINA
    print(f"    {len(filas):,} filas descargadas")
    df = pd.DataFrame(filas, columns=COLUMNAS.split(","))
    df.astype("string").to_parquet(destino, index=False)
    return destino


def descargar_todo(cfg: dict, carpeta: Path, refrescar: bool = False) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    ds = cfg["datasets"]
    for anio in cfg["anios"]:
        print(f"Corte {anio}")
        descargar_anio(ds["balance"], anio, C.BALANCE, carpeta, refrescar=refrescar)
        descargar_anio(ds["resultados"], anio, C.RESULTADOS, carpeta, refrescar=refrescar)
        # La carátula no siempre usa "Periodo Actual", así que no se filtra por periodo
        descargar_anio(ds["caratula"], anio, C.CARATULA, carpeta, solo_periodo_actual=False, refrescar=refrescar)
