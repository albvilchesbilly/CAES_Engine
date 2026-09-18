# CAE Engine — Instrucciones de entrada

**Versión 2.0 · 18/09/2026 · Proyecto CAE (Billy)**

Cambios en 2.0: consolidación documental para el arranque del repositorio en Claude Code. El código del Engine 0.1 no viaja con el repo y se reconstruye (Fase 0). Los detalles de plataforma, arquitectura, reglas y evaluación salen de aquí y pasan a `docs/02`–`docs/05`; este documento queda como esencia, reglas, glosario, modelo de negocio y estado. Renombrado de documentos: ver `docs/01`.
Cambios en 1.2: confrontación con la plataforma oficial OMIE/MIBGAS (unidad de trabajo actuación/grupo/expediente, frontera de firma, vía del perfil Modificación).
Cambios en 1.1: misión, visión y propuesta de valor; posición regulatoria y alegaciones al RD 36/2023.

Este documento es el punto de entrada del proyecto. Sirve para poner al día a una persona que entra y para dar contexto a una sesión de IA que arranca de cero. Si solo se lee un documento, que sea este.

---

## 0. Cómo entrar

**Orden de lectura** (para una sesión de código, `CLAUDE.md` lo repite y lo amplía):

1. Este documento: esencia, reglas de oro, glosario, modelo, estado.
2. `docs/01-estructura-del-repositorio.md`: qué carpeta es qué.
3. `docs/06-plan-de-construccion.md`: en qué fase estamos y qué sigue.
4. `docs/02-plataforma-oficial.md`: cómo tramita de verdad la plataforma oficial.
5. `docs/03-arquitectura-backend.md` y `docs/04-motor-de-reglas-y-specs.md`: cómo se construye.
6. `spec/IND240_v1.1.yaml`: la ficha traducida a configuración; ahí está el detalle real.
7. `docs/decisiones/ADR-001-decisiones-vigentes.md`: lo que ya está decidido.

**Fuentes de verdad, por orden**

| Orden | Fuente | Para qué |
|---|---|---|
| 1 | BOE | Lo vinculante. Ficha, reglamento europeo, RD 36/2023, Orden TED/815/2023. |
| 2 | Plataforma oficial (OMIE/MIBGAS) | Cómo se tramita: procesos, estados, formularios, API. Documentación publicada: presentación 30/06/2026. Lo no publicado se marca **NO DOCUMENTADO**, nunca se supone. |
| 3 | Catálogo MITECO | Recopilación práctica de fichas. Útil, no vinculante. |
| 4 | `spec/*.yaml` activa | Nuestra lectura de la norma, versionada. Si discrepa del BOE, manda el BOE. |
| 5 | `docs/` y `docs/decisiones/` | Lo decidido y lo que ha pasado desde la última sesión. |

**Para arrancar una sesión de trabajo**: "Lee `CLAUDE.md` y `docs/00`, mira `docs/06` y seguimos por donde lo dejamos."

---

## 1. La esencia

Estamos construyendo **la infraestructura que convierte documentación desordenada de una actuación de eficiencia energética en una actuación CAE trazable, calculada de forma determinista y prevalidada**, lista para que un profesional la revise en minutos en lugar de en horas y para que un sujeto delegado la firme y la presente.

El mercado español de CAE ya tiene gestores, marketplaces, software para instaladores y agregadores. Lo que no está resuelto es el cuello de botella real: preparar actuaciones correctas, con evidencia, a escala industrial y sin que cada una consuma horas de un técnico caro.

Por eso el orden es: **primero el motor, después todo lo demás**. Instaladores, financiación, movilidad, agregación y mercado son capas que crecen encima de un motor que funciona, no al revés.

**La métrica que importa** no es usuarios ni actuaciones subidas: es *horas de trabajo especializado sustituidas por minutos de revisión*, y el porcentaje de actuaciones que pasan la primera revisión sin subsanación.

### 1.1 Misión, visión y propuesta de valor

Fijado el 17/09/2026. Si cambia, se cambia aquí primero.

**Misión (qué hacemos hoy)**
Convertir documentación desordenada de una actuación de eficiencia energética en una actuación CAE trazable, calculada de forma determinista y prevalidada, lista para que un profesional la revise en minutos en lugar de en horas.

