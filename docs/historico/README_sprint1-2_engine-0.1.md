> **HISTÓRICO — RESULTADOS DE REFERENCIA.** README de la PoC #001 (Sprints 1 y 2, cerrados el 17/09/2026). El código del Engine 0.1 que produjo estos números **no forma parte de este repositorio**: se reconstruye desde cero en la Fase 0 de `docs/06-plan-de-construccion.md`. Los resultados que aquí figuran son los **criterios de aceptación** de esa reconstrucción, no el estado actual. La matriz de casos y las decisiones de diseño están consolidadas en `docs/05-evaluacion-y-banco-de-pruebas.md`.

# CAE Engine — PoC #001 · IND240 V1.1 · Sprints 1 y 2

- **Sprint 1**: especificación de la ficha como configuración, cálculo determinista con pruebas y paquete documental sintético con 7 variantes (A–G).
- **Sprint 2**: Engine 0.1 — de la carpeta de documentos al informe de prevalidación, con grafo de evidencias y las 26 reglas.

> Todos los documentos son **SINTÉTICOS**: empresas, personas, NIF, modelos, números de serie y coordenadas inventados. Cada página lleva la marca "DOCUMENTO SINTÉTICO – SOLO PRUEBAS". Ningún resultado implica CAE garantizado.

## Estructura

```
spec/IND240_v1.1.yaml              Ficha como configuración: ámbito, exclusiones, variables y fuentes,
                                   fórmula, 26 reglas, documentación, estados, puntos interpretativos
data/reg_2019_1781_cuadro6.csv     Pérdidas de referencia de variadores (Reg. UE 2019/1781, anexo I, cuadro 6)
engine/calculo.py                  Calculation Engine determinista (Decimal, fórmula leída del YAML, traza)
engine/registro_xlsx.py            Lector del registro SCADA → N2, P_prom, h_despues, huella SHA-256
engine/ingesta.py                  Capa 1: lectura (PDF, OCR, xlsx, EXIF), clasificación y separación de PDF combinados
engine/extraccion.py               Capa 2: extracción de variables y grafo de evidencias (documento, página, confianza)
engine/reglas.py                   Capa 3: Rules Engine que ejecuta las reglas del YAML y decide el estado
engine/motor.py                    Orquestador: ingesta → extracción → consolidación → reglas → cálculo → estado
engine/informe.py, engine/cli.py   Capa 4: informe de prevalidación (markdown y JSON) y línea de comandos
generator/generar.py               Generador del paquete sintético (un modelo de datos → todos los documentos)
evaluar_casos.py                   Evalúa los 7 casos contra el ground truth y escribe los informes
tests/                             61 pruebas: cálculo, paquete y Engine end-to-end
expedientes/EXP001-*/              Carpetas que recibiría el Engine
expedientes/_resultados_esperados/ Ground truth por caso (NO se entrega al Engine)
informes/                          Informes generados por el Engine (markdown + JSON)
```

## Cómo ejecutar

```bash
pip install pyyaml openpyxl reportlab pillow pdfplumber pytest    # + poppler-utils, qpdf, tesseract-ocr(-spa)
python -m generator.generar                                       # regenera los 7 expedientes y el ground truth
python -m engine.cli expedientes/EXP001-A_completo --md informe.md --json informe.json
python evaluar_casos.py                                           # matriz esperado/obtenido + informes
python -m pytest -q                                               # 61 passed
```

## Matriz de pruebas

| Caso | Qué prueba | Estado esperado | AETOTAL (CAE) |
|---|---|---|---|
| A · completo | Expediente perfecto, 1 motor 110 kW | 🟢 PREVALIDADO | 305.829 |
| B · falta registro | N2 solo declarado (lectura puntual), sin registro de 30 días | 🟡 SUBSANABLE | 305.829 (provisional) |
| C · contradictorio | PM = 110 kW en ficha técnica/placa vs 90 kW en certificado | 🔴 BLOQUEADO (no calcula) | — |
| D · fuera de ámbito | Bomba de tornillo (desplazamiento positivo), EXC-03 | 🔴 NO ELEGIBLE | — |
| E · dos motores | + ventilador radial 55 kW | 🟢 PREVALIDADO | 461.433 |
| F · tres motores | + compresor centrífugo 160 kW; aquí h_despues < h_antes | 🟢 PREVALIDADO | 777.128 |
| G · desordenado | Nombres genéricos, PDF combinado, escaneo girado, fotos sueltas, documento irrelevante, xlsx renombrado | 🟢 PREVALIDADO + avisos | 305.829 |

Valor bruto orientativo del caso A a 100–140 €/MWh: 30,6–42,8 k€ (lo que recibe el propietario es menos, una vez descontadas las comisiones).

## Resultado del Engine 0.1 (última ejecución)

