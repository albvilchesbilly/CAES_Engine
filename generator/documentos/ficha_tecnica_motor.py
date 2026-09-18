"""EVD-03: ficha técnica del motor (fuente primaria de PM y N1)."""

from __future__ import annotations

from generator.documentos.base import Seccion, nota, p, subtitulo, tabla_campos
from generator.modelo_caso import Motor, fmt_es

TIPO = "ficha_tecnica_motor"
TITULO = "Ficha técnica del motor eléctrico"


def seccion(motor: Motor) -> Seccion:
    s = Seccion(TIPO, f"{TITULO} – {motor.modelo_motor}")
    f = s.flowables
    f.append(s.marcador(motor.num_serie_motor))
    f.append(subtitulo("Identificación"))
    f.append(
        tabla_campos(
            [
                ("Fabricante", motor.fabricante_motor),
                ("Modelo", motor.modelo_motor),
                ("Nº de serie del motor", motor.num_serie_motor),
                ("Tipo", "Motor asíncrono trifásico de jaula de ardilla"),
            ]
        )
    )
    f.append(subtitulo("Características eléctricas y mecánicas"))
    f.append(
        tabla_campos(
            [
                ("Potencia nominal PM", f"{fmt_es(motor.PM)} kW"),
                ("Velocidad nominal N1", f"{fmt_es(motor.N1)} rpm"),
                ("Tensión nominal", f"{motor.tension_v} V"),
                ("Frecuencia", "50 Hz"),
                ("Número de polos", str(motor.polos)),
                ("Clase de eficiencia", "IE3"),
                ("Grado de protección", "IP55"),
                ("Servicio", "S1 (continuo)"),
                ("Forma constructiva", "IM B3"),
            ]
        )
    )
    f.append(
        p(
            f"Motor {motor.modelo_motor} de {fmt_es(motor.PM)} kW de potencia nominal y "
            f"{fmt_es(motor.N1)} rpm a carga nominal, {motor.polos} polos, {motor.tension_v} V, 50 Hz. "
            f"Nº de serie {motor.num_serie_motor}."
        )
    )
    f.append(nota("Documento sintético generado para pruebas del CAE Engine. El fabricante es inventado."))
    return s
