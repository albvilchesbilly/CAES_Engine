# CAE Engine — Motor de reglas, cálculo y specs

**Versión 1.0 · 18/09/2026 · Proyecto CAE (Billy)**

Este documento se lee **antes de tocar** `engine/reglas.py`, `engine/expresiones.py`, `engine/calculo.py`, `engine/spec_registry.py` o cualquier `spec/*.yaml`. Dice cómo se declara una regla, cómo se evalúa, en qué orden, con qué vocabulario, cómo se calcula el ahorro y qué reglas existen, cuáles están propuestas y cuáles no se cargan.

**Qué consolida.** Fusiona el motor de reglas (§6) y el motor de cálculo (§7) de `docs/historico/07-backend-y-motor-de-reglas_v1.0.md` con el motor a tres niveles, las familias nuevas y el Spec Registry (§5 y §3.6) de `docs/historico/11-backend-funcionalidades-y-motor-de-reglas_v1.0.md`. Regla de fusión: cuando los dos discrepan, gana `11`. Lo que era `A CONFIRMAR` en aquellos documentos es aquí una **decisión de diseño de la Fase 0**: no hay repositorio previo contra el que confirmar y el código se reconstruye desde cero con lo que aquí se fija.

**Precedencia cuando dos fuentes discrepan** (de mayor a menor): BOE → plataforma oficial (lo publicado) → catálogo MITECO → `spec/*.yaml` activa → `docs/00` → este documento → código. Si este documento contradice una regla de oro de `docs/00` o la spec activa, este documento está mal y se arregla en la misma sesión.

**Marcas de estado**: `F0` (existió en el Engine 0.1 con diseño probado; se reconstruye en la Fase 0) · `NUEVO` (diseño aprobado o propuesto, nunca implementado) · `EXISTE` / `PARCIAL` (implementado en este repo; al arrancar no hay ninguno) · `NO DOCUMENTADO` (la plataforma oficial no lo ha publicado → `TODO(API-xx)` en `docs/HUECOS.md`). Las marcas se actualizan en la misma sesión en que cambia el código.

**Fuera de este documento**: modelo canónico, log de eventos, máquina de estados, salida, agentes y seguridad viven en `docs/03-arquitectura-backend.md`. Los casos de prueba y el ground truth, en `docs/05-evaluacion-y-banco-de-pruebas.md`. La plataforma oficial, en `docs/02-plataforma-oficial.md`.

---

## 1. Qué es el motor de reglas y qué no es

El motor de reglas (N2, `engine/reglas.py`) evalúa las reglas declaradas en las specs sobre la actuación consolidada y emite un veredicto. **No lee documentos, no llama a modelos, no tiene estado propio.** Es una función pura: misma entrada + misma versión de spec = mismo resultado.

Opera a tres niveles, con una función por nivel:

```
evaluar_actuacion(actuacion, spec_ficha, spec_cabecera, tablas) → { resultados[], veredicto, hash_reglas }
evaluar_grupo(grupo, actuaciones_evaluadas)                     → { resultados[], veredicto_agregado, avisos[] }
evaluar_expediente(expediente, actuaciones_evaluadas)           → { resultados[], valido: bool, avisos_contagio[] }
```

- `evaluar_actuacion` es `F0`. Es la única que se reconstruye en la Fase 0 y la única que produce un **veredicto de calidad** (`NO_ELEGIBLE` … `PREVALIDADO`).
- `evaluar_grupo` y `evaluar_expediente` son `NUEVO` (Sprint 4). No producen veredicto de calidad sino **validez de composición** y **avisos**; la calidad sigue viviendo en cada actuación.

Lo que el motor de reglas **no es**:

- No es el extractor: no decide qué valor tiene una variable. Recibe datos ya consolidados (tres capas por dato, `docs/03` §8) y solo los evalúa.
- No es el motor de cálculo: la fórmula la ejecuta N3 (`engine/calculo.py`, §7). El motor de reglas decide si se puede calcular y qué se hace con el resultado.
- No es un LLM ni lo consulta. Regla de oro 1: la IA lee; el motor calcula. Con todos los agentes apagados el motor sigue produciendo veredicto (modo degradado; test `tests/test_modo_degradado.py`).
- No contiene ninguna regla escrita a mano por ficha. Un `if ficha == "IND240"` en `engine/` es un defecto del marco (regla de oro 4).

Patrón que rige todo el documento: **la regla detecta y decide; el agente explica y propone.**

---

## 2. Spec Registry (N1)

`engine/spec_registry.py` (`F0`, ampliado en `S3`) carga y valida las specs, resuelve qué versión aplica y garantiza invariantes antes de que ninguna regla se evalúe.

### 2.1 Tres tipos de spec

Todos YAML, todos versionados.

| Tipo | Fichero | Contenido | Estado |
|---|---|---|---|
| Ficha | `spec/IND240_v1.1.yaml` | Ámbito, exclusiones, variables, tablas, cálculo, documentación, reglas, estados, interpretaciones | `F0` (única ficha cargable) |
| Cabecera transversal | `spec/propuestas/cabecera_v1.yaml` | Variables comunes a todas las fichas, sus fuentes documentales, tipo de evidencia y reglas `R-CAB-*` | `NUEVO`; pendiente de aprobación de Billy |
| Tablas y coeficientes | `data/*.csv` + `spec/coeficientes_*.yaml` | Tablas de referencia con fuente y **vigencia** (`desde`, `hasta`) | `F0` cuadro 6 (`data/reg_2019_1781_cuadro6.csv`); coeficientes no existen (§14) |

Lo de composición (`R-GRP-*`, `R-EXP-*`, `R-REQ-*`) vive en `spec/propuestas/composicion_v1.yaml` (`NUEVO`, Sprint 4).

### 2.2 `spec/` activa frente a `spec/propuestas/`

- El registro **solo carga `spec/*.yaml`**. **Nunca** carga nada de `spec/propuestas/`; hay un test que lo comprueba (`tests/test_spec_registry.py`).
- Una propuesta se activa **moviéndola** (no copiándola) a `spec/` tras aprobación de Billy, con un ADR en `docs/decisiones/` (regla de oro 9).
- Una ficha = un fichero `<CODIGO>_v<version_ficha>.yaml`. El registro debe poder tener **varias versiones de la misma ficha cargadas a la vez**.

### 2.3 Versionado

Cada evaluación registra, sobre el conjunto de specs usado:

| Campo | Qué es | Dónde se declara |
|---|---|---|
| `version_ficha` | Versión oficial de la ficha (p. ej. `"1.1"`) | `spec.version_ficha` |
| `version_spec` | Versión semver de nuestra lectura de la ficha; cambia con **cualquier** cambio de reglas | `spec.version_spec` (hoy `0.1.0`) |
| `version_cabecera` | Versión de la spec transversal de cabecera | `cabecera_v1.yaml` (`NUEVO`) |
| `version_composicion` | Versión de la spec de composición | `composicion_v1.yaml` (`NUEVO`) |
| `hash_reglas` | SHA-256 del bloque de reglas canonizado (claves ordenadas, UTF-8, sin espacios) del conjunto cargado | Lo calcula el registro al cargar |

