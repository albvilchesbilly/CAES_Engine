"""EVD-04: ficha técnica del variador. Declara pérdidas de 3,90 kW (trampa: el Engine debe usar el
cuadro 6)."""

from __future__ import annotations

from generator.documentos.base import Seccion, nota, p, subtitulo, tabla_campos
from generator.modelo_caso import Motor, fmt_es

TIPO = "ficha_tecnica_variador"
TITULO = "Ficha técnica del variador de frecuencia"


def filas(motor: Motor) -> list[tuple[str, str]]:
    return [
        ("Fabricante", motor.fabricante_variador),
        ("Modelo", motor.modelo_variador),
        ("Nº de serie del variador", motor.num_serie_variador),
        ("Potencia nominal", f"{fmt_es(motor.potencia_variador_kw)} kW"),
        ("Tensión de alimentación", f"3 × {motor.tension_v} V, 50 Hz"),
        ("Pérdidas declaradas por el fabricante", f"{fmt_es(motor.perdidas_declaradas_variador, 2)} kW"),
        ("Rendimiento a carga nominal", f"{fmt_es(motor.rendimiento_variador_pct, 1)} %"),
        ("Grado de protección", "IP21"),
        ("Control", "Vectorial sin sensor"),
        ("Motor asociado (nº de serie)", motor.num_serie_motor),
    ]


def prosa(motor: Motor) -> str:
    return (
        f"Variador {motor.modelo_variador} de {fmt_es(motor.potencia_variador_kw)} kW, nº de serie "
        f"{motor.num_serie_variador}. Pérdidas declaradas por el fabricante: "
        f"{fmt_es(motor.perdidas_declaradas_variador, 2)} kW a carga nominal (dato del fabricante; la ficha "
        "IND240 exige las pérdidas de referencia del cuadro 6 del Reglamento (UE) 2019/1781)."
    )


def seccion(motor: Motor) -> Seccion:
    s = Seccion(TIPO, f"{TITULO} – {motor.modelo_variador}")
    f = s.flowables
    f.append(s.marcador(motor.num_serie_motor))
    f.append(subtitulo("Características"))
    f.append(tabla_campos(filas(motor)))
    f.append(p(prosa(motor)))
    f.append(nota("Documento sintético generado para pruebas del CAE Engine. El fabricante es inventado."))
    return s
