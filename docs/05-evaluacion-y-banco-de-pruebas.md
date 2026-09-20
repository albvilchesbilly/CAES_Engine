# CAE Engine — Evaluación y banco de pruebas

**Versión 1.0 · 18/09/2026 · Proyecto CAE (Billy)**

Este documento fija **cómo se evalúa el Engine**: los siete casos sintéticos A–G, su ground truth, el paquete documental que los materializa, las trampas deliberadas que debe superar, las cinco fuentes de verdad, las propiedades metamórficas, las métricas y la definición de hecho por módulo. Se lee **antes de escribir tests o el generator** (`docs/01` §2).

> **Nota clave.** El Engine 0.1 que produjo los resultados de la §2 (Sprints 1 y 2, cerrados el 17/09/2026) **no está en este repositorio**: se construyó en otro entorno y se reconstruye desde cero en la Fase 0 de `docs/06-plan-de-construccion.md`. Los números que aparecen aquí (7/7 veredictos, 305.829,6 kWh/año en el caso A, 58/58 variables con evidencia) son **criterios de aceptación** de esa reconstrucción, no el estado actual. A 18/09/2026 no hay ningún test en verde porque no hay ningún test.

Fuentes de este documento: `docs/historico/README_sprint1-2_engine-0.1.md` (matriz, resultados, decisiones de diseño, trampas), `docs/historico/07-backend-y-motor-de-reglas_v1.0.md` §10 (fuentes de verdad, metamórficas, métricas), `docs/historico/11-backend-funcionalidades-y-motor-de-reglas_v1.0.md` §6 (metamórficas de composición y ciclo, batería INT-xx, métrica de producto) y `spec/IND240_v1.1.yaml` (reglas citadas por id).

---

## 1. Qué demuestra y qué no el banco de pruebas

El banco de pruebas de la Fase 0 son siete carpetas de documentos sintéticos con resultado conocido. Sirve para tres cosas y no sirve para una cuarta:

| Sirve para | Cómo |
|---|---|
| **Regresión del núcleo** | Cualquier cambio en `engine/` se valida contra los 7 casos. Un veredicto que cambia, o un ahorro que se mueve un kWh, es un bug o una decisión que exige ADR |
| **Criterio de aceptación de la Fase 0** | La reconstrucción está terminada cuando `evaluar_casos.py` da 7/7 y el caso A produce exactamente 305.829,6 kWh/año |
| **Contrato entre módulos** | Cada caso ejercita una decisión de diseño concreta (§4.4): si un módulo se reescribe, los casos dicen si la decisión sigue respetada |

**Cómo leer el 100 %.** El extractor del Engine 0.1 funcionaba por reglas sobre etiquetas y unidades y se ajustó con estos mismos documentos. Que los siete casos den bien dice que **la cadena completa funciona** (ingesta → extracción → consolidación → reglas → cálculo → informe), no que el Engine vaya a acertar sobre una actuación real que no ha visto nunca. Para medir eso están las otras cuatro fuentes de verdad (§5). Un banco de pruebas que solo contenga estos siete casos no autoriza a decir nada sobre precisión en producción, y ningún texto de producto debe citar el "7/7" como evidencia de robustez (`CLAUDE.md` §7).

Lo que sí se exige, y no es poco: que el Engine reconstruido reproduzca los siete veredictos, los ahorros de A y G exactamente, y que E y F sean multiunidad `PREVALIDADO` con el ground truth recalculado (§2.3).

Resultado de referencia del Engine 0.1 (última ejecución, 17/09/2026), que la reconstrucción usa como línea base y no como cifra a igualar:

| Caso | Esperado | Obtenido | CAE (kWh) | Docs | Datos con evidencia | Extracción | Segundos |
|---|---|---|---|---:|---:|---:|---:|
| A | PREVALIDADO | PREVALIDADO | 305.829 | 11 | 43 | 6/6 | 0,8 |
| B | SUBSANABLE | SUBSANABLE | 305.829 (provisional) | 10 | 34 | 4/4 | 0,6 |
| C | BLOQUEADO | BLOQUEADO | — | 11 | 43 | 6/6 | 0,8 |
| D | NO ELEGIBLE | NO ELEGIBLE | — | 11 | 43 | 6/6 | 0,8 |
| E | PREVALIDADO | PREVALIDADO | 461.433 | 14 | 72 | 12/12 | 1,2 |
| F | PREVALIDADO | PREVALIDADO | 777.128 | 17 | 101 | 18/18 | 1,6 |
| G | PREVALIDADO | PREVALIDADO | 305.829 | 15 | 47 | 6/6 | 11,9 |

"Extracción" cuenta variables de cálculo extraídas con evidencia (58/58 en total: seis por motor en A, C–G, cuatro en B). Qué seis variables eran exactamente no está documentado fuera del código del Engine 0.1; la deducción coherente con la spec es PM, N1, N2, h_antes, h_despues y P_prom, y en B faltan las dos que se derivan del registro. El generator y `evaluar_casos.py` reconstruidos fijan la lista y la dejan escrita en el ADR-002. "Datos con evidencia" es el número de evidencias consolidadas con cita. Los tiempos son orientativos: G sube por el OCR de cuatro fotos y un escaneo.

---

## 2. Los siete casos A–G

### 2.1 Matriz de casos

Todos parten de un mismo caso base (una actuación IND240 sobre un motor de 110 kW) y se derivan como variaciones (`generator/casos.py`). Las reglas que "deben dispararse" se deducen de `spec/IND240_v1.1.yaml`; el comportamiento del Engine 0.1 regla a regla no está documentado fuera de su código, así que esta columna es **lo que el Engine reconstruido debe hacer según la spec**, y los tests de `test_reglas.py` y `test_engine_e2e.py` la protegen.

