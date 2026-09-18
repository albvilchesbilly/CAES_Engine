# CAE Engine — Entorno tecnológico y competitivo

**Versión 1.1 · 18/09/2026 · Proyecto CAE (Billy)**

Documento complementario a `docs/00-instrucciones-de-entrada.md`. Recoge lo que sabemos del ecosistema tecnológico del Sistema CAE: la plataforma oficial vista como mercado, quién tiene producto y quién no, y qué consecuencias tiene todo ello para el diseño del motor. Es contexto de producto; **no se construye sobre él** (`docs/01` §2). El detalle técnico de la plataforma oficial (actores, fases, cabecera común, estados, certificados, frontera de firma, huecos) está consolidado en `docs/02-plataforma-oficial.md` y `docs/HUECOS.md`.

**Cambios en 1.1:** alineación con `docs/02` y `docs/00` v1.2 según el anexo §9 de `docs/historico/11-backend-funcionalidades-y-motor-de-reglas_v1.0.md`. Vocabulario: "actuaciones" para lo que preparamos (antes "expedientes"). §1 acortada a resumen de mercado y remitida a `docs/02`. Añadidos: estados de fase 1 frente a fases 2–4, perfiles de usuario y frontera de firma, hito de septiembre marcado como no recibido, presencia frente a contenido documental, tres orígenes de subsanación, tres vías de acceso al sandbox, cinco competidores pendientes de verificar, sujetos obligados como usuarios directos, hueco de singulares/CVP, riesgo de contagio, capacidad de delegación, dato y posición sobre Moeve, decisiones 1 y 2 cerradas y decisión 4 añadida. Ruta a `00` corregida.

Regla de uso: aquí solo entra lo verificado con fuente y fecha. Lo que no se ha comprobado se marca como **sin evidencia pública** o **pendiente de verificar**, que no significa que no exista.

---

## 1. La plataforma oficial cambia la propuesta de valor (resumen de mercado)

MITECO ha encomendado a **OMIE y MIBGAS** el desarrollo, implantación y gestión de la plataforma electrónica del Sistema de CAE (art. 20 del RD 36/2023). Dominio: `registrocae.es`. Contacto técnico: `consultas-plataforma@registrocae.es`. Fuente: presentación "Plataforma electrónica del sistema de CAE", jornada MITECO/OMIE/MIBGAS del 30/06/2026. El detalle está en `docs/02-plataforma-oficial.md`; aquí solo lo que cambia el mercado.

**Qué hará.** Gestión de **actuaciones** (unidad de trabajo), grupos de actuaciones con dictamen único y **expedientes** oficiales (agregación de actuaciones `VERIFICADA_FAVORABLE` con misma CCAA, año, sector y verificador), más registro, transmisión, liquidación y consulta voluntaria previa de singulares. Las estandarizadas se cargan con **formulario de cabecera común + formulario específico por ficha**, con verificación del cálculo y validación automática de lo tratable y de la **presencia** de documentos por tipo. Los 8 estados de actuación publicados (`BORRADOR` … `NO_PUEDE_EMITIR_DICTAMEN`) son los de la **fase 1**; los de las fases 2–4 (expediente, gestor autonómico, Coordinador Nacional, registro) **no están documentados** (`docs/HUECOS.md` API-03).

**Cómo será el acceso.** Web o **API con peticiones firmadas** (JSON, manifiesto de adjuntos con hash, validación de esquema y permisos), consulta de estados, notificaciones y **tareas pendientes** por API. Perfiles de usuario dentro de cada agente: **Firma / Modificación / Consulta**. El certificado de **usuario** (emitido por el gestor de la plataforma) firma peticiones API; el de **representante** (FNMT) firma actos administrativos y es siempre humano. **La automatización termina en `COMPLETA`.**

**Calendario publicado** (misma presentación):

| Fecha | Hito | Estado a 18/09/2026 |
|---|---|---|
| Sep 2026 | Plataforma de pruebas y entrega de los modelos de intercambio | **Previsto; no recibido.** MITECO indica "en fase de desarrollo"; el único documento técnico sigue siendo la presentación del 30/06 |
| Oct–Nov 2026 | Sesiones de prueba con las entidades, incluidas conexiones API | Previsto |
| Dic 2026 | Alta en producción, carga de históricos, puesta en producción | Previsto |
| Ene–Mar 2027 | Resto de funcionalidades (CVP, información pública) | Previsto (fase II) |