Un cambio de `logica`, `severidad` o `fase` en cualquier regla cambia `hash_reglas`; un informe con un `hash_reglas` distinto del actual no es comparable sin replay.

### 2.4 Vigencias

La versión de ficha aplicable a una actuación depende de sus fechas. **La regla exacta de vigencia** (¿fecha de inicio? ¿fecha de fin? ¿fecha de solicitud?) **es una decisión abierta**: se valida con la normativa y, en su caso, con un verificador, y se registra en ADR cuando se cierre. No es una duda de implementación: el registro debe soportar varias versiones simultáneas desde la Fase 0, y la función que elige versión recibe las fechas y aplica el criterio que la spec o el ADR declaren. Mientras no haya más de una versión cargada, el criterio no tiene efecto.

### 2.5 Garantías de carga

Al cargar una spec, el registro falla (la ficha **no se activa**) si:

1. Alguna `logica` o `formula` usa una función o construcción fuera del vocabulario de `engine/expresiones.py` (§6). Error de carga, no de ejecución.
2. Alguna regla carece de `id`, `descripcion`, `logica` o `severidad`, o la severidad no está en el catálogo (§4).
3. **Toda regla bloqueante que pueda quedar `NO_EVALUABLE` tiene una regla `SUBSANABLE` que recoge la carencia que la causa.** Sin esto, un hueco de datos pasaría inadvertido: la bloqueante no falla (no puede evaluarse) y ninguna otra la sustituye. Es un **test automático del registro** para cualquier ficha, no una comprobación manual. La forma de declarar la relación (qué variable necesita cada regla y qué regla `SUBSANABLE` cubre la ausencia de esa variable) es una decisión de diseño de la Fase 0 que se documenta en el ADR de reconstrucción.
4. Una tabla referenciada (`tablas.<ID>.fichero`) no existe en `data/` o no tiene las columnas declaradas.

---

## 3. Anatomía de una regla

### 3.1 Campos reales de `IND240_v1.1.yaml` (`F0`)

Las 26 reglas activas usan exactamente estos campos:

```yaml
- id: R-CON-01
  descripcion: "PM coincide en todas las fuentes"
  logica: "unique(PM.valores_por_fuente)"
  severidad: BLOQUEANTE_DATOS
  referencia: SRC-FICHA §3          # opcional: fuente normativa (id de ficha.fuentes o EXC-xx)
  interpretacion: INT-xx            # opcional: interpretación de la que depende
```

`referencia` e `interpretacion` son opcionales; el resto obligatorios.

### 3.2 Campos nuevos, retrocompatibles (`NUEVO`)

Se añaden a la anatomía. **Si faltan se aplican valores por defecto**; una spec v1.1 sin ninguno de ellos carga igual.

```yaml
- id: R-CON-01
  descripcion: "PM coincide en todas las fuentes"
  logica: "unique(PM.valores_por_fuente)"
  severidad: BLOQUEANTE_DATOS
  referencia: SRC-FICHA §3
  fase: consistencia               # cabecera | ambito | consistencia | post_calculo | resto
  nivel: unidad                    # unidad | actuacion | grupo | expediente
  diferencial: true                # false si la plataforma oficial ya hace esta comprobación (R-DOC-01)
  equivalente_plataforma: null     # TODO(API-xx) si la plataforma valida lo mismo; permite el control cruzado
  origen_subsanacion: [interno, verificador]   # qué actores suelen requerir por esta regla (alimenta A9)
  subsanacion:
    mensaje: "La potencia del motor no coincide entre la ficha técnica y el certificado."
    documentos: [ficha_tecnica_motor, certificado_instalador]
  vigencia: { desde: "2025-05-07", hasta: null }   # solo si la regla cambia entre versiones
```

| Campo | Valor por defecto si falta | Efecto en la evaluación |
|---|---|---|
| `fase` | La que fija la tabla de §5.2 por `id` (decisión de Fase 0); para una regla desconocida, `resto` | Orden de evaluación y parada |
| `nivel` | `actuacion` | Sobre qué objeto se evalúa; `unidad` se evalúa una vez por motor |
| `diferencial` | `true` | Ninguno; informe y discurso comercial |
| `equivalente_plataforma` | `null` | Ninguno; qué comparar con el sandbox (`R-XCK`) |
| `origen_subsanacion` | `[interno]` | Ninguno; alimenta a A9 |
| `subsanacion` | `{ mensaje: descripcion, documentos: [] }` | Ninguno; es lo que consume A5 para redactar la petición al cliente. **Qué falta lo dice la regla; el agente solo redacta** |
| `vigencia` | `{ desde: null, hasta: null }` (siempre vigente) | La regla se salta si la actuación cae fuera de la vigencia |

`diferencial` y `equivalente_plataforma` no cambian nunca el resultado de la regla.

---

## 4. Severidades, veredicto y resultado de regla

### 4.1 Severidades y veredicto (`F0`)

| Severidad | Efecto si falla | ¿Calcula? |
|---|---|---|
| `BLOQUEANTE_AMBITO` | `NO_ELEGIBLE` | No |
| `BLOQUEANTE_DATOS` | `BLOQUEADO` | No |
| `SUBSANABLE` | `SUBSANABLE` | Sí, marcado como **provisional** (estimación no acreditada) |
| `AVISO` | No cambia el veredicto; requiere revisión humana | Sí |

Prioridad del veredicto: `NO_ELEGIBLE` > `BLOQUEADO` > `SUBSANABLE` > `PREVALIDADO`. `PREVALIDADO` significa "no falla ninguna regla salvo `AVISO`". Ningún veredicto significa CAE garantizado (descargo de la spec, `estados.descargo`).

### 4.2 Resultado de una regla: tres valores (`F0`)

| Resultado | Cuándo |
|---|---|
| `CUMPLE` | La condición es verdadera |
| `FALLA` | La condición es falsa |
| `NO_EVALUABLE` | Falta algún dato necesario para evaluarla (variable ausente o `valor_consumido = null` por conflicto) |

**Una regla `NO_EVALUABLE` no bloquea por sí misma.** La carencia la recoge la regla documental o de evidencia correspondiente, que sí falla. El registro garantiza que esa regla existe (§2.5, punto 3).

**Caso B como ejemplo** (`expedientes/EXP001-B_falta_registro/`): no hay registro de funcionamiento de 30 días, luego no existe N2 derivado. `R-CON-03` ("N2 declarado coincide con N2 derivado", `BLOQUEANTE_DATOS`) queda `NO_EVALUABLE`: no puede comparar contra algo que no existe. Lo que sí falla es `R-EVD-04` ("N2 es un dato demostrado, no solo declarado", `SUBSANABLE`), y `R-DOC-01` (falta `EVD-01`, obligatorio). El veredicto es `SUBSANABLE` con ahorro provisional de 305.829 kWh/año, **no** `BLOQUEADO`. Si `R-CON-03` fallase en lugar de quedar `NO_EVALUABLE`, el sistema bloquearía por una inconsistencia que no existe.

