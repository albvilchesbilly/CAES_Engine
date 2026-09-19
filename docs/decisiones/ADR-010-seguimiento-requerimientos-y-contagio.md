# ADR-010 — Seguimiento post-envío, requerimientos y contagio de expediente (S3.5)

**Estado**: ACEPTADA (técnica) · PROPUESTA (§7, lo que decide Billy)
**Fecha**: 2026-09-19
**Decide**: Claude (técnica) · Billy (lo marcado `PROPUESTA` en §7)
**Ámbito**: `engine/seguimiento.py`, `engine/requerimientos.py`, `salida/seguimiento.py`, `generator/`,
`spec/propuestas/`, `tests/`, `docs/01`, `docs/03` §10.5, `docs/04` §10.4

## Contexto

S3.4 dejó la salida: el paquete sale y el simulador lo acepta. S3.5 es **lo que pasa después**, que es donde
está el dinero y el riesgo: la actuación vuelve con un requerimiento y hay que reabrirla con la regla
correcta, sin perder trazabilidad y sin reabrir de más.

Tres orígenes, tres alcances distintos (`docs/03` §10.5, `docs/02` §5.6):

| Origen | Llega como | A quién alcanza | Por qué importa |
|---|---|---|---|
| `verificador` | `PDTE_RECTIFICACION_VER` + motivos (+ informe PDF) | La actuación, o el grupo con dictamen único | Se corrige y se reenvía; coste acotado |
| `GA` | Requerimiento en fase 3A | **Todo el expediente** | Una actuación mala bloquea a todas sus compañeras |
| `CN` | Requerimiento en fase 3B, con posible segunda ronda | **Todo el expediente** | Ídem, más tarde y más caro |

El **contagio** es el riesgo de negocio más caro del modelo: un expediente es una agregación de actuaciones que
se aprueba o se rechaza en conjunto. Que el motor lo refleje mal —de menos o de más— cuesta dinero real al
tenant. Por eso es lo primero que se prueba aquí.

## 1. El choque con una decisión abierta, y cómo se resuelve

`docs/06` describe S3.5 sobre `agentes/runtime/` y `agentes/redactor/`, porque **A9 (intérprete de
requerimientos) es un agente con LLM**. Pero el Agent Runtime es S3.6 y está `BLOQUEADO` esperando la decisión
de Billy sobre proveedor LLM y condiciones de datos (`CLAUDE.md` §6). Construir S3.5 *después* de esa decisión
dejaría parado todo el circuito post-envío, que no depende de ningún LLM.

**Decisión: se aplica `CLAUDE.md` §6 — se hace todo lo que no depende de la decisión y se deja la alternativa
preparada.** En concreto, y siguiendo el precedente que ya funcionó en la Fase 0 con `Extractor`:

- **A9 se convierte en una interfaz, `Interprete`**, con una implementación **determinista por léxico** en
  `engine/requerimientos.py`. Es exactamente el patrón de `engine/extraccion.py`: la interfaz y el motor por
  reglas viven en el núcleo, y la variante con LLM entrará en `agentes/redactor/` en S3.6 **sin tocar nada
  más**. Con el LLM apagado el circuito funciona: modo degradado, como manda la regla de oro.
- **La puerta humana no depende del intérprete.** `R-REQ-02` exige confirmación humana antes de reabrir, y eso
  se cumple igual venga la interpretación de un léxico o de un modelo. Se implementa una sola vez, aquí.
- **`agentes/` sigue sin existir.** No se crea una carpeta vacía para cumplir un plan: se crea cuando haya algo
  que poner dentro.

Lo que **queda fuera** de S3.5 y se declara: A5 (redacción de la petición de subsanación al cliente) es S4.2 y
necesita el runtime · el intérprete con LLM es S3.6 · la composición de expedientes (`R-GRP`, `R-EXP`) es S4.1
y es decisión de Billy. Aquí el `Expediente` se **recibe**, no se compone.

## 2. Contrato C9 — seguimiento (`engine/seguimiento.py`)

P9 vive en el núcleo porque es determinista y tiene que funcionar con la periferia apagada. Como `engine/` no
puede importar de `salida/`, el seguimiento trabaja sobre **datos planos**, no sobre los tipos del puerto; el
puente lo pone `salida/seguimiento.py` (C11).

