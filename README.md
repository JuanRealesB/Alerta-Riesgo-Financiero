# Alerta de riesgo financiero empresarial

Semáforo de salud financiera para las sociedades que reportan estados financieros a la Superintendencia de Sociedades de Colombia. Compara el Z'' de Altman con un modelo XGBoost y explica cada predicción con valores SHAP.


## Qué hace

1. Descarga de datos.gov.co los Estados Financieros NIIF de Supersociedades: situación financiera, resultado integral y carátula.
2. Calcula 16 indicadores de liquidez, endeudamiento, rentabilidad, actividad y tamaño, más el Z'' de Altman.
3. Define cuándo una empresa está en dificultad y entrena modelos para predecir si una empresa sana pasará a estarlo el año siguiente.
4. Compara tres enfoques con validación temporal y publica una página estática con buscador, fichas por empresa y análisis por sector.

## Datos

| Dataset | Identificador | Contenido |
| --- | --- | --- |
| Estados Financieros NIIF: Estado de Situación Financiera | `pfdp-zks5` | Activos, pasivos y patrimonio |
| Estados Financieros NIIF: Estado de Resultado Integral | `prwj-nzxa` | Ingresos, resultado operativo, costos financieros, ganancia neta |
| Estados Financieros NIIF: Carátula | `6hqw-m3dm` | Razón social, CIIU y domicilio |

Fuente: Superintendencia de Sociedades, datos abiertos en datos.gov.co, licencia [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Los resultados derivados se comparten con la misma licencia.

Los datasets están en formato largo (una fila por empresa, rubro y periodo). El pipeline toma el corte del 31 de diciembre de cada año, descarta los estados consolidados y usa el último reporte de cada empresa cuando hubo retransmisiones.

## Metodología

**Variable objetivo.** Una empresa está en dificultad en un año si su patrimonio es menor o igual a cero, o si tuvo pérdida neta y su resultado operativo no alcanzó a cubrir los costos financieros. El modelo predice si una empresa sin dificultad en el año *t* la tendrá en *t+1*. Es un indicador aproximado de deterioro, no de quiebra.

**Modelos comparados.**

| Modelo | Variables | Entrenamiento |
| --- | --- | --- |
| Z'' de Altman (1995) | Capital de trabajo, ganancias acumuladas y EBIT sobre activos; patrimonio sobre pasivos | Ninguno: coeficientes originales |
| Regresión logística | Las mismas cuatro razones de Altman | Reestimada con datos colombianos |
| XGBoost | 16 indicadores, sector y región | Calibrado con el método de Platt |

Z'' = 6,56·X1 + 3,26·X2 + 6,72·X3 + 1,05·X4. Zona de peligro por debajo de 1,1; zona segura por encima de 2,6.

**Validación temporal.** Con años etiquetados *a₁ … aₙ*: se entrena hasta *aₙ₋₂*, se hace la parada temprana y la calibración con *aₙ₋₁* y se evalúa con *aₙ*. El año más reciente, que aún no tiene resultado, es el que se puntúa en la página.

**Métricas.** AUC-ROC, AUC-PR (más informativa cuando los casos positivos son pocos), Brier y proporción de deterioros detectados en el 10 % de empresas con mayor riesgo. También se compara la zona de peligro de Altman con XGBoost marcando la misma cantidad de empresas.

**Explicaciones.** Contribuciones SHAP exactas para árboles (`pred_contribs=True` de XGBoost), agregadas por indicador y por familia.

**Semáforo.** Las empresas que ya están en dificultad van en una categoría aparte. Entre las demás: riesgo alto para el 10 % con mayor probabilidad, riesgo medio para el siguiente 20 % y riesgo bajo para el resto. Los umbrales se cambian en `config.yaml`.

## Estructura

```
├── config.yaml              # años, umbrales, autoría, parámetros del modelo
├── requirements.txt
├── src/
│   ├── pipeline.py          # orquesta todo (python -m src.pipeline)
│   ├── descarga.py          # API SODA de datos.gov.co
│   ├── conceptos.py         # rubros NIIF -> variables (expresiones regulares)
│   ├── features.py          # indicadores, Altman, variable objetivo, sector y región
│   ├── modelo.py            # entrenamiento, calibración, métricas, SHAP
│   ├── exportar.py          # JSON para la página
│   ├── og.py                # imagen de vista previa para redes
│   └── sintetico.py         # datos inventados para probar sin conexión
├── notebooks/
│   └── explorar_en_colab.ipynb
├── docs/                    # sitio de GitHub Pages
│   ├── index.html, styles.css, app.js
│   ├── og.png
│   └── data/                # resumen.json y empresas.json (generados)
└── .github/workflows/publicar.yml
```


Después de la primera ejecución, el flujo se repite el día 5 de cada mes y cada vez que cambias el código. Los años ya descargados se guardan en caché.

## Ejecutar en tu computador o en Colab

```bash
pip install -r requirements.txt
python -m src.pipeline --demo        # prueba sin conexión
python -m src.pipeline               # datos reales
python -m http.server -d docs 8000   # abre http://localhost:8000
```

El notebook `notebooks/explorar_en_colab.ipynb` clona el repositorio, ejecuta el pipeline y muestra los resultados principales.

## Si falla en la primera ejecución real

Los nombres de los rubros cambian levemente entre taxonomías. Si el pipeline no encuentra un rubro obligatorio, se detiene y muestra los rubros parecidos que sí existen en los datos. Para resolverlo:

1. Ejecuta `python -m src.pipeline --descubrir` o descarga el artefacto *reportes* del flujo de Actions.
2. Revisa `conceptos_disponibles_*.csv` y ajusta el patrón de esa variable en `src/conceptos.py`.
3. Revisa `conceptos_mapeados.csv` para confirmar qué rubro quedó asignado a cada variable.

Antes de publicar, compara dos o tres empresas conocidas con sus estados financieros para confirmar la unidad de los valores (`unidad_valor` en `config.yaml`).

## Limitaciones

- Solo incluye sociedades obligadas a reportar a Supersociedades; pueden faltar las vigiladas por otras superintendencias.
- Las empresas que dejan de reportar salen de la muestra y no cuentan como deterioro, lo que puede subestimar el riesgo.
- La variable objetivo es contable, no un evento legal de insolvencia. Una mejora natural es cruzarla con la base de procesos de insolvencia de Supersociedades.
- Un riesgo alto es una señal para revisar, no una conclusión sobre la empresa. Este proyecto es académico y no es una calificación crediticia ni una recomendación de inversión.

## Referencias

- Altman, E. I., Hartzell, J. y Peck, M. (1995). *Emerging Markets Corporate Bonds: A Scoring System*. Salomon Brothers.
- Chen, T. y Guestrin, C. (2016). XGBoost: A Scalable Tree Boosting System. *KDD '16*.
- Lundberg, S. M. y Lee, S.-I. (2017). A Unified Approach to Interpreting Model Predictions. *NeurIPS*.
- Platt, J. (1999). Probabilistic Outputs for Support Vector Machines and Comparisons to Regularized Likelihood Methods.