**Consecuencias para el producto.**

1. **El cálculo de la ficha deja de ser diferencial.** La plataforma calcula y valida lo "tratable". Nuestro Calculation Engine pasa a ser **control cruzado**: comprobar antes del envío que lo que enviamos coincide con lo que la plataforma calculará.
2. **El diferencial se desplaza aguas arriba.** La plataforma valida formularios ya rellenos; no convierte documentación desordenada en una actuación coherente ni cruza evidencias entre documentos.
3. **El output del Engine es un payload de actuación**: cabecera + detalle por ficha + manifiesto con hash. El SHA-256 que calculamos encaja.
4. **Ventana de integración limitada y tres vías de acceso al sandbox**: (a) **delegado partner** acreditado, con certificado y **capacidad de delegación disponible**; (b) **perfil Modificación** dado de alta por el delegado para nuestro personal o sistema — `NO DOCUMENTADO` si admite terceros; pregunta enviada al gestor de la plataforma (`docs/HUECOS.md` API-09); (c) **alegación a la DT 2ª** del proyecto de modificación del RD 36/2023 (sandbox para intermediarios técnicos; `docs/00` §5.6). Sin ninguna de las tres no hay pruebas de API en oct–nov 2026.
5. **La comprobación de presencia de documentos no es diferencial** (la plataforma la hace): `R-DOC-01` deja de serlo. El diferencial es el cruce de **contenido** (`R-CON`, `R-EVD`, `R-AMB`) y la extracción con evidencia.
6. **La subsanación puede venir de tres actores** (verificador por actuación; gestor autonómico y Coordinador Nacional por actuación pero **bloqueando el expediente completo** en las fases 3A/3B), y tras la firma solo se modifica vía requerimiento oficial.

---

## 2. Mapa de agentes: quién tiene tecnología

La página de agentes de MITECO (actualizada 22/07/2026) lista **gestores autonómicos** y **~70 sujetos delegados**. No lista verificadores: esos se consultan en el buscador de acreditados de ENAC, filtrando por validación y verificación, sector CAE. La figura de **colaborador técnico** que somos nosotros no existe en la plataforma; es el objeto de la alegación al art. 20.3 (`docs/00` §5.6).

### 2.1 Niveles de madurez digital (barrido parcial: ~12 de 70 verificadas)

| Nivel | Definición | Entidades verificadas |
|---|---|---|
| **A** | Portal propio con simulación, gestión de actuaciones y seguimiento | Bettergy (EnergySequence), Ingeniería Aplicada, AlfaCAE |
| **A-** | Área de cliente sin funcionalidad pública visible | Efficiency Program (CAE Gestión) |
| **B** | Servicio llave en mano sin plataforma pública | Acciona, Greenflex, Effic, DELCAE, Leyton/Caelia, Konery, Premium Energy, Loris ENR |
| **C** | Web corporativa o landing informativa | Mayoría del resto (sin verificar una a una) |
| **D** | Sin web dedicada según MITECO | Regenera Levante, Sacyr Facilities |

**Ningún sujeto delegado publica API.** Es el dato más accionable del benchmark.

**Pendiente de verificar** (citados en `docs/00` §7 o pedidos por Billy el 18/09/2026; no analizados uno a uno; no se afirma nada sobre ellos hasta que se verifiquen):

| Entidad | Lo que se sabe | Qué verificar |
|---|---|---|
| CAE Claro | Software CAE; competidor del segmento en que se mueve CAE Check | Fichas, funcionalidad, precios, si es delegado |
| caes.es | Citado en `docs/00` §7 | Qué es, quién opera, si tiene producto |
| Smart Light | Citado en `docs/00` §7 | Idem |
| CalculaCAE.ai | Preparación de expedientes de **transporte** para delegados con datos de la DGT: mismo modelo que el nuestro en otro sector | Alcance, delegados clientes; afecta a la decisión sobre TRA050 como segunda ficha |
| CAE Digital | Captación B2C; **se presenta como sujeto delegado pero no figura con ese nombre en la lista oficial** | Aclarar su figura antes de cualquier trato |

