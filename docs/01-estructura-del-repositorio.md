# CAE Engine — Estructura del repositorio

**Versión 1.0 · 18/09/2026 · Proyecto CAE (Billy)**

Este documento dice **qué carpetas y ficheros tiene el repositorio, para qué sirve cada uno, quién puede escribir en él y en qué fase se crea**. Es la referencia que Claude Code usa para construir el esqueleto en la primera sesión (`/bootstrap`) y para decidir dónde va cada cosa nueva después. Si una pieza de código no encaja en ninguna carpeta de este documento, la pregunta no es "dónde la meto" sino "por qué existe".

**Punto de partida (18/09/2026): el repositorio arranca vacío de código.** Solo existen documentación (`docs/`), la spec `spec/IND240_v1.1.yaml`, las propuestas en `spec/propuestas/` y la configuración de agentes (`.claude/`, `.github/`). El Engine 0.1 (Sprints 1 y 2) se reconstruye en la Fase 0 de `docs/06-plan-de-construccion.md` con los criterios de aceptación de `docs/05-evaluacion-y-banco-de-pruebas.md`.

**Marcas de fase**: `DOC` existe ya (documentación o configuración) · `F0` se creaba en la Fase 0 (reconstrucción del Engine 0.1, **cerrada el 19/09/2026**; hoy todas son `EXISTE`) · `S3` Sprint 3 · `S4` Sprint 4 · `RM` roadmap.

---

## 1. Vista general

```
cae-engine/
├── CLAUDE.md                        DOC  Entrada para Claude Code: reglas, vocabulario, orden de lectura
├── README.md                        EXISTE  Cómo instalar, ejecutar y probar (Windows y Linux)
├── pyproject.toml                   EXISTE  Paquete, dependencias, pytest (marcador `ocr`), ruff
├── .gitignore                       EXISTE  informes/, .venv/, __pycache__/, *.egg-info, .pytest_cache/
├── .github/
│   └── copilot-instructions.md      DOC  Misma verdad que CLAUDE.md, para GitHub Copilot
├── .claude/
│   ├── agents/                      DOC  Subagentes de Claude Code por dominio (§4)
│   └── commands/                    DOC  Comandos /bootstrap, /sprint, /contrastar, /nueva-ficha
│
├── docs/                            DOC  Documentación viva del proyecto (§2)
│   ├── 00 … 09-*.md
│   ├── HUECOS.md                         TODO(API-xx): lo que la plataforma no ha documentado
│   ├── decisiones/                       ADRs (una decisión = un fichero)
│   └── historico/                        Documentos superados; solo lectura
│
├── spec/                            DOC  Fichas como CONFIGURACIÓN. YAML versionado. No es código
│   ├── IND240_v1.1.yaml                  Ficha activa: 26 reglas, variables, fórmula, INT-01..07
│   └── propuestas/                       Cambios de spec pendientes de revisión humana (NO se cargan)
│       ├── cabecera_v1.yaml              Spec transversal común a todas las fichas (S3, tras aprobación)
│       └── IND240_v1.2.diff.md           Diff v1.1 → v1.2 (R-TMP-03, INT-08, INT-09, R-DOC-01)
├── mapping/                         S3   Modelo canónico → destino, por ficha (handoff, api, manifiesto)
├── data/                            EXISTE  Tablas de referencia con fuente, verificación y vigencia
│   ├── README.md                    DOC  Cómo se transcribe una tabla y qué está verificado
│   ├── reg_2019_1781_cuadro6.csv    F0   Cuadro 6 del Reg. (UE) 2019/1781 (transcribir del DOUE)
│   └── reg_2019_1781_cuadro6.meta.yaml  F0  Fuente, método de transcripción, verificación, vigencia, clave/valor y restricciones
│
├── engine/                          EXISTE  Núcleo determinista. No importa de agentes/ ni de salida/
├── agentes/                         S3   Periferia con LLM. Nunca el núcleo
├── salida/                          PARCIAL Puerto de salida y adaptadores; hoy solo el constructor del manifiesto
├── generator/                       EXISTE  Generador del paquete sintético (modelo de datos → documentos)
├── expedientes/                     EXISTE  Carpetas de entrada de los casos de prueba (salida del generator)
│   ├── EXP001-A_completo/ … EXP001-G_desordenado/
│   └── _resultados_esperados/            GROUND TRUTH. Nunca se entrega al Engine. Solo cambia con ADR
├── metricas/                        NUEVO   Catálogo de métricas en YAML, proyecciones y render (ADR-007)
├── informes/                        EXISTE  Salida generada (markdown + JSON). No se commitea
├── tests/                           EXISTE  Pruebas: cálculo, spec, paquete, Engine end-to-end, metamórficas
└── evaluar_casos.py                 EXISTE  Matriz esperado/obtenido sobre los casos de expedientes/
```

