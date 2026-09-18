# CAE Engine — Arquitectura del backend

**Versión 1.0 · 18/09/2026 · Proyecto CAE (Billy)**

## 0. Cabecera

**Qué consolida.** Este documento funde `07-backend-y-motor-de-reglas` v1.0 y las secciones §3 (backend) y §4 (funcionalidades) de `11-backend-funcionalidades-y-motor-de-reglas` v1.0, ambos ya en `docs/historico/`. Donde discrepaban, prevalece `11` (escrito tras la confrontación con la plataforma oficial); lo de `07` no contradicho sigue vigente. El detalle del motor de reglas (anatomía de regla, severidades, fases, familias `R-*`, lenguaje de expresiones, checklist de nueva ficha) vive en `docs/04-motor-de-reglas-y-specs.md`; el banco de pruebas en `docs/05-evaluacion-y-banco-de-pruebas.md`; el plan y el orden de construcción en `docs/06-plan-de-construccion.md`; los huecos de la plataforma oficial en `docs/HUECOS.md`.

**A quién sirve.** A cualquier persona o sesión de IA (p. ej. Claude Code) que vaya a diseñar o implementar un módulo del backend. Se lee después de `CLAUDE.md`, `docs/00` y `docs/01`, y antes de escribir código.

**Punto de partida.** El repositorio arranca sin código (18/09/2026). El Engine 0.1 (Sprints 1 y 2) se construyó en otro entorno y no está aquí; se reconstruye en la Fase 0 de `docs/06` con los criterios de aceptación de `docs/05`. Por eso este documento no describe "lo que hay", sino **lo que hay que construir y en qué orden lo que existió se reconstruye**.

**Marcas de estado** (las de `CLAUDE.md` §3):

| Marca | Significado |
|---|---|
| `F0` | Existió en el Engine 0.1 con diseño probado; se reconstruye en la Fase 0 de `docs/06` |
| `NUEVO` | Diseño aprobado, nunca implementado; entra en el sprint indicado |
| `EXISTE` | Implementado en este repositorio (al arrancar, ninguno) |
| `PARCIAL` | Implementado en parte en este repositorio; se indica cuál (al arrancar, ninguno) |
| `NO DOCUMENTADO` | La plataforma oficial no lo ha publicado; se modela como hueco `TODO(API-xx)` en `docs/HUECOS.md`, nunca como suposición |

La marca antigua `A CONFIRMAR` desaparece: no hay repositorio previo contra el que confirmar. Lo que era duda de implementación es ahora una decisión de diseño de la Fase 0 y está resuelta en §14 de este documento o en `docs/04`. Las marcas se actualizan en la misma sesión en que cambia el código (`/contrastar`).

**Precedencia cuando dos fuentes discrepan** (de mayor a menor): BOE → plataforma oficial (lo publicado) → catálogo MITECO → `spec/*.yaml` activa → `docs/00` → `docs/02` → este documento y `docs/04` → resto de `docs/` → código. Si este documento contradice una regla de oro de `docs/00`, este documento está mal. Si el código contradice este documento, uno de los dos está mal y se arregla en la misma sesión.

---

## 1. Instrucciones para quien escribe código (persona o IA)

Obligatorio, sin excepciones:

1. **Ningún LLM ejecuta aritmética ni decide si una regla se cumple.** Los agentes proponen valores con cita; el núcleo decide. El runtime rechaza cualquier salida de agente con un resultado calculado.
2. **Nada de `eval()` ni ejecución de cadenas arbitrarias.** `logica` y `formula` se interpretan con el parser de lista blanca de `engine/expresiones.py` (vocabulario en `docs/04`). Función desconocida = error de carga de la spec, no de ejecución.
3. **Aritmética con `Decimal`**, nunca `float`, en todo lo que toque el ahorro. `AETOTAL` truncado a kWh entero (`INT-06`).
4. **No inventar campos de la API oficial.** A 18/09/2026 no hay diccionario público (§10.4). Lo desconocido se deja como `TODO(API-xx)` enlazado a `docs/HUECOS.md`, no se rellena con suposiciones.
5. **Añadir una ficha es añadir YAML** (spec + mapping de salida). Si hace falta un `if ficha == ...` en `engine/`, el diseño está mal.
6. **Las dependencias apuntan hacia dentro.** `engine/` no importa nada de `agentes/`, `salida/`, `generator/` ni `tests/`.
7. **El sistema debe llegar a un veredicto sin ningún LLM disponible** (modo degradado = Engine 0.1). Un agente caído o caro nunca bloquea una actuación. Hay un test que lo comprueba desde la Fase 0 (`tests/test_modo_degradado.py`).
8. **Todo cambio pasa el banco de pruebas de `docs/05`** antes de entrar: `pytest -q` en verde, `evaluar_casos.py` 7/7 y caso A en 305.829,6 kWh/año. Un test que rompe no se borra ni se relaja: se explica.
9. **Nunca custodiar certificados de representante.** La firma de actos administrativos es un acto humano en casa del tenant; nosotros solo registramos `FirmaRegistrada`. El transporte (firma de peticiones API con certificado de usuario) es un módulo aparte (§10.3).
10. **Datos reales: anonimizados** antes de entrar en pruebas; nada de datos de cliente en documentos compartibles. Documentos sintéticos siempre con la marca "DOCUMENTO SINTÉTICO – SOLO PRUEBAS".
11. **Lo que la norma no cierra se marca como `INT-xx`**, con criterio, alternativa e impacto, declarado en la spec. Nunca se resuelve en silencio dentro del código.
12. **Todo cambio normativo y toda spec activa pasan por revisión humana** (Billy) antes de tocar `spec/` o el motor. Los diffs se preparan en `spec/propuestas/` o en un ADR; no se activan.

---

## 2. Principios de arquitectura

Los siete primeros vienen del diseño original; los tres últimos, de la confrontación con la plataforma oficial (`docs/02`).

| # | Principio | Consecuencia práctica |
|---|---|---|
| 1 | Núcleo determinista, agentes en la periferia | Reproducibilidad: misma entrada + misma versión = mismo resultado |
| 2 | Modelo canónico propio, independiente de cualquier destino | Un cambio en la API oficial toca un fichero de `mapping/`, no el motor |
| 3 | Puertos y adaptadores en la salida | Varios destinos sobre la misma actuación: handoff al tenant, simulador, API oficial |
| 4 | Log de eventos inmutable, solo-añadir, encadenado por hash | Auditoría, reproducción y regresión automática con actuaciones pasadas |
| 5 | Workflow primero, agentes como funciones tipadas | El orquestador es una máquina de estados, no un LLM que decide el siguiente paso |
| 6 | Configuración antes que código | Fichas, reglas, mappings y checklists viven en YAML versionado |
| 7 | Firma y transporte separados del constructor del payload | Operamos con la norma vigente (vía sujeto delegado) y quedamos listos para otros perfiles de acceso si se aprueban |
| 8 | **La unidad de trabajo es la actuación**; grupo y expediente son agregaciones con reglas propias | El motor evalúa a tres niveles; el payload se construye por actuación; el expediente se compone, no se calcula |
| 9 | **La automatización termina en `COMPLETA`**; la firma es un acto humano con certificado de representante | Ningún componente nuestro firma actos administrativos; transporte y firma son cosas distintas |
| 10 | **Lo no documentado por la plataforma es un hueco enumerado**, nunca una suposición en el código | `docs/HUECOS.md` es un artefacto de primera clase; cada `TODO(API-xx)` tiene dueño y fecha de revisión |

