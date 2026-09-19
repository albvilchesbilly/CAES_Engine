# ADR-008 — Manifiesto interno e integridad total (S3.3)

**Estado**: EN CURSO
**Fecha**: 2026-09-19
**Decide**: Claude (técnica) · Billy (lo marcado `PROPUESTA` en §5)
**Ámbito**: `salida/constructor/`, `tests/`, `docs/01` §3.8, `docs/03` §9

## Contexto

S3.1 dejó el modelo canónico, el log de eventos y la máquina de estados. Falta lo que convierte una actuación
evaluada en algo **entregable y demostrable**: un manifiesto que diga exactamente qué se envió y permita probar,
byte a byte, que nadie lo alteró después.

`docs/03` §9 fija su forma. Lo que S3.3 añade sobre lo que ya existe: los hashes del propio payload
(`hash_cabecera`, `hash_detalle`), el del log de eventos y el del manifiesto, de modo que la cadena de
integridad cubra desde el fichero que entregó el cliente hasta el paquete que sale.

Este es el primer módulo fuera de `engine/`. Estrena `salida/` y su regla: **nada aquí inventa un campo de la
API oficial**; lo desconocido es un `TODO(API-xx)` con su fila en `docs/HUECOS.md`.

**Lo que S3.3 no hace**: no construye el payload de la API (no hay diccionario, `API-01`), no entrega nada, no
implementa handoff ni simulador (son S3.4) y no toca `engine/`.

## Opciones consideradas

1. **Manifiesto calculado al vuelo cada vez que se pide.** Simple, sin estado. Si el paquete cambia, el
   manifiesto cambia con él, lo que es justo lo que se quiere detectar en otro sitio.
2. **Manifiesto como artefacto inmutable que se genera una vez y se firma con su propio hash.** Es lo que
   describe `docs/03` §9: `hash_manifiesto` sobre el resto del contenido, de forma que alterar cualquier
   entrada lo invalida.

**Decisión: opción 2.** El manifiesto es una fotografía fechada, no una vista. `verificar()` lo contrasta contra
los ficheros reales y dice **qué** cambió, no solo que algo cambió.

## Contratos

Convenciones de siempre: español sin tildes en identificadores, `Decimal` para magnitudes, `date`/`datetime` con
zona, sin `float`, sin `eval`. Dependencias hacia dentro: `salida/` **puede** importar de `engine/`; `engine/`
**nunca** importa de `salida/` (hay test desde la Fase 0).

```python
# salida/constructor/manifiesto.py
MANIFIESTO_VERSION = "1.0"
class ErrorManifiesto(Exception): ...

@dataclass(frozen=True) class FicheroManifiesto:
    ruta: str          # relativa al paquete, estable y ordenable
    tipo: str | None   # tipo de documento clasificado; None si no se clasificó
    sha256: str
    bytes: int
    origen: str | None # sha256 del PDF combinado del que se separó, si aplica

@dataclass(frozen=True) class Manifiesto:
    actuacion_id, codigo_identificativo_propio, modelo_version, manifiesto_version
    generado_en: datetime                      # UTC explícito
    ficha: Mapping                             # codigo, version_ficha, version_spec, hash_spec
    ficheros: tuple[FicheroManifiesto, ...]    # orden estable por ruta
    hash_cabecera: str
    hash_detalle: str
    hash_log_eventos: str | None               # None si la actuación no trae log
    hash_manifiesto: str
    def a_dict() -> dict

def construir(actuacion_canonica, *, log=None, generado_en=None, raiz=None) -> Manifiesto
def verificar(manifiesto, *, raiz) -> ResultadoVerificacion   # contrasta contra los ficheros reales
@dataclass(frozen=True) class ResultadoVerificacion:
    integro: bool
    alterados: tuple[str, ...]      # ruta de cada fichero cuyo sha256 no coincide
    ausentes: tuple[str, ...]
    sobrantes: tuple[str, ...]      # ficheros en la carpeta que el manifiesto no declara
    motivo: str | None              # si el propio hash_manifiesto no cuadra
```

Reglas de cálculo, todas sobre el **JSON canónico** que ya usa el log (`engine.eventos.json_canonico`: claves
ordenadas, UTF-8, sin espacios, `Decimal` y fechas como cadena). No se inventa una segunda canonicalización:

| Hash | Sobre qué |
|---|---|
| `sha256` de cada fichero | Los bytes tal y como entraron en ingesta, **no** se recalculan leyendo de nuevo: se toman de `DocumentoRef.sha256`, y `verificar` los contrasta contra el disco |
| `hash_cabecera` | `json_canonico(actuacion.cabecera)` |
| `hash_detalle` | `json_canonico` de unidades, variables de actuación, evaluación y cálculo |
| `hash_log_eventos` | El `hash` del último evento, que ya encadena todo el log |
| `hash_manifiesto` | `json_canonico` del manifiesto **sin** este campo |

**La cabecera está vacía hoy** (S3.2 espera la aprobación de `cabecera_v1.yaml`). `hash_cabecera` se calcula
igualmente sobre `{}`: es un hash real de un contenido real, no un hueco. Cuando la cabecera se llene, el hash
cambiará y los manifiestos antiguos seguirán siendo verificables contra su propio contenido. Un test lo fija.

## Consecuencias

- Nace `salida/` con `constructor/`. `docs/01` §3.8 pasa de `S3` a `PARCIAL` (solo el constructor).
- `docs/03` §9 pasa de `NUEVO` a `EXISTE` en la parte del manifiesto interno.
- El test de dependencias de la Fase 0 (`engine/` no importa de `salida/`) cubre ya el módulo nuevo.
- El manifiesto **oficial** sigue sin existir: su formato es `TODO(API-02)` y el mapeo vivirá en
  `mapping/manifiesto.handoff.yaml` (S3.4), nunca en `engine/`.

## 5. Lo que queda para Billy (PROPUESTA)

1. **`hash_cabecera` sobre cabecera vacía**: se calcula hoy sobre `{}` y cambiará al aprobar `cabecera_v1.yaml`
   (S3.2). Si prefiere que el manifiesto se niegue a generarse sin cabecera, es una línea y un test.
2. El formato del manifiesto oficial sigue siendo `API-02`: lo que construimos es **el nuestro**.

## Verificación

El manifiesto del caso A se genera y `verificar` lo da íntegro · alterar un byte de cualquier adjunto lo detecta
y nombra el fichero · quitar un adjunto y añadir uno de más se detectan por separado · `hash_cabecera` y
`hash_detalle` presentes y reproducibles · `hash_manifiesto` invalida cualquier manipulación del propio
manifiesto · `python -m pytest -q` en verde sin romper los 1403 anteriores · `ruff` limpio.
