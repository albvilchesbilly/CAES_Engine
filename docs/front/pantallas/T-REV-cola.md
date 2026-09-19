# Spec de pantalla — `T-REV-cola` (Cola de revisión)

| Campo | Valor |
|---|---|
| Superficie | Workspace del tenant (`ADR-050`) |
| Perfil | `T-REV` (Revisor técnico) |
| Id de pantalla | `cola_revision` (declarado en `engine/capacidades.yaml`, `superficies.workspace.pantallas`) |
| Pantalla de inicio del perfil | Sí |
| Entregable | `FR1` (absorbe `S4.4`) |
| Contrato | `ADR-012` §4 (C19) · `ADR-050` §"Front por perfil" y §"Paquete por pantalla" |
| Mockup | `docs/front/mockups/T-REV-cola.html` — **si el mockup y esta spec discrepan, manda la spec** |
| Estado | `NUEVO` (diseño aprobado, sin implementar) |

---

## 1. Objetivo

Que el revisor decida **en menos de treinta segundos y sin abrir nada** cuál de sus actuaciones toca ahora,
y por qué.

Es el "hecho cuando" de `S4.4`, literal: escalados, conflictos, correcciones pendientes y tareas de la
plataforma, **consumidas del simulador**, priorizadas por motivo y antigüedad. Cada fila dice **por qué está
ahí** y **cuánto lleva esperando**.

La cola no revisa: reparte trabajo. Todo lo que se decide sobre una actuación concreta ocurre en
`T-REV-revision`, y esta pantalla existe para llegar allí con el contexto ya puesto.

### Qué no hace esta pantalla

- **No ejecuta ningún comando.** Ninguna acción de la cola escribe un evento en el log. Aprobar, corregir,
  descartar y subsanar se hacen con la actuación delante, no desde una lista.
- **No ordena ni recalcula** lo que le llega (`ADR-012` §3, regla 3 del contrato C18). El orden es del
  servidor. Los encabezados de columna **no son controles de ordenación** en `FR1`.
- **No muestra valores de variables extraídas.** Una fila nombra el conflicto ("conflicto en `PM`") pero no
  enseña los dos valores: enseñarlos obligaría a arrastrar su cita (`R-UI-09`) a una lista que se lee de un
  vistazo. Los valores, con sus dos evidencias, están una pulsación más allá.

---

## 2. Capacidades que ejerce

Las tres son **lecturas**: no generan eventos y no necesitan que se resuelva un rol para el log
(`ADR-050`, §"Inferencia del rol"). Aun así, `Respuesta.rol` llega resuelto y la cabecera muestra
"actuando como Revisor técnico".

| Capacidad | Tipo | Concedida a `T-REV` | Manejador | Para qué en esta pantalla |
|---|---|---|---|---|
| `CAP-03` Consultar la actuación completa | lectura | sí | `actuacion_completa` | Veredicto, conflictos, ahorro y antigüedad de cada fila |
| `CAP-04` "Qué te falta" e informe de su destinatario | lectura | sí | `que_te_falta` | Carencias con su severidad: el motivo "corrección pendiente" |
| `CAP-14` Estados y tareas de la plataforma | lectura | sí | `estados_y_tareas` | Estado de ciclo (escalado), estado de plataforma y requerimiento abierto |

Ninguna otra capacidad se invoca desde aquí. En particular **no** se invocan `CAP-05`, `CAP-08`, `CAP-09`,
`CAP-10` ni `CAP-16`: son comandos y viven en `T-REV-revision`.

---

## 3. Lecturas que consume

Bloques tal y como los construye `api/proyeccion.py` (`CONSTRUCTORES`) para el ámbito `tenant`. La cola
**solo usa los campos de esta tabla**; lo que no esté aquí no se pinta aunque llegue.

