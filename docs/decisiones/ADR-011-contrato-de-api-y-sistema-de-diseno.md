# ADR-011 — Contrato de comandos y lecturas por capacidad, y sistema de diseño mínimo (FR0)

**Estado**: ACEPTADA (técnica) · PROPUESTA (§7, lo que decide Billy)
**Fecha**: 2026-09-19
**Decide**: Claude (técnica) · Billy (lo marcado `PROPUESTA` en §7)
**Ámbito**: `api/` (nuevo), `front/compartido/` (nuevo), `tests/test_api_*.py`, `docs/01`, `docs/06`

## Contexto

Billy aprobó el 19/09/2026 **C1** (un solo stack web, React con TypeScript) y **C7** (cuatro superficies
adaptadas por capacidades, orden `FR0` → `FR6`), y reafirmó que **el contrato antes que las pantallas no es
negociable**: es práctica establecida, no una preferencia de este proyecto. Eso desbloquea `FR0`.

`FR0` es el cimiento de todo el front: si está mal, los seis entregables siguientes heredan el error, y el
error típico es conocido — la lógica de negocio se filtra a la interfaz y los endpoints se inventan sobre la
marcha. Este ADR existe para que eso no pase por accidente.

**Criterio de `docs/06` FR0**: cada capacidad de `ADR-005` tiene su comando o lectura · tests de concesión y
denegación en verde **desde la API**, sin pasar por el front · rótulos `R-UI-06` a `R-UI-08` disponibles como
componentes.

## 1. La decisión que lo gobierna todo: la matriz es configuración

`ADR-006` define 8 perfiles y 47 capacidades en una tabla. Esa tabla **no se escribe en Python**: vive en
`api/capacidades.yaml`, validada con JSON Schema propio al cargar, exactamente con el mismo criterio que las
fichas (`spec/`) y las métricas (`metricas/catalogo.yaml`).

**Un `if perfil == "T-RES"` en `api/` es un defecto del marco, no una solución** — la misma regla de oro 4 que
protege las fichas. Cambiar quién puede hacer qué tiene que ser cambiar YAML, porque va a cambiar: siete
celdas de la matriz están hoy marcadas `(?)` esperando decisiones de Billy (A1 a A4).

**Las celdas `(?)` se cargan como `pendiente` y se deniegan.** Una capacidad cuya asignación no está decidida
no se concede "provisionalmente": se niega y se dice por qué. Conceder por defecto lo que nadie ha decidido es
como se abren los agujeros de permisos.

## 2. Contrato C13 — la matriz como configuración (`api/capacidades.yaml`)

```yaml
version_matriz: "1.0"
perfiles:
  - id: T-RES
    nombre: Responsable del tenant
    ambito: tenant            # tenant | externo | global | sistema
    superficie: workspace     # workspace | externo | consola | ninguna
capacidades:
  - id: CAP-05
    nombre: Resolver conflicto o corregir dato, con justificación
    tipo: comando             # comando | lectura
    proceso: P4
    eventos: [DatoCorregidoPorHumano]   # los que produce; vacío si es lectura
    exige_justificacion: true           # R-UI-04
    concede: [T-REV]
    pendiente: []                       # perfiles con la celda `(?)`: se DENIEGAN hasta decidir
    decide: null                        # la decisión que la cerraría (p. ej. "A1")
```

Reglas de carga, todas error al cargar y no en mitad de una petición:

1. **Toda capacidad de `ADR-006` está presente**, y ninguna de más. Un test lo contrasta contra el ADR.
2. **Un `comando` declara al menos un evento del catálogo cerrado** (`engine.eventos.catalogo.TIPOS`); una
   `lectura` no declara ninguno. Un evento inventado no carga.
3. **Un perfil en `pendiente` no puede estar además en `concede`**, y una capacidad con `pendiente` no vacío
   declara qué decisión la cierra (`decide`).
4. **`SYS-API` no tiene superficie**: aparece como identidad técnica, no como usuario con pantallas.

## 3. Contrato C14 — permisos e inferencia de rol (`api/permisos.py`)

```python
class ErrorPermiso(Exception): ...        # denegación; nunca devuelve datos parciales
class ErrorApi(Exception): ...

@dataclass(frozen=True) class Principal:
    usuario_id: str
    perfiles: tuple[str, ...]             # los que el usuario acumula (delegado pequeño: hasta tres)
    tenant_id: str | None                 # None solo para perfiles globales
@dataclass(frozen=True) class Contexto:
    superficie: str                       # de dónde viene la acción: desempata roles compartidos
    tenant_id: str | None
    actuacion_id: str | None = None

def matriz(ruta=None) -> Matriz                       # cargada una vez, error de carga si está mal
def concede(matriz, capacidad, principal) -> bool
def exigir(matriz, capacidad, principal, contexto) -> str   # devuelve el `rol` o levanta ErrorPermiso
def rol_para(matriz, capacidad, principal, contexto) -> str
```

Cuatro reglas:

1. **`R-UI-01`: la autorización ocurre aquí, en el servidor.** Ocultar un control no autoriza nada. Todo
   comando y toda lectura pasan por `exigir` antes de tocar `engine/`.
2. **Aislamiento por tenant, siempre.** Una capacidad de tenant sobre otro tenant es `ErrorPermiso`, aunque el
   perfil la conceda. El `tenant_id` no viene del cliente: viene del principal autenticado.
