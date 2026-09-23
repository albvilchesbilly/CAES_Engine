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
| F0.0 | Esqueleto del repositorio, `pyproject.toml`, `.gitignore`, `README.md` mínimo, `ruff` configurado, `tests/conftest.py` vacío | Todo `docs/01` §1 | `python -m pytest -q` arranca (0 tests) y `ruff check .` pasa; `docs/01` coincide con el árbol real | orquestador | HECHO (18/09/2026, 8ebb723) |
| F0.1 | Parser de expresiones de lista blanca para `logica` y `formula` | `engine/expresiones.py`, `tests/test_expresiones.py` | Evalúa todas las construcciones que aparecen en las 26 reglas y la fórmula de IND240 (`docs/04` §6); una función desconocida lanza error de carga; no hay `eval` en el módulo (test lo comprueba leyendo el fuente); operadores lógicos trivaluados con `NO_EVALUABLE` | motor-nucleo | HECHO (18/09/2026, 4f26284 + 4d715d5 tras QA) |
| F0.2 | Tablas de referencia con vigencia | `data/README.md`, `data/reg_2019_1781_cuadro6.csv`, `engine/tablas.py`, `tests/test_tablas.py` | 110 kW → 5,55 kW; fila inexistente devuelve `INT-02` en lugar de un valor; toda fila lleva marca `verificado` según `data/README.md` | spec-fichas | HECHO (18/09/2026, 79956a0 + 62df530 tras QA; 38 filas pendientes de verificación de Billy) |
| F0.3 | Calculation Engine | `engine/calculo.py`, `tests/test_calculo.py` | Caso A en memoria (110 kW, 1.485→1.188 rpm, 6.000 h) da exactamente `305829.6` con `Decimal`; `AETOTAL_cae = 305829`; `h = min(h_antes, h_despues)`; FIS-01/FIS-02 retiran el resultado; traza con cada paso; `p` solo desde tabla | motor-nucleo | HECHO (18/09/2026, 0c97217 + 78c9e58 tras QA) |
| F0.4 | Spec Registry | `engine/spec_registry.py`, `tests/test_spec_registry.py` | Carga `spec/IND240_v1.1.yaml` y rechaza cualquier fichero de `spec/propuestas/`; valida campos y valores por defecto de `docs/04` §3; comprueba al cargar la garantía NO_EVALUABLE → SUBSANABLE (`docs/04` §2); calcula `hash_reglas` | spec-fichas | HECHO (18/09/2026, 7700ba2 + 5f70caf tras QA) |
| F0.5 | Generator y los 7 casos | `generator/**`, `expedientes/EXP001-*/`, `expedientes/_resultados_esperados/`, `tests/test_generator.py` | `python -m generator.generar` produce 7 carpetas con los documentos de `docs/05` §4, todos con la marca sintética; el ground truth sale del mismo modelo de datos; E y F con parámetros fijados y AETOTAL recalculado y registrado en `ADR-002`; G contiene PDF combinado, escaneo girado, fotos y xlsx renombrado | generador-casos | HECHO (18/09/2026, cff6411) |
| F0.6 | Ingesta y clasificación | `engine/ingesta.py`, `engine/clasificacion.py`, `tests/test_ingesta.py` | SHA-256 de todo fichero antes de transformar; separación de PDF combinados conservando hash original y de partes; OCR con `tesseract` si está instalado (tests OCR marcados y saltados si no); clasificación léxica con confianza; el registro se vincula por hash y nº de serie, no por nombre | ingesta-extraccion | HECHO (18/09/2026, 225c1e1; revisión QA pendiente) |
| F0.7 | Extracción por reglas y lector de registro | `engine/extraccion.py` (interfaz `Extractor` + implementación por reglas), `engine/registro_xlsx.py` | Tablas del PDF antes que texto plano; cada evidencia con documento, página, texto literal, método y confianza; OCR entra con 0,75; el registro xlsx produce N2, P_prom y h_despues según los métodos de la spec (INT-03, INT-04) | ingesta-extraccion | HECHO (18/09/2026, 225c1e1; 135/135 variables con evidencia; revisión QA pendiente) |
| F0.8 | Evidence Store y consolidación | `engine/evidencias.py`, `tests/test_evidencias.py` | Tres capas por dato; normalización `exacto`/`normalizado`; tolerancias de la spec; conflicto entre fuentes fiables → `valor_consumido = null` y ambas evidencias; OCR discrepante no bloquea; declarado ≠ demostrado marcado | motor-nucleo | HECHO (18/09/2026, f0e0c7c; revisión QA pendiente) |
| F0.9 | Rules Engine | `engine/reglas.py`, `tests/test_reglas.py` | Las 26 reglas evaluadas desde su `logica`; fases de `docs/04` §5; tres resultados; veredicto por prioridad; por cada regla un test que cumple y uno que falla; caso B es `SUBSANABLE` y no `BLOQUEADO` | motor-nucleo | HECHO (18/09/2026, bf01a52; revisión QA pendiente) |
| F0.10 | Motor, informe y CLI | `engine/motor.py`, `engine/informe.py`, `engine/cli.py` | `python -m engine.cli expedientes/EXP001-A_completo --md --json` produce informe con veredicto, ahorro, evidencias, reglas, interpretaciones aplicadas y carencias; el orden es ámbito y consistencia → cálculo → resto | motor-nucleo | HECHO (18/09/2026, 84c90a4; 7/7 casos con veredicto y AETOTAL del ground truth) |
| F0.11 | Evaluación y tests end-to-end | `evaluar_casos.py`, `tests/test_engine_e2e.py`, `tests/test_metamorficas.py`, `tests/test_modo_degradado.py` | 7/7 veredictos; A, E, F, G con el AETOTAL del ground truth; las 6 metamórficas mínimas de `docs/05` §6 pasan; con `agentes/` y `salida/` ausentes el motor funciona | qa-evaluacion | HECHO (19/09/2026, 6273434) |
| F0.12 | Cierre de fase | `docs/03`, `docs/04`, `docs/06`, `docs/decisiones/ADR-002-reconstruccion-engine-0.1.md`, `README.md` | Marcas `F0` → `EXISTE`/`PARCIAL` actualizadas; ADR-002 con parámetros de E y F, ground truth, número de tests y cualquier desviación respecto a `docs/05`; `README.md` con instalación y ejecución en Windows y Linux | orquestador + revisor-normativo | HECHO (19/09/2026; revisión normativa en `ADR-003`) |

