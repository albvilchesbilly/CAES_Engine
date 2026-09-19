# ADR-007 — Construcción de los dashboards operativo y técnico

**Estado**: PROPUESTA
**Fecha**: 2026-09-19
**Decide**: Billy (catálogo de métricas, vistas, privacidad, interfaz) · Claude (arquitectura técnica del módulo `metricas/`)
**Ámbito**: `metricas/` (nuevo), `tests/test_metricas_*.py`, `informes/dashboards/`, log de eventos (N8), `telemetria/`, consola (S4), `docs/01`, `docs/03`, `docs/06`

## Contexto

Billy decidió el 19/09/2026 construir los dos dashboards completos:

- Dashboard **operativo** (actuaciones, estados…) y **técnico** (latencias, errores…) para `ADM-MOD` y `ADM-OPS`.
- Dashboards **funcional y operativo de su propio tenant** para el Responsable del tenant (`T-RES`), con capacidades CAP-35, CAP-36, CAP-66 y CAP-67.

Fuentes disponibles, según lo documentado:

- **Log de eventos** (N8, `docs/03`, antes `11` §3.4): eventos por proceso P0–P10, con actor y marca de tiempo. Existe desde S3.1.
- **Máquina de estados** (N6): estado de ciclo, veredicto, estado de plataforma de actuación (8 estados oficiales, fase 1) y de expediente (provisionales, `NO OFICIAL`, `TODO(API-03)`).
- **Telemetría** (`telemetria/*.jsonl`, paquete de agentes, antes `12` §3–4): ejecuciones por caso (veredicto, reglas, variables, documentos, métodos), `llamada_llm` (rol, prompt, modelo, tokens, `coste_eur`, `latencia_ms`, intentos, resultado) y `pasada_mejora`.
- **Métrica norte** (`docs/00` §1.1): horas de trabajo especializado sustituidas por minutos de revisión, y porcentaje de actuaciones que pasan la primera revisión sin subsanación.

No documentado:

- Línea base de horas manuales por actuación.
- Medición de minutos de revisión humana.
- Un tipo de telemetría para errores de ejecución.
- Comprobaciones de salud del servicio.
- Cómo se consulta en la plataforma oficial la capacidad de delegación disponible.

## Opciones consideradas

**Estructura**

1. **Opción A — Un dashboard independiente por audiencia** (global, funcional de tenant, equipo de tenant, técnico), cada uno con su cálculo. Ventaja: libertad por audiencia. Inconveniente: la misma métrica puede calcularse distinto para el tenant y para nosotros; cuatro implementaciones que mantener.
2. **Opción B — Dos dashboards (operativo y técnico) con vistas filtradas y un catálogo único de métricas.** Las vistas de tenant son filtros del operativo. Ventaja: una definición por métrica, coherencia entre lo que ve el tenant y lo que vemos nosotros, reproducible por replay. Inconveniente: un módulo nuevo y un catálogo que mantener.
3. **Opción C — Herramienta BI externa conectada directamente a los datos en bruto.** Ventaja: rapidez visual. Inconveniente: rompe el aislamiento por tenant y el enmascarado si no hay capa de acceso previa; la lógica de métricas queda fuera del repositorio y sin tests.

**Presentación**

1. **Opción D — Interfaz primero**, en la consola. Riesgo de construir paneles antes de saber qué se usa y antes de decidir la consola S4.
2. **Opción E — Informes estáticos generados primero y API de lectura con interfaz después.** Permite empezar sin decidir interfaz ni herramienta.

## Decisión

**Recomendación: opción B con presentación E.** Una métrica se define una sola vez en configuración, con el mismo criterio que las fichas, y las vistas de tenant son filtros aplicados antes del cálculo. Empezar por informes estáticos permite construir DB0 hoy, sin dependencias. La elección de interfaz o herramienta queda para Billy; si más adelante elige BI externa, se alimenta de la API de lectura, nunca de los datos en bruto.

### Dashboards y vistas

