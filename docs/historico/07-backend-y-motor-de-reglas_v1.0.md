> **SUPERADO.** Documento histórico (v1.0, 18/09/2026). Fue sustituido por `11-backend-funcionalidades-y-motor-de-reglas` v1.0 y, en la consolidación del 18/09/2026, ambos se fundieron en `docs/03-arquitectura-backend.md` y `docs/04-motor-de-reglas-y-specs.md`. Se conserva por la historia de decisiones. No construir sobre él.

# CAE Engine — Instrucciones del backend y del motor de reglas

**Versión 1.0 · 18/09/2026 · Proyecto CAE (Billy)**

Documento complementario a `00-instrucciones-de-entrada.md` (esencia, reglas de oro, agentes) y a `06-entorno-tecnologico-y-competitivo.md` (plataforma oficial y competencia). Este documento dice **cómo se construye el backend**: módulos, contratos, motor de reglas, salida hacia el delegado y la plataforma, y evaluación.

Sirve para dos lectores: una persona que entra a desarrollar y una sesión de IA (p. ej. Claude Code) que va a escribir código del proyecto.

**Convención de estado.** Cada pieza lleva una de estas marcas:

| Marca | Significado |
|---|---|
| `EXISTE` | Implementado en el Engine 0.1 (Sprints 1 y 2) |
| `PARCIAL` | Existe una parte; se indica cuál |
| `NUEVO` | Diseño aprobado el 18/09/2026, sin implementar |
| `A CONFIRMAR` | Afirmación sobre el código que no se ha contrastado con el repositorio; comprobar antes de construir encima |

**Precedencia.** BOE → catálogo MITECO → `spec/*.yaml` → `00` → este documento → código. Si este documento contradice una regla de oro del `00`, este documento está mal.

---

## 0. Instrucciones para quien escribe código (persona o IA)

Obligatorio, sin excepciones:

1. **Ningún LLM ejecuta aritmética ni decide si una regla se cumple.** Los agentes proponen valores con cita; el núcleo decide.
2. **Nada de `eval()` ni ejecución de cadenas arbitrarias.** Fórmulas y lógica de reglas se interpretan con un parser propio de lista blanca (§6.4 y §7).
3. **Aritmética con `Decimal`**, nunca `float`, en todo lo que toque el ahorro.
4. **No inventar campos de la API oficial.** A 18/09/2026 no hay diccionario público (§9.4). Lo desconocido se deja como hueco explícito en el contrato, no se rellena con suposiciones.
5. **Añadir una ficha es añadir YAML** (spec + mapeo de salida). Si hace falta un `if ficha == ...` en el código, el diseño está mal.
6. **El núcleo no importa nada de los adaptadores ni de los agentes.** Las dependencias apuntan hacia dentro.
7. **El sistema debe llegar a un estado sin ningún LLM disponible** (modo degradado = Engine 0.1). Un agente caído o caro nunca bloquea un expediente.
8. **Todo cambio pasa el banco de pruebas** (61 tests actuales + los de §10) antes de entrar.
9. **Nunca custodiar certificados digitales de terceros.** La firma ocurre en casa del delegado (§9.3).
10. **Datos reales: anonimizados** antes de entrar en pruebas; nada de datos de cliente en documentos compartibles.
11. **Lo que la norma no cierra se marca como `INT-xx`**, con criterio, alternativa e impacto. Nunca se resuelve en silencio dentro del código.
12. **Todo cambio normativo pasa por revisión humana** antes de tocar spec o motor.

---

## 1. Principios de arquitectura

| # | Principio | Consecuencia práctica |
|---|---|---|
| 1 | Núcleo determinista, agentes en la periferia | Reproducibilidad: misma entrada + misma versión = mismo resultado |
| 2 | Modelo canónico propio, independiente de cualquier destino | Un cambio en la API oficial toca un fichero de mapeo, no el motor |
| 3 | Puertos y adaptadores en la salida | Varios destinos sobre el mismo expediente: paquete para el delegado, API, simulador |
| 4 | Log de eventos inmutable, solo-añadir, encadenado por hash | Auditoría, reproducción y regresión automática con expedientes pasados |
| 5 | Workflow primero, agentes como funciones tipadas | El orquestador es una máquina de estados, no un LLM que decide el siguiente paso |
| 6 | Configuración antes que código | Fichas, reglas, mapeos y checklists viven en YAML versionado |
| 7 | Firma y transporte separados del constructor del payload | Operamos con la norma vigente (vía delegado) y quedamos listos para el perfil de colaborador si se aprueba |

---

## 2. Mapa de módulos

### 2.1 Núcleo determinista