Matiz de conflicto: si N2 tiene dos valores derivados de dos fuentes fiables, el consolidador deja `valor_consumido = null` (regla de oro 6) y `R-CON-03` es igualmente `NO_EVALUABLE`; quien bloquea entonces es el conflicto (`ConflictoDetectado`), no la regla.

### 4.3 Severidad `COMPOSICION` (`NUEVO`)

Para grupo y expediente hay una severidad propia con dos efectos:

| Efecto | Significado |
|---|---|
| `INVALIDO` | No se puede componer; la plataforma lo rechazaría |
| `AVISO_CONTAGIO` | Se puede componer, pero un miembro débil arrastra a los demás (dictamen único por grupo; requerimiento de GA/CN bloquea el expediente entero) |

No entra en el veredicto de calidad de ninguna actuación.

---

## 5. Orden de evaluación por fases

### 5.1 Fases

Principio: **nunca se publica un ahorro apoyado en datos incoherentes.** Primero lo que impide calcular, después el cálculo, después lo que solo se puede comprobar con el resultado, y por último lo que solo resta calidad.

| Fase | Reglas | Si falla | Estado |
|---|---|---|---|
| 0. Cabecera | `R-CAB-01, 02, 08` (bloqueantes) | `BLOQUEADO`; el resto de `R-CAB` se evalúa en fase 5 | `NUEVO` |
| 1. Ámbito | `R-AMB-*` | `NO_ELEGIBLE`. **Se detiene**: no se calcula aunque ficha o convenio declaren ahorro (caso D) | `F0` |
| 2. Consistencia previa | `R-CON-01..05, 07` · `R-TMP-01` · `R-CAL-01, 04` · `R-CAL-02` (aviso) | `BLOQUEADO`. No se elige valor ni se calcula (caso C) | `F0` |
| 3. Cálculo | — (N3, §7) | — | `F0` |
| 4. Posterior al cálculo | `R-CAL-03` (controles físicos) · `R-CON-06` (convenio vs. `AETOTAL`) | `R-CAL-03` bloquea y **retira** el resultado; `R-CON-06` es subsanable | `F0` |
| 5. Resto | `R-DOC-*` · `R-EVD-*` · `R-TMP-02, 03` · `R-CAB-03..07, 09..13` | `SUBSANABLE` o aviso | `F0` (ficha) · `NUEVO` (cabecera) |
| 6. Control cruzado (solo en P8, con simulador o sandbox) | `R-XCK-*` | Bloquea el envío | `NUEVO` |
| 7. Composición (solo en P10) | `R-GRP-*`, `R-EXP-*` | `INVALIDO` o `AVISO_CONTAGIO` | `NUEVO` |
| Transversal | `R-REQ-*` | Invariantes del ciclo | `NUEVO` |

Reglas de parada:

- Si alguna regla de la fase 1 falla, se evalúan igualmente las demás de la fase 1 (para informar de todas las exclusiones) y se detiene.
- Si alguna de la fase 2 falla, se evalúan todas las de la fase 2 y **se salta la fase 3 y la 4**; la fase 5 sí se evalúa, para que el informe liste todas las carencias documentales de una vez.
- Las fases 6 y 7 no las ejecuta `evaluar_actuacion`; las ejecutan el puerto de salida (P8) y el compositor (P10) respectivamente.

### 5.2 Asignación regla a regla de IND240 v1.1 — decisión de diseño de la Fase 0

La spec activa no declara `fase`. Hasta que lo declare (diff v1.2 o posterior), el motor asigna cada una de sus 26 reglas según esta tabla, que es la que el Engine 0.1 aplicaba en su diseño. **Es una decisión de diseño de la Fase 0**: el código la implementa como valor por defecto por `id` y `tests/test_reglas.py` la verifica.

| Fase | Regla | Descripción (spec) | Severidad |
|---|---|---|---|
| 1. Ámbito | `R-AMB-01` | El equipo accionado es rotodinámico e incluido en el ámbito | `BLOQUEANTE_AMBITO` |
| 1. Ámbito | `R-AMB-02` | El motor es existente (no hay factura de motor ni de equipo nuevo) | `BLOQUEANTE_AMBITO` |
| 1. Ámbito | `R-AMB-03` | El régimen previo era constante y sin modulación | `BLOQUEANTE_AMBITO` |
| 2. Consistencia previa | `R-CON-01` | PM coincide en todas las fuentes | `BLOQUEANTE_DATOS` |
| 2. Consistencia previa | `R-CON-02` | N1 coincide en todas las fuentes | `BLOQUEANTE_DATOS` |
| 2. Consistencia previa | `R-CON-03` | N2 declarado coincide con N2 derivado del registro (±1 rpm) | `BLOQUEANTE_DATOS` |
| 2. Consistencia previa | `R-CON-04` | Nº de serie de variador y motor coinciden entre documentos | `BLOQUEANTE_DATOS` |
| 2. Consistencia previa | `R-CON-05` | Titular (NIF) coincide entre ficha, factura, declaración y convenio | `BLOQUEANTE_DATOS` |
| 2. Consistencia previa | `R-CON-07` | Número de motores coherente entre factura, certificado, ficha y registro | `BLOQUEANTE_DATOS` |
| 2. Consistencia previa | `R-TMP-01` | fecha_inicio <= fecha_fin | `BLOQUEANTE_DATOS` |
| 2. Consistencia previa | `R-CAL-01` | N2 < N1 | `BLOQUEANTE_DATOS` |
| 2. Consistencia previa | `R-CAL-02` | Existe fila exacta en cuadro 6 para PM (INT-02) | `AVISO` |
| 2. Consistencia previa | `R-CAL-04` | p no procede de la ficha técnica del variador | `BLOQUEANTE_DATOS` |
| 3. Cálculo | — | N3 | — |
| 4. Posterior al cálculo | `R-CAL-03` | Controles físicos FIS-01 y FIS-02 | `BLOQUEANTE_DATOS` |
| 4. Posterior al cálculo | `R-CON-06` | El ahorro anual del convenio coincide con AETOTAL calculado | `SUBSANABLE` |
| 5. Resto | `R-DOC-01` | Están presentes todos los documentos obligatorios | `SUBSANABLE` |
| 5. Resto | `R-DOC-02` | El informe fotográfico contiene fotos ANTES y DESPUÉS por motor | `SUBSANABLE` |
| 5. Resto | `R-DOC-03` | La factura contiene los datos mínimos | `SUBSANABLE` |
| 5. Resto | `R-DOC-04` | El convenio CAE contiene todos los campos del art. 11.2 | `SUBSANABLE` |
| 5. Resto | `R-DOC-05` | Ficha firmada por el representante legal | `SUBSANABLE` |
| 5. Resto | `R-EVD-01` | El registro de funcionamiento cubre al menos 30 días | `SUBSANABLE` |
| 5. Resto | `R-EVD-02` | El registro es posterior a la puesta en marcha | `SUBSANABLE` |
| 5. Resto | `R-EVD-03` | Existe prueba de inalterabilidad del registro y la huella coincide (INT-05) | `SUBSANABLE` |
| 5. Resto | `R-EVD-04` | N2 es un dato demostrado (derivado del registro), no solo declarado | `SUBSANABLE` |
| 5. Resto | `R-TMP-02` | Convenio CAE firmado antes de la solicitud | `SUBSANABLE` |
| 5. Resto | `R-TMP-03` | La solicitud se presenta dentro de la validez del CAE | `AVISO` |

