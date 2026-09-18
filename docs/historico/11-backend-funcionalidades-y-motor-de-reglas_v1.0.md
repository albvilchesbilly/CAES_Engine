> **SUPERADO.** Documento histórico (v1.0, 18/09/2026). En la consolidación del 18/09/2026 se fundió con `07` en `docs/03-arquitectura-backend.md` y `docs/04-motor-de-reglas-y-specs.md`; su §1 (análisis de alineación de `06`) y su §9 (anexo de edición) se aplicaron sobre `docs/07-entorno-y-competencia.md` v1.1; su §7 pasó a `docs/HUECOS.md`; su §2 a `docs/06-plan-de-construccion.md`. Se conserva por la historia de decisiones. No construir sobre él.

# CAE Engine — Backend, funcionalidades y motor de reglas (alineado con la plataforma oficial)

**Versión 1.0 · 18/09/2026 · Proyecto CAE (Billy)**

Este documento nace del contraste entre `00-instrucciones-de-entrada.md` **v1.2** (que incorpora la confrontación con la plataforma oficial, `10`) y `06-entorno-tecnologico-y-competitivo.md` **v1.0** (17/09/2026, anterior a esa confrontación). Hace tres cosas, en este orden: (1) dice en qué `06` ya no describe la plataforma que estamos construyendo, (2) fija un plan para cerrarlo y (3) **ejecuta la parte de ese plan que es documental**: la descripción consolidada del backend, de las funcionalidades que incorpora y del motor de reglas, tal como quedan tras `10`.

**Relación con `07`.** `07-backend-y-motor-de-reglas.md` v1.0 se escribió sobre `00` v1.1, antes de la confrontación. Este documento lo **sustituye en todo lo que discrepe**; lo que `07` dice y aquí no se contradice sigue vigente (parser de lista blanca, `Decimal`, contrato de agentes, evaluación, seguridad). Recomendación: marcar `07` como *superado por 11* en su cabecera, no borrarlo, porque conserva la historia de decisiones.

**Precedencia.** BOE → plataforma oficial (lo publicado) → catálogo MITECO → `spec/*.yaml` → `00` → `10` → **este documento** → `07` → código. Si este documento contradice una regla de oro del `00`, este documento está mal.

**Marcas de estado** (mismas que `07`, más una):

| Marca | Significado |
|---|---|
| `EXISTE` | Implementado en el Engine 0.1 (Sprints 1 y 2) |
| `PARCIAL` | Existe una parte; se indica cuál |
| `NUEVO` | Diseño aprobado, sin implementar |
| `A CONFIRMAR` | Afirmación sobre el código no contrastada con el repositorio |
| `NO DOCUMENTADO` | La plataforma oficial no lo ha publicado; se modela como hueco `TODO(API-xx)`, nunca como suposición |

---

## 0. Resumen ejecutivo

1. **`06` no está completamente alineado.** Sigue siendo correcto en lo que describe (la plataforma calcula lo tratable, el diferencial está aguas arriba, el output debe ser payload, ningún delegado publica API), pero se escribió con una **unidad de trabajo equivocada** ("expediente" donde la plataforma dice "actuación"), **sin la frontera de firma** (la firma es humana con certificado de representante), **sin la cabecera común**, **sin las fases 2–4** (expediente → GA → CN → registro) y con **tres decisiones que ya están tomadas** presentadas como abiertas. Ninguna de sus afirmaciones es falsa; el problema es lo que falta y lo que ha quedado obsoleto.
2. **Se han identificado 14 desalineaciones o debilidades** (§1.2) y 6 puntos de mejora (§1.3). Cinco son de impacto alto porque afectan al diseño del backend: unidad de trabajo, firma, cabecera, estados de fases 2–4 y origen triple de la subsanación.
3. **El plan (§2) tiene cuatro horizontes**: inmediato (documental y de spec, sin código), Sprint 3 (modelo canónico, estados, cabecera, integridad, salida dividida en transporte/firma, P9), Sprint 4 (Expediente Builder, A5/A7, segunda ficha) y roadmap (singulares/CVP, CAE Supply).
4. **Lo ejecutado en este documento**: la arquitectura de backend revisada (§3), el catálogo de funcionalidades con su estado y su producto (§4) y el motor de reglas ampliado a tres niveles —actuación, grupo, expediente— con nuevas familias de reglas transversales, de agrupación y de control cruzado (§5). Cada regla nueva está marcada como propuesta hasta que Billy la apruebe y se refleje en el YAML.
5. **Lo que no se ejecuta aquí, por diseño**: no se modifica `06` (se propone su v1.1 en el anexo §9, decisión de Billy), no se toca código ni el YAML `IND240_v1.1` (los cambios de spec pasan por revisión humana, regla de oro 9) y no se rellena ningún hueco de la API con suposiciones (regla de oro 10).

---

## 1. Análisis de alineación de `06` con `00` v1.2

### 1.1 Lo que sigue vigente en `06` (no tocar)

- §1.1 y §1.2: descripción de la plataforma y de la API (JSON firmado, manifiesto con hash, notificaciones y tareas, sandbox). `10` §5 lo confirma punto por punto.
- §1.4.1 y §1.4.2: el cálculo pasa a control cruzado; el diferencial está aguas arriba. Es la tesis que `00` §1.1 adopta como "matiz importante".
- §1.4.3: el output evoluciona a payload (cabecera + detalle + manifiesto). Correcto; le falta el detalle de la cabecera (§1.2, D3).
- §2: mapa de delegados y el dato "ningún sujeto delegado publica API". Sigue siendo el hallazgo más accionable.
- §3.1: CertificAhorro como competidor directo. Vigente; matiz en D9.
- §3.4: fabricantes de variadores (Schneider Altivar) como fuente de evidencia y canal. Coherente con `07` §10 (documentos reales públicos).
- §4 y §5: referencias de mercado y huecos (industrial sin plataforma, ~55 delegados sin producto, nadie en prevalidación por cruce de evidencias).

### 1.2 Desalineaciones y debilidades

Criterio de impacto: **Alto** si obliga a cambiar el diseño del backend o del producto; **Medio** si cambia una regla, un dato o una prioridad; **Bajo** si es documental.

