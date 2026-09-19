# ADR-006 — Catálogo de perfiles y matriz de permisos por capacidades

**Estado**: PROPUESTA
**Fecha**: 2026-09-19
**Decide**: Billy (perfiles, acceso de externos, reglas de supervisión de equipos) · Claude (modelo técnico de autorización)
**Ámbito**: `docs/03` (modelo canónico N7, S7), `engine/modelo/`, `engine/estados.py`, log de eventos (N8), `salida/transporte/`, consola (S4), `tests/test_permisos_*.py`

## Contexto

ADR-005 creó los dos perfiles internos de administración, pero no había perfiles para quien usa la plataforma: el sujeto delegado, su equipo y las partes externas. Tampoco estaba definido qué acciones puede hacer cada uno sobre las actuaciones.

Referencias:

- **Plataforma oficial** (presentación OMIE/MIBGAS del 30/06/2026, `docs/02`, antes `10` §1): dentro de cada agente hay usuarios de **Firma**, **Modificación** y **Consulta**. El usuario **Responsable** (con poder de Firma) da de alta, baja y renueva al resto. El propietario inicial no accede para actuaciones estandarizadas. La firma de actos administrativos requiere certificado de representante.
- **Procesos del Engine** P0–P10 y máquina de estados (`docs/03`, antes `07` §3 y `11` §3.3–3.4): solo una actuación `PREVALIDADO` revisada por un humano pasa a `LISTA_PARA_ENVIO`; `ENTREGADA` → `EN_PLATAFORMA` exige `FirmaRegistrada` de actor humano.
- **Destinatarios de informe** (F-17): cliente, instalador y tenant.
- **Segmentos** (`docs/08` §2): el prioritario es el delegado que además instala o mantiene, donde una persona suele acumular funciones.

Decisiones de Billy tomadas en la sesión del 19/09/2026:

- **D3**: el sujeto delegado tiene un administrador que ve toda la actividad de su tenant y de los usuarios de su equipo que registran y validan actuaciones, con dashboards funcionales y operativos de su propio tenant.
- **D4**: administrador y responsable del tenant se consolidan en un único rol.

No documentado: si un usuario de Modificación puede ser un tercero o una cuenta de sistema (`HUECOS.md`, API-09); cómo se consulta la capacidad de delegación disponible de un sujeto.

## Opciones consideradas

**Modelo de autorización**

1. **Opción A — Replicar solo los tres perfiles oficiales (Firma, Modificación, Consulta).** Ventaja: familiar para el delegado. Inconveniente: no existe el revisor técnico, que es quien exigen nuestras reglas de transición; no cubre externos ni administración interna.
2. **Opción B — Perfiles fijos definidos en código.** Ventaja: simple de implementar. Inconveniente: cada cambio de perfil exige migración y código; revertir D4 para un cliente grande sería caro.
3. **Opción C — Capacidades atómicas y perfiles como paquetes de capacidades.** Ventaja: los perfiles cambian sin tocar el código de autorización; un usuario puede acumular perfiles; cada evento registra el perfil ejercido. Inconveniente: más entidades en el modelo desde el Sprint 3.

**Rol del responsable del tenant**

1. **Opción D — Administrador del tenant y responsable separados.** Segregación de funciones, pero sin equivalente en la plataforma oficial y artificial para delegados pequeños.
2. **Opción E — Un único rol `T-RES`** que gestiona el equipo, lo ve todo y ejecuta los actos del sujeto. Coincide con el Responsable oficial.

## Decisión

**Opción E** (Billy, D4). **Opción C recomendada** para el modelo de autorización, porque hace barata cualquier revisión futura de perfiles, incluida la de D4 para un tenant grande. El catálogo y la matriz siguientes quedan `PROPUESTA` hasta que Billy los apruebe.

### Catálogo de perfiles

