# ADR-009 — Puerto de salida, adaptador handoff y simulador (S3.4)

**Estado**: ACEPTADA (técnica) · PROPUESTA (§6, lo que decide Billy)
**Fecha**: 2026-09-19
**Decide**: Claude (técnica) · Billy (lo marcado `PROPUESTA` en §6)
**Ámbito**: `salida/puerto.py`, `salida/mapeo.py`, `salida/handoff/`, `salida/simulador/`, `salida/transporte/`,
`mapping/*.handoff.yaml`, `tests/`, `docs/01` §3.8 y §3.9, `docs/03` §10

## Contexto

S3.3 dejó el manifiesto interno: qué se entrega y cómo demostrar que nadie lo alteró. Falta **la salida**: el
puerto con sus cuatro operaciones (`docs/03` §10.1), el primer adaptador que de verdad entrega algo (handoff:
carpeta ordenada para que el tenant presente por el cauce vigente) y el simulador que permite desarrollar P8 y
P9 **sin sandbox** de la plataforma.

El entorno de este entregable es el peor posible para inventar: no hay diccionario de API (`API-01`), no hay
formato de manifiesto oficial (`API-02`), no hay nombres del formulario de detalle (`API-08`) y no se sabe
dónde puede vivir el transporte (`API-09`). La disciplina que hace esto posible es la misma de siempre: el
handoff es **nuestro** formato — ahí no hay nada que inventar porque no hay nada oficial que copiar — y el
simulador reproduce **solo lo publicado**; todo lo demás es un `TODO(API-xx)` con su fila en `docs/HUECOS.md`.

**Lo que S3.4 no hace**: no construye el payload de la API oficial (`mapping/IND240.api.yaml` sigue vacío), no
habla con ninguna plataforma real, no implementa P9 completo (es S3.5), no toca `engine/` y **no firma nada**.

## 1. Opciones consideradas

1. **Un solo adaptador handoff, sin puerto.** Menos código hoy. Cuando llegue el conector de API, el simulador
   y el handoff no tendrían un contrato común que respetar y P9 se escribiría dos veces.
2. **Puerto con cuatro operaciones y tres adaptadores** (handoff, simulador, api_oficial cuando exista), como
   `docs/03` §10.1. El coste es definir hoy tipos de retorno (`Acuse`, `EstadoPlataforma`, `TareaPendiente`)
   cuyo equivalente oficial no conocemos.

**Decisión: opción 2, con una salvaguarda.** Los tipos del puerto son **nuestros**, no una copia anticipada de
la API: ninguno tiene un campo que pretenda ser el campo oficial. Donde el equivalente oficial es desconocido,
el campo lleva su `TODO(API-xx)` y el adaptador de API que se escriba en S3.7 **traducirá**, no heredará. Si al
llegar el diccionario resulta que la traducción obliga a tocar `engine/`, el diseño está mal (`docs/03` §10.1).

### 1 bis. Por qué un mapeo declarativo y no un constructor por ficha

`construir(actuacion, mapeo)` no sabe qué ficha está procesando. Qué variable va a qué campo del handoff lo
dice `mapping/IND240.handoff.yaml`, con el mismo criterio que la spec (regla de oro 4): **dar de alta una ficha
en la salida es añadir un YAML**. `salida/mapeo.py` solo **selecciona** rutas del modelo canónico; no calcula,
no convierte unidades y no tiene `eval`. Una función o una operación en un mapeo es error de carga.

## 2. Contrato C4 — el puerto (`salida/puerto.py`)

Convenciones de siempre: español sin tildes en identificadores, `Decimal`, `datetime` con zona, sin `float`,
sin `eval`. `salida/` **puede** importar de `engine/`; `engine/` **nunca** de `salida/` (test desde la Fase 0).

