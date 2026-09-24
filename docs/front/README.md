# `docs/front/` — el paquete de pantalla

Aquí vive **el contrato de cada pantalla del front**, antes de que exista la pantalla. Es la aplicación
literal de `ADR-050` §"Paquete por pantalla para Claude Code" y de la decisión de Billy del 19/09/2026: el
contrato antes que las pantallas **no es negociable**.

```
docs/front/
  README.md                 este fichero
  pantallas/<perfil>-<pantalla>.md    el contrato: manda sobre todo lo demás
  mockups/<perfil>-<pantalla>.html    referencia visual; no es código base
```

| Pieza | Qué es | Qué no es |
|---|---|---|
| **Spec** (`pantallas/*.md`) | Objetivo · capacidades que ejerce · lecturas que consume · comandos que dispara · estados (incluidos vacío, cargando y error) · reglas `R-UI` aplicables · criterios de aceptación verificables | Un documento de diseño gráfico |
| **Mockup** (`mockups/*.html`) | Disposición, jerarquía visual y flujo, con datos reales del banco de pruebas. HTML y CSS a secas, sin dependencias | **No es código base.** No se copia a `front/`: no tiene accesibilidad, ni el sistema de diseño de `front/compartido/`, ni estados reales |

## La regla que resuelve cualquier duda

> **Si el mockup y la spec discrepan, manda la spec.**

Está en `ADR-050`, en `ADR-012` §4 y en `docs/01` §3.9 quater. El mockup se puede quedar viejo sin que pase
nada grave; la spec no, porque de ella salen los tests. Lo que mide "hecho" son los **criterios de
aceptación** de la spec, nunca el parecido con el mockup.

Y por encima de las dos, la precedencia de siempre (`CLAUDE.md` §1): BOE → plataforma oficial → catálogo
MITECO → `spec/*.yaml` activa → `docs/00` → `docs/02` → `docs/03`/`docs/04` → resto de `docs/` → código.

## Pantallas

| Pantalla | Perfil | Spec | Mockup | Entregable | Estado |
|---|---|---|---|---|---|
| Cola de revisión | `T-REV` | [`pantallas/T-REV-cola.md`](pantallas/T-REV-cola.md) | [`mockups/T-REV-cola.html`](mockups/T-REV-cola.html) | `FR1` (absorbe `S4.4`) | `EXISTE` (`front/workspace/src/cola/`) |
| Vista de revisión | `T-REV` | [`pantallas/T-REV-revision.md`](pantallas/T-REV-revision.md) | [`mockups/T-REV-revision.html`](mockups/T-REV-revision.html) | `FR1` | `EXISTE` (`front/workspace/src/revision/`) |

Marcas: `NUEVO` (diseño aprobado, sin implementar) · `PARCIAL` · `EXISTE` (implementada en `front/`). Se
actualizan **en la misma sesión** en que cambia el código (`CLAUDE.md` §3). `EXISTE` significa lo que dice
`ADR-014` §4: la pantalla cumple sus criterios de aceptación contra el contrato con un transporte de
pruebas, **no** que se abra en un navegador contra datos reales. Desde el 24/09/2026 sí se abre contra
**datos sintéticos**: `python servidor_desarrollo.py --desarrollo` publica `api/` y `npm run dev` en
`front/` monta las superficies (`GAP-HTTP-03`, cerrado; `ADR-015` §7.2). Contra datos **reales** sigue sin
abrirse, y eso es `FR-DESPLIEGUE`.

## Cómo se añade una pantalla nueva

1. **Comprobar que hay ADR.** Una pantalla nueva sale de una decisión, no de una idea: `ADR-050` para la
   superficie y el perfil, y un ADR propio si la pantalla añade contrato (como `ADR-012` para `FR1`).
2. **Leer la matriz antes de escribir nada**: `engine/capacidades.yaml` (qué capacidades tiene ese perfil,
   qué bloques proyecta cada lectura, cuáles están `pendiente`) y `api/proyeccion.py` (`CONSTRUCTORES`: los
   bloques que **de verdad** existen).
3. **Escribir la spec** en `pantallas/<perfil>-<pantalla>.md` con las siete secciones obligatorias:
   objetivo · capacidades · lecturas · comandos · estados (con vacío, cargando y error) · reglas `R-UI` ·
   criterios de aceptación. Cada criterio tiene que poder convertirse en un test sin reinterpretarlo.
4. **No inventar nada.** Todo lo que la spec pida existe en `engine/capacidades.yaml` y en
   `api/proyeccion.py`, o va en una tabla **"lo que hoy no existe en `api/`"** con: qué falta, qué haría
   falta exactamente y qué hace la pantalla mientras tanto. Una spec que pide un bloque inexistente es una
   spec que se incumple el primer día.
5. **Comprobar las doce reglas `R-UI`** de `ADR-050` una por una y dejar en la spec las que aplican, con
   cómo se cumplen. Las cuatro que siempre acaban en criterios de aceptación de una pantalla de trabajo:
   `R-UI-02` (ningún control fija un veredicto), `R-UI-04` (corregir exige justificación), `R-UI-05` (solo
   lectura una vez firmada y entregada, salvo requerimiento abierto — **no** basta con mirar
   `estado_ciclo == "EN_PLATAFORMA"`: al llegar un requerimiento el ciclo deja de serlo, y el candado se
   abriría justo cuando debe cerrarse; lo descubrió `FR1.c`) y `R-UI-09` (todo dato extraído con su cita).
6. **Dibujar el mockup** en `mockups/<perfil>-<pantalla>.html`, HTML y CSS a secas, sin dependencias, con
   datos del banco de pruebas y **nunca inventados**. El propio fichero dice, en su primera línea visible,
   que no es código base y que manda la spec.
7. **Registrar la pantalla** en la tabla de este README y, si la estructura cambia, en `docs/01`.
8. **Al implementar**: los criterios de aceptación se convierten en tests dentro de `front/<superficie>/`,
   y la marca de la tabla pasa a `EXISTE` en la misma sesión.

## Lo que nunca entra en una pantalla

- **Lógica de negocio** (`R-UI-11`): no calcula, no evalúa reglas, no decide transiciones y no reordena lo
  que le llega (`ADR-012` §3, regla 3 del contrato C18).
- **Autorización propia** (`R-UI-01`): ocultar un control no es autorizar. El servidor concede o niega, y un
  `ErrorPermiso` **se muestra**, no se traga.
- **Un `if ficha == …`**, en cualquiera de sus disfraces, incluido un diccionario de etiquetas por ficha en
  el front. La ficha es configuración (regla de oro 4): lo que la pantalla necesite de la spec lo sirve
  `api/`.
- **Textos que mienten**: nada dice "CAE garantizado", nadie llama "verificador" a A8, un kWh prevalidado
  lleva siempre su rótulo (`R-UI-06`) y `SIN DATO` no se pinta como cero (`R-UI-07`).
