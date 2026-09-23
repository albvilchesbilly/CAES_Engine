# Spec de pantalla — `T-REV-revision` (Vista de revisión)

| Campo | Valor |
|---|---|
| Superficie | Workspace del tenant (`ADR-050`) |
| Perfil | `T-REV` (Revisor técnico) |
| Id de pantalla en la matriz | `vista_revision` (declarado en `engine/capacidades.yaml`, `superficies.workspace.pantallas`, con `perfil: T-REV`; `GAP-REV-06` cerrado en `FR1.a`) |
| Se llega desde | `T-REV-cola`, con un `actuacion_id` |
| Entregable | `FR1` (absorbe `S4.4`) |
| Contrato | `ADR-012` §4 (C19) y §1–§2 (C17) · `ADR-050` §"Pantallas críticas" |
| Mockup | `docs/front/mockups/T-REV-revision.html` — **si el mockup y esta spec discrepan, manda la spec** |
| Estado | `NUEVO` (diseño aprobado, sin implementar) |

---

## 1. Objetivo

**Es la pantalla donde se mide el valor del producto.** Todo lo anterior —ingesta, evidencias, cálculo,
reglas, veredicto— existe para que un profesional revise una actuación en minutos en vez de en horas.

Concretamente, la pantalla tiene que dejar responder tres preguntas sin salir de ella:

1. **¿Esto está bien?** — veredicto, y qué lo sostiene o qué lo impide.
2. **¿Me lo creo?** — cada dato con su documento, su página y su texto literal, y el papel original al lado.
3. **¿Qué hago ahora?** — una sola acción evidente: corregir el dato que falla, pedir la subsanación,
   aprobar o descartar.

### La regla que da forma a toda la pantalla

**No hay control para cambiar el veredicto** (`R-UI-02`). El veredicto no es un campo: es el resultado de
aplicar la ficha a los datos. Si está mal, es que un dato está mal. Por eso el camino "corregir el dato" no
está escondido en un menú: es la acción principal al lado de cada dato que falla, y la pantalla dice, con
todas las letras, que **el motor recalcula** después. Que no parezca que falta un botón: que se vea que el
botón está en otro sitio y es mejor.

---

## 2. Qué se ve primero y qué es ruido

El informe de `engine/cli.py` es hoy lo que ve un revisor: 24 filas de reglas, 31 variables con sus
evidencias y una traza de cálculo, todo con el mismo peso. Para decidir hace falta muy poco de eso. Orden
de la pantalla, de arriba abajo:

| Nivel | Qué | Por qué ahí |
|---|---|---|
| 1 | **Veredicto** con su semáforo, su mensaje y el descargo obligatorio | Es la respuesta a "¿esto está bien?" |
| 2 | **Lo que lo impide**: conflictos primero, después carencias por severidad | Es lo único accionable. Caso C: la tarjeta de conflicto de `PM`. Caso B: las dos carencias `SUBSANABLE` |
| 3 | **El ahorro**, con su escalera de procedencia (§7) | Es la cifra que se va a presentar; sale con su rótulo |
| 4 | **Datos que entran en el cálculo** (6 en `IND240`), cada uno con su cita | Lo que hay que creerse para creerse la cifra |
| 5 | Resto de datos (25 en el caso A), reglas que cumplen, historial | Plegado. Está, y no estorba |

Regla dura: **lo que cumple no ocupa sitio**. Las reglas que `CUMPLE` no se listan una a una en el nivel
visible; se resumen en un contador ("24 de 24 comprobaciones conformes") que se despliega. Lo que falla,
lo que no se pudo evaluar y lo que está en conflicto, sí.

---

## 3. Disposición: pantalla partida

```
┌───────────────────────────────┬──────────────────────────────────────────────┐
│ CABECERA: código · ficha · estado de ciclo · estado de plataforma · rol      │
│           marca de origen de datos · aviso de solo lectura si procede        │
├───────────────────────────────┼──────────────────────────────────────────────┤
│                               │  VEREDICTO + descargo                        │
│  DOCUMENTO                    │  ─────────────────────────────────────────── │
│  (el papel original,          │  LO QUE LO IMPIDE  (conflictos, carencias)   │
│   servido por C17)            │  ─────────────────────────────────────────── │
│                               │  AHORRO (escalera de procedencia)            │
│  página de la cita,           │  ─────────────────────────────────────────── │
│  texto literal resaltado      │  DATOS DEL CÁLCULO (cada uno con su cita)    │
│                               │  ─────────────────────────────────────────── │
│                               │  ▸ Resto de datos · ▸ Reglas · ▸ Historial   │
└───────────────────────────────┴──────────────────────────────────────────────┘
```

- Pulsar una cita en el panel derecho **mueve el panel izquierdo** a ese documento y a esa página
  (`ADR-012` §4). Es la única forma de que "comprobar un dato" cueste una pulsación y no una búsqueda.
- El resaltado del texto literal lo hace el navegador sobre los bytes originales. **El servidor no retoca
  el documento** (`ADR-012` §2): si lo retocara, dejaría de poder demostrar que es el mismo fichero.
