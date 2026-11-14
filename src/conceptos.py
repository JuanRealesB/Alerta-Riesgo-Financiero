"""Mapeo de los rubros (CONCEPTO) de la taxonomía NIIF de Supersociedades a variables del modelo.

Los nombres de los rubros cambian levemente entre taxonomías (NIIF plenas, NIIF pymes, años).
Por eso se usan expresiones regulares sobre el texto normalizado (minúsculas, sin tildes,
espacios simples). En las posiciones de letras con tilde se usa "." para tolerar textos
con codificación dañada (por ejemplo "Raz�n social").

Si al correr el pipeline una variable obligatoria queda sin coincidencias, revisa
data/reportes/conceptos_disponibles_*.csv y ajusta el patrón aquí.
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd


def es_vacio(x: object) -> bool:
    """True para None, NaN y pd.NA (este último no se puede usar en un if)."""
    try:
        return x is None or bool(pd.isna(x))
    except (TypeError, ValueError):  # listas u objetos sin valor faltante definido
        return False


def normalizar(texto: object) -> str:
    if es_vacio(texto):
        return ""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower().strip()
    t = re.sub(r"\s+", " ", t)
    return t


# Orden = prioridad: si una empresa reporta dos rubros que coinciden, gana el primer patrón.
BALANCE: dict[str, list[str]] = {
    "activo_corriente": [
        r"^activos? corrientes? totales?$",
        r"^total (de )?activos? corrientes?$",
    ],
    "activo_total": [
        r"^total (de )?activos?$",
        r"^activos? totales?$",
    ],
    "pasivo_corriente": [
        r"^pasivos? corrientes? totales?$",
        r"^total (de )?pasivos? corrientes?$",
    ],
    "pasivo_total": [
        r"^total (de )?pasivos?$",
        r"^pasivos? totales?$",
    ],
    "patrimonio": [
        r"^patrimonio total$",
        r"^total (de )?patrimonio$",
    ],
    "inventarios": [
        r"^inventarios corrientes$",
        r"^inventarios$",
    ],
    "efectivo": [
        r"^efectivo y equivalentes al efectivo$",
    ],
    "ganancias_acumuladas": [
        r"^ganancias acumuladas$",
        r"^ganancias \(p.rdidas\) acumuladas$",
    ],
}

RESULTADOS: dict[str, list[str]] = {
    "ingresos": [
        r"^ingresos de actividades ordinarias$",
    ],
    "ganancia_operacion": [
        r"^ganancia \(p.rdida\) por actividades de operaci.n$",
        r"^ganancia \(p.rdida\) operacional$",
    ],
    "costos_financieros": [
        r"^costos financieros$",
    ],
    "ganancia_antes_impuestos": [
        r"^ganancia \(p.rdida\),? antes de impuestos$",
    ],
    "ganancia_neta": [
        r"^ganancia \(p.rdida\)$",
        r"^ganancia \(p.rdida\) procedente de operaciones continuadas$",
    ],
}

CARATULA: dict[str, list[str]] = {
    "razon_social": [r"^raz.n social de la sociedad$", r"^raz.n social$"],
    "departamento": [r"^departamento de la direcci.n del domicilio$", r"departamento.*domicilio"],
    "ciudad": [r"^ciudad de la direcci.n del domicilio$", r"(ciudad|municipio).*domicilio"],
    "ciiu": [r"ciiu", r"actividad econ.mica principal"],
}

OBLIGATORIAS = {
    "balance": ["activo_total", "pasivo_total", "patrimonio", "activo_corriente", "pasivo_corriente"],
    "resultados": ["ingresos", "ganancia_neta"],
    "caratula": ["razon_social"],
}

# Palabras clave para sugerir candidatos cuando un patrón no encuentra nada
PISTAS = {
    "activo_corriente": "activos corrientes", "activo_total": "activos", "pasivo_corriente": "pasivos corrientes",
    "pasivo_total": "pasivos", "patrimonio": "patrimonio", "inventarios": "inventario",
    "efectivo": "efectivo", "ganancias_acumuladas": "acumulad", "ingresos": "ingresos",
    "ganancia_operacion": "operaci", "costos_financieros": "financier", "ganancia_antes_impuestos": "antes de impuestos",
    "ganancia_neta": "ganancia", "razon_social": "social", "departamento": "departamento",
    "ciudad": "ciudad", "ciiu": "ciiu",
}


def mapear(conceptos: pd.Series, reglas: dict[str, list[str]]) -> pd.DataFrame:
    """Devuelve un DataFrame concepto -> (variable, prioridad) para los conceptos que coinciden."""
    filas = []
    for concepto in pd.Series(conceptos).dropna().unique():
        norm = normalizar(concepto)
        for variable, patrones in reglas.items():
            hecho = False
            for prioridad, patron in enumerate(patrones):
                if re.search(patron, norm):
                    filas.append({"concepto": concepto, "variable": variable, "prioridad": prioridad})
                    hecho = True
                    break
            if hecho:
                break
    return pd.DataFrame(filas, columns=["concepto", "variable", "prioridad"])


def sugerencias(conceptos: pd.Series, variable: str, n: int = 15) -> list[str]:
    pista = PISTAS.get(variable, variable)
    cands = [c for c in pd.Series(conceptos).dropna().unique() if pista in normalizar(c)]
    return sorted(cands, key=len)[:n]