| ID | Sección de `06` | Lo que dice `06` v1.0 | Lo que fija `00` v1.2 / `10` | Impacto | Acción |
|---|---|---|---|---|---|
| **D1** | §1.1, §1.4.3, todo el texto | Habla de "expedientes" como unidad que preparamos y enviamos | La unidad de trabajo de la plataforma es la **actuación**; el expediente oficial es una agregación posterior de actuaciones `VERIFICADA_FAVORABLE` con misma CCAA + año + sector + verificador; existe además el **grupo de actuaciones** con dictamen único | **Alto** | Renombrar modelo canónico a `Actuacion`; añadir `GrupoActuaciones` y `Expediente` (§3.2) |
| **D2** | §1.1 "Estados de actuación propios" | Lista los 8 estados como si fueran el ciclo completo | Son solo la **fase 1**. Las fases 2–4 (presentación, validación técnica GA, revisión formal CN, resolución, registro, desistimiento) tienen estados **no documentados** | **Alto** | Máquina de estados con estados de expediente provisionales marcados `NO OFICIAL` + `DESISTIDO` (§3.3) |
| **D3** | §1.1 "formulario de cabecera + formulario específico" | Menciona la cabecera pero no dice qué contiene | La cabecera común pide precio del contrato de cesión, inversión, costes operativos anuales, tipología de empresa, localización, propietario inicial, partícipe en subvención y en subasta, código identificativo propio. **Hoy no capturamos la mayoría** | **Alto** | Spec transversal `spec/cabecera_v1.yaml` + reglas `R-CAB-*` (§3.6, §5.6) |
| **D4** | §1.2 "Certificados" | Enumera los certificados sin decir quién firma qué | Tres certificados con roles distintos: el de **usuario** (Consulta / Modificación / Firma) firma peticiones API; el de **representante** (FNMT) firma actos administrativos y es **siempre humano**. La automatización termina en `COMPLETA` | **Alto** | Dividir `salida/firmante/` en `salida/transporte/` y `salida/firma/` (§3.8) |
| **D5** | §1.1 "validación automática de la información tratable y de la documentación" | No extrae la consecuencia sobre la subsanación | La subsanación llega de **tres actores** (verificador por actuación; GA y CN por actuación pero **bloqueando el expediente entero**) y en tres momentos; el sujeto puede desistir; tras la firma solo se modifica vía requerimiento oficial | **Alto** | P7 con `origen ∈ {interno, verificador, GA, CN}`; A9 lee requerimientos firmados con informe PDF (§3.9) |
| **D6** | §1.4.4 "sin un sujeto delegado partner no hay pruebas" | Presenta el delegado partner como única vía de acceso | `00` §5.6 añade dos vías más: la alegación a la DT 2ª (sandbox para intermediarios técnicos) y la **hipótesis del perfil Modificación** (usuario sin firma dado de alta por el delegado; no documentado si admite terceros). Pendiente de respuesta del gestor de la plataforma | Medio | Añadir a `06` §1.4.4 las tres vías y su estado; el backend queda preparado para ambas (§3.8) |
| **D7** | §1.3 calendario | Da la entrega de modelos de intercambio como "Sep 2026" sin estado | A 18/09/2026 **no se han recibido**; MITECO indica "en fase de desarrollo" y el único documento técnico es la presentación del 30/06 | Medio | Marcar el hito como *previsto, no recibido*; enlazar con `HUECOS.md` |
| **D8** | §6 "Moeve ya tiene jugada en CAE" | Plantea Moeve como aliado/cliente/conflicto sin el dato de acceso directo | `00` §8: los obligados con obligación ≥ 50 MWh **operan directamente** en la plataforma. Billy fijó el 18/09 la posición: CAE Engine es **independiente**, no se piensa solo para Moeve | Medio | Actualizar §6 con el dato y la decisión; el tenant "sujeto obligado directo" entra como perfil de cliente en §3.10 |
| **D9** | §3.1 "Intelligence … es exactamente nuestro Sprint 3" | Sitúa el extractor LLM como el Sprint 3 | El orden del Sprint 3 se revisó tras `10`: modelo canónico → salida y simulador → P9/A9 → **extractor LLM (paso 4)** → conector API | Medio | Reformular: "es nuestro paso 4 del Sprint 3"; el diferencial frente a CertificAhorro no es extraer, sino **cruzar** (R-CON/R-EVD/R-AMB) |
| **D10** | §7 decisiones abiertas 1 y 2 | Pregunta si priorizar API sobre LLM y si buscar delegado partner | Ambas están **decididas**: Sprint 3 hacia la integración (17/09); búsqueda de delegado en curso con criterio añadido de **capacidad de delegación disponible** (`10` D14) | Medio | Cerrar 1 y 2 en `06` §7; dejar la 3 (ficha residencial vs. industrial) como única abierta |
| **D11** | §1.4.2 | Dice que la plataforma "no cruza evidencias ni dice qué falta" | `10` §3 precisa: la plataforma **sí comprueba presencia** de documentos por tipo. `00` §1.1 remite a `06` §1.4 para esto, pero `06` no lo dice: **referencia rota** | Medio | Añadir a §1.4 el párrafo sobre presencia vs. contenido; etiquetar `R-DOC-01` como *no diferencial* (§5.5) |
| **D12** | §1.1 | No menciona la **capacidad máxima de delegación** ni su liberación al liquidar | `00` §8 y `10` D14: un partner sin capacidad limita nuestro volumen | Medio | Criterio de selección de partner; atributo `capacidad_disponible` en el tenant (§3.10) |
| **D13** | §5 huecos y §7 | No contempla actuaciones **singulares** ni Consulta Voluntaria Previa | `00` §9: módulo de singulares/CVP como decisión abierta de roadmap (fase II de la plataforma, ene–mar 2027); el sector industrial las genera con frecuencia | Bajo | Añadir hueco 4 en `06` §5 y entrada de roadmap (§4, F-19) |
| **D14** | Cabecera y §8 | Referencia a `claude/00-instrucciones-de-entrada.md` (ruta incorrecta) y a `00` v1.0 sin las alegaciones ni el perfil de colaborador | `00` está en la raíz del proyecto; v1.2 incluye §5.6 (alegaciones, art. 20.3) que da contexto regulatorio a "ningún delegado publica API" | Bajo | Corregir ruta; enlazar §2 y §4 (reclamación de CNI) con `00` §5.6 |

### 1.3 Puntos de mejora (ampliaciones, no errores)

| ID | Mejora | Por qué |
|---|---|---|
| M1 | Añadir a `06` §2.1 los competidores que `00` §8 cita y `06` no analiza: CAE Claro, caes.es, Smart Light; y los que Billy pidió revisar el 18/09: CalculaCAE.ai y CAE Digital | El benchmark queda incompleto justo en el segmento "software CAE" que compite con CAE Check |
| M2 | Tabla de **solapamiento funcional plataforma oficial ↔ Engine** (qué hace ella, qué hacemos nosotros, qué es diferencial) | Es la pregunta que hará cualquier delegado o inversor; hoy está repartida entre `06` §1.4, `10` §3 y `10` §8 |
| M3 | Recoger que la plataforma expone **tareas pendientes** consultables por API y que eso es, para el delegado, una cola de trabajo que podemos priorizar | Funcionalidad de producto (F-14) que `06` no aprovecha |
| M4 | Distinguir en `06` §3.3 (Feníe, Iberdrola) entre sujetos obligados con plataforma **propia** y sujetos obligados como **usuarios directos** de la oficial | Cambia el mapa de clientes tras `10` D13 |
| M5 | Añadir en `06` §6 el **riesgo de contagio** (dictamen único por grupo; requerimiento de GA/CN bloquea el expediente completo) | Es un riesgo de producto, no solo de backend; justifica el Expediente Builder |
| M6 | Actualizar el pie "mantener vivo" para que el disparador no sea solo el diccionario de API sino también la respuesta sobre el perfil de Modificación y la tramitación del RD | Coherencia con `00` §5.6 y con la vigilancia normativa |

---

## 2. Plan de implementación

Criterio de ordenación: primero lo que no depende de nadie externo y desbloquea al resto; lo que depende del diccionario de API o del delegado partner se engancha cuando llegue. Cada línea tiene un "hecho cuando" verificable.

### 2.1 Horizonte 0 — Inmediato, sin código (esta semana)

| # | Entregable | Cierra | Hecho cuando… | Quién |
|---|---|---|---|---|
| 0.1 | **Este documento** (backend + funcionalidades + motor de reglas) | D1–D5, D9, D11, M2, M3, M5 | Publicado en el proyecto; `07` marcado como superado | Claude ✅ |
| 0.2 | `06` → v1.1 con las ediciones del anexo §9 | D6, D7, D8, D10, D12, D13, D14, M1, M4, M6 | Billy aprueba el anexo; se aplica en la misma sesión | Billy decide, Claude ejecuta |
| 0.3 | `spec/IND240_v1.1.yaml` → `v1.2`: reescribir `R-TMP-03`, abrir `INT-08`, etiquetar `R-DOC-01` como no diferencial | `10` D6, D10 | Diff revisado por Billy; 61 tests en verde; `version_spec` incrementada | Billy revisa, Claude prepara el diff |
| 0.4 | Correo a `consultas-plataforma@registrocae.es` (modelos de intercambio, diccionario, perfil Modificación para terceros) | `10` D11 | Enviado; respuesta registrada en bitácora | Billy (decidido 18/09) |
| 0.5 | Cerrar delegado partner con certificado **y capacidad disponible** antes del 1/10 | `10` D11, D14 | Acuerdo de modo sombra firmado | Billy |

### 2.2 Horizonte 1 — Sprint 3 (orden revisado tras `10`)

| # | Entregable | Módulos | Hecho cuando… | Depende de |
|---|---|---|---|---|
| 1.1 | Modelo canónico `Actuacion` + `GrupoActuaciones` + `Expediente` + `Verificador`; log de eventos; máquina de estados con fases 2–4 provisionales y `DESISTIDO` | N6, N7, N8 | Los 7 casos producen `Actuacion` válida; replay del log reproduce veredicto y ahorro bit a bit; 61 tests en verde | Nada |
| 1.2 | Spec transversal `spec/cabecera_v1.yaml` + reglas `R-CAB-*` + extracción de las variables de cabecera que tienen fuente documental | N1, N2, S1 | El caso A rellena todos los campos de cabecera con fuente documental, y deja los sin fuente como `declarado` o `NO DOCUMENTADO` | 1.1 |
| 1.3 | Integridad total: SHA-256 de todo fichero en ingesta; manifiesto interno | N5 | Manifiesto del caso A verificable; alterar un byte de cualquier adjunto lo detecta | Nada |
| 1.4 | Puerto de salida + adaptador handoff + simulador; `salida/transporte/` y `salida/firma/` separados; `HUECOS.md` | S5 | Simulador acepta el paquete del caso A y rechaza uno con hash alterado; la "firma" es un paso humano simulado que cambia `COMPLETA` → `ENVIADA_A_VERIFICACION` | 1.1, 1.3 |
| 1.5 | P9 contra el simulador + A9 sobre requerimientos sintéticos de los **tres orígenes** + P7 con `origen` | S2 (redactor), N6 | Un `PDTE_RECTIFICACION_VER` simulado reabre subsanación con la regla correcta; un requerimiento de GA simulado bloquea el expediente completo y no solo la actuación | 1.4 |
| 1.6 | Agent Runtime + lector LLM (A2) con doble extracción, detrás de la interfaz `Extractor` existente | S2 | Evaluado en conjunto reservado de la fábrica de casos; modo degradado comprobado apagando el LLM | Proveedor LLM (decisión de Billy, `07` §11) |
| 1.7 | Conector API oficial + modo sombra + batería de casos para inferir criterios oficiales (INT-01..05) | S5, S6 | Un envío real en sandbox; primera `DiscrepanciaCalculoPlataforma` registrada o ausencia de discrepancia en los 7 casos | Diccionario de API **y** delegado partner (o perfil Modificación) |