| ID | Módulo | Función | Estado |
|---|---|---|---|
| N1 | Spec Registry | Carga fichas YAML versionadas; resuelve qué versión aplica a una actuación por fecha | `PARCIAL`: una ficha (`spec/IND240_v1.1.yaml`); sin gestión de vigencias ni coeficientes (art. 18 bis) |
| N2 | Rules Engine | Evalúa las reglas de la ficha y fija el veredicto | `EXISTE` (`engine/reglas.py`) |
| N3 | Calculation Engine + tablas | Fórmula leída del YAML, `Decimal`, traza; tabla cuadro 6 Reg. (UE) 2019/1781 | `EXISTE` (`engine/calculo.py`, `data/`) |
| N4 | Evidence Store | Grafo de evidencias con las tres capas por dato | `PARCIAL`: en memoria; falta persistencia |
| N5 | Integridad | SHA-256 por fichero y manifiesto | `PARCIAL`: hoy solo el registro SCADA (`engine/registro_xlsx.py`) |
| N6 | Máquina de estados | Ciclo de vida del expediente y mapeo a los estados de la plataforma oficial | `NUEVO` |
| N7 | Modelo canónico de expediente | Esquema interno estable y versionado | `NUEVO` |
| N8 | Log de eventos | Registro solo-añadir encadenado por hash; permite replay | `NUEVO` |

### 2.2 Servicios

| ID | Módulo | Función | Estado |
|---|---|---|---|
| S1 | Ingesta | PDF nativo, OCR, xlsx, EXIF, separación de PDF combinados, clasificación léxica | `EXISTE` (`engine/ingesta.py`) |
| S2 | Agent Runtime | El contrato común de agentes hecho código (§8) | `NUEVO` |
| S3 | Orquestador | Workflow duradero por eventos con tareas humanas | `PARCIAL`: `engine/motor.py` lineal y síncrono |
| S4 | Consola de revisión | Cola de escalados, conflictos y correcciones del profesional | `NUEVO` |
| S5 | Salida | Puerto de salida + adaptadores (§9) | `NUEVO` · prioridad Sprint 3 |
| S6 | Evaluación | Banco de pruebas, fábrica de casos, métricas por agente (§10) | `PARCIAL`: 7 casos, 61 tests, `evaluar_casos.py` |
| S7 | Seguridad y tenencia | Aislamiento por delegado, enmascarado, anonimización (§11) | `NUEVO` |

### 2.3 Estructura de repositorio propuesta

Lo existente no se mueve; lo nuevo se añade al lado.

```
spec/                     Fichas como configuración                          EXISTE
mapping/                  Mapeo modelo canónico → destino, por ficha         NUEVO
data/                     Tablas de referencia                               EXISTE
engine/
  ingesta.py extraccion.py reglas.py calculo.py registro_xlsx.py
  motor.py informe.py cli.py                                                 EXISTE
  modelo/                 Modelo canónico (N7) y validación de esquema       NUEVO
  eventos/                Log de eventos, hash, replay (N8)                  NUEVO
  estados.py              Máquina de estados (N6)                            NUEVO
  expresiones.py          Parser de lista blanca para `logica` y `formula`   A CONFIRMAR (puede existir parte en calculo.py)
agentes/
  runtime/                Esquema, reintentos, prompts, router, traza (S2)   NUEVO
  lector/ analista/ redactor/                                                NUEVO
salida/
  puerto.py               Interfaz común de salida                           NUEVO
  handoff/ api_oficial/ simulador/                                           NUEVO
  firmante/               Componente desplegable en casa del delegado        NUEVO
generator/                Generador sintético → fábrica de casos             PARCIAL
tests/                                                                        EXISTE
```

---

## 3. Procesos del motor

Patrón común: **la regla detecta y decide; el agente explica y propone.**

| # | Proceso | Rol de agente | Pieza que decide | Evento de salida |
|---|---|---|---|---|
| P0 | Admisión: alta, partes, delegado asociado | — | N6 | `ExpedienteAbierto` |
| P1 | Ingesta y clasificación | A1 (lector) | S1, N5 | `DocumentoRegistrado`, `DocumentoClasificado` |
| P2 | Extracción de evidencias | A2 (lector), doble extracción | N7 (validación), N4 | `EvidenciaPropuesta` |
| P3 | Ficha y ámbito | A3 (analista) propone ficha | N1 + reglas `R-AMB` | `FichaAsignada`, `VeredictoEmitido` |
| P4 | Consolidación y cruce | A4 (analista) explica el conflicto | Reglas `R-CON` + consolidador (§6.6) | `DatoConsolidado`, `ConflictoDetectado` |
| P5 | Cálculo | Ninguno, por diseño | N3 | `CalculoRealizado` |
| P6 | Pre-revisión | A8 (analista), **solo avisos** | Checklist en YAML | `ObservacionRegistrada` |
| P7 | Subsanación | A5, A7 (redactor) | Reglas falladas → carencias | `SubsanacionSolicitada`; vuelve a P1 |
| P8 | Empaquetado y envío | Ninguno | S5 + control cruzado del cálculo | `PayloadConstruido`, `EntregadoADelegado` |
| P9 | Seguimiento post-envío | A9 (redactor) interpreta rectificaciones | N6 (mapeo de estados) | `EstadoPlataformaRecibido`, `RectificacionInterpretada` |

