# CAE Engine — Potenciales clientes y primeros contactos estratégicos

**Versión 1.1 · 18/09/2026 · Proyecto CAE (Billy)**

Cambios en 1.1: consolidación documental; referencias cruzadas actualizadas a `docs/00`, `docs/03`, `docs/07`. Sin cambios de contenido.

Documento complementario a `docs/00` (modelo y quién paga, §5.4), `docs/07` (mapa de agentes y competencia) y `docs/03` (qué hace el motor). Este documento dice **a quién llamar primero, por qué, con qué argumento y qué preguntarle**.

**Convención de evidencia.** Cada afirmación sobre una entidad lleva una de estas marcas:

| Marca | Significado |
|---|---|
| `WEB` | Leído en la web propia de la entidad el 18/09/2026 |
| `MITECO` | Dato de la lista oficial de sujetos delegados (actualizada 22/07/2026) |
| `07` | Procede de `docs/07`, verificado el 17/09/2026 |
| `SIN VERIFICAR` | Hipótesis razonable que hay que confirmar en la primera conversación |

**Lo que este documento no contiene**, porque no es público y no se inventa: volumen de actuaciones de cada entidad, nombres de decisores, herramientas internas que usan, tasa de subsanaciones. Todo eso sale de la primera llamada (§6).

**Regla de uso.** La elección de a quién contactar y en qué orden es de Billy. Este documento propone y justifica; no decide.

---

## 1. Para qué sirve el primer contacto

No es una venta. Con un motor que hoy cubre una ficha (IND240) y no ha visto un expediente real, el primer contacto busca tres cosas, por este orden:

1. **Un expediente industrial real anonimizado** para medir el motor fuera del laboratorio (`docs/06` §5, X.4).
2. **Un delegado dispuesto a probar en paralelo** (modo sombra, `docs/05` §5) y, si llega el caso, a dar acceso a las pruebas de la plataforma oficial con su certificado (`docs/02` §9).
3. **Validar el dolor**: cuántas horas de técnico consume una actuación y cuántas vuelven con subsanación. Sin ese dato, la propuesta de valor de `docs/00` §1.1 es una hipótesis.

Un contacto que aporte cualquiera de las tres ya ha merecido la pena.

---

## 2. Segmentos, por orden de prioridad

| # | Segmento | Por qué | Cuándo |
|---|---|---|---|
| 1 | **Delegado que además instala o mantiene en industria** | Genera sus propias actuaciones industriales, no tiene herramienta CAE y sufre la preparación en primera persona | Ahora |
| 2 | **Delegado con foco industrial declarado** | Encaje directo con IND240 y con el hueco "industrial sin plataforma" (`docs/07` §5) | Ahora |
| 3 | **Delegado tramitador puro o consultora con cartera industrial** | Vive de la calidad del expediente o tiene clientes industriales y poca capacidad CAE | Segunda ola |
| 4 | **Canal: fabricantes y distribuidores de variadores** | No pagan por actuación, pero originan actuaciones IND240 y generan la evidencia (registro de 30 días) | Segunda ola |
| 5 | **Delegados de nivel B del `docs/07` y grandes grupos** | Ciclos de decisión largos; mejor llegar con un caso real ya hecho | Cuando haya referencia |
| 6 | **Sujetos obligados (compradores)** | Corresponde a CAE Supply (`docs/00` §5.3, producto 4): necesita volumen que hoy no existe | Más adelante |

**A quién no contactar como partner**, y por qué: delegados con plataforma propia (Bettergy, Ingeniería Aplicada, AlfaCAE, Efficiency Program — `docs/07`), porque son potenciales competidores; y CertificAhorro, competidor directo (`docs/07` §3.1).

---

## 3. Primera ola — fichas de candidato

### 3.1 Atein, S.A. (Vic, Barcelona) — segmento 2

| | |
|---|---|
| **Evidencia** | `WEB` Declara que actualmente se centra en proyectos del sector industrial; su formulario de contacto rechaza los demás sectores. `WEB` Su papel: identificar actuaciones, clasificarlas y recopilar la documentación para elaborar la memoria que justifica el ahorro. `WEB` Trabaja estandarizadas y singulares |
| **Por qué encaja** | Es el único delegado revisado con foco industrial exclusivo y declarado. Lo que describe como su trabajo (recopilar documentación y justificar el ahorro) es exactamente lo que automatiza el motor |
| **Argumento de entrada** | "Convertimos la carpeta desordenada del cliente industrial en una actuación con cada dato trazado a su documento, y avisamos de lo que falta antes de que lo vea el verificador" |
| **Dudas** | `SIN VERIFICAR` Tamaño y volumen. `WEB` Hay un enlace "Área personal" que lleva a la web corporativa: no se sabe si hay herramienta detrás |
| **Contacto oficial** | `MITECO` cae@ateinsa.com · 938 852 052 · Web CAE: certificados-ahorroenergetico.com |