### 2.3 Horizonte 2 — Sprint 4

| # | Entregable | Hecho cuando… |
|---|---|---|
| 2.1 | **Expediente Builder**: reglas `R-GRP-*` y `R-EXP-*`; sugerencia de lotes válidos; aviso de actuaciones huérfanas y de contagio | Sobre 20 actuaciones sintéticas con distintos CCAA/año/verificador, propone los lotes correctos y ningún lote mezcla `SUBSANABLE` con `PREVALIDADO` |
| 2.2 | A5 (subsanaciones) y A7 (informes) sobre el campo `subsanacion` de cada regla | Petición al cliente generada para el caso B sin inventar documentos que la spec no pide |
| 2.3 | Segunda ficha (TRA050) con **cero cambios en `engine/`** | Checklist de §5.12 completo; si `engine/` cambia, se registra como defecto del marco |
| 2.4 | Consola de revisión centrada en lo **previo a la firma** (S4) | Cola de escalados, conflictos y tareas pendientes consumidas de la plataforma (simulador) |

### 2.4 Horizonte 3 — Roadmap (decisiones de Billy)

Módulo de actuaciones singulares y CVP (fase II de la plataforma, ene–mar 2027); estados de CAE (`vigente`, `expirado`, `liquidado`) solo si entra CAE Supply; coeficientes de corrección (art. 18 bis) como tabla con vigencia cuando existan.

### 2.5 Riesgos del plan

| Riesgo | Efecto | Mitigación |
|---|---|---|
| El diccionario de API no llega en septiembre | 1.7 se retrasa; se pierde la ventana oct–nov | 1.1–1.6 no dependen de él; el simulador implementa solo lo conocido; `HUECOS.md` enumerado |
| No hay delegado partner antes de octubre | Sin sandbox ni modo sombra | Vía perfil Modificación (si el gestor responde afirmativamente) y alegación DT 2ª; mientras, handoff y simulador |
| Los estados provisionales de fases 2–4 no coinciden con los oficiales | Retrabajo en N6 | Se modelan como tabla de mapeo, no como código; cambiar nombres es cambiar YAML |
| Cabecera: campos sin fuente documental (costes operativos, tipología, subasta) | Payload incompleto o con datos declarados | Se marcan `declarado` y quedan recogidos por `R-CAB-*` como subsanables; semántica `NO DOCUMENTADO` no se inventa |
| Renombrar "expediente" → "actuación" rompe tests y nombres de fichero | Regresión | Alias `Expediente = Actuacion` durante un sprint; los 61 tests deben pasar antes y después |

---

## 3. Backend

### 3.1 Principios (delta sobre `07` §1)

Los siete principios de `07` §1 se mantienen. Se añaden tres:

| # | Principio | Consecuencia práctica |
|---|---|---|
| 8 | **La unidad de trabajo es la actuación**; grupo y expediente son agregaciones con reglas propias | El motor evalúa a tres niveles; el payload se construye por actuación; el expediente se compone, no se calcula |
| 9 | **La automatización termina en `COMPLETA`**; la firma es un acto humano con certificado de representante | Ningún componente nuestro firma actos administrativos; transporte y firma son módulos distintos |
| 10 | **Lo no documentado por la plataforma es un hueco enumerado**, nunca una suposición en el código | `HUECOS.md` es un artefacto de primera clase; cada `TODO(API-xx)` tiene dueño y fecha de revisión |

### 3.2 Modelo canónico (N7) — `NUEVO`, revisado tras `10`

```
Tenant (sujeto delegado u obligado directo)
├─ id, tipo {delegado, obligado_directo}, capacidad_delegacion_disponible?  (NO DOCUMENTADO cómo se consulta)
└─ Actuacion[]                                   ← lo que hoy el código llama "expediente"
    ├─ id, codigo_identificativo_propio           ← clave de reconciliación con la plataforma
    ├─ modelo_version, creado_en
    ├─ ficha: { codigo, version_ficha, version_spec, hash_spec }
    ├─ cabecera: { … }                            ← spec transversal cabecera_v1.yaml (§3.6)
    ├─ partes: propietario_inicial, solicitante (tenant), instalador, verificador?
    ├─ atributos_agrupacion: { ccaa, anio_finalizacion, sector, verificador_id }   ← obligatorios para componer expediente
    ├─ documentos[]: { doc_id, tipo, confianza_tipo, sha256, bytes, paginas, origen, metodo_lectura }
    ├─ unidades[]  (IND240: una por motor; clave de unión nº de serie) → variables{} → DatoConsolidado
    ├─ variables_actuacion{} → DatoConsolidado
    ├─ evaluacion: { reglas[], veredicto, hash_reglas, evaluado_en }
    ├─ calculo: { por_unidad[], total, traza[], provisional, control_cruzado? }
    ├─ observaciones[], interpretaciones_aplicadas[]
    ├─ subsanaciones[]: { origen ∈ {interno, verificador, GA, CN}, requerimiento_ref?, reglas[], documentos[], estado }
    └─ ciclo: { estado_ciclo, estado_plataforma?, grupo_id?, expediente_id?, historial → log }

GrupoActuaciones                                 ← verificación conjunta, dictamen único
├─ id, tenant, verificador_id, actuaciones[], estado_plataforma (comparte los 8 de fase 1)
└─ evaluacion_grupo: { reglas R-GRP[], veredicto_agregado }

Expediente (oficial)                             ← agregación de VERIFICADA_FAVORABLE
├─ id, tenant, ccaa, anio, sector, verificador_id, actuaciones[] | grupo_id
├─ estado_expediente (provisional, NO OFICIAL; §3.3)
├─ evaluacion_expediente: { reglas R-EXP[], avisos_contagio[] }
└─ requerimientos[]: { origen ∈ {GA, CN}, ronda, informe_pdf_sha256, actuaciones_afectadas[], estado }

Verificador                                      ← nueva entidad (10 §1)
├─ id, razon_social, acreditacion_enac_ref, ccaa_operativas?  (NO DOCUMENTADO si la plataforma lo expone)
```

`DatoConsolidado` con sus tres capas (documento → interpretación → cálculo) queda como en `07` §4. Se añade a la capa de interpretación el campo `tratable_por_plataforma: bool` (si el dato es de los que la plataforma valida/calcula; sirve para el control cruzado y para saber qué es diferencial).

**Renombrado.** `Expediente` (código actual) → `Actuacion`. Durante el Sprint 3 se mantiene un alias para no romper los 61 tests; al cerrar el sprint el alias desaparece.

### 3.3 Máquina de estados (N6) — `NUEVO`, ampliada

Se mantienen los **tres conceptos** de `07` §5.2 (veredicto, estado de ciclo, estado de plataforma) y se añade un cuarto nivel para el expediente oficial.

| Nivel | Valores | Quién lo fija | Estado documental |
|---|---|---|---|
| Veredicto (actuación) | `NO_ELEGIBLE`, `BLOQUEADO`, `SUBSANABLE`, `PREVALIDADO` | Rules Engine | `EXISTE` |
| Estado de ciclo (nuestro trabajo) | §3.3.1 | Máquina de estados | `NUEVO` |
| Estado de plataforma — actuación (fase 1) | `BORRADOR`, `COMPLETA`, `ENVIADA_A_VERIFICACION`, `PDTE_RECTIFICACION_VER`, `VERIFICACION_EN_PROCESO`, `VERIFICADA_FAVORABLE`, `VERIFICADA_DESFAVORABLE`, `NO_PUEDE_EMITIR_DICTAMEN` | Plataforma; nosotros reflejamos | Confirmado (presentación 30/06/2026) |
| Estado de plataforma — expediente (fases 2–4) | Provisionales: `BORRADOR_SOLICITUD`, `PRESENTADO`, `EN_VALIDACION_TECNICA`, `REQUERIDO_GA`, `VALIDADO_GA`, `EN_REVISION_FORMAL`, `REQUERIDO_CN`, `RESUELTO_FAVORABLE`, `RESUELTO_DESFAVORABLE`, `INSCRITO`, `DESISTIDO` | Plataforma; **nombres nuestros, no oficiales** | `NO DOCUMENTADO` → `TODO(API-03)` |

#### 3.3.1 Estado de ciclo

```
ABIERTA → EN_PROCESO → EVALUADA ─┬─► PENDIENTE_SUBSANACION(origen=interno) ──(nuevos docs)──► EN_PROCESO
                                 ├─► EN_REVISION_HUMANA ─────────────────────────────────────► EVALUADA
                                 ├─► DESCARTADA                    (NO_ELEGIBLE confirmado por humano)
                                 └─► LISTA_PARA_ENVIO ► ENTREGADA(handoff | API) ► EN_PLATAFORMA ► CERRADA
                                                                                   │
        EN_PLATAFORMA + PDTE_RECTIFICACION_VER ──► PENDIENTE_SUBSANACION(origen=verificador)
        EN_PLATAFORMA + REQUERIDO_GA | REQUERIDO_CN ──► PENDIENTE_SUBSANACION(origen=GA|CN), bloquea Expediente completo
        EN_PLATAFORMA + DESISTIDO ──► CERRADA(resultado=desistida)
```

