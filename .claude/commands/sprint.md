---
description: Ejecuta el siguiente entregable pendiente de docs/06 (o el indicado, p. ej. S3.1) con subagentes, puerta de calidad y actualización del plan.
argument-hint: [S3.1 | S3.4 | siguiente]
---

Actúa como `orquestador-arquitectura`. Entregable objetivo: `$ARGUMENTS` (si está vacío o es "siguiente": el primer `PENDIENTE` de `docs/06` cuyas dependencias estén `HECHO`).

## Protocolo

1. Lee `CLAUDE.md`, `docs/06`, `docs/decisiones/ADR-001` y los documentos que el entregable cite (`docs/03`, `docs/04`, `docs/02`, `docs/HUECOS.md` según toque). Contrasta `docs/06` con el repo (`git log`, `pytest -q`) y corrige estados desactualizados antes de empezar.
2. Si el entregable está `BLOQUEADO (decisión)`: no lo desbloquees. Construye la parte que no depende de la decisión, deja la alternativa preparada donde `docs/06` indica (p. ej. `spec/propuestas/`, proveedor configurable), márcalo en el resumen y elige el siguiente.
3. Si el entregable está `BLOQUEADO (externo)`: comprueba `docs/HUECOS.md`; si no hay documentación oficial nueva, no lo intentes. Elige el siguiente.
4. Escribe `docs/decisiones/ADR-nnn-<entregable>.md` si el entregable introduce arquitectura nueva (modelo canónico, log, estados, puerto de salida, runtime). Estado `PROPUESTA` si toca algo de la lista de Billy; si no, `ACEPTADA` al cerrar.
5. Marca la línea `EN CURSO` en `docs/06`. Descompón en briefs cerrados para los subagentes de `docs/06` (columna Agente) y para `qa-evaluacion` después de cada uno. Sin ficheros compartidos en paralelo.
6. Criterio de cierre: exactamente el "hecho cuando" de `docs/06`, ni más ni menos. Si no puedes verificarlo con un comando o un test, reescribe el criterio en `docs/06` para que se pueda, y dilo.
7. Puerta de calidad de `CLAUDE.md` §4–§5. Marcas de estado en `docs/03`/`docs/04` actualizadas; `docs/01` si cambió la estructura; `docs/HUECOS.md` si abriste huecos.
8. Un commit: `<ID>: <qué>` (p. ej. `S3.1: modelo canónico, log de eventos y máquina de estados`).
9. `docs/06`: línea a `HECHO (fecha, commit)`; fila nueva en la bitácora §7.

## Resumen final para Billy

Qué está hecho y cómo se verificó · qué quedó a medias y por qué · decisiones tomadas (ADR) · **decisiones suyas** que tocan este entregable · riesgos nuevos · siguiente entregable propuesto.
