# CAE Engine — La plataforma oficial (OMIE/MIBGAS) y qué implica para el Engine

**Versión 1.0 · 18/09/2026 · Proyecto CAE (Billy)**

**Fuente analizada:** presentación "Plataforma electrónica del sistema de CAE", jornada informativa MITECO/OMIE/MIBGAS del 30/06/2026, fichero `2026JUNIO_PlataformaSistCAE_OMIE_MIBGAS_SUJETOS 20260630v1.pdf`, publicada en `miteco.gob.es/es/energia/eficiencia/cae/plataformacae.html`.

**Regla de lectura:** este documento describe **solo lo publicado**. Lo que la presentación no dice se marca `NO DOCUMENTADO` y tiene un hueco enumerado en `docs/HUECOS.md` (`TODO(API-xx)`). Las hipótesis se marcan como tales. Nada de lo que aquí figura como `NO DOCUMENTADO` puede convertirse en un campo, un estado o un valor en el código.

**Origen:** consolida el antiguo `10-confrontacion-plataforma-oficial` (v1.0, 18/09/2026) y el §1 del antiguo `06-entorno-tecnologico-y-competitivo` (v1.0, 17/09/2026), ambos en `docs/historico/`. Las debilidades D1–D15 y las acciones derivadas de aquel análisis viven en `docs/06-plan-de-construccion.md`; los huecos documentales, en `docs/HUECOS.md`. Aquí queda la **referencia única** sobre cómo tramita la plataforma y qué obliga a nuestro modelo.

**Cuándo leerlo:** antes de tocar el modelo canónico (`engine/modelo/`), la máquina de estados (`engine/estados.py`), la salida (`salida/`) o cualquier `mapping/`. Se cambia solo con fuente oficial nueva.

---

## 0. Resumen ejecutivo

1. **La arquitectura encaja.** API JSON con peticiones firmadas, manifiesto de ficheros con hash, notificaciones y tareas pendientes consultables por API, inalterabilidad tras la firma. El diseño de salida de `docs/03` es compatible sin cambios de fondo.
2. **La unidad de trabajo es la `Actuacion`.** Lo que la documentación antigua llamaba "expediente" es la actuación de la plataforma. El `Expediente` oficial es una agregación posterior de actuaciones `VERIFICADA_FAVORABLE` con misma CCAA + año + sector + verificador. El modelo canónico tiene tres entidades: `Actuacion`, `GrupoActuaciones` y `Expediente` (`docs/00` §4, `docs/03`).
3. **Los 8 estados de actuación son solo la fase 1** (actuación → verificación). Los estados de las fases 2–4 (presentación, validación técnica del gestor autonómico, revisión formal del Coordinador Nacional, registro) existen pero **no están enumerados** en la presentación: se modelan con nombres provisionales, marcados `NO OFICIAL` (`TODO(API-03)`).
4. **La firma es un acto administrativo humano con certificado de representante** (FNMT), distinto del certificado de usuario que firma las peticiones API. La automatización termina en `COMPLETA`; "firma y cierre" es humano. Nuestra salida se divide en `constructor/` (payload), `transporte/` (certificado de usuario) y un paso de firma que **no es software nuestro**.
5. **El formulario de cabecera pide datos que la ficha IND240 no captura**: precio del contrato de cesión, inversión realizada, costes operativos anuales, tipología de empresa, partícipe en subvención (valor), partícipe en subasta, código identificativo propio. Sin ellos no hay payload completo. Se resuelven con una spec transversal de cabecera (`spec/propuestas/cabecera_v1.yaml`, pendiente de aprobación).
6. **Existe una vía operativa posible para el "colaborador sin firma"**: la plataforma prevé usuarios con perfil *Modificación* creados por el usuario con poder de Firma de cada agente. **Hipótesis a verificar**: si un delegado partner puede dar de alta a personal o a un sistema nuestro con ese perfil, tendríamos de facto lo que pedimos en la alegación al art. 20.3 sin esperar al RD modificado (`TODO(API-09)`).
7. **Calendario:** la entrega de los modelos de intercambio estaba prevista para septiembre de 2026; a 18/09/2026 no hay diccionario público. Pruebas con entidades en octubre–noviembre. Sin acceso acreditado (delegado partner u otra vía) no hay sandbox. Es el riesgo más urgente del plan (`docs/06`).

---

## 1. Qué es la plataforma y calendario publicado

MITECO ha encomendado a **OMIE y MIBGAS** el desarrollo, implantación y gestión de la plataforma electrónica del Sistema de CAE (art. 20 del RD 36/2023). Dominio: `registrocae.es`. Contacto técnico: `consultas-plataforma@registrocae.es`.

### 1.1 Qué hará