- Cuando el documento es una **parte de un PDF combinado**, se sirve el combinado entero y la pantalla
  muestra el aviso que viene en `Respuesta.avisos` y el rango de páginas de la parte.

---

## 4. Capacidades que ejerce

Las 12 de `T-REV` (`ADR-006`), menos `CAP-02`, que hoy no es ejercitable desde un navegador
(`GAP-REV-03`). `engine/capacidades.yaml` es la fuente: si una capacidad no está concedida allí, la
pantalla no la pide.

| Capacidad | Tipo | Evento que produce | Manejador | Dónde vive en la pantalla |
|---|---|---|---|---|
| `CAP-03` Consultar la actuación completa | lectura | — | `actuacion_completa` | Todo el panel derecho |
| `CAP-03` (C17) Servir el documento | lectura | — | `leer_documento` (`api/lecturas/documentos.py`) | Panel izquierdo |
| `CAP-04` "Qué te falta" | lectura | — | `que_te_falta` | Bloque "lo que lo impide" |
| `CAP-14` Estados y tareas de la plataforma | lectura | — | `estados_y_tareas` | Cabecera y candado de `R-UI-05` |
| `CAP-05` Resolver conflicto o corregir dato | comando | `DatoCorregidoPorHumano` | `corregir_dato` | "Usar este valor" y "Corregir dato" |
| `CAP-06` Resolver desacuerdo entre extractores | comando | `DatoCorregidoPorHumano` | `resolver_desacuerdo` | Igual que `CAP-05`, cuando el desacuerdo es entre extractores |
| `CAP-07` Revisar observaciones de A8 | comando | `ObservacionRevisada` | `revisar_observacion` | Lista de observaciones de prerrevisión |
| `CAP-08` Confirmar descarte de un `NO_ELEGIBLE` | comando | `ActuacionDescartada` | `confirmar_descarte` | Solo visible con veredicto `NO_ELEGIBLE` |
| `CAP-09` Enviar la subsanación redactada | comando | `SubsanacionSolicitada` | `enviar_subsanacion` | Bloque de carencias |
| `CAP-10` Aprobar el paso a `LISTA_PARA_ENVIO` | comando | `RevisionAprobada` | `aprobar_revision` | Acción principal de la cabecera |
| `CAP-15` Confirmar la interpretación de A9 | comando | `RequerimientoInterpretado` + `RequerimientoRecibido` | `confirmar_interpretacion` | Bloque de requerimiento abierto (`GAP-REV-04`) |
| `CAP-16` Decidir ante una discrepancia con la plataforma | comando | `DiscrepanciaResuelta` | `resolver_discrepancia` | Bloque de discrepancia |
| `CAP-02` Subir documentación | comando | `DocumentoRegistrado` | `registrar_documento` | **Inactivo** en `FR1` (`GAP-REV-03`) |

`A8` es prerrevisión: sus salidas son **observaciones**, nunca un veredicto, y en ningún texto de esta
pantalla se le llama "verificador".

---

## 5. Lecturas que consume

| Lectura | Bloque | Campos que usa la pantalla |
|---|---|---|
| `CAP-03` | `identificacion` | `actuacion_id`, `codigo_identificativo_propio`, `ficha`, `fecha_evaluacion` |
| `CAP-03` | `veredicto` | `valor`, `semaforo`, `mensaje`, `descargo`, `reglas_falladas`, `reglas_no_evaluables`, `interpretaciones_aplicadas`, `hash_reglas`, y `reglas[]` con `id`, `resultado`, `severidad`, `fase`, `nivel`, `descripcion`, `referencia`, `interpretacion`, `motivo` y `por_unidad` |
| `CAP-03` | `conflictos` | `variable`, `num_serie_motor`, `valor_consumido` (siempre `null`), `evidencias[]` completas |
| `CAP-03` | `calculo` | `total_exacto`, `total_cae`, sus dos `*_presentable`, `provisional`, `motivo_no_calculo`, `traza[]`, `variables{}` (la descripción de cada entrada y derivada, de la spec) y `por_unidad[]` (`entradas`, `derivadas`, sus `*_presentables`, `fuentes`, `salida`, `salida_presentable`, `controles`, `precondiciones`, `interpretaciones`, `avisos`, `motivo_no_calculo`) |
| `CAP-03` | `evidencias` | Por dato: `variable`, su `descripcion`, `definicion` y `referencia` de la spec, `num_serie_motor`, `valor_consumido`, `valor_normalizado`, `tipo_evidencia`, `fuente_primaria`, `interpretacion`, `valores_por_fuente`, `conflicto`, `posibles_errores_ocr`, `unidad`, `avisos`; y por evidencia: `doc_id`, `tipo_doc`, `pagina`, `texto_literal`, `metodo`, `confianza`, `extractor_version`, `tipo_evidencia` |
| `CAP-03` | `documentos` | `doc_id`, `sha256`, `nombre`, `tipo`, `paginas`, `formato`, `origen`, `rango_paginas`, `avisos` |
| `CAP-03` | `historial` | `tipo`, `ocurrido_en`, `actor`, `payload` (observaciones de A8, requerimientos, discrepancias, correcciones anteriores) |
| `CAP-03` (C17) | `datos.documento` | `doc_id`, `tipo`, `medio`, `bytes`, `paginas`, `origen`, `rango_paginas`, `contenido_base64` |
| `CAP-04` | `que_te_falta` | `hay_carencias`, y por carencia `id`, `severidad`, `mensaje`, `documentos` |
| `CAP-14` | `estados_plataforma` | `estado_ciclo`, `estado_plataforma`, `veredicto`, `revisada_por_humano`, `requerimiento_abierto`, `afectada_directamente`, `literales_desconocidos`, `rechazos`, `tareas_pendientes`, `abierta_en`, `ultimo_movimiento_en` |