### 3.2 Stratenergy, S.L. (Derio, Bizkaia / Getafe) — segmento 2

| | |
|---|---|
| **Evidencia** | `WEB` Empresa del grupo Velatia. `WEB` Publica casos con volumen: entre ellos, sustitución de compresores de aire con 5.573.000 CAE y otros de 7.891.000 y 5.311.000 CAE. `WEB` Tiene plataforma propia de monitorización de consumos (MIDE); no es una plataforma de gestión de CAE |
| **Por qué encaja** | Casos industriales reales y de tamaño. Su monitorización toca dos piezas del motor: la evidencia EVD-01 (registro ≥ 30 días) y el criterio abierto INT-05 (qué es un "registro inalterable") |
| **Argumento de entrada** | "Vuestra monitorización ya produce la evidencia que más cuesta acreditar en fichas como IND240. Nosotros la vinculamos por huella al resto de la actuación y comprobamos la coherencia entre todos los documentos" |
| **Dudas** | `SIN VERIFICAR` Al pertenecer a un grupo industrial, la decisión puede no ser local. `SIN VERIFICAR` Si tramitan IND240 en concreto |
| **Contacto oficial** | `MITECO` caes@stratenergy.es · 944 317 777 |

### 3.3 Inmarepro, S.L. (Madrid) — segmento 1

| | |
|---|---|
| **Evidencia** | `WEB` Empresa de instalaciones y mantenimiento industrial, con sistemas de control y frío industrial. `WEB` Como delegado se encarga del proceso completo de verificación y solicitud. `WEB` Solo ofrece formulario de contacto; la página CAE no se actualiza desde enero de 2024 |
| **Por qué encaja** | Instalador y delegado a la vez: prepara sus propias actuaciones con su propio personal técnico. Es el perfil donde una hora de técnico ahorrada se nota antes |
| **Argumento de entrada** | "Vuestros técnicos ya tienen la factura, la ficha técnica y el certificado de instalación. Nosotros comprobamos que todo cuadra entre sí y con la ficha antes de enviarlo a verificar" |
| **Dudas** | `SIN VERIFICAR` Actividad CAE real: la página sin actualizar puede indicar poco volumen |
| **Contacto oficial** | `MITECO` cae@inmarepro.com · 916 600 980 |

### 3.4 Tecman Servicios de Valor Añadido, S.L. (Erandio, Bizkaia) — segmento 1

| | |
|---|---|
| **Evidencia** | `WEB` Ingeniería, instalación y mantenimiento (incluye calderas industriales y cogeneración), servicios energéticos y facility services. `WEB` Su plan de mantenimiento más alto incluye integración en plataforma de gestión propia y "asesoramiento y generación de CAEs". `WEB` Participa en proyectos de I+D de gestión energética de centros de datos |
| **Por qué encaja** | Instalador-mantenedor y delegado, con cultura tecnológica y el CAE ya empaquetado dentro de un servicio recurrente: cada contrato de mantenimiento es una fuente de actuaciones |
| **Argumento de entrada** | "Ya ofrecéis generación de CAE dentro del mantenimiento. Nosotros hacemos que cada actuación salga de los datos que ya gestionáis, con trazabilidad y sin horas extra de técnico" |
| **Dudas** | `SIN VERIFICAR` Peso de industria frente a edificios en su cartera. La plataforma que tienen es de gestión energética y mantenimiento, no de CAE: confirmar que no la están extendiendo |
| **Contacto oficial** | `MITECO` cae@grupo-tecman.com · 944 538 360 |

---

## 4. Segunda ola

### 4.1 Delegados

