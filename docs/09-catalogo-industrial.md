# CAE Engine — Matriz del catálogo industrial (28 fichas)

**Versión 1.1 · 18/09/2026 · Proyecto CAE (Billy)**

Cambios en 1.1: consolidación documental; referencias cruzadas a `docs/00`, `docs/04` (checklist de alta de ficha, §15) y `docs/03`. La columna "¿Cubierta hoy?" de §4.2 se reinterpreta para el arranque desde cero (ver nota en esa sección). Sin cambios en los datos de las fichas.

Documento complementario a `docs/00` (reglas de oro), `docs/04` (marco de reglas y checklist de alta de ficha, §15) y a la spec `spec/IND240_v1.1.yaml`. Este documento dice **qué hay en el catálogo industrial y qué le pide al marco**, para elegir las siguientes fichas con criterio. Versión compacta de `CAE-Engine_matriz-catalogo-industrial_v1.xlsx` (fichero de trabajo de Billy, fuera del repositorio), que contiene el detalle por ficha (requisitos, documentos propios, firmantes, enlaces a cada PDF).

**Convención de evidencia.**

| Marca | Significado |
|---|---|
| `PDF` | Leído en el PDF de la ficha, catálogo vigente de MITECO, el 18/09/2026 |
| `SPEC` | Procede de la spec IND240 del proyecto, no de una relectura del PDF |
| `VALORACIÓN` | Clasificación o juicio de Claude para ayudar a decidir; no es dato de la ficha |
| `SIN VERIFICAR` | Observación que hay que confirmar abriendo el anexo o el PDF original |

**Lo que este documento no contiene**, porque no se ha leído y no se inventa: el contenido de los anexos (tablas de SEPR, Fd, Fc, pérdidas térmicas, horas por actividad, modelos de declaración), ni la resolución del BOE que aprueba cada versión. Ninguna tabla numérica está transcrita. Las fórmulas se han reconstruido a partir del texto extraído del PDF: **verificar sobre el original antes de escribir una spec.**

**Regla de uso.** Qué ficha entra después y en qué orden lo decide Billy. Este documento clasifica y justifica; no decide. No sustituye al paso 1 del checklist de `docs/04` §15.

---

## 1. Lectura rápida

- El catálogo vigente tiene **28 fichas industriales** (IND010 a IND290; no existen IND100 ni IND130). `PDF`
- Salen **9 patrones de fórmula**, muy concentrados: el frío industrial son 9 fichas con una sola fórmula y un mismo juego documental. `VALORACIÓN`
- **Recalculables por el Engine:** 18 totales, 9 parciales (el SEPR lo declara el instalador con una herramienta externa) y 1 mínima (solar térmica, resultado de simulación). `VALORACIÓN`
- **Vecinas de IND240:** IND170 (motores), IND280 (bombas sin regulación), IND090 (compresores sin variador). Sus ámbitos se excluyen entre sí: son las primeras fronteras del emparejador A3. `PDF`
- **Memoria entre expedientes:** IND190, 200, 210 y 220 obligan a usar el SEPR verificado en un CAE previo del mismo circuito. `PDF`
- **Calidad de la fuente:** 42 incidencias detectadas (§5). `SIN VERIFICAR` hasta confirmarlas sobre el PDF.

## 2. Arquetipos de fórmula `VALORACIÓN`

| Arquetipo | Patrón | Fichas | Nº |
|---|---|---|---|
| A1a | Δ(1/SEPR) · Pf · h · Fd · Fc, por circuito frigorífico | 020, 030, 140, 150, 160, 190, 200, 210, 220 | 9 |
| A1b | Δ(1/rendimiento) · potencia o demanda · horas | 040, 060, 120, 170 | 4 |
| A2 | Δ(rendimiento o consumo específico) · magnitud · horas | 070, 090, 260, 280 | 4 |
| A3 | Δ potencia instalada · horas (balance antes/después) | 050, 270 | 2 |
| A4 | Δ pérdidas térmicas por elemento · dimensión · horas | 010 | 1 |
| A5 | Calor recuperado o transferido: caudal · c · ΔT · h · η | 110, 180, 230, 290 | 4 |
| A6 | Energía hidráulica recuperada (desalación): (1−TC) · Q · h · Δp · f | 080, 081 | 2 |
| A7 | Control sobre equipo existente (ley de afinidad) | 240 | 1 |
| A8 | Diferencia de resultados de un cálculo externo (simulación) | 250 | 1 |

