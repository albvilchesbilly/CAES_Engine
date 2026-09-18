"""DOC-01: ficha IND240 cumplimentada y firmada por el representante legal del titular."""

from __future__ import annotations

from generator.documentos.base import Seccion, bloque, espacio, nota, p, subtitulo, tabla_campos
from generator.modelo_caso import Caso, fmt_es, fmt_fecha

TIPO = "ficha_cumplimentada"
TITULO = "Ficha IND240 cumplimentada – Implantación de variador de velocidad en motor existente"


def seccion(caso: Caso, ahorro_declarado_kwh: int | None = None) -> Seccion:
    s = Seccion(TIPO, TITULO)
    f = s.flowables
    f.append(
        p(
            "Ficha de actuación estandarizada IND240 V1.1 (sistemas dinámicos sin modulación). Solicitud de "
            "certificados de ahorro energético (CAE) conforme al RD 36/2023 y la Orden TED/815/2023. Todos "
            "los "
            "datos de esta ficha son sintéticos."
        )
    )
    f.append(subtitulo("1. Identificación de la actuación"))
    f.append(
        tabla_campos(
            [
                ("Código de ficha", "IND240"),
                ("Versión de la ficha", "V1.1"),
                ("Sector", "Industrial"),
                ("Propietario inicial del ahorro (titular)", caso.titular.razon_social),
                ("NIF del titular", caso.titular.nif),
                ("Dirección de la instalación", caso.localizacion.direccion),
                ("Fecha de inicio de la actuación", fmt_fecha(caso.fechas.inicio)),
                ("Fecha de fin de la actuación", fmt_fecha(caso.fechas.fin)),
                ("Número de motores incluidos", str(caso.n_motores)),
                ("Empresa instaladora", f"{caso.instalador.razon_social} ({caso.instalador.nif})"),
            ]
        )
    )
    f.append(
        p(
            f"La actuación se inició el {fmt_fecha(caso.fechas.inicio)} (pedido firme y factura) y quedó "
            f"completada y en funcionamiento el {fmt_fecha(caso.fechas.fin)}. Comprende {caso.n_motores} "
            f"motor(es) eléctrico(s) existente(s) sobre los que se ha instalado un variador de velocidad."
        )
    )
    f.append(subtitulo("2. Datos por motor"))
    for i, m in enumerate(caso.motores, start=1):
        f.append(
            bloque(
                s.marcador(m.num_serie_motor),
                p(f"Motor {i} de {caso.n_motores}: {m.descripcion}."),
                tabla_campos(
                    [
                        ("Nº de serie del motor", m.num_serie_motor),
                        ("Nº de serie del variador", m.num_serie_variador),
                        ("Equipo accionado", f"{m.equipo.tipo_texto} ({m.equipo.tipo})"),
                        ("Potencia nominal del motor PM", f"{fmt_es(m.PM)} kW"),
                        ("Velocidad antes de la actuación N1", f"{fmt_es(m.N1)} rpm"),
                        ("Velocidad media con variador N2 (declarada)", f"{fmt_es(m.N2)} rpm"),
                        ("Potencia promedio con variador P_prom (declarada)", f"{fmt_es(m.P_prom, 1)} kW"),
                        ("Horas anuales de funcionamiento previas", f"{fmt_es(m.h_antes)} h"),
                    ]
                ),
                espacio(3),
            )
        )
    if ahorro_declarado_kwh is not None:
        f.append(subtitulo("3. Ahorro declarado por el solicitante"))
        f.append(tabla_campos([("Ahorro anual estimado", f"{fmt_es(ahorro_declarado_kwh)} kWh")]))
        f.append(
            p(
                f"Ahorro anual estimado: {fmt_es(ahorro_declarado_kwh)} kWh, calculado por el solicitante "
                "con la "
                "fórmula de la ficha. Este valor es una declaración del solicitante."
            )
        )
    f.append(subtitulo("Firma del representante legal"))
    rep = caso.titular.representante
    f.append(
        tabla_campos(
            [
                ("Firmado electrónicamente por", f"{rep.nombre} ({rep.cargo}), NIF {rep.nif}"),
                ("En representación de", f"{caso.titular.razon_social}, NIF {caso.titular.nif}"),
                ("Fecha de firma", fmt_fecha(caso.fechas.firma_ficha)),
                ("Sistema de firma", "Firma electrónica cualificada (sintética)"),
            ]
        )
    )
    f.append(
        p(
            f"Firmado electrónicamente por {rep.nombre}, {rep.cargo} de {caso.titular.razon_social}, el "
            f"{fmt_fecha(caso.fechas.firma_ficha)}."
        )
    )
    f.append(
        nota("Documento sintético generado para pruebas del CAE Engine. Ninguna entidad ni persona es real.")
    )
    return s