Recuento: fase 1 = 3 · fase 2 = 10 · fase 4 = 2 · fase 5 = 11. **Total 26**, las 26 de la spec, ninguna más y ninguna menos.

Notas de asignación:

- `R-CAL-02` va en fase 2 aunque sea `AVISO` porque su resultado (hay fila exacta o no) decide cómo N3 obtiene `p` (INT-02: interpolación con aviso). Debe conocerse **antes** de calcular.
- `R-CAL-04` va en fase 2 porque comprueba el origen de `p`, no su valor; se conoce antes del cálculo.
- `R-CON-06` va en fase 4 porque necesita `AETOTAL_cae`. Si no se calcula (fases 1 o 2 falladas), queda `NO_EVALUABLE`; la carencia la recogen las reglas que causaron la parada.
- `R-EVD-01..04` van en fase 5 aunque condicionen el valor de N2: si el registro falta o es insuficiente, N2 derivado no existe, `R-CON-03` es `NO_EVALUABLE` y son estas las que fallan como `SUBSANABLE` (§4.2).

---

## 6. Lenguaje de expresiones (`engine/expresiones.py`)

### 6.1 Principios

- `logica` (reglas) y `formula` (cálculo) se interpretan con un **parser de lista blanca**. **Nunca `eval()`**, nunca ejecución de cadenas arbitrarias.
- Una función o construcción no reconocida es **error de carga de la spec**, no de ejecución: la ficha no se activa (§2.5).
- **Decisión de Fase 0: la `logica` del YAML es la ejecutable.** El motor evalúa el texto de `logica` con el parser. Lo que no se pueda expresar con el vocabulario cerrado se implementa en Python **registrada por `id`** (un registro `id → callable` en `engine/reglas.py`), y cada regla así registrada lleva un test que verifica que hace lo que dice su `logica`. El parser debe saber que el `id` está registrado; si no, error de carga. Que una regla esté en código no la exime de aparecer completa en el YAML: el YAML sigue siendo la única fuente de `descripcion`, `severidad`, `fase` y `subsanacion`.
- Toda aritmética sobre magnitudes del ahorro se hace con `Decimal`. El parser no produce `float`.

### 6.2 Vocabulario cerrado actual (`F0`)

Funciones y construcciones que ya aparecen en la spec activa:

| Grupo | Elementos |
|---|---|
| Agregación sobre colecciones | `unique(x)`, `exists(x)`, `all(x)`, `count(x)`, `sum(x)`, `min(a, b)` |
| Numéricas | `abs(x)`, `+ - * /`, `**` (solo en `formula`) |
| Integridad | `sha256(x)` |
| Documental | `presente(doc)` |
| Comparadores | `== != < <= > >=` |
| Pertenencia | `x in [lista]`, `x in coleccion` |
| Lógicos | `and`, `or`, `not` |
| Cuantificación | `for each <unidad>: <expresion>` (evalúa por motor; cumple si cumple en todas) |
| Aritmética de fechas | `fecha + N años` (`R-TMP-03`); comparación de fechas con `<=`, `>=` |
| Acceso | `objeto.atributo`, `coleccion.atributo` (proyección), `ambito.<lista>`, `tabla:<ID>` (literal de origen) |

Construcciones que aparecen en la spec activa y que el parser debe aceptar (o la regla queda registrada en código, §6.1):

- Implicación `a -> b` (`R-DOC-01`): equivale a `not a or b`.
- Filtro `coleccion where <condicion>` (`R-AMB-02`).
- Predicado como atributo, sin función (`factura.campos_minimos_presentes`, `ficha_cumplimentada.firmada`, `R-DOC-03`, `R-DOC-05`): el consolidador lo entrega como booleano; ausente → `NO_EVALUABLE`.
- Referencia a identificadores de la spec como booleanos (`FIS-01 and FIS-02`, `R-CAL-03`): cada `controles_fisicos[].id` se evalúa con su propio campo `regla` y expone su resultado con ese nombre.
- Literales de enumeración sin comillas (`constante_sin_modulacion`, `derivado`, `motor`).

### 6.3 Funciones nuevas (`NUEVO`)

Las requieren las familias propuestas (§10). Se añaden al vocabulario cuando se apruebe la spec que las usa; hasta entonces el parser las rechaza.

| Función | Semántica | Quién la usa |
|---|---|---|
| `unique_in_tenant(x)` | `x` no se repite en ninguna otra actuación del mismo tenant | `R-CAB-01` |
| `count_in_tenant(clave)` | Número de actuaciones del tenant con la misma clave | `R-EXP-05` |
| `anio(fecha)` | Año de una fecha | `R-CAB-13`, `R-TMP-03` v1.2 |
| `fecha(d, m, a)` | Construye una fecha | `R-CAB-13`, `R-TMP-03` v1.2 |
| `coherente(doc)` | Definida **por regla**, no genérica; si no se puede expresar con el vocabulario cerrado, la regla queda en código con test | `R-CAB-09` |
| `only_within(conjunto)` | Todos los elementos están dentro del conjunto dado | `R-REQ-03` |

### 6.4 Función → semántica → ejemplo en IND240 v1.1

Solo las funciones que aparecen en las 26 reglas activas.