| Entidad | Evidencia | Por qué después y no ahora | Contacto `MITECO` |
|---|---|---|---|
| **Céltica Energía** (grupo Ignis, Madrid) | `WEB` Consultora de compra de energía con línea para industria electrointensiva; su servicio CAE es una entrada de blog de 2025 | Cartera industrial grande pero capacidad CAE aparentemente incipiente: interesante como cliente, poco probable que aporte expedientes ya | caes@ignis.es · 910 059 775 |
| **Grecert Iberia** (Madrid) | `WEB` Especialista puro en CAE, gestiona el proceso completo, todos los sectores, opera en España, Italia, Polonia y Francia; tiene sección de partners | Vive de tramitar, así que la calidad del expediente es su negocio; sin foco industrial declarado | info@grecert.com · 659 674 717 |
| **AITESA** (Madrid) | `WEB` Ingeniería de recuperación de calor; química, siderurgia, papel, vidrio, alimentación | Su terreno es térmico y previsiblemente de actuaciones singulares; el motor hoy solo cubre una ficha estandarizada | aitesa@aitesa.com (`WEB`) · 913 501 687 |
| **EPSA Spain** (Madrid / Barcelona) | `WEB` Prepara expedientes, gestiona certificación y solicitud, cobra a éxito; multinacional francesa | Perfil similar a Leyton; la decisión probablemente no se toma en España | administracion.spain@epsa.com · 689 787 469 |
| **Uría Ingeniería de Instalaciones** (Asturias) | `WEB` Texto genérico sobre el sistema y su código de acreditación | Perfil instalador-delegado, pero sin señales de actividad CAE | info@urianet.com · 985 670 251 |

### 4.2 Canal: quien origina actuaciones IND240

| Entidad | Evidencia | Planteamiento |
|---|---|---|
| **Schneider Electric** | `07` §3.4: canal CAE para variadores, registrador integrado en Altivar Process, generador de informe de uso en Excel, calculadora | No es cliente ni rival: es fuente de evidencia. Primer paso técnico, sin necesidad de contacto: soportar su formato de exportación en `engine/registro_xlsx.py` |
| **Vector Energy** | Visto en búsqueda el 18/09/2026: ofrece poner en contacto al usuario final para tramitar el CAE de su variador. `SIN VERIFICAR` a fondo | Posible canal hacia actuaciones IND240; revisar su web antes de cualquier contacto |
| **Asociaciones de instaladores (CNI, CONAIF)** | `07` §2.2 y §4: CONAIF ya tiene plataforma con Bettergy; CNI reclama públicamente que la plataforma oficial permita la colaboración del instalador | CNI pide lo mismo que las alegaciones de `docs/00` §5.6: hay alineamiento de discurso. CONAIF está comprometida con un competidor |

### 4.3 Nivel B del `docs/07` (sin revisar de nuevo en esta sesión)

Acciona, Greenflex, Effic, DELCAE, Leyton/Caelia, Konery, Premium Energy, Loris ENR. Servicio llave en mano sin plataforma pública. Varios son grandes o filiales extranjeras: mejor llegar con un caso real ya resuelto.

---

## 5. Antes de escribir a nadie

| # | Comprobación | Estado |
|---|---|---|
| 1 | Revisar contrato laboral: exclusividad, propiedad intelectual y política de conflicto de interés. La posición es independiente de Moeve (decisión del 18/09/2026), pero el empleador es sujeto obligado del mismo sistema | Pendiente |
| 2 | Contactar desde cuenta personal, nunca corporativa | — |
| 3 | Tener lista la demo: informe de prevalidación del caso A y del caso C (contradictorio) con los documentos sintéticos. El caso C es el que mejor explica el valor: el motor se detiene y muestra las dos evidencias | **Depende de la Fase 0** (`docs/06` §1): el Engine 0.1 se reconstruye en este repositorio |
| 4 | Acuerdo de confidencialidad sencillo para recibir un expediente real, y procedimiento de anonimización (`docs/03` §12) | Pendiente |
| 5 | Decidir qué se ofrece a cambio del expediente real: informe de prevalidación gratuito, acceso preferente, o nada todavía | Decisión de Billy |
| 6 | Respuesta (o silencio) de `consultas-plataforma@registrocae.es`: condiciona si se pide al delegado acceso a las pruebas de la plataforma | Consulta decidida el 18/09/2026 |

**Lo que se podrá enseñar al cerrar la Fase 0:** IND240 de principio a fin, 7 casos sintéticos con el veredicto esperado, cada dato con documento y página, cálculo determinista, detección de contradicciones y de evidencia que falta.