### 2.2 Fichas destacadas

- **Bettergy** — el delegado más tecnológico y con la alianza más relevante. Plataforma **EnergySequence**: simulación, resultados en kWh y equivalencia financiera, gestión de actuaciones, seguimiento y gestión documental, con "retención del integrador" para el técnico que genera el CAE. Convenio **CGCOII + Moeve + Bettergy (17/10/2025)**: los ingenieros colegiados depositan actuaciones precursoras de CAE y Moeve las adquiere. Además, plataforma con **CONAIF** (72 asociaciones) en la que **Junkers Bosch** ha integrado su catálogo para que el instalador calcule ahorros.
- **Ingeniería Aplicada** — plataforma propia: estado de la actuación en tiempo real, subida de documentación, firma electrónica de convenios y declaraciones, gestión multi-actuación.
- **AlfaCAE** (filial de AlphaCEE, Francia) — plataforma unificada con módulo de gestión de riesgos, red de colaboración y herramientas de seguimiento y reporte. Foco industrial y terciario vía instaladores.
- **Premium Energy Iberia** — filial de grupo francés; modelo de renovación financiada (asume parte del coste vía CAE). Web WordPress de dos páginas, sin área privada ni simulador. Alianza con ANESE. Nivel B.
- **Clúster francés en España** — AlfaCAE, Hellio, Eco Environnement, Loris ENR, Premium Energy, Alphacee: replican el modelo CEE francés. Solo AlfaCAE trajo plataforma.

Los cinco competidores de la tabla "pendiente de verificar" se incorporarán aquí cuando se hayan revisado con la misma profundidad.

### 2.3 Lo que el mapa dice para el producto

| Nivel | Qué son para nosotros | Cómo se les habla |
|---|---|---|
| A / A- | Tienen portal propio; no necesitan marca blanca. Posibles integradores del motor detrás de su portal, o competidores si añaden cruce de evidencias | Solo con datos: precisión y trazabilidad medidas (`docs/05` §7), nunca con "CAE garantizado" |
| B | Llave en mano sin plataforma: preparan actuaciones a mano con técnicos caros | Horas sustituidas y % que pasa la primera revisión (`docs/00` §1) |
| C / D | ~55 entidades sin capa de producto | Motor de prevalidación en marca blanca (B2B2B); candidatos a delegado partner si tienen certificado y capacidad |
| Verificadores (ENAC) | No son clientes ni competidores; su criterio es el que cierra INT-01/03/04/05 | Sesión técnica, no comercial (`docs/06`) |
| Sujetos obligados directos (≥ 50 MWh) | Perfil de cliente propio: operan sin delegado | Pendiente de la posición comercial (§6, Moeve) |

Ninguna entidad se contacta desde este documento: la lista de candidatos, el orden y el seguimiento están en `docs/08-clientes-y-primeros-contactos.md`.

---

## 3. Competencia real: no son los delegados

### 3.1 Competidor directo — CertificAhorro (`certificahorro.es`)

SaaS operado por **HM Capital** (Francia). Es el competidor más cercano al CAE Engine.

- 117 fichas integradas, workflow guiado en 10 etapas (borrador → liquidación).
- Generación de documentación reglamentaria, formulario S1 y **ZIP con nomenclatura MITECO**.
- **Firma electrónica eIDAS** con audit trail y hash SHA-256.
- **"Intelligence"**: sube una factura o ficha técnica y extrae parámetros para pre-rellenar la actuación. Es el **paso 4 de nuestro Sprint 3** (extractor LLM tras modelo canónico, salida y seguimiento; `docs/06`). **Nuestro diferencial frente a Intelligence no es extraer sino cruzar**: consistencia entre documentos (`R-CON`), evidencia temporal (`R-EVD`) y ámbito (`R-AMB`), con cita por dato.
- Validaciones de control: acto de compromiso anterior al inicio de obras, formato CUPS, umbral de 30 MWh en tiempo real.
- Asistente conversacional y actuaciones singulares (Cap. V Orden TED/815/2023).
- **API v1 y webhooks** solo en el plan Delegado.
- Precios publicados: 49 € / 149 € / 399 € / 899 € al mes (sin IVA). Mercado secundario en beta con comisión desde 0,15 %.
- Tiene **calculadora pública de IND240**: compite en nuestra ficha de referencia.
- Sus cifras de conformidad ("99,3 % sobre 156 puntos de control") son **autodeclaradas**, sin auditoría independiente publicada.