- Gestión de actuaciones de ahorro, expedientes de solicitud, registro, transmisión y liquidación de CAE, más consulta voluntaria previa (CVP) de actuaciones singulares.
- Actuaciones estandarizadas mediante **formulario de cabecera + formulario específico según la ficha**, con **fichas con verificación del cálculo** y validación automática de la información tratable y de la documentación presentada.
- Perfiles diferenciados: sujetos obligados y delegados, verificadores, gestores autonómicos, Coordinador Nacional y ENAC (solo consulta).
- Estados de actuación propios (los 8 de §5.1).
- Inalterabilidad de la información una vez firmada por el sujeto.

### 1.2 Cómo será la API

- Acceso por navegación web **o por herramientas API**.
- **Peticiones firmadas con certificado digital**; validación de esquema, firma, certificado y permisos antes de aceptar la información.
- **Adjuntos con manifiesto de ficheros y hash**, carga asíncrona y validación de integridad.
- Consulta por API del estado de expedientes, actuaciones y CAE, del registro, transmisiones y liquidaciones.
- **Notificaciones y tareas pendientes** también consultables por API.
- Se entregará diccionario de endpoints, estructuras **JSON**, autenticación y ejemplos, más **entorno de pruebas** para validar la integración. A 18/09/2026: no recibido (`TODO(API-01)`).
- Certificados: de usuario, emitidos por el gestor de la plataforma; de representante de persona jurídica y de empleado público, emitidos por entidad autorizada (p. ej. FNMT). Ver §6.2.

### 1.3 Calendario publicado

| Fecha | Hito | Situación a 18/09/2026 |
|---|---|---|
| Sep 2026 | Plataforma de pruebas y entrega de los modelos de intercambio a las entidades | **Previsto; a 18/09/2026 no recibido** (página MITECO consultada ese día) |
| Oct–Nov 2026 | Sesiones de prueba con las entidades, **incluidas conexiones API** | Pendiente |
| Dic 2026 | Alta de usuarios y entidades en producción, carga de históricos, puesta en producción | Pendiente |
| Ene–Mar 2027 | Resto de funcionalidades (consulta voluntaria previa, información pública) — "fase II" | Pendiente |

---

## 2. Actores, perfiles de usuario y certificados

### 2.1 Actores de la plataforma y dónde encajan en nuestro modelo

| Actor plataforma | Perfil / capacidades (según presentación) | Dónde encaja en nuestro modelo | Situación |
|---|---|---|---|
| Gestor de la plataforma (OMIE/MIBGAS) | Alta de agentes, emisión de certificados de usuario, soporte técnico | Interlocutor para modelos de intercambio (`consultas-plataforma@registrocae.es`) | Mapeado |
| Sujeto delegado | Contratos de delegación, actuaciones, expedientes, solicitud, transmisión, liquidación | **Nuestro cliente/partner** (`Tenant` de tipo `delegado`). Firma con certificado de representante; sus usuarios operan la API | Mapeado (`docs/00`) |
| Sujeto obligado (≥ 50 MWh de obligación) | Igual que el delegado, más liquidación propia | Cliente alternativo (`Tenant` de tipo `obligado_directo`). Un sujeto obligado puede operar directamente sin delegado | Contemplado en el modelo; posición comercial en `docs/07` |
| Propietario inicial | Solo aparece en la Consulta Voluntaria Previa (singulares) | Nuestro "titular" (`propietario_inicial`). No tiene acceso a la plataforma para estandarizadas | Coherente |
| Verificador | Acepta la solicitud, verifica **fuera de la plataforma**, sube informe PDF + dictamen electrónico, emite requerimientos de rectificación por actuación | Entidad `Verificador` del modelo canónico (`NUEVO`); origen del estado `PDTE_RECTIFICACION_VER` que interpreta A9 | Modelado en `docs/03` |
| Gestor autonómico (GA) | Validación técnica del expediente, requerimientos de subsanación (bloquean todo el expediente), informe de validación | Fase 3A; origen `GA` de la subsanación (§4.4, §6.2) | Modelado como estado provisional |
| Coordinador nacional (CN) | Revisión formal / certificación, resolución, registro, cancelación, CVP, liquidación; expedientes que exceden una CCAA | Fases 3B–4; origen `CN` de la subsanación | Modelado como estado provisional |
| ENAC | Solo consulta | Irrelevante para el motor | — |
| **Colaborador / agregador técnico** (nuestra figura) | **No existe** en la presentación | Alegación al art. 20.3 (`docs/00`). Ver §7: perfil *Modificación* como vía operativa | Hipótesis |

### 2.2 Perfiles de usuario dentro de cada agente

Tres perfiles: **Firma**, **Modificación** y **Consulta**. El usuario Responsable (con poder de Firma) da de alta, baja y renueva al resto de usuarios de su agente. Los certificados de usuario los emite el gestor de la plataforma.

