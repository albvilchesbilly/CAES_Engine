# ADR-013 — Recálculo tras corrección humana (S3.8)

**Estado**: ACEPTADA (técnica) · PROPUESTA (§6, lo que decide Billy)
**Fecha**: 2026-09-20
**Decide**: Claude (técnica) · Billy (lo marcado `PROPUESTA` en §6)
**Ámbito**: `engine/correcciones.py` (nuevo), `engine/evidencias.py`, `engine/motor.py`, `docs/03` §5.3 y §8, `tests/`

## Contexto

`R-UI-02` —la pantalla de revisión no tiene control para cambiar el veredicto— se justifica con una frase:
**«se corrige el dato y el motor recalcula»**. Escribir la spec de esa pantalla (`FR1`) destapó que **la
segunda mitad no ocurre**: `CAP-05` escribe `DatoCorregidoPorHumano` en el log y nada recalcula.
`procesar_actuacion` recibe una carpeta y nada más; no hay una sola referencia al log en `engine/motor.py`.

Consecuencia medible: en el caso C —110 kW en la ficha contra 90 kW en la factura— el revisor elige la
evidencia buena, escribe su justificación, y la pantalla tiene que rotular «pendiente de recálculo» porque el
veredicto sigue siendo el viejo. **El circuito de revisión no se cierra justo en el caso que lo justifica.**

Esto no es deuda de interfaz: es una pieza que falta en el núcleo.

## 1. La decisión: una corrección humana es una evidencia más

La tentación es tratar la corrección como un parche: un diccionario de sobrescrituras que se aplica encima del
resultado. Sería más corto y rompería tres reglas de oro a la vez — el dato no llevaría evidencia (regla 2), se
perderían las tres capas (regla 3) y el valor consumido dejaría de tener trazabilidad hasta su origen.

**Decisión: la corrección entra en el Evidence Store como una evidencia, con sus tres capas completas.** Su
cita no es un documento del cliente: es el propio acto humano, que está en el log y es igual de auditable.

| Capa | Qué lleva una corrección |
|---|---|
| Documento | El evento: `evento_id`, `actuacion_id`, instante, y el `hash` que lo encadena al log |
| Interpretación | `metodo: "correccion_humana"`, `texto_literal`: **la justificación que escribió la persona**, `confianza: 1`, y quién la hizo (`actor.id` y `actor.rol`, obligatorio desde A8) |
| Cálculo | El valor entra en la consolidación como cualquier otra fuente fiable y el motor recalcula sin saber que vino de una persona |

Tres consecuencias buscadas:

1. **El informe la enseña sola.** No hay que tocar `engine/informe.py`: una corrección aparece en la tabla de
   evidencias con su cita, como la factura o el certificado. Quien audite ve quién decidió y por qué.
2. **El replay la reproduce.** `engine.eventos.replay` reconstruye el veredicto **solo con el log**; si la
   corrección está en el log, el veredicto corregido se reproduce bit a bit. Es el test que de verdad prueba
   que la pieza está bien puesta.
3. **La justificación deja de ser burocracia.** `R-UI-04` la exige; aquí **se usa**: es el texto literal de la
   cita. Una corrección sin justificación no tendría cita, y sin cita no entra (regla 2).

## 2. Contrato C20 — las correcciones (`engine/correcciones.py`)

```python
METODO = "correccion_humana"
TIPO_EVENTO = "DatoCorregidoPorHumano"

@dataclass(frozen=True) class Correccion:
    variable: str
    valor: str                     # como cadena; a Decimal lo convierte la consolidacion, nunca float
    justificacion: str             # el texto literal de la cita
    actor_id: str
    actor_rol: str
    evento_id: str
    instante: datetime
    num_serie_motor: str | None = None
    origen: str | None = None      # `desacuerdo` (CAP-06) o `conflicto`/`carencia` (CAP-05)

def de_log(log) -> tuple[Correccion, ...]      # en orden de secuencia; la ultima de cada clave manda
def a_evidencia(correccion) -> Evidencia       # las tres capas, con `metodo = METODO`
```

Cinco reglas:

1. **La última corrección de cada `(variable, num_serie_motor)` manda.** El log es solo-añadir: corregir dos
   veces no es un conflicto, es cambiar de opinión, y la traza de las dos queda.
2. **Precedencia sobre la evidencia documental**, y solo sobre ella. Una persona con rol que ha visto las dos
   evidencias enfrentadas decide mejor que un extractor; para eso existe la pantalla.
3. **El conflicto no se borra: se resuelve.** Las evidencias enfrentadas siguen en `DatoConsolidado.evidencias`
   (regla 3) y el `valor_consumido` pasa a ser el corregido. Quien lea el informe ve qué había y qué se eligió.
4. **Una corrección no inventa una variable que la spec no declara**: es error, no un dato nuevo. La ficha
   sigue siendo la que dice qué existe (regla de oro 4).