Comparación punto a punto (lo de CertificAhorro, según su web a 17/09/2026; lo nuestro, según `docs/03`, `docs/04` y `docs/06`):

| Aspecto | CertificAhorro | CAE Engine |
|---|---|---|
| Ángulo | Tramitación guiada de principio a fin | Prevalidación por cruce de evidencias, aguas arriba del delegado |
| Fichas | 117 integradas | 1 activa (IND240) como configuración YAML; el marco es lo que se prueba, no el número |
| Extracción de documentos | "Intelligence" pre-rellena desde factura o ficha técnica | Extractor por reglas (Fase 0) + LLM (Sprint 3, paso 4); cada valor con documento, página, texto literal y confianza |
| Cruce entre documentos | No publicado | `R-CON` (PM, N1, N2, nº de serie, titular, nº de motores), `R-EVD` (registro ≥ 30 días, huella, N2 demostrado), `R-AMB` (ámbito, motor existente, régimen previo) |
| Conflicto entre fuentes | No publicado | El motor se detiene: `valor_consumido = null`, dos evidencias |
| Cálculo | Calculadora pública de IND240 | Determinista con `Decimal`, fórmula leída del YAML, traza, control cruzado con la plataforma |
| Firma | eIDAS integrada con audit trail | Nunca; la firma es humana con certificado de representante en casa del delegado |
| Salida | ZIP con nomenclatura MITECO, formulario S1 | Payload de actuación (cabecera + detalle + manifiesto) y handoff; conector API cuando exista diccionario |
| API para el cliente | v1 y webhooks en plan Delegado | Puerto de salida hacia la plataforma oficial; API propia no decidida |
| Singulares | Sí (Cap. V Orden TED/815/2023) | Roadmap (decisión 4, §7) |
| Cliente objetivo | Delegados y gestores, todos los sectores | Delegados sin producto e industria; sin ser delegado |
| Precio | 49–899 €/mes publicados | No definido |

Lo que no sabemos de CertificAhorro y hay que verificar antes de usarlo en un argumento comercial: si "Intelligence" cruza fuentes o solo pre-rellena; si detecta declarado frente a demostrado; qué hace ante una contradicción; si prepara el registro ≥ 30 días de IND240.

### 3.2 Fabricantes: canal instalador, foco aerotermia residencial

Plataformas gratuitas para el instalador, con cálculo estimado del incentivo, verificación de elegibilidad, seguimiento y cobro por el cliente final:

- **Mitsubishi Electric** con Novawatt · **Hisense** (`cae.hisense.com`) · **Panasonic** · **Ferroli** (calculadora online) · **Daikin** (simulador) · **Bosch** vía CONAIF-Bettergy.

Impulsadas por el **RD-ley 7/2026**, que incluye plan de impulso de la bomba de calor con incentivos CAE y coeficientes de corrección específicos.

### 3.3 Sujetos obligados

Hay que distinguir dos situaciones que antes aparecían mezcladas:

**Sujetos obligados con plataforma propia** (herramienta para su canal de instaladores y clientes):

- **Feníe Energía / Fenie** — plataforma de tramitación para instalador y cliente final con cálculo de ahorro estimado, seguimiento y almacén documental. Peculiaridad valiosa: el instalador debe **homologarse** con formación y test antes de recibir credenciales. Modelo replicable como filtro de calidad de la actuación.
- **Iberdrola** — cita **NZE Manager** como herramienta digital del proceso.

**Sujetos obligados como usuarios directos de la plataforma oficial**: los que tienen obligación **≥ 50 MWh** operan directamente en ella (crean actuaciones, presentan expedientes, liquidan) sin pasar por un delegado (`docs/00` §7; `docs/02`). Son un **perfil de cliente distinto** del delegado: tenant "sujeto obligado directo" en `docs/03` (seguridad y tenencia). Moeve entra en esta categoría (§6).

### 3.4 Fabricantes como generadores de evidencia (no como competencia)

