# ADR-001 — Registro de decisiones vigentes al arranque del repositorio

**Estado**: ACEPTADA (§1) · PROPUESTA (§2) · ABIERTA (§3)
**Fecha**: 2026-09-18
**Decide**: Billy (§1 y §3); Claude propone (§2)
**Ámbito**: todo el proyecto

Este ADR es el punto de partida del registro de decisiones. Recoge en un solo sitio lo que ya está decidido (para que ninguna sesión lo reabra en silencio), lo que la consolidación documental propuso y Billy debe confirmar, y lo que sigue abierto. A partir de aquí, cada decisión nueva es un ADR propio (`ADR-002`, `ADR-003`…), y este se actualiza solo para mover líneas de §2/§3 a §1 o a un ADR nuevo.

---

## 1. Decisiones tomadas (no se reabren sin decir que se reabren)

| Fecha | Decisión | Fuente |
|---|---|---|
| — | Sujeto delegado como partner; financiación de partner sin riesgo CAE; entrada B2B2C vía instaladores (decisiones 1A · 2A · 3D del brainstorming inicial) | `docs/historico/cae-engine-estado-proyecto_2026-09-17.md` |
| — | Pivote: el activo es el motor de cálculo y validación CAE, no el marketplace | Idem |
| — | No somos sujeto delegado, verificador, financiera, instalador ni ingeniería; no prometemos CAE; no firmamos ni custodiamos certificados de representante | `docs/00` §2 |
| 17/09/2026 | Misión, visión y propuesta de valor | `docs/00` §1.1 |
| 17/09/2026 | Alegaciones al proyecto de modificación del RD 36/2023 presentadas a título personal (arts. 2, 8.3, 12, 16, 18, 18 bis, 20.3, DT 2ª) | `docs/00` §5.6 |
| 17/09/2026 | Sprint 3 orientado a la integración con la plataforma oficial | `docs/06` §2 |
| 18/09/2026 | A8 (revisor sombra) empieza emitiendo solo avisos; no altera el veredicto | `docs/03` §11, `docs/04` §12 |
| 18/09/2026 | P9 (seguimiento post-envío) entra en el Sprint 3 junto con el envío | `docs/06` §2 |
| 18/09/2026 | El orden técnico de construcción se delega en Claude | `docs/06` |
| 18/09/2026 | Posición respecto a Moeve: el CAE Engine es independiente, modelo de negocio propio; Moeve es posible cliente o aliado, no destinatario | `docs/00` §5.1, `docs/07` §6 |
| 18/09/2026 | Enviar, a título personal, consulta a `consultas-plataforma@registrocae.es` (modelos de intercambio, documentación de la API, acceso a pruebas, perfil Modificación para terceros) | `docs/06` §5 X.1 |
| 18/09/2026 | Búsqueda de delegado partner en curso: barrido de los 70 de la lista MITECO; revisión de CalculaCAE.ai y CAE Digital; criterio añadido de capacidad de delegación disponible | `docs/08`, `docs/07` |
| 18/09/2026 | Vigilancia normativa del Sistema CAE programada en días laborables (RD, órdenes, plataforma, catálogo) | Memoria del proyecto |
| 18/09/2026 | Arranque del repositorio en Claude Code **desde cero**, con consolidación documental y doble instrucción (Claude Code + GitHub Copilot) | Esta consolidación |
| 19/09/2026 | **Administración en dos planos sin permisos solapados**: `ADM-MOD` (propietario del modelo: specs, reglas, severidades, `INT-xx`, agentes y prompts) y `ADM-OPS` (operación: tenants, capacidad de delegación, accesos de soporte, auditoría global). Una persona con ambos actúa con uno a la vez, con cambio de rol registrado y segundo factor | `ADR-005` |
| 19/09/2026 | **Dos dashboards en solo lectura**, operativo y técnico, para los dos perfiles de administración | `ADR-005` |
| 19/09/2026 | **D3**: el sujeto delegado tiene un administrador (`T-RES`) que ve toda la actividad de su tenant y de su equipo, con dashboards de su propio tenant | `ADR-006` |
| 19/09/2026 | **D4**: administrador y responsable del tenant se consolidan en **un único rol** (`T-RES`) | `ADR-006` |
| 19/09/2026 | **Permisos por capacidades, no por pantallas**: catálogo de ocho perfiles y matriz de capacidades `CAP-nn`, cada una atada a su evento del log | `ADR-006` |
| 19/09/2026 | **Una métrica se define una sola vez en configuración** (`metricas/catalogo.yaml` validado por JSON Schema), con el mismo criterio que las fichas; las vistas de tenant son filtros aplicados antes del cálculo; se empieza por informes estáticos | `ADR-007` |

---

