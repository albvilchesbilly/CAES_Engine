> **CONSOLIDADO.** Documento histórico (v1.0, 18/09/2026). En la consolidación del 18/09/2026 su contenido pasó a `docs/02-plataforma-oficial.md` (actores, fases, cabecera, estados, API, perfil Modificación, lo que encaja) y a `docs/HUECOS.md` (§10). Sus debilidades D1–D15 y acciones ya están recogidas en `docs/06-plan-de-construccion.md`. Se conserva como fuente. No construir sobre él.

# CAE Engine — Confrontación con la Plataforma oficial (OMIE/MIBGAS, junio 2026)

**Versión 1.0 · 18/09/2026 · Proyecto CAE (Billy)**

Fuente analizada: presentación "Plataforma electrónica del sistema de CAE" (OMIE/MIBGAS, junio 2026, fichero `2026JUNIO_PlataformaSistCAE_OMIE_MIBGAS_SUJETOS 20260630v1.pdf`). Se confronta con `00` (esencia y reglas de oro), `06` (entorno), `07` (backend) y `spec/IND240_v1.1.yaml`.

Regla de lectura: lo que la presentación no dice se marca como **no documentado**. Las hipótesis se marcan como tales.

---

## 0. Resumen ejecutivo

1. **La arquitectura encaja** (API JSON firmada, manifiesto con hash, notificaciones y tareas por API, inalterabilidad tras firma). Lo que diseñamos en `07` §9 es compatible sin cambios de fondo.
2. **La unidad de trabajo no encaja.** Nuestro "expediente" es la **actuación** de la plataforma. El expediente oficial es una agregación posterior de actuaciones ya verificadas favorablemente, agrupadas por CCAA + año + sector + verificador. Hay que renombrar el modelo canónico y añadir dos entidades: *Grupo de actuaciones* y *Expediente*.
3. **Los 8 estados que espejamos son solo la fase 1** (actuación → verificación). Los estados de las fases 2–4 (presentación, validación técnica GA, revisión formal CN, registro) no están enumerados en la presentación. `N6` está incompleta.
4. **La firma es un acto administrativo con certificado de representante (FNMT)**, distinto del certificado de usuario para la API. La automatización termina en `COMPLETA`; "firma y cierre" es humano. Nuestro componente "firmante en casa del delegado" debe rediseñarse en dos: transporte API (cert. usuario) y firma (cert. representante, humano).
5. **El formulario de cabecera pide datos que no capturamos**: precio del contrato de cesión, inversión realizada, costes operativos anuales, tipología de empresa, partícipe en subvención, partícipe en subasta, código identificativo propio. Sin ellos no hay payload completo.
6. **Aparece una vía operativa para el "colaborador"**: la plataforma prevé usuarios con perfil *Modificación* (sin firma) creados por el usuario con poder de Firma del agente. **Hipótesis a verificar**: si el delegado partner puede dar de alta a nuestro personal como usuario de Modificación, tendríamos de facto lo que pedimos en la alegación al art. 20.3, sin esperar al RD.
7. **Calendario**: la entrega de modelos de intercambio estaba prevista para septiembre 2026; a 18/09 no hay diccionario público. Pruebas con entidades en oct–nov. Sin delegado partner con certificado no hay sandbox. Es el riesgo más urgente.

---

## 1. Actores y perfiles: mapeo