**Regla de dependencias (no negociable):** las importaciones apuntan hacia dentro.

```
tests/ → evaluar_casos.py → salida/ → agentes/ → engine/ → spec/ + data/
                              │           │
                              └───────────┴──► nunca al revés: engine/ no importa de agentes/ ni de salida/
```

Con `agentes/` y `salida/` vacíos o apagados, `engine/` sigue produciendo veredicto (modo degradado = Engine 0.1). Un test lo comprueba desde la Fase 0.

---

## 2. `docs/` — documentación viva

| Fichero | Propósito | Cuándo se lee | Quién lo cambia |
|---|---|---|---|
| `00-instrucciones-de-entrada.md` | Esencia, reglas de oro, glosario, modelo de negocio, estado. **Si solo se lee uno, este** | Siempre, al arrancar | Billy (decisiones); Claude prepara |
| `01-estructura-del-repositorio.md` | Este documento | Al crear o mover cualquier cosa | Claude, en la misma sesión en que cambia la estructura |
| `02-plataforma-oficial.md` | Cómo tramita de verdad la plataforma OMIE/MIBGAS: actores, fases, cabecera, estados, certificados, frontera de firma | Antes de tocar modelo canónico, estados o salida | Solo con fuente oficial nueva |
| `03-arquitectura-backend.md` | Principios, módulos N1–N9 / S1–S8, modelo canónico, log de eventos, máquina de estados, salida, agent runtime, seguridad | Antes de diseñar o implementar cualquier módulo | Claude; marcas de estado se actualizan en la sesión |
| `04-motor-de-reglas-y-specs.md` | Anatomía de regla, severidades, fases, lenguaje de expresiones, cabecera, familias R-*, checklist de nueva ficha | Antes de tocar `engine/reglas.py`, `engine/expresiones.py` o cualquier `spec/*.yaml` | Reglas nuevas: propuesta → aprobación de Billy → YAML |
| `05-evaluacion-y-banco-de-pruebas.md` | Los 7 casos, ground truth, trampas, metamórficas, métricas, cómo leer el 100 % | Antes de escribir tests o el generator | Ground truth solo con ADR |
| `06-plan-de-construccion.md` | Fase 0 (reconstrucción), Sprint 3, Sprint 4, roadmap, riesgos, "hecho cuando" | Al planificar una sesión | Claude actualiza estado; Billy cambia prioridades |
| `07-entorno-y-competencia.md` | Plataforma oficial (visión de mercado), delegados, competidores, referencias de precio | Contexto de producto; no para construir | Con fuente y fecha |
| `08-clientes-y-primeros-contactos.md` | Segmentos, candidatos, argumentos, preguntas, seguimiento | Comercial; no para construir | Billy tras cada contacto |
| `09-catalogo-industrial.md` | 28 fichas industriales: arquetipos de fórmula, evidencias, capacidades que exigen al marco | Al elegir la segunda ficha o diseñar capacidades del marco | Cuando cambie el catálogo |
| `HUECOS.md` | `TODO(API-xx)` enumerados con dueño y fecha de revisión | Antes de escribir cualquier cosa que toque la API oficial | Se cierra un hueco solo con documentación oficial |
| `decisiones/ADR-nnn-*.md` | Una decisión por fichero: contexto, opciones, decisión, consecuencias, quién | Al cambiar ground truth, spec activa, severidades, INT-xx, arquitectura | Claude redacta; Billy aprueba las de negocio y spec |
| `historico/` | Versiones superadas | Solo para entender por qué se decidió algo | Nadie: solo lectura |

