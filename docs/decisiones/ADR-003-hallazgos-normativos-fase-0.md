# ADR-003 — Hallazgos normativos del cierre de la Fase 0

**Estado**: PROPUESTA
**Fecha**: 2026-09-18
**Decide**: Billy (INT-11..INT-15, diffs de spec, fila 110 kW del cuadro 6, severidades) · Claude (nada: este ADR no aplica ningún cambio)
**Ámbito**: solo hallazgos. Ficheros escritos: este ADR y `spec/propuestas/IND240_v1.1_hallazgos_ADR-003.diff.md`. **No se ha tocado** `engine/`, `tests/`, `generator/`, `expedientes/`, `data/`, `evaluar_casos.py`, `spec/IND240_v1.1.yaml` ni `spec/propuestas/IND240_v1.2.diff.md`.

## Contexto

Revisión normativa de cierre de la Fase 0 exigida por `docs/06` §1 (fila «revisión», tras F0.9), sobre HEAD `84c90a4`. El encargo: contrastar **código contra spec contra fuente oficial** y sacar a la luz las **interpretaciones silenciosas** — constantes, redondeos, criterios de fecha, métodos de derivación, umbrales y desempates que ni la ficha IND240 V1.1, ni el RD 36/2023, ni la Orden TED/815/2023, ni el Reglamento (UE) 2019/1781 fijan, y que no están declarados como `INT-xx` (regla de oro 7).

Lo que sí es interpretación **bien hecha** y sirve de patrón: INT-06 (truncado a kWh entero) vive en `calculo.redondeo_salida` de la spec, el código exige que el criterio contenga la palabra `truncar` y lo cita en la traza (`engine/calculo.py:867-871`). El objetivo de este ADR es que los criterios que hoy no tienen ese trato lo tengan.

### Qué se pudo contrastar contra fuente oficial y qué no

**No he podido contrastar nada contra el texto oficial.** El proxy de egress denegó (403 / `EGRESS_BLOCKED`) todos los accesos intentados:

| Vía intentada | Resultado |
|---|---|
| `https://www.boe.es/buscar/doc.php?id=DOUE-L-2019-81609` | `EGRESS_BLOCKED` |
| `https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:32019R1781` | `EGRESS_BLOCKED` |
| `https://op.europa.eu/…` (Oficina de Publicaciones UE) | `EGRESS_BLOCKED` |
| `https://www.legislation.gov.uk/eur/2019/1781/2019-10-31` (EU retained law, reproduce los anexos) | `EGRESS_BLOCKED` |
| `https://www.miteco.gob.es/…` (catálogo y ficha IND240) | `403` del proxy en `CONNECT` |
| PDF CEMEP/CAPIEL (ABB, ZVEI), guía WEG (Roydisa), SEW-Eurodrive, noticias.juridicas, certificahorro | `EGRESS_BLOCKED` |

Solo funcionó el buscador (`WebSearch`), que devuelve **resúmenes de un modelo sobre el texto**, no el texto. De ahí salen dos **indicios** — no contrastes — que se registran como tales:

- **Indicio 1 (relevante para INT-02).** El propio Reglamento fija qué hacer con una potencia intermedia: «si la potencia aparente de salida de un variador se encuentra **entre dos valores del cuadro 6**, se utilizará el **valor de pérdidas de energía más alto** y el valor más bajo del factor de desplazamiento de la carga de ensayo». Eso es exactamente la **alternativa** de INT-02 («tomar la fila inmediatamente superior»), no nuestro `criterio_poc` (interpolación lineal). El Reglamento lo dice para determinar la clase IE del variador, no para la ficha CAE, así que no cierra INT-02 — pero invierte la carga de la prueba.
- **Indicio 2 (relevante para `cos_phi`).** Los resúmenes citan repetidamente una columna de **factor de desplazamiento de la carga de ensayo** en el cuadro 6. `data/README.md` («Sobre la columna `cos_phi`») afirma lo contrario: que el cuadro 6 solo tiene kVA, kW y pérdidas. Esa afirmación es **de memoria del agente** y hoy tiene un indicio en contra.
- **Ni un solo valor numérico del cuadro 6 apareció en ninguna fuente accesible.** La duda 5,55 frente a 6,11 kW para 110 kW (`ADR-002` §6.1) **queda exactamente donde estaba**: no he podido confirmarla ni refutarla.

Ficha IND240 V1.1: **no accesible** (MITECO bloqueado). Todo lo que este ADR dice sobre la ficha sale de lo que la spec cita (`SRC-FICHA §1/§2/§3 notas 1-3/§5.x`), no del PDF. Lo mismo con el RD 36/2023 y la Orden TED/815/2023 (arts. 11, 14.9.j, 17): no contrastados.

---

## Tabla de hallazgos