**Schneider Electric** tiene canal CAE específico para variadores (nuestra ficha IND240): registrador integrado en variadores **Altivar Process** sin cableado ni programación adicional, **generador de informe de uso en Excel**, videotutorial de registro, calculadora de ahorro/bonificación/retorno y guía con enlaces a las fichas.

Esto es literalmente nuestra evidencia **EVD-01** (registro ≥ 30 días) y toca el punto abierto **INT-05** (qué es un "registro inalterable"). Acción: soportar ese formato de exportación en `engine/registro_xlsx.py` y tratar a los fabricantes de variadores como **fuente de evidencia y canal**, no como rivales. Es también la tercera fuente de verdad del banco de pruebas (`docs/05` §5: documentos reales públicos).

---

### 3.5 Solapamiento funcional con la plataforma oficial: qué es diferencial

Es la pregunta que hará cualquier delegado o inversor. Consolida `docs/02` (lo que la plataforma hace) y `docs/03`/`docs/04` (lo que hacemos nosotros). Solo entra lo que la presentación del 30/06/2026 documenta; lo demás es hueco (`docs/HUECOS.md`).

| Función | Plataforma oficial | CAE Engine | ¿Diferencial? |
|---|---|---|---|
| Formulario de cabecera y de detalle por ficha | Lo define y lo valida | Lo rellenamos desde documentos, con cita por dato | Sí: el origen del dato, no el formulario |
| Cálculo de la ficha | Lo hace ("fichas con verificación del cálculo") | Lo hacemos de forma determinista **antes** del envío | Solo como control cruzado |
| Presencia de documentos por tipo | La comprueba | `R-DOC-01` | **No** |
| Contenido y coherencia entre documentos (PM en cuatro fuentes, nº de serie, titular, fechas) | No documentado (`API-04`) | `R-CON-*`, `R-EVD-*`, `R-AMB-*` | **Sí**, mientras API-04 no diga lo contrario |
| Declarado frente a demostrado (N2 con registro ≥ 30 días) | No documentado | `R-EVD-04`, tres capas por dato | Sí |
| Decir qué falta y pedirlo al cliente | No | Bucle de subsanación interna (P7) | Sí |
| Manifiesto de adjuntos con hash | Lo exige | Lo producimos (SHA-256 en ingesta) | No; es requisito de entrada |
| Firma y presentación | Certificado de representante; humano | Nunca; registramos `FirmaRegistrada` | No aplica |
| Estados de actuación (fase 1) | Los fija | Los reflejamos | No |
| Tareas pendientes y notificaciones por API | Las expone | Las leemos como **cola de trabajo** del delegado y las priorizamos (P9; `docs/03`) | Sí, como producto sobre la API |
| Composición de expedientes (CCAA + año + sector + verificador) y riesgo de contagio | Agrega; no avisa (no documentado) | Expediente Builder: lotes válidos, actuaciones huérfanas, aviso de contagio (Sprint 4) | Sí |
| Singulares y CVP | Fase II (ene–mar 2027) | Roadmap (decisión 4, §7) | Por decidir |

Lectura: nuestro producto vive en las filas marcadas "Sí". Cualquier funcionalidad que la plataforma incorpore en fase II en una de esas filas se revisa aquí y en `docs/06` en la misma sesión.

---

## 4. Referencias de mercado actualizadas

- Aportación al FNEE: **~189 €/MWh**. Actúa como **techo económico**: ningún sujeto obligado compra por encima (fuente: OCU).
- Remuneración media de las solicitudes concedidas: **~130 €/MWh** (dato MITECO citado en la nota del convenio CGCOII-Moeve-Bettergy, 17/10/2025).
- Ofertas observadas a propietarios iniciales: **100–140 €/MWh**.
- Volumen del sistema: **~4.500 GWh** solicitados a certificar desde su puesta en marcha (MITECO, citado en la misma nota).
- Orden de magnitud de una actuación IND240 tipo (caso A del banco de pruebas, `docs/05` §2: un motor de 110 kW, 305.829 kWh/año): valor bruto orientativo de **30,6–42,8 k€** a 100–140 €/MWh. Lo que recibe el propietario inicial es menos, una vez descontadas las comisiones del delegado y del canal. Sirve para dimensionar el argumento "una actuación mal preparada que vuelve del verificador cuesta más que el software", no como precio.
- Los instaladores (**CNI**) reclaman públicamente, a 17/09/2026, que la futura plataforma permita también la colaboración del instalador y que se consulte a las organizaciones del sector antes de cambios técnicos en las fichas. Es la misma necesidad que recoge nuestra **alegación al art. 20.3** del proyecto de modificación del RD 36/2023 (figura de colaborador técnico; `docs/00` §5.6): la reclamación de CNI da contexto sectorial a "ningún delegado publica API".

