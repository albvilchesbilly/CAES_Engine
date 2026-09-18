> **SUPERADO.** Documento histórico (v1.0, 17/09/2026). Sustituido por `docs/07-entorno-y-competencia.md` v1.1, que aplica el anexo §9 de `11` (alineación con la plataforma oficial). Se conserva como fuente. No construir sobre él.

# CAE Engine — Entorno tecnológico y competitivo

**Versión 1.0 · 17/09/2026 · Proyecto CAE (Billy)**

Documento complementario a `claude/00-instrucciones-de-entrada.md`. Recoge lo que sabemos
del ecosistema tecnológico del Sistema CAE: la plataforma oficial y su API, quién tiene
producto y quién no, y qué consecuencias tiene todo ello para el diseño del motor.

Regla de uso: aquí solo entra lo verificado con fuente y fecha. Lo que no se ha comprobado
se marca como **sin evidencia pública**, que no significa que no exista.

---

## 1. La plataforma oficial cambia la propuesta de valor

MITECO ha encomendado a **OMIE y MIBGAS** el desarrollo, implantación y gestión de la
plataforma electrónica del Sistema de CAE (art. 20 del RD 36/2023). Dominio: `registrocae.es`.
Contacto técnico: `consultas-plataforma@registrocae.es`.

### 1.1 Qué hará la plataforma

- Gestión de actuaciones de ahorro, expedientes de solicitud, registro, transmisión y
  liquidación de CAE, más consulta voluntaria previa de actuaciones singulares.
- Actuaciones estandarizadas mediante **formulario de cabecera + formulario específico según
  la ficha**, con **fichas con verificación del cálculo** y validación automática de la
  información tratable y de la documentación presentada.
- Perfiles diferenciados: sujetos obligados y delegados, verificadores, gestores autonómicos,
  Coordinador Nacional y ENAC (solo consulta).
- Estados de actuación propios: `BORRADOR`, `COMPLETA`, `ENVIADA_A_VERIFICACION`,
  `PDTE_RECTIFICACION_VER`, `VERIFICACION_EN_PROCESO`, `VERIFICADA_FAVORABLE`,
  `VERIFICADA_DESFAVORABLE`, `NO_PUEDE_EMITIR_DICTAMEN`.
- Inalterabilidad de la información una vez firmada por el sujeto.

### 1.2 Cómo será la API (lo más relevante para nosotros)

- Acceso por navegación web **o por herramientas API**.
- **Peticiones firmadas con certificado digital**; validación de esquema, firma, certificado
  y permisos antes de aceptar la información.
- **Adjuntos con manifiesto de ficheros y hash**, con carga asíncrona y validación de
  integridad.
- Consulta por API del estado de expedientes, actuaciones y CAE, del registro, transmisiones
  y liquidaciones.
- **Notificaciones y tareas pendientes** también consultables por API.
- Se entregará diccionario de endpoints, estructuras **JSON**, autenticación y ejemplos, más
  **entorno de pruebas** para validar la integración.
- Certificados: de usuario emitidos por el gestor de la plataforma, y de representante de
  persona jurídica / empleado público emitidos por entidad autorizada (p. ej. FNMT).

### 1.3 Calendario publicado

| Fecha | Hito |
|---|---|
| Sep 2026 | Plataforma de pruebas y entrega de los modelos de intercambio a las entidades |
| Oct–Nov 2026 | Sesiones de prueba con las entidades, **incluidas conexiones API** |
| Dic 2026 | Alta de usuarios y entidades en producción, carga de históricos, puesta en producción |
| Ene–Mar 2027 | Resto de funcionalidades (consulta voluntaria previa, información pública) |

Fuente: presentación "Plataforma electrónica del sistema de CAE", jornada informativa
MITECO/OMIE/MIBGAS del 30/06/2026, publicada en
`miteco.gob.es/es/energia/eficiencia/cae/plataformacae.html`.

### 1.4 Consecuencias para el producto (importante)

1. **El cálculo de la ficha deja de ser diferencial.** La plataforma oficial calculará y
   validará lo "tratable". Nuestro Calculation Engine pasa de ser el producto a ser el
   **control cruzado**: comprobar que lo que vamos a enviar coincide con lo que la
   plataforma va a calcular, y detectar la discrepancia antes del envío.
2. **El diferencial se desplaza aguas arriba.** La plataforma valida formularios ya
   rellenos; no convierte documentación desordenada en expediente coherente, ni cruza
   evidencias entre documentos, ni dice qué falta. Ahí sigue el valor del Engine.
3. **El output del Engine debe evolucionar** de informe (markdown/JSON) a **payload de
   actuación**: cabecera + detalle por ficha + manifiesto de ficheros con hash. El SHA-256
   que ya calculamos encaja con el esquema de adjuntos previsto.
4. **Ventana de integración limitada.** Al sandbox solo acceden agentes acreditados con
   certificado digital: sin un sujeto delegado partner no hay pruebas en oct–nov 2026.

