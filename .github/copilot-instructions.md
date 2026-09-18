# Instrucciones para GitHub Copilot — CAE Engine

Este repositorio es el **CAE Engine**: motor de prevalidación de actuaciones CAE (certificados de ahorro energético, RD 36/2023, Orden TED/815/2023). La fuente de verdad para trabajar aquí es `CLAUDE.md` y la carpeta `docs/`. Estas instrucciones son un resumen; **si algo discrepa, manda `CLAUDE.md`**.

## Antes de sugerir código

Lee `CLAUDE.md`, `docs/00-instrucciones-de-entrada.md`, `docs/01-estructura-del-repositorio.md` y, para cualquier módulo, `docs/03-arquitectura-backend.md` y `docs/04-motor-de-reglas-y-specs.md`. El plan y el estado están en `docs/06-plan-de-construccion.md`. Lo que ya está decidido y no se reabre: `docs/decisiones/ADR-001-decisiones-vigentes.md`.

## Reglas que nunca se rompen

- **La IA lee; el motor calcula.** Ningún LLM ejecuta la fórmula ni decide si una regla se cumple.
- **Todo dato lleva evidencia** (documento, página, texto literal, método, confianza). Sin cita no entra.
- **La ficha es configuración.** Añadir una ficha es añadir YAML en `spec/`. Un `if ficha == "IND240"` en `engine/` es un defecto.
- **Ante conflicto entre fuentes fiables, el motor se detiene** (`valor_consumido = null`), no elige.
- **Lo que la norma no cierra es un `INT-xx`** declarado en la spec, nunca un criterio escondido en código.
- **Lo que la plataforma oficial no ha documentado es `TODO(API-xx)`** con fila en `docs/HUECOS.md`. No inventes campos de la API.
- **Cambios en `spec/*.yaml` activa, `data/` o `expedientes/_resultados_esperados/` pasan por revisión humana.** Propón en `spec/propuestas/` o en un ADR.
- `Decimal`, nunca `float`, en todo lo que toque el ahorro. `AETOTAL` truncado a kWh entero.
- **Nada de `eval()`/`exec()`.** `logica` y `formula` se interpretan con `engine/expresiones.py` (lista blanca).
- SHA-256 de todo fichero en ingesta; vinculación por hash y nº de serie, nunca por nombre de fichero.
- **Dependencias hacia dentro**: `engine/` no importa de `agentes/` ni de `salida/`.
- Nunca custodiamos certificados de representante; la firma es humana; no existe `salida/firma/` como código.
- Ningún texto dice "CAE garantizado". A8 no se llama "verificador".

## Vocabulario

`Actuacion` es la unidad de trabajo (lo que antes se llamaba "expediente"). `GrupoActuaciones` se verifican juntas. `Expediente` es la agregación oficial de actuaciones `VERIFICADA_FAVORABLE` (misma CCAA + año + sector + verificador). Cuatro niveles de estado que no se mezclan: veredicto (`NO_ELEGIBLE` > `BLOQUEADO` > `SUBSANABLE` > `PREVALIDADO`), estado de ciclo, estado de plataforma de la actuación (8, confirmados), estado de plataforma del expediente (provisionales, `NO OFICIAL`). Resultado de regla: `CUMPLE` / `FALLA` / `NO_EVALUABLE`.

## Convenciones de código

Python ≥ 3.11; paquetes planos (`engine/`, `agentes/`, `salida/`, `generator/`), ejecución con `python -m`. Nombres en español sin tildes (`evaluar_actuacion`, `hash_reglas`); clases en CamelCase. `ruff` (línea 110). `pathlib`, nunca `os.system`. Tests con `pytest`, un fichero por módulo, nombres `test_<que>_<condicion>`; los que necesiten OCR (`tesseract`/`poppler`) llevan `@pytest.mark.ocr` y se saltan si no están instalados (el entorno principal es Windows con PowerShell).

## Definición de hecho

`python -m pytest -q` en verde · `python evaluar_casos.py` 7/7 veredictos y caso A en **305.829,6 kWh/año** · `ruff check . && ruff format --check .` limpio · marcas de estado actualizadas en `docs/03`/`docs/04` · `docs/01` coincide con el árbol. Un test que rompe no se borra ni se relaja: se explica. Commits en español con el identificador del plan (`F0.3: …`, `S3.1: …`).

## Decisiones que no toma Copilot

Proveedor LLM y condiciones de datos · umbral de activación de agentes · vía del perfil Modificación · aprobación de `spec/propuestas/` · familias de reglas nuevas · Expediente Builder · segunda ficha · singulares/CVP · posición comercial · orden de contactos. Si una sugerencia depende de una de ellas, deja la alternativa preparada y márcalo.