| Lectura | Bloque | Campos que usa la cola |
|---|---|---|
| `CAP-03` | `identificacion` | `actuacion_id`, `codigo_identificativo_propio`, `ficha`, `fecha_evaluacion` |
| `CAP-03` | `veredicto` | `valor`, `semaforo`, `mensaje`, `descargo` |
| `CAP-03` | `conflictos` | `variable`, `num_serie_motor` (solo el recuento y el nombre de la variable) |
| `CAP-03` | `calculo` | `total_exacto`, `total_cae`, `provisional`, `motivo_no_calculo` |
| `CAP-03` | `historial` | `ocurrido_en` del primer y del último evento (antigüedad); `tipo` `TareaPendienteRecibida` |
| `CAP-04` | `que_te_falta` | `hay_carencias` y, por carencia, `id`, `severidad`, `mensaje` |
| `CAP-14` | `estados_plataforma` | `estado_ciclo`, `estado_plataforma`, `requerimiento_abierto`, `literales_desconocidos`, `secuencia` |

Bloques que la cola **recibe y no usa**: `documentos` y `evidencias` (de `CAP-03`) y `estado_simplificado`
(de `CAP-04`). No se pintan. No se filtran en el cliente porque el filtrado es de serialización y lo hace
el servidor (`R-UI-12`); recibirlos no autoriza a enseñarlos.

---

## 4. Comandos que dispara

**Ninguno.** Es una decisión de diseño, no una carencia: una lista es el peor sitio para ejercer una
capacidad que escribe en el log, porque se ejerce sin haber mirado el expediente. Si aparece la necesidad de
una acción masiva (por ejemplo, descartar diez `NO_ELEGIBLE` de golpe), se abre un ADR: no se cuela como
botón de fila.

---

## 5. Anatomía de una fila

| Elemento | De dónde sale | Regla |
|---|---|---|
| Código identificativo propio | `identificacion.codigo_identificativo_propio`; si es nulo, `actuacion_id` | — |
| Ficha | `identificacion.ficha` | — |
| Semáforo y veredicto | `veredicto.semaforo` + `veredicto.valor` | `R-UI-02`: es un rótulo, no un selector |
| Motivo o motivos | Ver §6 | Cada fila declara **al menos uno**; una fila sin motivo no está en la cola |
| Antigüedad | `historial[0].ocurrido_en` (apertura) y `historial[-1].ocurrido_en` (último movimiento) | Fecha absoluta siempre; "hace N días" como texto secundario. Sin historial → `SIN DATO` (`R-UI-07`), nunca "0 días" |
| Estado de ciclo | `estados_plataforma.estado_ciclo` | Nuestro estado, rotulado como tal |
| Estado de plataforma | `estados_plataforma.estado_plataforma` | Solo se refleja. Si es nulo, `SIN DATO` |
| Ahorro prevalidado | `calculo.total_exacto` | `R-UI-06`: envuelto en `RotuloPrevalidado tipo="AHORRO_PREVALIDADO"`. Si es `null`, `SIN DATO` con el `motivo_no_calculo` como explicación (`R-UI-07`) |
| Marca de estimación | `calculo.provisional` | Si es `true`, la cifra sale marcada "estimación no acreditada" |
| Acción | Un único enlace a `T-REV-revision` con `actuacion_id` | La fila entera es el objetivo; no hay menú contextual |

**Caso C en la cola** (`EXP001-C_contradictorio`): semáforo rojo, veredicto `BLOQUEADO`, motivo
"Conflicto en `PM` (MTR-SYN-0001)", ahorro `SIN DATO` con la explicación "conflicto entre fuentes fiables en
`PM`: el motor no elige valor ni calcula". **La columna de ahorro no puede quedar en blanco ni mostrar 0.**

---

## 6. Motivos: los cuatro de `S4.4`