Las tres capas de cada dato (`CLAUDE.md` §2, regla 3) se ven **las tres**: la evidencia documental
(`texto_literal` con su documento y su página), la interpretación (`valor_normalizado`, `tipo_evidencia`,
`interpretacion`) y el valor que consumió el cálculo (`valor_consumido`). Ninguna se resume en otra.

---

## 6. El caso C: un conflicto resuelto en menos de un minuto

Caso `EXP001-C_contradictorio`: la ficha, la placa y la ficha técnica dicen `PM = 110 kW`; el certificado
del instalador dice `90 kW`. El motor **no elige y no calcula**: `valor_consumido = null`, veredicto
`BLOQUEADO`, `R-CON-01` falla y no hay ahorro publicable. Esto no es un fallo del motor: es la regla de oro
6 funcionando. La pantalla tiene que hacer que resolverlo sea rápido **sin** hacer que elegir parezca
trivial.

### La tarjeta de conflicto

Es lo primero del panel derecho, con borde rojo, y contiene exactamente esto:

- Título: **"Conflicto en `PM` · Potencia nominal del motor · motor MTR-SYN-0001"**
  (el nombre legible de la variable viene de la spec: `GAP-REV-05`).
- La frase que explica el vacío, no un hueco: **"El motor no elige entre fuentes fiables. Sin este dato no
  hay cálculo."** — y el ahorro, arriba, en `SIN DATO` con ese mismo motivo. Nunca 0.
- Una fila por evidencia, **las cuatro**, comparables de un vistazo:

  | Valor | Documento | Pág. | Texto literal | Método | Confianza | Tipo |
  |---|---|---|---|---|---|---|
  | 110 kW | `01_ficha_IND240_cumplimentada.pdf` | 1 | "Potencia nominal del motor PM 110 kW" | tabla | 1,00 | demostrado |
  | 110 kW | `04_informe_fotografico.pdf` (placa) | 2 | "110 kw 1485 rpm" | OCR | 0,75 | demostrado |
  | **90 kW** | `05_certificado_instalador.pdf` | 1 | "a) Potencia nominal del motor PM (según ficha técnica) 90 kW" | tabla | 1,00 | demostrado |
  | 110 kW | `08_ficha_tecnica_motor_MTR-SYN-0001.pdf` | 1 | "Potencia nominal PM 110 kW" | tabla | 1,00 | demostrado |

- Cada fila tiene dos acciones: **"Ver en el documento"** (lleva el panel izquierdo a ese documento y esa
  página) y **"Usar este valor"**.
- La tarjeta dice además **qué es** el dato y **de dónde sale cada valor**: la descripción de la ficha
  ("Potencia nominal de salida del motor sin variador"), su referencia normativa (`SRC-FICHA §3; §5.5.a`) y
  el valor que aporta cada fuente, con su cita. Todo ello sale del bloque `evidencias`
  (`descripcion`, `definicion`, `referencia`, `valores_por_fuente`) y **existe con cálculo o sin él**.

  > **Resuelto el 23/09/2026 (hallazgo de `FR1.a`).** La redacción anterior decía que esto se lee de
  > `calculo.por_unidad[].entradas` y `fuentes`, y **en un caso bloqueado no se puede**: con un conflicto
  > el motor se salta la fase de cálculo entera y `actuacion.calculo` es `None` —comprobado sobre el caso
  > C, que es justamente el que esta sección narra—. `por_unidad` llega vacío y `traza` también.
  >
  > El diagnóstico fue que **se le estaba pidiendo a la fuente equivocada**. Que `PM` importe no es un
  > resultado del cálculo: es una verdad de la **ficha**, y la ficha está cargada aunque no se calcule
  > nada. Por eso la tarjeta se apoya en `evidencias`, no en `calculo`. No hizo falta tocar el motor ni
  > añadir un campo: `api/` ya sirve las cuatro claves desde `FR1.a`.
  >
  > Lo que la tarjeta **no** dice en un caso bloqueado es qué salidas concretas dependían del dato, porque
  > no hay salidas. Para eso está `calculo.motivo_no_calculo`, que llega con el texto exacto —"conflicto
  > entre fuentes fiables en `PM`: el motor no elige valor ni calcula"— y explica el hueco en vez de
  > dejarlo en blanco (`R-UI-07`). La alternativa que se descartó era que el motor dejase constancia de las
  > entradas previstas antes de detenerse: es `engine/` con su ADR, y no hace falta.