---

## 5. Huecos de mercado identificados

1. **Industrial sin plataforma.** Toda la ola de producto va a aerotermia residencial (fabricantes de climatización). Nadie ha montado plataforma para fichas industriales. Es donde vive IND240 y donde tenemos ventaja.
2. **~55 delegados sin capa de producto.** Candidatos a motor de prevalidación en marca blanca (B2B2B), sin que nosotros tengamos que ser sujeto delegado.
3. **Nadie ocupa la prevalidación previa al verificador** salvo CertificAhorro, y este lo hace desde el ángulo de la tramitación, no del cruce de evidencias.
4. **Actuaciones singulares y Consulta Voluntaria Previa.** Fase II de la plataforma (ene–mar 2027); frecuentes en industria; nadie las prepara con trazabilidad (justificación técnica vinculada a la CVP). Roadmap, decisión abierta 4 (§7).

---

## 6. Riesgos y puntos abiertos que añade este documento

- **Moeve.** Ya tiene jugada en CAE (plataforma de Bettergy + captación vía CGCOII). Además, como sujeto obligado con obligación ≥ 50 MWh, **opera directamente en la plataforma oficial**: es comprador natural de CAE y usuario directo, sin necesidad de delegado. Puede ser aliado, cliente directo o conflicto de interés. **Posición fijada por Billy el 18/09/2026: CAE Engine es independiente; no se piensa solo para Moeve.** El orden de contactos comerciales sigue abierto (`docs/08`).
- **Acceso al sandbox.** Tres vías (§1, punto 4); ninguna cerrada a 18/09/2026. Sin una de ellas no hay pruebas de API en oct–nov 2026.
- **Capacidad de delegación del partner.** La plataforma controla la capacidad máxima de delegación de cada delegado y la libera al liquidar. Un partner sin capacidad disponible limita nuestro volumen: es criterio de selección (`docs/HUECOS.md` API-11 sobre cómo se consulta).
- **Riesgo de contagio.** Un grupo de actuaciones recibe **dictamen único**; un requerimiento del gestor autonómico o del Coordinador Nacional **bloquea el expediente completo**. Una actuación débil arrastra a las buenas. Es un riesgo de producto, no solo de backend: regla de negocio para el delegado (no agrupar `SUBSANABLE` con `PREVALIDADO`) y justificación del Expediente Builder (`docs/06`, Sprint 4).
- **Benchmark incompleto.** Verificadas ~12 de 70 entidades; cinco competidores de software pendientes (§2.1). Pendiente barrido sistemático.
- **Riesgo de solapamiento.** La plataforma ya comprueba la presencia de documentos. Si en fase II incorpora validación de **contenido** más allá de lo tratable, parte de nuestras reglas documentales perderían valor (`docs/HUECOS.md` API-04). Vigilar las funcionalidades de ene–mar 2027.

Resumen operativo:

| Riesgo | Qué lo dispara | Qué hacemos mientras tanto | Quién decide |
|---|---|---|---|
| Moeve como aliado / cliente / conflicto | Cualquier contacto comercial con Moeve, Bettergy o CGCOII | Producto independiente; tenant "sujeto obligado directo" previsto en `docs/03` | Billy (orden de contactos, `docs/08`) |
| Sin acceso al sandbox en oct–nov 2026 | Ninguna de las tres vías cerrada antes de las sesiones | Simulador de la plataforma con solo lo documentado (`docs/03`, `salida/simulador/`) | Billy (partner), gestor de la plataforma (API-09), tramitación del RD (DT 2ª) |
| Partner sin capacidad de delegación | Selección de partner sin ese criterio | Criterio en la lista de `docs/08`; atributo `capacidad_disponible` en el tenant | Billy |
| Contagio en grupo / expediente | Agrupar actuaciones `SUBSANABLE` con `PREVALIDADO`; requerimiento de GA o CN | Regla de negocio + Expediente Builder (Sprint 4) | Billy (Sprint 4 sí / posponer) |
| Benchmark incompleto | Argumento comercial apoyado en una entidad no verificada | Tabla "pendiente de verificar"; nada sube a §2.2 sin fuente y fecha | — |
| Solapamiento con fase II | Publicación de funcionalidades de ene–mar 2027 | Revisar §3.5 y `docs/06` en la misma sesión; `R-DOC-01` ya marcada como no diferencial | — |
| Modelos de intercambio que no llegan | Septiembre cerrado sin diccionario | `docs/HUECOS.md` API-01..12; conector vacío; mapping declarativo | Billy (correo al gestor) |