| Código | Perfil | Ámbito de datos | Equivalente oficial | Estado |
|---|---|---|---|---|
| `T-RES` | Responsable del tenant | Todo su tenant, con contenido | Responsable con Firma | Decidido (D3, D4) |
| `T-OPE` | Operador del tenant | Actuaciones de su tenant | Modificación | Propuesta |
| `T-REV` | Revisor técnico | Actuaciones de su tenant | Sin equivalente | Propuesta |
| `EXT-INS` | Instalador / ingeniería | Solo sus actuaciones | Sin acceso | Abierto |
| `EXT-CLI` | Cliente / propietario inicial | Solo sus actuaciones | Sin acceso para estandarizadas | Abierto |
| `ADM-MOD` | Propietario del modelo | Global, solo agregados | — | Decidido (ADR-005) |
| `ADM-OPS` | Administrador de operación | Global, solo metadatos | — | Decidido (ADR-005) |
| `SYS-API` | Identidad de sistema para la API oficial | Tenant al que sirve | Modificación técnico | Condicionado a API-09 |

### Capacidades

**Trabajo sobre actuaciones**

| ID | Capacidad | Evento |
|---|---|---|
| CAP-01 | Abrir actuación y asignar partes (P0) | `ActuacionAbierta`, `TenantAsignado` |
| CAP-02 | Subir documentación (P1) | `DocumentoRegistrado` |
| CAP-03 | Consultar la actuación completa: documentos, evidencias, conflictos, cálculo, veredicto, historial | Lectura |
| CAP-04 | Consultar el "qué te falta" y el informe de su destinatario (F-10, F-17) | Lectura |
| CAP-05 | Resolver conflicto o corregir dato, con justificación (P4) | `DatoCorregidoPorHumano` |
| CAP-06 | Resolver desacuerdo entre extractores (P2) | `DatoCorregidoPorHumano` |
| CAP-07 | Revisar observaciones de A8 (P6) | `ObservacionRevisada` (nuevo) |
| CAP-08 | Confirmar descarte de un `NO_ELEGIBLE` | `ActuacionDescartada` (nuevo) |
| CAP-09 | Revisar y enviar al cliente la subsanación redactada por A5 (P7) | `SubsanacionSolicitada{origen=interno}` |
| CAP-10 | Aprobar el paso a `LISTA_PARA_ENVIO` | `RevisionAprobada` (nuevo) |
| CAP-11 | Construir payload o paquete de handoff (P8) | `PayloadConstruido`, `ManifiestoGenerado` |
| CAP-12 | Ordenar la entrega (handoff o API) | `EntregadoADelegado` / `EnviadoAPI` |
| CAP-13 | Proponer grupos y expedientes con el Expediente Builder (P10) | `GrupoPropuesto`, `ExpedientePropuesto` |
| CAP-14 | Consultar estados y tareas de la plataforma oficial (P9) | Lectura |
| CAP-15 | Confirmar la interpretación de A9 de un requerimiento | `RequerimientoInterpretado{confirmado}` |
| CAP-16 | Decidir ante una discrepancia con el cálculo de la plataforma | `DiscrepanciaResuelta` (nuevo) |

**Actos del sujeto**

| ID | Capacidad | Evento |
|---|---|---|
| CAP-20 | Elegir o validar el verificador | `VerificadorAsignado` |
| CAP-21 | Aprobar la composición del expediente antes de firmar | `ExpedienteAprobado` (nuevo) |
| CAP-22 | Registrar la firma: quién firmó, cuándo y referencia | `FirmaRegistrada` |
| CAP-23 | Registrar un desistimiento | `DesistimientoRegistrado` |

**Gobierno del tenant**

| ID | Capacidad | Evento |
|---|---|---|
| CAP-30 | Alta, baja y asignación de perfiles a usuarios del tenant | `UsuarioAlta`, `UsuarioBaja`, `RolAsignado` (nuevos) |
| CAP-31 | Ver la actividad de todos los usuarios del tenant | Lectura |
| CAP-32 | Reasignar actuaciones y tareas entre usuarios | `ActuacionReasignada` (nuevo) |
| CAP-33 | Configurar la política del tenant | `PoliticaTenantCambiada` (nuevo) |
| CAP-34 | Autorizar o denegar un acceso de soporte | `AccesoSoporteAutorizado` / `Denegado` (nuevos) |
| CAP-35 | Dashboard operativo, vista funcional del tenant (ADR-007) | Lectura |
| CAP-36 | Dashboard operativo, vista de equipo del tenant (ADR-007) | Lectura |