`NO DOCUMENTADO`: si un usuario de Modificación puede ser una persona ajena a la plantilla del agente o una cuenta de sistema, y si su certificado puede usarse desde infraestructura de un tercero (`TODO(API-09)`).

### 2.3 Certificados: tres tipos

| Tipo | Emisor | Uso | Implicación para nosotros |
|---|---|---|---|
| Certificado de usuario (Consulta / Modificación / Firma) | Gestor de la plataforma | Acceso web y **firma de peticiones API** | Es lo que `salida/transporte/` necesita. Reside en el tenant o, si prospera la hipótesis de §7, en nuestro usuario de Modificación |
| Certificado de representante de persona jurídica | Entidad autorizada (FNMT) | Actos administrativos: alta de entidad, firma de solicitud de emisión, liquidación | **Humano.** No lo automatizamos ni lo custodiamos |
| Certificado de empleado público | Entidad autorizada | GA y CN | — |

---

## 3. Fases del procedimiento y encaje con nuestros procesos

La presentación define seis fases. Se confrontan con nuestros procesos P0–P10 (`docs/03`): P0 admisión · P1 ingesta · P2 evidencias · P3 ficha y ámbito · P4 consolidación y cruce · P5 cálculo · P6 pre-revisión · P7 subsanación · P8 empaquetado y envío · P9 seguimiento post-envío · P10 composición de grupos y expedientes.

| Fase oficial | Quién | Qué ocurre | Nuestro proceso | Encaje |
|---|---|---|---|---|
| **1A Creación de actuaciones** | Sujetos | Formulario de cabecera + formulario de detalle según ficha + documentación. Validación automática de lo tratable y de la presencia de documentos. Cálculo del ahorro por la plataforma. Estados `BORRADOR` → `COMPLETA` → firma y cierre | P0–P6 + P8 (construir payload) | Es nuestro núcleo. Requiere la cabecera común (§4) |
| **1B Verificación** | Verificadores | El sujeto elige verificador por actuación o por grupo; requerimientos de rectificación por actuación; informe PDF + dictamen electrónico; dictamen único para grupos | P9 (A9 interpreta rectificaciones) → P7 con `origen=verificador` | Diseñado. Necesita las entidades `Verificador` y `GrupoActuaciones` |
| **2A Presentación del expediente** | Sujetos | Borrador de solicitud → agregación de actuaciones `VERIFICADA_FAVORABLE` con **misma CCAA, año, sector y verificador** → firma y solicitud. Los grupos verificados juntos van en expediente propio | P10 (Expediente Builder, `NUEVO`, Sprint 4; decisión de Billy) | Capacidad nueva |
| **3A Validación técnica** | GA (o CN si el expediente excede una CCAA) | Revisión por actuación; un requerimiento de subsanación **bloquea todo el expediente**; el sujeto puede desistir; aprobación o rechazo en conjunto; informe PDF | P9 → P7 con `origen=GA` sobre todas las actuaciones del expediente | Estados provisionales (§5.2) |
| **3B Revisión formal / certificación** | CN | Segunda ronda de requerimientos posible; dictamen y resolución | P9 → P7 con `origen=CN` | Estados provisionales (§5.2) |
| **4 Registro** | CN (automático) | Inscripción, códigos únicos por CAE, tramos, notificación a sujetos y GA | Cierre de ciclo con etiqueta de resultado | Solo cierre |
| **5–6 Transmisión / liquidación / expiración** | Sujetos, CN | Fuera de nuestro ámbito (roadmap "CAE Supply", `docs/06`) | — | — |

**Consecuencia estructural.** El ciclo que asumía la documentación antigua era lineal: *expediente → verificador → emisión*. El real es:

```
Actuacion (individual o en GrupoActuaciones)
    → verificación (fase 1B, dictamen por actuación o único por grupo)
    → agregación en Expediente (fase 2A: misma CCAA + año + sector + verificador)
    → validación técnica GA (3A) → revisión formal CN (3B)
    → registro (4)
```

Tres implicaciones que atraviesan todo el diseño (`docs/03`, `docs/04`):

- La **subsanación puede llegar de tres actores** (verificador, GA, CN) en tres momentos distintos, además de la interna del Engine. P7 lleva `origen ∈ {interno, verificador, GA, CN}`.
- En las fases 3A y 3B **una sola actuación bloquea el expediente entero**, y la aprobación o rechazo es en conjunto. Es el riesgo de contagio: una actuación débil arrastra a las buenas. De ahí las reglas de composición `R-GRP`/`R-EXP` (diseño pendiente de aprobación) y el aviso de contagio del Expediente Builder.
- El **grupo de actuaciones** recibe un dictamen único en 1B y va en expediente propio en 2A. Agrupar es una decisión del tenant con consecuencias; el Engine la informa, no la toma.