**Hecho cuando (fase completa)**: F0.0–F0.12 en `HECHO`; `pytest -q` en verde; `evaluar_casos.py` 7/7; caso A = 305.829,6; `ruff` limpio; `docs/01` coincide con el árbol; `ADR-002` escrito.

**FASE 0 CERRADA el 19/09/2026.** 999 tests en verde (976 y 23 saltados sin OCR), `evaluar_casos.py` 7/7 con el caso A en 305.829,6 kWh/año exactos, `ruff` limpio, ground truth de E y F fijado en `ADR-002` §4 y desviaciones respecto a `docs/05` en §5. La revisión normativa está en `ADR-003` (22 hallazgos, INT-11..INT-15 propuestos, ninguno aplicado).

**Lo que la Fase 0 no hace, por diseño**: modelo canónico completo (`engine/modelo/`), log de eventos, máquina de estados, cabecera, salida, agentes LLM. El `motor.py` de la Fase 0 es lineal y síncrono; su interfaz pública se conserva en Sprint 3.

---

## 2. Sprint 3 — Integración con la plataforma oficial

Decidido el 17/09/2026 y reordenado el 18/09/2026 tras la confrontación con la plataforma (`docs/02`). Los pasos S3.1–S3.6 no dependen de nadie externo; S3.7 se engancha cuando existan diccionario y acceso.

| # | Entregable | Módulos | Hecho cuando… | Depende de | Estado |
|---|---|---|---|---|---|
| S3.1 | Modelo canónico `Actuacion` + `GrupoActuaciones` + `Expediente` + `Verificador` + `Tenant` con JSON Schema; log de eventos; máquina de estados con cuatro niveles, fases 2–4 provisionales y `DESISTIDO` | `engine/modelo/`, `engine/eventos/`, `engine/estados.py` | Los 7 casos producen `Actuacion` válida contra el esquema; el replay del log reproduce veredicto y ahorro bit a bit; ningún evento de actor `agente` o `motor` mueve `ENTREGADA` → `EN_PLATAFORMA`; un requerimiento GA/CN simulado marca todas las actuaciones del expediente | Fase 0 | HECHO (19/09/2026, ea89b6a; `ADR-004`) |
| S3.1b | Capacidades y perfiles en el modelo y en el log: entidades `Usuario`, `Perfil`, `Capacidad`, `AsignacionPerfil`, `PoliticaTenant`; `actor.rol` obligatorio en actor humano; los ~20 eventos nuevos de `ADR-006`; tests de autorización | `engine/modelo/`, `engine/eventos/`, `tests/test_permisos_*.py` | Un `ADM-OPS` no puede generar `SpecActivada` ni un `ADM-MOD` un `TenantAlta`; ningún evento de administración carece de `actor.rol`; CAP-10 y CAP-22 son los únicos disparadores humanos de sus transiciones | **A8 APROBADA por Billy el 19/09/2026** | **HECHO** (19/09/2026) |
| S3.2 | Spec transversal de cabecera + reglas `R-CAB-*` + extracción de las variables de cabecera con fuente documental | `spec/cabecera_v1.yaml` (movida desde `propuestas/` tras aprobación), `engine/spec_registry.py`, `engine/extraccion.py` | El caso A rellena todos los campos de cabecera con fuente documental y deja los sin fuente como `declarado` o `NO DOCUMENTADO`; IND240 hereda R-TMP-02/03 de la cabecera sin duplicarlas | **Aprobación de Billy** de `cabecera_v1.yaml` y del diff v1.2 | BLOQUEADO (decisión) |
| S3.3 | Manifiesto interno e integridad total | `salida/constructor/`, `tests/` | Manifiesto del caso A verificable; alterar un byte de cualquier adjunto lo detecta; `hash_cabecera` y `hash_detalle` presentes | S3.1 | HECHO (19/09/2026; `ADR-008`) |
| S3.4 | Puerto de salida + adaptador handoff + simulador; `transporte/` separado; huecos referenciados | `salida/puerto.py`, `salida/handoff/`, `salida/simulador/`, `mapping/IND240.handoff.yaml`, `mapping/manifiesto.handoff.yaml` | Simulador acepta el paquete del caso A y rechaza uno con hash alterado; la "firma" es un paso humano simulado que cambia `COMPLETA` → `ENVIADA_A_VERIFICACION` solo con `FirmaRegistrada` de actor humano; ningún campo inventado de la API (cada hueco cita `docs/HUECOS.md`) | S3.1, S3.3 | **HECHO** (19/09/2026, `ADR-009`) |
| S3.5 | P9 contra el simulador + A9 sobre requerimientos sintéticos de los tres orígenes + P7 con `origen`. **A9 se construye como interfaz `Interprete` con implementación determinista** (`ADR-010` §1): la variante con LLM entra en S3.6 detrás de la misma interfaz, sin tocar nada más | `engine/seguimiento.py`, `engine/requerimientos.py`, `salida/seguimiento.py`, `generator/` (`agentes/redactor/` en S3.6) | Un `PDTE_RECTIFICACION_VER` simulado reabre subsanación con la regla correcta; un requerimiento de GA simulado bloquea el expediente completo; toda interpretación de A9 exige confirmación humana antes de reabrir (R-REQ-02) | S3.4 | **HECHO** (19/09/2026, `ADR-010`) · A9 con LLM en S3.6 |
| S3.6 | Agent Runtime + extractor LLM (A2) con doble extracción, detrás de la interfaz `Extractor` | `agentes/runtime/`, `agentes/lector/`, `agentes/prompts/` | Runtime rechaza salidas sin cita y salidas con resultado calculado (tests); evaluado en conjunto reservado de la fábrica de casos; tasa de desacuerdo registrada; modo degradado comprobado apagando el LLM | **Proveedor LLM y condiciones de datos (Billy)** | BLOQUEADO (decisión) |
| S3.8 | **Recálculo tras corrección humana**: la corrección entra como evidencia con sus tres capas y el motor recalcula (`ADR-013`). Cierra `GAP-REV-01`, que hoy deja a medias la frase que justifica `R-UI-02` | `engine/correcciones.py`, `engine/evidencias.py`, `engine/motor.py` | Los 7 casos sin correcciones dan lo mismo (caso A en 305.829,6); el caso C con la corrección que elige 110 kW deja de estar `BLOQUEADO` y da ahorro; la corrección sale en el informe con su cita; **el replay reproduce el veredicto corregido solo con el log** | S3.1 (HECHO), FR0 (HECHO) | **HECHO** (20/09/2026, `ADR-013`) |
| S3.7 | Conector API oficial + modo sombra + batería de casos para inferir criterios oficiales (INT-01..05) | `salida/api_oficial/`, `salida/transporte/`, `mapping/IND240.api.yaml` | Un envío en sandbox; primera `DiscrepanciaCalculoPlataforma` registrada o ausencia de discrepancia en los 7 casos; R-XCK-01..03 evaluadas | Diccionario de API (API-01, API-02, API-08) **y** delegado partner o perfil Modificación (API-09) | BLOQUEADO (externo) |