### El presupuesto de tiempo

| Paso | Qué hace el revisor | Segundos |
|---|---|---|
| 1 | Lee el título y ve 3 contra 1, con el valor discrepante destacado | 5 |
| 2 | Pulsa "Ver en el documento" en la fila de 90 kW; el panel izquierdo salta al certificado, página 1, con el texto resaltado | 10 |
| 3 | Comprueba la ficha técnica del motor (la fuente primaria, que la pantalla marca como tal) | 10 |
| 4 | Pulsa "Usar este valor" en una fila; se abre el formulario con `variable`, `num_serie_motor` y `valor` puestos | 5 |
| 5 | **Escribe la justificación** (obligatoria) | 20 |
| 6 | Envía; la pantalla confirma la corrección registrada y dice qué falta para recalcular | 5 |
| | **Total** | **~55 s** |

El paso 5 es el único que no se puede acelerar, y es deliberado: `R-UI-04` no admite justificación
automática. La pantalla **no rellena** el campo; sí muestra, junto a él, qué evidencia se eligió y cuáles
se descartan, para que escribir el motivo cueste veinte segundos y no dos minutos.

### El formulario de corrección (`CAP-05`)

| Campo | Origen | Regla |
|---|---|---|
| `variable` | Precargado de la tarjeta | Obligatorio (`Peticion.exige`) |
| `num_serie_motor` | Precargado | Opcional en el contrato; obligatorio en pantalla cuando el dato es de nivel unidad |
| `valor` | Precargado con la evidencia elegida, editable | **Viaja como cadena.** Un `float` en `datos` es rechazado por `api/contrato._sin_coma_flotante` |
| `justificacion` | **Vacío, obligatorio, escrito por la persona** | `R-UI-04`; viaja al log dentro del payload de `DatoCorregidoPorHumano` |

Enviar con la justificación vacía **no llega a `api/`**: el botón está inhabilitado y, si aun así se
enviara, el servidor lo rechaza. Las dos barreras, no una.

`CAP-06` es el mismo formulario cuando lo que discrepa son dos extractores sobre el mismo documento; cambia
el `motivo` que se escribe en el log (`"desacuerdo entre extractores"`), no la pantalla.

### Después de corregir: el motor recalcula

Al confirmarse la corrección, la pantalla:

1. Muestra la corrección en el historial, con quién, cuándo y su justificación.
2. Marca el veredicto y el ahorro como **"pendiente de recálculo"**. No los borra y **no los presenta como
   si ya reflejaran la corrección**.
3. Vuelve a pedir `CAP-03`, `CAP-04` y `CAP-14`.

Hoy ese recálculo **no ocurre** (`GAP-REV-01`): `procesar_actuacion` no lee las correcciones del log. La
pantalla lo dice con esas palabras en vez de fingir que el número ya está actualizado. Una pantalla que
enseña un veredicto viejo como si fuera nuevo es peor que una que no enseña nada.

---

## 7. El ahorro: de dónde salen 305.829,6 kWh/año sin leer una fórmula

Caso `EXP001-A_completo`. La pantalla **no calcula nada** (`R-UI-11`): todos los números de esta sección
llegan servidos en `calculo.por_unidad[]`. Lo que aporta es el orden y las palabras.

```
AHORRO PREVALIDADO                 305.829,6 kWh/año
  [Cifra prevalidada por el motor: no son CAE emitidos.]
  Para presentar (truncado a kWh entero, criterio INT-06):   305.829 kWh

  De dónde sale, motor MTR-SYN-0001:
   ① Potencia nominal del motor            PM = 110 kW      → ficha técnica (fuente primaria) · 3 fuentes más
   ② Velocidad antes de la actuación       N1 = 1.485 rpm   → ficha técnica · placa (OCR 0,75) · 2 más
   ③ Velocidad media con variador          N2 = 1.188 rpm   → derivado del registro (INT-03)
   ④ Horas de funcionamiento               h  = 6.000 h     → el menor de 6.000 y 6.570 (INT-04)
   ⑤ Pérdidas del variador                 p  = 5,05 %      → 5,55 kW / 110 kW, cuadro 6 (INT-01)
   ⑥ Comprobaciones físicas                FIS-01 ✓ FIS-02 ✓
```

Reglas de esta sección:

- **Cada línea lleva su cita o su origen.** ①②③④ enlazan al documento y a la página (`R-UI-09`); ⑤ enlaza a
  la tabla (`fuentes` = `tabla:REG1781_CUADRO6`) y no a un documento, porque no sale de uno.
- **Los `INT-xx` se ven y se nombran como lo que son**: "criterio propio, no validado contra la norma"
  (`CLAUDE.md` §3). Nunca como "según la normativa".
