"""Documentos sin relación con la actuación (caso G): acta de reunión ficticia sin datos de la actuación."""

from __future__ import annotations

from generator.documentos.base import Seccion, nota, p, subtitulo, tabla

TITULO_NOTAS = "Acta de reunión – Comité de mantenimiento"


def seccion_notas() -> Seccion:
    s = Seccion(None, TITULO_NOTAS)
    f = s.flowables
    f.append(subtitulo("Asistentes"))
    f.append(
        tabla(
            ["Nombre", "Área"],
            [
                ("Persona Inventada Uno", "Mantenimiento"),
                ("Persona Inventada Dos", "Producción"),
                ("Persona Inventada Tres", "Compras"),
            ],
            [80, 60],
        )
    )
    f.append(subtitulo("Orden del día"))
    for texto in (
        "1. Planificación de la parada anual de mantenimiento de la línea de envasado.",
        "2. Revisión del calendario de calibración de instrumentos.",
        "3. Propuesta de reorganización del almacén de repuestos.",
        "4. Ruegos y preguntas.",
    ):
        f.append(p(texto))
    f.append(subtitulo("Acuerdos"))
    f.append(
        p(
            "Se acuerda trasladar la parada anual a la última semana de agosto y revisar el inventario de "
            "repuestos "
            "críticos antes de final de mes. No se tratan asuntos de eficiencia energética."
        )
    )
    f.append(
        nota("Documento sintético generado para pruebas del CAE Engine (documento irrelevante a propósito).")
    )
    return s