**Hecho cuando (sprint completo)**: S3.1, S3.3, S3.4, S3.5 y S3.8 en `HECHO` con tests; S3.2, S3.6, S3.7 en `HECHO` o `BLOQUEADO` con la alternativa preparada (spec en `propuestas/`, runtime con proveedor configurable, conector con huecos enumerados).

---

## 3. Sprint 4 — Composición y segunda ficha

| # | Entregable | Hecho cuando… | Depende de | Estado |
|---|---|---|---|---|
| S4.1 | **Expediente Builder**: reglas `R-GRP-*` y `R-EXP-*` desde `spec/composicion_v1.yaml`; propuesta de lotes válidos; avisos de huérfanas y contagio | Sobre 20 actuaciones sintéticas con distintos CCAA/año/verificador propone los lotes correctos y ningún lote mezcla `SUBSANABLE` con `PREVALIDADO`; metamórficas de composición pasan | Decisión de Billy (Expediente Builder en S4) y aprobación de `composicion_v1.yaml` | BLOQUEADO (decisión) |
| S4.2 | A5 (subsanaciones) y A7 (informes por destinatario) sobre el campo `subsanacion` de cada regla | Petición al cliente generada para el caso B sin inventar documentos que la spec no pide; informe para cliente, instalador y tenant | S3.6 | PENDIENTE |
| S4.3 | Segunda ficha con **cero cambios en `engine/`** | Checklist de `docs/04` §15 completo; si `engine/` cambia, se registra como defecto del marco en ADR | Decisión de Billy: vecina (IND170/IND280) o estresante (frío) — `docs/09` §6 | BLOQUEADO (decisión) |
| S4.4 | Consola de revisión centrada en lo previo a la firma → **la absorbe `FR1`** (`ADR-050`): es la cola y la vista de revisión del perfil `T-REV`. Su "hecho cuando" se mantiene literal como criterio de `FR1` | Cola de escalados, conflictos, correcciones y tareas pendientes consumidas del simulador | S3.5 | MOVIDO a `FR1` (§3 ter) |
| S4.5 | Fábrica de casos: mismas variables, plantillas y calidades de escaneo distintas; conjunto reservado | El extractor por reglas y el LLM se evalúan sobre casos nunca usados para ajustar | F0.5 | PENDIENTE |

---

## 3 bis. Perfiles, permisos y dashboards (ADR-005, ADR-006 y ADR-007, 19/09/2026)

Billy añadió tres decisiones que no estaban en este plan y que crean su propia línea de entregables: dos perfiles
de administración sin permisos solapados (`ADM-MOD`, propietario del modelo, y `ADM-OPS`, administrador de
operación), un catálogo de perfiles con matriz de capacidades, y dos dashboards (operativo y técnico) con cuatro
vistas. **El plan de construcción detallado vive en `ADR-007` §"Plan de construcción"**; aquí solo el resumen y
las dependencias, para que no haya dos planes.