---

## 4. Formulario de cabecera, formulario de detalle y documentación

### 4.1 Cabecera: campos publicados vs. nuestro modelo

La cabecera es común a todas las fichas. Confrontación campo a campo con `spec/IND240_v1.1.yaml`:

| Campo de cabecera (plataforma) | Variable nuestra | Fuente documental que tendríamos | Situación |
|---|---|---|---|
| Código identificativo personal (libre, organización interna) | `codigo_identificativo_propio` (= `Actuacion.id`) | — | Encaje directo: clave de reconciliación entre nuestro log y la plataforma |
| Fecha inicio / fin de ejecución | `fecha_inicio_actuacion`, `fecha_fin_actuacion` | Pedido, factura, certificado del instalador | Mapeado (definición art. 14.9.j Orden TED/815/2023) |
| Precio del contrato de cesión de ahorros | — | Convenio CAE (hoy solo se captura el *tipo de contraprestación*) | Falta |
| Inversión realizada | — | Facturas (hoy solo se comprueban los datos mínimos AEAT) | Falta |
| Costes operativos anuales | — | Sin fuente documental clara; previsiblemente declarado | Falta; origen por definir |
| Tipología de empresa (propietario inicial) | — | Declaración responsable o dato declarado | Falta; taxonomía `NO DOCUMENTADO` (`TODO(API-05)`) |
| Localización | Solo vía convenio (UTM, referencia catastral) | Convenio CAE | Parcial: capturar como variable propia; cómo se determina la CCAA `NO DOCUMENTADO` (`TODO(API-07)`) |
| Identificación del propietario inicial | `titular_nif`, `titular_razon_social` | Ficha, factura, declaración, convenio (cruce `R-CON-05`) | Mapeado |
| Partícipe en subvención | DOC-02 declaración responsable de ayudas | Declaración responsable | Mapeado como presencia; hace falta el **valor** |
| Partícipe en subasta | — | Nuevo concepto (subastas del RD modificado) | Falta; semántica `NO DOCUMENTADO` (`TODO(API-06)`) |

### 4.2 Variables de cabecera: fuente documental y tipo de evidencia

Traducción de la tabla anterior al modelo de tres capas (documento → interpretación → cálculo) y al principio "declarado ≠ demostrado". Es la base de la spec transversal `spec/propuestas/cabecera_v1.yaml` (`NUEVO`, pendiente de aprobación de Billy; ver `docs/04`).

| Variable | Fuente documental | Tipo de evidencia | Situación |
|---|---|---|---|
| `codigo_identificativo_propio` | Generado por el Engine (= `Actuacion.id`) | derivado | Encaje directo |
| `fecha_inicio_ejecucion`, `fecha_fin_ejecucion` | Pedido, factura, certificado del instalador (ya existen como `fecha_inicio/fin_actuacion`) | demostrado | `F0` |
| `precio_contrato_cesion` | Convenio CAE | demostrado | `NUEVO`: hoy solo se captura el *tipo de contraprestación* |
| `inversion_realizada` | Facturas (suma de base imponible de líneas elegibles) | derivado | `NUEVO`; criterio de qué líneas suman → `INT-09` (propuesta) |
| `costes_operativos_anuales` | Sin fuente documental clara | declarado | `NUEVO`; semántica `NO DOCUMENTADO` |
| `tipologia_empresa` | Declaración responsable o declarado | declarado | `NUEVO`; taxonomía `NO DOCUMENTADO` → `TODO(API-05)` |
| `localizacion` (UTM, ref. catastral, **CCAA**) | Convenio CAE | demostrado; CCAA derivada de la referencia | `NUEVO` como variable propia: hoy solo se comprueba presencia en el convenio; `TODO(API-07)` |
| `propietario_inicial` (NIF, razón social) | Ficha, factura, declaración, convenio (`R-CON-05`) | demostrado | `F0` |
| `participe_subvencion` (valor, no solo presencia) | Declaración responsable de ayudas | demostrado | Hoy solo presencia (DOC-02); el valor es `NUEVO` |
| `participe_subasta` | Nuevo concepto del RD modificado | declarado | `NUEVO`; semántica `NO DOCUMENTADO` → `TODO(API-06)` |
| `verificador_id`, `sector`, `anio_finalizacion` | Asignación del tenant; ficha; `fecha_fin_ejecucion` | declarado / derivado | `NUEVO`; necesarios para componer expediente (`atributos_agrupacion`) |

Nombres, tipos y unidades **oficiales** de cada campo: `NO DOCUMENTADO` (`TODO(API-08)`). Los nombres de esta tabla son nuestros; el mapeo al oficial vive en `mapping/`, nunca en `engine/`.

### 4.3 Formulario de detalle