---

## 2. Mapa de agentes: quién tiene tecnología

La página de agentes de MITECO (actualizada 22/07/2026) lista **gestores autonómicos** y
**~70 sujetos delegados**. No lista verificadores: esos se consultan en el buscador de
acreditados de ENAC, filtrando por validación y verificación, sector CAE.

### 2.1 Niveles de madurez digital (barrido parcial: ~12 de 70 verificadas)

| Nivel | Definición | Entidades verificadas |
|---|---|---|
| **A** | Portal propio con simulación, gestión de expedientes y seguimiento | Bettergy (EnergySequence), Ingeniería Aplicada, AlfaCAE |
| **A-** | Área de cliente sin funcionalidad pública visible | Efficiency Program (CAE Gestión) |
| **B** | Servicio llave en mano sin plataforma pública | Acciona, Greenflex, Effic, DELCAE, Leyton/Caelia, Konery, Premium Energy, Loris ENR |
| **C** | Web corporativa o landing informativa | Mayoría del resto (sin verificar una a una) |
| **D** | Sin web dedicada según MITECO | Regenera Levante, Sacyr Facilities |

**Ningún sujeto delegado publica API.** Es el dato más accionable del benchmark.

### 2.2 Fichas destacadas

- **Bettergy** — el delegado más tecnológico y con la alianza más relevante. Plataforma
  **EnergySequence**: simulación, resultados en kWh y equivalencia financiera, gestión de
  expedientes, seguimiento y gestión documental, con "retención del integrador" para el
  técnico que genera el CAE. Convenio **CGCOII + Moeve + Bettergy (17/10/2025)**: los
  ingenieros colegiados depositan actuaciones precursoras de CAE y Moeve las adquiere.
  Además, plataforma con **CONAIF** (72 asociaciones) en la que **Junkers Bosch** ha
  integrado su catálogo para que el instalador calcule ahorros.
- **Ingeniería Aplicada** — plataforma propia: estado del expediente en tiempo real, subida
  de documentación, firma electrónica de convenios y declaraciones, gestión multi-actuación.
- **AlfaCAE** (filial de AlphaCEE, Francia) — plataforma unificada con módulo de gestión de
  riesgos, red de colaboración y herramientas de seguimiento y reporte. Foco industrial y
  terciario vía instaladores.
- **Premium Energy Iberia** — filial de grupo francés; modelo de renovación financiada
  (asume parte del coste vía CAE). Web WordPress de dos páginas, sin área privada ni
  simulador. Alianza con ANESE. Nivel B.
- **Clúster francés en España** — AlfaCAE, Hellio, Eco Environnement, Loris ENR, Premium
  Energy, Alphacee: replican el modelo CEE francés. Solo AlfaCAE trajo plataforma.

---

## 3. Competencia real: no son los delegados

### 3.1 Competidor directo — CertificAhorro (`certificahorro.es`)

SaaS operado por **HM Capital** (Francia). Es el competidor más cercano al CAE Engine.

- 117 fichas integradas, workflow guiado en 10 etapas (borrador → liquidación).
- Generación de documentación reglamentaria, formulario S1 y **ZIP con nomenclatura MITECO**.
- **Firma electrónica eIDAS** con audit trail y hash SHA-256.
- **"Intelligence"**: sube una factura o ficha técnica y extrae parámetros para pre-rellenar
  el expediente. Es exactamente nuestro Sprint 3.
- Validaciones de control: acto de compromiso anterior al inicio de obras, formato CUPS,
  umbral de 30 MWh en tiempo real.
- Asistente conversacional y actuaciones singulares (Cap. V Orden TED/815/2023).
- **API v1 y webhooks** solo en el plan Delegado.
- Precios publicados: 49 € / 149 € / 399 € / 899 € al mes (sin IVA). Mercado secundario en
  beta con comisión desde 0,15 %.
- Tiene **calculadora pública de IND240**: compite en nuestra ficha de referencia.
- Sus cifras de conformidad ("99,3 % sobre 156 puntos de control") son **autodeclaradas**,
  sin auditoría independiente publicada.

### 3.2 Fabricantes: canal instalador, foco aerotermia residencial

Plataformas gratuitas para el instalador, con cálculo estimado del incentivo, verificación
de elegibilidad, seguimiento y cobro por el cliente final:

- **Mitsubishi Electric** con Novawatt · **Hisense** (`cae.hisense.com`) · **Panasonic** ·
  **Ferroli** (calculadora online) · **Daikin** (simulador) · **Bosch** vía CONAIF-Bettergy.

Impulsadas por el **RD-ley 7/2026**, que incluye plan de impulso de la bomba de calor con
incentivos CAE y coeficientes de corrección específicos.

### 3.3 Sujetos obligados con plataforma

