"""Catalogo cerrado de tipos de evento y clases de actor (`docs/03` §6.1 y §6.2, `ADR-004` C2).

Un unico sitio donde se declara que eventos existen. Un tipo no declarado es `ErrorEvento` **al anadir**, no
al leer: un log antiguo con un tipo que ya no existe se lee y se verifica igual (el log es solo-anadir y no
se reescribe; lo que no se puede es escribir hoy un tipo inventado).

Los tipos se agrupan por proceso P0–P10 para que se vea de donde sale cada uno. **Los procesos que todavia
no existen (P8 empaquetado, P9 seguimiento, P10 composicion) se declaran igual**: el catalogo es la
referencia del sprint, no el inventario de lo implementado.

Los grupos `G1`, `G2` y `G3` no son procesos del Engine: son los eventos de gobierno y administracion
que `ADR-006` da de alta con la decision A8 (S3.1b). No los produce ninguna ejecucion del motor; los escribe
una persona con un perfil, y por eso **todos exigen actor humano** (y, por tanto, `actor.rol`).

Dos detalles de lectura del catalogo de `docs/03` §6.2:

- `SubsanacionSolicitada{origen}` y `RequerimientoRecibido{origen}` se declaran **sin** la llave: el origen
  (`interno` | `verificador` | `GA` | `CN`) es un campo del payload, no parte del nombre del tipo. Si el
  origen formara parte del nombre, el catalogo dejaria de ser cerrado.
- La "confirmacion de una interpretacion de A9" que `docs/03` §6.1 exige que sea humana **no tiene tipo
  propio** en §6.2: el unico evento del catalogo es `RequerimientoInterpretado`, que A9 (un agente) tambien
  emite como propuesta. Se resuelve con `CONFIRMACIONES_SOLO_HUMANO`: ese evento exige actor humano cuando
  su payload lleva `confirmada: true`. Propuesta para el ADR: un tipo propio `InterpretacionConfirmada`.
"""

from __future__ import annotations

#: Clases de actor admitidas (`docs/03` §6.1).
CLASES_ACTOR = ("humano", "motor", "agente", "plataforma")

#: Catalogo por proceso (`docs/03` §6.2). Orden de declaracion = orden de los procesos.
TIPOS_POR_PROCESO: dict[str, tuple[str, ...]] = {
    "P0 Admision": ("ActuacionAbierta", "TenantAsignado", "VerificadorAsignado"),
    "P1 Ingesta": ("DocumentoRegistrado", "DocumentoClasificado", "PdfSeparado"),
    "P2 Evidencias": ("EvidenciaPropuesta", "EvidenciaDescartadaSinCita", "DesacuerdoExtractores"),
    "P3 Ficha": ("FichaAsignada", "CabeceraConsolidada", "VeredictoEmitido"),
    "P4 Cruce": ("DatoConsolidado", "ConflictoDetectado", "DatoCorregidoPorHumano"),
    "P5 Calculo": ("CalculoRealizado", "DiscrepanciaCalculoPlataforma", "DiscrepanciaResuelta"),
    "P6 Pre-revision": (
        "ObservacionRegistrada",
        "ObservacionRevisada",
        "RevisionAprobada",
        "ActuacionDescartada",
    ),
    "P7 Subsanacion": ("SubsanacionSolicitada", "SubsanacionCerrada", "CorreccionRechazadaPostFirma"),
    "P8 Empaquetado": (
        "PayloadConstruido",
        "ManifiestoGenerado",
        "EntregadoADelegado",
        "EnviadoAPI",
        "FirmaRegistrada",
    ),
    "P9 Seguimiento": (
        "EstadoPlataformaRecibido",
        "TareaPendienteRecibida",
        "RequerimientoRecibido",
        "RequerimientoInterpretado",
        "DesistimientoRegistrado",
    ),
    "P10 Composicion": (
        "GrupoPropuesto",
        "ExpedientePropuesto",
        "ExpedienteAprobado",
        "AvisoContagio",
        "ActuacionHuerfana",
    ),
    "G1 Gobierno del tenant": (
        "UsuarioAlta",
        "UsuarioBaja",
        "RolAsignado",
        "ActuacionReasignada",
        "PoliticaTenantCambiada",
        "AccesoSoporteAutorizado",
        "AccesoSoporteDenegado",
    ),
    "G2 Gobierno del modelo": (
        "SpecActivada",
        "AgenteActivado",
        "AgenteDesactivado",
        "PromptActivado",
        "UmbralCambiado",
    ),
    "G3 Operacion interna": (
        "TenantAlta",
        "TenantBaja",
        "TenantSuspendido",
        "CapacidadActualizada",
        "AccesoSoporteSolicitado",
        "AccesoSoporteUsado",
    ),
}

#: Los grupos de gobierno: lo que `ADR-006` llama administracion. No los produce el motor (ver cabecera).
GRUPOS_ADMINISTRACION = ("G1 Gobierno del tenant", "G2 Gobierno del modelo", "G3 Operacion interna")

#: El catalogo cerrado. Un tipo fuera de aqui es `ErrorEvento` al anadir.
TIPOS: frozenset[str] = frozenset(tipo for tipos in TIPOS_POR_PROCESO.values() for tipo in tipos)

#: Proceso de cada tipo (para informes y para saber de donde sale un evento).
PROCESO_DE_TIPO: dict[str, str] = {
    tipo: proceso for proceso, tipos in TIPOS_POR_PROCESO.items() for tipo in tipos
}