3. **Inferencia del rol** (C2 de `ADR-050`, **recomendada y aún abierta**): si la capacidad la concede un solo
   perfil del usuario, ese es el rol. Si la conceden varios (CAP-02 y CAP-09), lo desempata la
   `superficie`/pantalla del contexto. Si sigue sin resolverse, es `ErrorApi`: **no se elige uno al azar**.
4. **Denegación silenciosa, nunca.** `ErrorPermiso` dice qué capacidad y por qué (no concedida, pendiente de
   decisión, o cruce de tenant). Un permiso que falla sin explicación es un permiso que nadie arregla.

## 4. Contrato C15 — comandos y lecturas (`api/comandos/`, `api/lecturas/`)

```python
@dataclass(frozen=True) class Peticion:
    capacidad: str
    principal: Principal
    contexto: Contexto
    datos: Mapping[str, object]
@dataclass(frozen=True) class Respuesta:
    capacidad: str
    rol: str
    eventos: tuple[str, ...]              # ids de los eventos escritos; vacío en una lectura
    datos: Mapping[str, object]
    avisos: tuple[str, ...]

def ejecutar(peticion) -> Respuesta       # comando: valida, delega en engine/ y devuelve lo que pasó
def leer(peticion) -> Respuesta           # lectura: valida, proyecta y filtra por ámbito
```

- **El contrato no calcula nada** (`R-UI-11` aguas arriba): `ejecutar` valida, llama a `engine/` y traduce. Un
  cálculo, una evaluación de regla o una decisión de transición dentro de `api/` es un defecto.
- **`R-UI-12`: el filtrado es de serialización, no de pintado.** Una lectura de un perfil externo **no
  construye** los campos fuera de su ámbito; no basta con que el front no los muestre. Hay test.
- **`R-UI-04`: una corrección sin justificación no se ejecuta**, y la justificación va al log.
- **`R-UI-02` y `R-UI-03` por ausencia**: no existe comando para fijar un veredicto, y el de la firma se llama
  `CAP-22 Registrar firma`, nunca "firmar". Un test recorre el catálogo y lo comprueba.

**Dependencia abierta, declarada**: `actor.rol` **no se persiste todavía**. `engine.eventos.log.Actor` tiene
`clase` e `id`, y añadirle `rol` es `S3.1b`, que espera la decisión **A8** de Billy. `FR0` calcula el rol, lo
devuelve en `Respuesta.rol` y lo deja listo; escribirlo en el evento es una línea el día que A8 se cierre. Se
construye así en vez de esperar, porque el resto de `FR0` no depende de ello.

## 5. Contrato C16 — sistema de diseño mínimo (`front/compartido/`)

React con TypeScript (C1). Lo mínimo de `FR0` son **los tres rótulos que impiden que la interfaz mienta**:

| Componente | Regla | Qué garantiza |
|---|---|---|
| `RotuloPrevalidado` | `R-UI-06` | Todo kWh prevalidado sale acompañado de "no son CAE emitidos"; un estado de expediente sale marcado `NO OFICIAL` |
| `ValorMetrica` | `R-UI-07` | `SIN DATO` se muestra como `SIN DATO`; **nunca como cero**. Un cero real y un dato ausente no se parecen |
| `MarcaOrigen` | `R-UI-08` | Todo panel declara si mira datos sintéticos o reales |

No se construye ninguna pantalla en `FR0`: estos componentes existen para que `FR1` no tenga que inventárselos
y para que las tres reglas se apliquen una sola vez. `front/compartido/` **no habla con `engine/`**: solo con
`api/`, y en `FR0` ni siquiera eso — son componentes de presentación puros con sus tests.

## 6. Verificación

- `tests/test_api_capacidades.py`: cada capacidad de `ADR-006` está en el YAML y solo esas · para cada una, un
  caso concedido y otro denegado · las celdas `(?)` se deniegan y dicen qué decisión las cierra.
- `tests/test_api_aislamiento.py`: ninguna lectura devuelve datos de otro tenant ni campos fuera del ámbito
  del perfil (`R-UI-12`), comprobado sobre la respuesta, no sobre la pantalla.
- `tests/test_api_rol_inferido.py`: CAP-02 y CAP-09 resuelven el rol por contexto; el resto, por el único
  perfil que concede; un caso ambiguo es error y no una elección al azar.
- `tests/test_api_contrato.py`: no existe comando que fije un veredicto ni que se llame "firmar"; ningún
  comando declara un evento fuera del catálogo cerrado; `api/` no importa de `front/`.
- `front/compartido/`: tests de los tres rótulos, incluido que `SIN DATO` nunca se renderiza como `0`.
- Puerta de siempre: `pytest -q` sin romper los 1.781 · `evaluar_casos.py` 7/7 con el caso A en 305.829,6 ·
  `ruff` limpio · `engine/` sigue sin importar de nadie.

## 7. Lo que queda para Billy (PROPUESTA)

1. **A8** (`ADR-006`): modelar capacidades y `actor.rol` en el modelo y el log. Es lo único que impide
   persistir el rol que `FR0` ya calcula. Recomendación de `ADR-006`: sí.
2. **C2** (`ADR-050`): rol inferido frente a cambio explícito. `FR0` implementa la inferencia recomendada; si
   se prefiere el cambio explícito, cambia `rol_para` y nada más.
3. **A1 a A4**: mientras no se decidan, siete celdas de la matriz quedan `pendiente` y **se deniegan**. Afecta
   sobre todo a `FR4` (portal externo), que ya estaba bloqueado por eso.
4. **Herramienta de test del front**: se propone la del propio stack; si hay preferencia corporativa, decidirla
   antes de `FR1`, cuando haya pantallas de verdad que probar.
