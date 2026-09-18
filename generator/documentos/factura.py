"""DOC-03: factura del instalador al titular con los datos mínimos (número, fecha, NIF emisor y receptor,
base, IVA, total) y una línea por variador que identifica su nº de serie. La mención "instalación sobre motor
existente MTR-…" es contexto, no una línea de compra de motor (trampa `R-AMB-02`, docs/05 §4.3)."""

from __future__ import annotations

from decimal import Decimal

from generator.documentos.base import Seccion, espacio, nota, p, subtitulo, tabla, tabla_campos
from generator.modelo_caso import Caso, fmt_es, fmt_fecha

TIPO = "factura"
TITULO = "Factura"
IVA = Decimal("0.21")
PRECIO_INSTALACION = Decimal("1850.00")


def lineas(caso: Caso) -> list[tuple[str, int, Decimal]]:
    """(descripción, cantidad, base) por línea; la última es la instalación de todos los motores."""
    resultado = []
    for m in caso.motores:
        resultado.append(
            (
                f"Variador de frecuencia {m.fabricante_variador} modelo {m.modelo_variador} "
                f"({fmt_es(m.potencia_variador_kw)} kW), nº serie {m.num_serie_variador} "
                f"(instalación sobre motor existente {m.num_serie_motor})",
                1,
                m.precio_variador,
            )
        )
    resultado.append(
        (
            f"Instalación, parametrización y puesta en marcha del variador ({caso.n_motores} motor(es) "
            "existente(s); no incluye suministro de motor ni de equipo accionado)",
            caso.n_motores,
            PRECIO_INSTALACION * caso.n_motores,
        )
    )
    return resultado


def totales(caso: Caso) -> tuple[Decimal, Decimal, Decimal]:
    base = sum((b for _, _, b in lineas(caso)), Decimal("0.00"))
    iva = (base * IVA).quantize(Decimal("0.01"))
    return base, iva, base + iva


def seccion(caso: Caso) -> Seccion:
    s = Seccion(TIPO, TITULO)
    f = s.flowables
    base, iva, total = totales(caso)
    f.append(subtitulo("Datos de la factura"))
    f.append(
        tabla_campos(
            [
                ("Número de factura", caso.factura_numero),
                ("Fecha de factura", fmt_fecha(caso.fechas.inicio)),
                ("Fecha de pedido", fmt_fecha(caso.fechas.inicio)),
                ("Emisor", caso.instalador.razon_social),
                ("NIF del emisor", caso.instalador.nif),
                ("Domicilio del emisor", caso.instalador.direccion),
                ("Receptor (cliente)", caso.titular.razon_social_variante()),
                ("NIF del receptor", caso.titular.nif),
                ("Domicilio del receptor", caso.titular.direccion),
                ("Nº de variadores facturados", str(caso.n_motores)),
            ]
        )
    )
    f.append(subtitulo("Líneas"))
    filas = [
        (str(i), d, str(c), f"{fmt_es(b / c, 2)} €", f"{fmt_es(b, 2)} €")
        for i, (d, c, b) in enumerate(lineas(caso), start=1)
    ]
    f.append(tabla(["Nº", "Descripción", "Cant.", "Precio unitario", "Base"], filas, [8, 102, 12, 24, 24]))
    f.append(espacio(3))
    f.append(
        tabla_campos(
            [
                ("Base imponible", f"{fmt_es(base, 2)} €"),
                ("IVA (21 %)", f"{fmt_es(iva, 2)} €"),
                ("Total factura", f"{fmt_es(total, 2)} €"),
                ("Forma de pago", "Transferencia a 30 días"),
            ]
        )
    )
    f.append(
        p(
            f"Factura nº {caso.factura_numero} de fecha {fmt_fecha(caso.fechas.inicio)} emitida por "
            f"{caso.instalador.razon_social} (NIF {caso.instalador.nif}) a "
            f"{caso.titular.razon_social_variante()} (NIF {caso.titular.nif}). "
            f"Base imponible {fmt_es(base, 2)} €, IVA 21 % {fmt_es(iva, 2)} €, total {fmt_es(total, 2)} €. "
            "Los motores y los equipos accionados son existentes y no forman parte del "
            "suministro."
        )
    )
    f.append(
        nota("Documento sintético generado para pruebas del CAE Engine. Ninguna entidad ni persona es real.")
    )
    return s