---

## 3. Mapa de módulos

Rutas según `docs/01` §3. La columna Estado describe el arranque desde cero: `F0` se reconstruye en la Fase 0 con el alcance indicado; `NUEVO` entra en el sprint indicado.

### 3.1 Núcleo determinista (`engine/`)

| ID | Módulo | Función | Fichero | Estado |
|---|---|---|---|---|
| N1 | Spec Registry | Carga y valida fichas YAML versionadas; solo `spec/*.yaml`, nunca `spec/propuestas/`; garantía `NO_EVALUABLE` → `SUBSANABLE` al cargar; resuelve qué versión aplica por fecha | `engine/spec_registry.py` | `F0` una ficha (IND240) y garantía de carga · `NUEVO` S3: spec transversal de cabecera, vigencias de versiones, coeficientes (art. 18 bis) cuando existan |
| — | Parser de expresiones | Lista blanca para `logica` y `formula`. Nada de `eval()` | `engine/expresiones.py` | `F0` (decisión §14 a) |
| N2 | Rules Engine | Evalúa reglas por fases con tres resultados y fija el veredicto; **tres niveles** (actuación/unidad, grupo, expediente) | `engine/reglas.py` | `F0` nivel actuación/unidad · `NUEVO` S4: grupo y expediente (con N9) |
| N3 | Calculation Engine + tablas | Fórmula leída del YAML, `Decimal`, traza, controles físicos; tablas de `data/` con vigencia y búsqueda por clave (`INT-02`); **control cruzado** con el valor de la plataforma | `engine/calculo.py`, `engine/tablas.py` | `F0` cálculo y cuadro 6 · `NUEVO` S3: control cruzado (necesita sandbox) |
| N4 | Evidence Store | Grafo de evidencias, tres capas por dato, consolidación, conflictos, `tratable_por_plataforma` | `engine/evidencias.py` | `F0` en memoria con serialización JSON (§14 e) · `NUEVO` S3: persistencia junto al log |
| N5 | Integridad | SHA-256 de **todo** fichero en ingesta + manifiesto interno | `engine/ingesta.py` (hash) · `salida/constructor/` (manifiesto) | `F0` hash total desde la Fase 0 (§14 d) · `NUEVO` S3: manifiesto interno |
| N6 | Máquina de estados | Cuatro niveles de estado, contagio, inalterabilidad post-firma; es el A0 (coordinador) hecho código | `engine/estados.py` | `NUEVO` S3 |
| N7 | Modelo canónico | `Actuacion`, `GrupoActuaciones`, `Expediente`, `Verificador`, `Tenant`; validado con JSON Schema | `engine/modelo/` | `NUEVO` S3 |
| N8 | Log de eventos | Solo-añadir, hash encadenado, JSON canónico, replay | `engine/eventos/` | `NUEVO` S3 |
| N9 | Compositor de expedientes | Propone grupos y expedientes válidos a partir de `R-GRP` / `R-EXP` | `engine/compositor.py` | `NUEVO` S4 (Expediente Builder, decisión de Billy) |

Módulos de `engine/` sin ID propio en este mapa (`docs/01` §3.3): `motor.py` (S3), `informe.py` e `cli.py` (informe de prevalidación markdown + JSON y línea de comandos, `F0`), `ingesta.py`, `clasificacion.py`, `extraccion.py`, `registro_xlsx.py` (S1 y extractor por reglas, `F0`).

### 3.2 Servicios

| ID | Módulo | Función | Fichero | Estado |
|---|---|---|---|---|
| S1 | Ingesta | PDF nativo, OCR, xlsx, EXIF, separación de PDF combinados, clasificación léxica con confianza, extractor por reglas detrás de la interfaz `Extractor`, lector del registro SCADA; hash de todo | `engine/ingesta.py`, `engine/clasificacion.py`, `engine/extraccion.py`, `engine/registro_xlsx.py` | `F0` |
| S2 | Agent Runtime | El contrato común de agentes hecho código una sola vez (§11) | `agentes/runtime/` | `NUEVO` S3 |
| S3 | Orquestador | Workflow por eventos con tareas humanas; la máquina de estados (N6) hace de A0 | `engine/motor.py` | `F0` lineal y síncrono (ingesta → extracción → consolidación → reglas → cálculo) · `NUEVO` S3: emite eventos sin cambiar su interfaz pública |
| S4 | Consola de revisión | Escalados, conflictos, correcciones del profesional, tareas pendientes de la plataforma; centrada en lo previo a la firma | — (S4, `docs/06`) | `NUEVO` S4 |
| S5 | Salida | Puerto + adaptadores handoff / simulador / API; transporte separado de la firma humana (§10) | `salida/` | `NUEVO` S3 |
| S6 | Evaluación | Banco de pruebas, fábrica de casos, metamórficas, batería `INT-xx` contra sandbox | `generator/`, `expedientes/`, `tests/`, `evaluar_casos.py` | `F0` 7 casos, ground truth, tests y `evaluar_casos.py` · `NUEVO` S3: fábrica de casos y batería `INT-xx` |
| S7 | Seguridad y tenencia | Aislamiento por tenant (delegado u obligado directo), enmascarado, anonimización (§12) | transversal | `NUEVO` S3 |
| S8 | Vigilancia normativa (A6) | Fuera de línea; propone diffs sobre YAML en `spec/propuestas/`; sigue RD 36/2023, órdenes y plataforma | fuera de código | `NUEVO` (hoy vigilancia manual; sin diff automático) |

---

## 4. Procesos P0–P10

Patrón común: **la regla detecta y decide; el agente explica y propone.** Los eventos se detallan en §6.2.