| Actor plataforma | Perfil / capacidades (según presentación) | Dónde encaja en nuestro modelo | Estado |
|---|---|---|---|
| Gestor de la plataforma (OMIE/MIBGAS) | Alta de agentes, emisión de certificados de usuario, soporte técnico | Interlocutor para modelos de intercambio (`consultas-plataforma@registrocae.es`) | ✅ mapeado |
| Sujeto delegado | Contratos de delegación, actuaciones, expedientes, solicitud, transmisión, liquidación | **Nuestro cliente/partner**. Firma con cert. representante; sus usuarios operan la API | ✅ mapeado (`00` §5.1) |
| Sujeto obligado (≥ 50 MWh de obligación) | Igual que el delegado, más liquidación propia | Cliente alternativo. **Moeve** entra aquí: podría operar directamente sin delegado | ⚠️ no explorado |
| Propietario inicial | Solo aparece en Consulta Voluntaria Previa (singulares) | Nuestro "titular". No tiene acceso a la plataforma para estandarizadas | ✅ coherente |
| Verificador | Acepta solicitud, verifica **fuera de la plataforma**, sube informe PDF + dictamen electrónico, emite requerimientos de rectificación por actuación | Fuente de `PDTE_RECTIFICACION_VER` que interpreta A9. **No es entidad en nuestro modelo canónico** | ❌ falta |
| Gestor autonómico | Validación técnica del expediente, requerimientos de subsanación (bloquean todo el expediente), informe de validación | Fase 3A: no modelada en N6 | ❌ falta |
| Coordinador nacional | Revisión formal / certificación, resolución, registro, cancelación, CVP, liquidación; expedientes que exceden una CCAA | Fase 3B–4: no modelada en N6 | ❌ falta |
| ENAC | Solo consulta | Irrelevante para el motor | — |
| **Colaborador / agregador técnico** (nuestra figura) | **No existe** en la presentación | Alegación al art. 20.3 (`00` §5.6). Ver §6 de este documento: perfil *Modificación* como vía operativa | ⚠️ hipótesis |

**Perfiles de usuario dentro de cada agente**: Firma · Modificación · Consulta. El usuario Responsable (poder de Firma) da de alta, baja y renueva al resto. Certificados de usuario emitidos por el gestor de la plataforma.

**Certificados** (tres tipos, según presentación):

| Tipo | Emisor | Uso | Implicación para nosotros |
|---|---|---|---|
| Certificado de usuario (Consulta / Modificación / Firma) | Gestor de la plataforma | Acceso web y **firma de peticiones API** | Es lo que el transporte API necesita. Reside en el delegado o, si prospera la hipótesis del §6, en nuestro usuario de Modificación |
| Certificado de representante de persona jurídica | Entidad autorizada (FNMT) | Actos administrativos: alta de entidad, firma de solicitud de emisión, liquidación | **Humano.** No lo automatizamos ni lo custodiamos |
| Certificado de empleado público | Entidad autorizada | GA y CN | — |

---

## 2. Procesos: mapeo fase a fase

La presentación define 6 fases. Se confronta con nuestros procesos P0–P9 de `07` §3.

| Fase oficial | Quién | Qué ocurre | Nuestro proceso | Grado de encaje |
|---|---|---|---|---|
| **1A Creación de actuaciones** | Sujetos | Formulario cabecera + formulario de detalle según ficha + documentación. Validación automática de lo tratable y de la presencia de documentos. Cálculo del ahorro por la plataforma. Estados `BORRADOR` → `COMPLETA` → firma y cierre | P0–P6 + P8 (construir payload) | ✅ Es nuestro núcleo. Faltan campos de cabecera (§3) |
| **1B Verificación** | Verificadores | Sujeto elige verificador por actuación o grupo; requerimientos de rectificación por actuación; informe PDF + dictamen electrónico; único para grupos | P9 (A9 interpreta rectificaciones) → P7 | ✅ diseñado. ❌ falta entidad *Verificador* y *Grupo* |
| **2A Presentación del expediente** | Sujetos | Borrador de solicitud → agregación de actuaciones `VERIFICADA_FAVORABLE` con **misma CCAA, año, sector y verificador** → firma y solicitud. Grupos verificados juntos van en expediente propio | **No existe** | ❌ nueva capacidad: *Expediente Builder* |
| **3A Validación técnica** | GA (o CN si excede CCAA) | Revisión por actuación; requerimiento de subsanación **bloquea todo el expediente**; el sujeto puede desistir; aprobación/rechazo en conjunto; informe PDF | No modelado | ❌ N6 incompleta |
| **3B Revisión formal / certificación** | CN | Segunda ronda de requerimientos posible; dictamen y resolución | No modelado | ❌ N6 incompleta |
| **4 Registro** | CN (automático) | Inscripción, códigos únicos por CAE, tramos, notificación a sujetos y GA | Cierre con etiqueta de resultado | ⚠️ solo cierre |
| **5–6 Transmisión / liquidación / expiración** | Sujetos, CN | Fuera de nuestro ámbito | — | Ver §7 (CAE Supply) |