**Decisiones registradas el 18/09/2026:** A8 empieza emitiendo solo avisos (no altera el veredicto); P9 entra en el Sprint 3 junto con P8.

---

## 4. Modelo canónico de expediente (N7) — `NUEVO`

Esquema propio, versionado (`modelo_version`), validado con JSON Schema. Es lo único que consumen los adaptadores de salida.

```
Expediente
├─ id, modelo_version, tenant (delegado), creado_en
├─ ficha: { codigo, version_ficha, version_spec, hash_spec }
├─ partes: titular, solicitante (delegado/obligado), instalador
├─ documentos[]: { doc_id, tipo, confianza_tipo, sha256, paginas, origen, metodo_lectura }
├─ unidades[]                      (en IND240, una por motor; clave de unión: nº de serie)
│   └─ variables{}: nombre → DatoConsolidado
├─ variables_expediente{}: nombre → DatoConsolidado
├─ evaluacion: { reglas[], veredicto, hash_reglas, evaluado_en }
├─ calculo: { por_unidad[], total, traza[], provisional: bool }
├─ observaciones[]                 (avisos de A8 y de reglas AVISO)
├─ interpretaciones_aplicadas[]    (INT-xx que han influido en el resultado)
└─ ciclo: { estado_ciclo, estado_plataforma?, historial → log de eventos }
```

**Tres capas por dato** (regla de oro 3). Un `DatoConsolidado` guarda siempre:

| Capa | Contenido |
|---|---|
| 1. Documento | `evidencias[]`: `{doc_id, pagina, texto_literal, metodo (tabla / regex / ocr / llm), confianza, extractor_version}` |
| 2. Interpretación | `valor_normalizado`, `unidad`, `tipo_evidencia` (`demostrado` / `declarado` / `derivado`), `fuente_primaria`, `interpretacion` (INT-xx si aplica) |
| 3. Cálculo | `valor_consumido` (`Decimal` como cadena), o `null` si hay conflicto |

Un dato sin al menos una evidencia con cita literal **no entra** en el expediente.

---

## 5. Log de eventos (N8) y máquina de estados (N6) — `NUEVO`

### 5.1 Sobre de evento

```json
{
  "evento_id": "uuid",
  "expediente_id": "EXP-...",
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
- **El estado del expediente es una proyección del log.** Se puede reconstruir desde cero.
- **Replay**: cualquier expediente pasado se puede volver a ejecutar contra una versión nueva de spec, reglas o agente. Cada expediente procesado es, por tanto, una prueba de regresión.
- **JSON canónico**: claves ordenadas, UTF-8, sin espacios, `Decimal` como cadena. Sin esto el hash no es reproducible.
- Los eventos de agente incluyen modelo, versión de prompt, coste y latencia (contrato de agentes, punto 6).

### 5.2 Tres estados distintos, no mezclar

| Concepto | Valores | Quién lo fija |
|---|---|---|
| **Veredicto** (calidad del expediente) | `NO_ELEGIBLE`, `BLOQUEADO`, `SUBSANABLE`, `PREVALIDADO` | Rules Engine. `EXISTE` |
| **Estado de ciclo** (dónde está el trabajo) | Ver §5.3 | Máquina de estados. `NUEVO` |
| **Estado de plataforma** (espejo del oficial) | `BORRADOR`, `COMPLETA`, `ENVIADA_A_VERIFICACION`, `PDTE_RECTIFICACION_VER`, `VERIFICACION_EN_PROCESO`, `VERIFICADA_FAVORABLE`, `VERIFICADA_DESFAVORABLE`, `NO_PUEDE_EMITIR_DICTAMEN` | La plataforma oficial; nosotros solo lo reflejamos |

Ningún veredicto significa CAE garantizado.

### 5.3 Estado de ciclo (propuesta)

```
ABIERTO → EN_PROCESO → EVALUADO ─┬─► PENDIENTE_SUBSANACION ──(nuevos documentos)──► EN_PROCESO
                                 ├─► EN_REVISION_HUMANA ─────► EVALUADO
                                 ├─► DESCARTADO                (NO_ELEGIBLE confirmado)
                                 └─► LISTO_PARA_ENVIO ► ENTREGADO_A_DELEGADO ► EN_PLATAFORMA ► CERRADO
