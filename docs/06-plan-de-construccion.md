# CAE Engine — Plan de construcción

**Versión 1.0 · 18/09/2026 · Proyecto CAE (Billy)**

Este documento dice **qué se construye, en qué orden, quién lo hace y cuándo está hecho**. Es el que el orquestador de Claude Code lee al empezar cada sesión para elegir el siguiente entregable, y el que actualiza al cerrarla. Cada línea tiene un "hecho cuando" verificable; si no se puede verificar, no es un entregable, es una intención.

Criterio de ordenación: primero lo que no depende de nadie externo y desbloquea al resto; lo que depende del diccionario de API, del delegado partner o de una decisión de Billy se engancha cuando llegue, sin bloquear lo demás.

**Estado de cada línea**: `PENDIENTE` · `EN CURSO` · `HECHO (fecha, commit)` · `BLOQUEADO (por qué)`. Lo actualiza el orquestador en la misma sesión.

---

## 0. Situación de partida (18/09/2026)

- El Engine 0.1 (Sprints 1 y 2) se construyó en otro entorno y **no está en este repositorio**. Lo que hay: `docs/`, `spec/IND240_v1.1.yaml`, `spec/propuestas/`, `.claude/`, `.github/`.
- Los resultados de aquel Engine (7/7 veredictos, caso A = 305.829,6 kWh/año, 58/58 variables con evidencia) son los **criterios de aceptación** de la Fase 0, no el estado actual (`docs/05`).
- Fuera del código hay tres dependencias externas abiertas: diccionario de la API oficial (previsto sep-2026, no recibido), delegado partner con certificado y capacidad, y respuesta del gestor de la plataforma sobre el perfil Modificación.

---

## 1. Fase 0 — Reconstrucción del Engine 0.1

Objetivo: volver a tener, en este repositorio y con la estructura de `docs/01`, un motor que lleve la carpeta de documentos de una actuación IND240 al informe de prevalidación, con las 26 reglas, el cálculo determinista y el banco de 7 casos. **Sin agentes LLM, sin salida a plataforma**: eso es Sprint 3.

Diferencias deliberadas respecto al Engine 0.1 original (decisiones de la consolidación, `docs/decisiones/ADR-001` §2): la unidad de trabajo se llama `Actuacion` desde el principio; el SHA-256 se calcula para **todo** fichero en ingesta; `logica` del YAML es ejecutable por un parser de lista blanca; el Rules Engine devuelve tres resultados; la asignación de reglas a fases es la de `docs/04` §5.

Orden de construcción. Cada paso es un commit `F0.n: …`. Los pasos 1–4 no necesitan documentos; el 5 crea los documentos que necesitan del 6 en adelante.

