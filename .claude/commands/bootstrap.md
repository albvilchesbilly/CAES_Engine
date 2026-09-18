---
description: Primera sesión del repositorio. Crea el esqueleto de docs/01 y ejecuta la Fase 0 (reconstrucción del Engine 0.1) paso a paso con subagentes, con puerta de calidad en cada paso.
argument-hint: [hasta F0.n] (opcional: para en ese paso)
---

Actúa como `orquestador-arquitectura`. Objetivo: dejar el repositorio con el Engine 0.1 reconstruido según `docs/06` §1, o hasta el paso `$ARGUMENTS` si se indica.

## Protocolo

1. **Lee** `CLAUDE.md`, `docs/00`, `docs/01`, `docs/03`, `docs/04`, `docs/05`, `docs/06`, `docs/decisiones/ADR-001`. No empieces a escribir código antes de terminar la lectura.
2. **Contrasta el punto de partida**: confirma que no hay código previo (`engine/` no existe o está vacío). Si existe algo, para y pregunta antes de tocarlo.
3. **Escribe el plan de sesión** en `docs/decisiones/ADR-002-reconstruccion-engine-0.1.md` (estado `EN CURSO`): orden de pasos, agente por paso, criterio de aceptación de cada uno copiado de `docs/06` §1, y una sección "Decisiones de diseño tomadas durante la reconstrucción" que irás rellenando.
4. **F0.0** (tú): esqueleto completo de `docs/01` §1 con `__init__.py`, `pyproject.toml` (Python ≥ 3.11; dependencias `pyyaml openpyxl reportlab pillow pdfplumber`; extras `dev`: `pytest ruff`; config de pytest con marcador `ocr`; ruff línea 110), `.gitignore`, `README.md` mínimo. Verifica: `pytest -q` arranca y `ruff check .` pasa.
5. **F0.1 → F0.11**: para cada paso, delega al agente indicado en `docs/06` §1 con un brief cerrado (qué, ficheros, docs a leer, criterio de aceptación, qué no tocar). Después de cada paso, delega a `qa-evaluacion` la revisión; si devuelve `NO APTO`, vuelve al agente responsable con los hallazgos. No pases al siguiente paso sin `APTO` o `APTO CON RESERVAS` documentadas. Paraleliza solo pasos sin dependencia y sin ficheros compartidos (p. ej. F0.2 con F0.1; F0.5 con F0.3–F0.4).
6. **F0.5 en particular**: `generador-casos` fija los parámetros de E y F y recalcula su ground truth con `engine/calculo.py`; anótalos en el ADR-002 antes de seguir.
7. **Tras F0.9**: delega a `revisor-normativo` la revisión de `engine/reglas.py`, `engine/calculo.py` y `data/`. Sus hallazgos de tipo "interpretación silenciosa" se convierten en `INT-xx` propuestos (no en cambios de spec).
8. **F0.12 (cierre)**: actualiza marcas en `docs/03` y `docs/04` (`F0` → `EXISTE`/`PARCIAL`), `docs/01` si el árbol cambió, `docs/06` (estados y bitácora), completa el ADR-002 (estado `ACEPTADA` para lo técnico; `PROPUESTA` para lo que sea de Billy), y el `README.md` con instalación y ejecución en Windows (PowerShell) y Linux.
9. **Un commit por paso**: `F0.n: <qué>`; no agrupes pasos.

## Puerta de calidad final (todo debe cumplirse)

`python -m pytest -q` verde · `python evaluar_casos.py` 7/7 y caso A = 305.829,6 kWh/año · `ruff check . && ruff format --check .` limpio · `grep -rn "eval(" engine/` vacío · `engine/` no importa de `agentes/`/`salida/` · modo degradado comprobado · `docs/01` coincide con el árbol.

## Resumen final para Billy

Qué se construyó y con qué resultado (tabla de los 7 casos: esperado/obtenido/AETOTAL), diferencias respecto al Engine 0.1 documentado (`docs/05`), decisiones de diseño tomadas (ADR-002), **decisiones que son suyas** y siguen abiertas (`ADR-001` §3), y el siguiente paso propuesto de `docs/06` §2.