Reglas de transición:

- Solo una actuación `PREVALIDADO` **y revisada por un humano** pasa a `LISTA_PARA_ENVIO`.
- `ENTREGADA` → `EN_PLATAFORMA` requiere un evento `FirmaRegistrada` de actor `humano` (la firma no la hacemos nosotros; solo registramos que ocurrió, con quién y cuándo).
- Tras `EN_PLATAFORMA`, **ningún cambio de datos es válido fuera de un requerimiento oficial** (inalterabilidad). Un intento de corrección interna post-firma se rechaza con evento `CorreccionRechazadaPostFirma`.
- Un requerimiento de GA o CN sobre una actuación genera `PENDIENTE_SUBSANACION` en **todas** las actuaciones del expediente, con `afectada_directamente: bool`. Es el riesgo de contagio hecho estado.
- Presupuesto de pasos y de coste por actuación; agotado, `EN_REVISION_HUMANA`.

### 3.4 Log de eventos (N8) — `NUEVO`

Sobre, reglas de solo-añadir, JSON canónico y replay: como `07` §5.1. Se amplía el catálogo de eventos:

| Proceso | Eventos |
|---|---|
| P0 Admisión | `ActuacionAbierta`, `TenantAsignado`, `VerificadorAsignado` |
| P1 Ingesta | `DocumentoRegistrado` (con `sha256` **siempre**), `DocumentoClasificado`, `PdfSeparado` |
| P2 Evidencias | `EvidenciaPropuesta`, `EvidenciaDescartadaSinCita`, `DesacuerdoExtractores` |
| P3 Ficha | `FichaAsignada`, `CabeceraConsolidada` |
| P4 Cruce | `DatoConsolidado`, `ConflictoDetectado`, `DatoCorregidoPorHumano` |
| P5 Cálculo | `CalculoRealizado`, `DiscrepanciaCalculoPlataforma` |
| P6 Pre-revisión | `ObservacionRegistrada` |
| P7 Subsanación | `SubsanacionSolicitada{origen}`, `SubsanacionCerrada`, `CorreccionRechazadaPostFirma` |
| P8 Empaquetado | `PayloadConstruido`, `ManifiestoGenerado`, `EntregadoADelegado`, `EnviadoAPI`, `FirmaRegistrada` (actor humano) |
| P9 Seguimiento | `EstadoPlataformaRecibido`, `TareaPendienteRecibida`, `RequerimientoRecibido{origen}`, `RequerimientoInterpretado`, `DesistimientoRegistrado` |
| P10 Composición | `GrupoPropuesto`, `ExpedientePropuesto`, `AvisoContagio`, `ActuacionHuerfana` |

### 3.5 Mapa de módulos (estado a 18/09/2026)

**Núcleo determinista**

| ID | Módulo | Función | Estado |
|---|---|---|---|
| N1 | Spec Registry | Fichas YAML versionadas + **spec transversal de cabecera** + vigencias + coeficientes (art. 18 bis, cuando existan) | `PARCIAL`: una ficha; sin cabecera, vigencias ni coeficientes |
| N2 | Rules Engine | Evalúa reglas a **tres niveles** (actuación/unidad, grupo, expediente) y fija veredictos | `EXISTE` nivel actuación (`engine/reglas.py`); `NUEVO` grupo y expediente |
| N3 | Calculation Engine + tablas | Fórmula del YAML, `Decimal`, traza; cuadro 6 Reg. (UE) 2019/1781; **control cruzado** con el valor de la plataforma | `EXISTE`; control cruzado `NUEVO` |
| N4 | Evidence Store | Grafo de evidencias, tres capas, `tratable_por_plataforma` | `PARCIAL`: en memoria |
| N5 | Integridad | SHA-256 de **todo** fichero + manifiesto interno | `PARCIAL`: solo registro SCADA |
| N6 | Máquina de estados | Cuatro niveles (§3.3), contagio, inalterabilidad post-firma | `NUEVO` |
| N7 | Modelo canónico | `Actuacion`, `GrupoActuaciones`, `Expediente`, `Verificador`, `Tenant` | `NUEVO` |
| N8 | Log de eventos | Solo-añadir, hash encadenado, replay | `NUEVO` |
| N9 | Compositor de expedientes | Propone grupos y expedientes válidos a partir de `R-GRP`/`R-EXP` | `NUEVO` · Sprint 4 |

**Servicios**

| ID | Módulo | Función | Estado |
|---|---|---|---|
| S1 | Ingesta | PDF nativo, OCR, xlsx, EXIF, separación de PDF combinados, clasificación léxica; **hash de todo** | `EXISTE`; hash total `NUEVO` |
| S2 | Agent Runtime | Contrato común de agentes (`07` §8) | `NUEVO` |
| S3 | Orquestador | Workflow por eventos con tareas humanas; máquina de estados como A0 | `PARCIAL`: `engine/motor.py` lineal |
| S4 | Consola de revisión | Escalados, conflictos, correcciones, **tareas pendientes de la plataforma**; centrada en lo previo a la firma | `NUEVO` |
| S5 | Salida | Puerto + adaptadores handoff / simulador / API; `transporte/` y `firma/` separados | `NUEVO` · Sprint 3 |
| S6 | Evaluación | Banco de pruebas, fábrica de casos, metamórficas, **batería INT-xx contra sandbox** | `PARCIAL`: 7 casos, 61 tests |
| S7 | Seguridad y tenencia | Aislamiento por tenant (delegado u obligado directo), enmascarado, anonimización | `NUEVO` |
| S8 | Vigilancia normativa (A6) | Fuera de línea; propone diffs sobre YAML; sigue RD 36/2023, órdenes, plataforma | `PARCIAL`: vigilancia manual/programada; sin diff automático |

### 3.6 Spec Registry (N1): ficha + cabecera + vigencias

Tres tipos de spec, todos YAML, todos versionados:

| Tipo | Fichero | Contenido | Estado |
|---|---|---|---|
| Ficha | `spec/IND240_v1.1.yaml` | Ámbito, variables, cálculo, documentación, reglas, interpretaciones | `EXISTE` |
| **Cabecera transversal** | `spec/cabecera_v1.yaml` | Variables comunes a todas las fichas (tabla siguiente), fuentes documentales, tipo de evidencia, reglas `R-CAB-*` | `NUEVO` |
| Tablas y coeficientes | `data/*.csv` + `spec/coeficientes_*.yaml` | Tablas de referencia con fuente y **vigencia** (`desde`, `hasta`) | `PARCIAL`: cuadro 6 sin vigencia; coeficientes no existen |

**Variables de la cabecera** (`10` §3), con lo que sabemos de su fuente:

| Variable | Fuente documental | Tipo de evidencia | Estado |
|---|---|---|---|
| `codigo_identificativo_propio` | Generado por el Engine (= `Actuacion.id`) | derivado | Encaje directo |
| `fecha_inicio_ejecucion`, `fecha_fin_ejecucion` | Pedido, factura, certificado instalador (ya existen como `fecha_inicio/fin_actuacion`) | demostrado | `EXISTE` |
| `precio_contrato_cesion` | Convenio CAE | demostrado | `NUEVO`: hoy solo capturamos *tipo de contraprestación* |
| `inversion_realizada` | Facturas (suma de base imponible de líneas elegibles) | derivado | `NUEVO`; criterio de qué líneas suman → `INT-09` propuesto |
| `costes_operativos_anuales` | Sin fuente documental clara | declarado | `NUEVO`; semántica `NO DOCUMENTADO` |
| `tipologia_empresa` | Declaración responsable o declarado | declarado | `NUEVO`; taxonomía `NO DOCUMENTADO` → `TODO(API-05)` |
| `localizacion` (UTM, ref. catastral, **CCAA**) | Convenio CAE | demostrado; CCAA derivada de la referencia | `PARCIAL`: hoy solo se comprueba presencia en el convenio |
| `propietario_inicial` (NIF, razón social) | Ficha, factura, declaración, convenio (`R-CON-05`) | demostrado | `EXISTE` |
| `participe_subvencion` (valor, no solo presencia) | Declaración responsable de ayudas | demostrado | `PARCIAL`: hoy solo presencia (DOC-02) |
| `participe_subasta` | Nuevo concepto del RD modificado | declarado | `NUEVO`; semántica `NO DOCUMENTADO` → `TODO(API-06)` |
| `verificador_id`, `sector`, `anio_finalizacion` | Asignación del tenant; ficha; `fecha_fin_ejecucion` | declarado / derivado | `NUEVO`; necesarios para componer expediente |