| # | Proceso | Rol de agente | Pieza que decide | Eventos |
|---|---|---|---|---|
| P0 | Admisión: alta de la actuación, partes, tenant, verificador | — | N6 | `ActuacionAbierta`, `TenantAsignado`, `VerificadorAsignado` |
| P1 | Ingesta y clasificación | A1 (lector) | S1, N5 | `DocumentoRegistrado`, `DocumentoClasificado`, `PdfSeparado` |
| P2 | Extracción de evidencias, doble extracción | A2 (lector) | N7 (validación), N4 | `EvidenciaPropuesta`, `EvidenciaDescartadaSinCita`, `DesacuerdoExtractores` |
| P3 | Ficha, ámbito y cabecera | A3 (analista) propone ficha | N1 + reglas `R-AMB`, `R-CAB` | `FichaAsignada`, `CabeceraConsolidada`, `VeredictoEmitido` |
| P4 | Consolidación y cruce | A4 (analista) explica el conflicto | Reglas `R-CON` + consolidador (§8) | `DatoConsolidado`, `ConflictoDetectado`, `DatoCorregidoPorHumano` |
| P5 | Cálculo y control cruzado | Ninguno, por diseño | N3 | `CalculoRealizado`, `DiscrepanciaCalculoPlataforma` |
| P6 | Pre-revisión | A8 (analista), **solo avisos** | Checklist en YAML | `ObservacionRegistrada` |
| P7 | Subsanación, con origen | A5, A7 (redactor) | Reglas falladas → carencias (campo `subsanacion`) | `SubsanacionSolicitada{origen}`, `SubsanacionCerrada`, `CorreccionRechazadaPostFirma`; vuelve a P1 |
| P8 | Empaquetado y envío | Ninguno | S5 + control cruzado del cálculo (`R-XCK`) | `PayloadConstruido`, `ManifiestoGenerado`, `EntregadoADelegado`, `EnviadoAPI`, `FirmaRegistrada` (actor humano) |
| P9 | Seguimiento post-envío | A9 (redactor) interpreta requerimientos | N6 (mapeo de estados) | `EstadoPlataformaRecibido`, `TareaPendienteRecibida`, `RequerimientoRecibido{origen}`, `RequerimientoInterpretado`, `DesistimientoRegistrado` |
| P10 | Composición de grupos y expedientes | — | N9 + reglas `R-GRP`, `R-EXP` | `GrupoPropuesto`, `ExpedientePropuesto`, `AvisoContagio`, `ActuacionHuerfana` |

Decisiones registradas el 18/09/2026: A8 empieza emitiendo solo avisos (no altera el veredicto); P9 entra en el Sprint 3 junto con P8; P10 es Sprint 4 (Expediente Builder, decisión de Billy pendiente).

---

## 5. Modelo canónico (N7) — `NUEVO` S3

Esquema propio, versionado (`modelo_version`), validado con JSON Schema. Es lo único que consumen los adaptadores de salida. Vive en `engine/modelo/`.

### 5.1 Vocabulario y decisión de nombres

El código llama **`Actuacion`** a la unidad de trabajo **desde la Fase 0**. No existe alias `Expediente = Actuacion` porque no hay código previo ni tests antiguos que proteger: se adopta directamente el vocabulario de la plataforma oficial (decisión D1 de `docs/02`, recogida en `docs/01` §3.3). `Expediente` queda reservado para la agregación oficial de actuaciones `VERIFICADA_FAVORABLE`. Usar "expediente" para lo que se prepara y envía es un defecto. Las carpetas `expedientes/EXP001-*` conservan su nombre por ser los casos de prueba heredados; su contenido es una actuación cada una.

### 5.2 Entidades

```
Tenant (sujeto delegado u obligado directo)
├─ id, tipo {delegado, obligado_directo}, capacidad_delegacion_disponible?  (NO DOCUMENTADO cómo se consulta → TODO(API-11))
└─ Actuacion[]
    ├─ id, codigo_identificativo_propio           ← clave de reconciliación con la plataforma
    ├─ modelo_version, creado_en
    ├─ ficha: { codigo, version_ficha, version_spec, hash_spec }
    ├─ cabecera: { … }                            ← spec transversal cabecera_v1.yaml (docs/04)
    ├─ partes: propietario_inicial, solicitante (tenant), instalador, verificador?
    ├─ atributos_agrupacion: { ccaa, anio_finalizacion, sector, verificador_id }   ← obligatorios para componer expediente
    ├─ documentos[]: { doc_id, tipo, confianza_tipo, sha256, bytes, paginas, origen, metodo_lectura }
    ├─ unidades[]  (IND240: una por motor; clave de unión nº de serie) → variables{} → DatoConsolidado
    ├─ variables_actuacion{} → DatoConsolidado
    ├─ evaluacion: { reglas[], veredicto, hash_reglas, evaluado_en }
    ├─ calculo: { por_unidad[], total, traza[], provisional, control_cruzado? }
    ├─ observaciones[]                            (avisos de A8 y de reglas AVISO)
    ├─ interpretaciones_aplicadas[]               (INT-xx que han influido en el resultado)
    ├─ subsanaciones[]: { origen ∈ {interno, verificador, GA, CN}, requerimiento_ref?, reglas[], documentos[], estado }
    └─ ciclo: { estado_ciclo, estado_plataforma?, grupo_id?, expediente_id?, historial → log de eventos }

GrupoActuaciones                                 ← verificación conjunta, dictamen único
├─ id, tenant, verificador_id, actuaciones[], estado_plataforma (comparte los 8 de fase 1)
└─ evaluacion_grupo: { reglas R-GRP[], veredicto_agregado }

Expediente (oficial)                             ← agregación de VERIFICADA_FAVORABLE
├─ id, tenant, ccaa, anio, sector, verificador_id, actuaciones[] | grupo_id
├─ estado_expediente (provisional, NO OFICIAL; §7.1)
├─ evaluacion_expediente: { reglas R-EXP[], avisos_contagio[] }
└─ requerimientos[]: { origen ∈ {GA, CN}, ronda, informe_pdf_sha256, actuaciones_afectadas[], estado }

Verificador
├─ id, razon_social, acreditacion_enac_ref, ccaa_operativas?  (NO DOCUMENTADO si la plataforma lo expone)
```

**`codigo_identificativo_propio`** es la clave de reconciliación con la plataforma: es el campo de la cabecera común que la plataforma devuelve en estados, notificaciones y tareas, y el que permite emparejar lo que recibimos (P9) con la `Actuacion` que enviamos (P8). Lo genera el Engine (`= Actuacion.id`), es único dentro del tenant (`R-CAB-01`) y no cambia nunca después de `PayloadConstruido`.

Los campos marcados `NO DOCUMENTADO` se modelan como opcionales y se enlazan a su `TODO(API-xx)` en `docs/HUECOS.md`; no se les da semántica propia.

### 5.3 `DatoConsolidado`: tres capas por dato

Regla de oro 3 de `docs/00`. Un `DatoConsolidado` guarda siempre:

| Capa | Contenido |
|---|---|
| 1. Documento | `evidencias[]`: `{doc_id, pagina, texto_literal, metodo (tabla / regex / ocr / llm), confianza, extractor_version}` |
| 2. Interpretación | `valor_normalizado`, `unidad`, `tipo_evidencia` (`demostrado` / `declarado` / `derivado`), `fuente_primaria`, `interpretacion` (INT-xx si aplica), **`tratable_por_plataforma: bool`** |
| 3. Cálculo | `valor_consumido` (`Decimal` como cadena), o `null` si hay conflicto |

- Un dato sin al menos una evidencia con cita literal **no entra** en la actuación.
- `tratable_por_plataforma` indica si el dato es de los que la plataforma oficial valida o calcula por sí misma. Sirve para el control cruzado (`R-XCK`) y para saber qué es diferencial en el informe. No cambia la evaluación.
- `valor_consumido` se serializa como cadena para que el JSON canónico y el hash sean reproducibles (§6.1).

---

## 6. Log de eventos (N8) — `NUEVO` S3

Vive en `engine/eventos/`. Es la fuente de verdad del ciclo: el estado de una actuación es una proyección del log.

### 6.1 Sobre de evento

```json
{
  "evento_id": "uuid",
  "actuacion_id": "ACT-...",
  "secuencia": 17,
  "tipo": "EvidenciaPropuesta",
  "ocurrido_en": "2026-09-18T10:22:31Z",
  "actor": { "clase": "agente | motor | humano | plataforma", "id": "lector@prompt-v3" },
  "payload": { },
  "hash_previo": "…",
  "hash": "sha256(hash_previo + json_canonico(evento sin hash))"
}
```

Reglas del log:

- **Solo añadir.** Nunca se edita ni se borra un evento; una corrección es un evento nuevo (`DatoCorregidoPorHumano`).
- **El estado de la actuación es una proyección del log.** Se puede reconstruir desde cero.
- **Replay**: cualquier actuación pasada se puede volver a ejecutar contra una versión nueva de spec, reglas o agente. Cada actuación procesada es, por tanto, una prueba de regresión (F-22).
- **JSON canónico**: claves ordenadas, UTF-8, sin espacios, `Decimal` como cadena. Sin esto el hash no es reproducible.
- Los eventos de agente incluyen modelo, versión de prompt, coste y latencia (§11.2, punto 6).
- Los eventos `FirmaRegistrada`, `DatoCorregidoPorHumano` y `DesistimientoRegistrado`, y la confirmación de una interpretación de A9, solo son válidos con `actor.clase = humano`.

### 6.2 Catálogo de eventos por proceso

| Proceso | Eventos |
|---|---|
| P0 Admisión | `ActuacionAbierta`, `TenantAsignado`, `VerificadorAsignado` |
| P1 Ingesta | `DocumentoRegistrado` (con `sha256` **siempre**), `DocumentoClasificado`, `PdfSeparado` |
| P2 Evidencias | `EvidenciaPropuesta`, `EvidenciaDescartadaSinCita`, `DesacuerdoExtractores` |
| P3 Ficha | `FichaAsignada`, `CabeceraConsolidada`, `VeredictoEmitido` |
| P4 Cruce | `DatoConsolidado`, `ConflictoDetectado`, `DatoCorregidoPorHumano` |
| P5 Cálculo | `CalculoRealizado`, `DiscrepanciaCalculoPlataforma` |
| P6 Pre-revisión | `ObservacionRegistrada` |
| P7 Subsanación | `SubsanacionSolicitada{origen}`, `SubsanacionCerrada`, `CorreccionRechazadaPostFirma` |
| P8 Empaquetado | `PayloadConstruido`, `ManifiestoGenerado`, `EntregadoADelegado`, `EnviadoAPI`, `FirmaRegistrada` (actor humano) |
| P9 Seguimiento | `EstadoPlataformaRecibido`, `TareaPendienteRecibida`, `RequerimientoRecibido{origen}`, `RequerimientoInterpretado`, `DesistimientoRegistrado` |
| P10 Composición | `GrupoPropuesto`, `ExpedientePropuesto`, `AvisoContagio`, `ActuacionHuerfana` |

En la Fase 0, `engine/motor.py` no emite eventos: es lineal y síncrono. En el Sprint 3 pasa a emitirlos sin cambiar su interfaz pública (`docs/01` §3.3). Los tipos de evento se declaran en un único sitio (`engine/eventos/`); un tipo no declarado es un error.

---

## 7. Máquina de estados (N6) — `NUEVO` S3

Vive en `engine/estados.py`. Es el A0 (coordinador): código, no un LLM.

### 7.1 Cuatro niveles de estado, cuatro cosas distintas

| Nivel | Valores | Quién lo fija | Estado documental |
|---|---|---|---|
| Veredicto (calidad de la actuación) | `NO_ELEGIBLE` > `BLOQUEADO` > `SUBSANABLE` > `PREVALIDADO` | Rules Engine | `F0` |
| Estado de ciclo (nuestro trabajo) | §7.2 | Máquina de estados | `NUEVO` |
| Estado de plataforma — actuación (fase 1) | `BORRADOR`, `COMPLETA`, `ENVIADA_A_VERIFICACION`, `PDTE_RECTIFICACION_VER`, `VERIFICACION_EN_PROCESO`, `VERIFICADA_FAVORABLE`, `VERIFICADA_DESFAVORABLE`, `NO_PUEDE_EMITIR_DICTAMEN` | La plataforma; nosotros solo lo reflejamos | Confirmado (presentación OMIE/MIBGAS 30/06/2026, `docs/02`) |
| Estado de plataforma — expediente (fases 2–4) | Provisionales: `BORRADOR_SOLICITUD`, `PRESENTADO`, `EN_VALIDACION_TECNICA`, `REQUERIDO_GA`, `VALIDADO_GA`, `EN_REVISION_FORMAL`, `REQUERIDO_CN`, `RESUELTO_FAVORABLE`, `RESUELTO_DESFAVORABLE`, `INSCRITO`, `DESISTIDO` | La plataforma; **nombres nuestros, no oficiales** | `NO DOCUMENTADO` → `TODO(API-03)` |

Ningún veredicto significa CAE garantizado. Los nombres provisionales de fases 2–4 se modelan como **tabla de mapeo** (YAML), no como código: cuando llegue el diccionario oficial, cambiar nombres es cambiar YAML.

### 7.2 Estado de ciclo