## 3. Matriz

Fórmula, línea base y horas: `PDF` (IND240: `SPEC`). Recalculable y reutilización: `VALORACIÓN`.

| Ficha | Actuación | Arq. | Fórmula | Línea base | Horas | Histórico | Recalc. | Reutil. IND240 |
|---|---|---|---|---|---|---|---|---|
| IND010 V1.1 | Aislamiento de tuberías y superficies (>60°) | A4 | `AETOTAL = Σ(qRi − qFi)·Li·hi/1000 + Σ(qRj − qFj)·Aj·hj/1000` | Tabla normativa: pérdidas base (Anexo V, escenario 200 W/m o W/m²) frente a pérdidas objetivo (Anexo IV) | 1.976 h/año, sustituible con justificación | No | Total | Media |
| IND020 V1.2 | Sustitución de refrigerante | A1a | `AECTO = (1/SEPRant − 1/SEPRnue)·h·Fd·Fc·Pf ; AETOTAL = Σ circuitos` | Equipo existente: SEPRant declarado por el instalador para las condiciones de operación | Sin valor por defecto: declaración responsable del propietario | No | Parcial | Baja |
| IND030 V1.2 | Sustitución de compresor frigorífico | A1a | `AECTO = (1/SEPRant − 1/SEPRnue)·h·Fd·Fc·PF·Fsus ; AETOTAL = Σ circuitos` | Tabla normativa: SEPRant según tabla 1 del Anexo II | Sin valor por defecto: DR del propietario y Anexo III | No | Parcial | Baja |
| IND040 V1.1 | Caldera por bomba de calor | A1b | `AEc = Pc·(1/ηi − 1/SCOPBdC)·h ; AEACS = (1/ηi − 1/SCOPACS)·DACS·Fp ; AETOTAL = AEc + AEACS` | Equipo existente: ficha técnica, última inspección o tabla del Anexo IV | 1.920 h/año, sustituible con justificación | No | Total | Media |
| IND050 V1.1 | Iluminación LED | A3 | `AETOTAL = (PAnt − PPos)·t` | Equipo existente: potencia total anterior, acreditada con el CIE anterior | t según Anexo II, por actividad | No | Total | Media |
| IND060 V1.1 | Generador de climatización por bomba de calor | A1b | `AEC = Σ PCi·(1/SCOPsi − 1/SCOPni)·hCi ; AER = Σ PFi·(1/SEERsi − 1/SEERni)·hRi ; AETOTAL = AEC + AER` | Equipo existente: rendimiento estacional según Anexo II; SEER = 3 para equipos anteriores al ecodiseño | 1.152 h/año calefacción y 768 h/año refrigeración, sustituibles | No | Total | Media |
| IND070 V1.1 | Bomba de alta presión por pistones axiales (desalación) | A2 | `AETOTAL = (Cbc − Cbp)·Qm·hm, con C = Pn/QPM` | Equipo existente más histórico medido de 3 años | Media medida de los 3 años anteriores | 3 años | Total | Media |
| IND080 V1.1 | Instalación de cámara isobárica (desalación) | A6 | `AETOTAL = (1 − TC)·Qm·hm·Δp·f, con Δp = PBAP − PSCIP y f = 10,05` | Ausencia de recuperación: planta sin turbina ni otro medio de recuperación de energía | Media medida de los 3 años anteriores | 3 años | Total | Media |
| IND081 V1.1 | Sustitución de cámara isobárica (desalación) | A6 | `AETOTAL = (1 − TC)·Qm·hm·Δp·f, con Δp = PSCIPi − PSCIPn y f = 10,05` | Equipo existente: recuperador o cámara isobárica previa | Media medida de los 3 años anteriores | 3 años | Total | Media |
| IND090 V1.1 | Compresor de aire más eficiente | A2 | `AETOTAL = (PsCP − PsCT)·DA·h` | Equipo existente: potencia específica del compresor sustituido | Contador horario; valor de referencia 1.920 h, sustituible | 3 meses (sólo en una de las vías alternativas) | Total | Alta |
| IND110 V1.1 | Recuperación de calor de compresor | A5 | `Opción A (agua): AETOTAL = P·h·η ; Opción B (aire): AETOTAL = Q·c·ΔT·h·η, con c = 0,000344 y η = 0,96` | Ausencia de recuperación | 1.920 h/año, sustituible | No | Total | Media |
| IND120 V1.1 | Quemador modulante de gas | A1b | `AETOTAL = DC·(1/ηi − 1/ηm)` | Equipo existente (ficha técnica o media de las 3 últimas inspecciones) y demanda media de 3 años según auditorías | No aplica (usa demanda anual) | 3 años (auditorías) | Total | Baja |
| IND140 V1.2 | Planta frigorífica, refrigeración indirecta | A1a | `AECTO = (1/SEPRref − 1/SEPRnuev)·h·Fd·Fc·Pf ; AETOTAL = Σ circuitos` | Tabla normativa: SEPRref según tabla 1 del Anexo II (admite instalación nueva) | Sin valor por defecto: tabla justificativa del Anexo III y DR del propietario | No | Parcial | Baja |
| IND150 V1.2 | Instalación frigorífica, refrigeración directa | A1a | `AECTO = (1/SEPRref − 1/SEPRnuev)·h·Fd·Fc·Pf ; AETOTAL = Σ circuitos` | Tabla normativa: SEPRref según tabla 1 del Anexo II (admite instalación nueva) | Sin valor por defecto: tabla justificativa del Anexo III y DR del propietario | No | Parcial | Baja |
| IND160 V1.2 | Unidad de condensación | A1a | `AETOTAL = (1/SEPRrefant − 1/SEPRnuev)·h·Fd·Fc·Pf` | Tabla normativa: tabla 1 del Anexo II | Sin valor por defecto: tabla de servicios del Anexo III | No | Parcial | Baja |
| IND170 V1.1 | Sustitución de motores de inducción | A1b | `AETOTAL = Σ Ni·hi·Pmi·(1/ηref i − 1/ηnuev i)·100, con η en %` | Referencia normativa: motor de clase IE2 (o el valor de placa, según la nota 2) | 4.800 h/año: valor de referencia y a la vez mínimo exigido | No | Total | Alta |
| IND180 V1.1 | Intercambiadores de calor | A5 | `AETOTAL = Σ(1 − Uij/Upj)·QMj·Hj·t` | Equipo existente más histórico medido de 3 años | 1.920 h/año, sustituible | 3 años | Total | Baja |
| IND190 V1.1 | División de líneas de evaporación | A1a | `AETOTAL = [Pf/SEPRant − Σ Pfi/SEPRi]·Fd·Fc·h` | Equipo existente: SEPRant declarado, o el verificado en un CAE previo del mismo circuito | Sin valor por defecto: tabla de servicios del Anexo III | No | Parcial | Baja |
| IND200 V1.1 | Economizadores en instalación frigorífica | A1a | `AEi = (1/SEPRant − 1/SEPRpos)·h·Fd·Fc·Pf ; AETOTAL = Σ circuitos` | Equipo existente: SEPRant declarado, o el verificado en un CAE previo del mismo circuito | Sin valor por defecto: tabla de servicios del Anexo III | No | Parcial | Baja |
| IND210 V1.1 | Reducción de presión de condensación | A1a | `AEi = (1/SEPRant − 1/SEPRpos)·Pf·Fd·Fc·h ; AETOTAL = Σ circuitos` | Equipo existente: SEPRant declarado, o el verificado en un CAE previo del mismo circuito | Sin valor por defecto: tabla de servicios del Anexo III | No | Parcial | Media |
| IND220 V1.1 | Aumento de presión de evaporación | A1a | `AEi = (1/SEPRant − 1/SEPRpos)·Pf·Fd·Fc·h ; AETOTAL = Σ circuitos` | Equipo existente: SEPRant declarado, o el verificado en un CAE previo del mismo circuito | Sin valor por defecto: tabla de servicios del Anexo III | No | Parcial | Media |
| IND230 V1.0 | Recuperación de calor entre procesos | A5 | `AETOTAL = Σ Qj·Cj·ΔTj·hj/ηj` | Generador sustituido: rendimiento del equipo endotérmico | Sin valor por defecto: justificadas por 'ente de control habilitado y prueba de registro' | No (exige medida implantada, no histórico) | Total | Baja |
| IND240 V1.1 | Variador de velocidad | A7 | `AEM = PM·(1 − (N2/N1)³)·(1 − p)·h ; AETOTAL = Σ motores` | Equipo existente en régimen constante y sin modulación | Medidas: registro previo de un periodo representativo | Periodo representativo previo y ≥ 30 días posteriores | Total | Referencia |
| IND250 V1.0 | Solar térmica | A8 | `AETOTAL = EST nueva − EST anterior` | Instalación solar anterior, o cero si no hay sustitución | No aplica (resultado de simulación) | No | Mínima | Baja |
| IND260 V1.0 | Sustitución de SAI | A2 | `AETOTAL = PSAI·(ηn − η0)·taño` | Equipo existente: rendimiento del SAI sustituido (ficha técnica o Anexo II) | Horas anuales de conexión a red, justificadas en el Anexo II | No | Total | Alta |
| IND270 V1.0 | Transporte neumático por mecánico | A3 | `AETOTAL = Σ Pi·hi (neumático) − Σ Pj·hj (mecánico o mixto)` | Equipo existente: consumo del sistema neumático original | Por equipo, 'justificado mediante un parámetro de control' | 1 año (media de horas del último año) | Total | Media |
| IND280 V1.0 | Bomba más eficiente | A2 | `AETOTAL = (ηp − ηa)·P·hm, con η en %` | Equipo existente: rendimiento total de la bomba sustituida (Anexo II) | Promedio medido: registros de al menos 1 año | 1 año | Total | Alta |
| IND290 V1.0 | Recuperación de calor en circuito frigorífico | A5 | `AETOTAL = Q·c·ΔT·h·(1/η)` | Generador sustituido: rendimiento del generador cuyo calor se sustituye | La nota dice que 'podrá ser sustituido' pero la ficha no da valor de referencia | No (exige medida implantada) | Total | Media |