**Lo que no se puede afirmar:** que acierte en documentos reales no vistos (no se ha medido), que cubra otras fichas (no las cubre), ni nada parecido a un CAE garantizado (`docs/00` §2).

---

## 6. Qué preguntar en la primera conversación

Son las preguntas que convierten `SIN VERIFICAR` en dato. Ordenadas de menos a más comprometidas.

1. ¿Qué tipos de actuación tramitáis más? ¿Hacéis IND240 u otras fichas industriales de motores, bombas, compresores?
2. ¿Cuántas actuaciones al año, aproximadamente, y cuántas son industriales?
3. ¿Quién prepara la actuación y cuántas horas le lleva una típica?
4. ¿Qué porcentaje vuelve del verificador con rectificación? ¿Cuál es el motivo más repetido?
5. ¿Qué documento es el que más cuesta conseguir del cliente? (Hipótesis: el registro de 30 días.)
6. ¿Con qué herramienta lo gestionáis hoy: hojas de cálculo, gestor documental, algo propio?
7. ¿Habéis recibido información de la plataforma oficial de OMIE/MIBGAS? ¿Vais a participar en las pruebas de octubre–noviembre de 2026?
8. ¿Estaríais dispuestos a pasar una actuación ya cerrada, anonimizada, para comparar nuestro resultado con el vuestro?

Las respuestas a 2, 3 y 4 son la métrica que importa (`docs/00` §1): horas sustituidas y porcentaje que pasa a la primera.

---

## 7. Secuencia sugerida

1. **Ensayo**: primer contacto con un candidato de la segunda ola, para afinar el mensaje sin gastar un candidato prioritario.
2. **Primera ola**: los cuatro de §3. Orden a criterio de Billy; por encaje con IND240, Atein y Stratenergy; por facilidad de conseguir un expediente, Inmarepro y Tecman.
3. **Revisión a dos semanas**: si ninguno responde o ninguno tiene volumen industrial, completar la revisión de las entidades pendientes (§9) antes de insistir.

Referencia temporal: las sesiones de prueba de la plataforma oficial están previstas para octubre–noviembre de 2026 (`docs/02` §1).

---

## 8. Seguimiento

Se rellena con hechos, no con previsiones.

| Entidad | Fecha contacto | Canal | Persona | Respuesta | Siguiente paso | Dato obtenido (§6) |
|---|---|---|---|---|---|---|
| | | | | | | |

---

## 9. Pendiente de revisar

- **No visitadas (15):** Alpha Syltec, Balantia, mc2 (Grupo Emececuadrado), Didepro, Electrotecnia Monrabal, Eleukon, Global Factor, Humiclima Norte, Light Environment Control, Moneleg, Recursos de la Biomasa, Sertogal, Sitelec, Solvent, Soningeo. Casi todas declaran al MITECO su web corporativa general como "web dedicada al CAE": indicio de nivel C, no confirmación. Por denominación, Monrabal y Humiclima podrían ser instalador-delegado (segmento 1): serían las primeras a mirar.
- **Inaccesibles de forma automática (4):** Creara, Letter Ingenieros, Inventium (bloquean el acceso) y Sinceo2 (enlace roto en la lista oficial). Requieren revisión manual.
- **Herramientas a vigilar, no a contactar:** CalculaCAE.ai (preparación de expedientes de transporte para delegados, con datos de la DGT: mismo modelo que el nuestro en otro sector; afecta a la decisión sobre TRA050 como segunda ficha) y CAE Digital (captación B2C; se presenta como sujeto delegado pero no figura con ese nombre en la lista oficial: aclarar antes de cualquier trato).

---

## 10. Fuentes

- Lista oficial de sujetos delegados — `miteco.gob.es/es/energia/eficiencia/cae/agentes.html` (actualizada 22/07/2026; consultada 18/09/2026). 70 entidades.
- Webs propias de Atein, Stratenergy, Inmarepro, Tecman, Céltica Energía, Grecert, AITESA, EPSA Spain, Uría, Ness, Sawatco, Ondoan, CalculaCAE.ai y CAE Digital, consultadas el 18/09/2026.
- `docs/07` v1.1 para todo lo marcado `07`.

---

*Mantener vivo: tras cada conversación, sustituir la marca `SIN VERIFICAR` por el dato obtenido y anotar la fila en §8 el mismo día. Si un candidato resulta tener plataforma propia, pasa a la lista de "no contactar" y se anota en `docs/07`.*