**Visión (dónde queremos estar)**
Ser la capa de preparación y prevalidación entre quien ejecuta la actuación (instalador, ingeniería, industria) y quien puede solicitar el CAE (sujeto delegado u obligado): el **colaborador técnico** del sistema. Empezando por el sector industrial, donde nadie tiene plataforma, y sin ser nunca sujeto delegado, verificador ni financiera.

**Propuesta de valor (por qué alguien paga)**

| Para quién | Qué obtiene | Cómo se mide |
|---|---|---|
| Sujeto delegado | Actuaciones que llegan coherentes y con evidencia; menos subsanaciones y menos horas de técnico | % de actuaciones que pasan la primera revisión sin subsanación |
| Instalador / ingeniería | Saber qué le falta a una actuación para ser CAE antes de invertir tiempo en tramitarla (CAE Check) | Horas de técnico sustituidas por minutos de revisión |
| Todos | Cada dato con documento, página y confianza; contradicciones que se muestran, no se esconden; cálculo determinista que contrasta con el de la plataforma oficial | Traza de auditoría completa por actuación |

**Matiz importante.** Con la plataforma oficial calculando y validando lo "tratable" de cada ficha, **el cálculo deja de ser el producto y pasa a ser control cruzado**: comprobar antes del envío que lo que enviamos coincide con lo que la plataforma calculará. La propuesta de valor vive aguas arriba: cruce de evidencias entre documentos, detección de lo que falta y payload listo para enviar. La comprobación de **presencia** de documentos tampoco es diferencial (la plataforma la hace); lo es el cruce de **contenido** entre documentos. Ver `docs/02` §9.

---

## 2. Lo que no somos

Decidido y cerrado. Si alguien propone lo contrario, hay que reabrir la decisión explícitamente, no asumirla.

- **No somos sujeto delegado.** Trabajamos con uno como socio.
- **No somos verificador.** La verificación es independiente y acreditada.
- **No somos financiera.** Si hay financiación, la pone un partner.
- **No somos instaladores ni ingeniería de proyecto.**
- **No prometemos la emisión de CAE.** Prevalidamos con trazabilidad.
- **No firmamos ni custodiamos certificados de representante.** La firma de actuaciones y solicitudes es un acto administrativo humano en casa del sujeto.

---

## 3. Reglas de oro

No negociables. Cualquier propuesta que las rompa está mal planteada, por buena que suene.

1. **La IA lee; el motor calcula.** Un modelo de lenguaje nunca ejecuta la fórmula ni decide si una regla se cumple. Interpreta documentos y propone valores.
2. **Todo dato lleva su evidencia**: documento, página, texto literal, método y confianza. Un número sin procedencia no entra en la actuación.
3. **Tres capas por cada dato**: lo que dice el documento → lo que interpreta el sistema → lo que consume el cálculo. Se guardan las tres.
4. **La ficha es configuración, no código.** Añadir una ficha nueva es añadir un YAML, nunca un `if` más.
5. **Dato declarado ≠ dato demostrado.** Lo que alguien afirma y lo que acredita un registro se tratan distinto y se marcan distinto.
6. **Ante un conflicto, el motor se detiene.** Si dos documentos dicen cosas diferentes, no se elige: se muestra la contradicción con las dos evidencias.
7. **Lo que la norma no cierra se marca como interpretación pendiente** (`INT-xx`), con el criterio aplicado, la alternativa y su impacto. Nunca se disimula.
8. **El BOE manda.** El catálogo es una recopilación; nuestra spec es una lectura.
9. **Todo cambio normativo pasa por revisión humana** antes de tocar el motor.
10. **La plataforma oficial es la referencia de tramitación.** Nuestro vocabulario, estados y payload se alinean con los suyos. Lo que la plataforma no ha documentado se deja como hueco explícito (`TODO(API-xx)` en `docs/HUECOS.md`), nunca se rellena con suposiciones.

---

## 4. Glosario mínimo