**Precedencia cuando dos fuentes discrepan** (de mayor a menor): BOE → plataforma oficial (lo publicado) → catálogo MITECO → `spec/*.yaml` activa → `docs/00` → `docs/02` → `docs/03` y `docs/04` → resto de `docs/` → código. Si el código contradice un documento, uno de los dos está mal y se arregla en la misma sesión.

---

## 3. Carpetas de código: contenido por fase

### 3.1 `spec/` — fichas como configuración (`DOC`, ampliada en `S3`)

```
spec/
  IND240_v1.1.yaml            ACTIVA. 26 reglas. Única ficha cargable hoy
  propuestas/                 NO SE CARGAN. Revisión humana pendiente (regla de oro 9)
    cabecera_v1.yaml          Variables y reglas R-CAB-* comunes a todas las fichas
    IND240_v1.2.diff.md       Cambios propuestos sobre v1.1
    composicion_v1.yaml       R-GRP-*, R-EXP-*, R-REQ-* (S4)
```

- Una ficha = un YAML `<CODIGO>_v<version_ficha>.yaml`. La `version_spec` interna sigue semver y cambia con cualquier cambio de reglas.
- El Spec Registry (`engine/spec_registry.py`) **solo carga `spec/*.yaml`**, nunca `spec/propuestas/`. Cuando Billy aprueba una propuesta, se mueve (no se copia) a `spec/` y se registra un ADR.
- Función desconocida en `logica` o `formula` = error de carga; la ficha no se activa.

### 3.2 `data/` — tablas de referencia (`EXISTE`; 38 de 39 filas pendientes de verificación humana)

```
data/
  README.md                          Qué tablas hay, fuente, quién las verificó, vigencia, método de transcripción
  reg_2019_1781_cuadro6.csv          Columnas: kva_salida, kw_motor, perdidas_ref_kw, cos_phi, verificado
  reg_2019_1781_cuadro6.meta.yaml    id, fuente, fecha y método de transcripción, verificación, vigencia (desde/hasta), columnas, clave, valor, restricciones
```

Toda tabla son **dos ficheros con el mismo nombre base** (`.csv` + `.meta.yaml`); `engine/tablas.py` los lee juntos y `cargar_tabla(id)` resuelve el fichero por el `id` del meta, sin leer la spec. El motor es genérico: el esquema (columnas, columna `clave` de búsqueda, columna `valor` que devuelve `buscar` e interpola según INT-02, `restricciones`) es dato del `.meta.yaml`, nunca código. El `.meta.yaml` lleva fuente oficial (URL), fecha y método de transcripción (`doue` / `boe` / `memoria_agente`), quién la verificó y contra qué, y vigencia (`desde`, `hasta`); `README.md` lo explica en prosa. **Valor verificado que hay que reproducir**: 110 kW → 5,55 kW de pérdidas de referencia. El resto de filas se marcan `verificado: pendiente` hasta que Billy las contraste contra el DOUE (ver `data/README.md`; a 18/09/2026 la transcripción es de memoria del agente porque el proxy de la sesión bloqueó BOE y EUR-Lex).

### 3.3 `engine/` — núcleo determinista (`EXISTE` tras la Fase 0, ampliado en `S3`/`S4`)

