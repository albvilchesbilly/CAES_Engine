"""Documento de requerimiento (ADR-010 §5): el PDF con el que llega un requerimiento de verificador, GA o CN.

No es un tipo documental de la ficha IND240: es el documento que **abre** la subsanación, y lo que importa de
él son los motivos. Por eso los motivos van en una **tabla** (nº | texto): la extracción lee tablas antes que
texto plano (`docs/05` §4.4.1) y así el intérprete recibe cada motivo entero, sin que la marca de agua le
intercale caracteres. La marca "DOCUMENTO SINTÉTICO – SOLO PRUEBAS" la pone `construir_pdf` en cada página.
"""

from __future__ import annotations

from generator.documentos.base import Seccion, nota, p, subtitulo, tabla, tabla_campos
from generator.modelo_caso import fmt_fecha
from generator.modelo_requerimiento import Requerimiento

TIPO = "requerimiento"
PAPEL_DE_ORIGEN = {
    "verificador": "Requerimiento de rectificación por actuación (fase 1B)",
    "GA": "Requerimiento de subsanación del órgano gestor autonómico (fase 3A)",
    "CN": "Requerimiento de la coordinación nacional en revisión formal (fase 3B)",
}
ALCANCE_TEXTO = {
    "actuacion": "actuación (solo la actuación indicada)",
    "grupo": "grupo (dictamen único); sin grupo constituido, alcanza solo a la actuación indicada",
    "expediente": "expediente (la subsanación alcanza a todas las actuaciones que lo integran)",
}


def seccion(requerimiento: Requerimiento) -> Seccion:
    """Una sección por requerimiento: cabecera, motivos en tabla, plazo y advertencia."""
    r = requerimiento
    s = Seccion(TIPO, r.titulo)
    f = s.flowables
    f.append(p(PAPEL_DE_ORIGEN[r.origen]))
    f.append(subtitulo("1. Identificación del requerimiento"))
    campos: list[tuple[str, str]] = [
        ("Número de requerimiento", r.id),
        ("Organismo requirente", r.organismo.nombre),
        ("Código del organismo", r.organismo.codigo),
        ("Origen del requerimiento", r.origen),
        ("Fase del procedimiento", r.fase),
        ("Referencia oficial", r.referencia_oficial),
        ("Estado de plataforma asociado", r.literal_plataforma),
        ("Fecha de notificación", fmt_fecha(r.recibido_en.date())),
        ("Hora de notificación", r.recibido_en.strftime("%H:%M")),
        ("Ronda", f"{r.ronda}ª"),
        ("Plazo de contestación", f"{r.plazo_dias} días hábiles desde la notificación"),
    ]
    if r.organismo.nif:
        campos.insert(3, ("NIF del organismo requirente", r.organismo.nif))
    f.append(tabla_campos(campos))
    f.append(subtitulo("2. Alcance"))
    f.append(
        tabla_campos(
            [
                ("Actuación directamente afectada", r.actuacion_id),
                (
                    "Expediente afectado",
                    r.expediente_id or "No procede (la actuación aún no forma parte de un expediente)",
                ),
                ("Grupo de actuaciones", r.grupo_id or "No procede"),
                ("Alcance declarado", ALCANCE_TEXTO[r.alcance]),
            ]
        )
    )
    f.append(subtitulo("3. Motivos del requerimiento"))
    f.append(p(r.preambulo))
    f.append(
        tabla(
            ["Nº", "Motivo del requerimiento"],
            [[str(m.numero), m.texto] for m in r.motivos],
            [12, 158],
        )
    )
    f.append(subtitulo("4. Plazo y advertencia"))
    f.append(p(r.advertencia))
    f.append(subtitulo("5. Firma"))
    f.append(
        tabla_campos(
            [
                ("Firmado electrónicamente por", r.organismo.nombre),
                ("Fecha", fmt_fecha(r.recibido_en.date())),
            ]
        )
    )
    f.append(
        nota(
            "Documento sintético generado para pruebas del CAE Engine. Ningún organismo, persona, número de "
            "referencia ni plazo de este documento es real."
        )
    )
    return s
