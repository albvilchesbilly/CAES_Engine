# ADR-050 — Front por perfil: cuatro superficies adaptadas por capacidades

**Estado**: ACEPTADA en C1 y C7 (Billy, 19/09/2026) · PROPUESTA en C2 a C6
**Fecha**: 2026-09-19
**Decide**: Billy (superficies, stack de presentación, inferencia del rol, portal externo, orden de construcción) · Claude (arquitectura técnica del front y reglas de interfaz derivadas de las reglas de oro)
**Ámbito**: `api/` (nuevo), `front/` (nuevo), `docs/front/` (nuevo), `docs/01`, `docs/06`, `CLAUDE.md` §6, `.claude/agents/` (agente de front, propuesto), `tests/test_api_*.py`, `front/**/tests/`

## Contexto

ADR-005 define 8 perfiles y 51 capacidades, y ADR-006 define 4 vistas de dashboard. Ningún documento define cómo es la interfaz de cada perfil.

Lo documentado:

- **Consola de revisión** (S4.4, `docs/06`): cola de escalados, conflictos, correcciones y tareas pendientes consumidas del simulador, centrada en lo previo a la firma. Es la única pieza de interfaz que está en el plan.
- **Frontera de firma** (`docs/02`, `docs/00`): la firma de actos administrativos es humana, con certificado de representante. La automatización termina en `COMPLETA`. Solo registramos que la firma ocurrió (`FirmaRegistrada`, actor `humano`).
- **Transiciones humanas** (ADR-005): CAP-10 (`RevisionAprobada`) y CAP-22 (`FirmaRegistrada`) son los únicos disparadores humanos de sus transiciones.
- **Dashboards** (ADR-006): presentación en fase A (informes estáticos) y fase B (API de lectura con interfaz), con la interfaz pendiente de decisión (B1, B2).
- **Segmento prioritario** (`docs/08` §2): el delegado que además instala o mantiene, donde una persona suele acumular funciones.
- **Entorno de desarrollo**: Claude Code en la web conectado a GitHub, con orquestador y agentes en `.claude/agents/`.

No documentado:

- Stack de presentación (ADR-006 B1).
- Carpetas para la capa de API y para el front: `docs/01` no las contempla.
- Contrato de comandos y lecturas entre el front y el Engine.
- Forma de acceso de instaladores y clientes (ADR-005 A1, A2).
- Idiomas de la interfaz y requisitos de accesibilidad.

## Opciones consideradas

**Estructura**

1. **Opción A — Un front por perfil (8).** Ventaja: cada interfaz optimizada para su usuario. Inconveniente: ocho superficies que mantener; un usuario con varios perfiles salta entre apps; contradice ADR-005, donde un perfil es un paquete de capacidades y no una aplicación.
2. **Opción B — Cuatro superficies agrupadas por contexto de uso, que se adaptan a las capacidades del usuario.** Ventaja: coste acotado, coherente con ADR-005, cambiar un perfil no exige tocar pantallas. Inconveniente: cada pantalla debe resolver qué muestra según capacidades.
3. **Opción C — Una sola aplicación para todos.** Ventaja: una sola base. Inconveniente: mezcla usuarios internos con externos y tenants, amplía la superficie de ataque del portal externo e impone escritorio a quien trabaja desde la obra.

**Rol ejercido en el workspace del tenant** (`actor.rol` es obligatorio en todo evento humano, ADR-005)

1. **Opción D — Cambio de rol explícito**, como en la consola interna. Ventaja: trazabilidad inequívoca. Inconveniente: fricción diaria para el delegado pequeño que acumula tres perfiles.
2. **Opción E — Rol inferido por la capacidad ejercida y por el contexto de pantalla**, visible en todo momento. Ventaja: sin fricción y con trazabilidad equivalente, porque casi todas las capacidades que generan eventos pertenecen a un solo perfil. Inconveniente: regla de desempate necesaria para las capacidades compartidas.

**Stack de presentación** (decisión de Billy, ADR-006 B1)

1. **Opción F — Un solo stack web (React con TypeScript) para las cuatro superficies.** Ventaja: una tecnología, componentes compartidos (visor de evidencias, rótulos, estados), buen rendimiento con Claude Code. Inconveniente: arranque algo más lento para la consola interna.
2. **Opción G — Híbrido: herramienta rápida en Python para la consola interna y React para tenant y externos.** Ventaja: consola interna en días. Inconveniente: dos tecnologías, componentes duplicados y reglas de interfaz aplicadas dos veces.

**Orden**