"Según el cálculo de la ficha y tipo de ficha": son las variables tratables de la ficha. Para IND240, previsiblemente PM, N1, N2, h y el número de motores. **La plataforma calcula y valida el resultado.** Esto confirma que nuestro cálculo es control cruzado, no producto (§9.1).

`NO DOCUMENTADO`: nombres de campo, unidades y granularidad (¿por motor o agregado?) → `TODO(API-08)`. El modelo canónico prevé `unidades[]` (una por motor, clave de unión nº de serie) precisamente para no cerrar la granularidad antes de tiempo.

### 4.4 Documentación: presencia vs. contenido

La presentación habla de "comprobación de documentación subida según ficha escogida". Lectura razonable: comprobación de **presencia por tipo**, no de contenido. Si la validación comprueba también contenido es `NO DOCUMENTADO` (`TODO(API-04)`); la fase II (ene–mar 2027) podría ampliarla.

Consecuencia: la regla de presencia `R-DOC-01` pierde valor diferencial (se mantiene como control previo, no se vende como diferencial). Lo conservan las reglas que cruzan **contenido** entre documentos (`R-CON-*`), las de evidencia (`R-EVD-*`) y las de ámbito (`R-AMB-*`), y la extracción con cita.

---

## 5. Estados

Cuatro niveles de estado, cuatro cosas distintas (`CLAUDE.md` §3, `docs/03`). Aquí solo los dos que fija la plataforma; el veredicto y el estado de ciclo son nuestros y están en `docs/03`.

### 5.1 Estado de plataforma — actuación (fase 1): 8 estados confirmados

Confirmados literalmente en la presentación (pág. 26). La plataforma los fija; nosotros solo los reflejamos.

| Estado | Fase | Quién lo provoca |
|---|---|---|
| `BORRADOR` | 1A | Sujeto (creación; carga de cabecera, detalle y documentos) |
| `COMPLETA` | 1A | Plataforma (validación automática superada). **Fin de la automatización** |
| `ENVIADA_A_VERIFICACION` | 1A → 1B | Sujeto (firma y cierre; envío al verificador elegido) |
| `PDTE_RECTIFICACION_VER` | 1B | Verificador (requerimiento de rectificación por actuación) |
| `VERIFICACION_EN_PROCESO` | 1B | Verificador (solicitud aceptada) |
| `VERIFICADA_FAVORABLE` | 1B | Verificador (dictamen favorable). Única entrada a un `Expediente` |
| `VERIFICADA_DESFAVORABLE` | 1B | Verificador (dictamen desfavorable) |
| `NO_PUEDE_EMITIR_DICTAMEN` | 1B | Verificador |

`NO DOCUMENTADO`: las transiciones exactas entre estados y sus condiciones (la presentación enumera los estados, no el grafo). Un `GrupoActuaciones` comparte estos 8 estados con dictamen único.

### 5.2 Estado de plataforma — expediente (fases 2–4): provisionales, NO OFICIAL

Existen (presentado, en validación técnica, requerido, desistido, validado, en revisión formal, resuelto, inscrito…) pero la presentación **no los enumera**. Se modelan con **nombres nuestros**, marcados `NO OFICIAL`, hasta que llegue el diccionario (`TODO(API-03)`):

```
BORRADOR_SOLICITUD → PRESENTADO → EN_VALIDACION_TECNICA ─┬─► REQUERIDO_GA ──► (subsanado | DESISTIDO)
                                                          └─► VALIDADO_GA → EN_REVISION_FORMAL ─┬─► REQUERIDO_CN ──► (subsanado | DESISTIDO)
                                                                                                 ├─► RESUELTO_FAVORABLE → INSCRITO
                                                                                                 └─► RESUELTO_DESFAVORABLE
```

Regla: cada uno de estos nombres lleva en el código la marca `# TODO(API-03): ver docs/HUECOS.md`. Ningún test asume que la plataforma devuelve estos literales; el simulador los reproduce **como provisionales**.

### 5.3 Estado de CAE

`vigente`, `expirado`, `liquidado` (pág. 36). Solo relevante si entra el roadmap "CAE Supply" (`docs/06`). La regla de expiración que aplica la plataforma es "3 años desde el **año** de finalización, con vencimiento el 31/12 del último año"; su traslado a `R-TMP-03` es el objeto de `INT-08` (`spec/propuestas/IND240_v1.2.diff.md`, no aprobado).

### 5.4 Inalterabilidad

"Inalterabilidad de la información revisada una vez firmada por el sujeto." Coherente con nuestro log de eventos solo-añadir (`docs/03`). Implicación: tras la firma, **solo el sujeto modifica y solo vía requerimiento oficial**. Cualquier corrección interna posterior a `EN_PLATAFORMA` se rechaza (evento `CorreccionRechazadaPostFirma`); P7 post-firma pasa obligatoriamente por el flujo de rectificación o subsanación oficial.