Impacto: **alto** = puede mover el ahorro o el veredicto de forma sustancial · **medio** = lo mueve en casos frontera o solo el provisional · **bajo** = documental o de borde.

| # | Dónde | Qué dice el código / la spec | Qué dice la fuente | Impacto | Propuesta |
|---|---|---|---|---|---|
| H-01 | `engine/registro_xlsx.py:449-462`; consume `R-EVD-01` (`registro.dias >= 30`) | `dias = n_filas × intervalo_modal / 60 / 24`: «días equivalentes de muestreo», contando el último intervalo. El intervalo es la **moda** de los saltos; si hay saltos distintos, aviso `registro_irregular` y se conserva la moda | La ficha (`SRC-FICHA §3 nota 1`, vía `EVD-01`) pide un registro «≥ 30 días». No dice si son días naturales de cobertura o días de muestra, ni qué hacer con huecos o muestreo irregular. No contrastado contra el PDF | **medio** (veredicto: un registro de 30 días naturales con huecos cae por debajo de 30 y pasa a `SUBSANABLE`; al revés no) | **Nuevo `INT-11`** |
| H-02 | `engine/registro_xlsx.py:455-457` + `variables.h_despues.derivacion` (INT-04) | `h_despues = 8760 × n_marcha / n_filas`: el intervalo se cancela, así que la extrapolación es una **razón de número de filas**, no de tiempo | INT-04 declara «horas en MARCHA × 8760 / horas del periodo». Con muestreo regular coincide; con `registro_irregular` **no**: la spec dice horas y el código cuenta filas | **alto** en registros irregulares (mueve `h_despues` y, por tanto, `h` y el ahorro) | **Nuevo `INT-11`** (mismo tema: qué es «el periodo» de un registro). Alternativa de ingeniería: ponderar por el salto real de cada fila |
| H-03 | `variables.h_antes` (spec) + `engine/extraccion.py:180,236`; ninguna regla lo comprueba | `h_antes` se consume tal cual lo declara el documento como horas **anuales**, sin extrapolación, sin periodo mínimo y sin ninguna regla que compruebe que el registro previo es representativo | `EVD-02` (`SRC-FICHA §3 nota 2`) exige «registro de horas de funcionamiento antes de la actuación (**periodo representativo**)». La ficha no define «representativo»; la spec no lo traduce a nada | **alto** (`h = min(h_antes, h_despues)` multiplica todo el ahorro; en A, B, C, D, E y G el `h` que manda es `h_antes`) | **Nuevo `INT-12`**. Asimetría llamativa: `h_despues` tiene INT-04 y `h_antes` no tiene nada |
| H-04 | `data/reg_2019_1781_cuadro6.meta.yaml` (`clave: kw_motor`), `variables.perdidas_ref_kw.clave: PM` | La tabla se indexa por la **potencia del motor (kW)** y se interpola sobre esa columna | El cuadro 6 del Reglamento se indexa por la **potencia aparente nominal de salida del variador (kVA)**; la columna de kW es el «motor de 4 polos correspondiente». El indicio 1 habla de «la potencia aparente de salida… entre dos valores del cuadro 6». Un variador sobredimensionado respecto al motor cae en otra fila según con qué columna se entre | **medio** (cambia la fila y con ella `p`; irrelevante cuando variador y motor se corresponden 1:1, como en A-G) | **Nuevo `INT-13`**. No lo cubre INT-01 (que discute el **denominador** de `p`, no la **entrada** a la tabla) |
| H-05 | `engine/reglas.py:811-835` (`_sustituir_entrada_ausente`) | Con veredicto `SUBSANABLE` y una sola entrada ausente que comparte derivada con otra presente, la ausente **toma el valor de la presente**: `h_despues` ausente → `h = h_antes`. Se publica 305.829 kWh en el caso B con el rótulo «estimación no acreditada» | La ficha (`SRC-FICHA §3 nota 2`) manda «considerar el **menor** de los valores». Sustituir el ausente por el presente equivale a **suponer `h_despues ≥ h_antes`**: si el real fuese menor, el provisional sobreestima. No es el criterio conservador de la ficha, es el contrario | **medio** (solo el ahorro provisional, pero es la cifra que el informe del caso B pone en cabecera) | **Nuevo `INT-14`**. La regla genérica además no está acotada a `min(...)`: cualquier derivada de dos entradas la activa (hoy solo existe `h`) |
| H-06 | `engine/extraccion.py:129-137` (`SENALES_CATEGORIA`) y `:1199-1206` (`categoria_de_linea`); consume `R-AMB-02` (`BLOQUEANTE_AMBITO`) | Un léxico de 7 categorías con **orden de prioridad** (`instalacion` antes que `motor`) decide, a partir de la cabeza de la línea de factura, si hay «equipo nuevo». Ese léxico vive en `engine/`, no en la spec | `EXC-01` y `EXC-02` (`SRC-FICHA §1`) excluyen la sustitución total o parcial del equipo y los equipos con variador incorporado. La ficha no da criterio documental para reconocerlo. Consecuencias del orden actual: «Instalación de motor nuevo» → `instalacion` → **no** dispara R-AMB-02; «Motor: rebobinado» → `motor` → **NO_ELEGIBLE** | **alto** (decide `NO_ELEGIBLE`, el veredicto más severo, con una heurística léxica) | **Nuevo `INT-15`** + diff: el léxico debe ser configuración de la ficha (bloque `lexico:`/`contexto:`), no código (regla de oro 4) |
| H-07 | `engine/expresiones.py:426-444` (`_sumar_fecha`); `R-TMP-03` `solicitud.fecha <= fecha_fin_actuacion + 3 años` | `+ 3 años` se computa por meses de calendario con recorte de día al último del mes (29/02 + 3 años = 28/02) y el límite es **inclusivo** (`<=`) | `SRC-ORDEN815 art. 17.1` (**no contrastado**). `docs/02` §5 sostiene que la plataforma aplica «3 años desde el **año** de finalización, vencimiento el 31/12», que es lo que propone `INT-08` en el diff v1.2 — todavía no aprobado | **bajo** hoy (R-TMP-03 es `AVISO` y no cambia el veredicto); **medio** si INT-08 se aprueba con otra severidad | **Sin INT nuevo**: es el criterio efectivo de v1.1 bajo INT-08. Diff: declarar `interpretacion: INT-08` en `R-TMP-03` de v1.1 y añadir a INT-08 el cómputo de día y la inclusividad del límite |
| H-08 | `engine/reglas.py:167-178` (`ALIAS_CONTEXTO`), `engine/motor.py:191` (`date.today()`) | `solicitud.fecha` = fecha de evaluación (INT-10, propuesto en `ADR-002` §3). Por defecto `date.today()` del contenedor, sin zona horaria declarada | No hay solicitud presentada en prevalidación; ninguna fuente fija qué fecha usar. **Efecto secundario no documentado**: con la fecha de hoy, `R-TMP-02` (convenio firmado antes de la solicitud, `SUBSANABLE`) **es estructuralmente incapaz de fallar** — cualquier convenio ya firmado es anterior a hoy | **medio** (una regla que nunca puede fallar da una garantía falsa en el informe) | **`INT-10` documentado en forma** (§«INT-10 en forma» más abajo), con el efecto sobre R-TMP-02 explícito y la zona horaria fijada |
| H-09 | `variables.P_prom.tolerancia_cruce_kw: 0.5` y `cruce_con: [certificado_instalador]` | El campo **no lo lee nadie**: no aparece en `engine/` (solo en `generator/ground_truth.py:196`). `engine/evidencias.py:41` delega expresamente las tolerancias a las reglas, y **no hay regla** que cruce `P_prom` declarado contra derivado (las hay para PM, N1, N2, series, NIF y nº de motores) | La ficha (`SRC-FICHA §5.5.b`) exige que el certificado acredite `P_prom` y `N2` con el registro. La spec declara el cruce y el motor no lo hace | **medio** (un certificado que declare una `P_prom` incompatible con el registro pasa sin aviso; solo la atrapa `FIS-02` si además supera `PM`) | **Diff**: nueva regla `R-CON-08` (`abs(P_prom.declarado - P_prom.derivado) <= 0.5`, `SUBSANABLE`), simétrica de `R-CON-03`; o retirar el campo si el cruce no se quiere |
| H-10 | `variables.N2.derivacion.periodo_minimo_dias: 30` | Campo declarado en la spec y **no leído por el motor**. El 30 efectivo está duplicado en la `logica` de `R-EVD-01` | La ficha da el mínimo de 30 días una sola vez (`SRC-FICHA §3 nota 1`). Dos declaraciones del mismo número, una muerta: cambiar una y no la otra no rompe ningún test | **bajo** | **Diff**: o `R-EVD-01` lee `variables.N2.derivacion.periodo_minimo_dias`, o se retira el campo de la spec |
| H-11 | `engine/tablas.py:150-200` + `data/README.md` | Fuera del rango de la tabla (`PM < 0,12` o `> 1.000` kW) no se extrapola: `valor = null`, aviso, la unidad no calcula. Decidido en F0.2 (`ADR-002` §3) | `variables.perdidas_ref_kw.si_no_existe_fila: INT-02` cubre **solo** la interpolación. El «fuera de rango no se calcula» no está en la spec | **bajo** (el ámbito del Reglamento y el `rango_plausible` de `PM` coinciden) | **Diff**: declarar `si_fuera_de_rango: no_calcula` en la spec. Criterio correcto, pero hoy vive solo en el código |
| H-12 | `spec` §8 `INT-02`; `engine/tablas.py:189-198` | `criterio_poc`: interpolación lineal entre filas adyacentes, con aviso | **Indicio 1**: el Reglamento, para una potencia entre dos valores del cuadro 6, manda tomar **el valor de pérdidas más alto**. Es la `alternativa` declarada de INT-02, no nuestro criterio. Menos ahorro, más conservador | **bajo** hoy (A-G tienen fila exacta y `R-CAL-02` da CUMPLE en los 7 casos), **medio** en actuaciones reales con PM fuera de la serie | **Documentar mejor INT-02**: registrar el indicio, invertir la recomendación por defecto a la `alternativa` salvo que el verificador diga otra cosa. **No se cierra aquí** |
| H-13 | `data/reg_2019_1781_cuadro6.csv` (38 de 39 filas `verificado: pendiente`) | Transcripción **de memoria del agente**. Solo la fila de 110 kW está en `si`, y es justamente la que `ADR-002` §6.1 pone en duda (5,55 frente a 6,11 kW; pérdidas/PM = 5,05 % frente a 5,5-5,9 % en toda la serie vecina) | **No contrastado**: el DOUE y el BOE están bloqueados y ninguna fuente accesible reproduce el cuadro | **alto** (55 kW sostiene el caso E, 160 kW el caso F, 110 kW el criterio de aceptación de 305.829,6 kWh/año) | **Nada que yo pueda cerrar.** Verificación humana fila a fila contra el DOUE. El motor ya avisa por fila usada sin verificar (comprobado en el caso E) |
| H-14 | `data/README.md`, sección «Sobre la columna `cos_phi`» | Afirma que el cuadro 6 no contiene columna de factor de potencia y por eso `cos_phi` va vacía en las 39 filas | **Indicio 2**: los resúmenes del texto oficial mencionan una columna de **factor de desplazamiento de la carga de ensayo** en el cuadro 6. La afirmación del README es de memoria y hoy tiene un indicio en contra | **bajo** (la columna no entra en ninguna fórmula) | **Nada en `data/` (fuera de mi alcance)**: corregir la afirmación del README cuando se verifique el cuadro, y decidir entonces si `cos_phi` se rellena o se retira de la spec |
| H-15 | `engine/calculo.py:69` (`PRECISION_DECIMAL = 34`) | Precisión fija de 34 dígitos en `localcontext`, decidida en F0.3 tras el hallazgo QA H9 (con 6 dígitos el caso A daba 305.830) | `calculo.aritmetica: decimal_exacta` en la spec no fija ninguna precisión. Es un parámetro numérico que **ya demostró** poder mover el resultado | **bajo** con los valores actuales (el caso A es exacto en decimal), pero es una constante de cálculo no declarada | **Diff**: declarar `calculo.precision_decimal: 34` en la spec, como se hace con el criterio de redondeo |
| H-16 | `spec` `ambito.tipos_equipo_excluidos`; `R-AMB-01` | `R-AMB-01` solo comprueba pertenencia a `tipos_equipo_incluidos`. La lista de excluidos **no la lee nadie** en `engine/`. Un tipo desconocido (mal extraído, nombre de fabricante) cae en `NO_ELEGIBLE` igual que uno explícitamente excluido | `EXC-03` (`SRC-FICHA §1`) excluye desplazamiento positivo. «No reconocido» y «excluido por la ficha» son cosas distintas: lo primero es falta de evidencia (`SUBSANABLE`), lo segundo es ámbito (`NO_ELEGIBLE`) | **medio** (un error de extracción se convierte en el veredicto más severo, sin subsanación posible) | **Diff**: `R-AMB-01` distingue los tres casos (incluido / excluido → `NO_ELEGIBLE` / desconocido → `SUBSANABLE`), usando la lista de excluidos que la spec ya declara |
| H-17 | `engine/clasificacion.py` (`SUBTIPO_FOTO_ANTES`/`DESPUES`), `engine/extraccion.py:918,1109`; consume `R-DOC-02` | Que una foto sea «antes» o «después» lo decide un léxico de pie de foto / EXIF en `engine/` | `DOC-04` (`SRC-FICHA §5.4`) exige foto antes y después con placa legible. La ficha no dice cómo se acredita cuál es cuál | **bajo** (`R-DOC-02` es `SUBSANABLE`) | Mismo diff que H-06: el léxico es configuración de la ficha, no código |
| H-18 | `docs/04` §12 y §13.1; informe del caso A | `interpretaciones_aplicadas` lista **INT citados por reglas evaluadas**, no INT que influyeron: el caso A muestra INT-02 aunque tenga fila exacta y no se interpole nada | `docs/04` §13: «el informe lista las interpretaciones que **han influido** en el resultado». Código y documento no dicen lo mismo | **bajo** (ruido en el informe; diluye el valor de la lista) | Ya identificado en `ADR-002` §6.5. **Diff**: campo por regla que distinga «cita» de «aplica»; hasta entonces, corregir la frase de `docs/04` §13 |
| H-19 | `engine/reglas.py:364-391`; `DOC-05B` | `obligatorio: condicional` cuya `condicion` no se puede evaluar → el documento **no** es obligatorio, con aviso (F0.9) | `SRC-FICHA §5 nota`: el certificado de técnico competente es obligatorio **si** la instalación la hace personal propio. Ningún documento del paquete declara `instalacion_personal_propio`, y la spec no lo declara como variable | **medio** (un documento que la ficha puede exigir se da por no exigido) | Ya en `ADR-002` §6.4. **Diff**: declarar `instalacion_personal_propio` como variable de cabecera `declarado`; mientras tanto, que el aviso sea `SUBSANABLE` en lugar de un aviso mudo |
| H-20 | `engine/extraccion.py:1244-1320`; `R-CON-07` (`BLOQUEANTE_DATOS`) | `n_motores` de un tipo documental sin campo explícito = nº de nº de serie distintos observados | Ninguna fuente fija cómo se cuenta. Si a una actuación real le falta la documentación de un motor, falla `R-CON-07` → **`BLOQUEADO`** en lugar de `R-DOC-01` → `SUBSANABLE` | **medio** (convierte una carencia documental en un bloqueo) | Ya en `ADR-002` §6.6. Decisión de severidad de Billy; no la tomo |
| H-21 | Textos de producto: `engine/informe.py`, `README.md`, `docs/`, `spec` | «CAE garantizado» aparece **solo** en descargos y negaciones (`spec` `estados.descargo`, `README.md:39`, `docs/00` §4 y §6, `docs/03` §13, `docs/04` §4.1, `docs/07` §81, `docs/08` §134, `MISION_VISION.md`). `engine/informe.py:130-133,258-260,616` toma el descargo **de la spec**, no de una constante. A8 nunca se llama «verificador» (`docs/03` §11 y §428, `docs/04` §12 y §459 lo prohíben expresamente). El ahorro provisional lleva el rótulo «estimación no acreditada» (`engine/informe.py:51,330`) | `CLAUDE.md` §2 y `docs/00` §2 | — | **Conforme. Nada que proponer** |
| H-22 | `engine/calculo.py:837-871` | Precisión 34, truncado `ROUND_DOWN` **del total** y no por unidad, `AEM` sin redondeo interno | Todo declarado en `calculo.redondeo_salida` con `interpretacion: INT-06`, y el código exige que el criterio contenga «truncar». La alegación de `docs/00` §5.6 al art. 8.3 del RD pide precisamente que la norma fije método, unidad y **nivel** (actuación o expediente) | — | **Defendible tal como está.** Nota: INT-06 fija el nivel «actuación»; el nivel «expediente» sigue sin norma |

