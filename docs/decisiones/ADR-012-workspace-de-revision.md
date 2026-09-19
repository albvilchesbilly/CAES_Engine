# ADR-012 — Workspace de revisión (`T-REV`): cola y vista de revisión (FR1)

**Estado**: ACEPTADA (técnica) · PROPUESTA (§6, lo que decide Billy)
**Fecha**: 2026-09-19
**Decide**: Claude (técnica) · Billy (lo marcado `PROPUESTA` en §6)
**Ámbito**: `api/` (lectura de documento), `front/compartido/api/`, `front/workspace/`, `docs/front/`, `tests/`

## Contexto

`FR1` es **la pantalla donde se mide el valor del producto**. Todo lo construido hasta ahora —ingesta,
evidencias, cálculo, reglas, veredicto— existe para que un profesional pueda revisar una actuación en minutos
en vez de en horas. Si esa pantalla no lo consigue, el resto no se nota.

Absorbe `S4.4`, cuyo "hecho cuando" se mantiene literal: cola de escalados, conflictos, correcciones y tareas
pendientes **consumidas del simulador**. Y hereda de `ADR-050` la forma de la vista de revisión: pantalla
partida, el documento a la izquierda con la evidencia resaltada, a la derecha variables, reglas, cálculo y
veredicto, cada dato enlazado a su cita.

`FR0` dejó `api/` con las 12 capacidades de `T-REV` y `front/compartido/` con los tres rótulos. Falta el
cliente entre los dos, las dos pantallas, y una pieza que nadie había mirado: **cómo llega el documento**.

## 1. La decisión de alcance: el revisor tiene que ver el documento

`api/` devuelve hoy **metadatos** del documento (`doc_id`, huella, páginas, método de lectura, tipo), no el
documento. Con eso se puede pintar la cita —página y texto literal— pero no el papel.

**Una pantalla de revisión que solo muestra el texto extraído le pide al revisor que se fíe de nuestra
extracción, que es exactamente lo que la revisión existe para comprobar.** `R-UI-09` se cumpliría en la letra
(«muestra **o enlaza** su cita») y se incumpliría en el espíritu: revisar sería validar nuestro propio
trabajo mirándolo en nuestro propio formato.

**Decisión: `FR1` sirve el documento, bajo `CAP-03`.** No hace falta una capacidad nueva: `CAP-03` es
literalmente «consultar la actuación completa: **documentos**, evidencias, conflictos, cálculo, veredicto,
historial». Servir el documento es leerlo, y quien tiene `CAP-03` ya puede.

Condiciones, que son las de siempre:

- **Aislamiento por tenant**: los bytes pasan por el mismo `exigir` que el resto. Un documento de otro tenant
  es `ErrorPermiso`, no un 404 ambiguo.
- **Se sirve por huella, nunca por ruta.** El cliente pide `doc_id`; el repositorio resuelve dónde está. Una
  ruta en la petición es un camino a leer ficheros arbitrarios del servidor.
- **La huella se comprueba al servir.** Si los bytes del disco ya no casan con el `sha256` que declaró la
  ingesta, no se sirve: se informa de que el documento fue alterado. Es el mismo criterio del manifiesto.
- **`R-UI-12` también aquí**: un perfil sin ámbito de contenido no recibe los bytes, no es que no los pinte.

## 2. Contrato C17 — lectura de documento (`api/lecturas/documentos.py`)

```python
@dataclass(frozen=True) class Documento:
    doc_id: str                      # la huella, que es la identidad (`docs/03` §5.2)
    tipo: str | None
    medio: str                       # "application/pdf", "image/jpeg"…
    bytes: int
    paginas: int
    contenido: bytes
def leer_documento(peticion) -> Respuesta     # `datos["documento"]`; CAP-03; ErrorPermiso si no procede
```

No transforma nada: entrega los bytes tal y como entraron en ingesta. Rotar, ampliar o resaltar es del
navegador, no del servidor; el servidor que retoca un documento deja de poder demostrar que es el mismo.

## 3. Contrato C18 — el cliente (`front/compartido/api/`)

