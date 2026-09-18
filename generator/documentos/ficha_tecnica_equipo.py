"""EVD-05: ficha técnica del equipo accionado (acredita si es rotodinámico o de desplazamiento positivo)."""

from __future__ import annotations

from generator.documentos.base import Seccion, nota, p, subtitulo, tabla_campos
from generator.modelo_caso import Motor

TIPO = "ficha_tecnica_equipo_accionado"
TITULO = "Ficha técnica del equipo accionado"

PRINCIPIO = {
    "bomba_dinamica": "Rotodinámico (centrífugo)",
    "ventilador_axial": "Rotodinámico (axial)",
    "ventilador_radial": "Rotodinámico (radial / centrífugo)",
    "compresor_centrifugo": "Rotodinámico (centrífugo)",
    "compresor_axial": "Rotodinámico (axial)",
    "bomba_desplazamiento_positivo": "Desplazamiento positivo (volumétrico, tornillo)",
    "compresor_desplazamiento_positivo": "Desplazamiento positivo (volumétrico)",
}


def seccion(motor: Motor) -> Seccion:
    e = motor.equipo
    s = Seccion(TIPO, f"{TITULO} – {e.tipo_texto}")
    f = s.flowables
    f.append(s.marcador(motor.num_serie_motor))
    f.append(subtitulo("Identificación"))
    f.append(
        tabla_campos(
            [
                ("Tipo de equipo", f"{e.tipo_texto} ({e.tipo})"),
                ("Principio de funcionamiento", PRINCIPIO[e.tipo]),
                ("Fabricante", e.fabricante),
                ("Modelo", e.modelo),
                ("Nº de serie del equipo", e.num_serie),
                ("Motor asociado (nº de serie)", motor.num_serie_motor),
                ("Descripción", e.descripcion),
            ]
        )
    )
    f.append(
        p(
            f"{e.tipo_texto} modelo {e.modelo} ({e.descripcion.lower()}), accionado por el motor "
            f"{motor.num_serie_motor}. Principio de funcionamiento: {PRINCIPIO[e.tipo].lower()}."
        )
    )
    f.append(nota("Documento sintético generado para pruebas del CAE Engine. El fabricante es inventado."))
    return s