| # | Entregable | Depende de | Estado |
|---|---|---|---|
| DB0 | Catálogo de métricas en YAML, JSON Schema, validador y vista técnica estática | Nada | PENDIENTE |
| DB1 | Proyecciones sobre el log y las tres vistas operativas estáticas, con filtro por capacidad y tenant | S3.1 (HECHO) y `ADR-005` | PENDIENTE |
| DB2 | Métricas de salida y seguimiento contra el simulador | S3.4, S3.5 | PENDIENTE |
| DB3 | Métricas del runtime de agentes | S3.6 (proveedor LLM, decisión de Billy) | BLOQUEADO (decisión) |
| DB4 | Métricas con la plataforma real | S3.7 (diccionario de API y acceso) | BLOQUEADO (externo) |
| DB5 | API de lectura y vistas en la interfaz elegida | Decisión de Billy sobre la interfaz | BLOQUEADO (decisión) |

Una métrica se define **una sola vez en configuración**, con el mismo criterio que las fichas: el catálogo es
YAML validado, no código. Una métrica sin fuente se muestra como `SIN DATO`, nunca como cero.

Los perfiles y la matriz de capacidades que estas vistas filtran están en `ADR-006`; su encaje en el modelo y en
el log es **S3.1b**, arriba, y depende de la decisión A8 de Billy. Las consecuencias ya integradas en la
documentación viva: `docs/03` §5.2 (entidades), §6.1 y §6.2 (`actor.rol` y eventos de administración), §7.3
(disparadores humanos), §12 (seguridad, acceso de soporte, monitorización) y §13 (F-24, F-25); `docs/01` §3.9 bis
(`metricas/`); `docs/00` §4 (glosario de perfiles).

---

## 3 ter. Front por perfil (`ADR-050`, 19/09/2026) — `PROPUESTA`

Billy añadió una cuarta decisión externa: **cómo es la interfaz de cada perfil**. Hasta ahora había 8 perfiles
(`ADR-005`), 51 capacidades y 4 vistas de dashboard (`ADR-006`, `ADR-007`), pero ninguna pantalla. `ADR-050`
lo cierra con **cuatro superficies que se adaptan a las capacidades del usuario**, no ocho aplicaciones.
**El plan detallado vive en `ADR-050`; aquí solo el resumen y las dependencias, para que no haya dos planes.**

**Billy aprobó C1 y C7 el 19/09/2026**: un solo stack web (React con TypeScript) y las cuatro superficies con
el orden `FR0` → `FR6`. Con eso `FR0` queda desbloqueado y el resto del plan depende solo de él. Siguen
abiertas C2 a C6 (`ADR-050` §Pendiente), ninguna de las cuales bloquea `FR0`.

| # | Entregable | Depende de | Estado |
|---|---|---|---|
| FR0 | Contrato de comandos y lecturas por capacidad en `api/`; sistema de diseño mínimo en `front/compartido/` | S3.1 (HECHO) · stack C1 (**APROBADO**) · A8 de `ADR-005` para persistir `actor.rol` | **HECHO** (19/09/2026, `ADR-011`) |
| FR1 | Workspace `T-REV`: cola y vista de revisión. **Absorbe `S4.4`** | FR0 (HECHO), S3.5 (HECHO), S3.8 (HECHO) | **HECHO** (23/09/2026, `ADR-014`): `FR1.a` (proyección y matriz), `FR1.b` (el lazo del recálculo) y `FR1.c` (las dos pantallas, `front/workspace/`, 109 tests). **"Hecho" significa lo que dice `ADR-014` §4**: las pantallas existen, cumplen sus criterios de aceptación y están verificadas contra el contrato con un transporte de pruebas; **no se abren en un navegador contra datos reales** hasta `FR-HTTP` |
| **FR-HTTP** | **Capa HTTP y sesión autenticada**: publicar `api/` por red | FR0 (HECHO) · decisiones de Billy: framework, sesiones, despliegue | **NUEVO** (23/09/2026, `ADR-014` §4). Hasta que exista, **ninguna pantalla se puede abrir en un navegador contra datos reales**: el sobre está diseñado en `front/compartido/api/transporte.ts` y nada lo publica. No es un hueco de `T-REV`: afecta a las cuatro superficies por igual |
| FR2 | Workspace `T-OPE`: bandeja, alta, subida y "qué te falta" | FR0 | PENDIENTE (espera FR0) |
| FR3 | Workspace `T-RES`: pendiente de mí, registro de firma, equipo, `O-FUN` | FR0, DB1 | PENDIENTE (espera FR0 y DB1) |
| FR4 | Portal externo (`EXT-INS`, `EXT-CLI`) | FR0 · A1 y A2 de `ADR-005` | BLOQUEADO (decisión) |
| FR5 | Consola `ADM-OPS` | FR0 · primer tenant real | BLOQUEADO (externo) |
| FR6 | Consola `ADM-MOD`, **en solo lectura** | FR0, DB0 | PENDIENTE (espera FR0 y DB0) |

Tres reglas del ADR que condicionan todo lo demás y que no se reabren en una pantalla:

1. **El contrato antes que las pantallas** (FR0 primero). Si se empieza por la interfaz, la lógica de negocio
   acaba dentro de ella y los endpoints se inventan. Es la misma razón por la que `mapping/` es declarativo.
2. **`R-UI-11`: el front no contiene lógica de negocio.** No calcula, no evalúa reglas y no decide
   transiciones. Es la regla de oro 1 ("la IA lee, el motor calcula") llevada a la interfaz.
3. **`R-UI-01`: ocultar un control no es autorización.** Cada comando valida capacidad y tenant **en el
   servidor**. Un front que esconde un botón no protege nada.

Las doce reglas de interfaz `R-UI-01` a `R-UI-12` están en `ADR-050`; tres de ellas son traducción directa de
las reglas no negociables: ningún control fija un veredicto (`R-UI-02`), ningún control se llama "Firmar"
(`R-UI-03`) y tras `EN_PLATAFORMA` todo es solo lectura salvo requerimiento oficial (`R-UI-05`).

**Dependencia cruzada con los dashboards**: B1 de `ADR-007` (presentación) queda **subsumida en C1** de
`ADR-050` (stack), y B2 (cuándo se construye DB5) queda ligada al orden FR. Decidir el stack cierra las dos.

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
| ~~**`R-AMB-02` no dispara con una factura real**~~ · **CERRADO 20/09/2026** (`567733e`): `engine.extraccion.categoria_de_linea` clasifica «Suministro e instalación de motor nuevo 110 kW» y «Montaje de bomba centrífuga nueva BCN-250» como `instalacion`, porque decide por la cabeza de la descripción y la señal `instalacion` va por delante de `motor` y `bomba` | **Una actuación que la ficha excluye (EXC-01, EXC-02) sale `PREVALIDADA` con ahorro publicado.** `R-AMB-02` es `BLOQUEANTE_AMBITO` y su mitad negativa solo se ejercita en contextos fabricados en memoria: ni el banco A–G ni las metamórficas lo notarían | Cerrado, pero **no como se había propuesto**: reordenar las señales habría cambiado el falso negativo por un falso positivo («Instalación de variador sobre motor existente» → `motor`), bloqueando el caso de uso central. Se cambió el criterio (qué se factura, no qué palabra va antes) y se descartan antes las cláusulas que niegan, sin las cuales el «no incluye suministro de motor» de la factura real del caso A lo volvía `NO_ELEGIBLE`. `tests/test_ambito_factura.py` recorre el circuito en los dos sentidos. Quedan **INT-A, INT-B, INT-C** para Billy (`ADR-001` §3) |
| **Una corrección humana levanta una exclusión de ámbito** (`/contrastar` 20/09/2026, **verificado**): corregir `tipo_equipo_accionado` lleva el caso D de `NO_ELEGIBLE` a `PREVALIDADO` con 305.829,6 kWh/año | Es el único camino por el que una persona anula el veredicto más fuerte de la ficha, y no hay ni un test | Decisión de Billy (si una corrección puede sacar una actuación de una exclusión o si eso exige documento nuevo) + test. En `ADR-001` §3 y en `ADR-013` §5 bis |
| ~~**La guarda que impide calcular con datos incoherentes no está protegida**~~ · **CERRADO 20/09/2026** (`567733e`): anulada la rama `elif bloqueo_previo` de `engine/reglas.py`, los 2.499 tests, los 78 e2e y los 7/7 casos siguen en verde | Una actuación `BLOQUEADO` por `R-TMP-01` **publica 305.829,6 kWh/año**. Las precondiciones físicas de `engine/calculo.py` tapan la guarda en los casos que el banco recorre, pero no en los bloqueos documentales o temporales, que no tienen precondición física. El caso C no sirve: bloquea por conflicto, que va por la otra rama | Cerrado con cinco tests y la metamórfica M07. La investigación añadió lo importante: esa rama es la **única implementación de una precondición declarada en la spec activa**, que por ser prosa el cálculo no puede evaluar. Un test ata ahora la precondición con su implementación. Anular la rama tumba cuatro tests |
| **El OCR que expira no deja rastro** (21/09/2026, **medido**): `engine/ingesta.py` da 120 s a tesseract y, si expira, devuelve texto vacío sin avisar. Cuando tesseract **falta** sí hay aviso (`ocr_no_disponible`); cuando falla, no | Una placa fotografiada que no se pudo leer es indistinguible de una ilegible. El ahorro se calcula igual (PM y N1 tienen otras fuentes), pero se pierde en silencio el **cruce** de `R-CON-01`/`R-CON-02` entre la foto y lo declarado, que es para lo que la foto está | Hallazgo H8 abierto (`docs/05` §4.5) con propuesta concreta: avisar cuando el OCR se intenta y no produce texto. Decisión de Billy, porque toca `engine/ingesta.py` y el valor del límite |
| **La tarjeta de conflicto pide al cálculo algo que en un caso bloqueado no existe** (FR1.a, 23/09/2026, **verificado**): `T-REV-revision` §6 dice que la tarjeta lee "qué arrastra el dato" de `calculo.por_unidad[].entradas` y `fuentes`, pero con un conflicto bloqueante el motor se salta la fase de cálculo entera y `actuacion.calculo` es `None` — comprobado sobre el caso C | Afecta al **escenario estrella de la demo**: el conflicto resuelto en menos de un minuto. No es un hueco de proyección (`api/` sirve todo lo que hay) ni ninguno de los 13 de `ADR-014` | **Recomendación: se le está pidiendo a la fuente equivocada.** Que un dato alimente el ahorro es una verdad de la **ficha**, no del cálculo concreto: sale de `spec.variables[v].fuentes` y del plan de cálculo, que existen con o sin resultado. Reformular la frase de la spec y servir eso. La alternativa —que el motor deje constancia de las entradas previstas antes de detenerse— es `engine/` con ADR, y no hace falta. Se resuelve al arrancar `FR1.c` |
| Decisiones de Billy pendientes bloquean pasos | Sprint parcial | Cada paso bloqueado tiene la alternativa preparada (propuesta en `spec/propuestas/`, proveedor configurable, huecos enumerados); el orquestador lista las decisiones al cerrar cada sesión |

