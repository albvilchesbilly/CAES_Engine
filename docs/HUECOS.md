# HUECOS.md — Lo que la plataforma oficial no ha documentado

**Versión 1.0 · 18/09/2026 · Proyecto CAE (Billy)**

Regla de oro 10: lo que la plataforma oficial (OMIE/MIBGAS) no ha publicado es un hueco enumerado, **nunca una suposición en el código**. Cada hueco tiene un identificador `API-xx`, un dueño, qué bloquea y cuándo se revisa. En código se referencia así: `# TODO(API-07): ver docs/HUECOS.md`. Un hueco se cierra **solo** con documentación oficial (diccionario, modelos de intercambio, respuesta escrita del gestor) y el cierre se registra aquí con fuente y fecha.

Fuente de partida: presentación "Plataforma electrónica del sistema de CAE" (OMIE/MIBGAS, 30/06/2026). Estado de la documentación oficial a 18/09/2026: los modelos de intercambio previstos para septiembre **no se han recibido**; la página de MITECO indica "en fase de desarrollo". Consulta enviada a `consultas-plataforma@registrocae.es` (decisión del 18/09/2026).

---

## 1. Huecos abiertos

| ID | Hueco | Qué bloquea | Cómo se trabaja mientras tanto | Dueño | Revisar cuando |
|---|---|---|---|---|---|
| API-01 | Endpoints, autenticación concreta, ejemplos de petición y respuesta | `salida/api_oficial/`, `salida/transporte/` | Simulador (`salida/simulador/`) implementa solo lo conocido; handoff como vía operativa | Billy (consulta X.1) | Llegue el diccionario |
| API-02 | Formato del manifiesto oficial de ficheros (algoritmo de hash, estructura, campos) | `mapping/manifiesto.api.yaml` | Manifiesto interno propio (`docs/03` §9) con SHA-256; el mapeo al oficial se escribe cuando exista | Billy | Idem |
| API-03 | Estados de expediente en fases 2–4 (presentación, validación técnica GA, revisión formal CN, resolución, registro, desistimiento) y de la solicitud de certificación | Máquina de estados `engine/estados.py` | Nombres provisionales marcados `NO OFICIAL` en tabla de mapeo YAML: `BORRADOR_SOLICITUD`, `PRESENTADO`, `EN_VALIDACION_TECNICA`, `REQUERIDO_GA`, `VALIDADO_GA`, `EN_REVISION_FORMAL`, `REQUERIDO_CN`, `RESUELTO_FAVORABLE`, `RESUELTO_DESFAVORABLE`, `INSCRITO`, `DESISTIDO` | Billy | Idem |
| API-04 | Si la validación documental de la plataforma comprueba **contenido** o solo **presencia** por tipo | Valor diferencial de R-DOC frente a R-CON; `R-DOC-01.equivalente_plataforma` | Se asume presencia por tipo (lectura razonable de la presentación); R-DOC-01 marcada `diferencial: false` en la propuesta v1.2 | Billy | Diccionario / fase II (ene–mar 2027) |
| API-05 | Taxonomía de "tipología de empresa" del propietario inicial (¿PYME / gran empresa? ¿otra?) | `R-CAB-06`; variable `tipologia_empresa` | Dato `declarado`; regla solo `AVISO` | Billy | Diccionario |
| API-06 | Semántica de "partícipe en subasta" (nuevo concepto del RD modificado) | `R-CAB-10`; variable `participe_subasta` | Dato `declarado`; regla solo `AVISO` | Billy | Diccionario / texto definitivo del RD |
| API-07 | Cómo se determina la CCAA de una actuación (¿localización del convenio? ¿declaración?) | `R-EXP-01`; atributo `atributos_agrupacion.ccaa` | Se deriva de la referencia catastral y se marca `derivado` | Billy | Diccionario |
| API-08 | Nombres, tipos, unidades y granularidad (por motor o agregado) del formulario de detalle por ficha | `mapping/IND240.api.yaml`; `R-XCK-01` | Solo `mapping/IND240.handoff.yaml`; el detalle API queda como esqueleto con huecos | Billy | Diccionario |
| API-09 | Si el perfil de usuario **Modificación** admite personas ajenas a la plantilla del agente o cuentas de sistema, y si su certificado puede usarse desde infraestructura de un tercero | Dónde vive `salida/transporte/` (nuestra infra vs. casa del tenant) | Transporte diseñado como componente desplegable en ambos sitios; decisión de Billy tras la respuesta | Billy | Respuesta del gestor de la plataforma |
| API-10 | Plazos de requerimientos y contestaciones (la presentación menciona "seguimiento de plazos" sin cifras) | Alertas en la consola de revisión (S4) | Sin alertas de plazo; solo registro de fechas de requerimiento | — | Diccionario / fase II |
| API-11 | Cómo se consulta la capacidad de delegación disponible de un tenant | `R-EXP-06`; atributo `Tenant.capacidad_delegacion_disponible` | Atributo informativo introducido a mano; regla solo `AVISO` | — | Diccionario |
| API-12 | Criterio oficial de cálculo para PM sin fila exacta en el cuadro 6 y cómo se acredita N2 "media anual" con 30 días (nuestros INT-01..05) | Cálculo; cierre de INT-01..05 | Criterios propios declarados como `INT-xx` en la spec; batería de casos para inferir el criterio oficial en cuanto haya sandbox (`docs/05` §7) | Sandbox | Sesiones de prueba oct–nov 2026 |

---

## 2. Huecos cerrados

| ID | Cerrado el | Fuente oficial | Qué cambió en el repo |
|---|---|---|---|
| — | — | — | — |

---

## 3. Cómo añadir un hueco

1. Comprobar que no está ya en la tabla (buscar por concepto, no por número).
2. Asignar el siguiente `API-xx`.
3. Rellenar las seis columnas. "Cómo se trabaja mientras tanto" es obligatorio: un hueco sin alternativa bloquea trabajo, y eso también se anota.
4. En el código, `# TODO(API-xx): <una línea>`. Nunca un valor inventado "provisional" sin la marca.
5. Al cerrar: mover la fila a §2 con fuente y fecha, y abrir el cambio de código o de spec que corresponda (si toca `spec/`, pasa por revisión humana).

---

*Mantener vivo: cuando llegue el diccionario de API o una respuesta escrita del gestor, cerrar cada hueco aquí antes de tocar código. La lista de `TODO(API-xx)` del código y esta tabla deben coincidir; `/contrastar` lo comprueba.*