- **La fila del cuadro 6 se declara**: "fila de 110 kW → 5,55 kW". Es una decisión abierta de Billy
  (`ADR-003`), y la pantalla no la esconde: quien revisa tiene que poder ver de dónde sale ese 5,55.
- **La fórmula existe, pero está plegada.** Bajo "ver la fórmula" aparecen la expresión y la traza tal cual
  las da el motor. Se muestra, no se traduce: traducirla sería interpretarla.
- **`total_cae` nunca se presenta sin su etiqueta** de truncamiento ni sin el rótulo de `R-UI-06`.
- Si `calculo.provisional` es `true` (caso B), la cifra sale marcada **"estimación no acreditada"** en el
  mismo bloque, no en una nota al pie.
- Si `total_exacto` es `null` (caso C), el bloque entero es `SIN DATO` con `motivo_no_calculo`. **Nunca 0**.

---

## 8. Aprobar, subsanar, descartar

| Acción | Capacidad | Cuándo se activa | Qué dice la pantalla cuando no |
|---|---|---|---|
| **Aprobar la revisión** | `CAP-10` | Solo sin bloqueantes abiertos: `veredicto.valor == "PREVALIDADO"` y sin conflictos ni carencias bloqueantes | El botón está inhabilitado **con el motivo al lado**: "Falla `R-CON-01` (BLOQUEANTE_DATOS): PM coincide en todas las fuentes → corrige `PM`", con enlace al dato. Nunca un botón gris mudo |
| **Enviar la subsanación** | `CAP-09` | Hay carencias (`que_te_falta.hay_carencias`) | — |
| **Confirmar el descarte** | `CAP-08` | `veredicto.valor == "NO_ELEGIBLE"` | No se muestra en ningún otro caso. La máquina de estados lo exige igualmente |
| **Dar por revisada una observación** | `CAP-07` | Hay observaciones de A8 en el historial | — |
| **Confirmar la interpretación del requerimiento** | `CAP-15` | `estados_plataforma.requerimiento_abierto` no es nulo | `GAP-REV-04`: la interpretación propuesta no se sirve todavía |
| **Decidir ante la discrepancia** | `CAP-16` | Hay `DiscrepanciaCalculoPlataforma` en el historial | Exige justificación (`R-UI-04`) |

Inhabilitar un botón **no es autorización** (`R-UI-01`): el servidor valida siempre. La pantalla inhabilita
para explicar, no para proteger.

`CAP-10` marca `revisada_por_humano`, que es **la mitad** de la guarda de `LISTA_PARA_ENVIO`: la otra mitad
es el veredicto `PREVALIDADO`, y quien empaqueta es `T-OPE` (`CAP-11`). La pantalla lo dice al aprobar
("queda pendiente de que Operaciones prepare la entrega") en vez de dejar creer que aprobar es enviar.

**Ningún control se llama "Firmar"** (`R-UI-03`): en esta pantalla no hay ninguna acción de firma, y la
cabecera enlaza al registro de firma de `T-RES` solo como información de en qué paso está la actuación.

---

## 9. Estados de la pantalla

| Estado | Cuándo | Qué se ve |
|---|---|---|
| **Cargando** | Peticiones en vuelo | Esqueleto de las tres zonas. Ninguna cifra aparece: ni vacía, ni a cero |
| **Documento cargando** | El panel derecho ya está y `leer_documento` no ha vuelto | El panel izquierdo carga solo; el derecho ya es utilizable. Revisar el veredicto no espera a un PDF |
| **Completa** | Caso normal | §3 |
| **Conflicto** | `conflictos` no vacío | La tarjeta de §6 arriba del todo; el bloque de ahorro en `SIN DATO` |
| **Sin cálculo** | `calculo.total_exacto == null` | Bloque de ahorro con el `motivo_no_calculo` literal |
| **Provisional** | `calculo.provisional == true` | Cifra con "estimación no acreditada" |
| **Solo lectura** (`R-UI-05`) | `estado_ciclo == "EN_PLATAFORMA"` **y** `requerimiento_abierto == null` | Candado en la cabecera con el motivo; **todos** los controles de escritura inactivos. La lectura, entera |
| **Requerimiento abierto** | `requerimiento_abierto` no es nulo | El candado se levanta para el flujo de requerimiento; el resto sigue bloqueado, y la cabecera dice cuál es el requerimiento |
| **Contagiada** | `afectada_directamente == false` con requerimiento | Aviso: "afectada por un requerimiento de su expediente, no por un defecto propio" |
| **Corrección registrada, pendiente de recálculo** | Tras `CAP-05`/`CAP-06` | §6, punto 3 (`GAP-REV-01`) |
| **Corrección rechazada tras la firma** | `estados_plataforma.rechazos` no vacío | Se muestran los rechazos: no se pierden ni se silencian |
| **Documento alterado** | `ErrorIntegridad` al servir el documento | Aviso destacado: los bytes no casan con la huella de ingesta; **no se enseña nada en su lugar**. El panel derecho sigue funcionando |
| **Sin permiso** | `ErrorPermiso` | Mensaje literal del servidor (capacidad y motivo). No se oculta |
| **Error de la API** | `ErrorApi` | Mensaje literal + reintentar. Nunca "no hay datos" |
| **Actuación sin procesar** | La actuación no está en el repositorio | El mensaje del servidor tal cual: "no está procesada todavía; no hay nada que leer" |