| Función | Semántica | Ejemplo en la spec |
|---|---|---|
| `unique(coleccion)` | Verdadero si todos los valores presentes son iguales (tras `cruce` y `tolerancia_cruce_*` de la variable). Con un solo valor: verdadero. Sin valores: `NO_EVALUABLE` | `R-CON-01` `unique(PM.valores_por_fuente)` · `R-CON-04` `unique(num_serie_variador) and unique(num_serie_motor)` · `R-CON-05` `unique(titular_nif)` · `R-CON-07` `unique(n_motores_por_fuente)` |
| `exists(x)` | Verdadero si existe al menos un elemento que cumple (con `where` o condición interna) | `R-AMB-02` `not exists(factura.linea where categoria in [motor, bomba, ventilador, compresor, equipo_completo])` · `R-CAL-02` `exists(REG1781_CUADRO6.kw_motor == PM)` |
| `all(pred)` | Verdadero si el predicado se cumple para todos los elementos | `R-DOC-01` `all(doc.obligatorio == true -> presente(doc))` · `R-DOC-04` `all(requisito in convenio_cae)` |
| `count(x)` | Número de elementos | `R-DOC-02` `for each motor: count(foto.antes) >= 1 and count(foto.despues) >= 1` |
| `abs(x)` | Valor absoluto (`Decimal`) | `R-CON-03` `abs(N2.declarado - N2.derivado) <= 1` · `R-CON-06` `abs(convenio.ahorro_kwh - AETOTAL_cae) <= 1` |
| `sha256(x)` | Huella SHA-256 de los datos canónicos | `R-EVD-03` `registro.hash_declarado == sha256(registro.datos_canonicos)` |
| `presente(doc)` | Verdadero si hay al menos un documento de ese tipo en la actuación | `R-DOC-01` |
| `in` | Pertenencia a lista literal o a lista de la spec | `R-AMB-01` `tipo_equipo_accionado in ambito.tipos_equipo_incluidos` |
| `for each` | Evalúa la expresión por unidad (motor); cumple si cumple en todas | `R-DOC-02` |
| `+ N años` | Suma de años a una fecha | `R-TMP-03` `solicitud.fecha <= fecha_fin_actuacion + 3 años` |
| Comparadores | Sobre `Decimal`, fechas y enumerados | `R-CAL-01` `N2 < N1` · `R-EVD-01` `registro.dias >= 30` · `R-EVD-02` `registro.inicio >= fecha_fin_actuacion` · `R-TMP-01` `fecha_inicio_actuacion <= fecha_fin_actuacion` · `R-TMP-02` `convenio.fecha_firma <= solicitud.fecha` · `R-AMB-03` `regimen_previo == constante_sin_modulacion` · `R-EVD-04` `N2.evidencia == derivado` · `R-CAL-04` `p.fuente == tabla:REG1781_CUADRO6` |
| `and / or / not` | Lógica booleana con tres valores: si algún operando es `NO_EVALUABLE` y no decide el resultado, la regla es `NO_EVALUABLE` | `R-AMB-02`, `R-CON-04`, `R-CAL-03` `FIS-01 and FIS-02` |

`min` y `sum` no aparecen en `reglas`; aparecen en `variables.h.derivacion` (`min(h_antes, h_despues)`) y en `calculo.total.formula` (`sum(AEM)`). Forman parte del mismo vocabulario.

---

## 7. Motor de cálculo (N3, `engine/calculo.py`) — `F0`

- **Fórmula leída del YAML**, nunca escrita en código: `PM * (1 - (N2 / N1) ** 3) * (1 - p) * h` por unidad (`AEM`); `sum(AEM)` para el total (`AETOTAL`). Se interpreta con el mismo parser de §6.
- **`Decimal` de extremo a extremo**; sin redondeo interno. `AETOTAL_cae` = `AETOTAL` **truncado a kWh entero** (criterio conservador, INT-06). Un `float` en `calculo.py` es un defecto.
- **Precondiciones** (de `calculo.precondiciones`): `N2 < N1`; `0 < h <= 8760`; ninguna regla bloqueante fallida. Si alguna no se cumple, no se calcula y `calculo` queda vacío con motivo.
- **`p` sale siempre de la tabla de referencia** (cuadro 6 del Reg. (UE) 2019/1781, `data/reg_2019_1781_cuadro6.csv`, cargada por `engine/tablas.py` con vigencia), como `perdidas_ref_kw / PM` (INT-01). **Nunca** de la ficha técnica del variador (`R-CAL-04`). Sin fila exacta para PM: aviso `R-CAL-02` e interpolación lineal entre filas adyacentes (INT-02), con revisión humana.
- **`h = min(h_antes, h_despues)`** (nota 2 de la ficha: "se considerará el menor de los valores"). `h_despues` se extrapola del registro (INT-04).
- **Controles físicos** (`calculo.controles_fisicos`), evaluados tras el cálculo por `R-CAL-03`:
  - `FIS-01`: `AEM <= PM * h` — el ahorro no puede superar la energía máxima teórica del motor.
  - `FIS-02`: `P_prom <= PM` — la potencia promedio con variador no puede superar la nominal.
  Si alguno falla, `R-CAL-03` bloquea y **retira** el resultado: no se publica ningún ahorro.
- **Traza**: cada paso intermedio (valores consumidos, `p`, `h`, `(N2/N1)**3`, `AEM` por motor, suma, truncado) queda en `calculo.traza[]` con el `Decimal` como cadena. El informe la reproduce.
- **Provisional**: si el veredicto es `SUBSANABLE`, el cálculo se ejecuta y se marca `provisional: true` (estimación no acreditada).

**Valor de referencia para regresión** (caso A, `expedientes/EXP001-A_completo/`): PM = 110 kW, N1 = 1.485 rpm, N2 = 1.188 rpm, h = 6.000 h, `perdidas_ref_kw` = 5,55 → p = 5,55/110 = 0,050454… (5,0455 %). **`AETOTAL` = 305.829,6 kWh/año → `AETOTAL_cae` = 305.829.** Es criterio de aceptación de la Fase 0 (`tests/test_calculo.py`, `evaluar_casos.py`); si cambia, o hay bug o hay decisión con ADR.

**Control cruzado con la plataforma oficial** (`NUEVO`, familia `R-XCK`, §10.3). La plataforma calculará lo "tratable" de cada ficha. Nuestro cálculo pasa entonces a ser **control previo al envío**: si, cuando haya sandbox, el valor de la plataforma difiere del nuestro, se emite `DiscrepanciaCalculoPlataforma` y **no se envía** hasta que un humano lo resuelva. Cada discrepancia apunta a una de tres causas: bug nuestro, `INT-xx` mal resuelto o criterio oficial distinto. La tercera es la que cierra INT-01..05 empíricamente.

---

## 8. Consolidación de evidencias

Cómo se pasa de N evidencias a un `valor_consumido` (agrupación por clave de unión, normalización según `cruce`, tolerancias, OCR con confianza 0,75, conflicto → `null`, doble extracción, declarado ≠ demostrado) está en `docs/03-arquitectura-backend.md` §8. El motor de reglas recibe el resultado de esa consolidación y no la repite ni la corrige.

---

## 9. Familias de reglas

