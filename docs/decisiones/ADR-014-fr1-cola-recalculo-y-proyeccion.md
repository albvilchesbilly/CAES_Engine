# ADR-014 — FR1: la cola, el lazo del recálculo y lo que `api/` deja de esconder

**Estado: ACEPTADO en sus cuatro decisiones de Billy (23/09/2026). Los contratos C22–C26 son diseño de esta
sesión y se implementan en FR1.**

**Contexto**: `FR1` (workspace `T-REV`) tenía contrato y specs desde el 19/09/2026 y las pantallas pendientes.
Al arrancarlo, una auditoría de los **13 huecos de `api/`** que declaran `docs/front/pantallas/T-REV-cola.md`
§8 y `T-REV-revision.md` §10 contra el código de hoy (HEAD `62bd224`) cambió tres cosas del plan. Este ADR
recoge lo que se decidió y con qué contratos se construye.

Sustituye, en lo que discrepe, a las dos secciones de huecos de esas specs: **una de sus filas estaba
obsoleta y otra describía mal el problema**. Las specs se corrigen en FR1; este ADR es la fuente.

---

## 1. Lo que la auditoría cambió

Tres hallazgos que no estaban en la planificación:

1. **`GAP-REV-03` (subir un documento) ya está cerrado** en la forma de `CAP-02`: el comando rechaza
   `ruta`/`nombre_fichero`/`path`, exige `contenido` en bytes y la huella la calcula el núcleo
   (`api/comandos/actuaciones.py:113-144`, cerrado durante `/contrastar` el 20/09/2026). La spec describía
   un problema que ya no existe. Quedan dos flecos reales y distintos: el `Protocol` de
   `api/servicios.py:69` sigue declarando `registrar_documento(..., ruta: str)` y no declara
   `guardar_documento`, que el comando sondea con `getattr`; y el docstring del comando **afirma algo
   falso** ("no se puede ejercer de extremo a extremo": sí se puede con `RepositorioMemoria`).

2. **No existe capa HTTP en todo el repositorio**, y el sobre que `front/compartido/api/transporte.ts`
   describe asume una *sesión autenticada* que tampoco existe. Esto no es un hueco de `T-REV`: afecta a las
   trece pantallas por igual y estaba escondido dentro de la fila de un hueco concreto. Pasa a ser
   `GAP-HTTP-01`, transversal, en `docs/HUECOS.md`.

3. **`GAP-COLA-03`/`GAP-REV-07` (`origen_datos`) parecía barato y no lo es.** El campo es trivial; lo que no
   existe en ninguna parte del sistema es **de dónde sale el valor**: no hay noción de tenant sintético ni
   bandera de despliegue.

Y un hallazgo de seguridad que no era ninguno de los 13, en el camino exacto del recálculo: ver §5.

---

## 2. Decisión 1 — La cola cuelga de una capacidad nueva, no de un modo lista de `CAP-03`

**Billy, 23/09/2026.** La cola necesita una lectura que devuelva **varias** actuaciones del tenant;
`CAP-03`, `CAP-04` y `CAP-14` exigen `actuacion_id`.

Se descartó darle a `CAP-03` un modo lista. La razón no es de orden sino **de permisos**: `CAP-03` autoriza
hoy *consultar la actuación completa*, es decir **una**. Convertirla en «enumerar la cartera del tenant»
amplía su alcance de autorización sin que la matriz lo refleje, y quien la tuviera concedida para un caso
pasaría a poder listar todo el tenant. Un cambio de permisos no entra disfrazado de parámetro opcional: la
tabla de `ADR-006` tiene que seguir diciendo la verdad leyéndola.

**Contrato C22 — capacidad de cola.**

- Capacidad nueva de **lectura**, ámbito `tenant`, en `engine/capacidades.yaml`, concedida a `T-REV`.
- Bloque nuevo `cola` en `api/proyeccion.CONSTRUCTORES`, admitido por el ámbito `tenant`.
- Devuelve las filas **ya ordenadas por el servidor** (criterio de `T-REV-cola.md` §6). La pantalla no
  ordena ni recalcula: `R-UI-11`.
- Cada fila: identificación, veredicto, motivos, antigüedad y estado. Nada más: la cola no muestra valores
  de variables (arrastrar su cita a una lista, `R-UI-09`, es lo que la spec evita a propósito).
- La transcripción a mano de `tests/test_api_capacidades.py::MATRIZ_ADR` y la tabla de `ADR-006` se
  actualizan **a la vez**: ese test existe para fallar cuando divergen, y silenciarlo sería justo lo
  contrario de lo que esta decisión protege.

`ADR-006` queda modificado por este ADR en una fila. Es `PROPUESTA` y Billy ha aprobado esta adición.

---

## 3. Decisión 2 — El recálculo se dispara dentro de `CAP-05`

**Billy, 23/09/2026.** Corregir un dato recalcula en el acto.

