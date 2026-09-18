"""PRC-01: convenio CAE entre el propietario inicial del ahorro y el sujeto delegado. Cada requisito de
`documentacion[PRC-01].requisitos` de la spec aparece como epígrafe reconocible. El ahorro anual declarado es
el AETOTAL_cae calculado con `engine/calculo.py` (en D también, aunque la actuación esté fuera de ámbito)."""

from __future__ import annotations

from generator.documentos.base import Seccion, nota, p, subtitulo, tabla_campos
from generator.modelo_caso import Caso, fmt_es, fmt_fecha

TIPO = "convenio_cae"
TITULO = "Convenio CAE – Cesión del ahorro de energía final"


def seccion(caso: Caso, ahorro_kwh: int) -> Seccion:
    s = Seccion(TIPO, TITULO)
    f = s.flowables
    conv = caso.convenio
    deleg = conv.sujeto_delegado
    f.append(
        p(
            f"Convenio nº {conv.numero} suscrito al amparo del artículo 11 de la Orden TED/815/2023 entre el "
            "propietario inicial del ahorro y el sujeto delegado, para la cesión del ahorro de energía final "
            "de "
            "la actuación que se describe."
        )
    )
    f.append(subtitulo("1. Identificación de partes (NIF y razón social)"))
    f.append(
        tabla_campos(
            [
                ("Propietario inicial del ahorro (razón social)", caso.titular.razon_social),
                ("NIF del propietario inicial", caso.titular.nif),
                (
                    "Representante del propietario inicial",
                    f"{caso.titular.representante.nombre} ({caso.titular.representante.nif})",
                ),
                ("Sujeto delegado (razón social)", deleg.razon_social),
                ("NIF del sujeto delegado", deleg.nif),
                (
                    "Representante del sujeto delegado",
                    f"{deleg.representante.nombre} ({deleg.representante.nif})",
                ),
            ]
        )
    )
    f.append(subtitulo("2. Título descriptivo de la actuación"))
    f.append(tabla_campos([("Título descriptivo", conv.titulo), ("Ficha aplicable", "IND240 V1.1")]))
    f.append(subtitulo("3. Localización (UTM y referencia catastral)"))
    loc = caso.localizacion
    f.append(
        tabla_campos(
            [
                ("Dirección", loc.direccion),
                ("Coordenada UTM X", f"{fmt_es(loc.utm_x)} m"),
                ("Coordenada UTM Y", f"{fmt_es(loc.utm_y)} m"),
                ("Huso UTM", f"{loc.huso} (ETRS89)"),
                ("Referencia catastral", loc.referencia_catastral),
            ]
        )
    )
    f.append(subtitulo("4. Ahorro anual (kWh)"))
    f.append(
        tabla_campos(
            [
                ("Ahorro anual de energía final", f"{fmt_es(ahorro_kwh)} kWh"),
                ("Número de motores", str(caso.n_motores)),
                ("Fecha de fin de la actuación", fmt_fecha(caso.fechas.fin)),
            ]
        )
    )
    f.append(
        p(
            f"El ahorro anual de energía final estimado para la actuación es de {fmt_es(ahorro_kwh)} kWh, "
            "calculado conforme a la fórmula de la ficha IND240."
        )
    )
    f.append(subtitulo("5. Tipo de contraprestación"))
    f.append(tabla_campos([("Tipo de contraprestación", conv.tipo_contraprestacion)]))
    f.append(subtitulo("6. Vida útil de la actuación"))
    f.append(tabla_campos([("Vida útil de la actuación", f"{conv.vida_util_anos} años")]))
    f.append(subtitulo("7. Declaración de no suscribir otros convenios por la misma actuación"))
    f.append(
        p(
            "El propietario inicial del ahorro declara que no ha suscrito ni suscribirá otros convenios por "
            "la "
            "misma actuación con ningún otro sujeto obligado o delegado."
        )
    )
    f.append(subtitulo("8. Fecha de firma"))
    f.append(
        tabla_campos(
            [
                ("Fecha de firma del convenio", fmt_fecha(caso.fechas.firma_convenio)),
                ("Firmado electrónicamente por el propietario inicial", caso.titular.representante.nombre),
                ("Firmado electrónicamente por el sujeto delegado", deleg.representante.nombre),
            ]
        )
    )
    f.append(p(f"Firmado electrónicamente por ambas partes el {fmt_fecha(caso.fechas.firma_convenio)}."))
    f.append(
        nota("Documento sintético generado para pruebas del CAE Engine. Ninguna entidad ni persona es real.")
    )
    return s