| Dashboard | Vista | Código | Quién la ve | Ámbito |
|---|---|---|---|---|
| Operativo | Global | `O-GLO` | `ADM-MOD`, `ADM-OPS` (CAP-66) | Todos los tenants, solo agregados y metadatos |
| Operativo | Funcional del tenant | `O-FUN` | `T-RES` (CAP-35) | Su tenant, con contenido |
| Operativo | Equipo del tenant | `O-EQU` | `T-RES` (CAP-36) | Su tenant, por equipo hasta decidir ADR-005 A5 |
| Técnico | Técnico | `T-TEC` | `ADM-MOD`, `ADM-OPS` (CAP-67) | Global, sin contenido documental |

### Principios

1. Solo lectura: proyecciones del log y de la telemetría.
2. La métrica es configuración: cada una se declara en `metricas/catalogo.yaml`.
3. `SIN DATO` nunca es cero: sin fuente, el panel muestra `SIN DATO` y el entregable del que depende.
4. Reproducible: mismo log y misma telemetría, mismas cifras.
5. El filtro de acceso va antes del cálculo.
6. Sin datos personales en `O-GLO` ni en `T-TEC`.
7. Rotulado honesto: kWh prevalidados "no son CAE emitidos"; estados de expediente "NO OFICIAL"; métricas aproximadas "proxy".
8. Umbrales vacíos hasta que Billy los fije: los paneles informan pero no califican.

### Arquitectura

```
Log de eventos (N8) ──┐     metricas/proyecciones/               metricas/acceso.py          Fase A: informes/dashboards/
telemetria/*.jsonl ───┼──►  hechos_actuacion · hechos_evento  ──► filtro por capacidad  ──►  Fase B: API de lectura + consola
Estado N6 (derivado) ─┘     hechos_llamada · hechos_usuario       y tenant; enmascarado
                            metricas/catalogo.yaml → calcular.py
```

```
metricas/
  catalogo.yaml            Definición de todas las métricas
  esquema_catalogo.json    JSON Schema del catálogo
  proyecciones/            normalizar.py · hechos_actuacion.py · hechos_evento.py · hechos_llamada.py · hechos_usuario.py
  calcular.py              Evalúa el catálogo sobre las proyecciones
  acceso.py                Filtro por capacidad y tenant; enmascarado
  render/                  Salida estática por vista
```

Regla de dependencias: `metricas/` lee tipos y modelos de `engine/` y ficheros de `telemetria/`; nada importa de `metricas/`. Rendimiento: se recalcula desde el log en cada generación; se materializa de forma incremental solo cuando el tiempo de generación supere un umbral que se fijará con datos reales.

Ejemplo de entrada del catálogo:

```yaml
- id: M-OP-09
  nombre: Tiempo de ciclo interno
  formula: ts(RevisionAprobada) - ts(ActuacionAbierta)
  agregacion: [p50, p90]
  unidad: horas
  fuente: log_eventos
  eventos: [ActuacionAbierta, RevisionAprobada]
  cortes: [tenant, ficha, ccaa, mes]
  vistas: [O-GLO, O-FUN]
  capacidad: [CAP-66, CAP-35]
  desde: S3.1
  rotulo: null
  umbral: POR DEFINIR (Billy)
```

### Catálogo de métricas

Vistas: G = `O-GLO` · F = `O-FUN` · E = `O-EQU` · T = `T-TEC`. "Desde" = entregable a partir del cual existe la fuente.

**Operativo — métricas norte**

| ID | Métrica | Definición / fórmula | Vistas | Desde |
|---|---|---|---|---|
| M-OP-01 | Horas de técnico sustituidas | (Horas manuales de referencia − minutos de revisión humana) × actuaciones | G, F | Hueco doble: sin línea base ni medición de minutos |
| M-OP-02 | % sin rectificación del verificador | Actuaciones con dictamen sin `PDTE_RECTIFICACION_VER` previo / actuaciones con dictamen | G, F | S3.5 simulador; real con sandbox o API |
| M-OP-03 | % sin subsanación interna (proxy) | Actuaciones con `RevisionAprobada` sin `SubsanacionSolicitada{origen=interno}` / actuaciones aprobadas | G, F | S3.1 |