**Consecuencia estructural.** Nuestro modelo asume un ciclo lineal *expediente → verificador → emisión*. El real es: **actuación (individual o en grupo) → verificación → agregación en expediente → doble validación administrativa (GA, CN) → registro**. La subsanación puede llegar de tres actores distintos (verificador, GA, CN) y en tres momentos distintos, y en las fases 3A/3B una sola actuación bloquea el expediente entero.

---

## 3. Datos: formulario de cabecera vs. modelo canónico

La cabecera es común a todas las fichas. Confrontación campo a campo con `spec/IND240_v1.1.yaml`:

| Campo de cabecera (plataforma) | Variable nuestra | Fuente documental que tendríamos | Estado |
|---|---|---|---|
| Código identificativo personal (libre, organización interna) | `expediente_id` | — | ✅ Encaje directo: clave de reconciliación entre nuestro log y la plataforma |
| Fecha inicio / fin de ejecución | `fecha_inicio_actuacion`, `fecha_fin_actuacion` | Pedido, factura, certificado instalador | ✅ mapeado (definición art. 14.9.j) |
| Precio del contrato de cesión de ahorros | — | Convenio CAE (hoy solo capturamos *tipo de contraprestación*) | ❌ falta |
| Inversión realizada | — | Facturas (hoy solo comprobamos datos mínimos AEAT) | ❌ falta |
| Costes operativos anuales | — | Sin fuente documental clara; probablemente declarado | ❌ falta; definir origen |
| Tipología de empresa (propietario inicial) | — | Declaración responsable o dato declarado (PYME / gran empresa, **no documentado** qué taxonomía usa la plataforma) | ❌ falta |
| Localización | Solo vía convenio (UTM, ref. catastral) | Convenio | ⚠️ parcial: capturar como variable propia |
| Identificación del propietario inicial | `titular_nif`, `titular_razon_social` | Ficha, factura, declaración, convenio (cruce R-CON-05) | ✅ mapeado |
| Partícipe en subvención | DOC-02 declaración responsable ayudas | Declaración responsable | ✅ mapeado, pero hoy solo verificamos presencia; hace falta el valor |
| Partícipe en subasta | — | Nuevo concepto (subastas del RD modificado) | ❌ falta; **no documentado** su semántica |

**Formulario de detalle** ("según el cálculo de la ficha y tipo de ficha"): son las variables tratables de la ficha. Para IND240, previsiblemente PM, N1, N2, h y el número de motores. La plataforma calcula y valida el resultado. Esto confirma la decisión de `06` §1.4: **nuestro cálculo es control cruzado, no producto**. Nombres de campo, unidades y granularidad (¿por motor o agregado?) **no documentados** → `TODO(API-xx)`.

**Documentación**: "comprobación de documentación subida según ficha escogida". Lectura razonable: comprobación de **presencia por tipo**, no de contenido. Nuestra R-DOC-01 (presencia) pierde valor diferencial; las reglas de cruce de contenido (R-CON-*), de evidencia (R-EVD-*) y de ámbito (R-AMB-*) lo conservan. Si la fase II añadiera validación de contenido, el solapamiento crecería (riesgo ya anotado en `06` §6).

---

## 4. Estados: lo que espejamos y lo que falta