| Caso | Carpeta | Qué prueba | Veredicto esperado | AETOTAL (kWh/año) | Reglas que deben dispararse |
|---|---|---|---|---|---|
| A | `EXP001-A_completo` | Actuación perfecta, 1 motor 110 kW | `PREVALIDADO` | 305.829 (305.829,6 sin truncar) | Ninguna `FALLA`. `R-CAL-02` `CUMPLE` (110 kW tiene fila exacta). Sin avisos |
| B | `EXP001-B_falta_registro` | N2 solo declarado (lectura puntual en certificado y ficha), sin registro de 30 días | `SUBSANABLE` | 305.829 (provisional, no acreditado) | `R-EVD-04` `FALLA` (N2 no es `derivado`). `R-DOC-01` `FALLA` (falta `EVD-01`, obligatorio). `R-EVD-01`, `R-EVD-02`, `R-EVD-03` y `R-CON-03` `NO_EVALUABLE` (no hay registro ni N2 derivado). Ninguna bloqueante falla |
| C | `EXP001-C_contradictorio` | PM = 110 kW en ficha técnica del motor y placa vs 90 kW en certificado del instalador | `BLOQUEADO` (no calcula) | — | `R-CON-01` `FALLA`. `valor_consumido(PM) = null` con las dos evidencias. Fases 3–4 no se ejecutan: `R-CAL-03` y `R-CON-06` `NO_EVALUABLE` |
| D | `EXP001-D_fuera_ambito` | Bomba de tornillo (desplazamiento positivo), exclusión `EXC-03` | `NO_ELEGIBLE` | — | `R-AMB-01` `FALLA`. Se detiene en fase 1: no se calcula aunque ficha y convenio declaren ahorro; `R-CON-06` no se evalúa |
| E | `EXP001-E_dos_motores` | + ventilador radial 55 kW (M2) | `PREVALIDADO` | 461.433 en el Engine 0.1 (ver §2.3) | Ninguna `FALLA`. `R-CON-07` `CUMPLE` con 2 motores en todas las fuentes. `R-CON-04` `CUMPLE` por motor |
| F | `EXP001-F_tres_motores` | + compresor centrífugo 160 kW (M3) con `h_despues < h_antes` | `PREVALIDADO` | 777.128 en el Engine 0.1 (ver §2.3) | Ninguna `FALLA`. `R-CON-07` `CUMPLE` con 3 motores. La derivación `h = min(h_antes, h_despues)` toma `h_despues` en M3 y `h_antes` en M1 y M2 |
| G | `EXP001-G_desordenado` | Nombres genéricos, PDF combinado, escaneo girado, fotos sueltas, documento irrelevante, xlsx renombrado | `PREVALIDADO` + avisos | 305.829 | Ninguna regla de la spec `FALLA`. Avisos de **clasificación e ingesta** (no son reglas R-*): documento no clasificado / irrelevante, PDF separado en varios documentos, escaneo con confianza OCR 0,75, registro vinculado por hash con nombre de fichero distinto |

Notas sobre la columna de reglas:

- En B, que la actuación sea `SUBSANABLE` y no `BLOQUEADO` es la **garantía `NO_EVALUABLE` → `SUBSANABLE`** de `docs/04`: `R-CON-03` no puede evaluarse (no hay N2 derivado), pero la carencia la recoge `R-EVD-04`. El Spec Registry comprueba esta garantía al cargar la ficha. El cálculo provisional de B usa el N2 declarado y `h = h_antes` (no hay `h_despues` derivable); se muestra como estimación no acreditada.
- En C, la placa de características es una foto (OCR, confianza 0,75) y coincide con la ficha técnica; el conflicto que bloquea es entre dos fuentes fiables (ficha técnica del motor y certificado del instalador). Un desacuerdo solo con la placa no bloquearía: se marcaría como posible error de OCR (§4.4).
- En D, el orden de fases es lo que se prueba: ninguna regla de consistencia o de cálculo debe aparecer como `FALLA` en el informe, porque no se llega a ellas.
- `R-CAL-02` (`AVISO`, INT-02) debe dar `CUMPLE` en A–G: 110 kW tiene fila exacta en el cuadro 6. Para las potencias de M2 y M3 (55 y 160 kW) el generator reconstruido debe elegir valores con fila exacta o, si no la hubiera, documentar en el ADR que E y F llevan aviso INT-02.

### 2.2 Qué varía en cada caso respecto al base

El generator define cada caso como una **variación declarada** sobre el caso base (`generator/casos.py`), no como un juego de documentos escrito a mano. Esto es lo que cambia y lo que el informe de prevalidación debe mostrar:

| Caso | Variación sobre el base | Lo que el informe debe mostrar |
|---|---|---|
| A | Ninguna | Veredicto `PREVALIDADO`; 26 reglas evaluadas, ninguna `FALLA`; traza del cálculo con cada variable y su evidencia; AETOTAL 305.829 kWh (305.829,6 sin truncar) |
| B | Se omite `registro_funcionamiento`; el certificado y la ficha siguen declarando N2 = 1.188 rpm y P_prom | Veredicto `SUBSANABLE`; `R-EVD-04` y `R-DOC-01` en `FALLA`; lista de `NO_EVALUABLE` con el dato que falta; AETOTAL marcado **provisional / no acreditado**; petición de subsanación: "registro ≥ 30 días con huella" |
| C | En `certificado_instalador`, PM = 90 kW; el resto de fuentes mantienen 110 kW | Veredicto `BLOQUEADO`; `R-CON-01` en `FALLA`; conflicto con las **dos** evidencias (documento, página, texto literal); sin AETOTAL; sin cálculo provisional |
| D | `tipo_equipo_accionado = bomba_desplazamiento_positivo` (tornillo) en ficha del equipo y certificado; ficha cumplimentada y convenio declaran ahorro | Veredicto `NO_ELEGIBLE`; `R-AMB-01` en `FALLA` con referencia `EXC-03`; sin AETOTAL; las reglas de fases 2–5 no aparecen como `FALLA` |
| E | Se añade M2 (ventilador radial, 55 kW) con sus documentos por motor; factura, certificado, informe fotográfico y ficha cumplimentada cubren 2 motores | `PREVALIDADO`; un bloque de cálculo por motor con su nº de serie; AETOTAL = AEM(M1) + AEM(M2) |
| F | Se añade M3 (compresor centrífugo, 160 kW) con `h_despues < h_antes` | `PREVALIDADO`; en M3 la traza indica `h = h_despues` (menor); en M1 y M2, `h = h_antes` |
| G | Mismos datos que A, distinta forma: nombres genéricos (`doc1.pdf`, `scan.pdf`, `datos.xlsx`), varios documentos en un solo PDF, un escaneo girado, cuatro fotos sueltas, un documento irrelevante | `PREVALIDADO`; mismo AETOTAL que A; sección de avisos de ingesta y clasificación; el registro aparece vinculado por hash con su nombre real y el declarado |

Toda variación es un cambio en el **modelo de datos** del caso, nunca una edición manual del documento generado. Si un caso necesita un documento que el modelo no puede expresar, se amplía el modelo (y `docs/01` §3.4).

### 2.3 Parámetros del caso A (reproducible exactamente)

| Variable | Valor | Origen |
|---|---|---|
| PM | 110 kW | ficha técnica del motor (fuente primaria), placa, certificado, ficha cumplimentada |
| N1 | 1.485 rpm | ficha técnica del motor |
| N2 | 1.188 rpm | media en `MARCHA` del registro de funcionamiento (INT-03); cruza con certificado y ficha ± 1 rpm |
| h_antes | 6.000 h | registro de horas previo |
| h_despues | ≥ 6.000 h | extrapolado del registro (INT-04); en A no es el menor |
| h | 6.000 h | `min(h_antes, h_despues)` |
| perdidas_ref_kw | 5,55 kW | `data/reg_2019_1781_cuadro6.csv`, fila 110 kW (**no** los 3,90 kW de la ficha del variador) |
| p | 5,55 / 110 = 0,050454… (5,0455 %) | INT-01 |
| AEM = AETOTAL | **305.829,6 kWh/año** | `PM * (1 - (N2/N1)**3) * (1 - p) * h` con `Decimal` |
| AETOTAL (CAE) | 305.829 kWh | truncado a kWh entero (INT-06) |

El valor 305.829,6 es el que protege `test_calculo.py` y el que `CLAUDE.md` exige en la puerta de integración. Si cambia, o hay un bug o hay una decisión que se registra en ADR.

**Nota obligatoria sobre E y F.** Los totales 461.433 y 777.128 kWh/año proceden del Engine 0.1 original. Los parámetros de los motores 2 (ventilador radial, 55 kW) y 3 (compresor centrífugo, 160 kW, con `h_despues < h_antes`) **no están documentados fuera de aquel código**: no se conocen sus N1, N2 ni horas. Por tanto el generator reconstruido **fija sus propios parámetros** para M2 y M3, **recalcula el ground truth** de E y F con la misma fórmula y lo **registra en `docs/decisiones/ADR-002-reconstruccion-engine-0.1.md`** (`docs/01` §6). Los requisitos que sí son criterio de aceptación:

- E y F son `PREVALIDADO` y multiunidad (2 y 3 motores), con `AETOTAL = sum(AEM)` y un `AEM` por motor con su propia traza.
- F ejercita la regla del menor `h`: en M3 `h_despues < h_antes`, de modo que `h` toma `h_despues`; en M1 y M2 toma `h_antes`. Un test comprueba que cambiar cuál es el menor cambia el resultado.
- Los nuevos totales no se "igualan" a 461.433 y 777.128. Se calculan y se documentan; a partir de entonces son el ground truth.

---

## 3. Ground truth: `expedientes/_resultados_esperados/`

Un fichero JSON por caso, producido por `generator/generar.py` a partir del **mismo modelo de datos** que genera los documentos (`generator/modelo_caso.py`). Así ground truth y documentos no pueden discrepar. **Nunca se entrega al Engine**: `evaluar_casos.py` y los tests lo leen; `engine/` no lo conoce.

Contenido por caso:

| Campo | Qué contiene | Ejemplo (caso B) |
|---|---|---|
| `caso` | Identificador y carpeta | `EXP001-B_falta_registro` |
| `veredicto_esperado` | Uno de `NO_ELEGIBLE`, `BLOQUEADO`, `SUBSANABLE`, `PREVALIDADO` | `SUBSANABLE` |
| `reglas_falladas_esperadas` | Ids de regla que deben resultar `FALLA` | `["R-EVD-04", "R-DOC-01"]` |
| `reglas_no_evaluables_esperadas` | Ids que deben resultar `NO_EVALUABLE` (opcional; se comprueba si está) | `["R-EVD-01", "R-EVD-02", "R-EVD-03", "R-CON-03"]` |
| `aetotal_esperado` | kWh/año exacto (`Decimal` como cadena) y truncado; `null` si no calcula; `provisional: true` en `SUBSANABLE` | `"305829.6"`, `305829`, provisional |
| `motores` | Por motor: nº de serie de motor y variador, PM, N1, N2, h_antes, h_despues, h, p, AEM | — |
| `variables_consolidadas` | Por variable: valor esperado, `evidencia` esperada (`demostrado` / `declarado` / `derivado`), tipo de documento y nº de fuentes que deben aportarla | `N2: 1188, evidencia: declarado, fuentes: [certificado_instalador, ficha_cumplimentada]` |
| `conflictos_esperados` | Variables con `valor_consumido = null` y las dos evidencias (solo C) | — |
| `documentos` | Lista de ficheros con tipo esperado y SHA-256 | 10 entradas |
| `avisos_esperados` | Avisos de clasificación/ingesta (solo G) | — |