### 3.1 Qué exige cada ficha de nuevo al marco `VALORACIÓN`

| Ficha | Novedad frente a IND240 |
|---|---|
| IND010 | Dos ramas que se suman; decenas de unidades por actuación; búsqueda en tabla por elemento; anexos declarativos por elemento; valor por defecto sustituible |
| IND020 | Entrada clave calculada con herramienta externa (SEPR); búsqueda en tablas Fd y Fc; minoración condicional; habilitación del firmante |
| IND030 | Factor con tope (Fsus ≤ 1); exclusión por fecha de fabricación; comprobación de retirada |
| IND040 | Ramas de cálculo; dato con fuentes alternativas y valor por defecto en tabla; documento condicional |
| IND050 | Tabla por actividad; requisito sin evidencia asociada |
| IND060 | Documentación condicional con sustitutos; ramas; valores por defecto por rama |
| IND070 | Series históricas de 3 años con cálculo de medias; lectura de curvas de fabricante |
| IND080 | Umbrales numéricos de elegibilidad; conversión de unidades entre requisito y fórmula |
| IND081 | Ninguna sobre IND080 |
| IND090 | Evidencia alternativa (una de tres); tope contra placa; redondeo de un dato de entrada |
| IND110 | Ramas excluyentes; constantes físicas en la fórmula |
| IND120 | Regla de elegibilidad regulatoria; dependencia de una auditoría registrada |
| IND140 | Línea base normativa sin 'antes'; modalidades de actuación con reglas distintas |
| IND150 | Las de IND140 |
| IND160 | Las de IND140, sin sumatorio |
| IND170 | Umbral de elegibilidad sobre horas; tabla distinta del cuadro 6 (por polos y potencia) |
| IND180 | Series históricas; requisito sin evidencia asociada |
| IND190 | Memoria entre expedientes (historial CAE de la instalación); variante de fórmula con reparto de potencia |
| IND200 | Memoria entre expedientes |
| IND210 | Modalidades con documentación propia; evidencia digital de control; memoria entre expedientes |
| IND220 | Las de IND210 |
| IND230 | Tope de ahorro contra la demanda; firmante externo no tipificado |
| IND250 | El ahorro es el resultado de un cálculo externo: el Engine valida entradas, tope y coherencia, no recalcula |
| IND260 | Regla de mínimo entre dos valores |
| IND270 | Dos inventarios de equipos (antes y después) con horas propias |
| IND280 | Requisito sin evidencia asociada; lectura de curvas de fabricante |
| IND290 | Tope de ahorro contra la demanda |