**Externos**

| ID | Capacidad | Evento |
|---|---|---|
| CAP-40 | Consultar el estado simplificado de sus propias actuaciones | Lectura |

**Gobierno del modelo**

| ID | Capacidad | Evento |
|---|---|---|
| CAP-50 | Activar spec, cabecera o familia de reglas | `SpecActivada` (nuevo) |
| CAP-51 | Cambiar severidades; abrir, cerrar o reinterpretar `INT-xx` | `SpecActivada` |
| CAP-52 | Activar o desactivar agentes A1–A9; fijar umbrales | `AgenteActivado` / `Desactivado` (nuevos) |
| CAP-53 | Activar versiones de prompt o router | `PromptActivado` (nuevo) |
| CAP-54 | Fijar presupuestos y umbrales de alerta | `UmbralCambiado` (nuevo) |
| CAP-55 | Aceptar o descartar propuestas `MEJ-nnn` | Registro en `docs/mejoras/` |
| CAP-56 | Aprobar o rechazar diffs normativos de A6 | `SpecActivada` o ADR de rechazo |
| CAP-57 | Mantener `HUECOS.md` y el registro de `INT-xx` | Commit |
| CAP-58 | Recibir aviso de toda `DiscrepanciaCalculoPlataforma` | Notificación |

**Operación interna**

| ID | Capacidad | Evento |
|---|---|---|
| CAP-60 | Alta, baja y suspensión de tenants; alta del primer `T-RES` | `TenantAlta`, `TenantBaja`, `TenantSuspendido` (nuevos) |
| CAP-61 | Registrar la capacidad de delegación disponible | `CapacidadActualizada` (nuevo) |
| CAP-62 | Solicitar un acceso de soporte a una actuación concreta | `AccesoSoporteSolicitado` (nuevo) |
| CAP-63 | Usar un acceso de soporte autorizado y vigente | `AccesoSoporteUsado` (nuevo) |
| CAP-64 | Ver el estado de integración de cada tenant | Lectura |
| CAP-65 | Consultar la auditoría global | Lectura |
| CAP-66 | Dashboard operativo, vista global (ADR-007) | Lectura |
| CAP-67 | Dashboard técnico (ADR-007) | Lectura |

**Sistema**

| ID | Capacidad | Evento |
|---|---|---|
| CAP-70 | Transportar a la API oficial: enviar borrador, consultar estados, tareas y notificaciones | `EnviadoAPI`, `EstadoPlataformaRecibido`, `TareaPendienteRecibida` |

### Matriz

✅ tiene la capacidad · — no la tiene · (?) pendiente de decisión