| # | Entregable | Ficheros (`docs/01`) | Hecho cuando… | Agente | Estado |
|---|---|---|---|---|---|
| F0.0 | Esqueleto del repositorio, `pyproject.toml`, `.gitignore`, `README.md` mínimo, `ruff` configurado, `tests/conftest.py` vacío | Todo `docs/01` §1 | `python -m pytest -q` arranca (0 tests) y `ruff check .` pasa; `docs/01` coincide con el árbol real | orquestador | PENDIENTE |
| F0.1 | Parser de expresiones de lista blanca para `logica` y `formula` | `engine/expresiones.py`, `tests/test_expresiones.py` | Evalúa todas las construcciones que aparecen en las 26 reglas y la fórmula de IND240 (`docs/04` §6); una función desconocida lanza error de carga; no hay `eval` en el módulo (test lo comprueba leyendo el fuente); operadores lógicos trivaluados con `NO_EVALUABLE` | motor-nucleo | PENDIENTE |
| F0.2 | Tablas de referencia con vigencia | `data/README.md`, `data/reg_2019_1781_cuadro6.csv`, `engine/tablas.py`, `tests/test_tablas.py` | 110 kW → 5,55 kW; fila inexistente devuelve `INT-02` en lugar de un valor; toda fila lleva marca `verificado` según `data/README.md` | spec-fichas | PENDIENTE |
| F0.3 | Calculation Engine | `engine/calculo.py`, `tests/test_calculo.py` | Caso A en memoria (110 kW, 1.485→1.188 rpm, 6.000 h) da exactamente `305829.6` con `Decimal`; `AETOTAL_cae = 305829`; `h = min(h_antes, h_despues)`; FIS-01/FIS-02 retiran el resultado; traza con cada paso; `p` solo desde tabla | motor-nucleo | PENDIENTE |
| F0.4 | Spec Registry | `engine/spec_registry.py`, `tests/test_spec_registry.py` | Carga `spec/IND240_v1.1.yaml` y rechaza cualquier fichero de `spec/propuestas/`; valida campos y valores por defecto de `docs/04` §3; comprueba al cargar la garantía NO_EVALUABLE → SUBSANABLE (`docs/04` §2); calcula `hash_reglas` | spec-fichas | PENDIENTE |
| F0.5 | Generator y los 7 casos | `generator/**`, `expedientes/EXP001-*/`, `expedientes/_resultados_esperados/`, `tests/test_generator.py` | `python -m generator.generar` produce 7 carpetas con los documentos de `docs/05` §4, todos con la marca sintética; el ground truth sale del mismo modelo de datos; E y F con parámetros fijados y AETOTAL recalculado y registrado en `ADR-002`; G contiene PDF combinado, escaneo girado, fotos y xlsx renombrado | generador-casos | PENDIENTE |
| F0.6 | Ingesta y clasificación | `engine/ingesta.py`, `engine/clasificacion.py`, `tests/test_ingesta.py` | SHA-256 de todo fichero antes de transformar; separación de PDF combinados conservando hash original y de partes; OCR con `tesseract` si está instalado (tests OCR marcados y saltados si no); clasificación léxica con confianza; el registro se vincula por hash y nº de serie, no por nombre | ingesta-extraccion | PENDIENTE |
| F0.7 | Extracción por reglas y lector de registro | `engine/extraccion.py` (interfaz `Extractor` + implementación por reglas), `engine/registro_xlsx.py` | Tablas del PDF antes que texto plano; cada evidencia con documento, página, texto literal, método y confianza; OCR entra con 0,75; el registro xlsx produce N2, P_prom y h_despues según los métodos de la spec (INT-03, INT-04) | ingesta-extraccion | PENDIENTE |
| F0.8 | Evidence Store y consolidación | `engine/evidencias.py`, `tests/test_evidencias.py` | Tres capas por dato; normalización `exacto`/`normalizado`; tolerancias de la spec; conflicto entre fuentes fiables → `valor_consumido = null` y ambas evidencias; OCR discrepante no bloquea; declarado ≠ demostrado marcado | motor-nucleo | PENDIENTE |
| F0.9 | Rules Engine | `engine/reglas.py`, `tests/test_reglas.py` | Las 26 reglas evaluadas desde su `logica`; fases de `docs/04` §5; tres resultados; veredicto por prioridad; por cada regla un test que cumple y uno que falla; caso B es `SUBSANABLE` y no `BLOQUEADO` | motor-nucleo | PENDIENTE |
| F0.10 | Motor, informe y CLI | `engine/motor.py`, `engine/informe.py`, `engine/cli.py` | `python -m engine.cli expedientes/EXP001-A_completo --md --json` produce informe con veredicto, ahorro, evidencias, reglas, interpretaciones aplicadas y carencias; el orden es ámbito y consistencia → cálculo → resto | motor-nucleo | PENDIENTE |
| F0.11 | Evaluación y tests end-to-end | `evaluar_casos.py`, `tests/test_engine_e2e.py`, `tests/test_metamorficas.py`, `tests/test_modo_degradado.py` | 7/7 veredictos; A, E, F, G con el AETOTAL del ground truth; las 6 metamórficas mínimas de `docs/05` §6 pasan; con `agentes/` y `salida/` ausentes el motor funciona | qa-evaluacion | PENDIENTE |
| F0.12 | Cierre de fase | `docs/03`, `docs/04`, `docs/06`, `docs/decisiones/ADR-002-reconstruccion-engine-0.1.md`, `README.md` | Marcas `F0` → `EXISTE`/`PARCIAL` actualizadas; ADR-002 con parámetros de E y F, ground truth, número de tests y cualquier desviación respecto a `docs/05`; `README.md` con instalación y ejecución en Windows y Linux | orquestador + revisor-normativo | PENDIENTE |