Esqueleto orientativo (los nombres de campo definitivos los fija `generator/generar.py` y se documentan en `docs/01` §3.5 cuando existan):

```json
{
  "caso": "EXP001-A_completo",
  "ficha": "IND240", "version_ficha": "1.1", "version_spec": "0.1.0",
  "veredicto_esperado": "PREVALIDADO",
  "reglas_falladas_esperadas": [],
  "reglas_no_evaluables_esperadas": [],
  "aetotal_esperado": {"exacto": "305829.6", "cae": 305829, "provisional": false},
  "motores": [
    {"num_serie_motor": "…", "num_serie_variador": "…",
     "PM": "110", "N1": "1485", "N2": "1188",
     "h_antes": "6000", "h_despues": "…", "h": "6000",
     "perdidas_ref_kw": "5.55", "p": "0.0504545…", "AEM": "305829.6"}
  ],
  "variables_consolidadas": {
    "PM": {"valor": "110", "evidencia": "demostrado",
           "fuentes": ["ficha_tecnica_motor", "placa_caracteristicas_foto",
                       "certificado_instalador", "ficha_cumplimentada"]}
  },
  "conflictos_esperados": [],
  "documentos": [{"fichero": "…", "tipo": "ficha_cumplimentada", "sha256": "…"}],
  "avisos_esperados": []
}
```

Los valores numéricos se guardan como cadenas para que `Decimal` los lea sin pasar por `float`.

Regla de cambio: **el ground truth solo cambia con ADR** (`CLAUDE.md` regla 9). Si un cambio en `engine/` hace que un caso deje de coincidir, lo que se toca primero es el código; si la conclusión es que el ground truth estaba mal, se escribe el ADR, Billy lo aprueba y entonces se regenera. Un `git diff` en `_resultados_esperados/` sin ADR asociado es un defecto.

---

## 4. Paquete sintético

### 4.1 Los documentos de cada caso

La lista de tipos sale de la sección `documentacion` y de los campos `fuentes` de `spec/IND240_v1.1.yaml`. El caso A del Engine 0.1 tenía 11 documentos; se corresponden con estos tipos:

| # | Tipo (`tipo` en la spec) | Id spec | Formato | Aporta |
|---|---|---|---|---|
| 1 | `ficha_cumplimentada` | DOC-01 | PDF | titular, fechas, PM, N1, N2 declarado, nº de serie del variador, firma |
| 2 | `declaracion_responsable` | DOC-02 | PDF | titular (NIF, razón social) |
| 3 | `factura` | DOC-03 | PDF | titular, fecha (inicio), nº de serie del variador, líneas (ninguna de motor ni equipo) |
| 4 | `informe_fotografico` | DOC-04 | PDF con fotos | fotos ANTES/DESPUÉS por motor, placa de características (OCR), nº de serie |
| 5 | `certificado_instalador` | DOC-05 | PDF | fecha fin, PM, N1, P_prom y N2 declarados, nº de serie, tipo de equipo, régimen previo, hash del registro |
| 6 | `registro_funcionamiento` | EVD-01 | **xlsx** | intervalos con estado, velocidad y potencia ≥ 30 días → N2, P_prom, h_despues; huella SHA-256 |
| 7 | `registro_horas_previo` | EVD-02 | PDF | h_antes, régimen previo, nº de serie del motor |
| 8 | `ficha_tecnica_motor` | EVD-03 | PDF | PM, N1, nº de serie del motor (fuente primaria) |
| 9 | `ficha_tecnica_variador` | EVD-04 | PDF | nº de serie del variador y **pérdidas declaradas (trampa)** |
| 10 | `ficha_tecnica_equipo_accionado` | EVD-05 | PDF | tipo de equipo accionado |
| 11 | `convenio_cae` | PRC-01 | PDF | partes, título, localización, ahorro anual, contraprestación, vida útil, fecha de firma |

`pedido` figura como fuente de `fecha_inicio_actuacion` en la spec pero **no** forma parte de los 11 documentos del caso A; el generator puede incluirlo como documento opcional en un caso futuro. `certificado_tecnico_competente` (DOC-05B) es condicional y no aparece en ningún caso A–G.

Variaciones por caso: B omite el `registro_funcionamiento` (10 documentos). C y D tienen los 11 con un dato alterado. E y F añaden los documentos por motor de M2 y M3 (en el Engine 0.1: 14 y 17 ficheros; qué documentos se duplican por motor y cuáles se amplían —factura, certificado, informe fotográfico— lo fija el generator reconstruido y consta en el ADR). G reparte los mismos datos de A en 15 ficheros: un PDF combinado, un escaneo girado, fotos sueltas, un documento irrelevante y el xlsx con nombre genérico.

### 4.2 Marca y datos

- Cada página de cada documento lleva la marca visible **"DOCUMENTO SINTÉTICO – SOLO PRUEBAS"** (`generator/marcas.py`); las fotos llevan EXIF sintético. `test_generator.py` comprueba la marca página a página.
- Empresas, personas, NIF, modelos, números de serie, coordenadas y referencias catastrales son inventados. Nunca datos reales, ni anonimizados, en `expedientes/`.
- Los documentos se commitean para que los tests no dependan de `reportlab`/`pillow`; `python -m generator.generar` los regenera de forma determinista (mismo modelo → mismos bytes, o al menos mismos datos y mismo ground truth).