```
ABIERTA → EN_PROCESO → EVALUADA ─┬─► PENDIENTE_SUBSANACION(origen=interno) ──(nuevos docs)──► EN_PROCESO
                                 ├─► EN_REVISION_HUMANA ─────────────────────────────────────► EVALUADA
                                 ├─► DESCARTADA                    (NO_ELEGIBLE confirmado por humano)
                                 └─► LISTA_PARA_ENVIO ► ENTREGADA(handoff | API) ► EN_PLATAFORMA ► CERRADA
                                                                                   │
        EN_PLATAFORMA + PDTE_RECTIFICACION_VER ──► PENDIENTE_SUBSANACION(origen=verificador)
        EN_PLATAFORMA + REQUERIDO_GA | REQUERIDO_CN ──► PENDIENTE_SUBSANACION(origen=GA|CN), bloquea Expediente completo
        EN_PLATAFORMA + DESISTIDO ──► CERRADA(resultado=desistida)
```

### 7.3 Reglas de transición

- Solo una actuación `PREVALIDADO` **y revisada por un humano** pasa a `LISTA_PARA_ENVIO`.
- `ENTREGADA` → `EN_PLATAFORMA` requiere un evento `FirmaRegistrada` de actor `humano`. La firma no la hacemos nosotros; solo registramos que ocurrió, con quién y cuándo. Ningún evento de actor `agente` o `motor` puede hacer esa transición (propiedad metamórfica de ciclo, `docs/05`).
- Tras `EN_PLATAFORMA`, **ningún cambio de datos es válido fuera de un requerimiento oficial** (inalterabilidad). Un intento de corrección interna post-firma se rechaza con evento `CorreccionRechazadaPostFirma`.
- Un requerimiento de GA o CN sobre una actuación genera `PENDIENTE_SUBSANACION` en **todas** las actuaciones del expediente, con `afectada_directamente: bool`. Es el riesgo de contagio hecho estado.
- Un tenant sin `capacidad_delegacion_disponible` no puede recibir actuaciones en `LISTA_PARA_ENVIO` sin aviso explícito (§12).
- Presupuesto de pasos y de coste por actuación; agotado, `EN_REVISION_HUMANA`.
- Toda transición es un evento del log (§6); la máquina de estados no guarda estado propio fuera de la proyección.

---

## 8. Consolidación de evidencias (N4) — antes de las reglas

Cómo se pasa de N evidencias a un `valor_consumido`. Vive en `engine/evidencias.py`.

| Paso | Qué hace | Estado |
|---|---|---|
| 1. Agrupar | Evidencias por variable y por unidad. Clave de unión: números de serie. El registro SCADA se vincula por SHA-256, nunca por nombre de fichero | `F0` |
| 2. Normalizar | Según `cruce` de la spec: `exacto` o `normalizado` (mayúsculas, puntuación, "S.L." vs "SL") | `F0` |
| 3. Comparar | Todas las fuentes presentes; se aplica `tolerancia_cruce_*` cuando la spec la defina | `F0` |
| 4. OCR | Evidencias de foto o escaneo entran con confianza 0,75. Si discrepan de una fuente fiable no bloquean: se marcan como posible error de OCR | `F0` |
| 5. Conflicto entre fuentes fiables | `valor_consumido = null`, evento `ConflictoDetectado` con las dos evidencias. El motor **no elige** (regla de oro 6) | `F0` |
| 6. Doble extracción | Extractor de reglas y extractor LLM sobre el mismo documento. Coinciden → confianza alta. Discrepan → no es un conflicto documental sino un desacuerdo de lectura: `DesacuerdoExtractores`, se escala a revisión humana y se registra como métrica (tasa de desacuerdo, `docs/05`) | `NUEVO` S3 (con S2 y A2 LLM) |
| 7. Declarado ≠ demostrado | Si una variable exige `derivado` o `demostrado` y solo hay valor declarado, el dato entra marcado como tal y lo recoge la regla de evidencia correspondiente (`R-EVD-04` en IND240) | `F0` |

El consolidador es determinista y no llama a modelos. Lo que A4 aporta en P4 es la explicación del conflicto para el profesional, nunca su resolución.

---

## 9. Integridad (N5) y manifiesto interno

- SHA-256 de **todo** fichero en el momento de ingesta, antes de cualquier transformación (`engine/ingesta.py`, desde la Fase 0, §14 d). El hash del original se conserva aunque se separe un PDF combinado: se registran el original y cada parte (`PdfSeparado`).
- Vinculación de documentos por hash y por nº de serie, nunca por nombre de fichero. Renombrar, reordenar o duplicar ficheros no cambia nada (propiedades metamórficas de `docs/05`).
- Manifiesto interno (`NUEVO` S3, `salida/constructor/`): el nuestro, no el oficial. Añade `hash_cabecera` y `hash_detalle` del payload para poder demostrar exactamente qué se envió.

```json
{
  "actuacion_id": "ACT-...",
  "codigo_identificativo_propio": "ACT-...",
  "modelo_version": "1.0",
  "generado_en": "2026-09-18T10:40:00Z",
  "ficha": { "codigo": "IND240", "version_ficha": "1.1", "hash_spec": "…" },
  "ficheros": [
    { "ruta": "03_factura/FAC-001.pdf", "tipo": "factura", "sha256": "…", "bytes": 182034 }
  ],
  "hash_cabecera": "…",
  "hash_detalle": "…",
  "hash_log_eventos": "…",
  "hash_manifiesto": "…"
}
```

- El formato del manifiesto **oficial** (algoritmo, estructura) es `NO DOCUMENTADO` → `TODO(API-02)`. El mapeo del nuestro al oficial vive en `mapping/manifiesto.<destino>.yaml` y no toca `engine/`.
- Criterio de aceptación (Sprint 3, `docs/06`): el manifiesto del caso A es verificable; alterar un byte de cualquier adjunto lo detecta; el simulador rechaza un paquete con hash alterado.

---

## 10. Salida (S5) — `NUEVO` S3

Vive en `salida/` (`docs/01` §3.8). Nada en `salida/` inventa un campo de la API; lo desconocido es un `TODO(API-xx)` con enlace a `docs/HUECOS.md`.

### 10.1 Puerto de salida (`salida/puerto.py`)

```
construir(actuacion, mapping)       → Paquete { payload (cabecera + detalle), manifiesto, adjuntos[] }
entregar(paquete)                   → Acuse
consultar_estado(referencia)        → EstadoPlataforma
consultar_tareas(tenant)            → TareaPendiente[]
```

El mapeo modelo canónico → destino es **declarativo y por ficha** (`mapping/<FICHA>.<destino>.yaml`, `docs/01` §3.9). Si un cambio en la API oficial exige tocar `engine/`, el diseño está mal.

### 10.2 Adaptadores