### Interpretaciones nuevas propuestas (INT-11 .. INT-15)

Redactadas en el formato de `spec` §8 para que Billy pueda aprobarlas o rechazarlas como bloque. **Ninguna se aplica aquí**: la spec activa no se toca.

```yaml
  - id: INT-11
    tema: "Qué es «el periodo» de un registro de funcionamiento"
    criterio_poc: >-
      periodo = nº de filas × intervalo de muestreo modal (el último intervalo cuenta);
      `registro.dias` = ese periodo / 24 h; la extrapolación anual de INT-04 es, en la práctica,
      8760 × filas en MARCHA / filas totales (razón de filas, no de tiempo).
    alternativa: >-
      (a) periodo = diferencia entre el primer y el último instante registrado (cobertura natural);
      (b) ponderar cada fila por su propio salto temporal cuando el muestreo es irregular.
    impacto: medio          # veredicto (frontera de 30 días); alto sobre el ahorro si el registro es irregular
    cierra: verificador acreditado (qué acredita «30 días» a efectos de la ficha) / sandbox
    afecta: [R-EVD-01, INT-04, variables.h_despues]

  - id: INT-12
    tema: "Carácter anual y representatividad de h_antes"
    criterio_poc: >-
      h_antes se consume tal como el registro previo (EVD-02) lo declara, como horas anuales,
      sin extrapolación, sin periodo mínimo y sin ninguna regla que compruebe la representatividad.
    alternativa: >-
      (a) exigir un periodo mínimo al registro previo y extrapolar con el mismo criterio que INT-04;
      (b) exigir 12 meses o plan de producción, como pide la alternativa de INT-04 para h_despues.
    impacto: alto           # h = min(h_antes, h_despues) multiplica todo el ahorro
    cierra: verificador acreditado (qué es «periodo representativo» en la nota 2 de la ficha)
    afecta: [variables.h_antes, variables.h, EVD-02]

  - id: INT-13
    tema: "Con qué columna se entra al cuadro 6 del Reglamento (UE) 2019/1781"
    criterio_poc: >-
      se busca la fila por la potencia nominal del motor (kw_motor = PM).
    alternativa: >-
      entrar por la potencia aparente nominal de salida del variador (kVA), que es la magnitud con la
      que el Reglamento indexa el cuadro y a la que se refiere su propia regla de valores intermedios.
    impacto: medio          # cambia la fila y con ella p cuando variador y motor no se corresponden 1:1
    cierra: verificador acreditado / sandbox (batería INT-xx, TODO(API-12))
    afecta: [variables.perdidas_ref_kw, variables.p, INT-01, INT-02, R-CAL-02]

  - id: INT-14
    tema: "Cálculo provisional cuando falta una de las dos entradas del menor de h"
    criterio_poc: >-
      con veredicto SUBSANABLE, la entrada ausente toma el valor de la presente
      (h_despues ausente → h = h_antes); el resultado se rotula «estimación no acreditada».
    alternativa: >-
      (a) no publicar ahorro alguno cuando falta una entrada del menor;
      (b) publicar un intervalo [0, AEM(h_antes)] en lugar de un valor puntual.
    impacto: medio          # solo el ahorro provisional, pero equivale a suponer h_despues >= h_antes,
                            # que es lo contrario del criterio conservador de la nota 2 de la ficha
    cierra: Billy (criterio de producto) + verificador acreditado (qué se puede presentar como estimación)
    afecta: [variables.h, engine/reglas.py::_sustituir_entrada_ausente]

  - id: INT-15
    tema: "Cómo se reconoce documentalmente un «equipo nuevo» (EXC-01, EXC-02)"
    criterio_poc: >-
      léxico de categorías sobre la cabeza de cada línea de factura, con prioridad
      instalacion > variador > equipo_completo > motor > bomba > ventilador > compresor > otro.
    alternativa: >-
      (a) declaración responsable expresa del instalador de que el equipo accionado no se sustituye;
      (b) cruce con el nº de serie del motor previo al registro de horas (mismo motor antes y después).
    impacto: alto           # decide NO_ELEGIBLE; hoy «Instalación de motor nuevo» no dispara R-AMB-02
                            # y «Motor: rebobinado» sí lo dispara
    cierra: verificador acreditado (qué evidencia acredita que el equipo es existente)
    afecta: [R-AMB-02, EXC-01, EXC-02]
```