### 5.5 Desistimiento

El sujeto puede desistir durante un requerimiento (fases 3A y 3B). Se modela como transición `DESISTIDO` del expediente (provisional) y evento `DesistimientoRegistrado` de actor humano; en el ciclo, `CERRADA(resultado=desistida)`.

### 5.6 Cómo se refleja el estado de plataforma en nuestro ciclo

El estado de plataforma nunca se fija desde nuestro código: llega por API (o por el simulador) como evento `EstadoPlataformaRecibido` y **proyecta** una transición del estado de ciclo. Las reglas de proyección están en `docs/03`; las que se derivan directamente de lo publicado son estas:

| Estado de plataforma recibido | Efecto sobre el ciclo (`docs/03`) | Origen de la subsanación |
|---|---|---|
| `BORRADOR`, `COMPLETA` | `ENTREGADA(API)`; sigue siendo modificable por nosotros | — |
| `ENVIADA_A_VERIFICACION` | Requiere evento previo `FirmaRegistrada` (actor humano) → `EN_PLATAFORMA`. Desde aquí, inalterabilidad | — |
| `PDTE_RECTIFICACION_VER` | `PENDIENTE_SUBSANACION` de la actuación (o del grupo, por dictamen único) | `verificador` |
| `VERIFICADA_FAVORABLE` | Candidata a `Expediente`; P10 puede proponer agrupación | — |
| `VERIFICADA_DESFAVORABLE`, `NO_PUEDE_EMITIR_DICTAMEN` | `CERRADA` con etiqueta de resultado; el reintento es una actuación nueva o la vía que fije la plataforma (`NO DOCUMENTADO`) | — |
| `REQUERIDO_GA`, `REQUERIDO_CN` (provisionales) | `PENDIENTE_SUBSANACION` en **todas** las actuaciones del expediente, con `afectada_directamente: bool` | `GA` / `CN` |
| `DESISTIDO` (provisional) | `CERRADA(resultado=desistida)` | — |
| `INSCRITO` (provisional) | `CERRADA(resultado=inscrita)`; si entra CAE Supply, comienza el seguimiento del estado de CAE (§5.3) | — |

Si la plataforma devuelve un literal que no está en esta tabla, el evento se registra igual (nunca se descarta) y la actuación pasa a `EN_REVISION_HUMANA`: un estado desconocido es un hueco nuevo en `docs/HUECOS.md`, no un error silencioso.

---

## 6. API e integración

### 6.1 Encaje técnico

| Elemento de la plataforma | Nuestra pieza (`docs/03`) | Encaje |
|---|---|---|
| Peticiones JSON firmadas con certificado; validación de esquema, firma, certificado y permisos | `salida/api_oficial/` + `salida/simulador/` | Diseñado; sin diccionario (`TODO(API-01)`) |
| Adjuntos con manifiesto de ficheros + hash, carga asíncrona, validación de integridad | N5 integridad + manifiesto interno | Concepto idéntico. Prerrequisito: SHA-256 de **todos** los ficheros en ingesta (regla de implementación de `CLAUDE.md`). Formato oficial del manifiesto `NO DOCUMENTADO` (`TODO(API-02)`) |
| Consulta de estado de actuaciones, expedientes, CAE, registro | `consultar_estado(ref)` del puerto | Encaja |
| Notificaciones y tareas pendientes por API | `consultar_tareas(tenant)`; evento `EstadoPlataformaRecibido` / `TareaPendienteRecibida` en P9 | Encaja. Las tareas pendientes son la cola de trabajo del tenant: se consumen y se priorizan en la consola (S4) |
| Diccionario de endpoints, JSON, autenticación, ejemplos; entorno de pruebas | `docs/HUECOS.md` | Pendiente de recepción |
| Códigos identificativos libres | `codigo_identificativo_propio` | Reconciliación log ↔ plataforma |
| Multiselección de actuaciones | Handoff por lotes | No diseñado; útil para tenants con volumen |
| Dashboards por entidad, filtros, descarga | Consola de revisión (S4) | Solapamiento parcial: la plataforma ya da seguimiento; nuestra consola se centra en **lo previo a la firma** (la única excepción es la cola de tareas pendientes) |
| Plazos de requerimientos y contestaciones | Alertas en S4 | Se menciona "seguimiento de plazos" sin cifras: `NO DOCUMENTADO` (`TODO(API-10)`) |

### 6.2 Frontera de automatización y firma

```
[Engine]      documentos → payload cabecera + detalle + manifiesto → BORRADOR → COMPLETA
                                                                              │
[Humano, cert. representante]                                  firma y cierre de actuación
                                                                              │
[Plataforma]  verificación (1B) → expediente (2A) → GA (3A) → CN (3B) → registro (4)
                                                                              │
[Engine]      consume notificaciones y tareas → interpreta requerimientos (A9) → P7 con origen
```