### 4.3 Trampas deliberadas

Cada una existe para que el Engine falle si toma el atajo equivocado. Ninguna se elimina del paquete sin ADR.

| Trampa | Dónde | Qué debe hacer el Engine | Regla / test que lo protege |
|---|---|---|---|
| **p no sale de la ficha del variador**: declara 3,90 kW de pérdidas | ficha_tecnica_variador (A–G) | Usar 5,55 kW del cuadro 6 para 110 kW; ignorar el valor del fabricante | `R-CAL-04` (`BLOQUEANTE_DATOS`), `test_calculo.py`, `test_tablas.py` |
| **Regla del menor h** | F (M3 con `h_despues < h_antes`) | `h = min(h_antes, h_despues)` por motor | `test_calculo.py` (min(h)), `test_engine_e2e.py` (F) |
| **La factura menciona "motor existente"** | factura (A–G) | Es contexto, no una línea de compra de motor: `R-AMB-02` `CUMPLE` | `test_reglas.py` (R-AMB-02 con línea de contexto) |
| **Ficha y convenio declaran ahorro en D** | D | Ignorarlo: `NO_ELEGIBLE` por `R-AMB-01`, sin cálculo | `test_engine_e2e.py` (D), metamórfica "excluido → NO_ELEGIBLE" |
| **El registro no se llama como se espera** | G (xlsx renombrado) | Vincular por SHA-256 declarado en el certificado, no por nombre | `R-EVD-03`, `test_ingesta.py` |
| **Placa fotografiada (OCR) frente a documentos nativos** | C y G | Entrar con confianza 0,75; no bloquear por sí sola | `test_evidencias.py` |
| **N2 declarado sin registro** | B | Marcar `declarado`, no `derivado`; `SUBSANABLE`, no `PREVALIDADO` ni `BLOQUEADO` | `R-EVD-04`, `test_spec_registry.py` (garantía), `test_engine_e2e.py` (B) |

### 4.4 Decisiones de diseño del Engine 0.1 que los tests deben proteger

Son las decisiones probadas en Sprints 1–2 (`docs/historico/README_sprint1-2_engine-0.1.md`). La reconstrucción las adopta; el detalle de arquitectura está en `docs/03` y `docs/04`.

1. **Tablas antes que texto plano.** La marca de agua y los saltos de página desordenan el texto extraído y separan etiqueta de valor. Se leen primero las tablas del PDF; las expresiones regulares son respaldo. (`engine/extraccion.py`; `test_engine_e2e.py` sobre G.)
2. **Vinculación por número de serie y por huella.** Cada documento se asocia a su motor por `num_serie_motor` / `num_serie_variador` (`clave_union: true` en la spec); el registro SCADA se vincula por SHA-256, nunca por nombre de fichero. (`engine/ingesta.py`, `engine/evidencias.py`; `test_ingesta.py`.)
3. **OCR con menos confianza.** Evidencias de foto o escaneo entran con confianza 0,75. Si discrepan de una fuente fiable no bloquean: se marcan como posible error de OCR. (`test_evidencias.py`.)
4. **El cálculo se detiene ante un conflicto.** Con PM contradictorio el Engine no elige ni calcula: `valor_consumido = null`, se muestran las dos evidencias (`CLAUDE.md` regla 6). (`test_evidencias.py`, `test_engine_e2e.py` sobre C.)
5. **El orden importa.** Cabecera bloqueante → ámbito → consistencia → cálculo → post-cálculo → resto (orden de presentación; el de ejecución evalúa `resto` antes del cálculo, `docs/04` §5.1). Nunca se publica un ahorro apoyado en datos incoherentes. (`engine/reglas.py`; `test_reglas.py` (fases), `test_engine_e2e.py` sobre C y D.) **Ojo: la parte de "nunca se publica" no está protegida en el caso general** — ver H3 en §4.5.
6. **Tres capas por dato** (documento → interpretación → cálculo) y cita obligatoria: cada variable consolidada lleva documento, página, texto literal, método y confianza. El Engine 0.1 lo cumplía en 58/58 variables de cálculo; la reconstrucción debe cumplirlo en el 100 % de las variables que entren en la fórmula. (`test_evidencias.py`, `test_engine_e2e.py`.)


### 4.5 Huecos conocidos del banco de pruebas (`/contrastar` 20/09/2026)

Hallazgos **verificados por mutación** en esta pasada. No son defectos del motor: el motor hace lo correcto
hoy. Son sitios donde el banco **no se daría cuenta si dejara de hacerlo**, que es justo lo que un banco de
regresión existe para impedir. Están abiertos, con dueño `qa-evaluacion`.

| Id | Qué no está protegido | Cómo se verificó | Qué pasa si se rompe | Prioridad |
|---|---|---|---|---|
| **H3** | La guarda `elif bloqueo_previo` de `engine/reglas.py` (la que impide calcular cuando una regla `BLOQUEANTE_DATOS` de `cabecera` o `consistencia` ha fallado **sin conflicto**) | Anulada la rama: **2.499 tests, 78 e2e y los 7/7 casos siguen en verde**, y caso A sigue en 305.829,6 | Una actuación `BLOQUEADO` por `R-TMP-01` (fecha de inicio posterior a la de fin) **publica 305.829,6 kWh/año**. Medido. Es la regla de oro «nunca se publica un ahorro apoyado en datos incoherentes» sin red | **ALTA** |
| **H6** | El **valor** de las tolerancias y fronteras. `R-CON-03` declara `abs(N2.declarado - N2.derivado) <= 1`, y sus tests usan Δ = 0 (cumple) y Δ = 12 (falla) | Razonado sobre los dos tests: `< 1` y `<= 10` sobreviven ambos | La tolerancia se puede cambiar (o convertir en estricta) sin que nada avise. Mismo patrón en `rango_plausible` y en los ≥ 30 días de `R-EVD-01` | MEDIA |
| **H4** | Que una `R-CAL-03` fallida deje el ahorro retirado **vista desde la evaluación**. La retirada sí está probada un nivel más abajo (`test_calculo.py::test_fis_02_retira_el_resultado`) | `test_reglas.py` afirma `FALLA` y `BLOQUEADO`, no que `evaluacion.calculo.total` sea `None`; comprobado que hoy lo es | Poco: `engine/calculo.py` retira por su cuenta y su test lo cubre. Es cierre de la cadena, no un agujero | BAJA |