---

## 10. Lo que hoy no existe en `api/`

| Id | Qué falta | Qué haría falta exactamente | Mientras tanto |
|---|---|---|---|
| `GAP-REV-01` | **El recálculo tras corregir.** `CAP-05` escribe `DatoCorregidoPorHumano` en el log y nada vuelve a evaluar: `engine.motor.procesar_actuacion(carpeta)` no lee el log ni recibe correcciones. El lazo "se corrige el dato y el motor recalcula" (`R-UI-02`, `ADR-012` §4) **no se cierra hoy** | Que `procesar_actuacion` acepte las correcciones humanas del log y las trate como una fuente más (con su capa de interpretación y su trazabilidad), y que el repositorio sepa reprocesar una actuación bajo demanda. Es cambio de `engine/` y de `docs/03`: le corresponde un ADR, no un parche del front | La pantalla muestra "corrección registrada · pendiente de recálculo" y **no** presenta el veredicto anterior como actualizado (`CA-REV-09`) |
| ~~`GAP-REV-02`~~ | **Cerrado en `FR1.a`** (23/09/2026) | `veredicto.reglas[]` trae **todas** las reglas evaluadas —también las que cumplen, para el contador de `CA-REV-19`— con `id`, `resultado`, `severidad`, `fase`, `nivel`, `descripcion`, `referencia`, `interpretacion`, `motivo` y `por_unidad`. Se amplió `veredicto` en vez de abrir un bloque nuevo: los identificadores siguen siendo el índice | — |
| `GAP-REV-03` | **No se puede subir un documento desde el navegador.** `registrar_documento` exige `ruta` y el repositorio lee ese fichero del disco del servidor. Un navegador no tiene rutas del servidor, y aceptar una del cliente sería leer ficheros arbitrarios | Que `CAP-02` admita los **bytes** (o una subida en dos pasos), y que la huella la siga calculando el núcleo sobre los bytes recibidos, nunca el cliente | El control de subida está inactivo y lo dice. Las carencias se resuelven pidiendo subsanación (`CAP-09`) |
| `GAP-REV-04` | **La interpretación propuesta de un requerimiento no se sirve.** `CAP-15` la necesita; vive en `Repositorio.requerimiento(...)` y ninguna lectura la proyecta | Un bloque `requerimientos` con el requerimiento, su interpretación propuesta (texto, reglas afectadas, confianza) y quién la propuso | El bloque de requerimiento muestra lo que hay en `historial` (`RequerimientoRecibido`) y el botón de confirmar se envía "a ciegas": en `FR1` **se deja inactivo** antes que confirmar algo que no se ha podido leer |
| ~~`GAP-REV-05`~~ | **Cerrado en `FR1.a`** (23/09/2026) | Cada dato de `evidencias` trae `descripcion`, `definicion` y `referencia` leídas de `spec.variables[...]`, y `calculo.variables{}` hace lo mismo para cada entrada y cada derivada del cálculo (va al lado de `por_unidad` para no cambiar la forma de `entradas`). Sigue **prohibido** un diccionario de etiquetas por ficha, en el front y en `api/`: hay un test que lo comprueba | — |
| ~~`GAP-REV-06`~~ | **Cerrado en `FR1.a`** (23/09/2026) | `vista_revision` está declarada con `perfil: T-REV` en `superficies.workspace.pantallas`, y desempata igual que `cola_revision` (caso añadido en `tests/test_api_rol_inferido.py`). El contexto ya dice desde dónde se actúa | — |
| `GAP-REV-07` | **Origen de los datos** (sintético o real) no lo declara ningún bloque, y `R-UI-08` lo exige en todo panel | `origen_datos` en el bloque `identificacion` | `MarcaOrigen` muestra `ORIGEN DE DATOS SIN DECLARAR` |
| ~~`GAP-REV-08`~~ | **Cerrado en `FR1.a`** (23/09/2026) | `calculo` sirve `total_exacto_presentable` y `total_cae_presentable`, y cada unidad `entradas_presentables`, `derivadas_presentables` y `salida_presentable`, **junto** a los valores exactos y nunca en su lugar. El formato lo hace `engine.informe.texto_es` sobre el `Decimal` | Se pinta la cadena tal cual. **Sigue prohibido** pasar por `Number` (`CLAUDE.md` §2) |
| ~~`GAP-REV-09`~~ | **Cerrado en `FR1.a`** (23/09/2026) | `calculo.traza` es la lista de cadenas tal cual la escribe el motor, y cada unidad trae `controles`, `precondiciones`, `interpretaciones` y `avisos`. `NO_EVALUABLE` viaja como la cadena `"NO_EVALUABLE"`, igual que en el informe del núcleo: es un centinela, no un booleano | Los valores intermedios **siguen sin calcularse en el front** (`R-UI-11`) |