| Familia | Nivel | Qué comprueba | Quién la declara | Estado |
|---|---|---|---|---|
| `R-AMB` | unidad / actuación | Ámbito y exclusiones de la ficha | Ficha | `F0` (3) |
| `R-DOC` | actuación | Presencia y contenido mínimo de documentos | Ficha | `F0` (5); `R-DOC-01` propuesto como `diferencial: false` (§11) |
| `R-EVD` | unidad | Evidencia demostrada: registro, inalterabilidad, derivación | Ficha | `F0` (4) |
| `R-CON` | unidad / actuación | Consistencia entre fuentes | Ficha | `F0` (7) |
| `R-TMP` | actuación | Fechas y plazos de procedimiento | Ficha (o cabecera si es común) | `F0` (3); `R-TMP-03` con corrección propuesta (§11) |
| `R-CAL` | unidad | Precondiciones y controles físicos del cálculo | Ficha | `F0` (4) |
| `R-CAB` | actuación | Cabecera común: presencia, fuente y coherencia de los campos transversales | `spec/propuestas/cabecera_v1.yaml` | `NUEVO` (§10.1) |
| `R-GRP` | grupo | Composición válida de un grupo de actuaciones | `spec/propuestas/composicion_v1.yaml` | `NUEVO` (§10.2) |
| `R-EXP` | expediente | Composición válida de un expediente y avisos de contagio | `spec/propuestas/composicion_v1.yaml` | `NUEVO` (§10.2) |
| `R-XCK` | actuación | Control cruzado con la plataforma (cálculo y validaciones tratables) | `spec/propuestas/cabecera_v1.yaml` + `mapping/` | `NUEVO` (§10.3); necesita sandbox |
| `R-REQ` | actuación / expediente | Coherencia de la respuesta a un requerimiento oficial | `spec/propuestas/composicion_v1.yaml` | `NUEVO` (§10.4) |

`F0`: 3 + 5 + 4 + 7 + 3 + 4 = **26 reglas**, las de `spec/IND240_v1.1.yaml`.

---

## 10. Reglas propuestas — PENDIENTES DE APROBACIÓN DE BILLY

Las cinco familias siguientes son **diseño propuesto**. Su YAML vive en `spec/propuestas/` (`cabecera_v1.yaml`, `composicion_v1.yaml`) y **no se carga** (§2.2). Severidades, lógica y nombres son los propuestos; pueden cambiar en la revisión. Ninguna entra en la Fase 0.

### 10.1 Reglas transversales de cabecera (`R-CAB`)

Viven en `spec/propuestas/cabecera_v1.yaml` y se evaluarían en **toda** ficha. Los campos cuya semántica es `NO DOCUMENTADO` solo pueden ser `AVISO` hasta que llegue el diccionario de la API.

| ID | Descripción | Lógica (vocabulario cerrado) | Severidad | Diferencial |
|---|---|---|---|---|
| R-CAB-01 | Código identificativo propio único en el tenant | `unique_in_tenant(codigo_identificativo_propio)` | BLOQUEANTE_DATOS | — |
| R-CAB-02 | Fechas de ejecución presentes y coherentes | `exists(fecha_inicio) and exists(fecha_fin) and fecha_inicio <= fecha_fin` | BLOQUEANTE_DATOS | Parcial |
| R-CAB-03 | Precio del contrato de cesión presente en el convenio y con evidencia | `precio_contrato_cesion.evidencia == demostrado` | SUBSANABLE | Sí |
| R-CAB-04 | Inversión realizada derivada de facturas (INT-09) y > 0 | `inversion_realizada.evidencia == derivado and inversion_realizada > 0` | SUBSANABLE | Sí |
| R-CAB-05 | Costes operativos anuales informados | `exists(costes_operativos_anuales)` | AVISO (semántica no documentada) | — |
| R-CAB-06 | Tipología de empresa informada | `exists(tipologia_empresa)` | AVISO (taxonomía `TODO(API-05)`) | — |
| R-CAB-07 | Localización completa (UTM, ref. catastral) y CCAA derivable | `exists(localizacion.utm) and exists(localizacion.ref_catastral) and exists(localizacion.ccaa)` | SUBSANABLE | Sí |
| R-CAB-08 | Propietario inicial coincide con el titular del convenio y de la declaración | `propietario_inicial.nif == titular_nif` | BLOQUEANTE_DATOS | Sí |
| R-CAB-09 | Partícipe en subvención: valor declarado y coherente con la declaración responsable | `participe_subvencion in [true, false] and coherente(declaracion_responsable)` | SUBSANABLE | Sí |
| R-CAB-10 | Partícipe en subasta informado | `exists(participe_subasta)` | AVISO (`TODO(API-06)`) | — |
| R-CAB-11 | Verificador asignado y acreditado | `exists(verificador_id)` | SUBSANABLE (necesario para componer) | — |
| R-CAB-12 | Convenio CAE firmado antes de la solicitud (hoy R-TMP-02 en IND240) | `convenio.fecha_firma <= solicitud.fecha` | SUBSANABLE | Sí |
| R-CAB-13 | Validez del CAE (hoy R-TMP-03; INT-08) | `solicitud.fecha <= fecha(31,12, anio(fecha_fin) + n)` | AVISO | Parcial |

Con la aprobación, `R-TMP-02` y `R-TMP-03` de IND240 pasan a la cabecera y la ficha las hereda; así no se repiten en la segunda ficha.

### 10.2 Reglas de composición (`R-GRP`, `R-EXP`) — Sprint 4

| ID | Nivel | Descripción | Lógica | Severidad |
|---|---|---|---|---|
| R-GRP-01 | grupo | Todas las actuaciones del grupo tienen el mismo verificador | `unique(actuaciones.verificador_id)` | COMPOSICION → INVALIDO |
| R-GRP-02 | grupo | Ninguna actuación del grupo está `NO_ELEGIBLE` o `BLOQUEADO` | `all(a.veredicto in [PREVALIDADO, SUBSANABLE])` | COMPOSICION → INVALIDO |
| R-GRP-03 | grupo | No mezclar `SUBSANABLE` con `PREVALIDADO` (dictamen único) | `unique(actuaciones.veredicto)` | COMPOSICION → AVISO_CONTAGIO |
| R-EXP-01 | expediente | Misma CCAA, año de finalización, sector y verificador | `unique(ccaa) and unique(anio_finalizacion) and unique(sector) and unique(verificador_id)` | COMPOSICION → INVALIDO |
| R-EXP-02 | expediente | Solo actuaciones `VERIFICADA_FAVORABLE` (o un grupo con dictamen favorable) | `all(a.estado_plataforma == VERIFICADA_FAVORABLE)` | COMPOSICION → INVALIDO |
| R-EXP-03 | expediente | Un grupo verificado junto va en expediente propio | `grupo_id == null or count(grupos) == 1 and count(actuaciones_sueltas) == 0` | COMPOSICION → INVALIDO |
| R-EXP-04 | expediente | Aviso de contagio: alguna actuación con observaciones de A8 o avisos abiertos | `count(a where a.observaciones_abiertas > 0) > 0` | COMPOSICION → AVISO_CONTAGIO |
| R-EXP-05 | actuación | Actuación huérfana: única en su clave (CCAA, año, sector, verificador) dentro del tenant | `count_in_tenant(clave_agrupacion) == 1` | AVISO (informativo para el delegado) |
| R-EXP-06 | expediente | Capacidad de delegación disponible del tenant suficiente | `tenant.capacidad_disponible >= sum(ahorro)` | AVISO (`NO DOCUMENTADO` cómo se consulta, `TODO(API-11)`) |

