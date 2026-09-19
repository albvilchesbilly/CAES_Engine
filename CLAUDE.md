# CLAUDE.md — CAE Engine

Motor de prevalidación de actuaciones CAE (certificados de ahorro energético, RD 36/2023, Orden TED/815/2023).
Convierte documentación desordenada de una actuación de eficiencia energética en una **actuación trazable,
calculada de forma determinista y prevalidada**, lista para que un profesional la revise en minutos y para
que un sujeto delegado la firme y la presente en la plataforma oficial (OMIE/MIBGAS).

**Estado a 18/09/2026: el repositorio arranca sin código.** La documentación describe un Engine 0.1 (Sprints 1
y 2, una ficha IND240, 7 casos sintéticos, 61 tests) que se construyó en otro entorno y no está aquí. La
primera tarea es **reconstruirlo** (Fase 0 de `docs/06-plan-de-construccion.md`) con los criterios de
aceptación de `docs/05-evaluacion-y-banco-de-pruebas.md`. Después, el Sprint 3.

Este fichero dice lo que el código no puede decirte: qué es intocable, qué vocabulario usar, qué está decidido
y cómo se orquesta el trabajo. El detalle está en `docs/`.

---

## 1. Antes de tocar nada

Orden de lectura obligatorio en una sesión nueva (no lo saltes; es la única forma de no romper decisiones):

1. `docs/00-instrucciones-de-entrada.md` — esencia, reglas de oro, glosario, modelo, estado.
2. `docs/01-estructura-del-repositorio.md` — qué carpeta es qué, quién escribe dónde, orden de creación.
3. `docs/06-plan-de-construccion.md` — en qué fase estamos y cuál es el siguiente entregable.
4. `docs/03-arquitectura-backend.md` y `docs/04-motor-de-reglas-y-specs.md` — antes de escribir código.
5. `docs/02-plataforma-oficial.md` y `docs/HUECOS.md` — antes de tocar modelo canónico, estados o salida.
6. `spec/IND240_v1.1.yaml` — la ficha como configuración: ahí está el detalle real.
7. `docs/decisiones/ADR-001-decisiones-vigentes.md` — lo que ya está decidido y no se reabre en silencio.

**Precedencia cuando dos fuentes discrepan** (de mayor a menor):
BOE → plataforma oficial (lo publicado) → catálogo MITECO → `spec/*.yaml` activa → `docs/00` → `docs/02` →
`docs/03`/`docs/04` → resto de `docs/` → código. Si el código contradice un documento, uno de los dos está
mal y se arregla **en la misma sesión**; nunca se deja la discrepancia en silencio.

---

## 2. Reglas no negociables

Cualquier propuesta que rompa una de estas está mal planteada, por buena que suene.

1. **La IA lee; el motor calcula.** Ningún LLM ejecuta la fórmula ni decide si una regla se cumple. Los agentes
   proponen valores con cita; el núcleo decide. Una salida de agente con un resultado calculado se rechaza.
2. **Todo dato lleva evidencia**: documento, página, texto literal, método, confianza. Sin cita no entra.
3. **Tres capas por dato**: documento → interpretación → cálculo. Se guardan las tres.
4. **La ficha es configuración.** Añadir una ficha es añadir YAML (spec + mapping). Un `if ficha == ...` en
   `engine/` es un defecto del marco, no una solución.
5. **Declarado ≠ demostrado.** Se marcan y se tratan distinto.
6. **Ante conflicto entre fuentes fiables, el motor se detiene.** `valor_consumido = null`; se muestran las dos
   evidencias. No se elige, no se calcula.
7. **Lo que la norma no cierra es un `INT-xx`** con criterio, alternativa e impacto, declarado en la spec.
   Nunca se resuelve en silencio dentro del código.
8. **El BOE manda.** La spec es nuestra lectura; si discrepa, gana el BOE.
9. **Todo cambio en `spec/` activa, `data/` o en `expedientes/_resultados_esperados/` pasa por revisión
   humana (Billy).** Prepara el diff en `spec/propuestas/` o un ADR; no lo actives.
10. **Lo que la plataforma oficial no ha documentado es un hueco enumerado** (`TODO(API-xx)` en
    `docs/HUECOS.md`), nunca una suposición en el código. No inventes campos de la API.

Reglas de implementación:

- Aritmética con `Decimal`, nunca `float`, en todo lo que toque el ahorro. `AETOTAL` truncado a kWh entero (INT-06).
- **Nada de `eval()`.** `logica` y `formula` se interpretan con un parser de lista blanca (`engine/expresiones.py`).
  Función desconocida = error de carga de la spec, no de ejecución.
- SHA-256 de todo fichero en ingesta, antes de cualquier transformación. Vinculación por hash y por nº de
  serie, nunca por nombre de fichero.
- **Dependencias hacia dentro.** `engine/` no importa nada de `agentes/` ni de `salida/`. Con todos los agentes
  apagados el Engine sigue produciendo veredicto (modo degradado). Hay un test que lo comprueba.