### INT-10 en forma

`INT-10` nació como decisión de reconstrucción (`ADR-002` §3, fila «plan») y hoy llega al informe sin tema, sin alternativa y sin impacto: el JSON del caso A la imprime como `tema: "criterio del motor de reglas, no declarado en la spec"`. Propuesta de redacción completa para que Billy la apruebe o la rechace:

```yaml
  - id: INT-10
    tema: "Qué fecha es «la fecha de solicitud» en prevalidación"
    criterio_poc: >-
      en prevalidación no existe solicitud presentada: `solicitud.fecha` se resuelve como la fecha de
      evaluación del motor (`--fecha`, por defecto la del día en la zona horaria del servidor).
    alternativa: >-
      (a) dejar `solicitud.fecha` ausente y aceptar que R-TMP-02 y R-TMP-03 salgan NO_EVALUABLE
          en todas las actuaciones (la carencia la recogería la garantía NO_EVALUABLE → SUBSANABLE);
      (b) tomar la fecha de firma de la ficha cumplimentada (no es la solicitud, pero es un acto real);
      (c) exigir al usuario una fecha de presentación prevista y no calcular sin ella.
    impacto: medio
    efecto_conocido: >-
      con la fecha del día, R-TMP-02 («convenio firmado antes de la solicitud», SUBSANABLE) es
      estructuralmente incapaz de fallar: cualquier convenio ya firmado es anterior a hoy. El informe
      presenta como comprobada una condición que el motor no ha podido poner a prueba.
    cierra: Billy (criterio de producto) + confirmación contra la Orden TED/815/2023 art. 11.3 y el
      comportamiento de la plataforma (sandbox)
    afecta: [R-TMP-02, R-TMP-03, ALIAS_CONTEXTO de engine/reglas.py]
```

