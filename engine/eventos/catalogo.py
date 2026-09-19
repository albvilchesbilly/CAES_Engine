"""Catalogo cerrado de tipos de evento y clases de actor (`docs/03` §6.1 y §6.2, `ADR-004` C2).

Un unico sitio donde se declara que eventos existen. Un tipo no declarado es `ErrorEvento` **al anadir**, no
al leer: un log antiguo con un tipo que ya no existe se lee y se verifica igual (el log es solo-anadir y no
se reescribe; lo que no se puede es escribir hoy un tipo inventado).

Los tipos se agrupan por proceso P0–P10 para que se vea de donde sale cada uno. **Los procesos que todavia
no existen (P8 empaquetado, P9 seguimiento, P10 composicion) se declaran igual**: el catalogo es la
referencia del sprint, no el inventario de lo implementado.

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
    "P5 Calculo": ("CalculoRealizado", "DiscrepanciaCalculoPlataforma"),
    "P6 Pre-revision": ("ObservacionRegistrada",),
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
    "P10 Composicion": ("GrupoPropuesto", "ExpedientePropuesto", "AvisoContagio", "ActuacionHuerfana"),
}

#: El catalogo cerrado. Un tipo fuera de aqui es `ErrorEvento` al anadir.
TIPOS: frozenset[str] = frozenset(tipo for tipos in TIPOS_POR_PROCESO.values() for tipo in tipos)

#: Proceso de cada tipo (para informes y para saber de donde sale un evento).
PROCESO_DE_TIPO: dict[str, str] = {
    tipo: proceso for proceso, tipos in TIPOS_POR_PROCESO.items() for tipo in tipos
}

#: Eventos que solo son validos con `actor.clase == "humano"` (`docs/03` §6.1 y §7.3).
TIPOS_SOLO_HUMANO = ("DatoCorregidoPorHumano", "DesistimientoRegistrado", "FirmaRegistrada")

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


__all__ = [
    "ACTORES_ADMITIDOS",
    "CAMPOS_AGENTE",
    "CLASES_ACTOR",
    "CONFIRMACIONES_SOLO_HUMANO",
    "ORIGENES_SUBSANACION",
    "PROCESO_DE_TIPO",
    "TIPOS",
    "TIPOS_POR_PROCESO",
    "TIPOS_SOLO_HUMANO",
]