| Motivo | Condición, literal, sobre lo que sirve `api/` | Prioridad propuesta |
|---|---|---|
| **Conflicto** | `conflictos` no está vacío | 1 |
| **Escalado** | `estados_plataforma.estado_ciclo == "EN_REVISION_HUMANA"`, o `literales_desconocidos` no vacío | 2 |
| **Requerimiento abierto** | `estados_plataforma.requerimiento_abierto` no es nulo | 2 |
| **Corrección pendiente** | `que_te_falta.hay_carencias` es `true`; el rótulo lo da la severidad más alta (`BLOQUEANTE_AMBITO` > `BLOQUEANTE_DATOS` > `SUBSANABLE` > `AVISO`) | 3 |
| **Tarea de la plataforma** | Hay eventos `TareaPendienteRecibida` en `historial` sin cierre posterior | 4 |

**La prioridad la aplica el servidor, no la pantalla.** La columna de orden de esta tabla es lo que el
contrato de la lectura de cola tiene que implementar (§8, `GAP-COLA-01`), y está aquí para que sea
verificable, no para que la calcule el front. Mientras esa lectura no exista, la cola pinta las filas en el
orden en que las recibe y **lo dice** (§7, estado *degradado*).

---

## 7. Estados de la pantalla

| Estado | Cuándo | Qué se ve |
|---|---|---|
| **Cargando** | Petición en vuelo | Esqueleto de filas sin cifras. Ninguna celda numérica aparece vacía ni a cero: se ve el hueco de carga, que es distinto de `SIN DATO` |
| **Vacío** | La lectura responde y no hay ninguna actuación en la cola | "No hay nada esperando revisión." Nunca se confunde con un error ni con un cero |
| **Con filas** | Caso normal | La tabla de §5 |
| **Fila parcial** | Una de las tres lecturas de esa actuación falla | La fila se pinta con lo que hay y las celdas de la lectura caída son `SIN DATO` con el motivo. Una lectura caída **no tumba la cola entera** |
| **Sin permiso** | `ErrorPermiso` | Se muestra el mensaje del servidor tal cual, con la capacidad y el motivo. **No se oculta el error en silencio** (`ADR-012` §3, regla 2): un control que desaparece sin explicación es un control que nadie arregla |
| **Error de la API** | `ErrorApi` (repositorio ausente, actuación sin procesar, matriz que no carga) | Mensaje literal del servidor + acción "reintentar". No se sustituye por "no hay datos" |
| **Degradado** | Mientras `GAP-COLA-01` esté abierto | Banner fijo: "Cola en modo degradado: la lista y el orden de prioridad todavía no los sirve la API." Las filas se ven igual |

En todos los estados, la cabecera muestra la marca de origen de datos (`MarcaOrigen`) y el rol
("actuando como Revisor técnico", de `Respuesta.rol`).

---

## 8. Lo que hoy no existe en `api/`

Nada de lo que pide esta spec se inventa: lo que no existe se enumera aquí con lo que haría falta. Una spec
que pide un bloque inexistente es una spec que se incumple el primer día.

