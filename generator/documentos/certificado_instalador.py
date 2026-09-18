"""DOC-05: certificado de la empresa instaladora (apartados a y b) con la huella SHA-256 del registro
(INT-05). En C, PM se escribe con el valor de `variaciones.pm_certificado`; en B no hay registro y se omite
la huella."""

from __future__ import annotations

from generator.documentos.base import Seccion, bloque, espacio, mono, nota, p, subtitulo, tabla_campos
from generator.modelo_caso import REGIMEN_TEXTO, Caso, fmt_es, fmt_fecha

TIPO = "certificado_instalador"
TITULO = "Certificado de la empresa instaladora – Ficha IND240 (apartados a y b)"


def seccion(caso: Caso, huellas: dict[str, str]) -> Seccion:
    """`huellas`: num_serie_motor → SHA-256 de los datos canónicos del registro (vacío en B)."""
    s = Seccion(TIPO, TITULO)
    f = s.flowables
    rep = caso.instalador.representante
    f.append(subtitulo("Empresa instaladora y titular"))
    f.append(
        tabla_campos(
            [
                ("Empresa instaladora", caso.instalador.razon_social),
                ("NIF de la empresa instaladora", caso.instalador.nif),
                ("Técnico responsable", f"{rep.nombre} ({rep.cargo}), NIF {rep.nif}"),
                ("Titular de la instalación", caso.titular.razon_social),
                ("NIF del titular", caso.titular.nif),
                ("Emplazamiento", caso.localizacion.direccion),
                ("Fecha de puesta en marcha (fin de la actuación)", fmt_fecha(caso.fechas.fin)),
                ("Número de motores intervenidos", str(caso.n_motores)),
            ]
        )
    )
    f.append(
        p(
            f"{rep.nombre}, en nombre de {caso.instalador.razon_social}, CERTIFICA que el "
            f"{fmt_fecha(caso.fechas.fin)} quedó completada y en funcionamiento la instalación de "
            f"{caso.n_motores} variador(es) de velocidad sobre motor(es) eléctrico(s) existente(s) en las "
            f"instalaciones de {caso.titular.razon_social}, con los datos que se detallan por motor."
        )
    )
    for i, m in enumerate(caso.motores, start=1):
        pm = caso.pm_en_certificado(m)
        filas_a = [
            ("Nº de serie del motor", m.num_serie_motor),
            ("Nº de serie del variador", m.num_serie_variador),
            ("Tipo de equipo accionado", f"{m.equipo.tipo_texto} ({m.equipo.tipo})"),
            ("Régimen de funcionamiento previo", f"{REGIMEN_TEXTO[m.regimen_previo]} ({m.regimen_previo})"),
            ("a) Potencia nominal del motor PM (según ficha técnica)", f"{fmt_es(pm)} kW"),
            ("a) Velocidad nominal N1 (según ficha técnica)", f"{fmt_es(m.N1)} rpm"),
        ]
        filas_b = [
            ("b) Potencia promedio con variador P_prom", f"{fmt_es(m.P_prom, 1)} kW"),
            ("b) Velocidad media con variador N2", f"{fmt_es(m.N2)} rpm"),
        ]
        if m.num_serie_motor in huellas:
            periodo = f"{fmt_fecha(caso.fechas.registro_inicio)}–{fmt_fecha(caso.fechas.registro_fin)}"
            filas_b += [
                ("b) Registro de funcionamiento (fichero)", caso.nombre_registro(m)),
                ("b) Periodo del registro", f"{periodo} ({caso.fechas.dias_registro} días)"),
                ("b) SHA-256 del registro", mono(huellas[m.num_serie_motor])),
            ]
        prosa = (
            f"Motor {i}: {m.descripcion}. Antes de la actuación el motor giraba a {fmt_es(m.N1)} rpm en "
            f"{REGIMEN_TEXTO[m.regimen_previo].lower()}. Con el variador la velocidad media es de "
            f"{fmt_es(m.N2)} rpm y la potencia promedio de {fmt_es(m.P_prom, 1)} kW."
        )
        if m.num_serie_motor in huellas:
            prosa += (
                f" Registro de funcionamiento: fichero {caso.nombre_registro(m)}, periodo "
                f"{fmt_fecha(caso.fechas.registro_inicio)}–{fmt_fecha(caso.fechas.registro_fin)}, "
                f"SHA-256: {huellas[m.num_serie_motor]}."
            )
        f.append(
            bloque(
                s.marcador(m.num_serie_motor),
                subtitulo(f"Motor {i} de {caso.n_motores}: {m.num_serie_motor}"),
                tabla_campos(filas_a + filas_b, ancho_etiqueta_mm=64),
                espacio(1),
                p(prosa),
                espacio(2),
            )
        )
    f.append(subtitulo("Firma"))
    f.append(
        tabla_campos(
            [
                ("Firmado por", f"{rep.nombre}, {rep.cargo}"),
                ("Empresa", f"{caso.instalador.razon_social} ({caso.instalador.nif})"),
                ("Fecha", fmt_fecha(caso.fechas.fin)),
            ]
        )
    )
    f.append(
        nota("Documento sintético generado para pruebas del CAE Engine. Ninguna entidad ni persona es real.")
    )
    return s