| Capacidad | T-RES | T-OPE | T-REV | EXT-INS | EXT-CLI | ADM-MOD | ADM-OPS | SYS-API |
|---|---|---|---|---|---|---|---|---|
| CAP-01 Abrir actuación | — | ✅ | — | — | — | — | — | — |
| CAP-02 Subir documentación | — | ✅ | ✅ | ✅ (?) | ✅ (?) | — | — | — |
| CAP-03 Consultar actuación completa | ✅ | ✅ | ✅ | — | — | — | solo con CAP-63 | — |
| CAP-04 "Qué te falta" e informe | ✅ | ✅ | ✅ | ✅ (?) | ✅ (?) | — | — | — |
| CAP-05 Resolver conflicto o corregir dato | — | — | ✅ | — | — | — | — | — |
| CAP-06 Resolver desacuerdo de extractores | — | — | ✅ | — | — | — | — | — |
| CAP-07 Revisar observaciones de A8 | — | — | ✅ | — | — | — | — | — |
| CAP-08 Confirmar descarte | — | — | ✅ | — | — | — | — | — |
| CAP-09 Enviar subsanación al cliente | — | ✅ | ✅ | — | — | — | — | — |
| CAP-10 Aprobar `LISTA_PARA_ENVIO` | — | — | ✅ | — | — | — | — | — |
| CAP-11 Construir payload o handoff | — | ✅ | — | — | — | — | — | — |
| CAP-12 Ordenar la entrega | — | ✅ | — | — | — | — | — | — |
| CAP-13 Expediente Builder | — | ✅ | — | — | — | — | — | — |
| CAP-14 Estados y tareas de la plataforma | ✅ | ✅ | ✅ | — | — | — | — | — |
| CAP-15 Confirmar interpretación de A9 | — | — | ✅ | — | — | — | — | — |
| CAP-16 Decidir ante discrepancia | — | — | ✅ | — | — | — | — | — |
| CAP-20 Elegir o validar verificador | ✅ | — | — | — | — | — | — | — |
| CAP-21 Aprobar composición del expediente | ✅ | — | — | — | — | — | — | — |
| CAP-22 Registrar firma | ✅ | — | — | — | — | — | — | — |
| CAP-23 Registrar desistimiento | ✅ | — | — | — | — | — | — | — |
| CAP-30 Gestionar usuarios del tenant | ✅ | — | — | — | — | — | — | — |
| CAP-31 Ver actividad de todos los usuarios | ✅ | — | — | — | — | — | — | — |
| CAP-32 Reasignar actuaciones y tareas | ✅ (?) | — | — | — | — | — | — | — |
| CAP-33 Configurar política del tenant | ✅ | — | — | — | — | — | — | — |
| CAP-34 Autorizar acceso de soporte | ✅ | — | — | — | — | — | — | — |
| CAP-35 Vista funcional del tenant | ✅ | (?) | (?) | — | — | — | — | — |
| CAP-36 Vista de equipo del tenant | ✅ | — | — | — | — | — | — | — |
| CAP-40 Estado simplificado propio | — | — | — | ✅ (?) | ✅ (?) | — | — | — |
| CAP-50 Activar spec | — | — | — | — | — | ✅ | — | — |
| CAP-51 Severidades e `INT-xx` | — | — | — | — | — | ✅ | — | — |
| CAP-52 Agentes y umbrales | — | — | — | — | — | ✅ | — | — |
| CAP-53 Prompts y router | — | — | — | — | — | ✅ | — | — |
| CAP-54 Presupuestos y umbrales de alerta | — | — | — | — | — | ✅ | — | — |
| CAP-55 Mejoras `MEJ-nnn` | — | — | — | — | — | ✅ | — | — |
| CAP-56 Diffs normativos | — | — | — | — | — | ✅ | — | — |
| CAP-57 `HUECOS.md` e `INT-xx` | — | — | — | — | — | ✅ | — | — |
| CAP-58 Aviso de discrepancias | — | — | — | — | — | ✅ | — | — |
| CAP-60 Alta y baja de tenants | — | — | — | — | — | — | ✅ | — |
| CAP-61 Capacidad de delegación | — | — | — | — | — | — | ✅ | — |
| CAP-62 Solicitar acceso de soporte | — | — | — | — | — | — | ✅ | — |
| CAP-63 Usar acceso de soporte | — | — | — | — | — | — | ✅ | — |
| CAP-64 Estado de integración | — | — | — | — | — | — | ✅ | — |
| CAP-65 Auditoría global | — | — | — | — | — | — | ✅ | — |
| CAP-66 Dashboard operativo, vista global | — | — | — | — | — | ✅ | ✅ | — |
| CAP-67 Dashboard técnico | — | — | — | — | — | ✅ | ✅ | — |
| CAP-70 Transporte a la API oficial | — | — | — | — | — | — | — | ✅ |

`T-RES` no tiene CAP-05, CAP-10 ni CAP-11 por defecto: revisar y preparar no son funciones del Responsable. En delegados pequeños se le asignan además `T-REV` y `T-OPE`.

### Reglas transversales