```
engine/
  __init__.py
  spec_registry.py      EXISTE N1  Carga y valida specs; versiones; garantía NO_EVALUABLE→SUBSANABLE;
                                  valida el bloque `calculo` con `calculo.planificar` al cargar
  expresiones.py        EXISTE —   Parser de lista blanca para `logica` y `formula`. Nada de eval()
  calculo.py            EXISTE N3  Calculation Engine: Decimal, fórmula del YAML, traza, controles físicos;
                                  `planificar()` valida y compila lo que la spec declara
  tablas.py             EXISTE N3  Carga de data/*.csv + .meta.yaml con vigencia; clave y valor del meta; INT-02
  ingesta.py            EXISTE S1  PDF nativo, OCR, xlsx, EXIF, separación de PDF combinados, SHA-256 de TODO
  clasificacion.py      EXISTE A1  Clasificación léxica por tipo de documento con confianza
  extraccion.py         EXISTE A2  Interfaz `Extractor` + implementación por reglas (tablas antes que texto)
  registro_xlsx.py      EXISTE —   Lector del registro SCADA: N2, P_prom, h_despues, huella
  evidencias.py         EXISTE N4  Evidence Store en memoria: tres capas por dato, consolidación, conflictos
  reglas.py             EXISTE N2  Rules Engine: fases, severidades, CUMPLE/FALLA/NO_EVALUABLE, veredicto
  motor.py              EXISTE S3  Orquestador lineal: ingesta → clasificación → extracción → consolidación
                                  → reglas → cálculo; devuelve `Actuacion`
  informe.py            EXISTE —   Informe de prevalidación (markdown + JSON)
  cli.py                EXISTE —   `python -m engine.cli <carpeta> --md … --json … [--sin-ocr] [--fecha]`
  modelo/               EXISTE N7  ActuacionCanonica, GrupoActuaciones, Expediente, Verificador, Tenant,
                                  con JSON Schema propio en esquemas/ y `desde_motor` (S3.1)
  eventos/              EXISTE N8  Log solo-añadir, hash encadenado, JSON canónico, grabación y replay (S3.1)
  estados.py            EXISTE N6  Cuatro niveles de estado, contagio, inalterabilidad post-firma (S3.1)
  estados_plataforma.yaml EXISTE — Tabla de mapeo: 8 estados de actuación confirmados y 11 de expediente
                                  provisionales (`oficial: false`, TODO(API-03))
  compositor.py         S4  N9  R-GRP / R-EXP, propuesta de grupos y expedientes
```

Reglas de la carpeta:

- **No importa** de `agentes/`, `salida/`, `generator/` ni `tests/`.
- Aritmética del ahorro con `Decimal`. Un `float` en `calculo.py` o `reglas.py` es un defecto.
- Ningún `if ficha == "IND240"` en ningún fichero. Lo específico de una ficha vive en su YAML.
- `motor.py` en Fase 0 es lineal y síncrono; en Sprint 3 pasa a emitir eventos (`eventos/`) sin cambiar su interfaz pública.
- El código llama `Actuacion` a la unidad de trabajo desde la Fase 0 (no hay tests antiguos que proteger: se adopta el vocabulario de la plataforma oficial directamente, decisión D1 de `docs/02`). `Expediente` queda reservado para la agregación oficial.

### 3.4 `generator/` — fábrica de casos sintéticos (`EXISTE`)

```
generator/
  __init__.py
  modelo_caso.py        Modelo de datos de un caso (empresa, motores, fechas, valores) → dataclasses
  casos.py              Definición de los 7 casos A–G como variaciones de un caso base
  documentos/           Un render por tipo de documento (factura, ficha técnica, certificado, convenio…),
                        más `base.py` (utilidades de maquetación), `imagenes.py` (fotos y placa para OCR),
                        `escaneo.py` (el escaneo girado del caso G) e `irrelevantes.py`
  marcas.py             Marca "DOCUMENTO SINTÉTICO – SOLO PRUEBAS" en cada página; EXIF en fotos
  calculo_caso.py       Llama a `engine.calculo` para obtener el AETOTAL de cada caso (nunca a mano)
  ground_truth.py       Compone el JSON de `_resultados_esperados/` desde el mismo modelo de datos
  generar.py            `python -m generator.generar` → expedientes/EXP001-*/ + _resultados_esperados/
```

- Un solo modelo de datos produce todos los documentos de un caso: así el ground truth y los documentos no pueden discrepar.
- Todo nombre, NIF, nº de serie, coordenada y empresa es inventado. Nunca datos reales.
- En Sprint 3 se amplía a **fábrica de casos**: mismas variables, plantillas y calidades de escaneo distintas, con un conjunto reservado que nunca se usa para ajustar el extractor.

### 3.5 `expedientes/` — entradas de prueba (`EXISTE`, generadas)

```
expedientes/
  EXP001-A_completo/        1 motor 110 kW, perfecto                     → PREVALIDADO   305.829
  EXP001-B_falta_registro/  N2 solo declarado                            → SUBSANABLE    305.829 (provisional)
  EXP001-C_contradictorio/  PM 110 vs 90 kW                              → BLOQUEADO     —
  EXP001-D_fuera_ambito/    bomba de tornillo (EXC-03)                   → NO_ELEGIBLE   —
  EXP001-E_dos_motores/     + ventilador radial 55 kW                    → PREVALIDADO   461.433 (ver nota)
  EXP001-F_tres_motores/    + compresor centrífugo 160 kW, h_despues<h_antes → PREVALIDADO 777.128 (ver nota)
  EXP001-G_desordenado/     nombres genéricos, PDF combinado, escaneo girado, fotos, xlsx renombrado → PREVALIDADO + avisos  305.829
  _resultados_esperados/    ground truth por caso (JSON). NUNCA se pasa al Engine
```

