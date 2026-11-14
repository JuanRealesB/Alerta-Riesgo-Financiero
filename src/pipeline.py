"""Pipeline completo: descarga -> indicadores -> modelos -> JSON para la página.

Uso:
  python -m src.pipeline                 # datos reales de datos.gov.co
  python -m src.pipeline --demo          # datos sintéticos, sin conexión (para probar)
  python -m src.pipeline --descubrir     # solo lista los rubros disponibles del último año
  python -m src.pipeline --refrescar     # vuelve a descargar los años ya guardados
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", action="store_true", help="usar datos sintéticos")
    ap.add_argument("--descubrir", action="store_true", help="listar rubros disponibles y salir")
    ap.add_argument("--refrescar", action="store_true", help="volver a descargar todo")
    ap.add_argument("--sin-descarga", action="store_true", help="usar solo lo que ya está en data/raw")
    args = ap.parse_args()

    cfg = yaml.safe_load((RAIZ / "config.yaml").read_text(encoding="utf-8"))
    datos = RAIZ / "data" / ("demo" if args.demo else "")
    raw, reportes = datos / "raw", datos / "reportes"

    if args.descubrir:
        from .descarga import descubrir_conceptos
        anio = cfg["anios"][-1]
        reportes.mkdir(parents=True, exist_ok=True)
        for nombre, ds in cfg["datasets"].items():
            df = descubrir_conceptos(ds, anio)
            ruta = reportes / f"conceptos_disponibles_{ds}_{anio}.csv"
            df.to_csv(ruta, index=False)
            print(f"{nombre} ({ds}): {len(df)} rubros -> {ruta}")
            print(df.head(25).to_string(index=False))
        return

    print("1/4 Datos")
    if args.demo:
        from .sintetico import generar
        generar(raw, cfg["anios"])
    elif not args.sin_descarga:
        from .descarga import descargar_todo
        descargar_todo(cfg, raw, refrescar=args.refrescar)

    print("2/4 Indicadores y variable objetivo")
    from .features import construir_tabla
    tabla = construir_tabla(cfg, raw, reportes)
    tabla.to_parquet(datos / "tabla_empresas.parquet", index=False)
    etiquetadas = tabla["y"].notna()
    print(f"  {len(tabla):,} empresa-año; {etiquetadas.sum():,} etiquetadas; "
          f"tasa de deterioro {tabla.loc[etiquetadas, 'y'].mean():.1%}")

    print("3/4 Modelos (validación temporal)")
    from .modelo import entrenar
    modelo = entrenar(tabla, cfg)
    modelo["booster"].save_model(str(datos / "modelo_xgboost.json"))
    (datos / "metricas.json").write_text(json.dumps(modelo["resumen"]["metricas"], ensure_ascii=False, indent=1),
                                         encoding="utf-8")

    print("4/4 Exportar para la página")
    from .exportar import exportar
    exportar(tabla, modelo, cfg, RAIZ / "docs" / "data", demo=args.demo)
    from .og import generar as generar_og
    generar_og(RAIZ / "docs")
    print("Listo. Abre docs/index.html con un servidor local: python -m http.server -d docs 8000")


if __name__ == "__main__":
    main()