```python
class ErrorSeguimiento(Exception): ...

@dataclass(frozen=True) class EstadoRecibido:
    referencia, literal, nivel, oficial: bool, instante: datetime, motivos: tuple[str, ...]
@dataclass(frozen=True) class TareaRecibida:
    id, tenant_id, asunto, instante: datetime, referencia: str | None, vence_en: date | None

def indexar(actuaciones) -> dict[str, str]          # codigo_identificativo_propio -> actuacion_id
def actuacion_de(recibido, indice) -> str           # reconciliacion; ErrorSeguimiento si no cuadra
def registrar_estado(log, recibido) -> Evento       # EstadoPlataformaRecibido, actor `plataforma`
def registrar_tarea(log, tarea) -> Evento           # TareaPendienteRecibida, actor `plataforma`
def sincronizar(logs, recibidos, *, indice) -> Sincronizacion
@dataclass(frozen=True) class Sincronizacion:
    proyecciones: Mapping[str, Proyeccion]
    eventos: tuple[Evento, ...]
    desconocidos: tuple[str, ...]                   # literales que la tabla no conoce (hueco nuevo)
    contagiadas: Mapping[str, tuple[str, ...]]      # expediente -> actuaciones alcanzadas por contagio
```

Cinco reglas:

1. **La reconciliación es por `codigo_identificativo_propio`**, nunca por posición ni por nombre. Una
   referencia que no cuadra con ninguna actuación es `ErrorSeguimiento`: perder un estado en silencio es peor
   que fallar.
2. **Un estado se registra siempre, aunque no se entienda** (`docs/02` §5.6, invariante 5 de la máquina): un
   literal desconocido no se descarta, se refleja, la actuación pasa a `EN_REVISION_HUMANA` y sale en
   `desconocidos` para abrir un hueco en `docs/HUECOS.md`. **El código no abre el hueco: lo señala.**
3. **El contagio lo decide la tabla, no este módulo.** Que `REQUERIDO_GA` alcance al expediente entero está en
   `estados_plataforma.yaml` (`alcance: expediente`); `sincronizar` solo llama a
   `engine.estados.propagar_requerimiento` con las actuaciones del expediente que se le dan.
4. **Idempotencia**: sincronizar dos veces el mismo estado no duplica eventos ni vuelve a contagiar. El log es
   solo-añadir, pero no es un buzón que se llene de repeticiones.
5. **Sin reloj propio.** El instante lo trae el estado recibido. Dos sincronizaciones iguales dan el mismo log.

## 3. Contrato C10 — requerimientos e intérprete (`engine/requerimientos.py`)

```python
class ErrorRequerimiento(Exception): ...
ORIGENES = ("interno", "verificador", "GA", "CN")     # los de engine.eventos.catalogo
ALCANCE_DE_ORIGEN = {"interno": "actuacion", "verificador": "grupo", "GA": "expediente", "CN": "expediente"}

@dataclass(frozen=True) class Requerimiento:
    id, origen, actuacion_id, recibido_en: datetime
    expediente_id: str | None, grupo_id: str | None
    motivos: tuple[str, ...]                 # el texto tal cual lo emitió quien requiere
    informe_sha256: str | None               # el PDF del requerimiento, por su huella
    literal_plataforma: str | None
    ronda: int = 1                           # CN admite una segunda (docs/02 §5.6)

@dataclass(frozen=True) class Item:
    texto_literal: str                       # la cita: de dónde sale, palabra por palabra
    regla_id: str | None
    documento: str | None
    variable: str | None
    confianza: Decimal
    metodo: str                              # "lexico" hoy; "llm:<modelo>" en S3.6

@dataclass(frozen=True) class Interpretacion:
    requerimiento_id, version_interprete, items: tuple[Item, ...]
    confirmada_por_humano: bool = False
    confirmada_por: str | None = None

class Interprete(Protocol):
    version: str
    def interpretar(self, requerimiento, *, spec) -> Interpretacion: ...

class InterpreteLexico:      # determinista, sin LLM. La variante con LLM es S3.6, detrás de esta interfaz
def confirmar(interpretacion, *, actor) -> Interpretacion
def reabrir(log, requerimiento, interpretacion, *, actor) -> tuple[Evento, ...]
```

Los invariantes de la familia `R-REQ` (`docs/04` §10.4), en código y en test:

- **R-REQ-01** — un requerimiento de origen externo sin `informe_sha256` no se puede usar para reabrir:
  `ErrorRequerimiento`. Un requerimiento sin documento es un rumor.
- **R-REQ-02** — `reabrir` exige `confirmada_por_humano` **y** actor humano. Una interpretación, venga de un
  léxico o de un modelo, es una **propuesta**: nunca reabre sola. Es la regla que impide que un error de
  lectura mueva una actuación firmada.
- **R-REQ-03** — tras la firma, un cambio de dato fuera de un requerimiento abierto no cambia el estado y se
  anota como rechazo (ya lo hace `engine/estados.py`, invariante 3). Aquí se prueba de extremo a extremo.
- **R-REQ-04** — un requerimiento de `GA`/`CN` marca **todas** las actuaciones del expediente. Es invariante de
  test, no regla de spec.

Dos decisiones del intérprete determinista:

1. **Sin cita no hay item.** Igual que un extractor: un item sin `texto_literal` del propio requerimiento se
   descarta. El léxico no "deduce" reglas, las **reconoce** en el texto.
2. **`no_lo_se` es una salida legítima.** Un requerimiento que el léxico no sabe mapear produce una
   interpretación con cero items y confianza nula; eso escala a revisión humana, que es lo correcto, en vez de
   inventar una regla plausible.

## 4. Contrato C11 — el puente (`salida/seguimiento.py`)

`engine/` no importa de `salida/`; el bucle que **pregunta** al destino vive del lado de la salida:

```python
def sincronizar_desde(puerto, *, logs, indice, tenant_id=None) -> Sincronizacion
```

Llama a `consultar_estado` y `consultar_tareas` del puerto (el simulador hoy, la API en S3.7), traduce sus
tipos a los datos planos de C9 y deja que el núcleo decida. Una vía que se niega a consultar (el handoff) se
propaga como `ErrorSalida`, no se disfraza de "no hay nada".

## 5. Contrato C12 — requerimientos sintéticos (`generator/`)

Tres documentos, uno por origen, con la marca **"DOCUMENTO SINTÉTICO – SOLO PRUEBAS"** y motivos que el léxico
tenga que mapear a reglas reales de la ficha IND240. Más un **expediente de tres actuaciones** para que el
contagio se pueda probar de verdad: con una sola actuación, el contagio no se distingue de no contagiar.

Los tres cubren: un motivo que mapea a una regla concreta · un motivo que mapea a un documento que falta · un
motivo que el léxico **no** sabe mapear (y que por tanto escala). Si los tres fueran fáciles, el banco de
pruebas mentiría.

## 6. Verificación

Criterio de `docs/06` S3.5: un `PDTE_RECTIFICACION_VER` simulado reabre subsanación con la regla correcta · un
requerimiento de GA simulado bloquea el expediente completo · toda interpretación de A9 exige confirmación
humana antes de reabrir (`R-REQ-02`).
Añadido: `pytest -q` en verde sin romper los 1679 anteriores · `evaluar_casos.py` 7/7 con el caso A en
305.829,6 kWh/año · `ruff` limpio · el circuito completo funciona **sin un solo LLM** (modo degradado) · un
literal desconocido se refleja y escala en vez de perderse.

## 7. Lo que queda para Billy (PROPUESTA)

1. **Dónde vive la familia `R-REQ` como spec.** `docs/04` §10.4 la pone en `spec/propuestas/composicion_v1.yaml`
   junto a `R-GRP` y `R-EXP`, pero esas son Sprint 4 y decisión tuya, mientras que `R-REQ` se necesita ya.
   Propuesta: fichero propio `spec/propuestas/requerimientos_v1.yaml`, **sin activar**. Si prefieres el fichero
   único, es mover un bloque.
2. **Severidad de `R-REQ-01`**: hoy `BLOQUEANTE_DATOS`. Un requerimiento sin informe adjunto podría ser
   `SUBSANABLE` (se pide el informe) en vez de bloquear.
3. **Segunda ronda de CN**: se modela con `ronda: int` y no se limita. Si la plataforma la acota a dos, es una
   línea, pero hoy **no está documentado** (`API-03`).
4. **A9 con LLM** sigue esperando tu decisión de proveedor. La interfaz está lista y el circuito no la necesita
   para funcionar: lo que aporta el LLM es cobertura de motivos que el léxico no reconoce.