- **CAE**: certificado que acredita 1 kWh de ahorro de energía final, negociable entre sujetos habilitados. Se emite por el ahorro **anual**.
- **Actuación**: la unidad de trabajo de la plataforma oficial **y de nuestro código** (`Actuacion`). Una intervención concreta (p. ej. uno o varios variadores en la misma actuación) con formulario de cabecera, formulario de detalle según ficha y documentación. La documentación anterior a septiembre de 2026 la llamaba "expediente".
- **Grupo de actuaciones**: varias actuaciones que se verifican juntas, con informe y dictamen únicos, y se presentan en un expediente propio.
- **Expediente (oficial)**: agregación de actuaciones ya verificadas favorablemente con **misma CCAA, año, sector y verificador**, que el sujeto firma y presenta como solicitud de certificación. Se aprueba o rechaza como conjunto. **Nunca se usa esta palabra para la unidad de trabajo.**
- **Actuación estandarizada**: la que encaja en una ficha del catálogo, con método de cálculo y documentación tasados. **Singular**: la que no, y exige justificación técnica propia (y puede pasar por Consulta Voluntaria Previa).
- **Ficha** (p. ej. IND240): define ámbito, exclusiones, fórmula, variables y documentación de una actuación. Tiene versión; la versión importa.
- **Cabecera**: formulario común a todas las fichas en la plataforma (código propio, fechas, precio de cesión, inversión, costes operativos, tipología de empresa, localización, propietario inicial, subvención, subasta). Ver `docs/02` §4.
- **Propietario inicial del ahorro**: quien hace la inversión y puede ceder el ahorro. No tiene acceso a la plataforma para actuaciones estandarizadas.
- **Convenio CAE**: contrato de cesión del ahorro. Debe firmarse antes de solicitar la emisión.
- **Sujeto obligado / delegado**: los únicos que pueden solicitar la emisión de CAE. Los obligados con obligación ≥ 50 MWh operan directamente en la plataforma.
- **Verificador acreditado**: emite el dictamen sin el cual no hay emisión. Lo elige el sujeto por actuación o grupo; verifica fuera de la plataforma y sube informe PDF + dictamen electrónico.
- **Gestor autonómico (GA) / Coordinador nacional (CN)**: validación técnica y revisión formal del expediente, respectivamente. Ambos pueden emitir requerimientos de subsanación que bloquean el expediente completo.
- **Prevalidación**: lo que hacemos nosotros. Preparar y comprobar antes de que la actuación se firme y llegue al verificador.
- **Veredicto**: resultado de calidad de una actuación: `NO_ELEGIBLE`, `BLOQUEADO`, `SUBSANABLE`, `PREVALIDADO`. Ninguno significa CAE garantizado.
- **`INT-xx`**: interpretación pendiente de validar; criterio propio, no verdad normativa.
- **`TODO(API-xx)`**: hueco de documentación de la plataforma oficial; enumerado en `docs/HUECOS.md`.

---

## 5. El modelo

### 5.1 Decisiones estructurales tomadas

| Decisión | Elegido | Consecuencia |
|---|---|---|
| Capa regulatoria | Socio sujeto delegado | Llegamos antes al mercado; dependemos de un tercero (riesgo a mitigar con más de uno y con **capacidad de delegación disponible** como criterio). |
| Financiación | Partner, sin riesgo propio | No asumimos riesgo de crédito ni el desfase del cobro del CAE. |
| Entrada al mercado | Canal instalador, después consumidor | Adquisición barata: el instalador ya tiene al cliente decidiendo la inversión. |
| Centro de gravedad | El motor, no el marketplace | Todo lo demás se construye encima. |
| Posición respecto a Moeve | Independiente (18/09/2026) | El CAE Engine es un modelo de negocio propio; Moeve es un posible cliente o aliado, no el destinatario. |

### 5.2 Cadena de valor y dónde nos ponemos

```
 Cliente          Actuación         Actuación CAE     Verificación      Expediente        Emisión
 (empresa,        (instalador,      [NOSOTROS]        (verificador)  →  (sujeto        →  (GA, CN,
  industria,   →   ingeniería,   →   prevalidación →                     delegado u        registro)
  flota)           fabricante)       + payload                            obligado)
```

Nuestro sitio es el eslabón que hoy consume horas de técnico y genera subsanaciones: **desde la documentación del cliente hasta la actuación en estado `COMPLETA`, lista para que el sujeto la firme**. Aguas abajo, consumimos notificaciones y tareas de la plataforma para interpretar requerimientos y reabrir la subsanación.

