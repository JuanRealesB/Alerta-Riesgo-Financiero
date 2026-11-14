"""Imagen de vista previa (1200x630) para LinkedIn y otras redes, generada con los datos exportados."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

COLORES = {"dificultad": (122, 32, 26), "rojo": (180, 35, 24), "amarillo": (183, 121, 31), "verde": (47, 122, 78)}
PAPEL, TINTA, TENUE = (238, 242, 239), (27, 42, 58), (88, 102, 112)


def _fuente(tamano: int, serif: bool = False) -> ImageFont.FreeTypeFont:
    candidatas = (["DejaVuSerif-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"] if serif
                  else ["DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"])
    for c in candidatas:
        try:
            return ImageFont.truetype(c, tamano)
        except OSError:
            continue
    return ImageFont.load_default(size=tamano)


def generar(carpeta_docs: Path) -> None:
    empresas = json.loads((carpeta_docs / "data" / "empresas.json").read_text(encoding="utf-8"))
    resumen = json.loads((carpeta_docs / "data" / "resumen.json").read_text(encoding="utf-8"))
    campos = empresas["campos"]
    i_sem, i_pct = campos.index("sem"), campos.index("pct")
    orden = {"dificultad": 2, "rojo": 1, "amarillo": 0, "verde": 0}
    filas = sorted(empresas["filas"], key=lambda f: (orden[f[i_sem]], f[i_pct] or 0), reverse=True)

    img = Image.new("RGB", (1200, 630), PAPEL)
    d = ImageDraw.Draw(img)
    d.text((72, 70), "¿Qué empresas colombianas", font=_fuente(58, True), fill=TINTA)
    d.text((72, 140), "podrían entrar en dificultad?", font=_fuente(58, True), fill=TINTA)
    n = resumen["meta"]["n_empresas"]
    n_txt = f"{n:,}".replace(",", ".")
    d.text((72, 232), f"{n_txt} empresas puntuadas con XGBoost, SHAP y el Z'' de Altman",
           font=_fuente(28), fill=TENUE)

    x0, x1, y0, y1 = 72, 1128, 330, 500
    ancho = (x1 - x0) / max(1, len(filas))
    for k, f in enumerate(filas):
        xa = x0 + k * ancho
        h = 1.0 if f[i_sem] == "dificultad" else 0.2 + 0.8 * (f[i_pct] or 0)
        d.rectangle([xa, y1 - (y1 - y0) * h, xa + max(ancho, 1), y1], fill=COLORES[f[i_sem]])
    anio = resumen["meta"]["anio_puntuado"]
    pie = f"Estados financieros NIIF {anio}, Supersociedades (datos.gov.co)"
    if resumen["meta"].get("demo"):
        pie = "Versión de demostración con datos sintéticos"
    d.text((72, 530), pie, font=_fuente(24), fill=TENUE)
    img.save(carpeta_docs / "og.png", optimize=True)