## 4. Evidencias y capacidades

### 4.1 Frecuencia de cada tipo de evidencia `PDF`

X obligatorio · C condicional, alternativo o «cuando sea preceptivo» · R requisito de la ficha sin documento en su apartado 5.

| Evidencia | X | C | R | Fichas que la piden |
|---|---|---|---|---|
| Ficha firmada | 28 | 0 | 0 | todas |
| DR ayudas (Anexo I) | 28 | 0 | 0 | todas |
| Facturas | 28 | 0 | 0 | todas |
| Informe fotográfico | 26 | 0 | 0 | todas salvo 020, 050 |
| Certificado instalador con variables | 12 | 1 | 0 | 010, 060, 070, 080, 081, 090, 110, 120, 170, 180, 240, 250, 290 |
| Puesta en servicio o funcionamiento | 11 | 10 | 0 | 040, 050, 060, 070, 080, 081, 090, 110, 120, 140, 150, 160, 180, 190, 200, 210, 220, 230, 250, 280, 290 |
| Informe frigorista + Anexo III | 9 | 0 | 0 | 020, 030, 140, 150, 160, 190, 200, 210, 220 |
| DR de horas del propietario | 9 | 0 | 0 | 020, 030, 140, 150, 160, 190, 200, 210, 220 |
| Certificado instalación frigorífica (registro CCAA) | 2 | 0 | 0 | 020, 030 |
| Registros históricos previos | 6 | 1 | 2 | 070, 080, 081, 090, 120, 180, 240, 270, 280 |
| Registro o monitorización posterior | 1 | 2 | 4 | 050, 210, 220, 230, 240, 250, 290 |
| Fichas técnicas o gráficas de fabricante | 7 | 0 | 0 | 010, 070, 080, 081, 170, 240, 280 |
| Diagrama, esquema o plano | 6 | 0 | 0 | 010, 070, 080, 081, 270, 280 |
| Informe o anexo justificativo propio | 8 | 0 | 0 | 010, 050, 090, 110, 120, 230, 260, 270 |

