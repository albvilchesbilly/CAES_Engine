# docs/cambios/ — fichas de implantación

Lo escribe el agente `arquitecto-implantador`. Una ficha por cambio (funcionalidad, mejora o bug) que
cruza la puerta de integración. Es el registro de **cómo** entró cada cosa; el **qué** y el **cuándo**
siguen en `docs/06`; el **por qué** de las decisiones, en `docs/decisiones/`.

Numeración `CHG-nnn` correlativa y global. Fichero `CHG-nnn-<slug>.md`.

## Plantilla

```markdown
# CHG-nnn · <título>

**Tipo**: funcionalidad · mejora (MEJ-nnn) · bug · **Origen**: <línea docs/06 | MEJ | test rojo | petición de Billy>
**Estado**: EN ANALISIS · EN CURSO · INTEGRADO (fecha, commit) · PENDIENTE DE BILLY (qué) · DESCARTADO (por qué)
**Hecho cuando**: <verificable con un comando o test>

## 1. Matriz de impacto

| Carpeta / doc | ¿Toca? | Ficheros | Agente | Notas |
|---|---|---|---|---|
| spec/ | no | | | |
| data/ | no | | | |
| engine/ | sí | engine/extraccion.py | ingesta-extraccion | interfaz Extractor sin cambios |
| agentes/ | no | | | |
| salida/ · mapping/ | no | | | |
| generator/ · expedientes/ | no | | | ground truth intacto |
| tests/ | sí | tests/test_extraccion.py, tests/test_integracion_chg_nnn.py | qa-evaluacion · implantador | |
| docs/03 · docs/04 (marcas) | sí | docs/04 §x | orquestador | PARCIAL → EXISTE |
| docs/HUECOS.md | no | | | |
| docs/decisiones/ (ADR) | no | | | |
| telemetria/ | no | | | la fase medida no cambia |
| Dependencias externas | no | | | |

Comprobaciones: dependencias hacia dentro ✔ · sin `if ficha ==` ✔ · sin Decimal→float ✔ · sin eval ✔

## 2. Supuestos resueltos por el implantador

- …

## 3. Preguntas

| # | Para | Pregunta | Opción recomendada y por qué | Respuesta / estado |
|---|---|---|---|---|

## 4. Briefs

### Brief → <subagente>
- Qué:
- Dónde (ficheros exactos):
- Criterio de aceptación (comando/test):
- No tocar:
- Devolver:

## 5. Puerta de integración (salida real pegada)

pytest -q → 
evaluar_casos.py → 
ruff → 
modo degradado → 
marcas docs/03-04 → 
docs/01 coincide con árbol → 
ADR / HUECOS → 
(mejora) métrica antes → después → 

## 6. Cierre

Commit: · Línea para docs/06: · Decisiones para Billy: · Aviso a mejora-continua: sí/no
```