| Concepto | Lo que tenemos (`07` §5.2) | Lo que dice la presentación | Acción |
|---|---|---|---|
| Estados de actuación fase 1 | 8 estados (`BORRADOR` … `NO_PUEDE_EMITIR_DICTAMEN`) | Confirmados literalmente (pág. 26) | ✅ mantener |
| Estados de expediente (fases 2–4) | Ninguno | Existen (presentado, en validación técnica, requerido, desistido, validado, en revisión formal, resuelto, inscrito…) pero **no enumerados** | ❌ modelar como `TODO(API-xx)` con nombres provisionales marcados como no oficiales |
| Estado de CAE | Ninguno | `vigente`, `expirado`, `liquidado` (pág. 36) | ⚠️ solo si entra CAE Supply |
| Inalterabilidad | Log de eventos solo-añadir | "Inalterabilidad de la información revisada una vez firmada por el sujeto" | ✅ coherente. Implicación: tras la firma, **solo el sujeto modifica y solo vía requerimiento**; nuestro P7 post-firma pasa obligatoriamente por el flujo de rectificación oficial |
| Desistimiento | No existe | El sujeto puede desistir durante un requerimiento (3A, 3B) | ❌ añadir transición `DESISTIDO` |

---

## 5. API e integración: encaje técnico

| Elemento de la plataforma | Nuestra pieza | Encaje |
|---|---|---|
| Peticiones JSON firmadas con certificado; validación de esquema, firma, certificado y permisos | `salida/api_oficial` + simulador | ✅ diseñado; falta diccionario |
| Adjuntos con manifiesto de ficheros + hash, carga asíncrona, validación de integridad | N5 integridad + manifiesto interno (`07` §9.5) | ✅ concepto idéntico. ⚠️ N5 es `PARCIAL` (solo SCADA): extender SHA-256 a **todos** los ficheros es prerequisito |
| Consulta de estado de actuaciones, expedientes, CAE, registro | `consultar_estado()` del puerto | ✅ |
| Notificaciones y tareas pendientes por API | `EstadoPlataformaRecibido` en P9 | ✅ Tareas pendientes = cola de trabajo del delegado; podemos consumirla y priorizarla |
| Diccionario de endpoints, JSON, autenticación, ejemplos; entorno de pruebas | `HUECOS.md` | ⏳ pendiente de recepción |
| Códigos identificativos libres | `expediente_id` | ✅ reconciliación |
| Multiselección de actuaciones | Handoff por lotes | ⚠️ no diseñado; útil para delegados con volumen |
| Dashboards por entidad, filtros, descarga | Consola de revisión (S4) | Solapamiento parcial: la plataforma ya da seguimiento; nuestra consola debe centrarse en **lo previo a la firma** |

**Frontera de automatización (nueva, explícita):**

```
[Engine]  documentos → payload cabecera + detalle + manifiesto → BORRADOR → COMPLETA
                                                                      │
[Humano con cert. representante]                           firma y cierre de actuación
                                                                      │
[Plataforma]                          verificación → expediente → GA → CN → registro
                                                                      │
[Engine]                        consume notificaciones / tareas → interpreta requerimientos (A9)
```

---

## 6. La vía del perfil "Modificación" (hipótesis a verificar)

La presentación dice que el usuario con poder de Firma de un agente puede dar de alta usuarios de **Modificación** y de **Consulta**, con certificado de usuario emitido por el gestor de la plataforma, y que las peticiones API se firman con ese certificado.

**Si** el delegado partner puede crear un usuario de Modificación para personal nuestro (o para un sistema nuestro), la figura de "colaborador sin firma" que pedimos en la alegación al art. 20.3 existiría operativamente desde el día 1: preparar y cargar borradores, consultar estados y tareas, sin capacidad de firma ni de solicitud.

Lo que **no está documentado** y hay que preguntar al gestor de la plataforma:
- Si un usuario de Modificación puede ser una persona ajena a la plantilla del agente (o una cuenta de sistema).
- Si el certificado de usuario puede usarse desde infraestructura de un tercero.
- Responsabilidad del agente por lo que cargue ese usuario (previsiblemente total).

**Impacto en `07` §9.3**: el componente "firmante + transporte en casa del delegado" se divide en (a) **transporte API** con certificado de usuario de Modificación — podría vivir en nuestra infraestructura si la respuesta es afirmativa, con aislamiento por tenant — y (b) **firma** con certificado de representante, siempre humana y en casa del delegado. La regla "nunca custodiar certificados de terceros" se mantiene para (b); para (a) el certificado sería nuestro, emitido a nuestro usuario dentro del agente del delegado. **Decisión de Billy** tras la respuesta del gestor.