| Adaptador | Para qué | Dependencia externa | Cuándo |
|---|---|---|---|
| **Handoff** (`salida/handoff/`) | Carpeta ordenada + manifiesto + informe de prevalidación, para que el tenant presente por el cauce vigente | Ninguna | Sprint 3, primero |
| **Simulador** (`salida/simulador/`) | Reproduce **solo lo documentado** de la plataforma: los 8 estados de fase 1, estados provisionales de fases 2–4 (marcados `NO OFICIAL`), manifiesto con hash, validación de esquema, **firma humana simulada** (paso humano que cambia `COMPLETA` → `ENVIADA_A_VERIFICACION`), tareas pendientes. Permite desarrollar P8 y P9 sin sandbox | Ninguna | Sprint 3, primero |
| **API oficial** (`salida/api_oficial/`) | Envío, consulta, notificaciones, tareas reales | Diccionario de API (`API-01`) + certificado de usuario + tenant con acceso | Cuando existan ambos |

### 10.3 División transporte / firma

El antiguo componente único "firmante en casa del delegado" se divide en dos cosas de naturaleza distinta, tras la confrontación con la plataforma oficial (`docs/02`): el certificado de **usuario** firma peticiones API; el certificado de **representante** (FNMT) firma actos administrativos y es siempre humano.

```
salida/
  constructor/    payload cabecera + detalle + manifiesto, sin firmar        NUESTRO, en nuestra infraestructura
  transporte/     firma de peticiones API con certificado de USUARIO         Dónde vive: depende de la respuesta del gestor
                  Reenvía estados y tareas como eventos                      (perfil Modificación, TODO(API-09))
                                                                             · si admite terceros: nuestra infra, aislado por tenant
                                                                             · si no: componente desplegable en casa del tenant
  (firma)         NO ES SOFTWARE NUESTRO. Es un paso humano con certificado  Solo registramos FirmaRegistrada
                  de REPRESENTANTE en casa del tenant. No existe salida/firma/
```

Reglas:

- **Nunca custodiamos certificados de representante.** No existe `salida/firma/` como código; la firma se representa únicamente por el evento `FirmaRegistrada` de actor humano (§7.3).
- Para el certificado de **usuario** (transporte), dónde vive el componente es decisión de Billy tras la respuesta del gestor de la plataforma (`API-09`). El backend queda preparado para ambas opciones: el constructor no cambia en ningún caso.
- La automatización termina en `COMPLETA` (principio 9). Si la norma llega a contemplar un perfil de colaborador, se añade un adaptador directo limitado a borradores; el resto no cambia.

### 10.4 Lo que se sabe y lo que no de la API oficial

Conocido (presentación OMIE/MIBGAS del 30/06/2026, `docs/02`): acceso web o API; peticiones firmadas con certificado digital; validación de esquema, firma, certificado y permisos; adjuntos con manifiesto de ficheros y hash, carga asíncrona; estructuras JSON; notificaciones y tareas consultables; entorno de pruebas previsto.

No conocido a 18/09/2026: endpoints, esquemas JSON, autenticación concreta, formato del manifiesto, nombres y granularidad del formulario de detalle, estados de fases 2–4. Comprobado ese día en la página "Plataforma CAE" de MITECO: la plataforma figura "en fase de desarrollo", el único documento técnico publicado es la presentación del 30/06/2026 y la gestión sigue por los cauces habituales hasta la puesta en marcha.

**Regla:** el simulador implementa solo lo conocido. Cada hueco es un `TODO(API-xx)` enumerado en `docs/HUECOS.md` con dueño y fecha de revisión, no una suposición en el código. A 18/09/2026 hay doce enumerados (`API-01` a `API-12`).

### 10.5 Seguimiento post-envío (P9) y subsanación con tres orígenes (P7)

Los estados de plataforma llegan como `EstadoPlataformaRecibido` (del transporte o del simulador) y se reconcilian con la `Actuacion` por `codigo_identificativo_propio`.

| Origen | Llega como | Alcance | Bloquea | Lo interpreta | Alimenta |
|---|---|---|---|---|---|
| `interno` | Regla fallada del Engine | Actuación | Nada externo | Regla (campo `subsanacion`) + A5 redacta | Petición al cliente |
| `verificador` | `PDTE_RECTIFICACION_VER` + motivos (+ informe PDF) | Actuación (o grupo, con dictamen único) | La actuación / el grupo | A9 → `{regla_id \| documento, texto_literal, confianza}`; humano confirma | P7 + banco de pruebas (anonimizado) |
| `GA` | Requerimiento en fase 3A (+ informe PDF) | Por actuación, **bloquea el expediente completo** | Todo el expediente | A9 | P7 sobre todas las actuaciones del expediente |
| `CN` | Requerimiento en fase 3B, posible segunda ronda | Ídem | Todo el expediente | A9 | Ídem |

- `VERIFICADA_FAVORABLE`, `VERIFICADA_DESFAVORABLE` y `NO_PUEDE_EMITIR_DICTAMEN` cierran la actuación con etiqueta de resultado para evaluación (F-20).
- El sujeto puede **desistir** durante un requerimiento de GA o CN: evento `DesistimientoRegistrado`, actor humano.
- Toda subsanación con origen externo referencia un requerimiento con informe (PDF con hash) y la interpretación de A9 debe estar confirmada por un humano antes de reabrir P7 (familia `R-REQ`, `docs/04`).
- **Tareas pendientes** de la plataforma: se consumen por `consultar_tareas` y se proyectan en la consola (S4) como cola priorizada del tenant. Es la única parte de la consola que mira aguas abajo de la firma; el resto se centra en lo previo.

---

## 11. Agentes (S2) — `NUEVO` S3

Vive en `agentes/` (`docs/01` §3.7). Periferia con LLM; nunca el núcleo. Toda salida de agente pasa por `agentes/runtime/` antes de tocar `engine/`.

### 11.1 Tres capacidades sobre un único runtime

Los roles lógicos A0–A9 de `docs/00` se mantienen; se despliegan así:

| Capacidad | Carpeta | Roles | Entrada | Salida |
|---|---|---|---|---|
| **Lector** | `agentes/lector/` | A1 Clasificador · A2 Extractor (variantes texto y visión), detrás de la interfaz `Extractor` de `engine/extraccion.py` | Fichero / documento + variables que pide la ficha | Tipo + confianza · valor, unidad, página, texto literal, confianza |
| **Analista** | `agentes/analista/` | A3 Emparejador · A4 Auditor de inconsistencias · A8 Revisor sombra | Grafo de evidencias, catálogo, checklist | Ficha candidata · hipótesis de conflicto · observaciones (solo avisos) |
| **Redactor** | `agentes/redactor/` | A5 Subsanaciones · A7 Informes · A9 Intérprete de requerimientos | Reglas falladas · actuación resuelta · requerimiento del verificador, GA o CN | Texto para el cliente · informe · requerimiento mapeado a reglas y documentos |