- Nunca custodiamos certificados de representante. La firma es un acto humano; solo registramos `FirmaRegistrada`.
  Ningún componente nuestro firma actos administrativos.
- Datos reales: anonimizados antes de entrar en pruebas. Documentos sintéticos siempre con la marca
  "DOCUMENTO SINTÉTICO – SOLO PRUEBAS".
- Ningún texto de producto dice "CAE garantizado". A8 no se llama "verificador" en ningún sitio.

---

## 3. Vocabulario (no lo mezcles)

- **Actuación** (`Actuacion`): la unidad de trabajo de la plataforma oficial y de nuestro código. Una
  intervención concreta (p. ej. uno o varios variadores en la misma actuación) con cabecera, detalle según
  ficha y documentación. Es lo que la documentación antigua llamaba "expediente".
- **Grupo de actuaciones** (`GrupoActuaciones`): se verifican juntas, dictamen único.
- **Expediente** (`Expediente`): agregación oficial de actuaciones `VERIFICADA_FAVORABLE` con misma CCAA + año
  + sector + verificador. Se aprueba o rechaza en conjunto (riesgo de contagio). **No uses esta palabra para
  la unidad de trabajo.**
- **Cuatro estados distintos, cuatro cosas distintas:**

  | Concepto | Valores | Quién lo fija |
  |---|---|---|
  | Veredicto (calidad) | `NO_ELEGIBLE` > `BLOQUEADO` > `SUBSANABLE` > `PREVALIDADO` | Rules Engine |
  | Estado de ciclo (nuestro trabajo) | `ABIERTA … EN_PROCESO … EVALUADA … LISTA_PARA_ENVIO … CERRADA` | Máquina de estados |
  | Estado de plataforma — actuación | `BORRADOR … COMPLETA … VERIFICADA_FAVORABLE …` (8, confirmados) | La plataforma; solo reflejamos |
  | Estado de plataforma — expediente | Provisionales, `NO OFICIAL` (`TODO(API-03)`) | La plataforma; nombres nuestros |

- **Severidades de regla**: `BLOQUEANTE_AMBITO` → `NO_ELEGIBLE` · `BLOQUEANTE_DATOS` → `BLOQUEADO` ·
  `SUBSANABLE` → calcula provisional · `AVISO` → no cambia el veredicto.
- **Resultado de regla**: `CUMPLE` / `FALLA` / `NO_EVALUABLE`. Una `NO_EVALUABLE` no bloquea por sí misma; la
  carencia la recoge una regla `SUBSANABLE` (garantía que el Spec Registry comprueba al cargar).
- **Orden de evaluación**: cabecera bloqueante → ámbito → consistencia → cálculo → post-cálculo → resto.
  Nunca se publica un ahorro apoyado en datos incoherentes.
- **`INT-xx`**: interpretación pendiente. Abiertas: INT-01 (medio), INT-03/04/05 (alto), INT-02/06/07 (bajo);
  propuestas INT-08 (expiración) e INT-09 (inversión). Son criterios propios sin validar, **no** verdad normativa.
- **Marcas de estado en docs**: `F0` (existió en el Engine 0.1 con diseño probado; se reconstruye en la
  Fase 0) · `NUEVO` (diseño aprobado, nunca implementado) · `EXISTE` / `PARCIAL` (implementado en este repo;
  al arrancar no hay ninguno) · `NO DOCUMENTADO` (la plataforma oficial no lo ha publicado → `TODO(API-xx)`).
  La marca antigua `A CONFIRMAR` desaparece: no hay repositorio previo contra el que confirmar; lo que era
  duda de implementación es ahora una decisión de diseño de la Fase 0 y está resuelta en `docs/03`/`docs/04`.
  Las marcas se actualizan en la misma sesión en que cambia el código.

---

## 4. Cómo se orquesta el trabajo

La sesión principal de Claude Code actúa como **orquestador** (`.claude/agents/orquestador-arquitectura.md`)
y delega en subagentes por dominio (`.claude/agents/*.md`). Cada subagente tiene carpetas que puede tocar y
carpetas que no. Protocolo:

1. **Plan antes de código.** El orquestador lee `docs/06`, elige el siguiente entregable con su "hecho cuando",
   y lo descompone en tareas para subagentes con un brief cerrado (qué, dónde, criterio de aceptación,
   qué no tocar). Para trabajo de arquitectura, escribe primero un ADR en `docs/decisiones/` y lo deja
   marcado `PROPUESTA` si la decisión es de Billy.
2. **Paralelo solo sin solapamiento de carpetas.** Dos subagentes nunca escriben en el mismo fichero a la vez.
3. **Puerta de integración.** Nada se da por hecho sin: `pytest -q` en verde, `python evaluar_casos.py` con
   7/7 veredictos y caso A en **305.829,6 kWh/año**, y marcas actualizadas en `docs/03`/`docs/04`.
4. **Un commit por entregable**, mensaje en español con el identificador del plan (`F0.3: …`, `S3.1: …`).
5. **Al cerrar la sesión**: actualizar el estado en `docs/06`, registrar decisiones técnicas en ADR, y listar
   en el resumen final las **decisiones que quedan para Billy** sin tomarlas.