#: Eventos de administracion y gobierno (`ADR-006`): los tres grupos `G`. Se declaran aparte porque
#: `docs/06` S3.1b pide poder comprobar, de una vez, que **ninguno** de ellos carece de `actor.rol`.
TIPOS_ADMINISTRACION: frozenset[str] = frozenset(
    tipo for grupo in GRUPOS_ADMINISTRACION for tipo in TIPOS_POR_PROCESO[grupo]
)

#: Eventos que solo son validos con `actor.clase == "humano"` (`docs/03` §6.1 y §7.3).
#:
#: Los tres primeros son los de S3.1. El resto entra con A8 (`ADR-006`, S3.1b): **toda** capacidad que los
#: produce la ejerce una persona con un perfil — ningun agente aprueba una revision, descarta una actuacion,
#: activa una spec ni da de alta un tenant. Como el rol es obligatorio en actor humano (ver `log.py`), esta
#: lista es lo que hace cierto el criterio "ningun evento de administracion carece de `actor.rol`".
#:
#: `CapacidadActualizada` (CAP-61) tambien es solo-humano aunque su dato venga de la plataforma: ADR-006 se
#: lo da a `ADM-OPS`, que lo registra. Si algun dia la plataforma lo publica (`TODO(API-11)`), sera un hueco
#: y una decision, no un ensanchamiento silencioso de esta lista.
TIPOS_SOLO_HUMANO = (
    "DatoCorregidoPorHumano",
    "DesistimientoRegistrado",
    "FirmaRegistrada",
    "ObservacionRevisada",
    "ActuacionDescartada",
    "RevisionAprobada",
    "DiscrepanciaResuelta",
    "ExpedienteAprobado",
    *sorted(TIPOS_ADMINISTRACION),
)

#: Eventos que exigen actor humano **solo cuando** el payload lleva esa marca a `true` (ver cabecera).
CONFIRMACIONES_SOLO_HUMANO = {"RequerimientoInterpretado": "confirmada"}

#: Eventos que solo admiten ciertas clases de actor, cuando "solo humano" seria demasiado estrecho.
#:
#: `RequerimientoRecibido` mueve una actuacion a `PENDIENTE_SUBSANACION`, incluida una ya firmada. La puerta
#: de `R-REQ-02` (una interpretacion no reabre sola: la confirma un humano) vive en
#: `engine.requerimientos.reabrir`, pero un evento escrito **directamente** al log la rodearia. No se puede
#: exigir actor humano, porque el contagio de un requerimiento de GA o CN a las companeras del expediente lo
#: escribe la plataforma (`docs/02` §5.6). Lo que si se puede exigir es que no lo escriba el motor ni un
#: agente: **ningun componente automatico nuestro reabre una actuacion**. (`ADR-010` §5 quater, hallazgo 1.)
ACTORES_ADMITIDOS: dict[str, tuple[str, ...]] = {"RequerimientoRecibido": ("humano", "plataforma")}

#: Lo que un evento de actor `agente` tiene que traer siempre en el payload (`docs/03` §11.2 punto 6).
CAMPOS_AGENTE = ("coste", "latencia", "modelo", "version_prompt")

#: Origenes de subsanacion (`docs/03` §10.5); van en el payload, no en el nombre del tipo.
ORIGENES_SUBSANACION = ("interno", "verificador", "GA", "CN")

#: Tipo de evento -> capacidades de `ADR-006` que lo producen. **Este es el lado del catalogo; el otro (que
#: perfil concede cada capacidad) es la matriz, `engine/capacidades.yaml`, y no se copia aqui.**
#:
#: Sirve para dos cosas: (1) que el log pueda preguntar "¿puede este rol escribir esto?" sin saber nada de
#: perfiles — ese es el gancho `autorizador` de `LogEventos`, que hoy nadie instala y que se conecta a la
#: matriz al integrar S3.1b con `engine/capacidades.py`; (2) que un test contraste las dos mitades y falle
#: si se separan. Un tipo que no esta aqui no lo produce ninguna capacidad de `ADR-006` (lo escribe el motor,
#: un agente o la plataforma) y el gancho no lo mira.
#:
#: Varias capacidades pueden producir el mismo tipo (CAP-05 y CAP-06 corrigen un dato; CAP-50, CAP-51 y
#: **Aquí no se declara qué capacidad produce qué evento.** Lo dice `engine/capacidades.yaml`, y se consulta
#: con `engine.capacidades.capacidades_que_producen(tipo)` y `perfiles_que_pueden_emitir(tipo)`.
#:
#: Lo hubo aquí durante unas horas el 19/09/2026, en paralelo al YAML, y las dos declaraciones coincidían.
#: Se quitó igualmente: dos fuentes de la misma verdad no se separan el día que nacen, se separan el día que
#: alguien cambia una. Es la misma razón por la que la matriz bajó de `api/` a `engine/`.
#:
#: El log sigue sin leer el YAML: quien sella un evento no puede depender de un fichero de configuración
#: (ver `LogEventos(autorizador=...)` en `log.py`). Quien quiera autorizar por rol construye el autorizador
#: desde `engine.capacidades` y se lo pasa al log.


__all__ = [
    "ACTORES_ADMITIDOS",
    "CAMPOS_AGENTE",
    "CLASES_ACTOR",
    "CONFIRMACIONES_SOLO_HUMANO",
    "GRUPOS_ADMINISTRACION",
    "ORIGENES_SUBSANACION",
    "PROCESO_DE_TIPO",
    "TIPOS",
    "TIPOS_ADMINISTRACION",
    "TIPOS_POR_PROCESO",
    "TIPOS_SOLO_HUMANO",
]