Se regeneran con `python -m generator.generar`; se commitean para que los tests no dependan de reportlab/pillow. **Nota sobre E y F**: los totales proceden del Engine 0.1 original; los parámetros exactos de los motores 2 y 3 no están documentados fuera de aquel código, así que el generator reconstruido fija los suyos y el ground truth de E y F se recalcula y se registra en ADR (`docs/05` §2). El caso A sí es reproducible exactamente: 110 kW, 1.485 → 1.188 rpm, 6.000 h, p = 5,55/110.

### 3.6 `tests/` — banco de pruebas (`EXISTE`: 999 tests al cerrar la Fase 0)

```
tests/
  conftest.py                    Fixtures: spec cargada, tabla, caso A en memoria
  test_expresiones.py            Parser: funciones permitidas, error en función desconocida, sin eval
  test_calculo.py                Caso A = 305.829,6 exacto; Decimal; truncado; FIS-01/02; min(h)
  test_tablas.py                 110 kW → 5,55; fila inexistente → INT-02
  test_spec_registry.py          Carga IND240; rechaza propuestas/; garantía NO_EVALUABLE→SUBSANABLE
  test_reglas.py                 Por regla: un caso que cumple y uno que falla; fases; veredicto
  test_evidencias.py             Tres capas; conflicto → null; OCR 0,75; normalización S.L./SL
  test_ingesta.py                SHA-256 de todo; separación de PDF; vinculación por hash no por nombre
  test_extraccion.py             Cobertura de variables por caso; cita obligatoria; trampas; la spec manda
  test_motor.py                  Encadenado completo y `Actuacion`; los 7 casos contra el ground truth
  test_informe.py                Markdown y JSON: tres capas, traza, descargo de la spec, provisional
  test_generator.py              Los 7 casos se generan; marca sintética en cada página; ground truth coherente
  test_engine_e2e.py             7/7 veredictos; A/E/F/G ahorro esperado; tiempos razonables
  test_metamorficas.py           Renombrar/reordenar/duplicar/añadir irrelevante no cambia nada; alterar PM → BLOQUEADO
  test_modo_degradado.py         Con agentes/ y salida/ ausentes, engine/ produce veredicto (en subproceso)
  test_qa_hallazgos_f03.py       Defectos que encontró la revisión QA del cálculo; se conservan como regresión
  test_qa_hallazgos_f04.py       Ídem para el Spec Registry
```

Los tests que necesitan `tesseract` llevan `@pytest.mark.ocr` y se saltan si no está instalado: en un clon sin OCR
la suite queda en 976 pasados y 23 saltados, y `evaluar_casos.py` sigue dando 7/7.

Definición de hecho para cualquier cambio: `pytest -q` en verde, `evaluar_casos.py` 7/7, caso A en 305.829,6 kWh/año. Un test que rompe no se borra ni se relaja: se explica.

### 3.7 `agentes/` — periferia con LLM (`S3`)

```
agentes/
  runtime/        S2  Contrato común: JSON Schema, reintentos, cita obligatoria, no_lo_se, sin aritmética,
                      prompts versionados, traza (modelo, versión, coste, latencia), router, presupuesto
  lector/         A1 clasificador · A2 extractor (texto y visión) detrás de la interfaz `Extractor`
  analista/       A3 emparejador · A4 auditor de inconsistencias · A8 revisor sombra (solo avisos)
  redactor/       A5 subsanaciones · A7 informes · A9 intérprete de requerimientos
  prompts/        Un fichero por prompt, versionado en el nombre: `extractor_v3.md`
```

- Toda salida de agente pasa por `runtime/` antes de tocar `engine/`. Un valor sin cita se descarta.
- Una salida con resultado calculado se rechaza en el runtime (test).
- A0 (coordinador) no está aquí: es `engine/estados.py`. A6 (vigía normativo) trabaja fuera de línea y solo produce diffs en `spec/propuestas/`.