| Id | Qué falta | Qué haría falta exactamente | Mientras tanto |
|---|---|---|---|
| `GAP-COLA-01` | **No hay ninguna lectura de lista.** `CAP-03`, `CAP-04` y `CAP-14` exigen `actuacion_id` (`Peticion.actuacion_id` levanta `ErrorApi` si falta). El repositorio sí sabe (`Repositorio.actuaciones_de(tenant_id)`), pero ninguna lectura lo expone a `T-REV` | Un bloque nuevo (`cola`) en `api/proyeccion.CONSTRUCTORES`, admitido por el ámbito `tenant` en `engine/capacidades.yaml` y declarado en una capacidad que la matriz conceda a `T-REV`. Devuelve **filas ya ordenadas** por el criterio de §6, cada una con identificación, veredicto, motivos, antigüedad y estado. Dónde cuelga (modo lista de `CAP-03` frente a capacidad nueva en `ADR-006`) **es decisión de Billy**: las dos tocan la matriz de permisos | La lista de `actuacion_id` llega como **configuración de despliegue del workspace**, en un solo sitio, nunca dentro de un componente; la cola compone cada fila con tres lecturas por actuación y muestra el banner de degradado |
| `GAP-COLA-02` | El bloque `estados_plataforma` (`proyectar(log).a_dict()`) **no trae las tareas pendientes** ni ninguna marca de tiempo, aunque el log tiene los eventos `TareaPendienteRecibida` que escribe el simulador (`salida/simulador/plataforma.py`) | Añadir a ese bloque `tareas_pendientes` (id, asunto, referencia, `vence_en`, instante) leídas de `log.por_tipo("TareaPendienteRecibida")`, y `abierta_en` / `ultimo_movimiento_en`. Es proyección, no cálculo | La cola saca tareas y antigüedad de `historial` (`CAP-03`), que es más caro y trae payloads que la cola no necesita |
| `GAP-COLA-03` | **Ningún bloque declara el origen de los datos** (sintético o real), y `R-UI-08` obliga a declararlo en todo panel | Un campo `origen_datos` (`"SINTETICO"` / `"REAL"`) en el bloque `identificacion`, decidido por el servidor a partir del tenant o del despliegue | `MarcaOrigen` se pinta sin `origen` reconocido y sale `ORIGEN DE DATOS SIN DECLARAR`, que es el comportamiento honesto que ya tiene el componente |
| `GAP-COLA-04` | `calculo.total_exacto` llega en forma canónica (`"305829.6"`), no en la forma que lee una persona en español (`305.829,6`) | Que `api/` sirva también el texto presentable, como hace `MetricaPresentable` en `front/compartido` | La cola pinta la cadena tal cual llega. **Prohibido** convertirla a `Number` para reformatearla: el ahorro no pasa por coma flotante (`CLAUDE.md` §2) |

---

## 9. Reglas `R-UI` aplicables

| Regla | Cómo se cumple aquí |
|---|---|
| `R-UI-01` | La cola no habilita nada por su cuenta: pide, y el servidor concede o niega. Un `ErrorPermiso` se muestra |
| `R-UI-02` | No hay ningún control que fije, fuerce o cambie un veredicto. El veredicto es texto. Los filtros por veredicto **filtran la lista**, y el chip de filtro vive en la barra de filtros, nunca dentro de una fila |
| `R-UI-06` | Toda cifra de ahorro va envuelta en `RotuloPrevalidado`. La cola no muestra estados de expediente; el día que lo haga, van con `NO OFICIAL` |
| `R-UI-07` | `SIN DATO` en ahorro, antigüedad o estado de plataforma ausentes. Ninguna celda numérica queda en blanco |
| `R-UI-08` | `MarcaOrigen` en la cabecera de la pantalla |
| `R-UI-09` | La cola no muestra ningún valor extraído, así que no hay dato sin cita. El nombre de la variable en conflicto no es un valor |
| `R-UI-10` | Aviso de registro de actividad **solo cuando exista `O-EQU`** (`CAP-36`, hoy sin implementar). Hasta entonces no se pinta un aviso de algo que no ocurre |
| `R-UI-11` | La cola no calcula, no evalúa reglas, no decide transiciones y **no ordena** |
| `R-UI-12` | El aislamiento es del servidor. La cola nunca pide una actuación por identificador escrito a mano: navega con los que la lectura le dio |

`R-UI-03`, `R-UI-04` y `R-UI-05` no aplican en esta pantalla porque no dispara comandos. `R-UI-05` sí
condiciona lo que la cola **enseña**: una actuación en `EN_PLATAFORMA` sin requerimiento abierto aparece
marcada "solo lectura", para que el revisor sepa antes de entrar que allí no va a poder tocar nada.

---

## 10. Criterios de aceptación

Cada uno se convierte en un test de `front/workspace/` salvo donde se indique otra cosa.