La automatización **termina en `COMPLETA`**. Lo que ocurre entre `COMPLETA` y `ENVIADA_A_VERIFICACION` es un acto humano. Lo que ocurre después lo fija la plataforma y nosotros lo reflejamos.

**Tres certificados: quién firma qué.**

| Acto | Certificado | Quién | Nuestro papel |
|---|---|---|---|
| Petición API (crear borrador, cargar adjuntos, consultar estados y tareas) | De usuario (perfil Modificación o Firma) | Usuario del agente | `salida/transporte/` firma la petición con ese certificado. Dónde vive el componente: decisión de Billy (`TODO(API-09)`) |
| Firma y cierre de actuación, firma de solicitud de emisión, liquidación | De representante de persona jurídica (FNMT) | Persona con poder de representación del sujeto | **Ninguno.** Registramos el evento `FirmaRegistrada` (quién, cuándo); no firmamos ni custodiamos |
| Actos de GA y CN | De empleado público | Administración | Ninguno |

**Regla no negociable:** nunca custodiamos certificados de representante. La firma es un acto humano; ningún componente nuestro firma actos administrativos. No existe `salida/firma/` como código.

---

## 7. La vía del perfil "Modificación" (hipótesis a verificar)

La presentación dice que el usuario con poder de Firma de un agente puede dar de alta usuarios de **Modificación** y de **Consulta**, con certificado de usuario emitido por el gestor de la plataforma, y que las peticiones API se firman con ese certificado.

**Si** el delegado partner puede crear un usuario de Modificación para personal nuestro (o para un sistema nuestro), la figura de "colaborador sin firma" que pedimos en la alegación al art. 20.3 existiría operativamente desde el día 1: preparar y cargar borradores, consultar estados y tareas, sin capacidad de firma ni de solicitud.

**Qué preguntar al gestor de la plataforma** (`consultas-plataforma@registrocae.es`); nada de esto está documentado (`TODO(API-09)`):

1. Si un usuario de Modificación puede ser una persona ajena a la plantilla del agente, o una cuenta de sistema.
2. Si el certificado de usuario puede usarse desde infraestructura de un tercero.
3. Responsabilidad del agente por lo que cargue ese usuario (previsiblemente total).

**Impacto en salida y transporte** (`docs/03`, `salida/`):

| Componente | Qué hace | Dónde vive |
|---|---|---|
| `constructor/` | Payload cabecera + detalle + manifiesto, sin firmar | Nuestro, en nuestra infraestructura. No depende de la respuesta |
| `transporte/` | Firma de peticiones API con certificado de **usuario**; reenvía estados y tareas como eventos | Si el perfil admite terceros: nuestra infraestructura, aislado por tenant. Si no: componente desplegable en casa del tenant |
| Firma | Acto humano con certificado de **representante** | Siempre en casa del tenant. No es software nuestro |

El backend se diseña para las dos respuestas: la interfaz del puerto de salida no cambia; solo cambia dónde se despliega `transporte/`. **Decisión de Billy** tras la respuesta del gestor (`CLAUDE.md` §6).

---

## 8. Lo que encaja bien (no tocar)

- Núcleo determinista + agentes en la periferia: la plataforma valida esquema y calcula; nosotros producimos entradas coherentes y con evidencia.
- Modelo canónico propio + mapeo declarativo por ficha (`mapping/`): absorbe el diccionario cuando llegue sin tocar `engine/`.
- Log de eventos inmutable ↔ inalterabilidad tras firma.
- SHA-256 por fichero ↔ manifiesto con hash de la plataforma.
- P9 por eventos ↔ notificaciones y tareas pendientes por API.
- `codigo_identificativo_propio` ↔ código identificativo libre de la plataforma.
- Vinculación por nº de serie y por hash, no por nombre de fichero: compatible con la carga asíncrona de adjuntos.
- Regla "no custodiar certificados de representante": confirmada por el modelo de tres certificados.

---

## 9. Consecuencias para el producto