**Por qué H3 es el importante.** El motor tiene dos defensas contra publicar un ahorro incoherente: la guarda
de política en `engine/reglas.py` (no se calcula si hay bloqueo) y las precondiciones físicas de
`engine/calculo.py` (`N2 < N1` y demás). Las segundas tapan a las primeras en los casos que el banco recorre
—por eso el mutante sobrevive—, pero **solo cubren los bloqueos que además son físicamente imposibles**. Un
bloqueo documental o temporal (`R-TMP-01`, `R-CON-04`, `R-CON-05`) no tiene precondición física que lo pare,
y ahí la única defensa es la guarda que ningún test sujeta. El caso C del banco no sirve: bloquea **por
conflicto**, que entra por la otra rama (`if bloqueo_por_conflicto`).

**Lo que cierra H3**: un test de `test_reglas.py` con una `BLOQUEANTE_DATOS` no física fallada que afirme
`evaluacion.calculo is None`, y un caso del banco (o una metamórfica) con la misma forma. Mientras no exista,
esta fila de §4.4 promete más de lo que el banco sostiene.

**Comprobado y descartado en esta pasada**: se sospechó que una corrección humana no respetaba
`rango_plausible`. **Es falso**: una corrección de `PM` a 999.999 kW produce el aviso «valor 999999 fuera del
rango plausible [0.12, 1000]». La corrección pasa por la misma consolidación que cualquier evidencia.

---

## 5. Cinco fuentes de verdad

Por orden de disponibilidad. Los siete casos son solo la primera.

| # | Fuente | Qué aporta | Necesita | Estado |
|---|---|---|---|---|
| 1 | **Banco de casos A–G** | Regresión del núcleo; criterio de aceptación de la Fase 0 | `generator/`, `tests/`, `evaluar_casos.py` | `F0` |
| 2 | **Fábrica de casos** | El mismo modelo de datos renderizado en plantillas, vocabularios y calidades de escaneo no vistas; un **conjunto reservado** que nunca se usa para ajustar el extractor | Ampliar `generator/` (Sprint 3) | `NUEVO` |
| 3 | **Documentos reales públicos** | Fichas técnicas de fabricantes de motores y variadores; formato de exportación del registrador de variadores Schneider Altivar (`docs/07` §3.4) | Recopilación; sin datos de cliente | `NUEVO` |
| 4 | **Pruebas metamórficas** | Propiedades que se cumplen sin ground truth (§6) | Solo código | `F0` las seis mínimas; `NUEVO` composición y ciclo |
| 5 | **Modo sombra** con el delegado partner | Engine en paralelo al proceso manual; las rectificaciones reales del verificador, GA y CN son las etiquetas | Delegado partner con sandbox (`docs/02` §9) | `NUEVO`; depende de decisión de Billy |

El activo defendible del proyecto es el conjunto de casos reales con sus errores y correcciones (fuente 5 realimentando la 1), no el extractor ni el modelo de lenguaje. Cada actuación revisada por un profesional alimenta el banco (`docs/03` §11), previa anonimización con validación humana (`docs/03`, seguridad).

---

## 6. Pruebas metamórficas

Propiedades que deben cumplirse para **cualquier** caso, con o sin ground truth. Se implementan en `tests/test_metamorficas.py` sobre los casos A–G como semilla; en Sprint 3 se aplican también a la fábrica de casos.

### 6.1 Las seis mínimas (`F0`)

| # | Transformación | Propiedad | Generaliza |
|---|---|---|---|
| M-01 | Renombrar, reordenar, girar o combinar ficheros | Veredicto y AETOTAL **no cambian**; solo pueden aparecer avisos de clasificación | Caso G |
| M-02 | Alterar `PM` en un solo documento fiable | Veredicto pasa a `BLOQUEADO` con `R-CON-01` `FALLA` y `valor_consumido(PM) = null` | Caso C |
| M-03 | Quitar un documento obligatorio | El veredicto **nunca mejora** (orden `NO_ELEGIBLE` > `BLOQUEADO` > `SUBSANABLE` > `PREVALIDADO`) | Caso B |
| M-04 | Cambiar `tipo_equipo_accionado` a uno excluido | `NO_ELEGIBLE` con `R-AMB-01` `FALLA`, aunque ficha y convenio declaren ahorro | Caso D |
| M-05 | Añadir un documento irrelevante | Nada cambia salvo un aviso de documento no clasificado | Caso G |
| M-06 | Duplicar un documento | Nada cambia; el duplicado se detecta por SHA-256 | — |

### 6.2 De composición (`NUEVO`, Sprint 4, `engine/compositor.py`)

- Reordenar actuaciones dentro de un expediente no cambia su validez.
- Añadir una actuación de otra CCAA (o de otro año, sector o verificador) invalida el expediente (`R-EXP-*`, `docs/04`).
- Quitar la única actuación `SUBSANABLE` de un grupo elimina el aviso de contagio.