### 5.3 Productos, por orden de construcción

1. **CAE Check** — "¿esta actuación puede generar CAE y qué le falta?". Pago por actuación.
2. **CAE Platform** — gestión de muchas actuaciones para instaladores, ingenierías, industria y sujetos delegados, incluida la composición de expedientes válidos (*Expediente Builder*). Suscripción.
3. **CAE Monetization** — acompañamiento hasta el cobro, con el sujeto delegado socio. Comisión.
4. **CAE Supply** — cartera agregada y trazable que interesa a grandes compradores.
5. **Financiación** — producto derivado, cuando ya hay volumen y datos.

Qué funcionalidad sostiene cada producto y cuál es diferencial frente a la plataforma oficial: `docs/03` §13.

### 5.4 Quién paga

El cliente final no paga por entrar. Pagan quienes obtienen negocio del flujo: instalador o ingeniería (software y por actuación), sujeto delegado (volumen preparado y limpio), comprador (cartera agregada), fabricante (canal).

### 5.5 Referencias de mercado

Precio orientativo 2026: **100–140 €/MWh**; en 2025 los propietarios iniciales recibieron 115–140 €/MWh. De ahí salen verificación, gestión e intermediación, así que el neto al propietario es menor. Un solo variador de 110 kW del banco de pruebas vale del orden de **30–43 k€ brutos**: el tamaño del premio explica por qué la calidad de la actuación importa tanto. Más referencias en `docs/07` §4.

### 5.6 Posición regulatoria: alegaciones al proyecto de modificación del RD 36/2023

El 17/09/2026 se presentaron alegaciones, a título personal como persona física, en el trámite de audiencia e información pública del proyecto de modificación del RD 36/2023. Son la versión regulatoria de la tesis del proyecto: piden que la figura del **intermediario técnico / colaborador** exista formalmente en la plataforma y que la norma sea consumible por máquina.

| Artículo | Qué se pide | Pieza del Engine que lo necesita |
|---|---|---|
| Art. 2, letras h) e i) | Que el agregador de ahorros pueda acceder a la plataforma con perfil de colaborador habilitado por el sujeto obligado o delegado, sin capacidad de firma ni de solicitud | Modelo de negocio: preparar actuaciones por cuenta de un delegado sin ser delegado (§2) |
| Art. 8.3 | Que el propio artículo o la orden de desarrollo fije la regla de redondeo: método, unidad (kWh) y nivel (actuación o expediente) | INT-06 del YAML: hoy truncamos a kWh entero por criterio propio |
| Art. 12.1 | Aclarar que la limitación a un único agregador se refiere a la titularidad del ahorro y no impide que otros intermediarios técnicos presten servicios sin adquirirla | Nuestro sitio en la cadena de valor (§5.2) |
| Art. 16.b | Criterios de interpretación publicados con fecha de efecto, ficha/artículo, versión y formato estructurado y legible por máquina | Agente A6 (vigía normativo) y `spec/*.yaml` |
| Art. 18 | Catálogo y fichas en formato estructurado, con número de versión, entrada en vigor y periodo de aplicación | La ficha como configuración (regla de oro 4): hoy transcribimos a mano lo que pedimos que sea oficial |
| Art. 18 bis | Coeficientes de corrección publicados en formato estructurado además del BOE (ficha afectada, valor, vigencia, criterio de aplicación) | Rules Engine y Calculation Engine |
| Art. 20.3 | Perfil de colaborador habilitado y revocable por un sujeto obligado o delegado: preparar, cargar y consultar en borrador, sin firma ni presentación | Integración con la API oficial (Sprint 3) |
| DT 2ª, letras b) y c) | Formatos, esquemas de datos y entorno de pruebas accesibles a agregadores e intermediarios técnicos, no solo a agentes acreditados | Acceso al sandbox (oct–nov 2026) sin depender del certificado del delegado partner |

**Cómo leerlo.** Es una apuesta, no un hecho: la norma vigente no contempla el perfil de colaborador. El Engine se construye para funcionar **con la norma actual** (a través de un sujeto delegado partner) y se diseña para encajar **en la norma que pedimos**. Cualquier cambio en la tramitación del RD, en las órdenes de desarrollo o en la plataforma pasa por revisión humana antes de tocar el motor (regla de oro 9).