**Operativo — volumen, flujo y calidad de preparación**

| ID | Métrica | Definición / fórmula | Vistas | Desde |
|---|---|---|---|---|
| M-OP-04 | Actuaciones por estado de ciclo | Recuento por estado N6 (embudo) | G, F | S3.1 |
| M-OP-05 | Actuaciones por veredicto | Recuento por último veredicto | G, F | F0 |
| M-OP-06 | Actuaciones por estado de plataforma (fase 1) | Recuento por los 8 estados oficiales | G, F | S3.5 |
| M-OP-07 | Expedientes por estado (fases 2–4) | Recuento por estado provisional, rótulo `NO OFICIAL` | G, F | `TODO(API-03)` |
| M-OP-08 | Ahorro en actuaciones prevalidadas | Σ kWh/año de `CalculoRealizado` en `PREVALIDADO`; rótulo "no son CAE emitidos" | G, F | F0 |
| M-OP-09 | Tiempo de ciclo interno | `RevisionAprobada` − `ActuacionAbierta` (p50, p90) | G, F | S3.1 |
| M-OP-10 | Espera de firma | `FirmaRegistrada` − `EntregadoADelegado`/`EnviadoAPI` (p50, p90) | G, F | S3.4 |
| M-OP-11 | Cola de revisión humana | Número y antigüedad en `EN_REVISION_HUMANA` | G, F | S3.1 |
| M-OP-12 | Subsanaciones por origen | `SubsanacionSolicitada` por interno, verificador, GA, CN | G, F | S3.5 |
| M-OP-13 | Contagio | `PENDIENTE_SUBSANACION` con `afectada_directamente = false` | G, F | S3.5 |
| M-OP-14 | Tareas pendientes de la plataforma | Número y antigüedad de `TareaPendienteRecibida` abiertas | G, F | S3.5 simulador |
| M-OP-15 | Capacidad frente a demanda | Capacidad de delegación disponible frente a kWh en `LISTA_PARA_ENVIO` | G, F | Cuando se documente la consulta |
| M-OP-16 | Descartes | `ActuacionDescartada` por regla de `NO_ELEGIBLE` | G, F | S3.1 |
| M-OP-17 | Reglas más falladas | Top de reglas en `FALLA` en el último veredicto | G, F | F0 |
| M-OP-18 | Conflictos documentales | `ConflictoDetectado` por regla `R-CON` | G, F | F0 |
| M-OP-19 | Discrepancias con la plataforma | `DiscrepanciaCalculoPlataforma` y su resolución | G, F | Sandbox |
| M-OP-20 | Eventos de administración | Accesos de soporte, autoasignaciones, altas y bajas | G | S3.1 |

**Operativo — vista de equipo**

| ID | Métrica | Definición / fórmula | Desde |
|---|---|---|---|
| M-EQ-01 | Carga | Actuaciones asignadas y en curso por usuario o por perfil | S3.1 |
| M-EQ-02 | Actividad | Actuaciones abiertas, revisadas y aprobadas por `actor.id` y `actor.rol` | S3.1 |
| M-EQ-03 | Espera en revisión | Entrada en cola de revisión → `RevisionAprobada` | S3.1 |
| M-EQ-04 | Tareas de plataforma sin responsable | `TareaPendienteRecibida` sin usuario asignado | S3.5 |
| M-EQ-05 | Actuaciones bloqueadas | `BLOQUEADO` o `PENDIENTE_SUBSANACION` con motivo y responsable | S3.1 |
| M-EQ-06 | Preparación y aprobación por la misma persona | `actor.id` igual en `ActuacionAbierta` y `RevisionAprobada` | S3.1 |
| M-EQ-07 | Reasignaciones | `ActuacionReasignada` y motivo | S3.1 |

**Técnico**