**Hecho cuando (fase completa)**: F0.0–F0.12 en `HECHO`; `pytest -q` en verde; `evaluar_casos.py` 7/7; caso A = 305.829,6; `ruff` limpio; `docs/01` coincide con el árbol; `ADR-002` escrito.

**Lo que la Fase 0 no hace, por diseño**: modelo canónico completo (`engine/modelo/`), log de eventos, máquina de estados, cabecera, salida, agentes LLM. El `motor.py` de la Fase 0 es lineal y síncrono; su interfaz pública se conserva en Sprint 3.

---

## 2. Sprint 3 — Integración con la plataforma oficial

Decidido el 17/09/2026 y reordenado el 18/09/2026 tras la confrontación con la plataforma (`docs/02`). Los pasos S3.1–S3.6 no dependen de nadie externo; S3.7 se engancha cuando existan diccionario y acceso.

| # | Entregable | Módulos | Hecho cuando… | Depende de | Estado |
|---|---|---|---|---|---|
| S3.1 | Modelo canónico `Actuacion` + `GrupoActuaciones` + `Expediente` + `Verificador` + `Tenant` con JSON Schema; log de eventos; máquina de estados con cuatro niveles, fases 2–4 provisionales y `DESISTIDO` | `engine/modelo/`, `engine/eventos/`, `engine/estados.py` | Los 7 casos producen `Actuacion` válida contra el esquema; el replay del log reproduce veredicto y ahorro bit a bit; ningún evento de actor `agente` o `motor` mueve `ENTREGADA` → `EN_PLATAFORMA`; un requerimiento GA/CN simulado marca todas las actuaciones del expediente | Fase 0 | PENDIENTE |
| S3.2 | Spec transversal de cabecera + reglas `R-CAB-*` + extracción de las variables de cabecera con fuente documental | `spec/cabecera_v1.yaml` (movida desde `propuestas/` tras aprobación), `engine/spec_registry.py`, `engine/extraccion.py` | El caso A rellena todos los campos de cabecera con fuente documental y deja los sin fuente como `declarado` o `NO DOCUMENTADO`; IND240 hereda R-TMP-02/03 de la cabecera sin duplicarlas | **Aprobación de Billy** de `cabecera_v1.yaml` y del diff v1.2 | BLOQUEADO (decisión) |
| S3.3 | Manifiesto interno e integridad total | `salida/constructor/`, `tests/` | Manifiesto del caso A verificable; alterar un byte de cualquier adjunto lo detecta; `hash_cabecera` y `hash_detalle` presentes | S3.1 | PENDIENTE |
| S3.4 | Puerto de salida + adaptador handoff + simulador; `transporte/` separado; huecos referenciados | `salida/puerto.py`, `salida/handoff/`, `salida/simulador/`, `mapping/IND240.handoff.yaml`, `mapping/manifiesto.handoff.yaml` | Simulador acepta el paquete del caso A y rechaza uno con hash alterado; la "firma" es un paso humano simulado que cambia `COMPLETA` → `ENVIADA_A_VERIFICACION` solo con `FirmaRegistrada` de actor humano; ningún campo inventado de la API (cada hueco cita `docs/HUECOS.md`) | S3.1, S3.3 | PENDIENTE |
| S3.5 | P9 contra el simulador + A9 sobre requerimientos sintéticos de los tres orígenes + P7 con `origen` | `agentes/runtime/`, `agentes/redactor/`, `engine/estados.py` | Un `PDTE_RECTIFICACION_VER` simulado reabre subsanación con la regla correcta; un requerimiento de GA simulado bloquea el expediente completo; toda interpretación de A9 exige confirmación humana antes de reabrir (R-REQ-02) | S3.4 | PENDIENTE |
| S3.6 | Agent Runtime + extractor LLM (A2) con doble extracción, detrás de la interfaz `Extractor` | `agentes/runtime/`, `agentes/lector/`, `agentes/prompts/` | Runtime rechaza salidas sin cita y salidas con resultado calculado (tests); evaluado en conjunto reservado de la fábrica de casos; tasa de desacuerdo registrada; modo degradado comprobado apagando el LLM | **Proveedor LLM y condiciones de datos (Billy)** | BLOQUEADO (decisión) |
| S3.7 | Conector API oficial + modo sombra + batería de casos para inferir criterios oficiales (INT-01..05) | `salida/api_oficial/`, `salida/transporte/`, `mapping/IND240.api.yaml` | Un envío en sandbox; primera `DiscrepanciaCalculoPlataforma` registrada o ausencia de discrepancia en los 7 casos; R-XCK-01..03 evaluadas | Diccionario de API (API-01, API-02, API-08) **y** delegado partner o perfil Modificación (API-09) | BLOQUEADO (externo) |