```python
DESTINOS = ("handoff", "api")           # destino de un mapeo; "api" no tiene adaptador hoy (API-01)
VIAS = ("handoff", "API", "simulador")  # las dos primeras son las de `engine.estados.VIAS_ENTREGA`

class ErrorSalida(Exception): ...

@dataclass(frozen=True) class Adjunto:      # lo que viaja, tal y como lo declaró el manifiesto
    ruta, tipo, sha256, bytes, origen, es_parte

@dataclass(frozen=True) class Paquete:
    actuacion_id, codigo_identificativo_propio, destino, mapeo_id, mapeo_version
    generado_en: datetime                   # UTC explícito
    payload: Mapping                        # {"cabecera": {...}, "detalle": {...}} — NUESTRO, no el oficial
    manifiesto: Manifiesto                  # el de S3.3, sin tocar
    adjuntos: tuple[Adjunto, ...]
    raiz: str                               # carpeta de la que salen los bytes
    veredicto: str | None                   # se transporta, no se juzga
    carencias: tuple[str, ...]              # campos obligatorios del mapeo sin valor
    hash_paquete -> str                     # == manifiesto.hash_manifiesto
    a_dict() -> dict

@dataclass(frozen=True) class Acuse:
    referencia, via, instante, aceptado, hash_paquete
    estado_plataforma: str | None           # solo lo fija un destino que sea plataforma; None en handoff
    motivos: tuple[str, ...]                # por qué no se aceptó, si no se aceptó
    detalle: Mapping

@dataclass(frozen=True) class EstadoPlataforma:
    referencia, literal, nivel, oficial: bool, instante, motivos: tuple[str, ...]

@dataclass(frozen=True) class TareaPendiente:
    id, tenant_id, referencia, asunto, instante
    vence_en: date | None = None            # TODO(API-10): la plataforma no publica plazos

class PuertoSalida(Protocol):
    nombre: str
    def construir(self, actuacion, mapeo, *, raiz=None, log=None) -> Paquete
    def entregar(self, paquete, *, log=None) -> Acuse
    def consultar_estado(self, referencia) -> EstadoPlataforma
    def consultar_tareas(self, tenant_id) -> tuple[TareaPendiente, ...]
```

Cinco decisiones que el contrato fija y que no se reabren en el código:

1. **`Paquete.veredicto` se transporta, no se juzga.** Igual que el manifiesto (`ADR-008` §4 bis punto 7), el
   puerto describe. Quien decide si una actuación puede salir es la máquina de estados, y solo cuando hay log.
2. **El estado de ciclo lo mueve el log, no el adaptador.** `construir` y `entregar` emiten eventos del
   catálogo P8 (`PayloadConstruido`, `ManifiestoGenerado`, `EntregadoADelegado`) **solo si se les pasa un
   `log`**. Sin log, entregan igual y no hay transición: un adaptador no es una máquina de estados paralela.
   Consecuencia buscada: con log, entregar una actuación que no sea `PREVALIDADO` **y** revisada por un humano
   es `ErrorEstado` de `engine/estados.py` (invariante 2), no una comprobación duplicada aquí.
3. **`hash_paquete` es el `hash_manifiesto`.** No se inventa una segunda huella del mismo contenido.
4. **`consultar_estado` y `consultar_tareas` no son opcionales en el protocolo, pero sí pueden negarse.** El
   handoff no consulta nada: levanta `ErrorSalida` diciendo que por esa vía el estado lo trae el tenant. Es
   más honesto que devolver una lista vacía que se confunde con "no hay tareas".
5. **`via` del acuse alimenta `Proyeccion.via_entrega`**, con los mismos literales que `VIAS_ENTREGA`.

## 3. Contrato C5 — el mapeo declarativo (`salida/mapeo.py`, `mapping/*.yaml`)

```python
@dataclass(frozen=True) class Campo:
    clave, etiqueta, origen, unidad, obligatorio: bool, nota, hueco   # `hueco` = "API-08" si lo espera
@dataclass(frozen=True) class Mapeo:
    id, ficha, destino, version, cabecera, detalle_actuacion, detalle_unidad, documentos, ficheros
def cargar(ficha, destino, *, carpeta=None) -> Mapeo     # clave desconocida = error de carga
def aplicar(mapeo, actuacion_canonica) -> tuple[dict, tuple[str, ...]]   # (payload, carencias)
def resolver(documento, ruta) -> object                  # ruta punteada; sin comodines ni funciones
```

- `origen` es una **ruta punteada del modelo canónico ya serializado** (`engine.modelo.a_dict`), por ejemplo
  `variables_actuacion.potencia_nominal.valor_consumido`. Nada más: ni expresión, ni función, ni condicional.
- Un `origen` que no resuelve deja el campo a `null`; si el campo es `obligatorio`, entra en `carencias`. No es
  un error: **declarado ≠ demostrado** y el tenant tiene derecho a ver qué falta en la carpeta que recibe.