| ID | Métrica | Definición / fórmula | Desde |
|---|---|---|---|
| M-TE-01 | Latencia extremo a extremo | Primer `DocumentoRegistrado` → último `VeredictoEmitido` (p50, p95) | S3.1 |
| M-TE-02 | Latencia por fase | Duración de P1 a P8 (p50, p95) | S3.1 |
| M-TE-03 | Latencia LLM | `latencia_ms` por rol, prompt y modelo (p50, p95) | S3.6 |
| M-TE-04 | Errores de ejecución | Excepciones por módulo | Nuevo tipo de telemetría `error` (no existe) |
| M-TE-05 | Salidas de agente no válidas | Recuento por `invalido`, `rechazado_sin_cita`, `rechazado_calculo`, `no_lo_se` | S3.6 |
| M-TE-06 | Reintentos | Media y máximo de `intentos` por rol | S3.6 |
| M-TE-07 | Presupuesto agotado | Actuaciones a `EN_REVISION_HUMANA` por presupuesto | S3.1 |
| M-TE-08 | Integridad | Rechazos por hash; `CorreccionRechazadaPostFirma` | S3.3 / S3.4 |
| M-TE-09 | Integración | Rechazos del simulador y errores del conector por tipo (esquema, firma, certificado, permisos) | S3.4; real en S3.7 |
| M-TE-10 | Disponibilidad del servicio | Comprobaciones de salud correctas | No definido |
| M-TE-11 | Desacuerdo entre extractores | `DesacuerdoExtractores` / variables extraídas por ambos | S3.6 |
| M-TE-12 | Escalados por confianza | Datos enviados a revisión por confianza baja | S3.6 |
| M-TE-13 | Clasificación documental | Documentos con confianza baja o sin clasificar | F0 |
| M-TE-14 | Método de extracción | Reparto tabla / regex / OCR / LLM | F0 |
| M-TE-15 | Reglas `NO_EVALUABLE` | Media por actuación | F0 |
| M-TE-16 | Regresión | Veredicto obtenido frente a esperado en el banco de pruebas | F0 |
| M-TE-17 | Discrepancias con la plataforma | `DiscrepanciaCalculoPlataforma` por ficha y regla | Sandbox |
| M-TE-18 | Tokens y coste | `tokens_in`, `tokens_out`, `coste_eur` por actuación, rol y prompt | S3.6 |
| M-TE-19 | Mejora continua | Alertas abiertas y estado de `MEJ-nnn` | F0.11b |

### Composición de las vistas

- **`O-GLO`**: norte (M-OP-01 a 03) · embudo y estados (04 a 07) · flujo (09, 10, 11, 14) · calidad de preparación (12, 13, 16 a 19) · negocio (08, 15) · gobierno (20).
- **`O-FUN`**: norte de su tenant (M-OP-01 a 03) · estado de su cartera (04 a 08) · qué le frena (11 a 14, 17 a 19) · capacidad (15). Desde aquí se abre cualquier actuación (CAP-03).
- **`O-EQU`**: carga y actividad (M-EQ-01, 02) · cuellos de botella (03 a 05) · control (06, 07). Con aviso visible a los usuarios sobre el registro de su actividad (ADR-005).
- **`T-TEC`**: salud (M-TE-10, 04, 09) · rendimiento (01 a 03) · fiabilidad de la IA (05, 06, 11, 12) · calidad del motor (13 a 17) · integridad (07, 08) · coste y mejora (18, 19).

### Plan de construcción