Regla de vigencia de versiones de ficha: sigue `A CONFIRMAR` con normativa/verificador (`07` §6.10). N1 debe soportar varias versiones simultáneas.

### 3.7 Integridad (N5)

- SHA-256 de **todo** fichero en el momento de ingesta, antes de cualquier transformación; el hash del original se conserva aunque se separe un PDF combinado (se registran ambos: original y partes).
- Manifiesto interno como `07` §9.5, más `hash_cabecera` y `hash_detalle` del payload, para poder demostrar qué se envió.
- El formato del manifiesto **oficial** (algoritmo, estructura) es `NO DOCUMENTADO` → `TODO(API-02)`. El mapeo del nuestro al oficial vive en `mapping/manifiesto.<destino>.yaml`.

### 3.8 Salida (S5): puerto, adaptadores, transporte y firma

Puerto (`07` §9.1) sin cambios en su firma: `construir`, `entregar`, `consultar_estado`. Se añade `consultar_tareas(tenant) → TareaPendiente[]`.

| Adaptador | Para qué | Dependencia | Cuándo |
|---|---|---|---|
| Handoff | Carpeta ordenada + manifiesto + informe, para que el tenant presente por el cauce vigente | Ninguna | Sprint 3 |
| Simulador | 8 estados de fase 1 + estados provisionales de fases 2–4 + manifiesto con hash + validación de esquema + **firma humana simulada** + tareas pendientes | Ninguna | Sprint 3 |
| API oficial | Envío, consulta, notificaciones, tareas | Diccionario + certificado de usuario | Cuando existan |

**División del antiguo "firmante"** (`07` §9.3), tras `10` §6:

```
salida/
  constructor/    payload cabecera + detalle + manifiesto, sin firmar        NUESTRO, en nuestra infraestructura
  transporte/     firma de peticiones API con certificado de USUARIO         Dónde vive: depende de la respuesta del gestor
                  (perfil Modificación). Reenvía estados y tareas como eventos   · si admite terceros: nuestra infra, aislado por tenant
                                                                                · si no: componente desplegable en casa del tenant
  firma/          NO ES SOFTWARE NUESTRO. Es un paso humano con certificado    Solo registramos FirmaRegistrada
                  de REPRESENTANTE en casa del tenant
```

Regla que se mantiene: **nunca custodiamos certificados de representante**. Para el certificado de usuario, la decisión es de Billy tras la respuesta del gestor de la plataforma (`00` §5.6).

### 3.9 Seguimiento post-envío (P9) y subsanación con tres orígenes (P7)

| Origen | Llega como | Alcance | Bloquea | Lo interpreta | Alimenta |
|---|---|---|---|---|---|
| `interno` | Regla fallada del Engine | Actuación | Nada externo | Regla (campo `subsanacion`) + A5 redacta | Petición al cliente |
| `verificador` | `PDTE_RECTIFICACION_VER` + motivos (+ informe PDF) | Actuación (o grupo, con dictamen único) | La actuación / el grupo | A9 → `{regla_id | documento, texto_literal, confianza}`; humano confirma | P7 + banco de pruebas (anonimizado) |
| `GA` | Requerimiento en fase 3A (+ informe PDF) | Por actuación, **bloquea el expediente completo** | Todo el expediente | A9 | P7 sobre todas las actuaciones del expediente |
| `CN` | Requerimiento en fase 3B, posible segunda ronda | Idem | Todo el expediente | A9 | Idem |

El sujeto puede **desistir** durante un requerimiento de GA o CN: evento `DesistimientoRegistrado`, actor humano.

**Tareas pendientes** de la plataforma (`10` §5): se consumen por API y se proyectan en la consola (S4) como cola priorizada del tenant. Es la única parte de la consola que mira aguas abajo de la firma; el resto se centra en lo previo.

### 3.10 Seguridad y tenencia (S7)

Como `07` §11, con dos ampliaciones: el tenant puede ser un **sujeto obligado directo** (≥ 50 MWh) además de un delegado, y el tenant lleva `capacidad_delegacion_disponible` como atributo informativo (cómo se consulta en la plataforma: `NO DOCUMENTADO`). Un tenant sin capacidad no puede recibir actuaciones en `LISTA_PARA_ENVIO` sin aviso explícito.

### 3.11 Estructura de repositorio (revisada)

```
spec/                     IND240_v1.1.yaml · cabecera_v1.yaml (NUEVO) · coeficientes_*.yaml (cuando existan)
mapping/                  <FICHA>.handoff.yaml · <FICHA>.api.yaml · manifiesto.<destino>.yaml    NUEVO
data/                     tablas de referencia con vigencia
engine/
  ingesta.py extraccion.py reglas.py calculo.py registro_xlsx.py motor.py informe.py cli.py   EXISTE
  modelo/                 Actuacion, GrupoActuaciones, Expediente, Verificador, Tenant       NUEVO
  eventos/                log, hash, replay                                                   NUEVO
  estados.py              cuatro niveles, contagio, inalterabilidad                           NUEVO
  compositor.py           R-GRP / R-EXP, propuesta de lotes                                   NUEVO (Sprint 4)
  expresiones.py          parser de lista blanca                                              A CONFIRMAR
agentes/
  runtime/ lector/ analista/ redactor/                                                        NUEVO
salida/
  puerto.py constructor/ handoff/ simulador/ api_oficial/ transporte/                         NUEVO
  HUECOS.md               TODO(API-xx) enumerados con dueño y fecha                           NUEVO
generator/ tests/                                                                             PARCIAL / EXISTE
```

---

## 4. Funcionalidades que incorpora

Catálogo funcional visto desde el producto. Cada línea dice qué producto la vende, qué proceso la sostiene, si es **diferencial** frente a la plataforma oficial (lo que ella no hace) y su estado.

| ID | Funcionalidad | Producto | Proceso / módulo | ¿Diferencial? | Estado |
|---|---|---|---|---|---|
| F-01 | Ingesta de documentación desordenada (PDF, escaneos, xlsx, fotos, PDF combinados) con hash de todo | CAE Check | P1 / S1, N5 | Sí | `EXISTE` (hash total `NUEVO`) |
| F-02 | Clasificación documental con confianza | CAE Check | P1 / A1 | Sí | `EXISTE` (reglas léxicas) |
| F-03 | Extracción de variables con evidencia (documento, página, texto, método, confianza) | CAE Check | P2 / A2, N4 | Sí | `EXISTE` reglas · LLM `NUEVO` |
| F-04 | Cruce de **contenido** entre documentos y detección de contradicciones con ambas evidencias | CAE Check | P4 / R-CON, A4 | **Sí, el núcleo del diferencial** | `EXISTE` |
| F-05 | Comprobación de ámbito y exclusiones de la ficha | CAE Check | P3 / R-AMB | Parcial (la plataforma valida lo tratable; el ámbito exige leer documentos) | `EXISTE` |
| F-06 | Comprobación de presencia documental | CAE Check | R-DOC-01 | **No** (la plataforma lo hace); se mantiene como control previo | `EXISTE` |
| F-07 | Comprobación de evidencia demostrada vs. declarada (registro ≥ 30 días, inalterabilidad) | CAE Check | R-EVD | Sí | `EXISTE` |
| F-08 | Cálculo determinista con traza | CAE Check | P5 / N3 | No como producto; sí como **control cruzado** | `EXISTE` |
| F-09 | Control cruzado con el cálculo de la plataforma; bloqueo ante discrepancia | CAE Check / Platform | P5, P8 / N3, R-XCK | Sí | `NUEVO` (necesita sandbox) |
| F-10 | "Qué te falta": lista de carencias por regla, en lenguaje llano, con documentos concretos | CAE Check | P7 / campo `subsanacion`, A5 | Sí | `PARCIAL`: reglas sí, redacción `NUEVO` |
| F-11 | Cabecera común completa (precio de cesión, inversión, localización, propietario, subvención…) extraída de documentos | CAE Platform | P3 / `cabecera_v1.yaml`, R-CAB | Sí (la plataforma la pide; nosotros la rellenamos con evidencia) | `NUEVO` |
| F-12 | Payload de actuación (cabecera + detalle + manifiesto) listo para `BORRADOR` → `COMPLETA` | CAE Platform | P8 / S5 constructor | Sí | `NUEVO` |
| F-13 | Handoff al tenant (carpeta + manifiesto + informe) por el cauce vigente | CAE Platform | S5 handoff | Sí | `NUEVO` · Sprint 3 |
| F-14 | Consumo de notificaciones y **tareas pendientes** de la plataforma; cola priorizada por tenant | CAE Platform | P9 / S4 | Sí | `NUEVO` |
| F-15 | Interpretación de requerimientos de verificador, GA y CN → reglas y documentos; reapertura de subsanación con contagio | CAE Platform | P9, P7 / A9, N6 | Sí | `NUEVO` · Sprint 3 |
| F-16 | **Expediente Builder**: propuesta de grupos y expedientes válidos (CCAA + año + sector + verificador), avisos de huérfanas y de contagio | CAE Platform | P10 / N9, R-GRP, R-EXP | Sí | `NUEVO` · Sprint 4 |
| F-17 | Informe de prevalidación por destinatario (cliente, instalador, tenant) | CAE Check / Platform | A7 | Sí | `PARCIAL`: markdown/JSON único |
| F-18 | Revisor sombra (A8): observaciones sin alterar el veredicto; promoción a regla cuando anticipe rectificaciones | CAE Platform | P6 | Sí | `NUEVO` |
| F-19 | Preparación de actuaciones singulares y vinculación a CVP | Roadmap | — | Sí | Decisión de Billy · fase II plataforma |
| F-20 | Registro de resultado real (dictamen, resolución) como etiqueta para el banco de pruebas | CAE Monetization | P9 / S6 | Sí (activo defendible) | `NUEVO` |
| F-21 | Multi-tenant: delegados y sujetos obligados directos, aislamiento, capacidad disponible | CAE Platform | S7 | — | `NUEVO` |
| F-22 | Replay de cualquier actuación pasada contra nueva spec/regla/agente (regresión automática) | Interno | N8 | — | `NUEVO` |
| F-23 | Vigilancia normativa con propuesta de diff sobre el YAML | Interno / A6 | S8 | — | `PARCIAL` |