A0 (coordinador) es código: la máquina de estados (`engine/estados.py`). A6 (vigía normativo) trabaja fuera de línea y solo propone diffs en `spec/propuestas/`. Los prompts viven en `agentes/prompts/`, un fichero por prompt, versionado en el nombre (`extractor_v3.md`).

### 11.2 Lo que implementa el runtime (`agentes/runtime/`)

El contrato común de agentes de `docs/00`, hecho código una sola vez:

1. Validación de salida contra JSON Schema; si no valida, reintento acotado; si sigue sin validar, `no_lo_se`.
2. Cita obligatoria; un valor sin cita se descarta antes de llegar al Evidence Store (`EvidenciaDescartadaSinCita`).
3. Confianza declarada; `no_lo_se` es una salida legítima.
4. Rechazo de cualquier salida con resultado calculado (test).
5. Registro de prompts versionado; cambiar un prompt obliga a reevaluar.
6. Traza: modelo, versión de prompt, entrada, salida, coste, latencia → evento.
7. Escalado a humano por umbral de confianza o conflicto crítico.
8. Router de modelo por tarea y presupuesto de pasos y coste por actuación.

### 11.3 Reglas de activación

- **Fuera del camino crítico**: con todos los agentes apagados, el Engine sigue produciendo veredicto con el extractor por reglas (`tests/test_modo_degradado.py`).
- **Puerta de activación**: un rol solo entra en producción con conjunto de evaluación y línea base propios (conjunto reservado de la fábrica de casos, `docs/05`). El umbral numérico es decisión de Billy (`CLAUDE.md` §6).
- El proveedor de LLM y las condiciones de tratamiento de datos son decisión de Billy y se cierran antes del primer expediente real (§12).
- A8 no se llama "verificador" en ningún texto de producto. Si con datos reales se demuestra que una observación de A8 anticipa rectificaciones del verificador, se propone convertirla en regla determinista o en ítem de checklist del YAML: de juicio a norma, nunca al revés.

---

## 12. Seguridad y tenencia (S7) — `NUEVO` S3

- **Aislamiento por tenant**: datos, claves y logs separados. Requisito para marca blanca. El tenant puede ser un **sujeto delegado** o un **sujeto obligado directo** (obligación ≥ 50 MWh, que opera directamente en la plataforma).
- El tenant lleva `capacidad_delegacion_disponible` como atributo informativo (cómo se consulta en la plataforma: `NO DOCUMENTADO`, `TODO(API-11)`). Un tenant sin capacidad no puede recibir actuaciones en `LISTA_PARA_ENVIO` sin aviso explícito.
- **Antes de llamar a un LLM con documentación real**: enmascarar identificadores (NIF, razón social, direcciones, referencias catastrales) cuando la tarea no los necesite; región de proceso y no-entrenamiento con los datos como requisito contractual con el proveedor. A cerrar **antes** del primer expediente real.
- Anonimización de actuaciones reales para el banco de pruebas: detección asistida, validación humana obligatoria.
- Documentos sintéticos: siempre con la marca "DOCUMENTO SINTÉTICO – SOLO PRUEBAS".
- Sin certificados de representante en nuestra infraestructura (§10.3). El certificado de usuario, donde diga Billy tras `API-09`.

---

## 13. Catálogo de funcionalidades

Visto desde el producto. Cada línea dice qué producto la vende, qué proceso la sostiene, si es **diferencial** frente a la plataforma oficial (lo que ella no hace) y su estado con las marcas de §0.

| ID | Funcionalidad | Producto | Proceso / módulo | ¿Diferencial? | Estado |
|---|---|---|---|---|---|
| F-01 | Ingesta de documentación desordenada (PDF, escaneos, xlsx, fotos, PDF combinados) con hash de todo | CAE Check | P1 / S1, N5 | Sí | `F0` (hash total desde la Fase 0) |
| F-02 | Clasificación documental con confianza | CAE Check | P1 / A1 | Sí | `F0` (reglas léxicas) · LLM `NUEVO` S3 |
| F-03 | Extracción de variables con evidencia (documento, página, texto, método, confianza) | CAE Check | P2 / A2, N4 | Sí | `F0` reglas · LLM `NUEVO` S3 |
| F-04 | Cruce de **contenido** entre documentos y detección de contradicciones con ambas evidencias | CAE Check | P4 / R-CON, A4 | **Sí, el núcleo del diferencial** | `F0` |
| F-05 | Comprobación de ámbito y exclusiones de la ficha | CAE Check | P3 / R-AMB | Parcial (la plataforma valida lo tratable; el ámbito exige leer documentos) | `F0` |
| F-06 | Comprobación de presencia documental | CAE Check | R-DOC-01 | **No** (la plataforma lo hace); se mantiene como control previo | `F0` |
| F-07 | Comprobación de evidencia demostrada vs. declarada (registro ≥ 30 días, inalterabilidad) | CAE Check | R-EVD | Sí | `F0` |
| F-08 | Cálculo determinista con traza | CAE Check | P5 / N3 | No como producto; sí como **control cruzado** | `F0` |
| F-09 | Control cruzado con el cálculo de la plataforma; bloqueo ante discrepancia | CAE Check / Platform | P5, P8 / N3, R-XCK | Sí | `NUEVO` S3 (necesita sandbox) |
| F-10 | "Qué te falta": lista de carencias por regla, en lenguaje llano, con documentos concretos | CAE Check | P7 / campo `subsanacion`, A5 | Sí | `F0` carencias por regla fallada · campo `subsanacion` y redacción A5 `NUEVO` S4 |
| F-11 | Cabecera común completa (precio de cesión, inversión, localización, propietario, subvención…) extraída de documentos | CAE Platform | P3 / `cabecera_v1.yaml`, R-CAB | Sí (la plataforma la pide; nosotros la rellenamos con evidencia) | `NUEVO` S3 (tras aprobación de Billy) |
| F-12 | Payload de actuación (cabecera + detalle + manifiesto) listo para `BORRADOR` → `COMPLETA` | CAE Platform | P8 / S5 constructor | Sí | `NUEVO` S3 |
| F-13 | Handoff al tenant (carpeta + manifiesto + informe) por el cauce vigente | CAE Platform | S5 handoff | Sí | `NUEVO` S3 |
| F-14 | Consumo de notificaciones y **tareas pendientes** de la plataforma; cola priorizada por tenant | CAE Platform | P9 / S4 | Sí | `NUEVO` S3 (simulador) · S4 (consola) |
| F-15 | Interpretación de requerimientos de verificador, GA y CN → reglas y documentos; reapertura de subsanación con contagio | CAE Platform | P9, P7 / A9, N6 | Sí | `NUEVO` S3 |
| F-16 | **Expediente Builder**: propuesta de grupos y expedientes válidos (CCAA + año + sector + verificador), avisos de huérfanas y de contagio | CAE Platform | P10 / N9, R-GRP, R-EXP | Sí | `NUEVO` S4 (decisión de Billy) |
| F-17 | Informe de prevalidación por destinatario (cliente, instalador, tenant) | CAE Check / Platform | A7, `engine/informe.py` | Sí | `F0` markdown/JSON único · por destinatario `NUEVO` S4 |
| F-18 | Revisor sombra (A8): observaciones sin alterar el veredicto; promoción a regla cuando anticipe rectificaciones | CAE Platform | P6 | Sí | `NUEVO` |
| F-19 | Preparación de actuaciones singulares y vinculación a CVP | Roadmap | — | Sí | Decisión de Billy · fase II de la plataforma |
| F-20 | Registro de resultado real (dictamen, resolución) como etiqueta para el banco de pruebas | CAE Monetization | P9 / S6 | Sí (activo defendible) | `NUEVO` S3 |
| F-21 | Multi-tenant: delegados y sujetos obligados directos, aislamiento, capacidad disponible | CAE Platform | S7 | — | `NUEVO` S3 |
| F-22 | Replay de cualquier actuación pasada contra nueva spec/regla/agente (regresión automática) | Interno | N8 | — | `NUEVO` S3 |
| F-23 | Vigilancia normativa con propuesta de diff sobre el YAML | Interno / A6 | S8 | — | `NUEVO` (hoy vigilancia manual, fuera de código) |