1. **Opción H — Pantallas primero.** Riesgo: lógica de negocio escrita en el front y endpoints inventados.
2. **Opción I — Contrato de comandos y lecturas primero (FR0), pantallas después.** El front solo consume el contrato.

## Decisión

**Recomendación: opción B, opción E, opción I, y opción F como recomendación de stack pendiente de Billy.** Cuatro superficies adaptadas por capacidades mantienen el coste bajo y son coherentes con ADR-005. Inferir el rol elimina la fricción del segmento prioritario sin perder trazabilidad. Empezar por el contrato impide que las reglas de negocio acaben en la interfaz. Un solo stack evita aplicar dos veces las reglas de interfaz.

### Superficies

| Superficie | Perfiles | Dispositivo | Acceso |
|---|---|---|---|
| **Workspace del tenant** | `T-RES`, `T-OPE`, `T-REV` | Escritorio | Cuenta de usuario del tenant |
| **Portal externo** | `EXT-INS`, `EXT-CLI` | Móvil primero | Pendiente de ADR-005 A1 y A2 (recomendación para cliente: enlace sin cuenta) |
| **Consola interna** | `ADM-MOD`, `ADM-OPS` | Escritorio | Cuenta interna con segundo factor y cambio de rol explícito (ADR-002) |
| **Sin front** | `SYS-API` | — | Aparece como identidad técnica en el panel de integración de `ADM-OPS` (CAP-64) y `T-RES` |

### Front por perfil

| Perfil | Pantalla de inicio | Pantallas y acciones | Nunca ve ni hace |
|---|---|---|---|
| `T-OPE` | **Mis actuaciones**: bandeja por estado de ciclo | Alta guiada de actuación (CAP-01) · subida con clasificación de A1 y checklist "qué te falta" (CAP-02, CAP-04) · subsanación redactada por A5 (CAP-09) · preparar y ordenar entrega (CAP-11, CAP-12) · Expediente Builder (CAP-13, sujeto a S4.1) · tareas de la plataforma (CAP-14) | Corregir datos, aprobar, registrar firma |
| `T-REV` | **Cola de revisión** priorizada por motivo y antigüedad | Vista de revisión (ver abajo) · corregir con justificación (CAP-05, CAP-06) · observaciones de A8 (CAP-07) · descartes (CAP-08) · subsanación (CAP-09) · aprobar `LISTA_PARA_ENVIO` (CAP-10) · requerimientos y discrepancias (CAP-15, CAP-16) | Forzar un veredicto; editar tras `EN_PLATAFORMA` |
| `T-RES` | **Pendiente de mí** + vista `O-FUN` | Verificador (CAP-20) · composición del expediente (CAP-21) · registrar firma (CAP-22) · desistimiento (CAP-23) · equipo y perfiles (CAP-30, CAP-31) · `O-EQU` con aviso (CAP-36) · reasignar (CAP-32, sujeto a A3) · política (CAP-33) · accesos de soporte (CAP-34) · estado de integración | Revisar o preparar, salvo que tenga también esos perfiles |
| `EXT-INS` / `EXT-CLI` | **Enlace de actuación**, sin navegación | "Qué te falta" en lenguaje no técnico · subida por foto o PDF · estado simplificado (CAP-40) | Cabecera económica, otras actuaciones, payloads, veredictos técnicos |
| `ADM-OPS` | **Tenants** con salud de integración | Alta, baja y suspensión; primer `T-RES` (CAP-60) · capacidad de delegación (CAP-61) · accesos de soporte con banner mientras estén vigentes (CAP-62, CAP-63) · auditoría (CAP-65) · `O-GLO`, `T-TEC` (CAP-66, CAP-67) | Specs, reglas, agentes, prompts; contenido documental sin acceso autorizado |
| `ADM-MOD` | **`T-TEC` + bandeja de gobierno** | Specs y versiones, agentes y umbrales, prompts, presupuestos, `MEJ-nnn`, diffs de A6, discrepancias (CAP-50 a CAP-58) · `O-GLO` | Tenants, usuarios, cualquier dato de un tenant |

### Pantallas críticas