Cómo se determina la CCAA de una actuación es `NO DOCUMENTADO` → `TODO(API-07)` en `docs/HUECOS.md`. Hasta entonces se deriva de la referencia catastral y se marca `derivado`.

### 10.3 Control cruzado con la plataforma (`R-XCK`) — necesita sandbox

| ID | Descripción | Lógica | Efecto |
|---|---|---|---|
| R-XCK-01 | El ahorro calculado por la plataforma coincide con el nuestro | `abs(plataforma.ahorro_kwh - AETOTAL_cae) <= tolerancia_xck` | Si falla: `DiscrepanciaCalculoPlataforma`, **no se envía** hasta resolución humana |
| R-XCK-02 | Todas las validaciones "tratables" de la plataforma pasan en el simulador antes del envío real | `simulador.validaciones_tratables == OK` | BLOQUEANTE_DATOS en P8 |
| R-XCK-03 | El manifiesto que aceptó la plataforma coincide con el nuestro (hashes) | `plataforma.manifiesto.hashes == manifiesto_interno.hashes` | BLOQUEANTE_DATOS en P8 |

`tolerancia_xck` empieza en 0 (aritmética exacta, `Decimal`). Cada discrepancia se clasifica a mano: bug nuestro, `INT-xx` mal resuelto o criterio oficial distinto.

### 10.4 Reglas de requerimiento (`R-REQ`) — Sprint 3

| ID | Descripción | Lógica | Severidad |
|---|---|---|---|
| R-REQ-01 | Toda subsanación con origen externo referencia un requerimiento con informe (PDF con hash) | `origen != interno -> exists(requerimiento_ref) and exists(informe_pdf_sha256)` | BLOQUEANTE_DATOS |
| R-REQ-02 | La interpretación de A9 ha sido confirmada por un humano antes de reabrir P7 | `requerimiento.interpretacion.confirmada_por_humano == true` | BLOQUEANTE_DATOS |
| R-REQ-03 | Tras la firma, ningún dato consolidado cambia fuera de un requerimiento abierto | `estado_ciclo >= EN_PLATAFORMA -> cambios_datos.only_within(requerimientos_abiertos)` | BLOQUEANTE_DATOS |
| R-REQ-04 | Un requerimiento de GA/CN marca como afectadas todas las actuaciones del expediente | `origen in [GA, CN] -> afectadas == expediente.actuaciones` | Invariante (test) |

---

## 11. Diff IND240 v1.1 → v1.2 (propuesto, no aprobado)

El diff está preparado en `spec/propuestas/IND240_v1.2.diff.md` y **no se activa sin revisión de Billy** (regla de oro 9). Cuando se apruebe, se mueve a `spec/IND240_v1.2.yaml` con ADR; v1.1 permanece cargable para replay.

| Cambio | Antes | Después | Motivo |
|---|---|---|---|
| `R-TMP-03` | `solicitud.fecha <= fecha_fin_actuacion + 3 años` | `solicitud.fecha <= fecha(31, 12, anio(fecha_fin_actuacion) + n)` con `n` en `INT-08` | La plataforma aplica "3 años desde el **año** de finalización, vencimiento el 31/12" (`docs/02`). Confirmar `n` con art. 17 Orden TED/815/2023 |
| `INT-08` (nuevo) | — | Tema: regla de expiración; criterio: `31/12/(año_fin + n)`, `n = 3` provisional; alternativa: fecha exacta + 3 años; impacto: medio | Interpretación abierta hasta confirmar con la Orden y con la plataforma |
| `R-DOC-01` | — | `diferencial: false`, `equivalente_plataforma: TODO(API-04)` | La plataforma comprueba presencia de documentos por tipo (`docs/02`) |
| `R-CON-05` | `unique(titular_nif)` | Sin cambio en lógica; `nivel: actuacion`, alimenta `cabecera.propietario_inicial` | Enlace con la cabecera |
| Variables | — | `fecha_inicio/fin_actuacion` pasan a declararse en `cabecera_v1.yaml` y la ficha las **hereda** | Son comunes a todas las fichas (art. 14.9.j Orden TED/815/2023) |
| `INT-09` (nuevo) | — | Tema: qué líneas de factura suman en `inversion_realizada`; criterio: base imponible de líneas del variador y su instalación; alternativa: total factura; impacto: bajo para el ahorro, medio para la cabecera | Campo de cabecera sin criterio oficial publicado |
| `version_spec` | `0.1.0` | `0.2.0` | Cambio de reglas |

Ningún otro cambio en las 26 reglas. La herencia de `cabecera_v1.yaml` depende de que la cabecera se apruebe antes o a la vez.

---

## 12. Avisos y observaciones

Dos canales que **nunca** alteran el veredicto:

- **Reglas con severidad `AVISO`** (`R-TMP-03`, `R-CAL-02` en la spec activa). Van al informe con su regla y su motivo; exigen revisión humana.
- **Observaciones de A8 (revisor sombra)**: cada una con cita, categoría y confianza. Van a `observaciones[]` y a la consola de revisión. A8 no se llama "verificador" en ningún texto.

Camino de promoción: si con datos reales se demuestra que una observación de A8 anticipa rectificaciones del verificador, se propone convertirla en regla determinista o en ítem de checklist del YAML, vía `spec/propuestas/` y aprobación de Billy. **De juicio a norma, nunca al revés.** Una regla del YAML nunca se degrada a observación de agente.

---

## 13. Interpretaciones `INT-xx`

Toda regla o derivación que dependa de un `INT-xx` lo declara en la spec (`interpretacion: INT-xx`). El código lo lee de ahí y nunca hardcodea el criterio. El informe y el modelo canónico listan las interpretaciones que han influido en el resultado (`interpretaciones_aplicadas[]`). Son criterios propios sin validar, **no** verdad normativa.

### 13.1 Abiertas (declaradas en `spec/IND240_v1.1.yaml`)