**Vía operativa paralela (hipótesis, 18/09/2026).** La plataforma prevé, dentro de cada agente, usuarios con perfil **Modificación** (sin firma) que el usuario con poder de Firma da de alta. Si el delegado partner puede dar de alta a personal o sistema nuestro con ese perfil, tendríamos de facto el colaborador del art. 20.3 sin esperar al RD. **NO DOCUMENTADO** si admite terceros ni cuentas de sistema: consulta enviada al gestor de la plataforma (decisión del 18/09/2026). Detalle en `docs/02` §7; hueco `API-09`. Decisión de Billy tras la respuesta.

---

## 6. El motor, en una página

Detalle en `docs/03` (arquitectura) y `docs/04` (reglas, cálculo y specs).

```
Documentos del cliente (PDF, escaneos, Excel, fotos)
        │
   [1] INGESTA            lectura, OCR, clasificación, separación de PDF combinados, SHA-256 de todo fichero
        │
   [2] EVIDENCIAS         extracción de variables con documento, página, método y confianza
        │
   [3] REGLAS             comprobaciones de la ficha y de la cabecera: ámbito, documentación,
        │                 evidencia, consistencia, fechas y cálculo
        ├──► NÚCLEO DETERMINISTA
        │      · Calculation Engine (fórmula leída del YAML, aritmética exacta)
        │      · Tablas de referencia con vigencia (cuadro 6 Reg. (UE) 2019/1781)
        │      · Huella SHA-256 y manifiesto
        │
   [4] INFORME + PAYLOAD  veredicto, ahorro, evidencias, subsanaciones, traza de auditoría;
        │                 cabecera + detalle por ficha + manifiesto de ficheros
        │
   Revisión humana → sujeto (firma) → verificador → expediente → GA → CN → registro
        │
   [5] SEGUIMIENTO        notificaciones y tareas de la plataforma → requerimientos interpretados → subsanación
```

**Cuatro veredictos**: 🟢 `PREVALIDADO` (supera todas las comprobaciones; calcula) · 🟡 `SUBSANABLE` (parece elegible, falta evidencia; calcula provisional) · 🔴 `BLOQUEADO` (inconsistencia crítica; no calcula) · 🔴 `NO_ELEGIBLE` (fuera del ámbito; no calcula). Ninguno significa CAE garantizado.

**Frontera de automatización**: el Engine llega hasta `COMPLETA`. La firma es humana con certificado de representante. Después, el Engine solo consume lo que la plataforma notifica.

**Agentes**: donde hay juicio (clasificar, extraer, auditar contradicciones, redactar, interpretar requerimientos), nunca donde hay norma (reglas, cálculo, tablas, huella, evidencias). El agente propone; el motor dispone. Contrato común y roles A0–A9 en `docs/03` §11. Con todos los agentes apagados, el Engine sigue produciendo veredicto.

**Criterios abiertos que pueden mover el resultado**: INT-01 (base de *p*, medio), INT-03 (N₂ media anual con 30 días, alto), INT-04 (extrapolación de horas, alto), INT-05 (registro inalterable, alto), INT-08 propuesta (expiración del CAE). Cerrarlos con un verificador es trabajo pendiente, no un detalle. El sandbox de la plataforma permitirá además cerrarlos **empíricamente**, comparando nuestro cálculo con el oficial.

---

## 7. Datos, riesgos y límites