### 6.3 De ciclo (`NUEVO`, Sprint 3, `engine/estados.py` y `engine/eventos/`)

- Ningún evento con actor `agente` o `motor` puede mover una actuación de `ENTREGADA` a `EN_PLATAFORMA`: solo un actor `humano` con `FirmaRegistrada`.
- El replay del log de eventos reproduce veredicto y ahorro bit a bit (`docs/03`, N8).
- Con `agentes/` y `salida/` ausentes, `engine/` produce el mismo veredicto que con ellos presentes (`test_modo_degradado.py`; `F0`).

---

## 7. Métricas

### 7.1 Por agente (`docs/03` §11; `docs/03`, agent runtime)

Ningún rol de agente entra en producción sin conjunto de evaluación y línea base propios; el umbral numérico está por definir (decisión de Billy).

| Métrica | Definición | Contra qué |
|---|---|---|
| **Acierto** | Variables extraídas cuyo valor y evidencia coinciden con el ground truth / variables esperadas | Casos A–G, fábrica de casos (conjunto reservado) |
| **Coste** | Coste por actuación (tokens, llamadas, latencia), registrado en la traza del runtime | Presupuesto por actuación |
| **Tasa de desacuerdo** | % de valores en que el extractor por reglas y el extractor LLM discrepan sobre el mismo documento. No es un conflicto documental: es un desacuerdo de lectura, se escala a revisión humana y se mide | Doble extracción (Sprint 3, paso 4) |

### 7.2 De producto

| Métrica | Definición | Cuándo tiene valor |
|---|---|---|
| **% de actuaciones `PREVALIDADO` que llegan a `VERIFICADA_FAVORABLE` sin requerimiento** | Es la métrica de `docs/00` §1 hecha medible sobre estados de la plataforma oficial | A partir del modo sombra; antes, cero valor |
| **Horas de trabajo especializado sustituidas por minutos de revisión** | Horas del técnico por actuación antes y después del Engine | Con el delegado partner; las preguntas 2–4 de `docs/08` §6 la alimentan |
| **% de actuaciones que pasan la primera revisión sin subsanación** | Actuaciones sin rectificación del verificador / GA / CN en el primer envío | Modo sombra y producción |

### 7.3 Batería INT-xx contra el sandbox (`NUEVO`; depende de `docs/HUECOS.md` API-12)

Para cada interpretación abierta (INT-01, 03, 04, 05 de impacto medio/alto; INT-02, 06, 07 de impacto bajo), **al menos dos casos** que produzcan resultados distintos según el criterio adoptado y su alternativa (p. ej. INT-01: p sobre kW del motor frente a kVA del variador, ≈ 1 % de ahorro en 110 kW). La respuesta de la plataforma oficial discrimina cuál es el criterio válido; el resultado se registra como ADR y, si procede, como diff de spec en `spec/propuestas/`. Hasta que exista sandbox, la batería se prepara pero no se puede resolver.

---

## 8. Definición de hecho y tests por módulo

Definición de hecho para cualquier cambio (`CLAUDE.md` §5): `pytest -q` en verde; `evaluar_casos.py` 7/7 veredictos; caso A en 305.829,6 kWh/año; nueva regla en código → test que verifica su `logica` del YAML; marca de estado actualizada en `docs/03`/`docs/04`; `docs/01` actualizado si cambia la estructura. Un test que rompe no se borra ni se relaja: se explica.

Mapa módulo → fichero de tests (`docs/01` §3.6). Todos son `F0` salvo donde se indica.

| Módulo | Fichero de tests | Qué exige como mínimo |
|---|---|---|
| `engine/expresiones.py` | `test_expresiones.py` | Todas las funciones que usa `IND240_v1.1.yaml` en `logica` y `formula` están en la lista blanca; función desconocida → error de carga; no existe `eval` en el módulo (test que inspecciona el código) |
| `engine/calculo.py` | `test_calculo.py` | Caso A = `Decimal("305829.6")` exacto; truncado a 305.829; `float` ausente; FIS-01 y FIS-02 detectan valores imposibles; `min(h)` toma `h_despues` cuando es menor |
| `engine/tablas.py` | `test_tablas.py` | 110 kW → 5,55 kW; fila inexistente → aviso INT-02 con interpolación entre adyacentes; vigencia respetada |
| `engine/spec_registry.py` | `test_spec_registry.py` | Carga `IND240_v1.1.yaml` con 26 reglas; rechaza cualquier fichero de `spec/propuestas/`; garantía "toda bloqueante que pueda quedar `NO_EVALUABLE` tiene una `SUBSANABLE` que recoge la carencia" |
| `engine/reglas.py` | `test_reglas.py` | Por cada una de las 26 reglas: un caso que `CUMPLE` y uno que `FALLA`; `NO_EVALUABLE` cuando falta el dato; asignación a fases; veredicto por severidad; en D no se evalúan fases 2–5, en C no se evalúan 3–4 |
| `engine/evidencias.py` | `test_evidencias.py` | Tres capas por dato; conflicto entre fiables → `valor_consumido = null` con las dos evidencias; OCR 0,75 no bloquea; `cruce: normalizado` iguala "S.L." y "SL"; tolerancias `±1 rpm` y `±0,5 kW` |
| `engine/ingesta.py` | `test_ingesta.py` | SHA-256 de todo fichero antes de cualquier transformación; separación de PDF combinado; vinculación del xlsx por hash cuando el nombre no coincide; EXIF leído |
| `engine/clasificacion.py`, `engine/extraccion.py`, `engine/registro_xlsx.py` | `test_ingesta.py`, `test_engine_e2e.py` | Cada uno de los 11 tipos de A se clasifica con confianza; tablas antes que texto; del xlsx salen N2, P_prom, h_despues y huella |
| `generator/` | `test_generator.py` | Los 7 casos se generan; marca sintética en cada página; ground truth coherente con el modelo (AETOTAL recalculado desde `motores` coincide con `aetotal_esperado`) |
| `engine/motor.py`, `engine/informe.py`, `engine/cli.py`, `evaluar_casos.py` | `test_engine_e2e.py` | 7/7 veredictos; A y G = 305.829; E y F = ground truth del ADR-002; informe markdown y JSON con reglas, evidencias y traza; tiempos razonables (referencia Engine 0.1: ≈ 1 s por caso sin OCR, ≈ 12 s en G); tests con OCR marcados `@pytest.mark.ocr` |
| Propiedades transversales | `test_metamorficas.py` | Las seis de §6.1 sobre A–G |
| Regla de dependencias | `test_modo_degradado.py` | Con `agentes/` y `salida/` ausentes o vacíos, `engine/` produce veredicto; `engine/` no importa de `agentes/`, `salida/`, `generator/` ni `tests/` |
| `engine/estados.py`, `engine/eventos/` (`S3`) | `test_estados.py`, `test_eventos.py` (`NUEVO`) | Metamórficas de ciclo (§6.3); replay bit a bit; inalterabilidad post-firma |
| `engine/compositor.py` (`S4`) | `test_compositor.py` (`NUEVO`) | Metamórficas de composición (§6.2) |
| `agentes/runtime/` (`S3`) | `test_runtime.py` (`NUEVO`) | Salida sin cita se descarta; salida con resultado calculado se rechaza; presupuesto agotado → escalado |