5. **Sin justificación no hay evidencia**, porque no hay cita (regla 2). `R-UI-04` deja de ser solo una regla
   de interfaz y pasa a ser una condición del núcleo.

## 3. Contrato C21 — reprocesar (`engine/motor.py`)

```python
def procesar_actuacion(carpeta, *, spec_id=None, fecha_evaluacion=None, ocr=True, registro=None,
                       correcciones: Sequence[Correccion] = ()) -> Actuacion
```

Un parámetro más, con valor por defecto vacío: **la firma pública no cambia para quien no corrige**, y los
7 casos del banco siguen dando exactamente lo mismo. Es la condición de aceptación que lo protege todo.

Quien tiene el log llama `procesar_actuacion(carpeta, correcciones=de_log(log))`. El motor no lee el log: lo
lee quien lo tiene, y le pasa datos planos, igual que hace `engine/seguimiento.py` con los estados de
plataforma. **El núcleo no adquiere una dependencia de dónde viven los eventos.**

## 4. Lo que NO hace este entregable

- **No reprocesa solo.** Nadie dispara el recálculo automáticamente: lo pide quien tiene el log (hoy, `api/`
  en la siguiente iteración de `FR1`). Un motor que se reprocesa a sí mismo es un motor que no sabes cuándo
  corrió.
- **No toca la inalterabilidad**, pero sí la defiende. La frase original de este ADR —«si el evento no debió
  escribirse, no está en el log»— **era falsa**, y lo destapó construirlo: `engine/estados.py` no levanta ante
  un cambio de datos posterior a la firma, lo **anota** en `Proyeccion.rechazos`, y el evento queda sellado
  igual. Sin filtro, reprocesar una actuación firmada aplicaba una corrección que la inalterabilidad prohíbe
  (`docs/02` §5.4). **`de_log` descarta las correcciones que el ciclo rechazó**, y lo hace ahí porque tiene el
  log y puede proyectarlo: una guarda que depende de que el llamante se acuerde no es una guarda. Sigue
  faltando que `api/` emita `CorreccionRechazadaPostFirma` al intentarlo (§6 punto 4).
- **No decide qué se puede corregir.** Que solo se corrija lo que está en conflicto, en desacuerdo o en
  carencia es criterio de la pantalla (`FR1`), no del motor. El motor acepta la corrección que le den y la
  hace trazable.

## 5. Verificación

- **Los 7 casos sin correcciones dan exactamente lo mismo**: `evaluar_casos.py` 7/7 y el caso A en
  **305.829,6 kWh/año**. Es la primera comprobación, no la última.
- **Caso C**: con la corrección que elige 110 kW, el conflicto se resuelve, `valor_consumido` deja de ser
  `null`, el veredicto deja de ser `BLOQUEADO` y **aparece un ahorro que antes no existía**. Sin la
  corrección, sigue `BLOQUEADO`.
- **La corrección sale en el informe con su cita**: quién, cuándo, con qué rol y con qué justificación.
- **El replay reproduce el veredicto corregido** solo con el log, bit a bit.
- **Dos correcciones de la misma variable**: manda la última y las dos quedan en la traza.
- **Sin justificación**: no entra.
- **Variable que la spec no declara**: error.
- Puerta de siempre: `pytest -q` sin romper los 2.441 · `ruff` limpio · `engine/` sin importar de nadie.

## 6. Lo que queda para Billy (PROPUESTA)

1. **Precedencia de la corrección humana sobre la evidencia documental** (§2 regla 2). Es lo razonable —una
   persona que ve las dos evidencias decide mejor que un extractor— pero significa que **un humano puede fijar
   un valor contra lo que dice un documento**. Queda trazado y justificado, nunca oculto; aun así, confírmalo.
2. **Qué se puede corregir**: hoy la pantalla lo limita a conflicto, desacuerdo y carencia. Si se quiere
   permitir corregir cualquier dato, es cambiar la pantalla, no el motor — y se pierde saber qué leyó el motor.
3. **Si una corrección debe caducar** cuando llega documentación nueva que la contradice. Hoy no caduca: manda
   la última corrección. No es obvio que sea lo correcto para siempre.
4. **Corregir un hecho documental** (`factura.firmada`, `registro.dias`) no se puede hoy: la regla 4 se
   implementó estricta contra `spec.variables`. La pantalla de `FR1` permite corregir carencias, y una
   carencia puede caer sobre un hecho documental. Es un hueco funcional, no un defecto: decide si se abre.
5. **`R-CON-03` deja de evaluarse tras corregir una variable con `cruce_con`** (`N2`, `P_prom`), porque la
   corrección se queda sola y desaparece una de las dos mitades del cruce declarado ↔ derivado. Está probado
   y documentado. Que la corrección sustituya solo **dentro de su tipo de evidencia** complicaría el
   consolidador; no se hace sin decisión.