---

## 7. Debilidades a replantear (priorizadas)

| # | Debilidad | Impacto | Qué replantear | Prioridad |
|---|---|---|---|---|
| D1 | Modelo canónico llama "expediente" a lo que es una **actuación**; no existen *Grupo de actuaciones* ni *Expediente* oficial | Payload mal estructurado; imposible seguir fases 2–4 | Renombrar N7 a `Actuacion`; añadir `GrupoActuaciones` y `Expediente` (agregación por CCAA + año + sector + verificador) | Alta · Sprint 3 paso 1 |
| D2 | N6 solo cubre fase 1; fases 2–4 sin estados; sin `DESISTIDO` | P9 ciego tras la verificación | Ampliar máquina de estados con estados provisionales marcados no oficiales; cerrar con diccionario | Alta · Sprint 3 paso 1 |
| D3 | Cabecera: faltan precio de cesión, inversión, costes operativos, tipología de empresa, localización propia, partícipe subvención (valor), partícipe subasta | Sin payload completo no hay `COMPLETA` | Añadir variables de cabecera **comunes a todas las fichas** en una spec transversal (`spec/cabecera_v1.yaml`), con fuentes documentales y tipo de evidencia | Alta · Sprint 3 |
| D4 | Verificador no es entidad; no capturamos CCAA ni año de finalización como atributos de agrupación | No podemos proponer al delegado cómo componer expedientes | Nueva capacidad **Expediente Builder**: sugerir lotes válidos y avisar de actuaciones huérfanas (única en su CCAA/año/verificador) | Media · Sprint 4 |
| D5 | Firma tratada como automatizable en `07` §9.3 | Diseño de conector irreal | Separar transporte (cert. usuario) de firma (cert. representante, humano). Ver §6 | Alta · Sprint 3 |
| D6 | R-TMP-03 usa "fin de actuación + 3 años"; la plataforma aplica "3 años desde el **año** de finalización, vencimiento el 31/12 del último año" | Regla de expiración imprecisa | Reescribir como `31/12/(año_fin + n)`; confirmar `n` contra art. 17 Orden TED/815/2023 → nuevo `INT-08` | Media · inmediata (cambio de spec) |
| D7 | Subsanación modelada como un solo bucle con el cliente | Tres actores (verificador, GA, CN), tres momentos; en 3A/3B una actuación bloquea el expediente | P7 con `origen ∈ {interno, verificador, GA, CN}`; A9 debe leer requerimientos firmados con informe PDF | Media · Sprint 3 paso 3 |
| D8 | Riesgo de contagio en grupos: dictamen único; requerimiento bloquea expediente completo | Un expediente débil arrastra a los buenos | Regla de negocio para el delegado: no agrupar actuaciones `SUBSANABLE` con `PREVALIDADO`; aviso en Expediente Builder | Media |
| D9 | N5 integridad solo cubre el registro SCADA | Manifiesto oficial exige hash de **todos** los adjuntos | Extender SHA-256 a todo fichero en ingesta | Alta · Sprint 3 paso 2 |
| D10 | R-DOC-01 (presencia de documentos) duplica lo que hará la plataforma | Pérdida de diferencial; posible falsa sensación de valor | Mantener como control previo, pero **no** venderlo como diferencial; el valor está en R-CON/R-EVD/R-AMB y en la extracción | Baja |
| D11 | Sandbox: modelos de intercambio previstos para sep-2026, no recibidos; pruebas oct–nov; sin delegado partner no hay acceso | Perder la ventana de integración | Enviar hoy petición formal a `consultas-plataforma@registrocae.es`; cerrar delegado partner antes de octubre | **Crítica** · esta semana |
| D12 | INT-01/03/04/05 siguen abiertos; la plataforma implementará su propia lectura al calcular | Discrepancias sistemáticas con el cálculo oficial | El sandbox cierra INT-xx **empíricamente**: diseñar batería de casos para inferir el criterio oficial (p. ej. PM sin fila exacta en cuadro 6) | Alta · en cuanto haya sandbox |
| D13 | Sujetos obligados ≥ 50 MWh operan directamente; Moeve podría ser usuario directo | Cambia el mapa de partners y el conflicto de interés | Reabrir explícitamente la cuestión Moeve (`00` §8) con este dato | Decisión de Billy |
| D14 | "Liberación de capacidad máxima de delegación": los delegados tienen un tope | El partner elegido puede no tener capacidad para nuestro volumen | Añadir capacidad disponible como criterio de selección de partner | Media |
| D15 | Actuaciones singulares y Consulta Voluntaria Previa (fase II, ene–mar 2027) fuera de nuestro alcance; el sector industrial las genera con frecuencia | Roadmap industrial incompleto | Evaluar en Sprint 5 un módulo de preparación de singulares (justificación técnica + vinculación a CVP) | Baja · roadmap |