- **Feníe Energía / Fenie** — plataforma de tramitación para instalador y cliente final con
  cálculo de ahorro estimado, seguimiento y almacén documental. Peculiaridad valiosa: el
  instalador debe **homologarse** con formación y test antes de recibir credenciales.
  Modelo replicable como filtro de calidad del expediente.
- **Iberdrola** — cita **NZE Manager** como herramienta digital del proceso.

### 3.4 Fabricantes como generadores de evidencia (no como competencia)

**Schneider Electric** tiene canal CAE específico para variadores (nuestra ficha IND240):
registrador integrado en variadores **Altivar Process** sin cableado ni programación
adicional, **generador de informe de uso en Excel**, videotutorial de registro, calculadora
de ahorro/bonificación/retorno y guía con enlaces a las fichas.

Esto es literalmente nuestra evidencia **EVD-01** (registro ≥ 30 días) y toca el punto
abierto **INT-05** (qué es un "registro inalterable"). Acción sugerida: soportar ese formato
de exportación en `engine/registro_xlsx.py` y tratar a los fabricantes de variadores como
**fuente de evidencia y canal**, no como rivales.

---

## 4. Referencias de mercado actualizadas

- Aportación al FNEE: **~189 €/MWh**. Actúa como **techo económico**: ningún sujeto obligado
  compra por encima (fuente: OCU).
- Remuneración media de las solicitudes concedidas: **~130 €/MWh** (dato MITECO citado en la
  nota del convenio CGCOII-Moeve-Bettergy, 17/10/2025).
- Ofertas observadas a propietarios iniciales: **100–140 €/MWh**.
- Volumen del sistema: **~4.500 GWh** solicitados a certificar desde su puesta en marcha
  (MITECO, citado en la misma nota).
- Los instaladores (**CNI**) reclaman públicamente, a 17/09/2026, que la futura plataforma
  permita también la colaboración del instalador y que se consulte a las organizaciones del
  sector antes de cambios técnicos en las fichas.

---

## 5. Huecos de mercado identificados

1. **Industrial sin plataforma.** Toda la ola de producto va a aerotermia residencial
   (fabricantes de climatización). Nadie ha montado plataforma para fichas industriales.
   Es donde vive IND240 y donde tenemos ventaja.
2. **~55 delegados sin capa de producto.** Candidatos a motor de prevalidación en marca
   blanca (B2B2B), sin que nosotros tengamos que ser sujeto delegado.
3. **Nadie ocupa la prevalidación previa al verificador** salvo CertificAhorro, y este lo
   hace desde el ángulo de la tramitación, no del cruce de evidencias.

---

## 6. Riesgos y puntos abiertos que añade este documento

- **Moeve ya tiene jugada en CAE** (plataforma de Bettergy + captación vía CGCOII). El punto
  "aclarar posición de Moeve" deja de ser teórico: hay proveedor y canal establecidos.
  Decisión pendiente del usuario sobre cómo navegarlo.
- **Acceso al sandbox**: sin delegado partner acreditado no hay pruebas de API en oct–nov 2026.
- **Benchmark incompleto**: verificadas ~12 de 70 entidades. Pendiente barrido sistemático.
- **Riesgo de solapamiento**: si la plataforma oficial incorpora validación documental más
  allá de lo "tratable", parte de nuestras reglas documentales perderían valor. Vigilar las
  funcionalidades de fase II (ene–mar 2027).

---

## 7. Decisiones abiertas para el usuario

1. ¿Priorizar la integración con la API oficial en el Sprint 3, por delante del extractor
   LLM, dado que la ventana de pruebas es oct–nov 2026?
2. ¿Buscar delegado partner para el sandbox? ¿De qué perfil: industrial sin plataforma o
   volumen residencial?
3. ¿Añadir una ficha residencial/terciaria al roadmap para no quedar fuera del segmento
   donde se mueve el canal, o doblar la apuesta por industrial, donde nadie compite?

---

## 8. Fuentes

- Agentes del Sistema de CAE — `miteco.gob.es/es/energia/eficiencia/cae/agentes.html` (listado
  de sujetos delegados actualizado 22/07/2026)
- Plataforma CAE — `miteco.gob.es/es/energia/eficiencia/cae/plataformacae.html` y presentación
  de la jornada informativa OMIE/MIBGAS del 30/06/2026
- CertificAhorro — `certificahorro.es` (consultado 17/09/2026)
- Convenio CGCOII–Moeve–Bettergy (17/10/2025) — notas de prensa sectoriales; webinar Bettergy
  para el COII
- Schneider Electric — landing CAE para variadores de frecuencia y blog corporativo (07/05/2025,
  sobre la revisión de IND240 v1.1)
- Hisense, Mitsubishi Electric/Novawatt, Panasonic, Ferroli — notas de prensa sectoriales 2026
- Feníe Energía / Fenie — `fenieenergia.es` y comunicados de la federación
- OCU — nota sobre CAE y precios de mercado