| # | Entregable | Hecho cuando… | Depende de |
|---|---|---|---|
| DB0 | Catálogo YAML completo, JSON Schema, validador y vista `T-TEC` estática sobre la telemetría existente | El informe técnico se genera sobre los casos del banco; toda métrica sin fuente muestra `SIN DATO` con su "desde"; el validador rechaza una métrica sin fuente, vista o capacidad | Nada |
| DB1 | Proyecciones sobre el log; vistas `O-GLO`, `O-FUN` y `O-EQU` estáticas; filtro por capacidad y tenant | M-OP-03 a 05, 08, 09, 11, 16 a 18, 20; M-EQ-01 a 03, 05 a 07; M-TE-01, 02, 07 calculadas; tests de aislamiento en verde | S3.1 y ADR-005 |
| DB2 | Métricas de salida y seguimiento contra el simulador | M-OP-06, 10, 12 a 14; M-EQ-04; M-TE-08, 09 | S3.4, S3.5 |
| DB3 | Métricas del runtime de agentes | M-TE-03, 05, 06, 11, 12, 18 | S3.6 (proveedor LLM) |
| DB4 | Métricas con la plataforma real | M-OP-02 real; M-OP-19 y M-TE-17; M-OP-07 al cerrar API-03 | S3.7 (diccionario de API y delegado partner o perfil Modificación) |
| DB5 | API de lectura y vistas en la interfaz elegida | Las cuatro vistas accesibles según capacidad, con las mismas cifras que el informe estático | Decisión de Billy sobre la interfaz |

## Consecuencias

- **Código nuevo**: `metricas/` con la estructura anterior; `tests/test_metricas_*.py`; salida en `informes/dashboards/` (no se commitea, como el resto de `informes/`).
- **Documentación**: `docs/01` (carpeta `metricas/` y su regla de dependencias); `docs/03` (proyecciones como consumidor de N8); `docs/06` (líneas DB0–DB5); `CLAUDE.md` §6 (decisiones pendientes).
- **Telemetría**: nuevo tipo `error` propuesto para M-TE-04; sin aprobar no se añade.
- **Marcas de estado**: todas las métricas nacen con su "desde"; pasan de `SIN DATO` a calculadas al cerrarse el entregable correspondiente.
- **Riesgos**:
  - Cifras sintéticas tomadas por reales. Mitigación: marca de origen (sintético o real) en cada panel.
  - Vista de equipo usada como control individual de productividad. Mitigación: agregación por equipo y aviso a usuarios.
  - Métrica norte principal sin medir ante el primer cliente.
  - Paneles con muchos `SIN DATO` durante semanas en demostraciones.
- **Pendiente (Billy)**:
  - B1 · Presentación: informes estáticos, consola propia (S4) o herramienta BI externa alimentada por la API de lectura.
  - B2 · Cuándo se construye DB5: Sprint 4 con la consola de revisión o con el primer cliente.
  - B3 · Vista de equipo por persona o por equipo (mismo punto que ADR-005 A5).
  - B4 · Línea base de horas manuales para M-OP-01: medida con el primer delegado partner o declarada por el tenant y rotulada como declarada.
  - B5 · Medición de minutos de revisión: tiempo de sesión en consola o duración declarada al aprobar.
  - B6 · Aprobar el tipo de telemetría `error`.
  - B7 · Comprobaciones de salud del servicio y si el tenant ve un indicador de estado.
  - B8 · Umbrales de alerta de cada métrica.
  - B9 · Exportación de datos para el tenant.

## Verificación

Comandos y tests a crear con DB0 y DB1:

- `python -m metricas.validar`: valida `metricas/catalogo.yaml` contra el JSON Schema; falla si una métrica no tiene fuente, vista, capacidad o "desde", o si una vista referencia una métrica inexistente.
- `python -m metricas.generar --vista T-TEC`: genera el informe técnico sobre los casos del banco en `informes/dashboards/`.
- `tests/test_metricas_reproducibilidad.py`: dos generaciones sobre el mismo log producen cifras idénticas.
- `tests/test_metricas_sin_dato.py`: sin fuente devuelve `SIN DATO`; con fuente y sin casos, 0.
- `tests/test_metricas_aislamiento.py`: añadir eventos de otro tenant no cambia `O-FUN` ni `O-EQU` de un tenant (metamórfica).
- `tests/test_metricas_privacidad.py`: `O-GLO` y `T-TEC` no contienen campos de la lista prohibida (NIF, razón social, dirección, referencia catastral, texto literal).
- `tests/test_metricas_rotulos.py`: M-OP-08, M-OP-07 y M-OP-03 llevan su rótulo.