- **Vista de revisión (`T-REV`).** Pantalla partida: a la izquierda, el documento con la evidencia resaltada (página y texto literal); a la derecha, variables, reglas, cálculo y veredicto, cada dato enlazado a su cita. "Aprobar" solo se activa sin bloqueantes abiertos. No existe control para cambiar el veredicto: se corrige el dato y el motor recalcula. Es el punto de medida candidato para los minutos de revisión (ADR-006 B5).
- **Registro de firma (`T-RES`).** La acción se llama "Registrar firma realizada", nunca "Firmar". Recoge quién firmó, cuándo y la referencia. Con `SYS-API` activo, el paso a `EN_PLATAFORMA` espera la confirmación de la plataforma (ADR-005 A7).
- **Acceso de soporte (`ADM-OPS`).** Mientras un acceso está vigente, un banner fijo muestra la actuación, el motivo y la caducidad. Al caducar, la sesión pierde el acceso sin recargar.

### Inferencia del rol en el workspace

- Si la capacidad que genera el evento pertenece a un solo perfil del usuario, ese es el `actor.rol`.
- Las lecturas (CAP-03, CAP-04, CAP-14) no generan eventos y no necesitan rol.
- Capacidades compartidas que sí generan eventos: CAP-02 (`T-OPE`, `T-REV`) y CAP-09 (`T-OPE`, `T-REV`). El rol lo fija el contexto de pantalla: desde la cola de revisión, `T-REV`; desde la bandeja de actuaciones, `T-OPE`.
- La cabecera muestra siempre el rol con el que se va a actuar ("actuando como Revisor").
- La inferencia ocurre en el servidor. El front solo la muestra.

### Reglas de interfaz

| ID | Regla | Origen |
|---|---|---|
| R-UI-01 | Ocultar un control no es autorización: cada comando valida capacidad y tenant en el servidor | ADR-005 |
| R-UI-02 | Ningún control permite fijar, forzar o cambiar un veredicto | Reglas de oro |
| R-UI-03 | Ningún control se llama "Firmar"; la firma solo se registra | `docs/02` |
| R-UI-04 | Toda corrección exige justificación y queda en el log | ADR-005 CAP-05 |
| R-UI-05 | Tras `EN_PLATAFORMA`, solo lectura salvo flujo de requerimiento oficial | Reglas de oro |
| R-UI-06 | kWh prevalidados rotulados "no son CAE emitidos"; estados de expediente "NO OFICIAL" | ADR-006 |
| R-UI-07 | `SIN DATO` nunca se muestra como cero | ADR-006 |
| R-UI-08 | Marca de origen de datos (sintético o real) en todo panel | ADR-006 |
| R-UI-09 | Todo dato extraído muestra o enlaza su cita (documento, página, texto literal) | Contrato de agentes |
| R-UI-10 | Aviso visible de registro de actividad para usuarios de tenant mientras exista `O-EQU` | ADR-005 |
| R-UI-11 | El front no contiene lógica de negocio: no calcula, no evalúa reglas, no decide transiciones | Opción I |
| R-UI-12 | El portal externo no recibe del servidor campos que el perfil no puede ver (no basta con no pintarlos) | ADR-005, aislamiento |

### Arquitectura

```
engine/ ──► api/ (comandos y lecturas por capacidad) ──► front/
                                                          ├── compartido/   sistema de diseño, visor de evidencias, rótulos
                                                          ├── workspace/    T-RES, T-OPE, T-REV
                                                          ├── externo/      EXT-INS, EXT-CLI
                                                          └── consola/      ADM-MOD, ADM-OPS
```

Regla de dependencias: `front/` solo habla con `api/`; `api/` lee de `engine/` y `metricas/`; nada importa de `api/` ni de `front/`. Con `front/` apagado, el Engine sigue funcionando.

### Paquete por pantalla para Claude Code

Cada pantalla se entrega con tres piezas en `docs/front/`:

| Pieza | Ruta | Función |
|---|---|---|
| Spec de pantalla | `docs/front/pantallas/<perfil>-<pantalla>.md` | **Contrato**: objetivo, capacidades, lecturas consumidas, comandos disparados, estados, reglas R-UI aplicables y criterios de aceptación |
| Mockup | `docs/front/mockups/<perfil>-<pantalla>.html` | Referencia visual de disposición y flujo. No es código base |
| Criterios de aceptación | Dentro de la spec, convertidos en tests al implantar | "Hecho cuando" verificable |

Si el mockup y la spec discrepan, manda la spec.

### Plan de construcción

