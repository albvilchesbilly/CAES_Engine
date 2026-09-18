# docs/mejoras/ — propuestas de mejora continua

Lo escribe el agente `mejora-continua`. Nada de lo que hay aquí está activo: son propuestas con evidencia.
Una propuesta se convierte en cambio cuando pasa por `/implantar` (ficha `CHG-nnn` en `docs/cambios/`) o,
si toca spec, severidades o `INT-xx`, cuando Billy la aprueba.

```
docs/mejoras/
  README.md            Este fichero
  ESTADO.md            Última pasada, ventana analizada, alertas abiertas, MEJ por estado
  MEJ-2026-10-03.md    Un informe por pasada completa (fecha). Contiene una o varias MEJ-nnn
```

Numeración de propuestas: `MEJ-nnn` correlativa y global (no por informe). Nunca se reutiliza.

## Plantilla de informe `MEJ-<fecha>.md`

```markdown
# Mejora continua — pasada completa <fecha>

Ventana: <desde> → <hasta> · líneas de telemetría: <n> · commit: <hash> · fase del plan: <F0|S3|S4>

## 1. Línea base

| Eje | Métrica | Valor | Fuente |
|---|---|---|---|
| Coste | tokens por actuación (media, p95) | SIN DATO (sin LLM hasta S3.6) | — |
| Valor | variables solo declaradas por caso (media) | 2,1 | evaluacion_caso.variables |
| Valor | reglas NO_EVALUABLE por caso (media) | 3,4 | evaluacion_caso.reglas |
| Latencia | tiempo total por caso (media, p95) | 2.140 ms / 3.900 ms | evaluacion_caso.tiempo_ms |

## 2. Propuestas aplicadas anteriormente — resultado

| MEJ | CHG | Objetivo | Real | Estado |
|---|---|---|---|---|

## 3. Propuestas nuevas (ordenadas por impacto × esfuerzo)

### MEJ-nnn · <título corto>

- **Eje**: coste · valor · latencia
- **Tipo**: prompt · router · extractor-reglas · spec · arquitectura · tests
- **Evidencia**: casos, reglas, variables y líneas de telemetría concretas. Sin evidencia no hay MEJ.
- **Hipótesis**: por qué pasa.
- **Cambio propuesto**: qué se haría, en qué fichero(s).
- **Métrica objetivo**: de <valor base> a <valor objetivo>, medido con <comando o test>.
- **Riesgo**: qué podría romper; qué test lo detectaría.
- **Impacto / esfuerzo**: alto · medio · bajo / S · M · L
- **Quién aprueba**: implantador (prompt, router, tests) · Billy (spec, severidades, INT-xx, engine/)
- **Decisiones previas necesarias**: ninguna · <referencia a CLAUDE.md §6>

## 4. Decisiones que quedan para Billy

- …
```

## Estados de una MEJ (en `ESTADO.md`)

`PROPUESTA` → `EN IMPLANTACION (CHG-nnn)` → `CONSEGUIDA` · `PARCIAL` · `SIN EFECTO` · `DESCARTADA (por qué)`
· `PENDIENTE DE BILLY`