Añadido menor: fijar la zona horaria de `date.today()` (`engine/motor.py:191`) o exigir `--fecha` en producción; hoy dos ejecuciones en días distintos pueden dar resultados distintos y eso contradice la pureza que `docs/04` §1 exige al Rules Engine.

### INT-01 .. INT-07: comprobación de aplicación

| INT | Dónde dice la spec que se aplica | Se aplica ahí | Observación |
|---|---|---|---|
| INT-01 | `variables.p.derivacion.interpretacion` | Sí (`engine/calculo.py::_derivar_expresion`, aparece en `interpretaciones_aplicadas` del caso A) | Abierta. La alternativa (kVA) sigue sin contrastar contra la ficha |
| INT-02 | `variables.perdidas_ref_kw.si_no_existe_fila`, `R-CAL-02` | Sí (`engine/tablas.py:189-198`) | Abierta. Ver H-12: el propio Reglamento parece prescribir la alternativa. **No cerrada** |
| INT-03 | `variables.N2.derivacion.interpretacion` | Sí (`engine/registro_xlsx.py`, método `media_en_marcha`) | Abierta. Pendiente: qué hacer con muestreo irregular (media sin ponderar) → H-02 |
| INT-04 | `variables.h_despues.derivacion.interpretacion` | Sí | Abierta. El «8760» ignora años bisiestos (8.784 h); documentarlo dentro de INT-04 |
| INT-05 | `EVD-01`, `R-EVD-03` | Sí (`engine/registro_xlsx.py`, datos canónicos + SHA-256; `R-EVD-03` recalcula) | Abierta. El formato canónico concreto (`fecha;estado;rpm;kW`) es nuestro, no de la norma |
| INT-06 | `calculo.redondeo_salida` | Sí (`engine/calculo.py:867-871`) | **Modelo a seguir.** Lo que sigue abierto es el **nivel** (actuación vs expediente): alegación al art. 8.3 |
| INT-07 | Ninguna regla (Di, fines estadísticos) | No aplica | Correcto: el Engine no lo valida, tal como declara la spec |

