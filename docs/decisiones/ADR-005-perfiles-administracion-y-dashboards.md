# ADR-002 — Administración interna en dos planos con dashboards operativo y técnico

**Estado**: ACEPTADA
**Fecha**: 2026-09-19
**Decide**: Billy (separación de planos y dashboards) · Claude (límites técnicos derivados de las reglas de oro)
**Ámbito**: `docs/03` (modelo canónico, S7), `docs/decisiones/`, log de eventos (N8), `telemetria/`, consola (S4)

## Contexto

Ningún documento del proyecto definía perfiles de usuario ni un rol administrador. El gobierno del modelo se ejercía solo desde el repositorio: comandos de Claude Code (`/sprint`, `/mejorar`, `/implantar`), aprobación de diffs en `spec/propuestas/` y ADR.

Lo documentado antes de esta decisión:

- Decisiones reservadas a Billy: `CLAUDE.md` §6 y `docs/decisiones/` (paquete de agentes, antes `12` §5).
- Dos tipos de tenant: sujeto delegado y sujeto obligado directo (≥ 50 MWh), con aislamiento de datos, claves y logs (`docs/03`, antes `11` §3.10; `07` §11).
- Telemetría definida en `telemetria/*.jsonl`: ejecuciones, `llamada_llm` y `pasada_mejora`.
- Métrica norte en `docs/00` §1.1: horas de trabajo especializado sustituidas y porcentaje de actuaciones que pasan la primera revisión sin subsanación.

Sin un perfil administrador en el producto no hay forma de operar tenants ni de gobernar el modelo cuando exista una plataforma desplegada, y las acciones de administración no quedan trazadas en el log.

## Opciones consideradas

1. **Opción A — Sin perfil en el producto; gobierno solo desde el repositorio.** Ventaja: cero desarrollo. Inconveniente: no escala a clientes; alta de tenants y accesos de soporte fuera de trazabilidad. Rompe la regla de que toda acción humana relevante quede en el log.
2. **Opción B — Un único perfil administrador con todos los permisos.** Ventaja: simple. Inconveniente: mezcla cambiar cómo piensa el sistema (specs, reglas, agentes) con gestionar quién lo usa (tenants, usuarios); con un solo titular, un error operativo puede tocar el modelo.
3. **Opción C — Dos planos separados: gobierno del modelo y administración de la operación.** Ventaja: permisos sin solapamiento, trazabilidad por rol, reparto directo si entra una segunda persona. Inconveniente: fricción mientras el titular sea una sola persona.

Para los dashboards:

1. **Opción D — Solo los informes de `/mejorar` y `evaluar_casos.py`.** Insuficiente para operar tenants.
2. **Opción E — Dos dashboards: operativo de la plataforma y técnico.** Cubren negocio y salud del sistema por separado.

## Decisión

**Opción C y opción E** (Billy, 19/09/2026). El administrador se separa en dos perfiles sin permisos solapados, y ambos consultan en solo lectura un dashboard operativo (nº de actuaciones, estados…) y un dashboard técnico (latencias, errores…).

### Perfiles

| Código | Perfil | Gobierna | Puede | No puede |
|---|---|---|---|---|
| `ADM-MOD` | Propietario del modelo | Cómo piensa el sistema | Activar specs, cabecera y reglas (nueva `version_spec`); severidades e `INT-xx`; activar o desactivar agentes A1–A9 y sus umbrales; activar prompts que hayan pasado `/implantar`; fijar presupuestos y umbrales de alerta; aceptar `MEJ-nnn`; aprobar diffs normativos de A6; mantener `HUECOS.md` | Gestionar tenants o usuarios; ver datos de un tenant |
| `ADM-OPS` | Administrador de operación | Quién usa el sistema | Alta, baja y suspensión de tenants; capacidad de delegación; solicitar y usar accesos de soporte; estado de integración por tenant; auditoría global | Activar specs, reglas, prompts o agentes; cambiar severidades o `INT-xx` |

Si una persona tiene los dos, actúa con uno a la vez. El cambio de rol es explícito y queda en el log. Ambos requieren segundo factor.

### Controles previos a la activación en `ADM-MOD`

Activar spec, severidades o `INT-xx` exige tests en verde, replay de actuaciones pasadas (F-22) con informe de veredictos que cambian, y ADR. Activar un agente exige conjunto de evaluación y línea base del rol. Activar un prompt exige `CHG-nnn` en `INTEGRADO`.

### Límites comunes a los dos perfiles (derivados de las reglas de oro)

- No forzar veredictos: se corrige la spec, con versión y replay.
- No firmar ni simular la firma; no custodiar certificados de representante.
- No modificar datos tras `EN_PLATAFORMA` fuera de un requerimiento oficial.
- No editar el log de eventos, la telemetría ni el ground truth sin ADR.
- Sin acceso a contenido documental de tenants por defecto: solo metadatos y agregados. Un acceso a una actuación concreta es temporal, con motivo, y queda en auditoría.

### Dashboards

Operativo y técnico, en solo lectura para ambos perfiles. Catálogo de métricas, vistas y plan de construcción en ADR-006.

## Consecuencias

- **Modelo canónico** (`docs/03`, `engine/modelo/`): entidades `Usuario` y `Rol`; `actor.rol` en todo evento de actor humano. Encaje en S3.1.
- **Log de eventos**: eventos de administración (`SpecActivada`, `AgenteActivado`/`Desactivado`, `TenantAlta`/`Baja`, accesos de soporte). Catálogo completo en ADR-005.
- **Dashboards**: se construyen según ADR-006.
- **Catálogo de perfiles**: el de este ADR se amplía con los perfiles de tenant y externos en ADR-005, que es la referencia vigente para la matriz de permisos.
- **Riesgo aceptado**: con un solo aprobador no hay segunda firma. Control compensatorio técnico (tests, replay, ADR). Si entra una segunda persona, las activaciones de spec pasan a doble aprobación.
- **Pendiente**: cuándo se construye la interfaz de administración (ADR-006); condiciones del acceso de soporte (ADR-005).

## Verificación

- `docs/03` recoge `Usuario`, `Rol` y `actor.rol` (revisión con `/contrastar`).
- Tests de autorización (a crear con S3.1, `tests/test_permisos_*.py`): un `ADM-OPS` no puede generar `SpecActivada`; un `ADM-MOD` no puede generar `TenantAlta`.
- Ningún evento de administración carece de `actor.rol` (test sobre el log).