**Lectura de negocio.** De las 23 funcionalidades, 17 son diferenciales, una lo es parcialmente (F-05), tres son internas (F-21..23) y dos no lo son. Esas dos (F-06 y F-08 como producto) son justo las que la competencia vende como "checklist" y "calculadora"; no deben aparecer como reclamo, sino como controles previos. Lo que se vende es F-03 + F-04 + F-07 + F-10 (CAE Check) y F-11 a F-16 (CAE Platform).

---

## 5. Motor de reglas (N2)

### 5.1 Qué es, ampliado a tres niveles

Sigue siendo una función pura, sin estado, sin modelos, sin lectura de documentos:

```
evaluar_actuacion(actuacion, spec_ficha, spec_cabecera, tablas) → { resultados[], veredicto, hash_reglas }
evaluar_grupo(grupo, actuaciones_evaluadas)                     → { resultados[], veredicto_agregado, avisos[] }
evaluar_expediente(expediente, actuaciones_evaluadas)           → { resultados[], valido: bool, avisos_contagio[] }
```

El veredicto de la actuación (`NO_ELEGIBLE` … `PREVALIDADO`) no cambia. El grupo y el expediente no tienen veredicto de calidad sino **validez de composición** y **avisos**; la calidad sigue viviendo en cada actuación.

### 5.2 Anatomía de una regla

Campos `EXISTE` (`07` §6.2) más los `NUEVO` de `07` (`fase`, `nivel`, `subsanacion`, `vigencia`). Se añaden, retrocompatibles:

```yaml
- id: R-CON-01
  descripcion: "PM coincide en todas las fuentes"
  logica: "unique(PM.valores_por_fuente)"
  severidad: BLOQUEANTE_DATOS
  referencia: SRC-FICHA §3
  fase: consistencia
  nivel: unidad                    # unidad | actuacion | grupo | expediente
  diferencial: true                # false si la plataforma oficial ya hace esta comprobación (R-DOC-01)
  equivalente_plataforma: null     # TODO(API-xx) si la plataforma valida lo mismo; permite el control cruzado
  origen_subsanacion: [interno, verificador]   # qué actores suelen requerir por esta regla (alimenta A9)
  subsanacion:
    mensaje: "…"
    documentos: [ficha_tecnica_motor, certificado_instalador]
```

`diferencial` y `equivalente_plataforma` no cambian la evaluación: sirven para el informe, para el discurso comercial y para saber qué comparar con el sandbox.

### 5.3 Severidades, veredicto y resultado de regla

Sin cambios respecto a `07` §6.3 y §6.5: cuatro severidades, orden `NO_ELEGIBLE` > `BLOQUEADO` > `SUBSANABLE` > `PREVALIDADO`, tres resultados (`CUMPLE`, `FALLA`, `NO_EVALUABLE`) y la garantía de que toda regla bloqueante que pueda quedar `NO_EVALUABLE` tiene una regla `SUBSANABLE` que detecta la carencia. Esa garantía se convierte en **test automático del Spec Registry** al cargar cualquier ficha (hoy `A CONFIRMAR`).

Para grupo y expediente se añade una severidad propia, `COMPOSICION`, con dos efectos: `INVALIDO` (no se puede componer; la plataforma lo rechazaría) y `AVISO_CONTAGIO` (se puede, pero un miembro débil arrastra a los demás).

### 5.4 Familias de reglas

| Familia | Nivel | Qué comprueba | Quién la declara | Estado |
|---|---|---|---|---|
| `R-AMB` | unidad / actuación | Ámbito y exclusiones de la ficha | Ficha | `EXISTE` (3) |
| `R-DOC` | actuación | Presencia y contenido mínimo de documentos | Ficha | `EXISTE` (5); R-DOC-01 `diferencial: false` |
| `R-EVD` | unidad | Evidencia demostrada: registro, inalterabilidad, derivación | Ficha | `EXISTE` (4) |
| `R-CON` | unidad / actuación | Consistencia entre fuentes | Ficha | `EXISTE` (7) |
| `R-TMP` | actuación | Fechas y plazos de procedimiento | Ficha (o cabecera si es común) | `EXISTE` (3); R-TMP-03 a corregir |
| `R-CAL` | unidad | Precondiciones y controles físicos del cálculo | Ficha | `EXISTE` (4) |
| **`R-CAB`** | actuación | Cabecera común: presencia, fuente y coherencia de los campos transversales | `cabecera_v1.yaml` | `NUEVO` (§5.6) |
| **`R-GRP`** | grupo | Composición válida de un grupo de actuaciones | `composicion_v1.yaml` | `NUEVO` (§5.7) |
| **`R-EXP`** | expediente | Composición válida de un expediente y avisos de contagio | `composicion_v1.yaml` | `NUEVO` (§5.7) |
| **`R-XCK`** | actuación | Control cruzado con la plataforma (cálculo y validaciones tratables) | `cabecera_v1.yaml` + mapping | `NUEVO` (§5.8); necesita sandbox |
| **`R-REQ`** | actuación / expediente | Coherencia de la respuesta a un requerimiento oficial | `composicion_v1.yaml` | `NUEVO` (§5.9) |

### 5.5 Cambios sobre `IND240_v1.1.yaml` → `v1.2` (propuesta para revisión humana)

| Cambio | Antes | Después | Motivo |
|---|---|---|---|
| `R-TMP-03` | `solicitud.fecha <= fecha_fin_actuacion + 3 años` | `solicitud.fecha <= fecha(31, 12, anio(fecha_fin_actuacion) + n)` con `n` en `INT-08` | La plataforma aplica "3 años desde el **año** de finalización, vencimiento el 31/12" (`10` D6). Confirmar `n` con art. 17 Orden TED/815/2023 |
| `INT-08` (nuevo) | — | Tema: regla de expiración; criterio: `31/12/(año_fin + n)`, `n = 3` provisional; alternativa: fecha exacta + 3 años; impacto: medio | Interpretación abierta hasta confirmar con la Orden y con la plataforma |
| `R-DOC-01` | — | `diferencial: false`, `equivalente_plataforma: TODO(API-04)` | `10` §3: la plataforma comprueba presencia por tipo |
| `R-CON-05` | `unique(titular_nif)` | Sin cambio en lógica; `nivel: actuacion`, alimenta `cabecera.propietario_inicial` | Enlace con la cabecera |
| Variables | — | `fecha_inicio/fin_actuacion` pasan a declararse en `cabecera_v1.yaml` y la ficha las **hereda** | Son comunes a todas las fichas (art. 14.9.j) |
| `INT-09` (nuevo) | — | Tema: qué líneas de factura suman en `inversion_realizada`; criterio: base imponible de líneas del variador y su instalación; alternativa: total factura; impacto: bajo para el ahorro, medio para la cabecera | Campo de cabecera sin criterio oficial publicado |
| `version_spec` | `0.1.0` | `0.2.0` | Cambio de reglas |

Ningún otro cambio en las 26 reglas. El diff se prepara como fichero aparte y no se activa sin revisión de Billy (regla de oro 9).

### 5.6 Reglas transversales de cabecera (`R-CAB`, propuesta)

Viven en `spec/cabecera_v1.yaml` y se evalúan en **toda** ficha. Severidades propuestas; los campos cuya semántica es `NO DOCUMENTADO` solo pueden ser `AVISO` hasta que llegue el diccionario.