| ID | Tema | Criterio PoC | Alternativa | Impacto | Dónde se usa |
|---|---|---|---|---|---|
| INT-01 | Conversión de pérdidas de referencia (kW) a p | `p = pérdidas_ref_kW / PM` | `p = pérdidas_ref_kW / kVA de salida del variador` (≈1 % más de ahorro en 110 kW) | medio | `variables.p` |
| INT-02 | PM sin fila exacta en el cuadro 6 | Aviso + interpolación lineal entre filas adyacentes; revisión humana | Tomar la fila inmediatamente superior | bajo | `variables.perdidas_ref_kw`, `R-CAL-02` |
| INT-03 | N2 "media anual" acreditada con registro de 30 días | Media en MARCHA del periodo registrado; aviso si el proceso es estacional | — | alto | `variables.N2` |
| INT-04 | Extrapolación de `h_despues` a partir del periodo registrado | Horas en MARCHA × 8760 / horas del periodo | Plan de producción anual o registro de 12 meses | alto | `variables.h_despues` |
| INT-05 | Qué constituye un "registro inalterable" | Exportación de SCADA/datalogger con huella SHA-256 declarada en metadatos y en el certificado | Informe firmado electrónicamente por el sistema o por tercero | alto | `EVD-01`, `R-EVD-03` |
| INT-06 | Redondeo de `AETOTAL` a CAE | Truncar a kWh entero | — | bajo | `calculo.redondeo_salida` |
| INT-07 | Di — duración indicativa (fines estadísticos) | Dato informado por el técnico; el Engine no lo valida | — | bajo | Ninguna regla (Recomendación (UE) 2019/1658) |

### 13.2 Propuestas (en `spec/propuestas/IND240_v1.2.diff.md`)

| ID | Tema | Criterio propuesto | Alternativa | Impacto |
|---|---|---|---|---|
| INT-08 | Regla de expiración del CAE | `31/12/(año_fin + n)`, `n = 3` provisional | Fecha exacta + 3 años | medio |
| INT-09 | Qué líneas de factura suman en `inversion_realizada` | Base imponible de líneas del variador y su instalación | Total factura | bajo para el ahorro, medio para la cabecera |

### 13.3 Cerrar una interpretación

Cerrar un `INT-xx` es un **cambio normativo**: revisión humana, nueva `version_spec` y ADR en `docs/decisiones/`. Nunca se cierra en silencio en el código. INT-01, 03, 04 y 05 se cierran preferentemente con sesión de verificador o con la batería INT-xx contra el sandbox (`R-XCK-01`, `TODO(API-12)`).

---

## 14. Coeficientes de corrección (art. 18 bis)

El proyecto de modificación del RD 36/2023 introduce coeficientes de corrección (art. 18 bis). **Hoy no se implementan**: no están aprobados ni publicados con valores.

Cuando existan, se modelan como el tercer tipo de spec (§2.1): `spec/coeficientes_<ambito>.yaml` con, por fila, coeficiente, ficha o fichas afectadas, fuente oficial y vigencia (`desde`, `hasta`). N1 elige la fila por fecha con el mismo criterio de vigencia de §2.4. N3 aplica el coeficiente como paso adicional en la traza, nunca dentro de la `formula` de la ficha. Sin fila vigente para la fecha de la actuación → no se aplica coeficiente y se emite aviso. Alineado con lo que la alegación de `docs/00` pide que sea oficial.

---

## 15. Checklist para añadir una ficha

Es lo que ejecuta `/nueva-ficha <CODIGO>`. Rutas de `docs/01-estructura-del-repositorio.md`.

1. **Leer la ficha en BOE / catálogo MITECO.** Anotar versión oficial y fecha; incorporarlas como `spec.version_ficha` y `ficha.fuentes[]`.
2. **Escribir `spec/<CODIGO>_v<version_ficha>.yaml`** heredando `cabecera_v1.yaml` (cuando esté aprobada): solo lo específico de la ficha. Secciones: ámbito, exclusiones, variables (nivel, evidencia, fuentes, cruce), tablas, cálculo, documentación, reglas con `fase` y `subsanacion`, estados, interpretaciones. Empieza en `spec/propuestas/` hasta el paso 8.
3. **Todo lo que la ficha no cierre → `INT-xx`** con criterio, alternativa e impacto. No resolver en silencio.
4. **Tablas de referencia en `data/`** con entrada en `data/README.md`: fuente oficial (URL), fecha de transcripción, quién la verificó y contra qué, vigencia.
5. **`mapping/<CODIGO>.handoff.yaml`** y, cuando exista diccionario (`TODO(API-08)`), `mapping/<CODIGO>.api.yaml`.
6. **Paquete sintético** en `generator/` → `expedientes/`: un caso por veredicto (`PREVALIDADO`, `SUBSANABLE`, `BLOQUEADO`, `NO_ELEGIBLE`), uno desordenado y **uno con cabecera incompleta**. Ground truth en `expedientes/_resultados_esperados/` con ADR.
7. **Tests** en `tests/`: por regla, un caso que cumple y uno que falla; garantía `NO_EVALUABLE → SUBSANABLE` (§2.5); metamórficas de `docs/05`; **composición** (la ficha entra en un expediente con otra ficha del mismo sector).
8. **Revisión humana de la spec** (Billy) antes de moverla de `spec/propuestas/` a `spec/`; ADR en `docs/decisiones/`.
9. **Cero cambios en `engine/`.** Si hacen falta, es un defecto del marco: se arregla en el marco (con su propio test) y se registra como tal, nunca con una excepción para la ficha.

---

## 16. Fuentes

- `spec/IND240_v1.1.yaml` (`version_spec` 0.1.0, revisión 17/09/2026) — 26 reglas, variables, cálculo, controles físicos, INT-01..07.
- `docs/historico/07-backend-y-motor-de-reglas_v1.0.md` v1.0 (18/09/2026) — §6 motor de reglas, §7 motor de cálculo. Superado; base de este documento.
- `docs/historico/11-backend-funcionalidades-y-motor-de-reglas_v1.0.md` v1.0 (18/09/2026) — §3.6 Spec Registry, §5 motor de reglas a tres niveles, familias nuevas, diff v1.2. Superado; gana sobre `07` en lo que discrepa.
- `docs/00-instrucciones-de-entrada.md` — reglas de oro, glosario.
- `docs/02-plataforma-oficial.md` — cabecera común, presencia documental, regla de expiración, estados.
- `docs/03-arquitectura-backend.md` — modelo canónico, consolidación de evidencias (§8), log de eventos, máquina de estados.
- `docs/05-evaluacion-y-banco-de-pruebas.md` — casos A–G, ground truth, metamórficas.
- `docs/HUECOS.md` — `TODO(API-04, 05, 06, 07, 08, 11, 12)` citados aquí.
- Ficha IND240 V1.1 (catálogo vigente MITECO); Reglamento (UE) 2019/1781, anexo I, cuadro 6; Orden TED/815/2023 (arts. 11, 14.9.j, 17); Real Decreto 36/2023 y su proyecto de modificación (art. 18 bis) — enlaces en `spec/IND240_v1.1.yaml` `ficha.fuentes` y en `docs/00`.

---

*Mantener vivo: este documento cambia en la misma sesión en que cambia `engine/reglas.py`, `engine/expresiones.py`, `engine/calculo.py`, `engine/spec_registry.py` o cualquier spec activa. Una regla en el YAML que no esté en §5.2, una función en `logica` que no esté en §6, o una marca `F0`/`NUEVO` que el código ya haya superado, es un defecto que se corrige antes de cerrar la sesión. Las severidades, los criterios `INT-xx` y las familias propuestas solo cambian con aprobación de Billy y ADR.*
