"""De los archivos crudos (formato largo) a una tabla empresa-año con indicadores financieros,
el Z'' de Altman y la variable objetivo.

Variable objetivo (proxy de deterioro, porque no hay una etiqueta pública de quiebra lista para usar):
  Una empresa está "en dificultad" en un año si
    a) su patrimonio es menor o igual a cero, o
    b) tiene pérdida neta y su resultado operativo no alcanza a cubrir los costos financieros.
  y = 1 si la empresa NO estaba en dificultad en el año t y SÍ lo está en t+1.
Solo se etiquetan las empresas que reportan en t y en t+1.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import conceptos as C

FAMILIAS = {
    "razon_corriente": "Liquidez",
    "prueba_acida": "Liquidez",
    "kt_activos": "Liquidez",
    "efectivo_activos": "Liquidez",
    "endeudamiento": "Endeudamiento",
    "concentracion_cp": "Endeudamiento",
    "patrimonio_pasivos": "Endeudamiento",
    "cobertura_intereses": "Endeudamiento",
    "roa": "Rentabilidad",
    "roe": "Rentabilidad",
    "margen_neto": "Rentabilidad",
    "margen_operacional": "Rentabilidad",
    "utilidades_ret_activos": "Rentabilidad",
    "rotacion_activos": "Actividad",
    "crecimiento_ingresos": "Actividad",
    "log_activos": "Tamaño",
    "sector": "Sector y región",
    "region": "Sector y región",
}
VARIABLES_MODELO = [v for v in FAMILIAS if v not in ("sector", "region")]

# CIIU Rev. 4 A.C.: división (2 dígitos) -> macrosector
_MACRO = [
    (1, 3, "Agropecuario"), (5, 9, "Minero-energético"), (10, 33, "Manufactura"),
    (35, 39, "Servicios públicos"), (41, 43, "Construcción"), (45, 47, "Comercio"),
    (49, 53, "Transporte y logística"), (55, 56, "Alojamiento y comida"),
    (58, 63, "Información y comunicaciones"), (64, 66, "Financiero y seguros"),
    (68, 68, "Inmobiliario"), (69, 75, "Servicios profesionales"), (77, 82, "Servicios administrativos"),
    (84, 84, "Administración pública"), (85, 85, "Educación"), (86, 88, "Salud"),
    (90, 93, "Arte y entretenimiento"), (94, 99, "Otros servicios"),
]
_SECCION = {
    "A": "Agropecuario", "B": "Minero-energético", "C": "Manufactura", "D": "Servicios públicos",
    "E": "Servicios públicos", "F": "Construcción", "G": "Comercio", "H": "Transporte y logística",
    "I": "Alojamiento y comida", "J": "Información y comunicaciones", "K": "Financiero y seguros",
    "L": "Inmobiliario", "M": "Servicios profesionales", "N": "Servicios administrativos",
    "O": "Administración pública", "P": "Educación", "Q": "Salud", "R": "Arte y entretenimiento",
    "S": "Otros servicios", "T": "Otros servicios", "U": "Otros servicios",
}

# Departamento -> (nombre para mostrar, región). Los datos de origen a veces traen las tildes
# dañadas ("BOGOT\ufffd", "NARI\ufffdO"), así que la comparación tolera ese carácter.
_DEPARTAMENTOS = {
    "atlantico": ("Atlántico", "Caribe"), "bolivar": ("Bolívar", "Caribe"), "cesar": ("Cesar", "Caribe"),
    "cordoba": ("Córdoba", "Caribe"), "la guajira": ("La Guajira", "Caribe"), "guajira": ("La Guajira", "Caribe"),
    "magdalena": ("Magdalena", "Caribe"), "sucre": ("Sucre", "Caribe"),
    "archipielago de san andres": ("San Andrés", "Caribe"), "san andres": ("San Andrés", "Caribe"),
    "choco": ("Chocó", "Pacífica"), "valle del cauca": ("Valle del Cauca", "Pacífica"),
    "valle": ("Valle del Cauca", "Pacífica"), "cauca": ("Cauca", "Pacífica"), "narino": ("Nariño", "Pacífica"),
    "bogota": ("Bogotá D.C.", "Bogotá-Cundinamarca"), "cundinamarca": ("Cundinamarca", "Bogotá-Cundinamarca"),
    "antioquia": ("Antioquia", "Antioquia-Eje Cafetero"), "caldas": ("Caldas", "Antioquia-Eje Cafetero"),
    "risaralda": ("Risaralda", "Antioquia-Eje Cafetero"), "quindio": ("Quindío", "Antioquia-Eje Cafetero"),
    "norte de santander": ("Norte de Santander", "Santanderes"), "santander": ("Santander", "Santanderes"),
    "boyaca": ("Boyacá", "Centro-Oriente"), "tolima": ("Tolima", "Centro-Oriente"), "huila": ("Huila", "Centro-Oriente"),
    "meta": ("Meta", "Orinoquía-Amazonía"), "casanare": ("Casanare", "Orinoquía-Amazonía"),
    "arauca": ("Arauca", "Orinoquía-Amazonía"), "vichada": ("Vichada", "Orinoquía-Amazonía"),
    "amazonas": ("Amazonas", "Orinoquía-Amazonía"), "caqueta": ("Caquetá", "Orinoquía-Amazonía"),
    "guainia": ("Guainía", "Orinoquía-Amazonía"), "guaviare": ("Guaviare", "Orinoquía-Amazonía"),
    "putumayo": ("Putumayo", "Orinoquía-Amazonía"), "vaupes": ("Vaupés", "Orinoquía-Amazonía"),
}
_PATRONES_DEPTO = [
    (re.compile("".join(f"[{c}\ufffd]" if c in "aeioun" else re.escape(c) for c in clave)), valor)
    for clave, valor in sorted(_DEPARTAMENTOS.items(), key=lambda kv: -len(kv[0]))  # el más largo primero
]


def _departamento(departamento: object) -> tuple[str, str]:
    d = C.normalizar(departamento)
    if not d:
        return "", "Sin dato"
    for patron, valor in _PATRONES_DEPTO:
        if patron.match(d):
            return valor
    return str(departamento).strip().title(), "Otra"


def region(departamento: object) -> str:
    return _departamento(departamento)[1]


def macrosector(ciiu: object) -> str:
    if C.es_vacio(ciiu):
        return "Sin clasificar"
    texto = str(ciiu).strip().upper()
    if not texto or texto in ("NAN", "NONE", "<NA>"):
        return "Sin clasificar"
    # Se prefiere la división (2 primeros dígitos de la clase CIIU); la letra de sección es el respaldo.
    digitos = "".join(ch for ch in texto.split(".")[0].split(" ")[0] if ch.isdigit())
    if len(digitos) >= 3:
        division = int(digitos.zfill(4)[:2])
        for a, b, nombre in _MACRO:
            if a <= division <= b:
                return nombre
    if texto[0] in _SECCION and (len(texto) == 1 or not texto[1].isalpha()):
        return _SECCION[texto[0]]
    return "Sin clasificar"


def _a_numero(serie: pd.Series) -> pd.Series:
    s = serie.astype("string").str.strip()
    s = s.str.replace(r"[\s$]", "", regex=True)
    # "1.234.567,89" -> "1234567.89"; "1,234,567" -> "1234567"
    con_coma_decimal = s.str.contains(r",\d{1,2}$", regex=True, na=False) & s.str.contains(r"\.", regex=True, na=False)
    s = s.where(~con_coma_decimal, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    s = s.str.replace(",", "", regex=False)
    return pd.to_numeric(s, errors="coerce").astype("float64")


def _cargar(carpeta: Path, dataset: str, anios: list[int]) -> pd.DataFrame:
    partes = []
    for anio in anios:
        f = carpeta / f"{dataset}_{anio}.parquet"
        if f.exists():
            df = pd.read_parquet(f)
            if len(df):
                df["anio"] = anio
                partes.append(df)
    if not partes:
        raise FileNotFoundError(f"No hay archivos de {dataset} en {carpeta}. Corre primero la descarga.")
    return pd.concat(partes, ignore_index=True)


def _filtrar_reportes(df: pd.DataFrame, excluir: list[str]) -> pd.DataFrame:
    pe = df["punto_entrada"].map(C.normalizar)
    mascara = pd.Series(True, index=df.index)
    for palabra in excluir:
        mascara &= ~pe.str.contains(palabra, regex=False)
    df = df[mascara].copy()
    df["nit"] = df["nit"].astype("string").str.replace(r"\D", "", regex=True)
    df["codigo_instancia"] = pd.to_numeric(
        df["codigo_instancia"].astype("string").str.replace(",", "", regex=False), errors="coerce").astype("float64")
    # Si una empresa tiene varios reportes en el mismo corte (retransmisiones), se usa el último.
    ultimo = df.groupby(["nit", "anio"])["codigo_instancia"].transform("max")
    return df[df["codigo_instancia"] == ultimo]


def _pivotar(df: pd.DataFrame, reglas: dict, nombre: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    mapa = C.mapear(df["concepto"], reglas)
    faltan = [v for v in C.OBLIGATORIAS.get(nombre, []) if v not in set(mapa["variable"])]
    if faltan:
        detalle = "\n".join(f"  {v}: candidatos -> {C.sugerencias(df['concepto'], v)}" for v in faltan)
        raise ValueError(
            f"En '{nombre}' no se encontró ningún rubro para: {faltan}.\n"
            f"Ajusta los patrones en src/conceptos.py. Rubros parecidos en los datos:\n{detalle}")
    d = df.merge(mapa, on="concepto", how="inner")
    if nombre != "caratula":
        d["valor"] = _a_numero(d["valor"])
    d = d.sort_values(["nit", "anio", "variable", "prioridad"]).drop_duplicates(["nit", "anio", "variable"])
    ancho = d.pivot(index=["nit", "anio"], columns="variable", values="valor").reset_index()
    ancho.columns.name = None
    if nombre != "caratula":
        for col in ancho.columns.drop(["nit", "anio"]):
            ancho[col] = pd.to_numeric(ancho[col], errors="coerce").astype("float64")
    else:
        for col in ancho.columns.drop(["nit", "anio"]):
            ancho[col] = ancho[col].astype(object).where(ancho[col].notna(), None)
    return ancho, mapa


def _div(a: pd.Series, b: pd.Series) -> pd.Series:
    a = pd.to_numeric(a, errors="coerce").astype(float)
    b = pd.to_numeric(b, errors="coerce").astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = a / b
    return r.where(np.isfinite(r))


def construir_tabla(cfg: dict, carpeta_raw: Path, carpeta_reportes: Path) -> pd.DataFrame:
    ds, anios = cfg["datasets"], cfg["anios"]
    excluir = cfg.get("excluir_punto_entrada", [])
    carpeta_reportes.mkdir(parents=True, exist_ok=True)

    bal, mapa_b = _pivotar(_filtrar_reportes(_cargar(carpeta_raw, ds["balance"], anios), excluir), C.BALANCE, "balance")
    res, mapa_r = _pivotar(_filtrar_reportes(_cargar(carpeta_raw, ds["resultados"], anios), excluir), C.RESULTADOS, "resultados")
    car_raw = _cargar(carpeta_raw, ds["caratula"], anios)
    car_raw = _filtrar_reportes(car_raw, excluir)
    car, mapa_c = _pivotar(car_raw, C.CARATULA, "caratula")
    pd.concat([mapa_b.assign(estado="balance"), mapa_r.assign(estado="resultados"),
               mapa_c.assign(estado="caratula")]).to_csv(carpeta_reportes / "conceptos_mapeados.csv", index=False)

    df = bal.merge(res, on=["nit", "anio"], how="inner")
    for col in list(C.BALANCE) + list(C.RESULTADOS):
        if col not in df:
            df[col] = np.nan

    # Datos descriptivos: el reporte más reciente de cada empresa
    car = car.sort_values("anio").groupby("nit").last().reset_index().drop(columns="anio")
    for col in C.CARATULA:
        if col not in car:
            car[col] = pd.NA
    df = df.merge(car, on="nit", how="left")
    df["sector"] = df["ciiu"].map(macrosector)
    deptos = df["departamento"].map(_departamento)
    df["departamento"] = deptos.str[0]
    df["region"] = deptos.str[1]

    df = df[pd.to_numeric(df["activo_total"], errors="coerce") > cfg.get("min_activos", 0)].copy()

    # Indicadores
    ebit = df["ganancia_operacion"].fillna(df["ganancia_antes_impuestos"] + df["costos_financieros"].fillna(0))
    df["ebit"] = ebit
    kt = df["activo_corriente"] - df["pasivo_corriente"]
    df["razon_corriente"] = _div(df["activo_corriente"], df["pasivo_corriente"])
    df["prueba_acida"] = _div(df["activo_corriente"] - df["inventarios"].fillna(0), df["pasivo_corriente"])
    df["kt_activos"] = _div(kt, df["activo_total"])
    df["efectivo_activos"] = _div(df["efectivo"], df["activo_total"])
    df["endeudamiento"] = _div(df["pasivo_total"], df["activo_total"])
    df["concentracion_cp"] = _div(df["pasivo_corriente"], df["pasivo_total"])
    df["patrimonio_pasivos"] = _div(df["patrimonio"], df["pasivo_total"])
    df["cobertura_intereses"] = _div(ebit, df["costos_financieros"].where(df["costos_financieros"] > 0))
    df["roa"] = _div(df["ganancia_neta"], df["activo_total"])
    df["roe"] = _div(df["ganancia_neta"], df["patrimonio"].where(df["patrimonio"] > 0))
    df["margen_neto"] = _div(df["ganancia_neta"], df["ingresos"].where(df["ingresos"] > 0))
    df["margen_operacional"] = _div(ebit, df["ingresos"].where(df["ingresos"] > 0))
    df["utilidades_ret_activos"] = _div(df["ganancias_acumuladas"], df["activo_total"])
    df["rotacion_activos"] = _div(df["ingresos"], df["activo_total"])
    df["log_activos"] = np.log10(df["activo_total"].astype(float))

    df = df.sort_values(["nit", "anio"])
    ingreso_previo = df.groupby("nit")["ingresos"].shift(1)
    anio_previo = df.groupby("nit")["anio"].shift(1)
    df["crecimiento_ingresos"] = _div(df["ingresos"] - ingreso_previo, ingreso_previo.where(ingreso_previo > 0))
    df.loc[anio_previo != df["anio"] - 1, "crecimiento_ingresos"] = np.nan

    # Recortes suaves para que valores absurdos (por errores de reporte) no dominen
    for col in VARIABLES_MODELO:
        if col == "log_activos":
            continue
        lo, hi = df[col].quantile([0.005, 0.995])
        df[col] = df[col].clip(lo, hi)

    # Z'' de Altman (1995, versión para empresas no manufactureras y mercados emergentes)
    x1 = _div(kt, df["activo_total"])
    x2 = _div(df["ganancias_acumuladas"].fillna(0), df["activo_total"])
    x3 = _div(ebit, df["activo_total"])
    x4 = _div(df["patrimonio"], df["pasivo_total"]).clip(-5, 20)
    df["altman_z"] = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
    df["altman_zona"] = np.select(
        [df["altman_z"] < 1.1, df["altman_z"] <= 2.6], ["Peligro", "Gris"], default="Segura")
    df.loc[df["altman_z"].isna(), "altman_zona"] = "Sin dato"

    # Dificultad actual y objetivo
    costos = df["costos_financieros"].fillna(0)
    df["dificultad"] = ((df["patrimonio"] <= 0) | ((df["ganancia_neta"] < 0) & (ebit < costos))).astype(int)
    siguiente = df[["nit", "anio", "dificultad"]].copy()
    siguiente["anio"] -= 1
    siguiente = siguiente.rename(columns={"dificultad": "dificultad_siguiente"})
    df = df.merge(siguiente, on=["nit", "anio"], how="left")
    df["y"] = np.where((df["dificultad"] == 0) & df["dificultad_siguiente"].notna(), df["dificultad_siguiente"], np.nan)

    return df.reset_index(drop=True)
