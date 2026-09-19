# ADR-004 — Modelo canónico, log de eventos y máquina de estados (S3.1)

**Estado**: ACEPTADA (contratos y decisiones técnicas) · PROPUESTA (§6, lo que decide Billy)
**Fecha**: 2026-09-19
**Decide**: Claude (técnica) · Billy (lo que se marca `PROPUESTA` en §6)
**Ámbito**: `engine/modelo/`, `engine/eventos/`, `engine/estados.py`, `engine/motor.py` (solo el enganche), `tests/`

## Contexto

Cerrada la Fase 0, el Engine produce un veredicto y un informe pero no tiene **memoria ni ciclo**: cada ejecución
empieza de cero, no hay forma de reproducir una actuación pasada contra una spec nueva, y el estado de nuestro
trabajo no está modelado. S3.1 añade las tres piezas que lo resuelven (`docs/06` §2), todas diseñadas en
`docs/03`: modelo canónico (N7, §5), log de eventos (N8, §6) y máquina de estados (N6, §7).

Es la base de todo el Sprint 3: el puerto de salida (S3.4) construye su payload desde el modelo canónico, el
seguimiento post-envío (S3.5) proyecta estados de plataforma sobre la máquina de estados, y el manifiesto (S3.3)
se apoya en el log. Sin esto, cada uno inventaría su propio modelo.

**Lo que S3.1 no hace**: no toca el veredicto ni el cálculo (el núcleo de la Fase 0 se conserva intacto), no
construye payload ni adaptadores de salida, no implementa las familias de reglas `R-GRP`/`R-EXP`/`R-REQ` (son
diseño pendiente de Billy, `ADR-001` §3) y no inventa ningún campo de la API oficial.

## Opciones consideradas

1. **Modelo canónico como dataclasses + JSON Schema generado a mano y validado con un validador propio.** Sin
   dependencias nuevas; el esquema es un artefacto versionado que vive junto al código.
2. **Añadir `pydantic` o `jsonschema` como dependencia.** Menos código propio, pero una dependencia más en el
   núcleo determinista para algo que hacemos una vez, y `pydantic` arrastra coerción automática de tipos, justo
   lo que el contrato de la Fase 0 prohíbe (`ADR-002` §2.4: el contexto entrega valores tipados, sin coerción).

**Decisión: opción 1.** El validador es pequeño (tipos, requeridos, enumerados, formatos `decimal` y `date`), el
esquema se versiona con `modelo_version` y el núcleo no gana dependencias. Si un día hace falta un validador
completo, el esquema ya está escrito en JSON Schema estándar y se puede delegar.

## Contratos (obligatorios para todos los agentes de este sprint)

Mismas convenciones que la Fase 0: español sin tildes en identificadores, `Decimal` para magnitudes, `date` para
fechas, nada de `float`, sin `eval`. `engine/` no importa de `agentes/`, `salida/`, `generator/` ni `tests/`.

### C1. `engine/modelo/` (N7)

Entidades de `docs/03` §5.2, como dataclasses serializables y validables:

```python
MODELO_VERSION = "1.0"
class ErrorModelo(Exception): ...

@dataclass class Tenant:            id, tipo ("delegado"|"obligado_directo"), razon_social, nif,
                                    capacidad_delegacion_disponible: Decimal | None   # TODO(API-11)
@dataclass class Verificador:       id, razon_social, nif, acreditacion_enac_ref | None,
                                    ccaa_operativas: tuple[str, ...] | None            # NO DOCUMENTADO
@dataclass class Parte:             rol ("propietario_inicial"|"solicitante"|"instalador"|"verificador"), nif, razon_social
@dataclass class DocumentoRef:      doc_id, tipo | None, confianza_tipo | None, sha256, bytes, paginas,
                                    origen | None, metodo_lectura
@dataclass class Unidad:            clave (num_serie_motor), num_serie_variador | None, variables: dict[str, dict]  # DatoConsolidado.a_dict()
@dataclass class ActuacionCanonica: id, codigo_identificativo_propio, modelo_version, creado_en,
                                    ficha {codigo, version_ficha, version_spec, hash_spec},
                                    cabecera: dict,                       # vacío en S3.1: es S3.2 (aprobación de Billy)
                                    partes: list[Parte], atributos_agrupacion {ccaa|None, anio_finalizacion|None, sector, verificador_id|None},
                                    documentos: list[DocumentoRef], unidades: list[Unidad], variables_actuacion: dict,
                                    evaluacion {reglas, veredicto, hash_reglas, evaluado_en},
                                    calculo: dict | None, observaciones, interpretaciones_aplicadas,
                                    subsanaciones: list[dict], ciclo {estado_ciclo, estado_plataforma|None, grupo_id|None, expediente_id|None}
@dataclass class GrupoActuaciones:  id, tenant_id, verificador_id, actuaciones: tuple[str, ...], estado_plataforma | None
@dataclass class Expediente:        id, tenant_id, ccaa, anio, sector, verificador_id, actuaciones, grupo_id | None,
                                    estado_expediente | None, requerimientos: list[dict]

def desde_motor(actuacion, *, tenant=None, verificador=None) -> ActuacionCanonica
def validar(obj) -> None            # contra el JSON Schema; ErrorModelo con la ruta del campo que falla
def a_dict(obj) -> dict             # JSON canónico compatible (Decimal y date como cadena)
```

`engine/modelo/esquemas/actuacion-1.0.json` y los de grupo y expediente son JSON Schema (draft 2020-12) escritos
a mano y versionados. `validar` implementa el subconjunto que usamos: `type`, `required`, `enum`, `items`,
`properties`, `additionalProperties: false`, y dos formatos propios, `decimal-string` y `date`.

Campos `NO DOCUMENTADO` (`capacidad_delegacion_disponible`, `ccaa_operativas`, `atributos_agrupacion.ccaa`):
opcionales, con `# TODO(API-xx)` y su fila en `docs/HUECOS.md`. No se les da semántica propia ni valor inventado.

### C2. `engine/eventos/` (N8)

```python
class ErrorEvento(Exception): ...
CLASES_ACTOR = ("humano", "motor", "agente", "plataforma")
TIPOS: frozenset[str]              # catálogo cerrado de docs/03 §6.2; un tipo no declarado es ErrorEvento

@dataclass(frozen=True) class Actor:  clase: str, id: str
@dataclass(frozen=True) class Evento:
    evento_id, actuacion_id, secuencia: int, tipo: str, ocurrido_en: datetime, actor: Actor,
    payload: Mapping, hash_previo: str, hash: str

def json_canonico(obj) -> str      # claves ordenadas, UTF-8, sin espacios, Decimal y date como cadena
def calcular_hash(evento_sin_hash, hash_previo) -> str      # sha256(hash_previo + json_canonico(evento))
class LogEventos:                  # solo-añadir, en memoria con serialización JSONL
    def anadir(tipo, payload, *, actor, ocurrido_en=None) -> Evento
    def verificar() -> None        # recorre la cadena; ErrorEvento en el primer eslabón roto
    def proyectar() -> Proyeccion  # estado derivado del log (no hay estado propio fuera de esta proyección)
    def a_jsonl() / desde_jsonl()
```

Reglas: nunca se edita ni se borra un evento (una corrección es un evento nuevo); la secuencia es densa y
creciente; `hash_previo` del primero es la cadena vacía; `ocurrido_en` en UTC con `timezone.utc` explícito, nunca
`datetime.now()` sin zona (la Fase 0 ya tuvo ese defecto con `date.today()`, ADR-003 H-08).

**Replay** (criterio de aceptación de `docs/06`): `reproducir(log, spec) -> Evaluacion` vuelve a ejecutar el
núcleo con los datos que el log conserva y produce **el mismo veredicto y el mismo ahorro, bit a bit**. Lo que se
compara es `json_canonico` del resultado, no un `==` de objetos.

### C3. `engine/estados.py` (N6)

Los **cuatro niveles no se mezclan** (`docs/03` §7.1, `CLAUDE.md` §3):

| Nivel | Dónde vive | Quién lo fija |
|---|---|---|
| Veredicto | `Evaluacion.veredicto` (Fase 0) | Rules Engine |
| Estado de ciclo | `estados.py` | Máquina de estados, como proyección del log |
| Estado de plataforma — actuación | Se refleja, no se decide | La plataforma (8 estados confirmados, `docs/02` §5.1) |
| Estado de plataforma — expediente | Se refleja, no se decide | La plataforma (provisionales, `TODO(API-03)`) |