---

## 7. Bitácora de sesiones

Se rellena con hechos. Una línea por sesión de Claude Code: fecha, pasos tocados, estado resultante, decisiones que quedan para Billy.

| Fecha | Pasos | Resultado | Para Billy |
|---|---|---|---|
| 18/09/2026 | Consolidación documental (fuera de Claude Code) | Repositorio listo para `/bootstrap` | Confirmar las decisiones de consolidación de `ADR-001` §2 |
| 18/09/2026 | `/bootstrap`: F0.0–F0.4 (esqueleto, parser, tablas, cálculo, Spec Registry), QA de la oleada 1 con correcciones | 321 tests en verde, `ruff` limpio, caso A = 305.829,6 en memoria; oleada 3 (F0.5, F0.8, QA de F0.3/F0.4) lanzada y abortada por límite de sesión de la API; sesión cerrada a petición de Billy. Siguiente: relanzar la oleada 3 con `/sprint` o `/bootstrap` (ADR-002 §1) | 1) Fila 110 kW del cuadro 6: 5,55 kW verificado frente a 6,11 kW que sugiere la serie (ADR-002 §6.1); 2) verificar las 38 filas `pendiente` (55 y 160 kW sostienen E y F); 3) INT-10 fecha de solicitud; 4) diff v1.2: reescribir `0 < h <= 8760` o ampliar la gramática, y declarar la precondición de procedimiento |
| 18–19/09/2026 | `/sprint`: F0.5–F0.12 (generator y 7 casos, Evidence Store, ingesta y extracción, Rules Engine, motor, informe y CLI, `evaluar_casos.py`, revisión normativa, cierre) | **Fase 0 cerrada**: 999 tests en verde, 7/7 casos, caso A = 305.829,6 kWh/año; E = 470.791,7875 y F = 832.770,2819125 (ground truth nuevo, `ADR-002` §4); QA devolvió NO APTO en F0.2, F0.3 y F0.4 y se corrigieron antes de seguir | Lista única en `ADR-002` §6 y `ADR-003`: fila 110 kW del cuadro 6 (5,55 vs 6,11), verificación de las 38 filas pendientes, INT-10 a INT-15, severidad de `R-CON-07` y `R-AMB-01`, `instalacion_personal_propio`, léxicos de `engine/` a la spec v1.2 |
| 19/09/2026 | `/sprint`: S3.1 (modelo canónico, log de eventos y máquina de estados) | 365 tests nuevos: los 7 casos validan contra el JSON Schema, el replay del log reproduce veredicto y ahorro bit a bit, y `ENTREGADA` → `EN_PLATAFORMA` exige firma humana. Marcas N6, N7 y N8 a `EXISTE` | `ADR-004` §6: cabecera vacía hasta que se apruebe `cabecera_v1.yaml` (S3.2); estados de fases 2–4 provisionales (`API-03`); `ccaa` sin determinar (`API-07`) |
| 19/09/2026 | Integración de `ADR-005`, `ADR-006` y `ADR-007` (perfiles, matriz de capacidades y dashboards) en la documentación viva | Consecuencias en `docs/00` §4 y §8, `docs/01` §1 y §3.9 bis, `docs/03` §3.2, §5.2, §6.1, §6.2, §7.3, §12 y §13, `docs/06` §3 bis y S3.1b, `CLAUDE.md` §6 y `ADR-001` §1 y §3. Corregidas 7 referencias cruzadas obsoletas que dejó el renombrado de los ADR | Decisiones A1–A8 de `ADR-006`, umbrales e interfaz de `ADR-007`, y la **revisión jurídica de la monitorización de trabajadores antes del primer cliente** |
| 19/09/2026 | `/sprint`: S3.3 (manifiesto interno e integridad total) | 64 tests: el manifiesto del caso A se verifica, alterar un byte de cualquier adjunto lo detecta y lo nombra, y ausentes y sobrantes se distinguen. Nace `salida/` con el constructor; un adjunto ya alterado impide generar el manifiesto en vez de sellar una foto falsa | `ADR-008` §5: `hash_cabecera` se calcula hoy sobre la cabecera vacía y cambiará al aprobar `cabecera_v1.yaml`. Tres preguntas nuevas para el gestor de la plataforma sobre `API-02`, en `docs/HUECOS.md` §2 bis |
| 19/09/2026 | `/sprint`: S3.4 (puerto de salida, mapeo declarativo, handoff, simulador y transporte) | **1679 tests en verde**, 7/7 casos y caso A = 305.829,6 kWh/año. El caso A recorre motor → handoff → simulador y el log proyecta hasta `EN_PLATAFORMA` sin traducción; un byte alterado se rechaza nombrando el fichero y la firma solo avanza con actor humano y perfil `Firma`. Construido en dos mitades paralelas sobre contratos cerrados (`ADR-009`); la revisión adversarial encontró cuatro defectos que ningún test de los constructores cubría —entre ellos una tolerancia de idempotencia que habría **borrado eventos del log del tenant**— y dos tests que no probaban lo que decían. Marcas de `salida/` y `mapping/` a `EXISTE`/`PARCIAL` | `ADR-009` §6: dónde vive el transporte (`API-09`), formato del handoff (es YAML, no código), perfil con el que operaríamos, y si el handoff debe negarse a construir lo que no está `PREVALIDADO`. Nueve preguntas nuevas para el gestor de la plataforma en `docs/HUECOS.md` §2 bis; las dos con filo comercial: si el detalle es por motor o agregado, y en qué formato viajan los decimales del ahorro (`API-08`) |
| 19/09/2026 | `/sprint`: S3.5 (seguimiento P9, requerimientos, contagio y banco de requerimientos sintéticos) | Circuito post-envío completo **sin un solo LLM**: A9 se construye como interfaz `Interprete` con implementación determinista (`ADR-010` §1), porque el Agent Runtime está bloqueado esperando decisión de proveedor. Un requerimiento de GA deja las tres actuaciones del expediente en `PENDIENTE_SUBSANACION` con **una sola señalada**; el intérprete acierta 5 de 5 mapeos del banco y escala el motivo de prosa administrativa en vez de inventarse una regla. Cerrado un agujero real en `R-REQ-02`: la puerta humana vivía en la función y se rodeaba escribiendo el evento a mano; ahora el catálogo impide que ningún componente automático nuestro reabra una actuación | `ADR-010` §7: dónde vive la familia `R-REQ` como spec (propuesta: fichero propio, sin activar) · severidad de `R-REQ-01` · límite de rondas de CN (`API-03`) · A9 con LLM sigue esperando el proveedor. **Deuda declarada**: el contagio no sabe cerrarse, así que hoy un expediente contagiado se queda contagiado (cierre de ciclo, S4) |
| 19/09/2026 | Integración de `ADR-050` (front por perfil) en la documentación viva, tras fusionar todas las ramas en `main` | Cuatro superficies adaptadas por capacidades, no ocho aplicaciones. Plan `FR0`–`FR6` en §3 ter con sus dependencias y bloqueos; **`S4.4` queda absorbida por `FR1`** para que no haya dos consolas en el plan. `docs/01` gana `api/`, `front/` y `docs/front/` con la regla de dependencias ampliada (`front/` solo habla con `api/`; nada importa de `api/` ni de `front/`). `B1` de `ADR-007` queda subsumida en `C1` y `B2` ligada al orden FR: decidir dos veces la misma cosa es como aparecen dos planes | `ADR-050` sigue en `PROPUESTA`: C1 a C7 son de Billy, y sin C1 (stack) y C7 (superficies y orden) no se construye nada de `api/` ni de `front/`. Detectada y anotada una colisión de nomenclatura: `C1`–`C10` de `ADR-001` §2 son decisiones tomadas y `C1`–`C7` de `ADR-050` son abiertas |
| 19/09/2026 | Billy aprueba C1, C7 y A8. **S3.1b** (capacidades y perfiles en el modelo y el log) y **FR0** (contrato de API y sistema de diseño mínimo) | `actor.rol` obligatorio en actor humano, 23 eventos nuevos y 5 entidades; la matriz de `ADR-006` como configuración en `engine/capacidades.yaml`, con 46 capacidades, 9 celdas pendientes que **se deniegan** y 21 con implementación real; `front/compartido/` con los tres rótulos que impiden que la interfaz mienta. **El hallazgo que más vale**: forzar el rol destapó que el banco de pruebas simulaba un usuario omnipotente que revisaba y firmaba a la vez, cosa que la matriz no permite; ~100 casos actualizados | Dos huecos del modelo de capacidades para Billy (`ADR-011` §6 bis): **nadie puede escalar a revisión humana** y **los eventos de gobierno no tienen dónde vivir** (`LogEventos` es por actuación y la auditoría de tenant y la global no existen). Y una colisión de nombres: `Capacidad` significa dos cosas distintas en dos módulos |
| 20/09/2026 | `/sprint`: **S3.8** (recálculo tras corrección humana), más el alcance de `api/` a fallar cerrado | **2.476 tests en verde**, 7/7 casos y caso A en 305.829,6 kWh/año. La corrección humana entra como **evidencia con sus tres capas** —su cita es el acto humano, con la justificación como texto literal— y la precedencia vive en un único sitio del consolidador. El caso C pasa de `BLOQUEADO` a `PREVALIDADO` con el mismo ahorro que el A, porque el C **es** el A con una errata de 90 kW. El replay reproduce el veredicto corregido solo con el log | **Corregida una afirmación falsa del propio `ADR-013`**: un evento que no debió escribirse **sí** está en el log, porque la máquina de estados anota el rechazo en vez de levantar; `de_log` lo filtra. Para Billy, `ADR-013` §6: precedencia de la corrección sobre el documento · corregir hechos documentales · `R-CON-03` tras corregir una variable con cruce |
| 20/09/2026 | `/contrastar`: auditoría docs ↔ código (las diez comprobaciones) | Tres commits. **Ocho marcas de estado decían menos de lo que hay y una decía más**; tres criterios propios sin declarar pasan a `spec/propuestas/` como INT-16, INT-17 e INT-18 (uno mide **+33 %** de ahorro). Cobertura de reglas: **26/26 con ambas mitades y 26/26 fases coincidentes**. Cuatro hallazgos verificados a mano y **tres por mutación**; uno sospechado se comprobó **falso** y se descartó. Corregido el orden de fases en `docs/04` §5.1: `resto` se evalúa **antes** del cálculo, cosa que ningún documento decía | **H1** (`R-AMB-02` no dispara con una factura real: una actuación excluida sale `PREVALIDADA`) y **H3** (la guarda de «no calcular con datos incoherentes» sobrevive a su propia eliminación) son los dos que tocan la regla de oro. Decisión nueva en `ADR-001` §3: si una corrección humana puede sacar una actuación de una exclusión de ámbito — hoy puede, y lleva el caso D de `NO_ELEGIBLE` a `PREVALIDADO` con 305.829,6 |
| 20/09/2026 | Cierre de **H1** y **H3** antes de FR1 (Billy), y `avisos_carga` como puerta de calidad | **2.532 tests**, 7/7 casos, caso A = 305.829,6. H1 no se arregló como proponía la auditoría: reordenar las señales habría cambiado el falso negativo por un **falso positivo sobre el caso de uso central**, y la factura real del caso A contiene un «no incluye suministro de motor» que tumba cualquier criterio ingenuo de compra. H3 resultó ser la única implementación de una **precondición declarada en la spec**. Los dos verificados por mutación. Nueva puerta: los avisos de carga —que señalaban ambos defectos desde F0.4 sin que nadie los leyera— quedan en una línea base cerrada que rompe ante cualquier desviación. `docs/03` §8 bis documenta por primera vez la heurística de categoría; `docs/01` §3.6 pasa de 17 ficheros de test listados a los 41 reales | **INT-A, INT-B, INT-C** de la clasificación de líneas de factura (`ADR-001` §3). **INT-C es el que importa**: una compra con un sustantivo que el léxico no conoce cae en `otro` y no bloquea **sin avisar** — es la forma exacta de H1, y hemos tapado la instancia, no la clase. Sigue abierto **H6** (el valor de las tolerancias), que es criterio normativo y entra en la spec v1.2 |
| 23/09/2026 | Arranque de **FR1**: `ADR-014` (cuatro decisiones de Billy) y los bloques `FR1.a` y `FR1.b` | **2.578 tests**, 7/7 casos, caso A en 305.829,6 kWh/año, 4 avisos de carga (los declarados, ninguno nuevo). **El lazo central del producto está cerrado**: corregir un dato por `api/` lleva el caso C de `BLOQUEADO` a `PREVALIDADO`, y el test lo comprueba sin llamar al motor por su cuenta. La cola tiene capacidad propia (`CAP-17`) en vez de un modo lista de `CAP-03`, que habría ampliado un alcance de autorización sin que la matriz lo reflejara. Una auditoría previa encontró que **tres cosas de la planificación eran falsas**, entre ellas que `GAP-REV-03` ya estaba cerrado desde el 20/09 sin que nadie lo supiera | **Dos errores de mi propio `ADR-014` los encontró quien lo implementaba**, y el primero importa: `C25` decía «emite el evento» sin mirar la matriz, y eso habría permitido a un `T-REV` sellar a mano que su corrección fue rechazada — o que no lo fue —, volviendo decorativo el control que estábamos reforzando. Para Billy: **`FR-HTTP`** (sin capa HTTP ninguna pantalla se abre contra datos reales), `origen_datos`, `GAP-REV-04`, y la tarjeta de conflicto del caso C |
| 23/09/2026 | **`FR1.c`**: las dos pantallas de `T-REV` contra el contrato ya cerrado (`front/workspace/`) | **208 tests de front** (98 de `compartido/`, 110 del workspace: 52 son los criterios `CA-REV-*` de la vista de revisión), la puerta de Python intacta (**2.588 tests**, 7/7 casos, caso A en 305.829,6 kWh/año, los 4 avisos de carga declarados) y el **caso C de punta a punta**: ver el conflicto de `PM` con sus evidencias y su cita, saltar al certificado, corregir con justificación y que el veredicto pase a `PREVALIDADO` con 305.829,6 kWh/año, **sin un solo control que toque el veredicto**. Los datos de prueba los genera `api/` de verdad, incluidas las cuatro negativas del servidor (sin justificación, con coma flotante, de otro tenant, documento alterado) | Tres huecos nuevos, y los tres son de contrato, no de pantalla: **`GAP-REV-12`** (`api/` no dice qué acciones caben, así que "Aprobar" se apoya en lo que el servidor declara abierto y no en interpretar el veredicto), **`GAP-REV-13`** (tres comandos exigen un texto que nadie redacta: A5 no existe) y **`GAP-REV-14`** (el cliente de `compartido/` pierde `Respuesta.avisos` al leer un documento). Y una corrección de la spec: la condición de solo lectura de `R-UI-05` no se puede apoyar en `estado_ciclo == "EN_PLATAFORMA"`, porque al llegar un requerimiento el ciclo deja de serlo — el candado se abría justo cuando debía cerrarse |

---

*Mantener vivo: el orquestador actualiza el estado de cada línea en la misma sesión en que cambia, y añade una línea a la bitácora al cerrar. Un "hecho cuando" que no se puede verificar con un comando o un test se reescribe hasta que se pueda.*
