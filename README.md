# CAE Engine

Motor de prevalidación de actuaciones CAE (certificados de ahorro energético, España): convierte documentación desordenada de una actuación de eficiencia energética en una actuación trazable, calculada de forma determinista y prevalidada.

**Estado (18/09/2026): Fase 0 en curso** (reconstrucción del Engine 0.1, `docs/06-plan-de-construccion.md`, plan en `docs/decisiones/ADR-002`). Este README se completa al cerrar la fase.

## Instalación mínima

```bash
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m pytest -q
ruff check . && ruff format --check .
```

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