Núcleo común a las 28 fichas: ficha firmada, declaración responsable de ayudas (Anexo I, común al sector) y facturas.

### 4.2 Capacidades que el catálogo exige al marco

**Nota de la consolidación (18/09/2026):** el código arranca de cero. La tercera columna dice si la capacidad está **prevista en el marco de la Fase 0** (según la spec IND240 y `docs/04`), no si existe código. Lo marcado "Sí" es lo que el marco debe cubrir al cerrar la Fase 0; lo marcado "No" o "Parcial" es lo que la segunda ficha obligará a añadir, y por eso pesa en la decisión de `§6`.

| Capacidad | Fichas que la exigen | ¿Prevista en el marco F0? |
|---|---|---|
| Multiunidad con clave de unión | IND010, 020, 030, 060, 140, 150, 170, 180, 190, 200, 210, 220, 230, 240, 270 | Sí (nivel 'motor' y `clave_union` en la spec IND240) |
| Búsqueda en tabla de referencia | IND010, 020, 030, 040, 050, 060, 140, 150, 160, 170, 190, 200, 210, 220, 240 | Sí (cuadro 6 del Reglamento 2019/1781, `engine/tablas.py`) |
| Ramas de cálculo sumadas o excluyentes | IND010, 040, 060, 110 | No prevista en F0 |
| Valor por defecto sustituible con justificación | IND010, 040, 060, 090, 110, 170, 180 | No prevista en F0 |
| Documento condicional, alternativo o sustituto | IND040, 050, 060, 090, 110, 120, 180, 190, 210, 220, 240, 250, 280 | Parcial (DOC-05B condicional simple; falta 'uno de N' y sustitutos encadenados) |
| Series históricas con cálculo de medias | IND070, 080, 081, 120, 180 (3 años); 270, 280 (1 año); 090 (3 meses); 240 | Parcial (`registro_horas_previo`) |
| Entrada clave producida por herramienta externa | IND020, 030, 140, 150, 160, 190, 200, 210, 220 (SEPR); 250 (simulación solar) | No |
| Umbrales y topes numéricos de elegibilidad | IND030 (Fsus ≤ 1), 080 y 081 (≤ 2 bar, ≥ 45 %), 090 (DA ≤ placa), 170 (≥ 4.800 h), 230, 250, 290 (aporte ≤ demanda) | Parcial (precondiciones y controles físicos FIS-01 y FIS-02) |
| Habilitación o registro del firmante | Familia frío (frigorista habilitada), 050 (REBT), 110 (equipos a presión) | No prevista en F0 |
| Modalidades de actuación con reglas o documentos distintos | IND140, 150, 160, 210, 220, 250 | No prevista en F0 |
| Memoria entre expedientes (CAE previo del mismo circuito) | IND190, 200, 210, 220 | No |
| Elegibilidad regulatoria (combustibles fósiles) | IND120 | No |
| Evidencia digital de control | IND210, 220, 240 | Sí (registro inalterable, INT-05) |
| Requisito sin evidencia asociada en la ficha | IND030, 050, 160, 180, 230, 250, 280, 290 | Decisión de diseño pendiente (Billy): ¿aviso, o se pide igualmente? |