Ninguna de estas carencias se resuelve inventando el campo en el front. Lo que no llega, no se pinta, y se
dice por qué.

---

## 11. Reglas `R-UI` aplicables

| Regla | Cómo se cumple aquí |
|---|---|
| `R-UI-01` | Todo comando se valida en el servidor. Los controles inhabilitados explican; no autorizan |
| `R-UI-02` | **No existe ningún control que fije, fuerce o cambie el veredicto.** El veredicto es texto, no campo. El camino es corregir el dato |
| `R-UI-03` | Ningún control se llama "Firmar". En esta pantalla no hay ninguna acción de firma |
| `R-UI-04` | `CAP-05`, `CAP-06` y `CAP-16` exigen justificación escrita por la persona. El front no la rellena, no la sugiere y no la copia de la evidencia |
| `R-UI-05` | Con `estado_ciclo == "EN_PLATAFORMA"` y sin requerimiento abierto, todos los controles de escritura están inactivos; con requerimiento abierto, se activan los del flujo de requerimiento |
| `R-UI-06` | Toda cifra de ahorro va en `RotuloPrevalidado`; `total_cae` lleva además su etiqueta de truncamiento (INT-06) |
| `R-UI-07` | `SIN DATO` en `valor_consumido` nulo, en el ahorro del caso C y en cualquier campo ausente. Nunca 0, nunca una celda muda |
| `R-UI-08` | `MarcaOrigen` en la cabecera |
| `R-UI-09` | **Todo dato extraído muestra su documento, su página y su texto literal**, y pulsarlo lleva al papel. Un dato sin cita es un defecto visible, no una celda más |
| `R-UI-10` | Aviso de registro de actividad solo cuando exista `O-EQU` (`CAP-36`, sin implementar) |
| `R-UI-11` | La pantalla no calcula, no evalúa reglas y no decide transiciones. No deriva valores intermedios ni recompone la fórmula |
| `R-UI-12` | El filtrado es del servidor. La pantalla no pide bloques por su cuenta ni compone identificadores de documento: usa los `doc_id` que vinieron en `documentos` |

---

## 11 bis. El descargo del servidor y la lista de fórmulas prohibidas

`front/compartido/tests/textos.test.ts` prohíbe en el **catálogo de textos del front** cuatro fórmulas:
"CAE garantizado", cualquier forma de "garantizar", la palabra "verificador" y presentar un kWh como CAE
emitido. El propio test deja dicho que, si `FR1` necesita nombrar al verificador, **la excepción se razona
en `FR1`**. Se razona aquí:

El descargo que sirve `api/` en `veredicto.descargo` es, literalmente:

> Ningún estado implica CAE garantizado. La emisión requiere dictamen favorable de verificador acreditado y
> solicitud por sujeto obligado o delegado.

Lo dice la ficha (`spec/IND240_v1.1.yaml`) y lo sirve el motor. Contiene las dos palabras porque **las está
negando**: es el texto que impide exactamente lo que la regla quiere impedir, y el "verificador acreditado"
que nombra es el organismo del RD 36/2023, no `A8`.

Reglas, para que la excepción no se convierta en una puerta:

1. El descargo **se muestra literal y completo**, sin reescribirlo ni recortarlo, junto al veredicto.
2. **No entra en el catálogo de textos del front.** Es dato del servidor, no texto de producto; el catálogo
   de la pantalla sigue pasando la lista completa de fórmulas prohibidas, sin excepciones.
3. En ningún texto propio de la pantalla se llama "verificador" a `A8`: sus salidas son **observaciones de
   prerrevisión**.

---

## 12. Criterios de aceptación