```ts
type Respuesta = { capacidad: string; rol: string; eventos: string[]; datos: unknown; avisos: string[] }
cliente.leer(capacidad, contexto, datos?) → Promise<Respuesta>
cliente.ejecutar(capacidad, contexto, datos) → Promise<Respuesta>
```

Cuatro reglas:

1. **El cliente no decide permisos.** No mira capacidades para habilitar nada: pide, y el servidor concede o
   niega. `R-UI-01` dice que ocultar un control no es autorización; el corolario es que el front tampoco
   autoriza por su cuenta.
2. **Un `ErrorPermiso` se muestra, no se traga.** Un control que desaparece sin explicación es un control que
   nadie arregla; un error que dice «esta capacidad espera la decisión A3» es información.
3. **El cliente no reordena ni recalcula** lo que llega. `R-UI-11`.
4. **Tipos derivados del contrato, no escritos a mano** donde se pueda: si `api/` cambia un bloque, el front
   tiene que enterarse al compilar y no en producción.

## 4. Contrato C19 — las dos pantallas (`front/workspace/`)

Cada una con su spec en `docs/front/pantallas/` y su mockup en `docs/front/mockups/` (`ADR-050`). **Si el
mockup y la spec discrepan, manda la spec.**

**Cola de revisión** (`T-REV-cola`), pantalla de inicio del perfil. Es el "hecho cuando" de `S4.4`: escalados,
conflictos, correcciones pendientes y tareas de la plataforma, **consumidas del simulador**, priorizadas por
motivo y antigüedad. Cada fila dice por qué está ahí y cuánto lleva esperando.

**Vista de revisión** (`T-REV-revision`), pantalla partida:

- Izquierda: el documento, con la página de la cita y el texto literal resaltado.
- Derecha: variables, reglas, cálculo y veredicto. **Cada dato enlaza a su cita** (`R-UI-09`); pulsarla mueve
  el panel izquierdo a esa página.
- **No existe control para cambiar el veredicto** (`R-UI-02`). Se corrige el dato y el motor recalcula. Esto
  no es una restricción de interfaz: es la regla de oro 1 hecha pantalla.
- Corregir exige justificación (`R-UI-04`), que viaja al log.
- Tras `EN_PLATAFORMA`, todo es solo lectura salvo requerimiento abierto (`R-UI-05`).
- «Aprobar» solo se activa sin bloqueantes abiertos, y es `CAP-10`.

## 5. Verificación

- `R-UI-02`: no existe en todo `front/workspace/` ningún control que fije un veredicto. Test que recorre el
  árbol, no solo la pantalla.
- `R-UI-04`: corregir sin justificación no llega a `api/`, y la justificación acaba en el log.
- `R-UI-05`: con la actuación en `EN_PLATAFORMA` y sin requerimiento abierto, ningún control de escritura
  está activo; con requerimiento abierto, sí.
- `R-UI-09`: ningún dato extraído se pinta sin su cita; un dato sin cita es un defecto visible en el test.
- La cola sale del simulador, no de datos inventados, y el caso A recorre la pantalla entera.
- Puerta de siempre: `pytest -q` sin romper los 2.388 · `npm test` en `front/` · `evaluar_casos.py` 7/7 con
  el caso A en 305.829,6 · `ruff` limpio.

## 6. Lo que queda para Billy (PROPUESTA)

1. **Servir el documento bajo `CAP-03`** (§1): es una lectura de lo que `CAP-03` ya nombra, pero conviene que
   lo confirmes, porque significa que quien revisa ve el papel original del cliente.
2. **Minutos de revisión como métrica** (B5 de `ADR-006`): esta pantalla es el punto de medida candidato. Si
   quieres medirlo desde el primer día, hay que instrumentarla ahora y no después.
3. **C6 (idiomas y accesibilidad)** sigue abierta y empieza a costar: cada pantalla que se escribe sin i18n es
   una pantalla que hay que volver a tocar.
4. **Linter y formateador de TypeScript**: `ruff` no ve `front/`, así que hoy el front no tiene el control que
   sí tiene el resto del repositorio.