El lazo «se corrige el dato y el motor recalcula» estaba **entero dentro de `engine/` y sin ningún
consumidor**: `procesar_actuacion` acepta `correcciones` (`engine/motor.py:183`), `de_log` las lee del log
(`engine/correcciones.py:266`) y la consolidación les da precedencia (`engine/evidencias.py:583`). `api/` no
importa nada de eso: `_correccion` sella el evento y devuelve (`api/comandos/actuaciones.py:160-180`).

La alternativa era una capacidad aparte de reproceso. Se descarta porque parte en dos, de cara a la persona,
lo que para ella es un solo acto, y porque obliga a tocar otra vez la matriz. Se acepta a cambio el coste
que `api/servicios.py:7-10` argumenta para no llamar al motor desde `api/`: **latencia de segundos dentro
del comando**. Es asumible mientras el reproceso sea de **una** actuación; si algún día hay que reprocesar
en lote, esta decisión se revisa y entonces sí hará falta separar el disparo.

**Contrato C23 — puerto de reproceso.**

```python
def reprocesar(self, actuacion_id: str) -> object:
    """Vuelve a procesar la actuacion aplicando las correcciones humanas de su log, y guarda el resultado."""
```

- Se añade al `Protocol` `Repositorio` y se implementa en `RepositorioMemoria`.
- Por dentro: `procesar_actuacion(carpeta, correcciones=de_log(log))`, y **sustituye** la `Actuacion`
  guardada, para que la siguiente lectura vea el veredicto nuevo.
- **`api/` sigue sin decidir nada**: no elige valores, no evalúa reglas, no fija veredicto. Pide al núcleo
  que rehaga su trabajo con una entrada más. La regla de oro 1 se mantiene.

**Contrato C24 — el disparo, y qué pasa si falla.**

- `_correccion` llama a `reprocesar` **después** de sellar el evento, nunca antes: el hecho de que una
  persona corrigió es un hecho aunque el recálculo se caiga.
- Si el reproceso falla, **el comando no falla**: devuelve la corrección sellada y un aviso que dice que el
  veredicto está pendiente de recálculo. Perder el evento sería perder el acto humano; ocultar el fallo
  sería peor que la latencia.
- `Salida.datos` incluye si el recálculo se hizo, para que la pantalla no presente como actualizado un
  veredicto que no lo está (`CA-REV-09`).

**Contrato C25 — `CorreccionRechazadaPostFirma` deja de ser un evento que nadie emite.**

Está en el catálogo y no lo emite nadie: `de_log` descarta en silencio la corrección posterior a la firma,
de modo que **quien corrige después de firmar no se entera de que su corrección se ignoró**. `ADR-013` §4 ya
lo reconocía. Al cerrar el lazo, el disparo compara lo que `de_log` admitió con lo que hay en el log y emite
el evento por cada corrección descartada.

> **Corregido el 23/09/2026, durante la implementación.** La primera redacción de este contrato decía «emite
> el evento» sin más, y eso **chocaba con la matriz de capacidades**. `api.comandos._comprobar_eventos_escritos`
> exige que todo evento de una `Salida` esté declarado en `capacidad.eventos`; meter
> `CorreccionRechazadaPostFirma` en `CAP-05` habría permitido que un `T-REV` sellara a mano «mi corrección fue
> rechazada» —o que **no** lo fue—, y el control de inalterabilidad se habría vuelto decorativo. La matriz
> tenía razón y el ADR estaba mal.
>
> Forma correcta, ya implementada: el evento lo sella el **actor `motor`** (`engine@ciclo`), ninguna capacidad
> lo concede a ningún perfil, y no se esconde: sale en `Salida.datos["rechazos_post_firma"]` y en un aviso por
> cada corrección descartada. Hay un test que fija la invariante
> (`test_ninguna_capacidad_concede_el_evento_de_rechazo_a_un_perfil`). Si algún día se quiere que viaje en
> `Respuesta.eventos`, eso es una decisión de diseño del contrato, no un detalle de implementación.

---

## 4. Decisión 3 — FR1 entrega pantallas contra el contrato, no una aplicación en un navegador

**Billy, 23/09/2026.** Las pantallas se construyen contra el cliente con el transporte **inyectado**, como
ya hacen los 98 tests de `front/compartido`.

Es lo honesto con lo que hay: el sobre está diseñado en un solo sitio, pero nada lo publica y el propio
sobre exige un principal autenticado que no existe. Levantar un servidor dentro de FR1 arrastraría
decisiones no tomadas —framework, sesiones, despliegue— y acabaría con media autenticación improvisada
dentro de un entregable de interfaz.

**Qué significa entonces «FR1 hecho»**, sin ambigüedad: las dos pantallas existen, cumplen sus criterios de
aceptación y están verificadas contra el contrato con un transporte de pruebas. **No se pueden abrir en un
navegador contra datos reales.** Esto se dice así en `docs/06`, para que nadie lea «FR1 hecho» y entienda
otra cosa.

`GAP-HTTP-01` (capa HTTP y sesión autenticada) es un entregable propio, con sus decisiones para Billy.

---

## 5. Decisión 4 — El control de inalterabilidad deja de fallar abierto