| Id | Hecho cuando… |
|---|---|
| `CA-REV-01` | **`R-UI-02`**: un recorrido de todo `front/workspace/` no encuentra ningún control cuyo valor o acción sea un veredicto (`PREVALIDADO`, `SUBSANABLE`, `BLOQUEADO`, `NO_ELEGIBLE`). El test recorre el árbol, no solo esta pantalla (`ADR-012` §5) |
| `CA-REV-02` | **`R-UI-04`**: con la justificación vacía o en blanco, el control de corregir no envía nada; y una petición forzada sin justificación es rechazada por `api/`. Las dos mitades se comprueban |
| `CA-REV-03` | **`R-UI-04`**: la justificación que escribe la persona aparece literal en el payload de `DatoCorregidoPorHumano`, y el front **no** la precarga: el campo nace vacío en todos los caminos de entrada al formulario |
| `CA-REV-04` | **`R-UI-05`**: con `estado_ciclo == "EN_PLATAFORMA"` y `requerimiento_abierto == null`, ningún control de escritura está activo; con requerimiento abierto, los del flujo de requerimiento sí, y el resto no |
| `CA-REV-05` | **`R-UI-09`**: ningún dato extraído se pinta sin su cita. El test recorre todos los datos del caso A y falla si alguno aparece sin `doc_id`, `pagina` y `texto_literal` accesibles desde su celda |
| `CA-REV-06` | **Caso C**: la tarjeta de conflicto de `PM` está por encima del bloque de ahorro en el DOM, muestra las cuatro evidencias con valor, documento, página, texto literal, método y confianza, y el ahorro se lee `SIN DATO` con el motivo. Falla si aparece `0` |
| `CA-REV-07` | **Caso C, en dos pulsaciones**: "Ver en el documento" cambia el documento del panel izquierdo a `05_certificado_instalador.pdf` página 1; "Usar este valor" abre el formulario con `variable="PM"`, `num_serie_motor="MTR-SYN-0001"` y `valor="90"` precargados y la justificación vacía |
| `CA-REV-08` | **Nada de coma flotante**: el `valor` enviado en `CAP-05` es una cadena. Un test que intente enviar un `number` recibe el error de `api/contrato._sin_coma_flotante` |
| `CA-REV-09` | **`GAP-REV-01` visible**: tras una corrección aceptada, el veredicto y el ahorro se marcan "pendiente de recálculo" y no se presentan como actualizados |
| `CA-REV-10` | **Caso A**: el ahorro se lee `305.829,6 kWh/año` con el rótulo "no son CAE emitidos", el truncado `305.829 kWh` con su etiqueta INT-06, y las seis líneas de procedencia con su cita o su origen de tabla |
| `CA-REV-11` | **Caso A**: los `INT-xx` aplicados aparecen rotulados como criterio propio no validado, nunca como norma; y la fila del cuadro 6 (110 kW → 5,55 kW) se muestra con su tabla de origen |
| `CA-REV-12` | **Caso B**: las dos carencias (`R-DOC-01`, `R-EVD-04`) se ven con su severidad y el documento que las subsana, la cifra sale marcada "estimación no acreditada" y "Aprobar" está inhabilitado con el motivo |
| `CA-REV-13` | **"Aprobar"**: activo únicamente con `veredicto.valor == "PREVALIDADO"` y sin conflictos ni carencias bloqueantes. Inhabilitado, muestra la regla concreta que lo impide y enlaza al dato |
| `CA-REV-14` | **`R-UI-03`**: ningún texto de la pantalla contiene "Firmar" como acción |
| `CA-REV-15` | **Textos**: el catálogo de textos de la pantalla pasa la misma lista de fórmulas prohibidas que `front/compartido/tests/textos.test.ts` (nada dice "CAE garantizado", nada "garantiza", A8 no se llama "verificador", ningún kWh prevalidado se presenta como CAE emitido). El descargo del servidor queda fuera del catálogo y se muestra literal: ver §11 bis |
| `CA-REV-16` | **Documento**: el panel izquierdo enseña los bytes que sirve `leer_documento` sin transformarlos, y el sha256 de lo que decodifica el cliente coincide con el `doc_id`. Con `ErrorIntegridad`, no se enseña nada y se avisa |
| `CA-REV-17` | **Parte de PDF combinado**: se muestra el aviso de `Respuesta.avisos` y el rango de páginas de la parte |
| `CA-REV-18` | **Errores**: `ErrorPermiso` y `ErrorApi` se muestran literales; el test falla si alguno se traga o se traduce a "no hay datos" |
| `CA-REV-19` | **Ruido**: con el caso A, las reglas que cumplen no ocupan el nivel visible (van plegadas tras un contador) y los datos que no entran en el cálculo tampoco |
| `CA-REV-20` | **El caso A recorre la pantalla entera** desde el simulador, sin datos inventados (`ADR-012` §5) |

---

## 13. Dejado fuera a propósito

- **Editar cualquier dato "porque sí".** Solo se corrigen datos que participan en un conflicto, un
  desacuerdo o una carencia. Una pantalla que permite reescribir los 31 datos es una pantalla en la que el
  humano sustituye al extractor y se pierde la trazabilidad de qué leyó el motor.
- **Comparar con otra actuación** o ver el expediente completo. Es `S4.1` / `FR3`.
- **Editar la spec, las severidades o los `INT-xx`** desde aquí. Son `CAP-50`/`CAP-51` de `ADM-MOD`, y
  además pasan por Billy (regla de oro 9). Desde la revisión se puede **señalar** una discrepancia
  (`CAP-16`), no cambiar la ficha.
- **Anotaciones libres sobre el documento.** Un resaltado que el revisor dibuja no es una evidencia y no
  debe poder confundirse con una.
- **Medición de minutos de revisión.** Esta pantalla es el punto de medida candidato (`ADR-006` B5), pero
  instrumentarla es decisión de Billy (`ADR-012` §6.2) y arrastra la revisión jurídica de la monitorización
  de trabajadores. No se instrumenta por iniciativa propia.
- **Traducción o accesibilidad formal.** C6 sigue abierta (idiomas y nivel exigido). Los textos se escriben
  en español, centralizados en un catálogo, para que internacionalizar después sea mover un fichero.