| ID | Descripción | Lógica (vocabulario cerrado) | Severidad | Diferencial |
|---|---|---|---|---|
| R-CAB-01 | Código identificativo propio único en el tenant | `unique_in_tenant(codigo_identificativo_propio)` | BLOQUEANTE_DATOS | — |
| R-CAB-02 | Fechas de ejecución presentes y coherentes | `exists(fecha_inicio) and exists(fecha_fin) and fecha_inicio <= fecha_fin` | BLOQUEANTE_DATOS | Parcial |
| R-CAB-03 | Precio del contrato de cesión presente en el convenio y con evidencia | `precio_contrato_cesion.evidencia == demostrado` | SUBSANABLE | Sí |
| R-CAB-04 | Inversión realizada derivada de facturas (INT-09) y > 0 | `inversion_realizada.evidencia == derivado and inversion_realizada > 0` | SUBSANABLE | Sí |
| R-CAB-05 | Costes operativos anuales informados | `exists(costes_operativos_anuales)` | AVISO (semántica no documentada) | — |
| R-CAB-06 | Tipología de empresa informada | `exists(tipologia_empresa)` | AVISO (taxonomía `TODO(API-05)`) | — |
| R-CAB-07 | Localización completa (UTM, ref. catastral) y CCAA derivable | `exists(localizacion.utm) and exists(localizacion.ref_catastral) and exists(localizacion.ccaa)` | SUBSANABLE | Sí |
| R-CAB-08 | Propietario inicial coincide con el titular del convenio y de la declaración | `propietario_inicial.nif == titular_nif` | BLOQUEANTE_DATOS | Sí |
| R-CAB-09 | Partícipe en subvención: valor declarado y coherente con la declaración responsable | `participe_subvencion in [true, false] and coherente(declaracion_responsable)` | SUBSANABLE | Sí |
| R-CAB-10 | Partícipe en subasta informado | `exists(participe_subasta)` | AVISO (`TODO(API-06)`) | — |
| R-CAB-11 | Verificador asignado y acreditado | `exists(verificador_id)` | SUBSANABLE (necesario para componer) | — |
| R-CAB-12 | Convenio CAE firmado antes de la solicitud (hoy R-TMP-02 en IND240) | `convenio.fecha_firma <= solicitud.fecha` | SUBSANABLE | Sí |
| R-CAB-13 | Validez del CAE (hoy R-TMP-03; INT-08) | `solicitud.fecha <= fecha(31,12, anio(fecha_fin) + n)` | AVISO | Parcial |

R-TMP-02 y R-TMP-03 de IND240 pasan a la cabecera y la ficha las hereda; así no se repiten en TRA050.

### 5.7 Reglas de composición (`R-GRP`, `R-EXP`, propuesta — Sprint 4)

| ID | Nivel | Descripción | Lógica | Severidad |
|---|---|---|---|---|
| R-GRP-01 | grupo | Todas las actuaciones del grupo tienen el mismo verificador | `unique(actuaciones.verificador_id)` | COMPOSICION → INVALIDO |
| R-GRP-02 | grupo | Ninguna actuación del grupo está `NO_ELEGIBLE` o `BLOQUEADO` | `all(a.veredicto in [PREVALIDADO, SUBSANABLE])` | COMPOSICION → INVALIDO |
| R-GRP-03 | grupo | No mezclar `SUBSANABLE` con `PREVALIDADO` (dictamen único) | `unique(actuaciones.veredicto)` | COMPOSICION → AVISO_CONTAGIO |
| R-EXP-01 | expediente | Misma CCAA, año de finalización, sector y verificador | `unique(ccaa) and unique(anio_finalizacion) and unique(sector) and unique(verificador_id)` | COMPOSICION → INVALIDO |
| R-EXP-02 | expediente | Solo actuaciones `VERIFICADA_FAVORABLE` (o un grupo con dictamen favorable) | `all(a.estado_plataforma == VERIFICADA_FAVORABLE)` | COMPOSICION → INVALIDO |
| R-EXP-03 | expediente | Un grupo verificado junto va en expediente propio | `grupo_id == null or count(grupos) == 1 and count(actuaciones_sueltas) == 0` | COMPOSICION → INVALIDO |
| R-EXP-04 | expediente | Aviso de contagio: alguna actuación con observaciones de A8 o avisos abiertos | `count(a where a.observaciones_abiertas > 0) > 0` | COMPOSICION → AVISO_CONTAGIO |
| R-EXP-05 | actuación | Actuación huérfana: única en su clave (CCAA, año, sector, verificador) dentro del tenant | `count_in_tenant(clave_agrupacion) == 1` | AVISO (informativo para el delegado) |
| R-EXP-06 | expediente | Capacidad de delegación disponible del tenant suficiente | `tenant.capacidad_disponible >= sum(ahorro)` | AVISO (`NO DOCUMENTADO` cómo se consulta) |

Cómo se determina la CCAA de una actuación (¿por localización del convenio? ¿por declaración?) es `NO DOCUMENTADO` → `TODO(API-07)`. Hasta entonces se deriva de la referencia catastral y se marca `derivado`.

### 5.8 Control cruzado con la plataforma (`R-XCK`, propuesta — necesita sandbox)

| ID | Descripción | Lógica | Efecto |
|---|---|---|---|
| R-XCK-01 | El ahorro calculado por la plataforma coincide con el nuestro | `abs(plataforma.ahorro_kwh - AETOTAL_cae) <= tolerancia_xck` | Si falla: `DiscrepanciaCalculoPlataforma`, **no se envía** hasta resolución humana |
| R-XCK-02 | Todas las validaciones "tratables" de la plataforma pasan en el simulador antes del envío real | `simulador.validaciones_tratables == OK` | BLOQUEANTE_DATOS en P8 |
| R-XCK-03 | El manifiesto que aceptó la plataforma coincide con el nuestro (hashes) | `plataforma.manifiesto.hashes == manifiesto_interno.hashes` | BLOQUEANTE_DATOS en P8 |

`tolerancia_xck` empieza en 0 (aritmética exacta, `Decimal`). Cada discrepancia se clasifica a mano en una de tres causas: bug nuestro, `INT-xx` mal resuelto o criterio oficial distinto. La tercera es la que cierra INT-01..05 empíricamente.

### 5.9 Reglas de requerimiento (`R-REQ`, propuesta — Sprint 3 paso 1.5)

| ID | Descripción | Lógica | Severidad |
|---|---|---|---|
| R-REQ-01 | Toda subsanación con origen externo referencia un requerimiento con informe (PDF con hash) | `origen != interno -> exists(requerimiento_ref) and exists(informe_pdf_sha256)` | BLOQUEANTE_DATOS |
| R-REQ-02 | La interpretación de A9 ha sido confirmada por un humano antes de reabrir P7 | `requerimiento.interpretacion.confirmada_por_humano == true` | BLOQUEANTE_DATOS |
| R-REQ-03 | Tras la firma, ningún dato consolidado cambia fuera de un requerimiento abierto | `estado_ciclo >= EN_PLATAFORMA -> cambios_datos.only_within(requerimientos_abiertos)` | BLOQUEANTE_DATOS |
| R-REQ-04 | Un requerimiento de GA/CN marca como afectadas todas las actuaciones del expediente | `origen in [GA, CN] -> afectadas == expediente.actuaciones` | Invariante (test) |

### 5.10 Orden de evaluación por fases (actualizado)

| Fase | Reglas | Si falla |
|---|---|---|
| 0. Cabecera | `R-CAB-01, 02, 08` (bloqueantes) | `BLOQUEADO`; el resto de `R-CAB` se evalúa en fase 5 |
| 1. Ámbito | `R-AMB-*` | `NO_ELEGIBLE`; se detiene |
| 2. Consistencia previa | `R-CON-01..05, 07` · `R-TMP-01` · `R-CAL-01, 04` · `R-CAL-02` (aviso) | `BLOQUEADO`; no se calcula |
| 3. Cálculo | N3 | — |
| 4. Posterior al cálculo | `R-CAL-03` (retira el resultado) · `R-CON-06` | Según severidad |
| 5. Resto | `R-DOC-*` · `R-EVD-*` · `R-CAB-03..07, 09..13` | `SUBSANABLE` o aviso |
| 6. Control cruzado (solo en P8, con simulador o sandbox) | `R-XCK-*` | Bloquea el envío |
| 7. Composición (solo en P10) | `R-GRP-*`, `R-EXP-*` | `INVALIDO` o `AVISO_CONTAGIO` |
| Transversal | `R-REQ-*` | Invariantes del ciclo |

La asignación regla a regla de las fases 1–5 sigue `A CONFIRMAR` contra `engine/reglas.py`.

### 5.11 Lenguaje de expresiones

Como `07` §6.7 (parser de lista blanca, nunca `eval()`, función desconocida = error de carga). Funciones que las reglas nuevas necesitan y que hay que añadir al vocabulario: `unique_in_tenant`, `count_in_tenant`, `anio`, `fecha(d, m, a)`, `coherente` (definida por regla, no genérica; si no se puede expresar con el vocabulario cerrado, la regla queda en código con test que verifique su `logica`), `only_within`.

### 5.12 Versionado, vigencias y coeficientes