### 8.1 `evaluar_casos.py`: la matriz esperado/obtenido

Es la puerta de integración (`CLAUDE.md` §4) y se ejecuta en cada sesión. Recorre `expedientes/EXP001-*/`, ejecuta `engine.motor` sobre cada carpeta, lee el ground truth de `_resultados_esperados/` y escribe los informes en `informes/`. Salida mínima:

- Una fila por caso con las columnas de la tabla de §1 (esperado, obtenido, CAE, documentos, datos con evidencia, extracción, segundos).
- Comparación de `reglas_falladas_esperadas` con las obtenidas: cualquier diferencia, en un sentido u otro, cuenta como fallo del caso aunque el veredicto coincida.
- Comparación de AETOTAL exacto (`Decimal`), no solo del truncado.
- Línea final `N/7 veredictos correctos` y código de salida distinto de cero si N < 7 o si el caso A no da 305.829,6.

`evaluar_casos.py` no sustituye a `pytest`: es la vista humana de los casos end-to-end; los tests son la garantía módulo a módulo.

### 8.2 Qué se considera "hecho" en la Fase 0

La Fase 0 (`docs/06`) está terminada cuando, en un clon limpio y sin `poppler`/`tesseract`:

1. `python -m generator.generar` regenera los 7 casos y el ground truth sin diferencias respecto a lo commiteado (salvo las que un ADR explique).
2. `python -m pytest -q` está en verde, con los tests `@pytest.mark.ocr` saltados y documentados como tales.
3. `python evaluar_casos.py` da 7/7, caso A en 305.829,6 kWh/año, E y F en el ground truth del ADR-002.
4. `docs/03` y `docs/04` tienen todas las marcas `F0` de los módulos reconstruidos pasadas a `EXISTE` o `PARCIAL`, con la razón de cada `PARCIAL`.
5. `docs/decisiones/ADR-002-reconstruccion-engine-0.1.md` existe con los parámetros de M2 y M3, los totales de E y F, la lista de variables de extracción y cualquier desviación respecto a este documento.

Con OCR instalado se ejecuta además la suite completa (G con escaneo y fotos) antes de cerrar la fase.

El número de tests no es un objetivo: el Engine 0.1 tenía 61 y la reconstrucción tendrá los que exija esta tabla, sean 55 u 80 (`CLAUDE.md` §7). Lo que se mide es que cada fila esté cubierta.

---

## 9. Fuentes

- `docs/historico/README_sprint1-2_engine-0.1.md` — matriz de casos, resultados del Engine 0.1 (última ejecución), decisiones de diseño, trampas deliberadas, límites conocidos.
- `docs/historico/07-backend-y-motor-de-reglas_v1.0.md` §6.4–6.6 y §10 — fases, tres resultados de regla, consolidación de evidencias, cinco fuentes de verdad, metamórficas mínimas, métricas por agente.
- `docs/historico/11-backend-funcionalidades-y-motor-de-reglas_v1.0.md` §6 — metamórficas de composición y de ciclo, batería INT-xx, métrica de producto.
- `spec/IND240_v1.1.yaml` — variables, fuentes, fórmula, 26 reglas, severidades, INT-01..07.
- `docs/00-instrucciones-de-entrada.md` §1 y §7.5 — la métrica que importa; banco de pruebas como juez; dos métricas por agente.
- `docs/01-estructura-del-repositorio.md` §3.4–3.6 — generator, expedientes, tests; nota sobre E y F.
- `docs/03-arquitectura-backend.md`, `docs/04-motor-de-reglas-y-specs.md`, `docs/06-plan-de-construccion.md` — arquitectura, reglas y plan que este documento evalúa.
- Ficha IND240 V1.1 (catálogo MITECO); Reglamento (UE) 2019/1781, anexo I, cuadro 6; Orden TED/815/2023; RD 36/2023.

---

*Mantener vivo: cambia en la misma sesión en que cambian los casos, el ground truth (con ADR) o la lista de tests. Cuando el Engine reconstruido pase la Fase 0, la nota de cabecera se sustituye por la fecha y el commit de la ejecución que la cumplió.*