**Ninguno de los siete se ha cerrado en silencio.** Los siete siguen declarados en `spec` §8 y el motor los cita.

---

## Opciones consideradas

1. **Escribir los INT-11..15 directamente en `spec/IND240_v1.1.yaml`.** Rechazada: rompe la regla de oro 9 y el encargo. La spec activa no se toca.
2. **Ampliar `spec/propuestas/IND240_v1.2.diff.md`.** Rechazada: ese diff ya está pendiente de Billy y mezclarlo con hallazgos nuevos impediría aprobar uno sin el otro.
3. **Diff propio en `spec/propuestas/`, independiente y acumulable con el v1.2.** Elegida.

## Decisión

Este ADR **no decide nada**: registra 22 hallazgos, propone cinco interpretaciones nuevas (INT-11..INT-15), redacta INT-10 en forma y deja el diff correspondiente en `spec/propuestas/IND240_v1.1_hallazgos_ADR-003.diff.md`. Todo queda en `PROPUESTA` para Billy.

**Recomendación**, si hay que priorizar: H-03 (INT-12, `h_antes` sin ningún criterio) y H-06 (INT-15, léxico de factura decidiendo `NO_ELEGIBLE`) son los dos hallazgos que más pueden doler en una actuación real; H-13 (cuadro 6 sin verificar) es el que más puede doler en el banco de pruebas.