---

## 8. Lo que encaja bien (no tocar)

- Núcleo determinista + agentes en la periferia: la plataforma valida esquema y calcula; nosotros producimos entradas coherentes y con evidencia.
- Modelo canónico propio + mapeo declarativo por ficha: absorbe el diccionario cuando llegue sin tocar el motor.
- Log de eventos inmutable ↔ inalterabilidad tras firma.
- SHA-256 por fichero ↔ manifiesto con hash de la plataforma.
- P9 por eventos ↔ notificaciones y tareas pendientes por API.
- `expediente_id` ↔ código identificativo libre de la plataforma.
- Vinculación por nº de serie y no por nombre de fichero: compatible con carga asíncrona de adjuntos.
- Regla de oro "no custodiar certificados de representante": confirmada por el modelo de tres certificados.

---

## 9. Acciones propuestas (para decisión de Billy)

| # | Acción | Plazo sugerido | Dependencia |
|---|---|---|---|
| 1 | Correo a `consultas-plataforma@registrocae.es`: solicitar modelos de intercambio, diccionario API y **preguntar por el perfil de Modificación para terceros** (§6) | Esta semana | Ninguna |
| 2 | Cerrar delegado partner con certificado y capacidad de delegación disponible, antes de las sesiones de oct–nov | Antes del 1/10 | Billy |
| 3 | Sprint 3 paso 1 revisado: modelo canónico `Actuacion` + `GrupoActuaciones` + `Expediente`; N6 con fases 2–4 provisionales; `spec/cabecera_v1.yaml` | Sprint 3 | Ninguna |
| 4 | Dividir `salida/firmante/` en `transporte/` (cert. usuario) y `firma/` (humano) | Sprint 3 | Respuesta de la acción 1 |
| 5 | Corregir R-TMP-03 y abrir `INT-08` (regla de expiración) | Inmediato | Confirmar con Orden TED/815/2023 art. 17 |
| 6 | Batería de casos para inferir criterios oficiales (INT-01/02/03/04/05) en cuanto haya sandbox | Oct–nov 2026 | Acciones 1 y 2 |
| 7 | Reabrir posición de Moeve con el dato de acceso directo de sujetos obligados | Decisión | Billy |

---

## 10. Huecos documentales (no inventar)

Lo que la presentación **no** dice y debe quedar como `TODO(API-xx)` en `HUECOS.md`:

- Nombres, tipos y unidades de los campos de cabecera y de detalle por ficha; granularidad por unidad (motor).
- Taxonomía de "tipología de empresa" y semántica de "partícipe en subasta".
- Estados de expediente en fases 2–4 y de la solicitud de certificación.
- Si la validación documental comprueba contenido o solo presencia.
- Formato del manifiesto de ficheros (algoritmo de hash, estructura).
- Si el perfil de Modificación admite terceros y cuentas de sistema.
- Cómo se resuelve PM sin fila exacta en el cuadro 6 y cómo se acredita N2 (nuestros INT-01..05).
- Plazos de requerimientos y contestaciones (se mencionan "seguimiento de plazos" sin cifras).