| Caso | Esperado | Obtenido | CAE | Docs | Datos con evidencia | Extracción | Segundos |
|---|---|---|---|---:|---:|---:|---:|
| A | PREVALIDADO | PREVALIDADO | 305.829 | 11 | 43 | 6/6 | 0,8 |
| B | SUBSANABLE | SUBSANABLE | 305.829 (provisional) | 10 | 34 | 4/4 | 0,6 |
| C | BLOQUEADO | BLOQUEADO | — | 11 | 43 | 6/6 | 0,8 |
| D | NO ELEGIBLE | NO ELEGIBLE | — | 11 | 43 | 6/6 | 0,8 |
| E | PREVALIDADO | PREVALIDADO | 461.433 | 14 | 72 | 12/12 | 1,2 |
| F | PREVALIDADO | PREVALIDADO | 777.128 | 17 | 101 | 18/18 | 1,6 |
| G | PREVALIDADO | PREVALIDADO | 305.829 | 15 | 47 | 6/6 | 11,9 |

7/7 estados correctos · 58/58 variables de cálculo extraídas con su evidencia · 2,5 s de media por expediente (G sube por el OCR de cuatro fotos y un escaneo).

**Cómo leer estos números.** El extractor de esta versión funciona por reglas sobre etiquetas y unidades, y se ha ajustado con estos documentos: el 100 % dice que la cadena completa funciona, no que vaya a acertar en un expediente real que no ha visto nunca. Para eso está el siguiente paso.

## Decisiones de diseño del Engine

- **Tablas antes que texto plano.** La marca de agua y los saltos de página desordenan el texto extraído y separan una etiqueta de su valor. El Engine lee primero las tablas del PDF y solo usa expresiones regulares como respaldo.
- **Vinculación por número de serie y por huella.** Cada documento se asocia a su motor por los números de serie, y el registro SCADA se vincula por SHA-256, no por el nombre del fichero (en el caso G no coinciden).
- **OCR con menos confianza.** Los datos leídos de fotografías y escaneos entran con confianza 0,75. Si discrepan de una fuente fiable no bloquean el expediente: se marcan como posible error de OCR.
- **El cálculo se detiene ante un conflicto.** Con PM contradictorio (caso C) el Engine no elige un valor ni calcula: devuelve el conflicto con las dos evidencias.
- **El orden importa.** Primero ámbito y consistencia; solo si pasan se calcula; después el resto de reglas. Así nunca se publica un ahorro apoyado en datos incoherentes.

## Trampas deliberadas para el Engine

- **p no sale de la ficha técnica del variador.** Esta declara 3,90 kW de pérdidas, pero la ficha exige las de referencia del cuadro 6: 5,55 kW para 110 kW.
- **Regla del menor h.** Se usa el menor valor de horas: h_antes en M1 y M2, y h_despues en M3.
- **La factura menciona "motor existente".** Es contexto, no una compra de motor, así que no debe activar R-AMB-02.
- **En D, la ficha y el convenio declaran ahorro.** El Engine debe ignorarlo por exclusión de ámbito.
- **En G, el registro se vincula por huella SHA-256**, no por nombre de fichero.

## Puntos interpretativos a validar con un verificador (antes del Sprint 3)

| ID | Tema | Criterio PoC | Impacto |
|---|---|---|---|
| INT-01 | Pasar las pérdidas de kW a p (%) | p = pérdidas / PM (kW). Alternativa: sobre kVA del variador (≈ +1 % de ahorro) | Medio |
| INT-03 | N2 como "media anual" acreditada con 30 días | Media de la velocidad en marcha del periodo | Alto |
| INT-04 | Extrapolar h_despues | Horas en marcha × 8760 / horas del periodo | Alto |
| INT-05 | Qué cuenta como "registro inalterable" | Exportación SCADA con huella SHA-256 declarada | Alto |
| INT-02, 06, 07 | Interpolación en el cuadro 6, redondeo, duración indicativa (Di) | Ver spec | Bajo |

## Fuentes

- Ficha IND240 V1.1 — catálogo vigente MITECO
- Reglamento (UE) 2019/1781, anexo I, cuadro 6 (BOE/DOUE)
- Orden TED/815/2023 (arts. 11, 14.9.j, 17.1) y RD 36/2023

## Límites conocidos de esta versión

- Extracción por reglas ajustada a estos documentos; falta el extractor con LLM para formatos no vistos (la interfaz ya está: `Extractor`).
- Sin validación por un experto CAE de los criterios INT-01/03/04/05.
- Una sola ficha (IND240). TRA050 y RES060 aún no están especificadas.
- Sin interfaz de usuario: línea de comandos e informes en markdown/JSON.

## Siguiente sprint (propuesta original, superada por `docs/06-plan-de-construccion.md`)

Sprint 3 — que el Engine salga de su laboratorio:
1. Extractor con LLM detrás de la misma interfaz, comparado contra el de reglas sobre los mismos 7 casos.
2. Un expediente real anonimizado (opción B del plan original) para medir la precisión fuera de casa.
3. Cerrar INT-01/03/04/05 con un verificador y actualizar el YAML.
4. Segunda ficha (TRA050, movilidad) para comprobar que el marco aguanta en otro sector.