1. **El cálculo de la ficha es control cruzado, no producto.** La plataforma calculará y validará lo "tratable". El Calculation Engine (N3) comprueba que lo que vamos a enviar coincide con lo que la plataforma va a calcular y detecta la discrepancia **antes** del envío (evento `DiscrepanciaCalculoPlataforma`; familia `R-XCK`, propuesta que necesita sandbox). El criterio oficial para los casos que nuestras interpretaciones dejan abiertos (PM sin fila exacta en el cuadro 6, acreditación de N2: INT-01..05) es `NO DOCUMENTADO` (`TODO(API-12)`) y se infiere empíricamente con una batería de casos en cuanto haya sandbox.
2. **El diferencial se desplaza aguas arriba.** La plataforma valida formularios ya rellenos; no convierte documentación desordenada en una actuación coherente, ni cruza evidencias entre documentos, ni dice qué falta. Ahí sigue el valor del Engine: ingesta, extracción con cita, consolidación en tres capas, reglas de cruce y veredicto explicable.
3. **El output del Engine es un payload de actuación**, no un informe: cabecera + detalle por ficha + manifiesto de ficheros con hash. El informe markdown/JSON del Engine 0.1 se conserva como vista para el revisor humano; el producto es el paquete que entra en `BORRADOR` y llega a `COMPLETA`. Hasta que exista el diccionario, el paquete se entrega por handoff (carpeta ordenada + manifiesto + informe) y se prueba contra el simulador.
4. **Tres vías de acceso al sandbox, ninguna cerrada.** Al entorno de pruebas solo acceden agentes acreditados con certificado. (a) **Delegado partner** que nos dé acceso bajo su agente: vía directa, depende de cerrar el partner antes de las sesiones de oct–nov. (b) **Perfil Modificación** a nombre nuestro dentro del agente del partner: `NO DOCUMENTADO` si admite terceros (`TODO(API-09)`, §7). (c) **Alegación a la DT 2ª** del proyecto de modificación del RD 36/2023 (sandbox para intermediarios técnicos): depende de la tramitación del RD. Mientras ninguna esté resuelta, se trabaja con handoff y simulador.
5. **Presencia vs. contenido.** La plataforma comprueba la **presencia** de documentos por tipo; esa comprobación deja de ser diferencial (`R-DOC-01` se mantiene como control previo). El diferencial es el cruce de **contenido** (`R-CON`, `R-EVD`, `R-AMB`) y la extracción con evidencia. Si la fase II añadiera validación de contenido, el solapamiento crecería (`TODO(API-04)`); vigilar.
6. **La subsanación viene de tres actores.** Verificador (fase 1B, por actuación o grupo), gestor autonómico (3A) y Coordinador Nacional (3B, posible segunda ronda), además de la interna del Engine. En 3A/3B una actuación bloquea el expediente completo y el sujeto puede desistir. P7 lleva `origen`; A9 interpreta requerimientos firmados con informe PDF y un humano confirma la interpretación; el resultado alimenta el banco de pruebas anonimizado.

Consecuencias secundarias, ya recogidas en `docs/06` y `docs/07`: capacidad máxima de delegación de cada delegado (la presentación menciona su "liberación"; cómo se consulta es `NO DOCUMENTADO`, `TODO(API-11)`); sujetos obligados ≥ 50 MWh como usuarios directos; actuaciones singulares y CVP en fase II.

---

## 10. Fuentes

- Presentación "Plataforma electrónica del sistema de CAE" — OMIE/MIBGAS, jornada informativa MITECO del 30/06/2026. Fichero `2026JUNIO_PlataformaSistCAE_OMIE_MIBGAS_SUJETOS 20260630v1.pdf`. Páginas citadas: 26 (estados de actuación), 36 (estados de CAE).
- Página "Plataforma CAE" de MITECO — `miteco.gob.es/es/energia/eficiencia/cae/plataformacae.html` (consultada el 18/09/2026: modelos de intercambio no publicados).
- `docs/historico/10-confrontacion-plataforma-oficial_v1.0.md` (18/09/2026) — fuente principal de §0, §2–§8.
- `docs/historico/06-entorno-tecnologico-y-competitivo_v1.0.md` §1 (17/09/2026) — fuente de §1 y base de §9.
- `docs/historico/11-backend-funcionalidades-y-motor-de-reglas_v1.0.md` §3.3, §3.6, §3.8, §3.9, §7 y §9 (18/09/2026) — estados provisionales, variables de cabecera, división de la salida, subsanación con tres orígenes, IDs `API-01..API-12`.
- Real Decreto 36/2023 (art. 20); Orden TED/815/2023 (arts. 14.9.j, 17); proyecto de modificación del RD 36/2023 en audiencia pública (`AUDIENCIA E INFORMACIÓN PÚBLICA DEL PROYECTO DE MODIFICACIÓN DEL REAL DECRETO 36_2023 DE 20 DE MARZO.pdf`) — enlaces en `docs/00`.

---

*Mantener vivo: este documento cambia solo con fuente oficial nueva. Actualizar con el diccionario de API (cierra `API-01`, `API-02`, `API-03`, `API-08`), con la respuesta del gestor sobre el perfil Modificación (`API-09`), con cada sesión del sandbox (`API-12`) y con cada hito de la tramitación del RD 36/2023. Cada hueco que se cierre aquí se cierra el mismo día en `docs/HUECOS.md`; cada `NO DOCUMENTADO` que desaparezca de aquí desaparece del código en la misma sesión.*