- Un campo con `hueco` no puede ser `obligatorio`: es lo que todavía no se sabe pedir (`API-08`).
- `version` del mapeo viaja en el paquete: dos handoffs generados con mapeos distintos son distinguibles.

## 4. Contrato C6 — el handoff (`salida/handoff/`)

El handoff es el cauce que funciona hoy: una carpeta que el tenant abre, revisa y presenta él mismo.
**No tiene nada de oficial**, y por eso es el único sitio de `salida/` donde no hay riesgo de inventar un campo
de la API: no imita ningún formato de la plataforma.

```
<destino>/
  00_LEEME.md                    qué es esto, qué hace el tenant, qué NO hemos hecho (no firmamos)
  01_manifiesto.json             el manifiesto de S3.3, tal cual, con sus cinco hashes
  02_payload.json                cabecera + detalle según el mapeo (NUESTRO formato, no el de la API)
  03_informe_prevalidacion.md    engine.informe.a_markdown, sin cambios
  04_informe_prevalidacion.json  engine.informe.a_json
  05_log_eventos.jsonl           solo si se pasó log
  documentos/<tipo>/<fichero>    los adjuntos, copiados byte a byte y agrupados por tipo documental
  99_verificacion.txt            cómo comprobar la integridad de la carpeta sin nuestro software
```

- **Los bytes se copian, no se regeneran.** Tras escribir, el adaptador vuelve a verificar el manifiesto contra
  la carpeta escrita: si una copia no coincide, la entrega es `aceptado: False` y no se declara entregada.
- Las **partes de un PDF combinado** no se copian como fichero (no existen en disco, `ADR-008` §4 bis punto 1):
  se listan en el `00_LEEME.md` bajo su combinado.
- `entregar` es **idempotente por contenido**: entregar dos veces el mismo paquete en la misma carpeta da el
  mismo resultado; una carpeta destino no vacía con contenido distinto es `ErrorSalida`, nunca un borrado.
- El `00_LEEME.md` dice explícitamente que la firma es un acto humano del tenant con certificado de
  representante y que nosotros no firmamos ni custodiamos nada (`CLAUDE.md` §2, `docs/02` §6.2).

## 5. Contrato C7 — el simulador (`salida/simulador/`)

Reproduce **solo lo publicado** (presentación OMIE/MIBGAS 30/06/2026, `docs/02` §5 y §6.1): estados, validación
de esquema, manifiesto de ficheros con hash, firma humana, tareas pendientes. Todo lo demás, hueco.

```python
class ErrorSimulador(ErrorSalida): ...
PERFILES = ("Firma", "Modificacion", "Consulta")        # docs/02 §2.2, confirmados
@dataclass(frozen=True) class Credencial:  usuario_id, perfil, tenant_id
class Simulador:   # implementa PuertoSalida
    def crear_borrador(paquete, credencial) -> Acuse         # -> BORRADOR
    def validar(referencia) -> Acuse                         # -> COMPLETA, o rechazo con motivos
    def entregar(paquete, *, credencial, log=None) -> Acuse  # crear_borrador + validar
    def registrar_firma(referencia, evento_o_actor, *, credencial) -> Acuse   # COMPLETA -> ENVIADA_A_VERIFICACION
    def avanzar(referencia, literal, *, motivos=()) -> EstadoPlataforma       # lo que hacen verificador/GA/CN
    def consultar_estado(referencia) -> EstadoPlataforma
    def consultar_tareas(tenant_id) -> tuple[TareaPendiente, ...]
    def eventos_en(log, referencia) -> tuple[Evento, ...]    # EstadoPlataformaRecibido / TareaPendienteRecibida
```

Ocho reglas, cada una con su fuente:

1. **Ni un literal de plataforma en el código del simulador.** Los estados salen de
   `engine.estados.tabla_plataforma()` (`estados_plataforma.yaml`). Si mañana el diccionario renombra
   `PDTE_RECTIFICACION_VER`, cambia el YAML y el simulador no se toca (`docs/03` §7.1).
2. **La firma es lo único que abre `COMPLETA` → `ENVIADA_A_VERIFICACION`**, y exige un `FirmaRegistrada` (o un
   `Actor`) de clase `humano` **y** credencial de perfil `Firma`. Actor `motor`, `agente` o `plataforma` es
   `ErrorSimulador` (`docs/02` §5.6, `CLAUDE.md` §2). El simulador **no firma**: comprueba que alguien firmó.