- **Combinación de perfiles.** Un usuario puede acumular perfiles de tenant; cada evento registra `actor.clase`, `actor.id` y `actor.rol`. La política del tenant (CAP-33) decide si quien prepara puede aprobar; propuesta por defecto: permitido y señalado en la vista de equipo.
- **Autoasignación.** Que un `T-RES` se asigne un perfil genera un evento visible en la auditoría del tenant y en la global.
- **Continuidad.** Mínimo dos usuarios `T-RES` por tenant o procedimiento de recuperación por `ADM-OPS` con verificación de identidad fuera de la plataforma.
- **Firma.** CAP-22 registra quién firmó, que puede no ser quien lo anota. Con `SYS-API` activo, `ENTREGADA` → `EN_PLATAFORMA` exige confirmación de la plataforma oficial (P9); el registro manual solo vale en modo handoff.
- **Reasignación.** `ActuacionReasignada` nunca sobrescribe el actor de eventos anteriores.
- **Acceso de soporte.** `ADM-OPS` solicita sobre una actuación, con motivo y caducidad; `T-RES` autoriza; `ADM-OPS` usa. Todo queda en ambas auditorías.
- **Aislamiento.** Ninguna capacidad de tenant cruza tenants. Los externos solo ven actuaciones en las que son parte, nunca la cabecera económica, otras actuaciones ni payloads.
- **Límites absolutos.** Nadie fuerza un veredicto, firma actos administrativos, custodia certificados de representante, corrige datos tras `EN_PLATAFORMA` fuera de un requerimiento oficial ni edita el log o la telemetría.
- **Monitorización de trabajadores.** CAP-31 y CAP-36 permiten al tenant supervisar la actividad de sus empleados. La plataforma mostrará un aviso a los usuarios de tenant, y el contrato con el tenant recogerá su obligación de informarles. Requiere revisión jurídica antes del primer cliente.

## Consecuencias

- **Modelo canónico** (`docs/03`, `engine/modelo/`): entidades `Usuario`, `Perfil`, `Capacidad`, `AsignacionPerfil` y `PoliticaTenant`; `Tenant` referencia a sus usuarios. Encaje en S3.1.
- **Log de eventos** (`engine/eventos/`): `actor.rol` obligatorio en actor humano; los eventos marcados "(nuevo)" en las tablas de capacidades.
- **Máquina de estados** (`engine/estados.py`): CAP-10 y CAP-22 como únicos disparadores humanos de sus transiciones.
- **Salida** (`salida/transporte/`): `SYS-API` limitado a CAP-70; condicionado a API-09.
- **Documentación**: `docs/03` §S7 y §N7; `docs/06` S3.1 ampliado; `CLAUDE.md` §6 con los puntos pendientes; ADR-001 §1 con D3 y D4.
- **Sustituye** el catálogo de perfiles de ADR-005; el resto de ADR-005 sigue vigente.
- **Coste**: cinco entidades y unos veinte eventos nuevos antes del primer cliente.
- **Pendiente (Billy)**:
  - A1 · Instalador: usuario externo del tenant, tenant propio de CAE Check o ambos.
  - A2 · Cliente: cuenta, enlace de subida puntual sin cuenta o sin acceso. Recomendación: enlace sin cuenta.
  - A3 · `T-RES` reasigna trabajo o solo lo ve. Recomendación: reasigna.
  - A4 · Vista funcional también para `T-OPE` y `T-REV`.
  - A5 · Vista de equipo por persona o por equipo. Recomendación: por equipo hasta revisión jurídica.
  - A6 · Preparar y aprobar la misma persona. Recomendación: configurable, por defecto permitido y señalado.
  - A7 · Firma manual con API activa. Recomendación: rechazarla si la plataforma no la confirma.
  - A8 · Modelar capacidades desde el Sprint 3. Recomendación: sí; es la única que condiciona el código del S3.1.

## Verificación

Tests a crear con S3.1:

- `tests/test_permisos_capacidades.py`: para cada capacidad, un caso que la concede y otro que la deniega según la matriz.
- `tests/test_permisos_aislamiento.py`: ningún comando de un perfil de tenant devuelve datos de otro tenant.
- `tests/test_permisos_actores.py`: ningún evento de actor `agente`, `motor` o `SYS-API` produce `RevisionAprobada`, `FirmaRegistrada` ni `DesistimientoRegistrado`.
- Metamórfica: `ActuacionReasignada` no altera el actor de eventos previos.
- Replay del log reproduce el estado de permisos en cualquier instante.
- `/contrastar`: `docs/03` y `engine/modelo/` coinciden con el catálogo de este ADR.