```python
ESTADOS_CICLO = ("ABIERTA","EN_PROCESO","EVALUADA","PENDIENTE_SUBSANACION","EN_REVISION_HUMANA",
                 "LISTA_PARA_ENVIO","ENTREGADA","EN_PLATAFORMA","CERRADA","DESCARTADA")
ESTADOS_PLATAFORMA_ACTUACION = (...)        # los 8 de docs/02 §5.1, confirmados
ESTADOS_PLATAFORMA_EXPEDIENTE = (...)       # provisionales, cada uno con TODO(API-03)
def transiciones_validas(estado) -> frozenset[str]
def aplicar(proyeccion, evento) -> Proyeccion              # pura; una transición inválida es ErrorEstado
def proyectar_estado_plataforma(literal) -> str | None     # tabla de mapeo en YAML, no en código
```

Invariantes que los tests deben proteger:

1. `ENTREGADA` → `EN_PLATAFORMA` exige un evento `FirmaRegistrada` de actor `humano`. **Ningún evento de actor
   `agente` o `motor` puede hacer esa transición** (criterio de `docs/06`).
2. Solo una actuación `PREVALIDADO` **y revisada por un humano** llega a `LISTA_PARA_ENVIO`.
3. Tras `EN_PLATAFORMA`, un cambio de datos fuera de un requerimiento abierto se rechaza con
   `CorreccionRechazadaPostFirma` (inalterabilidad, `docs/02` §5.4).
4. Un requerimiento de GA o CN marca `PENDIENTE_SUBSANACION` en **todas** las actuaciones del expediente, con
   `afectada_directamente: bool` (contagio, criterio de `docs/06`).
5. Un literal de plataforma desconocido no se descarta: se registra y la actuación pasa a `EN_REVISION_HUMANA`
   (`docs/02` §5.6), y es un hueco nuevo en `docs/HUECOS.md`.

Los nombres provisionales de fases 2–4 viven en una **tabla de mapeo YAML** (`engine/estados_plataforma.yaml` o
equivalente), nunca como literales dispersos por el código: cuando llegue el diccionario oficial, cambiar nombres
es cambiar YAML (`docs/03` §7.1).

**Añadido en S3.4** (`ADR-009` §5 ter punto 2): la tabla declara además `inicial` y `validacion_automatica`, y
la carga garantiza que hay exactamente una fila de cada —y de `exige_firma`—, de nivel actuación. Son las tres
marcas por las que `salida/simulador/` reconoce los estados **sin nombrarlos y sin depender del orden de las
filas**; reordenar el fichero ya no puede cambiar el comportamiento en silencio.

## Consecuencias

- `engine/motor.py` gana la construcción del modelo canónico y la emisión de eventos **sin cambiar su interfaz
  pública** (`docs/03` §6.2): `procesar_actuacion` sigue devolviendo lo mismo y los 999 tests de la Fase 0 siguen
  en verde. El log es opcional en la Fase 0 y obligatorio desde aquí.
- `docs/03` §3.1 pasa `N6`, `N7` y `N8` de `NUEVO` a `EXISTE`; `docs/01` §3.3 añade `modelo/`, `eventos/` y
  `estados.py`.
- Cada actuación procesada pasa a ser una prueba de regresión reproducible (F-22 de `docs/03` §13).

## 6. Lo que queda para Billy (PROPUESTA)

1. **`cabecera` vacía en S3.1**: la spec transversal es S3.2 y depende de su aprobación (`ADR-001` §3). El campo
   existe en el modelo con su hueco; no se rellena ni se inventa.
2. **Estados provisionales de fases 2–4**: son nombres nuestros (`TODO(API-03)`). Se modelan como mapeo YAML para
   que el diccionario oficial no obligue a tocar código.
3. **`capacidad_delegacion_disponible`** (`API-11`) y **`ccaa`** (`API-07`): atributos opcionales sin semántica
   propia hasta que la plataforma los documente.

## 7. Decisiones tomadas al construir (19/09/2026)

