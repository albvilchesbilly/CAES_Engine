"""EVD-02: registro de horas de funcionamiento antes de la actuación (periodo representativo 2025)."""

from __future__ import annotations

from decimal import Decimal

from generator.documentos.base import Seccion, nota, p, subtitulo, tabla, tabla_campos
from generator.modelo_caso import REGIMEN_TEXTO, Caso, Motor, fmt_es, fmt_fecha

TIPO = "registro_horas_previo"
TITULO = "Registro de horas de funcionamiento previo a la actuación"

MESES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def _reparto_mensual(total: Decimal) -> list[Decimal]:
    """Reparte las horas anuales en 12 meses enteros con un patrón fijo (agosto con menos horas)."""
    pesos = [Decimal(p) for p in (9, 8, 9, 8, 9, 8, 9, 5, 8, 9, 8, 10)]
    suma = sum(pesos)
    meses = [(total * w / suma).to_integral_value() for w in pesos]
    meses[-1] += total - sum(meses)
    return meses


def seccion(caso: Caso, motor: Motor) -> Seccion:
    s = Seccion(TIPO, f"{TITULO} – motor {motor.num_serie_motor}")
    f = s.flowables
    f.append(s.marcador(motor.num_serie_motor))
    f.append(subtitulo("Identificación"))
    f.append(
        tabla_campos(
            [
                ("Titular", f"{caso.titular.razon_social} ({caso.titular.nif})"),
                ("Nº de serie del motor", motor.num_serie_motor),
                ("Equipo accionado", f"{motor.equipo.tipo_texto} ({motor.equipo.tipo})"),
                (
                    "Periodo representativo",
                    f"{fmt_fecha(caso.fechas.horas_previo_inicio)} – "
                    f"{fmt_fecha(caso.fechas.horas_previo_fin)}",
                ),
                ("Horas anuales de funcionamiento (h_antes)", f"{fmt_es(motor.h_antes)} h"),
                (
                    "Régimen de funcionamiento",
                    f"{REGIMEN_TEXTO[motor.regimen_previo]} ({motor.regimen_previo})",
                ),
                ("Velocidad de giro en el periodo", f"{fmt_es(motor.N1)} rpm (constante, sin variador)"),
                ("Origen del dato", "Contador horario del cuadro de arranque (sintético)"),
            ]
        )
    )
    f.append(subtitulo("Desglose mensual"))
    meses = _reparto_mensual(motor.h_antes)
    f.append(
        tabla(
            ["Mes", "Horas"],
            [(MESES[i].capitalize(), f"{fmt_es(h)} h") for i, h in enumerate(meses)],
            [60, 40],
        )
    )
    f.append(
        p(
            f"Durante el periodo representativo el motor {motor.num_serie_motor} funcionó "
            f"{fmt_es(motor.h_antes)} "
            f"horas anuales en régimen constante sin modulación, a velocidad fija de {fmt_es(motor.N1)} rpm."
        )
    )
    f.append(nota("Documento sintético generado para pruebas del CAE Engine."))
    return s