## Consecuencias

- **Código**: ninguna. No se ha tocado un solo fichero de `engine/`, `tests/`, `generator/`, `expedientes/`, `data/` ni `evaluar_casos.py`. `pytest` y `evaluar_casos.py` no se ven afectados por este ADR.
- **Spec**: nada activo. Un fichero nuevo en `spec/propuestas/`.
- **`docs/04` §13**: cuando Billy apruebe, §13.2 pasa a listar INT-08..INT-15 y §13.1 recoge las que se activen; propuesta de redacción en el diff.
- **`docs/HUECOS.md`**: **ningún hueco `API-xx` nuevo.** Todo lo encontrado cae dentro de `API-04` (presencia vs contenido) y `API-12` (criterio oficial de cálculo y acreditación de N2), que ya están abiertos. Sugerencia: añadir INT-11..INT-15 a la lista de criterios que `API-12` bloquea.
- **Abierto**: todo lo de §«Para Billy».

## Qué solo puede cerrar un verificador acreditado o el sandbox de la plataforma

No lo cierra este ADR, ni Billy solo, ni ningún agente:

| Qué | Quién puede cerrarlo | Por qué |
|---|---|---|
| INT-01 (denominador de `p`), INT-13 (columna de entrada al cuadro 6) | Verificador acreditado; confirmación empírica en el sandbox comparando con el cálculo oficial | Es la lectura de la nota 3 de la ficha sobre el cuadro 6; nosotros no tenemos autoridad interpretativa |
| INT-02 (potencia sin fila exacta) | Verificador acreditado; sandbox (`R-XCK-01`, `TODO(API-12)`) | El indicio del Reglamento es para la clase IE, no para la ficha CAE |
| INT-03 (N2 «media anual» con 30 días), INT-11 (qué es «el periodo»), INT-04 (extrapolación) | Verificador acreditado | Qué acredita una media anual es juicio de verificación, no de cálculo |
| INT-12 (representatividad del registro previo) | Verificador acreditado | «Periodo representativo» es indeterminado en la propia ficha |
| INT-05 (registro inalterable) | Verificador acreditado | Qué prueba de inalterabilidad acepta lo decide quien verifica |
| INT-14 (qué se puede publicar como ahorro provisional) | Billy (producto) + verificador (qué admite como estimación) | Mixto |
| INT-15 (cómo se acredita que el equipo es existente) | Verificador acreditado | Es la aplicación de EXC-01/EXC-02 a evidencia documental |
| INT-08 (expiración) y el cómputo de H-07 | Texto del art. 17 Orden TED/815/2023 (BOE) + comportamiento de la plataforma | Es una regla de plazo, no una interpretación técnica |
| INT-06 a nivel expediente | BOE (art. 8.3 del RD, si la modificación lo fija) | Es exactamente lo que pide la alegación de `docs/00` §5.6 |
| Cuadro 6: fila de 110 kW y las 38 `pendiente` | DOUE / BOE, verificación humana fila a fila | Dato normativo transcrito de memoria; no es interpretable, es contrastable |
| API-04 (si la plataforma valida contenido o solo presencia) | Sandbox / diccionario oficial | Ya abierto en `docs/HUECOS.md` |

