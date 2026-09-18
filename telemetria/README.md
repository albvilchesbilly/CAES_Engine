# telemetria/ — histórico de ejecuciones

**Se commitea.** Es la memoria del agente `mejora-continua` entre sesiones: en Claude Code en la nube cada
sesión arranca limpia y `informes/` no se commitea, así que sin esta carpeta no hay de qué aprender.

Reglas:

- Formato JSONL: una línea por evento, claves ordenadas, UTF-8, `Decimal` como cadena (mismo criterio que
  el JSON canónico del log de eventos, `docs/03`).
- **Solo añadir.** Nunca se edita ni se borra una línea. Una medición mala se corrige con otra línea.
- **Nunca datos reales.** Solo casos sintéticos (`EXP001-*`) y, en producción, identificadores de
  actuación opacos sin nombres, NIF ni documentos. Si un día entra un expediente real anonimizado (X.4),
  su telemetría se escribe con `origen: "real-anonimizado"` y sin texto literal de evidencias.
- Un fichero por mes: `telemetria/2026-10.jsonl`. `evaluar_casos.py` y el runtime escriben; nadie más.
- `ruff` y `pytest` no lo leen. Si un test necesita telemetría, usa un fixture propio, no esta carpeta.

## Eventos

### `evaluacion_caso` — lo escribe `evaluar_casos.py` (desde F0.11)

```json
{"tipo":"evaluacion_caso","ts":"2026-10-03T17:41:02Z","commit":"a1b2c3d","fase_plan":"F0",
 "caso":"EXP001-B_falta_registro","ficha":"IND240","version_spec":"0.1.0","hash_reglas":"…",
 "veredicto_esperado":"SUBSANABLE","veredicto":"SUBSANABLE","aetotal":"305829","provisional":true,
 "tiempo_ms":{"total":2140,"ingesta":610,"clasificacion":90,"extraccion":1180,"consolidacion":40,"reglas":30,"calculo":5},
 "reglas":{"CUMPLE":21,"FALLA":1,"NO_EVALUABLE":4},
 "reglas_no_evaluables":["R-CAL-02","R-DOC-04"],
 "reglas_falladas":["R-DOC-03"],
 "variables":{"total":58,"con_evidencia":54,"solo_declaradas":3,"en_conflicto":0,"sin_dato":1},
 "documentos":{"total":9,"clasificados":9,"confianza_baja":1,"ocr":2},
 "metodos":{"tabla":31,"regex":19,"ocr":4,"llm":0}}
```

### `llamada_llm` — lo escribe `agentes/runtime/` (desde S3.6)

```json
{"tipo":"llamada_llm","ts":"…","commit":"…","fase_plan":"S3","caso":"EXP001-G_desordenado",
 "rol":"A2","prompt":"extractor_v3","modelo":"<id>","proveedor":"<nombre>",
 "tokens_in":4210,"tokens_out":380,"coste_eur":"0.0123","latencia_ms":2870,
 "intentos":2,"resultado":"valido|no_lo_se|rechazado_sin_cita|rechazado_calculo|invalido",
 "variables_pedidas":6,"variables_devueltas":5,"desacuerdo_con_reglas":1}
```

### `pasada_mejora` — lo escribe `mejora-continua` al terminar una pasada

```json
{"tipo":"pasada_mejora","ts":"…","commit":"…","modo":"ligera|completa","ventana_desde":"…",
 "lineas_analizadas":42,"alertas":0,"propuestas_nuevas":["MEJ-005","MEJ-006"],
 "propuestas_verificadas":{"MEJ-002":"CONSEGUIDA","MEJ-003":"SIN EFECTO"}}
```

## Campos nuevos

Un campo nuevo se añade aquí antes de escribirlo. Los campos existentes no cambian de nombre ni de
significado; si hace falta, se añade otro. `mejora-continua` puede editar este fichero solo para
documentar campos, no para cambiar reglas.
