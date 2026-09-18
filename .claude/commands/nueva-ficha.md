---
description: Da de alta una ficha CAE nueva como configuración siguiendo el checklist de docs/04 §15, con cero cambios en engine/. Deja la spec en spec/propuestas/ hasta la aprobación de Billy.
argument-hint: <CODIGO_FICHA> (p. ej. IND170)
---

Actúa como `orquestador-arquitectura`; el trabajo lo hacen `spec-fichas` (spec, tablas), `generador-casos` (paquete sintético), `qa-evaluacion` (tests) y `revisor-normativo` (contraste con la ficha oficial). Ficha: `$ARGUMENTS`.

## Antes de empezar

- Comprueba en `docs/decisiones/ADR-001` §3 si la elección de esta ficha es una decisión abierta de Billy (segunda ficha: vecina vs. frío). Si lo es y no hay ADR que la cierre, **para y dilo**: puedes preparar el análisis, no la spec.
- Lee `docs/04` §15 (checklist), `docs/09` (qué exige esta ficha al marco, §3.1 y §4.2; incidencias de la fuente, §5), `spec/IND240_v1.1.yaml` como modelo y `spec/propuestas/cabecera_v1.yaml` (si está aprobada, la ficha hereda de ella).

## Checklist (docs/04 §15), en orden

1. Ficha oficial en BOE / catálogo MITECO: versión, fecha, URL. Anotar en `fuentes` de la spec. El BOE manda.
2. `spec/propuestas/<CODIGO>_v<version>.yaml` heredando la cabecera: solo lo específico de la ficha (ámbito, exclusiones, variables con fuentes y tipo de evidencia, tablas, cálculo, documentación, reglas con `fase`/`nivel`/`subsanacion`, estados, interpretaciones).
3. Todo lo que la ficha no cierre → `INT-xx` (continuando la numeración global). Las incidencias de `docs/09` §5 para esta ficha se revisan sobre el PDF original y, si se confirman, se convierten en `INT-xx`.
4. Tablas en `data/` con fuente, fecha, `verificado: pendiente` y vigencia (`data/README.md`).
5. `mapping/<CODIGO>.handoff.yaml`; el `.api.yaml` solo si existe diccionario (si no, esqueleto con `TODO(API-08)`).
6. Paquete sintético: un caso por veredicto (PREVALIDADO, SUBSANABLE, BLOQUEADO, NO_ELEGIBLE) + uno desordenado + uno con cabecera incompleta. Ground truth desde el mismo modelo de datos.
7. Tests: por regla, un caso que cumple y otro que falla; garantía NO_EVALUABLE → SUBSANABLE; metamórficas; composición (la ficha entra en un expediente con IND240 del mismo sector).
8. `revisor-normativo` contrasta spec ↔ ficha oficial y devuelve hallazgos.
9. **Cero cambios en `engine/`.** Si el marco no soporta algo (`docs/09` §4.2: ramas de cálculo, valor por defecto sustituible, documento "uno de N", series históricas, entrada externa…), se registra como **defecto del marco** en un ADR con la capacidad que falta; no se parchea la ficha ni se añade un `if` al motor.

## Cierre

La spec queda en `spec/propuestas/` con estado `propuesta`. ADR `PROPUESTA` con: resumen de la ficha, INT-xx abiertos, tablas transcritas pendientes de verificación, capacidades del marco que faltan (si las hay) y lo que Billy debe aprobar para activarla. `docs/09` §4.2 actualizado si se descubrió algo nuevo sobre el marco. Un commit `ficha <CODIGO>: propuesta de spec y banco de pruebas`.