| # | Entregable | Hecho cuando… | Depende de |
|---|---|---|---|
| FR0 | Contrato de comandos y lecturas por capacidad en `api/`; sistema de diseño mínimo en `front/compartido/` | Cada capacidad de ADR-005 tiene su comando o lectura; tests de concesión y denegación en verde desde la API; rótulos R-UI-06 a 08 disponibles como componentes | S3.1, ADR-005 A8, stack (B1) |
| FR1 | Workspace `T-REV`: cola y vista de revisión | Cumple S4.4 sobre el simulador; R-UI-02, 04, 05, 09 verificadas por test | FR0, S3.5 |
| FR2 | Workspace `T-OPE`: bandeja, alta, subida y "qué te falta" | Un caso sintético va de alta a `EN_REVISION_HUMANA` solo desde el front | FR0 |
| FR3 | Workspace `T-RES`: pendiente de mí, registro de firma, equipo, `O-FUN` | R-UI-03 y R-UI-10 verificadas; `O-FUN` da las mismas cifras que el informe estático de DB1 | FR0, DB1 |
| FR4 | Portal externo | R-UI-12 verificada por test sobre las respuestas de la API | FR0, ADR-005 A1 y A2 |
| FR5 | Consola `ADM-OPS` | Ciclo completo de acceso de soporte probado de extremo a extremo | FR0, primer tenant real |
| FR6 | Consola `ADM-MOD`, primero en solo lectura | `T-TEC` y bandeja de gobierno visibles; las activaciones siguen por repositorio (`/implantar`, ADR) hasta nueva decisión | FR0, DB0 |

## Consecuencias

- **Código nuevo**: `api/` y `front/` con la estructura anterior; `tests/test_api_*.py`; tests de front dentro de `front/`.
- **Documentación**: `docs/01` (carpetas `api/`, `front/`, `docs/front/` y su regla de dependencias); `docs/06` (líneas FR0 a FR6; FR1 absorbe S4.4); `CLAUDE.md` §6 (decisiones pendientes); ADR-006 B1 y B2 quedan vinculadas a C1 y al plan FR.
- **Agente de front** (propuesto): `.claude/agents/front.md` con R-UI-01 a R-UI-12 como reglas cerradas, trabajo solo contra el contrato de `api/` y la spec de pantalla por encima del mockup. Se entrega aparte, con el paquete de FR0.
- **Marcas de estado**: FR0 a FR6 nacen `BLOQUEADO (decisión)` o `PENDIENTE` según su dependencia.
- **Riesgos**:
  - Lógica de negocio filtrada al front. Mitigación: R-UI-11, contrato primero, agente de front.
  - Mockup tomado como especificación. Mitigación: la spec manda y lleva los criterios de aceptación.
  - Consola `ADM-MOD` que duplica el flujo del repositorio. Mitigación: FR6 en solo lectura.
  - Portal externo expuesto a más datos de los necesarios. Mitigación: R-UI-12 en servidor.
- **Pendiente (Billy)**:
  - ~~C1 · Stack de presentación~~ → **APROBADO por Billy el 19/09/2026: opción F**, un solo stack web
    (React con TypeScript) para las cuatro superficies. Cierra también B1 de `ADR-007`.
  - C2 · Inferencia del rol en el workspace (opción E) frente a cambio explícito (opción D). Recomendación: E.
  - C3 · Forma del portal externo: depende de ADR-005 A1 y A2.
  - C4 · Aprobar el agente de front en `.claude/agents/`.
  - C5 · FR6 en solo lectura hasta tener clientes.
  - C6 · Idiomas de la interfaz y nivel de accesibilidad exigido.
  - ~~C7 · Aprobar las superficies y el orden~~ → **APROBADO por Billy el 19/09/2026**: opción B (cuatro
    superficies adaptadas por capacidades) y el orden FR0 → FR6. Billy reafirma además que **el contrato
    antes que las pantallas no es negociable**: es práctica establecida, no una preferencia de este proyecto.

## Verificación

A crear con FR0 y siguientes:

- `tests/test_api_capacidades.py`: para cada capacidad, un comando concedido y otro denegado según la matriz de ADR-005, llamando a la API sin pasar por el front.
- `tests/test_api_aislamiento.py`: ninguna lectura de un perfil de tenant o externo devuelve datos de otro tenant ni campos fuera de su ámbito (R-UI-12).
- `tests/test_api_rol_inferido.py`: CAP-02 y CAP-09 registran `actor.rol` según el contexto; el resto, según el único perfil que concede la capacidad.
- Tests de front por pantalla, derivados de los criterios de aceptación de cada spec: ausencia de control de veredicto (R-UI-02), ausencia de "Firmar" (R-UI-03), justificación obligatoria (R-UI-04), solo lectura tras `EN_PLATAFORMA` (R-UI-05), rótulos presentes (R-UI-06 a 08).
- `/contrastar`: `docs/01`, `docs/06` y `CLAUDE.md` §6 reflejan este ADR.