### 3.8 `salida/` — puerto y adaptadores (`PARCIAL`: solo `constructor/`, desde S3.3)

```
salida/
  puerto.py       construir(actuacion, mapping) · entregar(paquete) · consultar_estado(ref) · consultar_tareas(tenant)
  constructor/    EXISTE (S3.3) manifiesto interno con los cinco hashes y `verificar()`; el payload de
                  cabecera y detalle llega con S3.2 y S3.4. Nuestro, nunca el oficial (TODO(API-02))
  handoff/        Carpeta ordenada + manifiesto + informe, para que el tenant presente por el cauce vigente
  simulador/      Reproduce SOLO lo documentado de la plataforma: 8 estados de fase 1, estados provisionales
                  de fases 2–4 (marcados NO OFICIAL), manifiesto con hash, validación de esquema, firma humana
                  simulada, tareas pendientes
  api_oficial/    Conector real. Vacío hasta que exista diccionario (docs/HUECOS.md API-01)
  transporte/     Firma de peticiones API con certificado de USUARIO. Dónde vive: decisión de Billy (API-09)
```

- **No existe `salida/firma/` como código.** La firma es un acto humano con certificado de representante; solo se registra el evento `FirmaRegistrada`.
- Nada en `salida/` inventa un campo de la API. Lo desconocido se referencia como `TODO(API-xx)` con enlace a `docs/HUECOS.md`.

### 3.9 `mapping/` — modelo canónico → destino (`S3`)

```
mapping/
  README.md
  IND240.handoff.yaml       Cómo se ordena la carpeta de handoff para IND240
  IND240.api.yaml           Cuando exista el diccionario (API-08). Hasta entonces, solo huecos
  manifiesto.handoff.yaml
  manifiesto.api.yaml       Cuando exista (API-02)
```

Declarativo. Si un cambio en la API oficial exige tocar `engine/`, el diseño está mal.

### 3.9 bis `metricas/` — catálogo y dashboards (`NUEVO`, `ADR-007`)

```
metricas/
  catalogo.yaml            Definición de todas las métricas: fórmula, fuente, cortes, vistas y capacidad
  esquema_catalogo.json    JSON Schema del catálogo; una métrica sin fuente, vista o capacidad no carga
  proyecciones/            normalizar · hechos_actuacion · hechos_evento · hechos_llamada · hechos_usuario
  calcular.py              Evalúa el catálogo sobre las proyecciones
  acceso.py                Filtro por capacidad y tenant; enmascarado
  render/                  Salida estática por vista (O-GLO, O-FUN, O-EQU, T-TEC)
```

Una métrica se define **una sola vez en configuración**, con el mismo criterio que las fichas: el catálogo es
YAML validado, no código. Una métrica sin fuente se muestra `SIN DATO` con su "desde", nunca como cero.
Dependencias: `metricas/` lee de `engine/` y de `telemetria/`; **nada importa de `metricas/`**.

### 3.10 `informes/` (`EXISTE`, no se commitea)

Salida de `engine/cli.py` y `evaluar_casos.py`. En `.gitignore`. Los informes que valen como referencia se copian a `docs/decisiones/` o a un ADR, nunca se dejan aquí.

---

## 4. `.claude/` y `.github/` — orquestación

```
.claude/
  agents/
    orquestador-arquitectura.md   Lee docs/, contrasta el repo, produce el plan de sesión, reparte trabajo, integra
    spec-fichas.md                Todo lo que toca spec/*.yaml, data/ y docs/04; prepara diffs, no los activa
    generador-casos.md            generator/, expedientes/, ground truth, docs/05
    motor-nucleo.md               engine/ (reglas, cálculo, evidencias, estados, eventos, modelo)
    ingesta-extraccion.md         engine/ingesta.py, clasificacion.py, extraccion.py, registro_xlsx.py; luego agentes/lector
    integracion-plataforma.md     salida/, mapping/, docs/02, docs/HUECOS.md
    qa-evaluacion.md              tests/, evaluar_casos.py, metamórficas, definición de hecho
    revisor-normativo.md          Contrasta código y spec contra BOE/ficha; abre INT-xx; nunca decide
  commands/
    bootstrap.md                  Primera sesión: crea el esqueleto de §1 y ejecuta la Fase 0
    sprint.md                     Ejecuta el siguiente paso de docs/06 con "hecho cuando" verificable
    contrastar.md                 Comprueba docs ↔ código y actualiza marcas EXISTE/PARCIAL/NUEVO
    nueva-ficha.md                Checklist de docs/04 §9 para dar de alta una ficha
.github/
  copilot-instructions.md         Resumen de CLAUDE.md para Copilot: mismas reglas, mismo orden de lectura
```