```

- Solo un expediente `PREVALIDADO` y revisado por un humano puede pasar a `LISTO_PARA_ENVIO`.
- `EN_PLATAFORMA` + `PDTE_RECTIFICACION_VER` reabre `PENDIENTE_SUBSANACION` con origen `verificador` (lo interpreta A9).
- Presupuesto de pasos y de coste por expediente; agotado, pasa a `EN_REVISION_HUMANA`.

---

## 6. Motor de reglas (N2)

### 6.1 Qué es y qué no es

Evalúa reglas declaradas en la ficha YAML sobre el modelo canónico y emite un veredicto. No lee documentos, no llama a modelos, no tiene estado propio. Es una función pura:

```
evaluar(expediente_canonico, spec, tablas) → { resultados_por_regla[], veredicto, hash_reglas }
```

### 6.2 Anatomía de una regla

Campos actuales (`EXISTE` en `spec/IND240_v1.1.yaml`):

```yaml
- id: R-CON-01
  descripcion: "PM coincide en todas las fuentes"
  logica: "unique(PM.valores_por_fuente)"
  severidad: BLOQUEANTE_DATOS
  referencia: SRC-FICHA §3
  interpretacion: INT-xx        # opcional
```

Campos que se añaden (`NUEVO`, retrocompatibles; si faltan, se aplican los valores por defecto):

```yaml
  fase: consistencia            # ambito | consistencia | post_calculo | resto
  nivel: unidad                 # expediente | unidad (p. ej. motor)
  subsanacion:
    mensaje: "La potencia del motor no coincide entre la ficha técnica y el certificado."
    documentos: [ficha_tecnica_motor, certificado_instalador]
  vigencia: { desde: "2025-05-07", hasta: null }    # solo si la regla cambia entre versiones