**Hecho cuando (sprint completo)**: S3.1, S3.3, S3.4, S3.5 en `HECHO` con tests; S3.2, S3.6, S3.7 en `HECHO` o `BLOQUEADO` con la alternativa preparada (spec en `propuestas/`, runtime con proveedor configurable, conector con huecos enumerados).

---

## 3. Sprint 4 — Composición y segunda ficha

| # | Entregable | Hecho cuando… | Depende de | Estado |
|---|---|---|---|---|
| S4.1 | **Expediente Builder**: reglas `R-GRP-*` y `R-EXP-*` desde `spec/composicion_v1.yaml`; propuesta de lotes válidos; avisos de huérfanas y contagio | Sobre 20 actuaciones sintéticas con distintos CCAA/año/verificador propone los lotes correctos y ningún lote mezcla `SUBSANABLE` con `PREVALIDADO`; metamórficas de composición pasan | Decisión de Billy (Expediente Builder en S4) y aprobación de `composicion_v1.yaml` | BLOQUEADO (decisión) |
| S4.2 | A5 (subsanaciones) y A7 (informes por destinatario) sobre el campo `subsanacion` de cada regla | Petición al cliente generada para el caso B sin inventar documentos que la spec no pide; informe para cliente, instalador y tenant | S3.6 | PENDIENTE |
| S4.3 | Segunda ficha con **cero cambios en `engine/`** | Checklist de `docs/04` §15 completo; si `engine/` cambia, se registra como defecto del marco en ADR | Decisión de Billy: vecina (IND170/IND280) o estresante (frío) — `docs/09` §6 | BLOQUEADO (decisión) |
| S4.4 | Consola de revisión centrada en lo previo a la firma (S4) | Cola de escalados, conflictos, correcciones y tareas pendientes consumidas del simulador | S3.5 | PENDIENTE |
| S4.5 | Fábrica de casos: mismas variables, plantillas y calidades de escaneo distintas; conjunto reservado | El extractor por reglas y el LLM se evalúan sobre casos nunca usados para ajustar | F0.5 | PENDIENTE |

---

## 4. Roadmap (decisiones de Billy)

Módulo de actuaciones singulares y Consulta Voluntaria Previa (fase II de la plataforma, ene–mar 2027) · estados de CAE (`vigente`, `expirado`, `liquidado`) solo si entra CAE Supply · coeficientes de corrección (art. 18 bis) como tabla con vigencia cuando existan · A6 vigía normativo con diff automático sobre `spec/propuestas/` · memoria entre expedientes (IND190–220) si entra la familia de frío.