- **Documentación real**: anonimizar antes de usarla en pruebas. Nada de datos de cliente en páginas publicadas ni en documentos compartibles.
- **Documentos sintéticos**: siempre marcados como tales, con empresas y números de serie inventados.
- **Moeve**: previsiblemente sujeto obligado (comprador natural de CAE) y, con obligación ≥ 50 MWh, usuario directo de la plataforma. Posición fijada el 18/09/2026: el CAE Engine es independiente. Sigue pendiente revisar el contrato laboral (exclusividad, propiedad intelectual, conflicto de interés) antes de cualquier contacto comercial (`docs/08` §5).
- **Delegado partner**: además del certificado, importa su **capacidad máxima de delegación disponible** (la plataforma la controla y la libera al liquidar). Un partner sin capacidad limita nuestro volumen.
- **Ventana de integración**: modelos de intercambio previstos para sep-2026 (no recibidos a 18/09); pruebas con entidades y API en oct–nov; producción dic-2026; fase II (Consulta Voluntaria Previa, información pública) ene–mar 2027. Sin delegado partner acreditado (o perfil Modificación) no hay sandbox.
- **Competencia**: CertificAhorro (directo), CAE Claro, caes.es, Smart Light, plataformas de fabricantes y delegados con portal propio. El diferencial debe demostrarse con números de prevalidación y trazabilidad, no con discurso. Ver `docs/07`.
- **Discurso**: prevalidación con trazabilidad. Nunca "te garantizamos X euros".
- **Riesgo de contagio**: un grupo tiene dictamen único y un expediente se aprueba o rechaza en conjunto. Regla de negocio para el delegado: no mezclar actuaciones `SUBSANABLE` con `PREVALIDADO` en el mismo grupo o expediente.

---

## 8. Dónde estamos y qué sigue

**Hecho (fuera de este repositorio)**: Sprint 1 (ficha como configuración, cálculo determinista, banco de pruebas) y Sprint 2 (Engine 0.1 de principio a fin, 7/7 casos, 61 tests) en otro entorno; confrontación con la plataforma oficial; alegaciones al RD; consolidación documental (18/09/2026).

**Punto de partida del repositorio (18/09/2026)**: documentación, spec IND240 v1.1, propuestas de spec y configuración de agentes. **Sin código.**

**Fase 0 — Reconstrucción del Engine 0.1** (`docs/06` §1): esqueleto de `docs/01`, tablas, cálculo, spec registry, generator con los 7 casos, ingesta y extracción por reglas, evidencias, reglas, motor, informe, CLI, evaluación y tests. Hecho cuando: 7/7 veredictos, caso A en 305.829,6 kWh/año, modo degradado comprobado, ADR de reconstrucción escrito.

**Sprint 3 — Integración con la plataforma oficial** (`docs/06` §2): modelo canónico `Actuacion`/`GrupoActuaciones`/`Expediente`, log de eventos, máquina de estados, `cabecera_v1.yaml` (tras aprobación), puerto de salida con handoff y simulador, P9 y A9, extractor LLM detrás de la interfaz existente, conector API cuando existan diccionario y acceso.

**En paralelo, fuera del código**: respuesta de `consultas-plataforma@registrocae.es` (modelos de intercambio, diccionario, perfil Modificación); cierre de delegado partner con certificado y capacidad; expediente real anonimizado; sesión con verificador para INT-01/03/04/05; seguimiento de la tramitación del RD 36/2023; primeros contactos (`docs/08`).

**Decisiones abiertas para Billy**: lista única en `CLAUDE.md` §6 y `docs/decisiones/ADR-001` §3.

---

## 9. Fuentes oficiales

- Catálogo de fichas MITECO — https://www.miteco.gob.es/es/energia/eficiencia/cae/catalogo-de-fichas.html
- Plataforma CAE (MITECO) y presentación OMIE/MIBGAS 30/06/2026 — https://www.miteco.gob.es/es/energia/eficiencia/cae/plataformacae.html · dominio `registrocae.es` · contacto `consultas-plataforma@registrocae.es`
- Real Decreto 36/2023 (sistema de CAE) — https://www.boe.es/buscar/doc.php?id=BOE-A-2023-2027
- Orden TED/815/2023 (desarrollo: convenio, expediente, validez) — https://www.boe.es/buscar/doc.php?id=BOE-A-2023-16734
- Reglamento (UE) 2019/1781, anexo I, cuadro 6 (pérdidas de variadores) — https://www.boe.es/buscar/doc.php?id=DOUE-L-2019-81609
- Proyecto de modificación del RD 36/2023, audiencia e información pública (septiembre 2026) — texto en los ficheros del proyecto.

---

*Mantener este documento vivo: cuando una decisión cambie, se cambia aquí primero. Si el documento y el código discrepan, el documento está desactualizado y hay que arreglarlo en la misma sesión.*