| Id | Hecho cuando… |
|---|---|
| `CA-COLA-01` | Con el simulador y los siete casos sintéticos cargados, la cola pinta una fila por actuación con cola pendiente y **ninguna sin motivo**: toda fila declara al menos uno de los cinco motivos de §6 |
| `CA-COLA-02` | La fila del caso C muestra el motivo "Conflicto en `PM`", veredicto `BLOQUEADO` y ahorro `SIN DATO` con el texto de `calculo.motivo_no_calculo`. El test falla si aparece `0`, `0,0`, `—` o una celda vacía en la columna de ahorro |
| `CA-COLA-03` | La fila del caso A muestra `305.829,6 kWh/año` (o la cadena que sirva `api/`, sin reformatear con `Number`) envuelta en `RotuloPrevalidado`, y el aviso "no son CAE emitidos" está en el DOM |
| `CA-COLA-04` | La fila del caso B muestra el motivo "Corrección pendiente (SUBSANABLE)" con las dos carencias (`R-DOC-01`, `R-EVD-04`) y su cifra marcada como estimación no acreditada (`calculo.provisional == true`) |
| `CA-COLA-05` | **`R-UI-02`**: un recorrido del árbol de `front/workspace/` no encuentra ningún control (botón, `select`, `input`, campo editable) cuyo valor o acción sea un veredicto. El mismo test cubre las dos pantallas |
| `CA-COLA-06` | **No se ordena en el cliente**: el orden del DOM es exactamente el orden en que llegan las filas. Un test que devuelve las filas en orden inverso las ve en orden inverso en pantalla, y no hay ningún encabezado con control de ordenación |
| `CA-COLA-07` | Con la lectura de una actuación devolviendo `ErrorApi`, su fila se pinta con `SIN DATO` y el motivo, y las demás filas siguen completas |
| `CA-COLA-08` | Con `ErrorPermiso`, el mensaje del servidor aparece literal en pantalla (capacidad y motivo). El test falla si el error se traga o se sustituye por "no hay datos" |
| `CA-COLA-09` | Con la lectura devolviendo cero filas, se ve el estado *vacío* con su texto, distinto del estado de error y del de carga |
| `CA-COLA-10` | El catálogo de textos de la pantalla pasa la misma lista de fórmulas prohibidas que `front/compartido/tests/textos.test.ts` (nada dice "CAE garantizado", nada "garantiza", `A8` no se llama "verificador", ningún kWh prevalidado se presenta como CAE emitido). El descargo que sirve el servidor no es texto de producto y no entra en el catálogo: ver `T-REV-revision.md` §11 bis |
| `CA-COLA-11` | Los identificadores de actuación no aparecen en ningún componente: el test busca `EXP001-` en `front/workspace/**` (excluidos los tests y el fichero de configuración) y no encuentra nada (`GAP-COLA-01`, modo degradado) |
| `CA-COLA-12` | Una actuación en `EN_PLATAFORMA` sin `requerimiento_abierto` aparece marcada "solo lectura" en la cola (`R-UI-05` anticipado) |
| `CA-COLA-13` | La cabecera muestra el rol que devuelve `Respuesta.rol` y la marca de origen de datos. Sin `origen_datos` (`GAP-COLA-03`), se lee `ORIGEN DE DATOS SIN DECLARAR` |

---

## 11. Dejado fuera a propósito

- **Búsqueda libre y filtros avanzados.** En `FR1` la cola de un revisor cabe en una pantalla. Un buscador
  que recorre el tenant es otra lectura y otra conversación sobre aislamiento.
- **Asignación de actuaciones a revisores.** Es `CAP-32`, que la matriz **deniega** hasta la decisión A3 de
  `ADR-005`. Sin esa decisión no hay "mías" frente a "del equipo": la cola es la del tenant.
- **Contadores agregados y métricas** (cuántas revisé hoy, minutos de revisión). Son `O-FUN` y `O-EQU`
  (`CAP-35`, `CAP-36`), que no existen, y la métrica de minutos de revisión sigue pendiente de Billy
  (`ADR-012` §6.2).
- **Acciones masivas.** Ver §4.
- **Vista de grupo o de expediente.** El Expediente Builder es `S4.1` (`CAP-13`, sin implementar) y el
  contagio entre actuaciones se enseña en la vista de revisión, donde hay sitio para explicarlo.
