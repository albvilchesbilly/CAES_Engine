"""DOC-02: declaración responsable (Anexo I) del propietario inicial del ahorro sobre ayudas públicas.
La razón social se escribe con puntuación distinta ("SL", sin coma) para ejercitar `cruce: normalizado`."""

from __future__ import annotations

from generator.documentos.base import Seccion, nota, p, subtitulo, tabla_campos
from generator.modelo_caso import Caso, fmt_fecha

TIPO = "declaracion_responsable"
TITULO = "Declaración responsable (Anexo I) – Propietario inicial del ahorro"


def seccion(caso: Caso) -> Seccion:
    s = Seccion(TIPO, TITULO)
    f = s.flowables
    rep = caso.titular.representante
    razon = caso.titular.razon_social_variante()
    f.append(subtitulo("Datos del declarante"))
    f.append(
        tabla_campos(
            [
                ("Razón social del titular", razon),
                ("NIF del titular", caso.titular.nif),
                ("Domicilio", caso.titular.direccion),
                ("Representante legal", f"{rep.nombre} ({rep.cargo})"),
                ("NIF del representante", rep.nif),
                ("Actuación", "IND240 – Implantación de variador de velocidad en motor eléctrico existente"),
            ]
        )
    )
    f.append(subtitulo("Declaración"))
    f.append(
        p(
            f"D./Dña. {rep.nombre}, con NIF {rep.nif}, en calidad de {rep.cargo.lower()} de {razon}, con NIF "
            f"{caso.titular.nif}, DECLARA BAJO SU RESPONSABILIDAD:"
        )
    )
    for texto in (
        "Primero. Que la actuación de eficiencia energética descrita no ha recibido ni recibirá ayudas "
        "públicas incompatibles con la obtención de certificados de ahorro energético, y que en caso de "
        "haber solicitado "
        "otras ayudas se detallarán en el apartado correspondiente de la solicitud.",
        "Segundo. Que es el propietario inicial del ahorro de energía final generado por la actuación y que "
        "no ha "
        "cedido ni cederá dicho ahorro a ningún otro sujeto salvo lo previsto en el convenio CAE suscrito.",
        "Tercero. Que los datos aportados en la ficha IND240 y en la documentación justificativa son ciertos "
        "y "
        "verificables.",
        "Cuarto. Que conoce que la falsedad en esta declaración conlleva la denegación o revocación del "
        "certificado.",
    ):
        f.append(p(texto))
    f.append(subtitulo("Ayudas públicas"))
    f.append(
        tabla_campos(
            [
                ("Ayudas públicas solicitadas para la actuación", "Ninguna"),
                ("Ayudas públicas recibidas para la actuación", "Ninguna"),
            ]
        )
    )
    f.append(subtitulo("Firma"))
    f.append(
        tabla_campos(
            [
                ("Firmado electrónicamente por", f"{rep.nombre}, NIF {rep.nif}"),
                ("Fecha", fmt_fecha(caso.fechas.firma_ficha)),
            ]
        )
    )
    f.append(
        nota("Documento sintético generado para pruebas del CAE Engine. Ninguna entidad ni persona es real.")
    )
    return s
