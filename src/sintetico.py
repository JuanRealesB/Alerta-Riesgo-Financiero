"""Datos sintéticos con la misma forma que los datasets de Supersociedades.

Sirven para probar el pipeline y la página sin conexión a datos.gov.co.
Las empresas y sus cifras son inventadas: no publiques estos resultados como reales.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SECTORES = [  # (CIIU, peso, rotación de activos, margen base)
    ("4711", 0.14, 1.9, 0.03), ("4659", 0.10, 1.6, 0.04), ("1040", 0.05, 1.3, 0.06), ("2229", 0.05, 1.1, 0.05),
    ("4111", 0.09, 0.5, 0.07), ("4290", 0.05, 0.6, 0.06), ("4923", 0.06, 1.0, 0.04), ("5611", 0.04, 1.4, 0.03),
    ("6201", 0.06, 1.2, 0.08), ("6810", 0.08, 0.2, 0.12), ("7020", 0.07, 1.0, 0.07), ("8610", 0.05, 0.9, 0.05),
    ("0125", 0.05, 0.6, 0.06), ("0810", 0.03, 0.7, 0.09), ("3511", 0.03, 0.4, 0.14), ("8559", 0.05, 0.9, 0.05),
]
DEPTOS = [  # (departamento, ciudad, peso)
    ("BOGOT\ufffd D.C.", "BOGOT\ufffd, D.C.", 0.36), ("ANTIOQUIA", "MEDELLIN", 0.16), ("VALLE", "CALI", 0.10),
    ("ATLANTICO", "BARRANQUILLA", 0.07), ("CUNDINAMARCA", "CHIA", 0.05), ("SANTANDER", "BUCARAMANGA", 0.05),
    ("BOL\ufffdVAR", "CARTAGENA", 0.04), ("MAGDALENA", "SANTA MARTA", 0.03), ("RISARALDA", "PEREIRA", 0.03),
    ("CALDAS", "MANIZALES", 0.02), ("TOLIMA", "IBAGUE", 0.02), ("META", "VILLAVICENCIO", 0.02),
    ("NORTE DE SANTANDER", "CUCUTA", 0.02), ("CORDOBA", "MONTERIA", 0.015), ("HUILA", "NEIVA", 0.015),
    ("NARI\ufffdO", "PASTO", 0.01),
]
PALABRAS_A = ["Comercializadora", "Inversiones", "Distribuidora", "Constructora", "Industrias", "Servicios",
              "Agroindustrial", "Transportes", "Soluciones", "Grupo", "Laboratorios", "Inmobiliaria"]
PALABRAS_B = ["Andina", "del Caribe", "Sierra Nevada", "Pacífico", "Altiplano", "Rio Grande", "Los Llanos",
              "Ceiba", "Guayacán", "Cordillera", "Bahía", "Orquídea", "Tayrona", "Macondo", "La Esmeralda"]
SUFIJOS = ["S.A.S.", "S.A.", "LTDA.", "S.A.S. BIC"]

ROTULOS = {
    "activo_corriente": "Activos corrientes totales", "activo_total": "Total de activos",
    "pasivo_corriente": "Pasivos corrientes totales", "pasivo_total": "Total pasivos",
    "patrimonio": "Patrimonio total", "inventarios": "Inventarios corrientes",
    "efectivo": "Efectivo y equivalentes al efectivo", "ganancias_acumuladas": "Ganancias acumuladas",
    "otros": "Propiedades, planta y equipo",
    "ingresos": "Ingresos de actividades ordinarias",
    "ganancia_operacion": "Ganancia (p\ufffdrdida) por actividades de operaci\ufffdn",
    "costos_financieros": "Costos financieros", "ganancia_antes_impuestos": "Ganancia (p\ufffdrdida), antes de impuestos",
    "ganancia_neta": "Ganancia (p\ufffdrdida)",
}


def generar(carpeta: Path, anios: list[int], n: int = 6000, semilla: int = 7) -> None:
    rng = np.random.default_rng(semilla)
    carpeta.mkdir(parents=True, exist_ok=True)
    pesos_s = np.array([s[1] for s in SECTORES]); pesos_s /= pesos_s.sum()
    pesos_d = np.array([d[2] for d in DEPTOS]); pesos_d /= pesos_d.sum()

    nits = rng.choice(np.arange(800_000_000, 901_999_999), size=n, replace=False)
    sector = rng.choice(len(SECTORES), size=n, p=pesos_s)
    depto = rng.choice(len(DEPTOS), size=n, p=pesos_d)
    tam = rng.lognormal(mean=np.log(25_000_000), sigma=1.3, size=n)  # miles de pesos: ~25 mil millones
    salud = rng.normal(0.6, 0.9, size=n)
    nacimiento = np.where(rng.random(n) < 0.8, anios[0], rng.choice(anios[1:], size=n))
    nombres = [f"{rng.choice(PALABRAS_A)} {rng.choice(PALABRAS_B)} {rng.choice(SUFIJOS)}" for _ in range(n)]
    nombres = [f"{nm.split(' S.A')[0].split(' LTDA')[0]} {i % 97 + 1} {nm.split()[-1]}" if i % 5 == 0 else nm
               for i, nm in enumerate(nombres)]
    activa = np.ones(n, dtype=bool)
    instancia = 100_000

    for k, anio in enumerate(anios):
        choque = {2020: -0.45, 2021: 0.15}.get(anio, 0.0)
        sector_shock = rng.normal(0, 0.15, size=len(SECTORES))
        salud = 0.85 * salud + 0.15 * 0.6 + choque + sector_shock[sector] + rng.normal(0, 0.45, size=n)
        if k > 0:
            activa &= rng.random(n) > (0.03 + 0.05 * (salud < -1.2))  # algunas dejan de reportar
        presentes = activa & (nacimiento <= anio)
        tam = tam * np.exp(0.03 + 0.05 * np.tanh(salud) + rng.normal(0, 0.08, size=n))

        bal, res, car = [], [], []
        for i in np.where(presentes)[0]:
            ciiu, _, rot, mbase = SECTORES[sector[i]]
            h = salud[i]
            act = tam[i]
            end = float(np.clip(0.55 - 0.18 * h + rng.normal(0, 0.12), 0.05, 1.6))
            pas = act * end
            patr = act - pas
            pas_c = pas * float(np.clip(rng.normal(0.6, 0.15), 0.15, 0.98))
            rc = float(np.clip(np.exp(0.25 + 0.3 * h + rng.normal(0, 0.25)), 0.2, 6))
            act_c = pas_c * rc
            act_c = min(act_c, act * 0.95)
            inv = act_c * float(np.clip(rng.normal(0.3, 0.12), 0, 0.8))
            efe = act_c * float(np.clip(rng.normal(0.15, 0.08), 0.01, 0.7))
            ing = act * rot * float(np.exp(rng.normal(0, 0.2)))
            mop = mbase + 0.05 * h + rng.normal(0, 0.03)
            ebit = ing * mop
            cf = pas * float(np.clip(rng.normal(0.07, 0.02), 0.01, 0.15)) * (0.6 if rng.random() < 0.3 else 1)
            gai = ebit - cf
            gn = gai * (0.65 if gai > 0 else 1.0)
            ret = act * float(np.clip(0.12 + 0.08 * h + rng.normal(0, 0.06), -0.6, 0.6))

            instancia += 1
            filas_b = {"activo_corriente": act_c, "activo_total": act, "pasivo_corriente": pas_c, "pasivo_total": pas,
                       "patrimonio": patr, "inventarios": inv, "efectivo": efe, "ganancias_acumuladas": ret,
                       "otros": act - act_c}
            filas_r = {"ingresos": ing, "ganancia_operacion": ebit, "costos_financieros": cf,
                       "ganancia_antes_impuestos": gai, "ganancia_neta": gn}
            pe = "10 NIIF Plenas - Individuales" if act > 60_000_000 else "40 NIIF Pymes - Individuales"
            base = {"codigo_instancia": str(instancia), "nit": str(nits[i]), "punto_entrada": pe,
                    "fecha_corte": f"{anio}-12-31T00:00:00.000", "periodo": "Periodo Actual"}
            opcionales = {"inventarios", "efectivo", "ganancias_acumuladas", "ganancia_operacion", "costos_financieros"}
            for var, val in filas_b.items():
                if var in opcionales and rng.random() < 0.08:
                    continue
                bal.append({**base, "concepto": ROTULOS[var], "valor": None if rng.random() < 0.003 else str(int(round(val)))})
            for var, val in filas_r.items():
                if var in opcionales and rng.random() < 0.08:
                    continue
                res.append({**base, "concepto": ROTULOS[var], "valor": None if rng.random() < 0.003 else str(int(round(val)))})
            d, c, _ = DEPTOS[depto[i]]
            if rng.random() < 0.05:  # algunas empresas sin carátula ese año
                continue
            for concepto, val in [("Raz\ufffdn social de la sociedad", nombres[i]),
                                  ("Departamento de la direcci\ufffdn del domicilio", d),
                                  ("Ciudad de la direcci\ufffdn del domicilio", c),
                                  ("Clasificaci\ufffdn Industrial Internacional Uniforme Versi\ufffdn 4 A.C (CIIU)", ciiu)]:
                if concepto.startswith("Ciudad") and rng.random() < 0.1:
                    continue
                car.append({**base, "periodo": None, "concepto": concepto, "valor": val})
            # Algunas empresas también reportan estados consolidados (el pipeline debe ignorarlos)
            if rng.random() < 0.03:
                for var, val in filas_b.items():
                    bal.append({**base, "codigo_instancia": str(instancia + 5_000_000),
                                "punto_entrada": "11 NIIF Plenas - Consolidados", "concepto": ROTULOS[var],
                                "valor": str(int(round(val * 1.8)))})

        # Igual que la descarga real: todas las columnas como texto
        for nombre, filas in (("pfdp-zks5", bal), ("prwj-nzxa", res), ("6hqw-m3dm", car)):
            pd.DataFrame(filas).astype("string").to_parquet(carpeta / f"{nombre}_{anio}.parquet", index=False)
        print(f"  {anio}: {presentes.sum():,} empresas sintéticas")