```

`subsanacion` es lo que consume A5 para redactar la petición al cliente: el agente redacta, pero **qué falta** lo dice la regla.

### 6.3 Severidades y veredicto — `EXISTE`

| Severidad | Efecto si falla | ¿Calcula? |
|---|---|---|
| `BLOQUEANTE_AMBITO` | `NO_ELEGIBLE` | No |
| `BLOQUEANTE_DATOS` | `BLOQUEADO` | No |
| `SUBSANABLE` | `SUBSANABLE` | Sí, marcado como provisional |
| `AVISO` | No cambia el veredicto; requiere revisión humana | Sí |

Orden de prioridad del veredicto: `NO_ELEGIBLE` > `BLOQUEADO` > `SUBSANABLE` > `PREVALIDADO`.

### 6.4 Orden de evaluación por fases

El principio ya está implementado (ámbito y consistencia → cálculo → resto). La asignación regla a regla es `A CONFIRMAR` contra `engine/reglas.py`.

| Fase | Reglas IND240 | Si falla |
|---|---|---|
| 1. Ámbito | `R-AMB-01..03` | `NO_ELEGIBLE`. Se detiene: no se calcula aunque ficha o convenio declaren ahorro (caso D) |
| 2. Consistencia previa | `R-CON-01, 02, 03, 04, 05, 07` · `R-TMP-01` · `R-CAL-01` · `R-CAL-04` · `R-CAL-02` (aviso) | `BLOQUEADO`. No se elige valor ni se calcula (caso C) |
| 3. Cálculo | — (N3) | — |
| 4. Posterior al cálculo | `R-CAL-03` (controles físicos) · `R-CON-06` (convenio vs. AETOTAL) | `R-CAL-03` bloquea y **retira** el resultado; `R-CON-06` es subsanable |
| 5. Resto | `R-DOC-01..05` · `R-EVD-01..04` · `R-TMP-02, 03` | `SUBSANABLE` o aviso |

Total: 26 reglas.

### 6.5 Resultado de una regla: tres valores

| Resultado | Cuándo |
|---|---|
| `CUMPLE` | La condición es verdadera |
| `FALLA` | La condición es falsa |
| `NO_EVALUABLE` | Falta algún dato necesario para evaluarla |

**Criterio:** una regla `NO_EVALUABLE` no bloquea por sí misma; la carencia debe quedar recogida por la regla documental o de evidencia correspondiente. Es coherente con el caso B del banco de pruebas: sin registro de 30 días, `R-CON-03` no puede evaluarse (no hay N2 derivado) y el expediente resulta `SUBSANABLE` por `R-EVD-04`, no `BLOQUEADO`.

Garantía que hay que probar para cada ficha: **toda regla bloqueante que pueda quedar `NO_EVALUABLE` tiene una regla `SUBSANABLE` que detecta la carencia que la causa.** Si no, un hueco de datos pasaría inadvertido. La formalización de los tres valores es `A CONFIRMAR` contra el comportamiento actual del código.

### 6.6 Consolidación de evidencias (antes de las reglas)

Cómo se pasa de N evidencias a un `valor_consumido`:

1. **Agrupar** evidencias por variable y por unidad (clave de unión: números de serie; el registro SCADA se vincula por SHA-256, no por nombre de fichero). `EXISTE`
2. **Normalizar** según `cruce`: `exacto` o `normalizado` (mayúsculas, puntuación, "S.L." vs "SL"). `EXISTE`
3. **Comparar** todas las fuentes presentes; aplicar `tolerancia_cruce_*` cuando la spec la defina. `EXISTE`
4. **OCR**: evidencias de foto o escaneo entran con confianza 0,75. Si discrepan de una fuente fiable no bloquean: se marcan como posible error de OCR. `EXISTE`
5. **Conflicto entre fuentes fiables**: `valor_consumido = null`, evento `ConflictoDetectado` con las dos evidencias. El motor **no elige** (regla de oro 6). `EXISTE`
6. **Doble extracción** (`NUEVO`): extractor de reglas y extractor LLM sobre el mismo documento. Coinciden → confianza alta. Discrepan → no es un conflicto documental, es un desacuerdo de lectura: se escala a revisión humana y se registra como métrica.
7. **Declarado ≠ demostrado**: si una variable exige `derivado` o `demostrado` y solo hay valor declarado, el dato entra marcado como tal y lo recoge la regla de evidencia (`R-EVD-04`).

### 6.7 Lenguaje de expresiones

El campo `logica` usa un vocabulario cerrado. Funciones que ya aparecen en la spec: `unique`, `exists`, `all`, `count`, `abs`, `min`, `sum`, `sha256`, `presente`, comparadores, `in`, `and / or / not`, `for each`, aritmética de fechas (`+ 3 años`).

- Se interpreta con un parser de lista blanca. **Nunca `eval()`**.
- Una función no reconocida es error de carga de la spec, no de ejecución: la ficha no se activa.
- `A CONFIRMAR`: si hoy `logica` es descriptiva y cada regla está implementada en Python por su `id`, el objetivo de la versión 0.2 es que la ejecutable sea la del YAML. Hasta entonces, **cada regla implementada en código debe tener un test que verifique que hace lo que dice su `logica`**.

### 6.8 Avisos y observaciones

Dos canales que **nunca** alteran el veredicto:

- Reglas con severidad `AVISO` (p. ej. `R-TMP-03`, `R-CAL-02`).
- Observaciones de A8 (revisor sombra): cada una con cita, categoría y confianza. Van a `observaciones[]` y a la consola de revisión.

Si con datos reales se demuestra que una observación de A8 anticipa rectificaciones del verificador, se propone convertirla en regla determinista o en ítem de checklist del YAML. Ese es el camino de promoción: **de juicio a norma, nunca al revés.**

### 6.9 Interpretaciones pendientes

Toda regla o derivación que dependa de un `INT-xx` lo declara en la spec. El informe y el modelo canónico listan las interpretaciones que han influido en el resultado. Abiertas a 18/09/2026: `INT-01` (base de p, impacto medio), `INT-03`, `INT-04`, `INT-05` (impacto alto), `INT-02`, `INT-06`, `INT-07` (bajo). Cerrar una interpretación es un cambio normativo: revisión humana y nueva `version_spec`.

### 6.10 Versionado

- Cada evaluación registra `version_ficha`, `version_spec` y `hash_reglas` (SHA-256 del bloque de reglas canonizado).
- La versión de ficha aplicable depende de las fechas de la actuación. La regla exacta de vigencia es `A CONFIRMAR` con la normativa y, en su caso, con verificador; N1 debe soportar varias versiones simultáneas de una misma ficha.
- Los coeficientes de corrección (art. 18 bis del proyecto de modificación del RD) se modelarán como tabla con vigencia cuando existan. Hoy no se implementan.

### 6.11 Checklist para añadir una ficha

1. Leer la ficha en BOE / catálogo. Anotar versión y fecha.
2. Escribir `spec/<FICHA>_v<x>.yaml`: ámbito, exclusiones, variables (nivel, evidencia, fuentes, cruce), tablas, cálculo, documentación, reglas con `fase` y `subsanacion`, estados, interpretaciones.
3. Todo lo que la ficha no cierre → `INT-xx`. No resolver en silencio.
4. Tablas de referencia en `data/`, con fuente y verificación.
5. Escribir `mapping/<FICHA>.handoff.yaml` (y el de API cuando exista diccionario).
6. Generar paquete sintético: como mínimo un caso por veredicto (prevalidado, subsanable, bloqueado, no elegible) y uno desordenado.
7. Tests: por cada regla, un caso que cumple y uno que falla; garantía de §6.5; propiedades metamórficas de §10.
8. Revisión humana de la spec antes de activarla.
9. **Cero cambios en `engine/`.** Si hacen falta, es un defecto del marco: se arregla en el marco, no con una excepción para la ficha.

---

## 7. Motor de cálculo (N3) — `EXISTE`

- Fórmula leída del YAML: `PM * (1 - (N2 / N1) ** 3) * (1 - p) * h` por unidad; `sum(AEM)` para el total.
- `Decimal` de extremo a extremo; sin redondeo interno; `AETOTAL` truncado a kWh entero (`INT-06`).
- Precondiciones: `N2 < N1`, `0 < h <= 8760`, ninguna regla bloqueante fallida.
- `p` sale **siempre** de la tabla de referencia (cuadro 6), nunca de la ficha técnica del variador (`R-CAL-04`).
- `h = min(h_antes, h_despues)`.
- Controles físicos: `AEM <= PM * h`; `P_prom <= PM`.
- Traza: cada paso intermedio queda en `calculo.traza[]`.
- Valor de referencia para regresión: caso A = 305.829,6 kWh/año → 305.829 CAE.

**Control cruzado con la plataforma oficial** (`NUEVO`). La plataforma calculará lo "tratable" de cada ficha. Nuestro cálculo pasa a ser control previo al envío: si cuando haya sandbox el valor de la plataforma difiere del nuestro, se emite `DiscrepanciaCalculoPlataforma` y **no se envía** hasta que un humano lo resuelva. Cada discrepancia apunta a un bug nuestro, a un `INT-xx` mal resuelto o a un criterio oficial distinto: las tres cosas valen mucho.

---

## 8. Agentes (S2) — `NUEVO`

### 8.1 Tres capacidades sobre un único runtime

Los roles lógicos A0–A9 se mantienen; se despliegan así:

| Capacidad | Roles | Entrada | Salida |
|---|---|---|---|
| **Lector** | A1 Clasificador · A2 Extractor (variantes texto y visión) | Fichero / documento + variables que pide la ficha | Tipo + confianza · valor, unidad, página, texto literal, confianza |
| **Analista** | A3 Emparejador · A4 Auditor de inconsistencias · A8 Revisor sombra | Grafo de evidencias, catálogo, checklist | Ficha candidata · hipótesis de conflicto · observaciones (solo avisos) |
| **Redactor** | A5 Subsanaciones · A7 Informes · A9 Intérprete de rectificaciones | Reglas falladas · expediente resuelto · comentario del verificador | Texto para el cliente · informe · rectificación mapeada a reglas y documentos |

A0 (coordinador) es código: la máquina de estados. A6 (vigía normativo) trabaja fuera de línea y solo propone diffs sobre el YAML.

### 8.2 Lo que implementa el runtime

El contrato común del `00` §7.3, hecho código una sola vez:

1. Validación de salida contra JSON Schema; si no valida, reintento acotado; si sigue sin validar, `no_lo_se`.
2. Cita obligatoria; un valor sin cita se descarta antes de llegar al Evidence Store.
3. Confianza declarada; `no_lo_se` es una salida legítima.
4. Rechazo de cualquier salida con resultado calculado.
5. Registro de prompts versionado; cambiar un prompt obliga a reevaluar.
6. Traza: modelo, versión de prompt, entrada, salida, coste, latencia → evento.
7. Escalado a humano por umbral de confianza o conflicto crítico.
8. Router de modelo por tarea y presupuesto de pasos y coste por expediente.

### 8.3 Reglas de activación

- **Fuera del camino crítico**: con todos los agentes apagados, el Engine sigue produciendo veredicto con el extractor por reglas.
- **Puerta de activación**: un rol solo entra en producción con conjunto de evaluación y línea base propios. El umbral numérico está **por definir**.
- A8 no se llama "verificador" en ningún texto de producto (no somos verificador, `00` §2).

---

## 9. Salida (S5) — `NUEVO`

### 9.1 Puerto de salida

```
construir(expediente_canonico, mapping) → Paquete { payload, manifiesto, adjuntos[] }
entregar(paquete)                       → Acuse
consultar_estado(referencia)            → EstadoPlataforma
```

El mapeo modelo canónico → destino es **declarativo y por ficha** (`mapping/IND240.<destino>.yaml`).

### 9.2 Adaptadores

| Adaptador | Para qué | Dependencia externa | Cuándo |
|---|---|---|---|
| **Handoff** | Carpeta ordenada + manifiesto + informe de prevalidación, para que el delegado presente por el cauce vigente | Ninguna | Primero |
| **Simulador** | Reproduce lo conocido de la plataforma: los 8 estados, manifiesto con hash, validación de esquema y de firma; permite desarrollar P8 y P9 sin sandbox | Ninguna | Primero |
| **API oficial** | Envío y consulta reales | Diccionario de API + delegado partner con certificado | Cuando existan ambos |

### 9.3 Firma en casa del delegado

El conector se parte en dos:

- **Constructor** (nuestro): genera payload y manifiesto sin firmar.
- **Firmante + transporte** (`salida/firmante/`): componente pequeño desplegable en la infraestructura del delegado, con su certificado en su almacén de claves. Firma, envía y nos reenvía los cambios de estado como eventos.

Nunca custodiamos certificados de terceros. Si la norma llega a contemplar un perfil de colaborador (alegación al art. 20.3, `00` §5.6), se añade un adaptador directo limitado a borradores; el resto no cambia.

### 9.4 Lo que se sabe y lo que no de la API oficial

Conocido (presentación OMIE/MIBGAS del 30/06/2026, ver `06` §1): acceso web o API; peticiones firmadas con certificado digital; validación de esquema, firma, certificado y permisos; adjuntos con manifiesto de ficheros y hash, carga asíncrona; estructuras JSON; notificaciones y tareas consultables; entorno de pruebas previsto.

No conocido a 18/09/2026: endpoints, esquemas JSON, autenticación concreta, formato del manifiesto. Comprobado ese día en `miteco.gob.es/es/energia/eficiencia/cae/plataformacae.html`: la plataforma figura "en fase de desarrollo", el único documento técnico publicado es la presentación del 30/06/2026 y la gestión sigue por los cauces habituales hasta la puesta en marcha.

**Regla:** el simulador implementa solo lo conocido. Cada hueco es un `TODO(API-xx)` enumerado en `salida/simulador/HUECOS.md`, no una suposición en el código.

### 9.5 Manifiesto interno (el nuestro, no el oficial)

```json
{
  "expediente_id": "EXP-...",
  "modelo_version": "1.0",
  "generado_en": "2026-09-18T10:40:00Z",
  "ficha": { "codigo": "IND240", "version_ficha": "1.1", "hash_spec": "…" },
  "ficheros": [
    { "ruta": "03_factura/FAC-001.pdf", "tipo": "factura", "sha256": "…", "bytes": 182034 }
  ],
  "hash_log_eventos": "…",
  "hash_manifiesto": "…"
}
```

### 9.6 Seguimiento (P9)

- Los estados de plataforma llegan como `EstadoPlataformaRecibido` (del firmante del delegado, o del simulador).
- `PDTE_RECTIFICACION_VER` → A9 lee el comentario del verificador y propone `{regla_id | documento, texto_literal, confianza}`. Un humano confirma. El resultado alimenta P7 y, anonimizado, el banco de pruebas.
- `VERIFICADA_FAVORABLE / DESFAVORABLE / NO_PUEDE_EMITIR_DICTAMEN` → cierre, con etiqueta de resultado para evaluación.

---

## 10. Evaluación (S6)

Los 7 casos sintéticos demuestran que la cadena funciona, no que acierte fuera del laboratorio. Cinco fuentes de verdad, por orden de disponibilidad:

| Fuente | Qué aporta | Necesita |
|---|---|---|
| Banco actual (7 casos, 61 tests) | Regresión del núcleo | `EXISTE` |
| **Fábrica de casos** | El mismo modelo de datos renderizado en plantillas, vocabularios y calidades de escaneo no vistas; conjunto reservado que **nunca** se usa para ajustar | Ampliar `generator/` |
| **Documentos reales públicos** | Fichas técnicas de fabricantes de motores y variadores; formato de exportación del registrador de los variadores Schneider Altivar (`06` §3.4) | Recopilación; sin datos de cliente |
| **Pruebas metamórficas** | Propiedades sin ground truth (abajo) | Solo código |
| **Modo sombra** con el delegado partner | Engine en paralelo al proceso manual; las rectificaciones reales son las etiquetas | Partner |

Propiedades metamórficas mínimas:

- Renombrar, reordenar, girar o combinar ficheros **no cambia** veredicto ni ahorro (generaliza el caso G).
- Alterar `PM` en un solo documento → `BLOQUEADO` (generaliza el caso C).
- Quitar un documento obligatorio → nunca mejora el veredicto.
- Cambiar el equipo accionado a uno excluido → `NO_ELEGIBLE`, aunque se declare ahorro (generaliza el caso D).
- Añadir un documento irrelevante → no cambia nada.
- Duplicar un documento → no cambia nada.

Métricas por agente (`00` §7.5): acierto frente a ground truth y coste por expediente. Se añade: **tasa de desacuerdo** entre extractor de reglas y extractor LLM.

---

## 11. Seguridad y datos (S7)

- Aislamiento por tenant (delegado): datos, claves y logs separados. Requisito para marca blanca.
- **Antes de llamar a un LLM con documentación real**: enmascarar identificadores (NIF, razón social, direcciones, referencias catastrales) cuando la tarea no los necesite; región de proceso y no-entrenamiento con los datos como requisito contractual con el proveedor. A cerrar **antes** del primer expediente real.
- Anonimización de expedientes reales para el banco de pruebas: detección asistida, validación humana obligatoria.
- Documentos sintéticos: siempre con la marca "DOCUMENTO SINTÉTICO – SOLO PRUEBAS".
- Sin certificados de terceros en nuestra infraestructura (§9.3).

---

## 12. Orden de construcción — Sprint 3

Criterio: los pasos 1 a 4 no dependen de nadie externo; el 5 se engancha cuando llegue lo que hoy no controlamos.

| # | Entregable | Hecho cuando… |
|---|---|---|
| 1 | Modelo canónico (N7) + log de eventos (N8) + máquina de estados (N6) | Los 7 casos producen modelo canónico válido; el replay del log reproduce veredicto y ahorro bit a bit; 61 tests siguen en verde |
| 2 | Puerto de salida + adaptador handoff + simulador con tests de contrato | El caso A genera paquete con manifiesto verificable; el simulador lo acepta y rechaza uno con hash alterado |
| 3 | P9 contra el simulador + A9 sobre rectificaciones sintéticas | Un `PDTE_RECTIFICACION_VER` simulado reabre subsanación con la regla correcta identificada |
| 4 | Agent Runtime + lector (A2 LLM) con doble extracción | Evaluado sobre fábrica de casos (conjunto reservado) y metamórficas; modo degradado comprobado apagando el LLM |
| 5 | Conector API oficial · firmante en delegado · modo sombra | Depende de: diccionario de API y delegado partner |

En paralelo, fuera del código: delegado partner; petición de los modelos de intercambio a `consultas-plataforma@registrocae.es`; sesión con verificador para `INT-01/03/04/05`.

---

## 13. Decisiones y puntos abiertos

**Tomadas (18/09/2026)**

- A8 (revisor sombra) emite solo avisos; no altera el veredicto.
- P9 (seguimiento post-envío) entra en el Sprint 3 junto con el envío.
- Orden de construcción: el de §12.
- Sprint 3 priorizado hacia la integración con la plataforma oficial (decisión del 17/09/2026).

**Abiertas**

| Asunto | Quién |
|---|---|
| Umbral de activación de un rol de agente en producción (§8.3) | Billy |
| Delegado partner: perfil y candidato | Billy |
| Proveedor de LLM y condiciones de tratamiento de datos (§11) | Billy |
| Regla de vigencia de versiones de ficha (§6.10) | Validar con normativa / verificador |
| `INT-01`, `INT-03`, `INT-04`, `INT-05` | Sesión con verificador |
| Puntos `A CONFIRMAR` de este documento | Contrastar con el repositorio en la primera sesión de desarrollo |

---

## 14. Fuentes

- `00-instrucciones-de-entrada.md` v1.1 — reglas de oro, agentes, contrato común.
- `06-entorno-tecnologico-y-competitivo.md` v1.0 — plataforma oficial, estados, API, competencia.
- `spec/IND240_v1.1.yaml` y `README` de los Sprints 1 y 2 — reglas, fases, decisiones de diseño y casos de prueba.
- Página "Plataforma CAE" de MITECO, consultada el 18/09/2026 — estado de desarrollo y documentación publicada.
- Real Decreto 36/2023, Orden TED/815/2023, Reglamento (UE) 2019/1781 — ver enlaces en `00` §10.