Comandos: `/bootstrap` (primera sesión: esqueleto + Fase 0), `/sprint` (siguiente paso de `docs/06`),
`/contrastar` (docs ↔ código), `/nueva-ficha <CODIGO>` (checklist de `docs/04` §9).

---

## 5. Cómo trabajar

```bash
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"                             # pyyaml openpyxl reportlab pillow pdfplumber pytest ruff
# OCR (opcional; tests e2e con OCR se saltan si faltan): poppler-utils, qpdf, tesseract-ocr-spa
python -m generator.generar                         # regenera los 7 casos y el ground truth
python -m engine.cli expedientes/EXP001-A_completo --md informe.md --json informe.json
python evaluar_casos.py                             # matriz esperado/obtenido
python -m pytest -q
ruff check . && ruff format --check .
```

**Definición de hecho para cualquier cambio:**

- `pytest` en verde. Un test que rompe no se borra ni se relaja: se explica.
- `evaluar_casos.py` 7/7 veredictos correctos; caso A en **305.829,6 kWh/año** (p = 5,55/110 = 5,0455 %).
  Si cambia, o hay bug o hay decisión: ADR en `docs/decisiones/`.
- Nueva regla en código → test que verifica que hace lo que dice su `logica` del YAML.
- Módulo que pasa de `NUEVO` a `EXISTE` → marca actualizada en `docs/03`/`docs/04` en la misma sesión.
- Estructura nueva → `docs/01` actualizado en la misma sesión.

**Qué no cambias sin revisión de Billy:** `spec/*.yaml` activa, `data/`, `expedientes/_resultados_esperados/`,
severidades de reglas, criterios INT-xx, cualquier texto de `docs/00`. Prepara el diff y déjalo listo.

**Diff pendiente, NO aprobado:** `spec/propuestas/IND240_v1.2.diff.md` (R-TMP-03 con INT-08, R-DOC-01
`diferencial: false`, herencia de `cabecera_v1.yaml`, INT-09, `version_spec 0.2.0`). No lo actives.

---

## 6. Decisiones abiertas de Billy — no las tomes tú

Proveedor LLM y condiciones de datos · umbral de activación de agentes en producción · vía del perfil
Modificación (API-09) · aprobación del diff v1.2 y de `cabecera_v1.yaml` · familias `R-CAB`, `R-GRP/R-EXP`,
`R-XCK`, `R-REQ` como diseño · Expediente Builder en Sprint 4 · segunda ficha (vecina vs. frío) · módulo de
singulares/CVP · posición comercial respecto a Moeve · orden de contactos comerciales.

De la Fase 0 y de la revisión normativa (`ADR-002` §6, `ADR-003`): **fila de 110 kW del cuadro 6** (5,55 frente a
6,11 kW; sostiene el criterio de aceptación de 305.829,6 y nadie ha podido contrastarla contra el DOUE) ·
verificación de las 38 filas `pendiente` · INT-10 a INT-15 · severidad de `R-CON-07` y desdoble de `R-AMB-01` ·
`instalacion_personal_propio` · léxicos de lectura a la spec v1.2.

Del front por perfil (`ADR-050`, en `PROPUESTA`): **C1 stack de presentación** (subsume B1 de `ADR-007`) ·
C2 rol inferido frente a cambio explícito · C3 forma del portal externo (depende de A1 y A2) · C4 agente de
front en `.claude/agents/` · C5 `ADM-MOD` en solo lectura hasta tener clientes · C6 idiomas y accesibilidad ·
C7 aprobar las cuatro superficies y el orden FR0–FR6. Nada de `api/` ni de `front/` se construye antes de C1
y C7: el contrato va primero (`FR0`) para que la lógica de negocio no acabe en la interfaz.

De perfiles y dashboards (`ADR-005`, `ADR-006` §"Pendiente", `ADR-007`): A1 a A8 (instalador, cliente,
reasignación, vistas, doble función, firma manual con API activa, y si las capacidades se modelan ya) · umbrales
de las métricas · interfaz de los dashboards (DB5) · **revisión jurídica de la monitorización de trabajadores
antes del primer cliente**. Lista única y al día en `docs/decisiones/ADR-001` §3.

Cuando una tarea choque con una de estas, haz lo que no dependa de la decisión, deja la alternativa preparada
y márcalo en el resumen de sesión.

---

## 7. Cómo leer los números heredados

"7/7 casos correctos" y "61 tests" son resultados del Engine 0.1 original con documentos que el extractor por
reglas ya conocía. No demuestran precisión sobre un expediente real no visto. Al reconstruir, úsalos como
**regresión y criterio de aceptación**, no como evidencia de robustez ni como cifra a "igualar" a toda costa:
si el nuevo banco de pruebas tiene 80 tests o 55, lo que importa es que cubra `docs/05` §4.

---

*Mantener vivo: si este fichero y el código discrepan, uno de los dos está mal y se arregla en la misma sesión.
Las decisiones de negocio se cambian primero en `docs/00`, después aquí.*