Los agentes son **roles con permisos de escritura acotados** (columna "carpetas que toca" en cada fichero). El orquestador es el único que escribe en `docs/06` (estado del plan) y en `docs/01` (este fichero); el resto propone.

---

## 5. Convenciones

| Tema | Convención |
|---|---|
| Lenguaje | Python ≥ 3.11. Paquetes planos (`engine/`, `agentes/`, `salida/`, `generator/`), sin `src/`. Se ejecuta con `python -m` |
| Nombres | Módulos, funciones y variables en **español sin tildes** (`evaluar_actuacion`, `hash_reglas`), igual que las specs. Clases en CamelCase (`Actuacion`, `DatoConsolidado`) |
| Vocabulario | `Actuacion` (unidad de trabajo) · `GrupoActuaciones` · `Expediente` (agregación oficial). Nunca "expediente" para lo que se prepara y envía. Ver `docs/00` §4 |
| Estados | Cuatro niveles distintos, nunca mezclados: veredicto, estado de ciclo, estado de plataforma (actuación), estado de plataforma (expediente). Ver `docs/03` |
| Marcas en docs | `F0` (existió en Engine 0.1; se reconstruía en Fase 0, ya cerrada) · `NUEVO` (nunca implementado) · `EXISTE` / `PARCIAL` (implementado en este repo) · `NO DOCUMENTADO` (→ `TODO(API-xx)`). `A CONFIRMAR` ya no se usa. Se actualizan en la misma sesión en que cambia el código |
| Huecos de API | En código: `# TODO(API-07): ver docs/HUECOS.md`. Nunca un valor inventado |
| Interpretaciones | En spec: `interpretacion: INT-xx`. En código: se lee de la spec, nunca se hardcodea un criterio |
| Tests | `pytest`; un fichero por módulo; nombres `test_<que>_<condicion>`; ground truth solo desde `_resultados_esperados/` |
| Formato | `ruff` (lint + format), línea 110. Sin `black` ni `isort` aparte |
| Commits | Un commit por entregable con "hecho cuando" cumplido; mensaje en español: `F0.3: Rules Engine con fases y tres resultados` |
| Datos | Nunca datos reales en el repo. Documentos sintéticos con marca visible. Anonimización antes de cualquier prueba con documentación real |
| Windows | Billy trabaja en Windows con PowerShell y ruta OneDrive: rutas con `pathlib`, sin `os.system`, sin dependencias de `poppler`/`tesseract` en los tests unitarios (solo en los e2e, marcados `@pytest.mark.ocr` y saltados si no están instalados) |

---

## 6. Orden de creación en `/bootstrap`

1. Leer `CLAUDE.md`, `docs/00`, este documento, `docs/03`, `docs/04`, `docs/05`, `docs/06`.
2. Crear el esqueleto de §1 con carpetas vacías y `__init__.py`; `pyproject.toml`; `.gitignore`; `README.md` mínimo.
3. `data/reg_2019_1781_cuadro6.csv` según `data/README.md` (fila 110 kW → 5,55 verificada; resto `pendiente`).
4. Fase 0 de `docs/06` en su orden: expresiones → tablas → cálculo → spec registry → generator → ingesta/extracción → evidencias → reglas → motor/informe/cli → evaluar_casos → tests.
5. Al cerrar la Fase 0: actualizar marcas en `docs/03` y `docs/04`, escribir `docs/decisiones/ADR-002-reconstruccion-engine-0.1.md` con los ground truth de E y F, y dejar `docs/06` con la Fase 0 marcada como hecha.

---

*Mantener vivo: este documento cambia en la misma sesión en que cambia la estructura. Un fichero que exista en el repo y no aparezca aquí, o al revés, es un defecto que se corrige antes de cerrar la sesión.*