**Lectura de negocio.** De las 23 funcionalidades, 17 son diferenciales, una lo es parcialmente (F-05), tres son internas (F-21..23) y dos no lo son. Esas dos (F-06 y F-08 como producto) son justo las que la competencia vende como "checklist" y "calculadora"; no deben aparecer como reclamo, sino como controles previos. Lo que se vende es F-03 + F-04 + F-07 + F-10 (CAE Check) y F-11 a F-16 (CAE Platform).

---

## 14. Decisiones de diseño de la Fase 0

Sustituyen a los antiguos puntos `A CONFIRMAR` de los documentos históricos. Son decisiones técnicas: no requieren aprobación de Billy, pero se registran aquí y en `docs/decisiones/` si cambian.

| # | Antes era duda | Decisión de la Fase 0 |
|---|---|---|
| a | Si `logica` del YAML era descriptiva o ejecutable, y si existía un parser | **`logica` es ejecutable** por `engine/expresiones.py`, parser de lista blanca con el vocabulario cerrado de `docs/04`. Nada de `eval()`. Una regla que **no** pueda expresarse con ese vocabulario se implementa en Python, registrada por su `id`, y lleva un test que verifica que hace lo que dice su `logica`. Función desconocida = error de carga de la spec |
| b | Si el código formalizaba los tres resultados de regla | **`engine/reglas.py` devuelve `CUMPLE` / `FALLA` / `NO_EVALUABLE` desde la Fase 0.** Una `NO_EVALUABLE` no bloquea por sí misma; la garantía "toda regla bloqueante que pueda quedar `NO_EVALUABLE` tiene una regla `SUBSANABLE` que detecta la carencia" es un test del Spec Registry al cargar cualquier ficha |
| c | Qué regla iba en qué fase | **La asignación de reglas a fases es la tabla de fases de `docs/04`** y se declara en el YAML con el campo `fase`. El motor lee la fase de la spec; no hay lista de reglas por fase en el código |
| d | El hash cubría solo el registro SCADA | **SHA-256 de todo fichero en ingesta desde la Fase 0**, antes de cualquier transformación (§9). Vinculación por hash y por nº de serie, nunca por nombre |
| e | Persistencia del Evidence Store | **En memoria en la Fase 0, con serialización JSON** (es lo que produce `engine/informe.py`). La persistencia llega en el Sprint 3 junto con el log de eventos (N8): el Evidence Store se reconstruye por replay |

Otras decisiones ya recogidas en este documento: `Actuacion` sin alias desde la Fase 0 (§5.1); `motor.py` lineal en Fase 0 y por eventos en Sprint 3 sin cambiar su interfaz (§6.2); estados provisionales de fases 2–4 como tabla de mapeo (§7.1); `salida/firma/` no existe como código (§10.3); huecos de la API en `docs/HUECOS.md`, no en `salida/` (§10.4).

Lo que sigue **abierto y es de Billy** (no se decide aquí): proveedor LLM y condiciones de datos, umbral de activación de agentes, vía del perfil Modificación (`API-09`), aprobación de `cabecera_v1.yaml` y del diff v1.2, familias `R-CAB` / `R-GRP` / `R-EXP` / `R-XCK` / `R-REQ` como diseño, Expediente Builder en Sprint 4, regla de vigencia de versiones de ficha (validar con normativa/verificador). Ver `CLAUDE.md` §6 y `docs/06`.

---

## 15. Fuentes

- `docs/historico/07-backend-y-motor-de-reglas_v1.0.md` (18/09/2026) — principios 1–7, instrucciones, procesos P0–P9, sobre de evento, consolidación, agentes, salida, seguridad.
- `docs/historico/11-backend-funcionalidades-y-motor-de-reglas_v1.0.md` (18/09/2026) — §3 (principios 8–10, modelo canónico, cuatro niveles de estado, catálogo de eventos, mapa N1–N9 / S1–S8, integridad, transporte/firma, P7/P9 con tres orígenes, tenencia) y §4 (funcionalidades F-01..F-23).
- `docs/00-instrucciones-de-entrada.md` — reglas de oro, glosario, roles A0–A9 y contrato común de agentes.
- `docs/01-estructura-del-repositorio.md` v1.0 — rutas de `engine/`, `agentes/`, `salida/`, `mapping/`; decisión `Actuacion` sin alias.
- `docs/02-plataforma-oficial.md` — actores, fases, cabecera, estados de fase 1, frontera de firma.
- `docs/HUECOS.md` — `TODO(API-01..12)`.
- `spec/IND240_v1.1.yaml` — 26 reglas, variables, fórmula, `INT-01..07`.
- Presentación "Plataforma electrónica del sistema de CAE" (OMIE/MIBGAS, 30/06/2026) y página "Plataforma CAE" de MITECO consultada el 18/09/2026.
- Real Decreto 36/2023; Orden TED/815/2023; Reglamento (UE) 2019/1781 — enlaces en `docs/00`.

---

*Mantener vivo: las marcas de estado de §3 y §13 cambian en la misma sesión en que cambia el código (`/contrastar`); una decisión de §14 que se revise pasa por ADR en `docs/decisiones/`; los estados provisionales de §7.1 y los huecos de §10.4 se actualizan con el diccionario de la API oficial y con la respuesta sobre el perfil Modificación.*