3. **La automatización termina en `COMPLETA`** (`docs/02` §6.2). El simulador nunca avanza solo más allá.
4. **Validación**: esquema del modelo canónico (`engine.modelo.validar` — es el **nuestro**, el oficial es
   `TODO(API-01)`), integridad del manifiesto (`salida.constructor.verificar` contra la carpeta entregada) y
   recálculo de `hash_manifiesto`. Un paquete con un hash alterado se rechaza nombrando el fichero.
5. **Permisos por perfil** (`docs/02` §2.2, confirmados): `Consulta` no crea ni firma; `Modificacion` crea y
   carga borradores pero no firma; `Firma` todo. Si el usuario de `Modificacion` puede ser ajeno al agente es
   `TODO(API-09)` y el simulador **no lo modela**: solo mira el perfil, nunca de quién es la infraestructura.
6. **Los estados de fases 2–4 se sirven marcados `oficial: false`** y ningún test afirma que la plataforma
   devuelva esos literales (`docs/02` §5.2, `TODO(API-03)`).
7. **El simulador no inventa identificadores de la plataforma.** `referencia` se deriva del
   `codigo_identificativo_propio` y del `hash_paquete`, y va marcada como nuestra: cómo son las referencias
   oficiales es parte de `API-01`.
8. **Transiciones**: el simulador acepta los avances que la presentación enumera y rechaza un literal que la
   tabla no conoce. Las **transiciones exactas** entre los 8 estados son `NO DOCUMENTADO` (`docs/02` §5.1): el
   simulador exige solo lo que está escrito (firma antes de `ENVIADA_A_VERIFICACION`, y `COMPLETA` antes de la
   firma) y registra el resto sin inventar un grafo que nadie ha publicado.

## 5 bis. Contrato C8 — el transporte (`salida/transporte/`), separado y vacío a propósito

```python
class ErrorTransporte(ErrorSalida): ...
UBICACIONES = ("nuestra_infraestructura", "casa_del_tenant")     # TODO(API-09): decide Billy
class Transporte(Protocol):
    def firmar_peticion(peticion, credencial) -> PeticionFirmada
    def enviar(peticion_firmada) -> Acuse
class TransporteNoDisponible(Transporte):   # la única implementación hoy
    # levanta ErrorTransporte citando docs/HUECOS.md API-01 y API-09
```

Existe como **frontera declarada**, no como funcionalidad: firma peticiones con certificado de **usuario** y
jamás con el de representante. `docs/01` §3.8: **no existe `salida/firma/` como código** y no lo habrá. Un test
lo comprueba sobre el árbol de ficheros, no sobre un comentario.

## 6. Lo que queda para Billy (PROPUESTA)

1. **Dónde vive el transporte** (`API-09`): `UBICACIONES` está declarado y sin decidir. No bloquea S3.4.
2. **Formato del handoff**: el árbol de §4 es nuestro y es una propuesta operativa. Si el cauce que usan hoy
   los delegados con los que hablemos exige otro orden o otros nombres, cambia el mapeo, no el código.
3. **Perfil de la credencial con la que operaríamos nosotros** (`Modificacion` vs. usuario del tenant): el
   simulador modela los tres perfiles sin presuponer cuál usamos.
4. **Si el handoff debe negarse a construir un paquete de una actuación no `PREVALIDADO`**: hoy construye y lo
   transporta en `Paquete.veredicto`; la puerta la pone la máquina de estados cuando hay log (§2 punto 2).

## 7. Verificación

Criterio de `docs/06` S3.4: el simulador acepta el paquete del caso A y rechaza uno con hash alterado · la
firma es un paso humano simulado que cambia `COMPLETA` → `ENVIADA_A_VERIFICACION` solo con `FirmaRegistrada` de
actor humano · ningún campo inventado de la API, cada hueco citando `docs/HUECOS.md`.
Añadido: `pytest -q` en verde sin romper los 1467 anteriores · `evaluar_casos.py` 7/7 con el caso A en
305.829,6 kWh/año · `ruff` limpio · el test de dependencias sigue probando que `engine/` no importa de
`salida/` · ningún literal de plataforma en el código de `salida/simulador/`.