## 2. Decisiones de la consolidación documental — PROPUESTAS, pendientes de confirmación de Billy

Se tomaron para que los documentos fueran coherentes entre sí y ejecutables por Claude Code sin código previo. Ninguna cambia negocio, spec activa ni ground truth. Si Billy rechaza alguna, se revierte en la misma sesión.

| # | Decisión propuesta | Por qué | Dónde está | Alternativa |
|---|---|---|---|---|
| C1 | La unidad de trabajo se llama `Actuacion` en el código **desde la Fase 0**; no hay alias `Expediente = Actuacion` | No hay tests antiguos que proteger; adoptar el vocabulario de la plataforma desde el principio evita el renombrado del Sprint 3 | `docs/01` §3.3, `docs/03` §5 | Mantener "Expediente" en código y renombrar en S3 (más trabajo, ningún beneficio) |
| C2 | Marcas de estado: `F0` (existió en Engine 0.1, se reconstruye) sustituye a `EXISTE`/`PARCIAL` mientras no haya código; `A CONFIRMAR` desaparece y sus dudas se convierten en decisiones de diseño de la Fase 0 | Sin repositorio previo no hay nada que confirmar; dejar la marca invitaría a inventar un estado | `CLAUDE.md` §3, `docs/03` §14, `docs/04` §0 | Conservar las marcas antiguas como histórico |
| C3 | Decisiones de diseño de la Fase 0 que cierran los antiguos `A CONFIRMAR`: (a) `logica` del YAML es ejecutable por un parser de lista blanca; lo inexpresable se implementa en Python registrado por `id` con test de su `logica`; (b) tres resultados de regla desde F0; (c) asignación de las 26 reglas a fases según `docs/04` §5, declarada en YAML con `fase`; (d) SHA-256 de todo fichero en ingesta desde F0; (e) Evidence Store en memoria con serialización JSON en F0, persistencia con el log de eventos en S3 | Son las opciones que la documentación anterior recomendaba "si se confirmaba"; al no haber código, se adoptan | `docs/03` §14, `docs/04` §5–§6 | Cualquiera de ellas puede cambiarse con un ADR antes de F0.1 |
| C4 | `docs/HUECOS.md` es la ubicación canónica de los huecos de API (antes `salida/HUECOS.md` o `salida/simulador/HUECOS.md`) | Los huecos afectan a modelo, estados y reglas, no solo a `salida/`; un único fichero evita duplicados | `docs/01` §2, `docs/HUECOS.md` | Copia en `salida/` (riesgo de divergencia) |
| C5 | No existe `salida/firma/` como código; la firma es un paso humano y solo se registra `FirmaRegistrada` | Coherente con `docs/02` (tres certificados) y con "nunca custodiamos certificados de representante" | `docs/01` §3.8, `docs/03` §10 | Carpeta vacía con README (ruido) |
| C6 | Asignaciones de reglas a fases que la fuente no razonaba: `R-CAL-02` (aviso, INT-02) en fase 2 porque decide cómo se obtiene `p`; `R-CON-06` en fase 4 con `NO_EVALUABLE` si no hay cálculo; si falla la fase 2 se saltan 3–4 pero **sí** se evalúa la 5 para listar todas las carencias de una vez | Maximiza la utilidad del informe ("qué te falta") sin publicar un ahorro incoherente | `docs/04` §5 | Parar del todo tras fase 2 (informe más pobre) |
| C7 | Semántica trivaluada de `and`/`or`/`not` con `NO_EVALUABLE`: si un operando es `NO_EVALUABLE` y no decide el resultado, la regla es `NO_EVALUABLE` | Las fuentes definen los tres resultados pero no su propagación; esta es la lectura conservadora | `docs/04` §6 | Tratar `NO_EVALUABLE` como `FALLA` (más bloqueos falsos) |
| C8 | En el caso B, `R-DOC-01` también `FALLA` (EVD-01 es obligatorio y falta), además de `R-EVD-04`; el cálculo provisional de B usa `h = h_antes` | Deducción directa de la spec; el README original solo citaba R-EVD-04 | `docs/05` §2 | Si el ground truth de B debe listar solo R-EVD-04, se fija en `ADR-002` |
| C9 | Los ground truth de E (461.433) y F (777.128) se **recalculan** en la Fase 0 con los parámetros que fije el generator, y se registran en `ADR-002`; el caso A (305.829,6) es el único exactamente reproducible | Los parámetros de los motores 2 y 3 no están documentados fuera del código original | `docs/01` §3.5, `docs/05` §2, `docs/06` F0.5 | Intentar reproducir 461.433 y 777.128 por ensayo y error (sin garantía; sin valor) |
| C10 | `docs/07-entorno-y-competencia.md` v1.1 aplica íntegro el anexo §9 del antiguo `11` (incluidas las mejoras M2 y M3: tabla de solapamiento plataforma ↔ Engine y tareas pendientes como cola de trabajo) | El anexo era documental; Billy había pedido "consolidar" | `docs/07` | Retirar §3.5 (solapamiento) y la mención de tareas pendientes si se quiere el anexo estricto |
| C11 | El número de tests del Engine 0.1 (61) **no** es criterio de aceptación; lo es la cobertura de `docs/05` §8 | Evita "igualar una cifra" en lugar de cubrir comportamientos | `CLAUDE.md` §7, `docs/06` §1 | — |