---

## 5. Fuera del código (en paralelo, dueño Billy)

| # | Acción | Estado a 18/09/2026 | Desbloquea |
|---|---|---|---|
| X.1 | Consulta a `consultas-plataforma@registrocae.es`: modelos de intercambio, diccionario de API, sandbox, perfil Modificación para terceros | Decidido enviar (18/09) | S3.7, API-01..09 |
| X.2 | Delegado partner con certificado **y capacidad de delegación disponible** | Búsqueda en curso; barrido de la lista MITECO; sin candidato elegido | S3.7, modo sombra |
| X.3 | Revisar contrato laboral (exclusividad, PI, conflicto de interés) antes de contactos comerciales | Pendiente | `docs/08` |
| X.4 | Expediente industrial real anonimizado | Pendiente (objetivo de los primeros contactos) | Medir precisión fuera del laboratorio |
| X.5 | Sesión con verificador para INT-01/03/04/05 | Pendiente | Cierre de INT-xx; nueva `version_spec` |
| X.6 | Aprobar o rechazar `spec/propuestas/` (cabecera_v1, diff v1.2, composicion_v1) | Pendiente | S3.2, S4.1 |
| X.7 | Elegir proveedor LLM y condiciones de datos | Pendiente | S3.6 |
| X.8 | Seguimiento de la tramitación del proyecto de RD 36/2023 y de las órdenes de desarrollo | Vigilancia programada | Cambios de spec por revisión humana |

---

## 6. Riesgos del plan

| Riesgo | Efecto | Mitigación |
|---|---|---|
| La reconstrucción no reproduce exactamente los resultados del Engine 0.1 (E, F, número de tests) | Confusión sobre qué es regresión y qué es cambio | El caso A es reproducible exactamente; E y F se fijan en `ADR-002`; el número de tests no es criterio, la cobertura de `docs/05` §8 sí |
| El diccionario de API no llega | S3.7 se retrasa; se pierde la ventana oct–nov | S3.1–S3.6 no dependen de él; el simulador implementa solo lo conocido; `docs/HUECOS.md` enumerado |
| No hay delegado partner antes de octubre | Sin sandbox ni modo sombra | Vía perfil Modificación (si el gestor responde afirmativamente) y alegación DT 2ª; mientras, handoff y simulador |
| Los estados provisionales de fases 2–4 no coinciden con los oficiales | Retrabajo en la máquina de estados | Se modelan como tabla de mapeo en YAML, no como código |
| Cabecera: campos sin fuente documental (costes operativos, tipología, subasta) | Payload incompleto o con datos declarados | Se marcan `declarado` y quedan recogidos por `R-CAB-*` como subsanables o avisos; semántica `NO DOCUMENTADO` no se inventa |
| Extractor por reglas ajustado a documentos propios | Falsa sensación de precisión | Fábrica de casos con conjunto reservado (S4.5); expediente real anonimizado (X.4); doble extracción (S3.6) |
| Decisiones de Billy pendientes bloquean pasos | Sprint parcial | Cada paso bloqueado tiene la alternativa preparada (propuesta en `spec/propuestas/`, proveedor configurable, huecos enumerados); el orquestador lista las decisiones al cerrar cada sesión |

---

## 7. Bitácora de sesiones

Se rellena con hechos. Una línea por sesión de Claude Code: fecha, pasos tocados, estado resultante, decisiones que quedan para Billy.

| Fecha | Pasos | Resultado | Para Billy |
|---|---|---|---|
| 18/09/2026 | Consolidación documental (fuera de Claude Code) | Repositorio listo para `/bootstrap` | Confirmar las decisiones de consolidación de `ADR-001` §2 |

---

*Mantener vivo: el orquestador actualiza el estado de cada línea en la misma sesión en que cambia, y añade una línea a la bitácora al cerrar. Un "hecho cuando" que no se puede verificar con un comando o un test se reescribe hasta que se pueda.*