## Para Billy — decisiones que quedan (no las he tomado)

1. **Aprobar o rechazar INT-11, INT-12, INT-13, INT-14, INT-15** como bloque, o pedir que alguna se resuelva en el código (en cuyo caso deja de ser INT).
2. **Aprobar INT-10 con la redacción de este ADR** (incluido el efecto sobre `R-TMP-02`), o elegir una de sus tres alternativas.
3. **Cuadro 6: fila de 110 kW (5,55 frente a 6,11 kW).** Sigue abierta. No he podido contrastar; el indicio de la serie (`ADR-002` §6.1) sigue siendo el único argumento y no es prueba. Si cambia, cambia INT-01, el caso A y el criterio de aceptación de 305.829,6 kWh/año: ADR nuevo, no parche.
4. **Verificación fila a fila de las 38 filas `pendiente`**, con prioridad en 55 kW (caso E) y 160 kW (caso F).
5. **`cos_phi`**: mantener la columna vacía, rellenarla con el factor de desplazamiento del cuadro 6 (si el indicio 2 se confirma) o retirarla de la spec.
6. **`R-CON-08`** (cruce de `P_prom` declarado contra derivado con la tolerancia que la spec ya declara): crearla o retirar `tolerancia_cruce_kw`.
7. **`R-AMB-01`**: ¿un tipo de equipo **no reconocido** debe ser `NO_ELEGIBLE` (hoy) o `SUBSANABLE`?
8. **`R-CON-07`** (`n_motores`): ¿`BLOQUEANTE_DATOS` (hoy) o `SUBSANABLE`? Ya planteado en `ADR-002` §6.6; este ADR lo confirma con el mecanismo concreto (conteo por nº de serie distintos).
9. **`DOC-05B` / `instalacion_personal_propio`**: declararlo como variable de cabecera o dejar el documento como no obligatorio con aviso. Ya en `ADR-002` §6.4.
10. **Léxicos en `engine/`** (categorías de línea de factura, fotos antes/después): mover a un bloque de configuración de la ficha en v1.2 (regla de oro 4) o aceptarlos como marco genérico documentado.
11. **`calculo.precision_decimal`**: declararla en la spec o dejarla como constante del motor.
12. **`docs/04` §13**: la frase «interpretaciones que **han influido** en el resultado» no describe lo que hace el código (lista las citadas). Corregir el documento o el código.

## Verificación

- `git status` limpio salvo `docs/decisiones/ADR-003-hallazgos-normativos-fase-0.md` y `spec/propuestas/IND240_v1.1_hallazgos_ADR-003.diff.md`.
- `python -m pytest -q` y `python evaluar_casos.py` **no deben cambiar** por este ADR (no toca código ni spec activa).
- Reproducción de los hallazgos observados en ejecución:
  `python -m engine.cli expedientes/EXP001-A_completo --json a.json --silencioso` → `interpretaciones_aplicadas` incluye INT-02 sin haber interpolado (H-18) e INT-10 sin tema ni impacto (H-08); `R-TMP-02` y `R-TMP-03` salen `CUMPLE`.
  `python -m engine.cli expedientes/EXP001-E_dos_motores --json e.json --silencioso` → aviso `tabla REG1781_CUADRO6 pendiente de verificacion humana (filas usadas sin verificar: kw_motor = 55)` (H-13).
- Contraste con fuente oficial: **no realizable en este entorno**; repetir cuando el proxy permita `boe.es` o `eur-lex.europa.eu`.