**Billy, 23/09/2026.** Se cierra dentro de FR1.

`_rechazados_por_el_ciclo` (`engine/correcciones.py:293-305`) proyecta el log para saber qué correcciones
rechazó la máquina de estados por ser **posteriores a la firma**. Si la proyección lanza, captura y devuelve
`frozenset()`: es decir, **un log que no se puede proyectar aplica todas las correcciones, incluidas las
prohibidas**. El docstring lo justifica con los logs de prueba y parciales.

Es el mismo patrón que `/contrastar` corrigió el 20/09/2026 en `api.contrato.comprobar_alcance`, y la misma
familia que H3: *un control que se desactiva justo cuando algo va mal no es un control*. La intención del
docstring es legítima; el precio no.

**Contrato C26 — distinguir el log parcial del log ilegible.**

- Un log **sin ninguna corrección** no tiene nada que filtrar: conjunto vacío **sin proyectar**.

  *Precisión del 23/09/2026, durante la implementación: la primera redacción decía «log vacío o sin eventos
  de ciclo», y era inexacta. Un `LogEventos` vacío **se proyecta perfectamente** y ya devolvía cero rechazos;
  lo único que el `except` protegía de verdad eran los logs `duck-typed` de las pruebas, que no son
  `LogEventos` y hacen levantar a `proyectar`. La condición correcta no es «el log está vacío» sino «no hay
  correcciones que filtrar», que cubre el vacío, el parcial y el doble de prueba sin rendir la guarda cuando
  sí hay una corrección delante.*
- Un log que **falla al proyectarse** no permite afirmar que no hay rechazos: `de_log` **levanta**, y el
  llamante decide. Nunca se aplican correcciones sobre un log cuyo ciclo no se ha podido leer.
- El test se escribe por **mutación**: volver al `except` que devuelve `frozenset()` tiene que romper algo.

---

## 6. Lo que se construye en FR1, y en qué orden

El contrato antes que las pantallas (`ADR-050`, no negociable), así que `FR1.c` empieza cuando `api/` está
cerrado.

| | Bloque | Contenido | Toca |
|---|---|---|---|
| `FR1.a` | Proyección y matriz | C22 (cola) · `GAP-REV-02` reglas con descripción · `GAP-REV-05` descripción de variables · `GAP-REV-09` traza y controles · `GAP-COLA-02` tareas y marcas de tiempo · `GAP-REV-06` pantalla `vista_revision` · `GAP-COLA-04`/`GAP-REV-08` cifra presentable | `api/proyeccion.py`, `api/lecturas/`, `engine/capacidades.yaml`, `engine/informe.py` |
| `FR1.b` | El lazo | C23, C24, C25, C26 · y los dos flecos de `GAP-REV-03` (el `Protocol` y el docstring que miente) | `api/servicios.py`, `api/comandos/actuaciones.py`, `api/repositorio.py`, `engine/correcciones.py` |
| `FR1.c` | Pantallas | `T-REV-cola` y `T-REV-revision` contra el contrato ya cerrado | `front/` |

`FR1.a` y `FR1.b` no comparten ni un fichero y van en paralelo.

**Se quedan fuera de FR1, declarados y no inventados:**

- `GAP-COLA-03`/`GAP-REV-07` (`origen_datos`): falta decidir de dónde sale el valor (§7). Mientras tanto
  `MarcaOrigen` pinta `ORIGEN DE DATOS SIN DECLARAR`, que es el comportamiento honesto que ya tiene.
- `GAP-REV-04` (interpretación propuesta de un requerimiento): bloque nuevo, campo nuevo en `Vista` y una
  capacidad que lo proyecte. En `FR1` el control de confirmar se deja **inactivo**: antes eso que confirmar
  a ciegas algo que no se ha podido leer.
- `GAP-HTTP-01`: §4.

---

## 7. Para Billy

| Qué | Por qué llega aquí |
|---|---|
| **`origen_datos`: de dónde sale** | `R-UI-08` obliga a declarar en todo panel si los datos son sintéticos o reales, y hoy el sistema no tiene forma de saberlo. Propuesta: campo obligatorio en la configuración del tenant, y si no está, `SIN DECLARAR` — nunca un valor por defecto, porque tanto asumir `REAL` como asumir `SINTETICO` es mentir en la mitad de los casos |
| **`GAP-HTTP-01`: capa HTTP y sesión autenticada** | Entregable propio. Arrastra framework, sesiones y despliegue, y bloquea que cualquier pantalla se use de verdad |
| **`GAP-REV-04`: interpretación propuesta** | Intermedio entre proyección y ADR. Decide si entra en `FR2` o antes |
| **Latencia de `CAP-05`** | Aceptada para una actuación (§3). Si aparece el reproceso en lote, hay que revisar esta decisión |

---

*`ADR-012` (workspace de revisión) y `ADR-013` (recálculo) siguen vigentes; este ADR los continúa y no los
sustituye. Donde este ADR y las dos specs de pantalla discrepen sobre el estado de `api/`, manda este ADR:
las specs se corrigen en `FR1`.*