---

## 3. Decisiones abiertas de Billy (no las toma Claude)

| Asunto | Opciones sobre la mesa | Bloquea | Dónde se detalla |
|---|---|---|---|
| Aprobar `spec/propuestas/cabecera_v1.yaml` y el diff `IND240_v1.1 → v1.2` | Sí tal cual / revisar `n` de INT-08 y las severidades de R-CAB antes / no | S3.2 | `docs/04` §10–§11, `spec/propuestas/` |
| Aprobar las familias `R-GRP/R-EXP`, `R-XCK`, `R-REQ` como diseño | Sí / recortar | S3.5, S3.7, S4.1 | `docs/04` §10 |
| Proveedor LLM y condiciones de tratamiento de datos (región, no-entrenamiento, enmascarado) | — | S3.6 | `docs/03` §12 |
| Umbral de activación de un rol de agente en producción | — | S3.6 | `docs/03` §11 |
| Vía del perfil Modificación (tras respuesta del gestor): transporte en nuestra infra o en casa del tenant | — | S3.7, `salida/transporte/` | `docs/02` §7, `docs/HUECOS.md` API-09 |
| Expediente Builder en Sprint 4 | Sí / posponer | S4.1 | `docs/06` §3 |
| Segunda ficha: vecina (IND170 o IND280) o estresante (frío: IND030, IND140) | — | S4.3 | `docs/09` §6 |
| Requisitos de ficha sin evidencia asociada (IND030, 050, 160, 180, 230, 250, 280, 290): ¿aviso o se pide documento igualmente? | — | Marco de reglas | `docs/09` §6 |
| Módulo de actuaciones singulares / CVP en roadmap | Sí / no | Roadmap | `docs/06` §4 |
| Regla de vigencia de versiones de ficha por fechas de actuación | Validar con normativa / verificador | Spec Registry N1 | `docs/04` §2 |
| Qué se ofrece a cambio del expediente real (informe gratuito, acceso preferente, nada) y orden de contactos | — | `docs/08` | `docs/08` §5, §7 |
| Contrato laboral: exclusividad, PI, conflicto de interés | Revisar antes de cualquier contacto | Comercial | `docs/08` §5 |
| A1 · Instalador: usuario externo del tenant, tenant propio de CAE Check o ambos | — | Perfiles externos | `ADR-006` |
| A2 · Cliente: cuenta, enlace de subida puntual sin cuenta o sin acceso | Recomendación: enlace sin cuenta | Perfiles externos | `ADR-006` |
| A3 · `T-RES` reasigna trabajo o solo lo ve | Recomendación: reasigna | CAP-32 | `ADR-006` |
| A4 · Vista funcional del dashboard también para `T-OPE` y `T-REV` | — | `O-FUN` | `ADR-006` |
| A5 · Vista de equipo por persona o por equipo | Recomendación: por equipo hasta revisión jurídica | `O-EQU` | `ADR-006`, `ADR-007` B3 |
| A6 · Preparar y aprobar la misma persona | Recomendación: configurable, por defecto permitido y señalado | CAP-10, CAP-33 | `ADR-006` |
| A7 · Firma manual con API activa | Recomendación: rechazarla si la plataforma no la confirma | CAP-22, `SYS-API` | `ADR-006` |
| A8 · Modelar capacidades desde el Sprint 3 | Recomendación: sí; es lo único que condiciona el código de S3.1 | `engine/modelo/`, `engine/eventos/` | `ADR-006` |
| Umbrales de las métricas del catálogo (`umbral: POR DEFINIR`) | — | Dashboards | `ADR-007` |
| Interfaz o herramienta de los dashboards (DB5); si es BI externa, se alimenta de la API de lectura | — | DB5 | `ADR-007` |
| **Revisión jurídica de la monitorización de trabajadores** (CAP-31 y CAP-36) antes del primer cliente | Obligatoria | Perfiles de tenant | `ADR-006` |

---

## Verificación

`/contrastar` comprueba que ninguna sesión ha implementado algo que dependa de una línea de §3 sin un ADR nuevo que la cierre, y que las decisiones de §2 rechazadas por Billy se han revertido.