## 5. Candidatos a INT-xx e incidencias de la fuente `SIN VERIFICAR`

Detectadas sobre texto extraído. Confirmar visualmente antes de citarlas fuera del proyecto. Si la ficha entra en el Engine, cada línea se convierte en `INT-xx` (regla: no resolver en silencio).

| Ficha | Tipo | Incidencia |
|---|---|---|
| IND020 | Inconsistencia web–PDF | La ficha usa el Anexo III como tabla de Pf y h a cumplimentar y firmar; la web titula el Anexo III 'nota informativa' sobre sustitución de refrigerantes. A verificar abriendo el anexo. |
| IND020 | Ambigüedad | Minoración del 10 % del SEPR con PCA<150 'salvo justificación técnica': no se dice qué justificación basta. |
| IND030 | Inconsistencia interna | La fórmula usa SEPRant y la tabla de resultados SEPRref. |
| IND030 | Laguna documental | La retirada de los compresores sustituidos es requisito y no tiene documento propio que la acredite. |
| IND040 | Ambigüedad | Tres fuentes posibles para ηi (ficha técnica, última inspección, tabla del Anexo IV) sin orden de prelación. |
| IND040 | Inconsistencia web–PDF | La web publica un Anexo V 'Documentación técnica' que el apartado 5 no cita. A verificar. |
| IND050 | Laguna documental | El sistema de información de consumos y horas es requisito y no tiene documento asociado. |
| IND050 | Ambigüedad | Se exige el CIE anterior a la actuación, que puede no existir o no desglosar la iluminación. |
| IND060 | Errata | La tabla de resultados expresa AER y AETOTAL en 'kW/año'. |
| IND060 | Ambigüedad | Cadena condicional de los documentos 5, 6 y 7: cuándo basta cada uno. |
| IND070 | Ambigüedad | La potencia 'nominal' se obtiene de la curva al caudal medio, no de la placa; dos caudales distintos en la misma fórmula. |
| IND080 | Ambigüedad | Requisito en bar y variables en m.c.a.; Qm en m³/s frente a m³/h en IND070. |
| IND090 | Ambigüedad | Redondeo de Ps a 'dos dígitos representativos' y tres vías alternativas para acreditar la demanda. |
| IND110 | Contradicción interna | El requisito dice que el sistema de calefacción 'será por agua' y el cálculo ofrece una Opción B para calefacción por aire. |
| IND110 | Ambigüedad | η tiene valor de referencia (0,96) en la opción B y no en la A. |
| IND120 | Ambigüedad | 'Fracción de ahorro correspondiente' en combustibles fósiles sin fórmula de reparto; alcance de los documentos 7 y 8. |
| IND140 | Inconsistencia web–PDF | Título de la web distinto del título del PDF. |
| IND140 | Inconsistencia interna | El apartado 5 pide justificar 'SEPRant' y la fórmula usa SEPRref (tabla). |
| IND150 | Inconsistencia interna | Misma discrepancia SEPRant / SEPRref que IND140. |
| IND160 | Inconsistencia interna | Tres nombres para la misma variable: SEPRrefant, SEPRant y SEPRref. |
| IND160 | Laguna documental | Pf se 'justifica según anexo III' pero el apartado 5 no exige aportar el Anexo III firmado. |
| IND170 | Ambigüedad | ηref es el motor de referencia IE2, pero la nota 2 manda usar el valor de placa si existe, sin decir de qué motor. |
| IND170 | Ambigüedad | 4.800 h es el mínimo exigido y a la vez el valor de referencia sustituible. |
| IND180 | Ambigüedad | 'Normalizadas a unas condiciones específicas' sin definir. |
| IND180 | Laguna documental | Tres años de medidas como requisito, sin documento en el apartado 5. |
| IND190 | Inconsistencia interna | El glosario define SEPRnue y la fórmula usa SEPRi; bloque de firma de 'persona técnica responsable'. |
| IND190–IND220 | Dependencia externa | SEPRant debe ser el valor verificado en un CAE previo del mismo circuito: exige conocer el historial CAE de la instalación. |
| IND200 | Inconsistencia web–PDF | El título de la web añade 'o multietapa' y 'centralizada o compacta'. |
| IND210 | Errata | Cita un 'Reglamento nº 2027/573'. |
| IND220 | Errata | La numeración del apartado 5 salta del 5 al 7; el ámbito habla de 'central térmica'. |
| IND230 | Inconsistencia web–PDF | El título del Anexo II difiere entre la web y la ficha. |
| IND230 | Ambigüedad | 'Ente de control habilitado' sin definir. |
| IND250 | Ambigüedad | Tres métodos de cálculo admitidos; monitorización exigida sin documento asociado. |
| IND260 | Inconsistencia web–PDF | Firmante del Anexo II: 'empresa instaladora' en la web, 'técnico responsable' en la ficha. |
| IND260 | Inconsistencia interna | Ámbito de 'uno o varios' SAI con fórmula sin sumatorio. |
| IND270 | Errata | La tabla de resultados rotula Etransneum j donde corresponde Etransmec j. |
| IND270 | Ambigüedad | 'Potencia consumida' y 'parámetro de control' sin definir. |
| IND280 | Ambigüedad | η en % y fórmula sin dividir entre 100, a diferencia de IND170. |
| IND280 | Laguna documental | Registros de horas de al menos 1 año como requisito, sin documento en el apartado 5. |
| IND290 | Errata | La nota 2 se refiere al cálculo de energía solar térmica (texto de IND250). |
| IND290 | Ambigüedad | Las horas 'podrán ser sustituidas' sin que la ficha dé valor de referencia. |
| Familia frío | Inconsistencia entre fichas | Unas fichas citan el Reglamento (UE) 517/2014 de gases fluorados y otras el 2024/573 que lo deroga. |

## 6. Decisiones abiertas (de Billy)

1. **Criterio para la ficha n.º 2.** Vecina (IND170 o IND280: coste bajo, prueba el «cero cambios en `engine/`») o estresante (una de frío, p. ej. IND030 o IND140: obliga a construir capacidades nuevas y abre 9 fichas, con recalculabilidad parcial). Depende de la demanda real del delegado partner, que no está documentada.
2. **Requisitos sin evidencia en la ficha** (IND030, 050, 160, 180, 230, 250, 280, 290): ¿el Engine avisa, o pide el documento igualmente?
3. **Familia de frío:** si entra, exige conocimiento de dominio de empresa frigorista y la herramienta SEPR de la Comisión como entrada opaca.
4. **Memoria entre expedientes:** depende del acceso a datos históricos de la instalación (propios o vía plataforma oficial).

## 7. Mantenimiento

Regenerar cuando cambie el catálogo (resolución en BOE) o cuando se lea un anexo. Fuente: `https://www.miteco.gob.es/es/energia/eficiencia/cae/catalogo-de-fichas/catalogo-vigente-de-fichas/industria.html`. El BOE manda; el catálogo web es recopilación.