Cerrado en tres piezas: modelo canónico (161 tests), log de eventos (112) y máquina de estados (92).

**Modelo canónico**

- `desde_motor` **no llama al reloj**: `creado_en` y `evaluado_en` son la `fecha_evaluacion` de la actuación. El
  modelo es función pura de lo procesado, que es lo que el replay bit a bit necesita, y evita el defecto H-08 de
  `ADR-003` (`date.today()` no determinista).
- El validador propio acepta un subconjunto declarado de JSON Schema y **cualquier palabra no declarada es error
  de carga**, el mismo criterio que el parser de expresiones con una función desconocida.
- El esquema exige la regla de oro 2: `evidencias` con `minItems: 1` y `texto_literal` con `minLength: 1`. Un dato
  sin cita no valida.
- `ActuacionCanonica` **no lleva `tenant_id`**: el tenant contiene la actuación, no al revés. Si el aislamiento
  por tenant o el payload de S3.4 lo necesitan dentro, es campo nuevo y `modelo_version` 1.1.
- `ciclo.estado_plataforma` y `estado_expediente` **no se enumeran** en el esquema: esos literales viven en la
  tabla YAML de la máquina de estados, y duplicarlos sería el literal disperso que `docs/02` §5.2 prohíbe.

**Log de eventos**

- `LogEventos.proyectar()` que anunciaba §C2 **no existe**: la proyección vive en `engine/estados.py`
  (`proyectar(log)`). Ponerla en el log crearía una dependencia circular, porque `estados` ya importa `eventos`.
  **Corrige §C2 en ese punto.**

**Máquina de estados**

- El catálogo de eventos de `docs/03` §6.2 no tiene tipo para tres cosas que el ciclo necesita: revisión humana,
  escalado y descarte. Se resuelven con `ObservacionRegistrada` y un `origen` en el payload. **Propuesta**: tipos
  propios `RevisionHumanaRegistrada` y `ActuacionDescartada` (y, de la pieza B, `InterpretacionConfirmada` y
  `ConsolidacionCompletada`).
- Dos aristas que `docs/03` §7.2 no dibuja pero su prosa implica: `EN_REVISION_HUMANA` alcanzable desde cualquier
  estado no terminal (presupuesto agotado, literal desconocido) y **`ENTREGADA` → `EN_PROCESO`**, porque en
  `BORRADOR` y `COMPLETA` la actuación sigue siendo modificable por nosotros (`docs/02` §5.6): la inalterabilidad
  empieza en `EN_PLATAFORMA`, no en la entrega.
- La inalterabilidad se evalúa por `firmada and requerimiento_abierto is None`, no por el estado, para que siga
  valiendo cuando una subsanación oficial devuelve la actuación a `EN_PROCESO`.
- `aplicar` es pura y **no escribe en el log**: el rechazo post-firma se acumula en `Proyeccion.rechazos` y quien
  llama emite `CorreccionRechazadaPostFirma`. Queda por decidir de quién es esa responsabilidad (¿`motor.py`, el
  puerto de salida?).
- Una actuación terminal no se contagia: un requerimiento de GA o CN no revienta un expediente con actuaciones ya
  cerradas.
- A los estados de expediente sin efecto declarado en `docs/02` §5.6 (entre ellos `RESUELTO_DESFAVORABLE`) **no se
  les inventa uno**: quedan con `ciclo: null` hasta que llegue `API-03`.

**Pendiente de enganche**: `engine/motor.py` no construye todavía el modelo canónico ni emite eventos. Es una tarea
pequeña y aislada que va con S3.3 o S3.4, cuando haya un consumidor real; hoy `grabar(actuacion)` y `desde_motor`
se invocan desde fuera y los tests lo cubren.

## Verificación

`python -m pytest -q` verde (999 anteriores más los nuevos) · los 7 casos producen `ActuacionCanonica` válida
contra el esquema · el replay del log reproduce veredicto y ahorro bit a bit · ningún evento de actor `agente` o
`motor` mueve `ENTREGADA` → `EN_PLATAFORMA` · un requerimiento GA/CN simulado marca todas las actuaciones del
expediente · `python evaluar_casos.py` sigue dando 7/7 · `ruff check . && ruff format --check .` limpio.
