# CAE Engine

Motor de prevalidación de actuaciones CAE (certificados de ahorro energético, España): convierte documentación desordenada de una actuación de eficiencia energética en una actuación trazable, calculada de forma determinista y prevalidada.

**Estado (19/09/2026): Fase 0 cerrada.** El Engine procesa las siete carpetas de prueba de principio a fin y
reproduce el ground truth: 7/7 veredictos y el caso A en **305.829,6 kWh/año** exactos. 999 tests en verde
(976 y 23 saltados si no hay OCR). Lo que viene es el Sprint 3 (`docs/06` §2). Lo que la Fase 0 **no** hace, por
diseño: modelo canónico completo, log de eventos, máquina de estados, cabecera común, salida a plataforma y
agentes con LLM.

## Instalación

Python ≥ 3.11. El OCR es opcional: sin él la suite salta 23 tests y el banco de pruebas sigue dando 7/7.

**Linux / macOS**

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
sudo apt-get install -y tesseract-ocr tesseract-ocr-spa   # opcional (OCR)
```

**Windows (PowerShell)**

```powershell
py -3.11 -m venv .venv; .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
# OCR opcional: instalar Tesseract (UB Mannheim) con el paquete de idioma `spa`
# y añadir su carpeta al PATH; sin él, los tests marcados `ocr` se saltan solos.
```

## Cómo se usa

```bash
# Prevalidar una actuación: informe markdown + JSON en informes/
python -m engine.cli expedientes/EXP001-A_completo --md informe.md --json informe.json
python -m engine.cli <carpeta> --sin-ocr --fecha 2026-09-18      # sin OCR, fecha de evaluación fija

# Banco de pruebas: matriz esperado/obtenido de los 7 casos
python evaluar_casos.py                 # 7/7 y caso A = 305.829,6; código de salida 0
python evaluar_casos.py --sin-ocr --caso A

# Regenerar los casos sintéticos (determinista: mismos bytes)
python -m generator.generar

# Servir `api/` por red, en local y contra los 7 casos sintéticos (FR-HTTP, ADR-015)
pip install -e ".[http]"                # starlette y uvicorn: extra, nunca dependencia obligatoria
python servidor_desarrollo.py --desarrollo
# Sin `--desarrollo` no arranca: lee el principal de una cabecera y no comprueba ninguna credencial,
# así que solo sirve en el bucle local y lo dice en `avisos` de cada respuesta.

# Puerta de calidad completa
python -m pytest -q
ruff check . && ruff format --check .
```

Códigos de salida de la CLI: `0` si el veredicto es `PREVALIDADO` o `SUBSANABLE`, `1` si es `BLOQUEADO` o
`NO_ELEGIBLE`, `2` si no se pudo evaluar.

## Qué hay dentro

| Pieza | Qué hace |
|---|---|
| `spec/IND240_v1.1.yaml` | La ficha como configuración: ámbito, variables, fórmula, 26 reglas, INT-01..07 |
| `engine/expresiones.py` | Parser de lista blanca que ejecuta la `logica` y la `formula` del YAML. Nunca `eval` |
| `engine/spec_registry.py` | Carga y valida la spec; garantía `NO_EVALUABLE` → `SUBSANABLE`; `hash_reglas` |
| `engine/ingesta.py` y `clasificacion.py` | SHA-256 de todo fichero, OCR, separación de PDF combinados, tipo con confianza |
| `engine/extraccion.py` y `registro_xlsx.py` | Evidencias con documento, página, cita literal, método y confianza |
| `engine/evidencias.py` | Tres capas por dato; ante conflicto entre fuentes fiables, no elige: se detiene |
| `engine/reglas.py` y `calculo.py` | Veredicto por fases y cálculo determinista con `Decimal` y traza |
| `engine/informe.py` y `cli.py` | Informe de prevalidación con evidencias, carencias e interpretaciones |

## Lo que todavía no está cerrado

El valor de pérdidas de 110 kW del cuadro 6 (5,55 kW) sostiene el criterio de aceptación y **no ha podido
contrastarse contra el DOUE** en este entorno; 38 de las 39 filas de `data/reg_2019_1781_cuadro6.csv` están
marcadas `verificado: pendiente`. La revisión normativa dejó 22 hallazgos y cinco interpretaciones nuevas
propuestas en `docs/decisiones/ADR-003-hallazgos-normativos-fase-0.md`, ninguna aplicada. Ningún resultado del
Engine implica CAE garantizado.

## Por dónde empezar

| Si eres… | Lee |
|---|---|
| Una persona que entra al proyecto | `docs/00-instrucciones-de-entrada.md` |
| Claude Code | `CLAUDE.md` y después `/bootstrap` |
| GitHub Copilot | `.github/copilot-instructions.md` |
| Alguien que va a tocar código | `docs/01`, `docs/03`, `docs/04` en ese orden |

## Mapa

```
CLAUDE.md          reglas, vocabulario, orquestación
docs/              00 esencia · 01 estructura · 02 plataforma oficial · 03 arquitectura · 04 reglas y specs
                   05 evaluación · 06 plan · 07 entorno · 08 clientes · 09 catálogo · HUECOS.md · decisiones/ · historico/
spec/              IND240_v1.1.yaml (activa) · propuestas/ (pendientes de aprobación)
data/              tablas normativas (README con procedimiento de transcripción)
.claude/           agentes y comandos de Claude Code
.github/           instrucciones de Copilot
```

## Descargo

Ningún resultado del Engine implica CAE garantizado. La emisión requiere dictamen favorable de verificador acreditado y solicitud por sujeto obligado o delegado. Los documentos de prueba son sintéticos.