Como `07` §6.10. Se añade: la **cabecera** tiene su propia `version_cabecera`; cada evaluación registra `version_ficha`, `version_spec`, `version_cabecera`, `version_composicion` y `hash_reglas` sobre el conjunto. Los coeficientes de corrección (art. 18 bis del proyecto de RD) se modelan como tabla con vigencia y ficha afectada, alineado con lo que la alegación pide que sea oficial (`00` §5.6).

### 5.13 Checklist para añadir una ficha (actualizado)

1. Leer la ficha en BOE / catálogo; anotar versión y fecha.
2. Escribir `spec/<FICHA>_v<x>.yaml` **heredando** `cabecera_v1.yaml`: solo lo específico de la ficha.
3. Todo lo que la ficha no cierre → `INT-xx`.
4. Tablas en `data/` con fuente, verificación y vigencia.
5. `mapping/<FICHA>.handoff.yaml` y, cuando exista diccionario, `<FICHA>.api.yaml`.
6. Paquete sintético: un caso por veredicto + uno desordenado + **uno con cabecera incompleta**.
7. Tests: por regla, caso que cumple y que falla; garantía de §5.3; metamórficas; **composición** (la ficha entra en un expediente con otra ficha del mismo sector).
8. Revisión humana de la spec.
9. **Cero cambios en `engine/`**; si hacen falta, defecto del marco.

---

## 6. Evaluación (delta sobre `07` §10)

Se mantienen las cinco fuentes de verdad y las propiedades metamórficas. Se añaden:

- **Metamórficas de composición**: reordenar actuaciones dentro de un expediente no cambia su validez; añadir una actuación de otra CCAA lo invalida; quitar la única `SUBSANABLE` elimina el aviso de contagio.
- **Metamórficas de ciclo**: ningún evento de actor `agente` o `motor` puede mover una actuación de `ENTREGADA` a `EN_PLATAFORMA` (solo `humano` con `FirmaRegistrada`).
- **Batería INT-xx** (cuando haya sandbox): para cada interpretación abierta, al menos dos casos que produzcan resultados distintos según el criterio; la respuesta de la plataforma discrimina.
- **Métrica nueva de producto**: % de actuaciones `PREVALIDADO` que llegan a `VERIFICADA_FAVORABLE` sin requerimiento. Es la métrica de `00` §1 hecha medible; no tiene valor hasta el modo sombra.

---

## 7. Huecos documentales consolidados (`HUECOS.md`)

| ID | Hueco | Bloquea | Dueño | Revisar cuando |
|---|---|---|---|---|
| API-01 | Endpoints, autenticación concreta, ejemplos | Conector API | Billy (correo 0.4) | Llegue el diccionario |
| API-02 | Formato del manifiesto oficial (algoritmo, estructura) | Mapping de manifiesto | Idem | Idem |
| API-03 | Estados de expediente fases 2–4 y de la solicitud | N6 (nombres provisionales) | Idem | Idem |
| API-04 | Si la validación documental comprueba contenido o solo presencia | Valor de R-DOC y R-CON | Idem | Idem / fase II |
| API-05 | Taxonomía de "tipología de empresa" | R-CAB-06 | Idem | Idem |
| API-06 | Semántica de "partícipe en subasta" | R-CAB-10 | Idem | Idem / RD modificado |
| API-07 | Cómo se determina la CCAA de una actuación | R-EXP-01 | Idem | Idem |
| API-08 | Nombres, tipos, unidades y granularidad (por motor o agregado) del formulario de detalle | Mapping por ficha | Idem | Idem |
| API-09 | Si el perfil Modificación admite terceros o cuentas de sistema | Dónde vive `transporte/` | Billy | Respuesta del gestor |
| API-10 | Plazos de requerimientos y contestaciones | Alertas en S4 | — | Diccionario / fase II |
| API-11 | Cómo se consulta la capacidad de delegación disponible | R-EXP-06 | — | Diccionario |
| API-12 | Criterio oficial para PM sin fila exacta y acreditación de N2 (INT-01..05) | Cálculo | Sandbox | Batería INT-xx |

---

## 8. Decisiones abiertas para Billy

| Asunto | Opciones | Dónde impacta |
|---|---|---|
| Aprobar la edición de `06` a v1.1 (anexo §9) | Aplicar tal cual / con cambios / no tocar | Coherencia documental |
| Aprobar el diff `IND240_v1.1` → `v1.2` (§5.5) | Sí / revisar `n` de INT-08 antes | Spec, tests |
| Aprobar las familias `R-CAB`, `R-GRP/R-EXP`, `R-XCK`, `R-REQ` como diseño | Sí / recortar | Sprint 3 y 4 |
| Vía del perfil Modificación (tras respuesta del gestor) | Transporte en nuestra infra / en casa del tenant | `salida/transporte/` |
| Expediente Builder en Sprint 4 | Sí / posponer | N9, F-16 |
| Módulo de singulares / CVP en roadmap | Sí / no | F-19 |
| Proveedor LLM y condiciones de datos (`07` §11) | — | Paso 1.6 |
| Umbral de activación de agentes en producción (`07` §8.3) | — | S2 |

---

## 9. Anexo — Propuesta de edición de `06` → v1.1 (no aplicada)

| Sección | Edición propuesta |
|---|---|
| Cabecera | Versión 1.1 · 18/09/2026. Corregir la ruta a `00-instrucciones-de-entrada.md` (raíz). Añadir línea "Cambios en 1.1: alineación con `10` y `00` v1.2". |
| §1.1 | Sustituir "expedientes" por "actuaciones" donde se hable de lo que preparamos. Añadir tras los estados: "Son los estados de la **fase 1**; los de las fases 2–4 (expediente, GA, CN, registro) no están documentados." Añadir el contenido de la cabecera común y el concepto de grupo de actuaciones y expediente oficial (remitir a `10` §2–3). |
| §1.2 | Añadir los perfiles de usuario (Firma / Modificación / Consulta) y la frase: "El certificado de usuario firma peticiones API; el de representante firma actos administrativos y es siempre humano. La automatización termina en `COMPLETA`." |
| §1.3 | Anotar en la fila "Sep 2026": *previsto; a 18/09/2026 no recibido* (fuente: página MITECO consultada ese día). |
| §1.4 | Añadir punto 5: "La plataforma comprueba la **presencia** de documentos por tipo; esa comprobación deja de ser diferencial. El diferencial es el cruce de **contenido** (R-CON, R-EVD, R-AMB) y la extracción con evidencia." Punto 6: "La subsanación puede venir de tres actores (verificador, GA, CN); en fases 3A/3B una actuación bloquea el expediente completo." Reescribir el punto 4 con las tres vías de acceso al sandbox (delegado partner; perfil Modificación, no documentado si admite terceros; alegación DT 2ª). |
| §2.1 / §2.2 | Añadir CAE Claro, caes.es, Smart Light, CalculaCAE.ai y CAE Digital al barrido (pendiente de verificar; marcar como tal). |
| §3.1 | "Es exactamente nuestro Sprint 3" → "Es el paso 4 de nuestro Sprint 3; nuestro diferencial frente a Intelligence no es extraer sino cruzar." |
| §3.3 | Separar "sujetos obligados con plataforma propia" de "sujetos obligados como usuarios directos de la oficial (≥ 50 MWh)". |
| §4 | Enlazar la reclamación de CNI con la alegación al art. 20.3 (`00` §5.6). |
| §5 | Añadir hueco 4: "Actuaciones singulares y CVP: fase II de la plataforma (ene–mar 2027); frecuentes en industria; nadie las prepara con trazabilidad." |
| §6 | Añadir: riesgo de contagio (grupo/expediente); capacidad de delegación del partner; Moeve con el dato de acceso directo y la posición fijada el 18/09 (independiente). |
| §7 | Cerrar 1 y 2 como decididas (17–18/09); dejar la 3 abierta; añadir 4: "¿Módulo de singulares/CVP en roadmap?" |
| Pie | "Mantener vivo: actualizar con el diccionario de API, con la respuesta sobre el perfil Modificación y con cada hito de la tramitación del RD 36/2023." |

---

## 10. Fuentes

- `00-instrucciones-de-entrada.md` v1.2 (18/09/2026) — esencia, reglas de oro, glosario, §6.5 y §6.6.
- `claude/10-confrontacion-plataforma-oficial.md` v1.0 (18/09/2026) — mapeo de actores, fases, cabecera, estados, debilidades D1–D15, huecos.
- `06-entorno-tecnologico-y-competitivo.md` v1.0 (17/09/2026) — objeto del análisis.
- `07-backend-y-motor-de-reglas.md` v1.0 (18/09/2026) — base que este documento revisa.
- `claude/poc001/IND240_v1.1.yaml` — 26 reglas, variables, interpretaciones INT-01..07.
- `claude/cae-engine-estado-proyecto.md` — Sprints 1 y 2.
- Presentación "Plataforma electrónica del sistema de CAE" (OMIE/MIBGAS, 30/06/2026) — vía `10`.
- Real Decreto 36/2023; Orden TED/815/2023 (arts. 11, 14.9.j, 17); Reglamento (UE) 2019/1781 — enlaces en `00` §10.