---

## 7. Decisiones abiertas para el usuario

| # | Decisión | Estado |
|---|---|---|
| 1 | ¿Priorizar la integración con la API oficial en el Sprint 3, por delante del extractor LLM, dada la ventana de pruebas oct–nov 2026? | **Decidida (17/09/2026):** Sprint 3 orientado a la integración; el extractor LLM es el paso 4 (`docs/06`) |
| 2 | ¿Buscar delegado partner para el sandbox? ¿De qué perfil? | **Decidida (18/09/2026):** búsqueda en curso, con el criterio añadido de **capacidad de delegación disponible**; perfil y candidato siguen en manos de Billy (`docs/08`) |
| 3 | ¿Añadir una ficha residencial/terciaria al roadmap para no quedar fuera del segmento donde se mueve el canal, o doblar la apuesta por industrial, donde nadie compite? | **Abierta.** Se cruza con la elección de segunda ficha (vecina industrial vs. frío; `CLAUDE.md` §6) y con lo que se verifique de CalculaCAE.ai para transporte |
| 4 | ¿Módulo de actuaciones singulares / CVP en el roadmap? | **Abierta.** Fase II de la plataforma (ene–mar 2027); frecuente en industria (§5, hueco 4) |

---

## 8. Fuentes

- Agentes del Sistema de CAE — `miteco.gob.es/es/energia/eficiencia/cae/agentes.html` (listado de sujetos delegados actualizado 22/07/2026; consultado 18/09/2026)
- Plataforma CAE — `miteco.gob.es/es/energia/eficiencia/cae/plataformacae.html` (consultada 18/09/2026: "en fase de desarrollo") y presentación de la jornada informativa OMIE/MIBGAS del 30/06/2026
- `docs/02-plataforma-oficial.md` y `docs/HUECOS.md` — detalle técnico de la plataforma y huecos API-01..12
- `docs/00-instrucciones-de-entrada.md` v1.2 — §5.6 (alegaciones al proyecto de RD: art. 20.3 y DT 2ª), §8 (Moeve, capacidad de delegación)
- `docs/historico/11-backend-funcionalidades-y-motor-de-reglas_v1.0.md` §1.2, §1.3 y anexo §9 — desalineaciones D6–D14 y mejoras M1–M6 aplicadas en esta versión
- `docs/08-clientes-y-primeros-contactos.md` §9 — CalculaCAE.ai y CAE Digital como herramientas a vigilar
- CertificAhorro — `certificahorro.es` (consultado 17/09/2026)
- Convenio CGCOII–Moeve–Bettergy (17/10/2025) — notas de prensa sectoriales; webinar Bettergy para el COII
- Schneider Electric — landing CAE para variadores de frecuencia y blog corporativo (07/05/2025, sobre la revisión de IND240 v1.1)
- Hisense, Mitsubishi Electric/Novawatt, Panasonic, Ferroli — notas de prensa sectoriales 2026
- Feníe Energía / Fenie — `fenieenergia.es` y comunicados de la federación
- OCU — nota sobre CAE y precios de mercado
- Proyecto de modificación del RD 36/2023 (audiencia e información pública) — texto en el proyecto Claude

---

*Mantener vivo: actualizar con el diccionario de API, con la respuesta sobre el perfil Modificación (API-09) y con cada hito de la tramitación del proyecto de modificación del RD 36/2023. Cada entidad de la tabla "pendiente de verificar" sube a §2.2 solo con fuente y fecha.*

