"""Ground truth de un caso (docs/05 §3) a partir del mismo modelo que produce los documentos.

Campos (los fija este módulo; `docs/01` §3.5 los documenta):

- `caso`, `id`, `descripcion`, `ficha`, `version_ficha`, `version_spec`, `fecha_evaluacion`
- `veredicto_esperado`, `reglas_falladas_esperadas`, `reglas_no_evaluables_esperadas`
- `aetotal_esperado {exacto, cae, provisional}`: `exacto`/`cae` son `null` si el Engine no debe publicar
  ahorro (C, D); `referencia_no_publicada` guarda entonces el valor que daría la fórmula con los datos del
  modelo.
- `motores[]`: por motor, las entradas y derivadas de `engine/calculo.py` (`a_dict`), como cadenas `Decimal`.
  En B `h_despues` es `null` (no hay registro) y `h = h_antes`.
- `variables_consolidadas.actuacion` y `.motores.<num_serie>`: por variable `valor`, `evidencia`
  (demostrado | declarado | derivado), `fuentes` (documentos nativos: tipo, fichero, página) y `fuentes_ocr`
  (placa fotografiada), `fuente_primaria` si la spec la declara, `conflicto` cuando `valor` es `null`.
- `hechos_documentales`: lo que la extracción debe producir además de las variables (ADR-002 §2.3).
- `conflictos_esperados`: variables con `valor_consumido = null` y las dos evidencias (solo C).
- `documentos[]`: fichero, tipo, sha256, formato, `partes` (PDF combinado), `subtipo`, `irrelevante`.
- `avisos_esperados`: avisos de ingesta/clasificación (solo G).
- `registro`: formato canónico, periodo y huella por motor (`ausente: true` en B).
- `trampas`: presencia de cada trampa de docs/05 §4.3 en el caso, para `test_generator.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.calculo import a_dict
from engine.spec_registry import Spec
from generator.documentos import factura as doc_factura
from generator.documentos.registro import FORMATO_CANONICO, INTERVALO_MIN
from generator.marcas import MARCA
from generator.modelo_caso import Motor

if TYPE_CHECKING:
    from generator.generar import CasoGenerado

PLACA = "placa_caracteristicas_foto"
REGISTRO = "registro_funcionamiento"
INFORME = "informe_fotografico"
CONFIANZA_OCR = "0.75"


def _localizar(generado: CasoGenerado, tipo: str, clave: str | None = None) -> dict[str, object] | None:
    """Fichero y página donde debe hallarse `tipo` (y el bloque `clave`, p. ej. un nº de serie)."""
    for f in generado.ficheros:
        if f.irrelevante:
            continue
        for s in f.secciones:
            if s.tipo != tipo:
                continue
            if clave is not None and f.num_serie_motor not in (None, clave) and clave not in s.paginas:
                continue
            pagina = s.paginas.get(clave, s.pagina_inicio) if clave else s.pagina_inicio
            fuente: dict[str, object] = {"tipo": tipo, "fichero": f.nombre, "pagina": pagina}
            if f.tipo == "combinado":
                fuente["parte"] = {"tipo": tipo, "pagina_inicio": s.pagina_inicio, "pagina_fin": s.pagina_fin}
            return fuente
        if f.tipo == tipo and not f.secciones:
            if clave is not None and f.num_serie_motor not in (None, clave):
                continue
            return {"tipo": tipo, "fichero": f.nombre, "pagina": 0}
    return None


def _placa(generado: CasoGenerado, motor: Motor) -> dict[str, object] | None:
    for f in generado.ficheros:
        if f.formato == "imagen" and f.subtipo == "placa" and f.num_serie_motor == motor.num_serie_motor:
            return {
                "tipo": PLACA,
                "fichero": f.nombre,
                "pagina": 0,
                "metodo": "ocr",
                "confianza": CONFIANZA_OCR,
            }
    ubicacion = _localizar(generado, INFORME, f"{motor.num_serie_motor}|placa")
    if ubicacion is None:
        return None
    return {**ubicacion, "tipo": PLACA, "metodo": "ocr", "confianza": CONFIANZA_OCR}


def _fuentes(generado: CasoGenerado, tipos: list[str], clave: str | None = None) -> list[dict[str, object]]:
    fuentes = []
    for tipo in tipos:
        ubicacion = _localizar(generado, tipo, clave)
        if ubicacion is not None:
            fuentes.append(ubicacion)
    return fuentes


def _variable(valor: object, evidencia: str, fuentes: list, **extra: object) -> dict[str, object]:
    dato: dict[str, object] = {"valor": valor, "evidencia": evidencia, "fuentes": fuentes}
    dato.update(extra)
    return dato


def _variables_actuacion(generado: CasoGenerado, spec: Spec) -> dict[str, dict[str, object]]:
    caso = generado.caso
    v = spec.variables
    return {
        "titular_nif": _variable(
            caso.titular.nif, "demostrado", _fuentes(generado, list(v["titular_nif"]["fuentes"]))
        ),
        "titular_razon_social": _variable(
            caso.titular.razon_social,
            "demostrado",
            _fuentes(generado, list(v["titular_razon_social"]["fuentes"])),
            variantes=sorted({caso.titular.razon_social, caso.titular.razon_social_variante()}),
            cruce="normalizado",
        ),
        "fecha_inicio_actuacion": _variable(
            caso.fechas.inicio.isoformat(),
            "demostrado",
            _fuentes(generado, list(v["fecha_inicio_actuacion"]["fuentes"])),
        ),
        "fecha_fin_actuacion": _variable(
            caso.fechas.fin.isoformat(),
            "demostrado",
            _fuentes(generado, list(v["fecha_fin_actuacion"]["fuentes"])),
        ),
        "n_motores": _variable(
            caso.n_motores,
            "demostrado",
            _fuentes(generado, ["factura", "certificado_instalador", "ficha_cumplimentada", INFORME])
            + [
                {"tipo": REGISTRO, "fichero": f.nombre, "pagina": 0}
                for f in generado.ficheros
                if f.tipo == REGISTRO
            ],
        ),
    }


def _variables_motor(generado: CasoGenerado, spec: Spec, motor: Motor) -> dict[str, dict[str, object]]:
    caso = generado.caso
    serie = motor.num_serie_motor
    v = spec.variables
    hay_registro = serie in generado.registros
    conflicto_pm = serie in caso.variaciones.pm_certificado

    def nativas(nombre: str) -> list[dict[str, object]]:
        return _fuentes(generado, [t for t in v[nombre]["fuentes"] if t != PLACA], serie)

    placa = _placa(generado, motor)
    fuentes_ocr = [placa] if placa else []
    pm = _variable(
        None if conflicto_pm else str(motor.PM),
        "demostrado",
        nativas("PM"),
        fuentes_ocr=fuentes_ocr,
        fuente_primaria=v["PM"]["fuente_primaria"],
        unidad="kW",
        conflicto=conflicto_pm,
    )
    if conflicto_pm:
        pm["valores_por_fuente"] = {
            "ficha_tecnica_motor": str(motor.PM),
            "ficha_cumplimentada": str(motor.PM),
            "certificado_instalador": str(caso.pm_en_certificado(motor)),
        }
    n2_declaradas = _fuentes(generado, list(v["N2"]["cruce_con"]), serie)
    p_prom_declaradas = _fuentes(generado, list(v["P_prom"]["cruce_con"]), serie)
    registro_fuente = _fuentes(generado, [REGISTRO], serie) if hay_registro else []
    return {
        "num_serie_motor": _variable(serie, "demostrado", nativas("num_serie_motor")),
        "num_serie_variador": _variable(
            motor.num_serie_variador, "demostrado", nativas("num_serie_variador")
        ),
        "tipo_equipo_accionado": _variable(
            motor.tipo_equipo_accionado, "demostrado", nativas("tipo_equipo_accionado")
        ),
        "regimen_previo": _variable(motor.regimen_previo, "demostrado", nativas("regimen_previo")),
        "PM": pm,
        "N1": _variable(
            str(motor.N1),
            "demostrado",
            nativas("N1"),
            fuentes_ocr=fuentes_ocr,
            fuente_primaria=v["N1"]["fuente_primaria"],
            unidad="rpm",
        ),
        "N2": _variable(
            str(motor.N2),
            "derivado" if hay_registro else "declarado",
            registro_fuente if hay_registro else n2_declaradas,
            fuentes_declaradas=n2_declaradas,
            unidad="rpm",
            interpretacion="INT-03" if hay_registro else None,
            tolerancia_cruce_rpm="1",
        ),
        "P_prom": _variable(
            str(motor.P_prom),
            "derivado" if hay_registro else "declarado",
            registro_fuente if hay_registro else p_prom_declaradas,
            fuentes_declaradas=p_prom_declaradas,
            unidad="kW",
            tolerancia_cruce_kw="0.5",
        ),
        "h_antes": _variable(str(motor.h_antes), "demostrado", nativas("h_antes"), unidad="h"),
        "h_despues": _variable(
            str(motor.h_despues) if hay_registro else None,
            "derivado",
            registro_fuente,
            unidad="h",
            interpretacion="INT-04" if hay_registro else None,
            ausente=not hay_registro,
        ),
    }


def _hechos(generado: CasoGenerado, spec: Spec) -> dict[str, object]:
    caso = generado.caso
    lineas = doc_factura.lineas(caso)
    convenio = next(d for d in spec.documentacion if d["tipo"] == "convenio_cae")
    hechos: dict[str, object] = {
        "factura.lineas": [
            {"descripcion": d, "categoria": "instalacion" if i == len(lineas) - 1 else "variador"}
            for i, (d, _, _) in enumerate(lineas)
        ],
        "factura.campos_minimos_presentes": True,
        "factura.menciona_motor_existente": True,
        "ficha_cumplimentada.firmada": True,
        "ficha_cumplimentada.ahorro_declarado_kwh": generado.calculo.total_cae
        if caso.variaciones.ficha_declara_ahorro
        else None,
        "convenio.requisitos_presentes": list(convenio["requisitos"]),
        "convenio.ahorro_kwh": generado.calculo.total_cae,
        "convenio.fecha_firma": caso.fechas.firma_convenio.isoformat(),
        "solicitud.fecha": caso.fechas.evaluacion.isoformat(),
    }
    for m in caso.motores:
        serie = m.num_serie_motor
        if serie in generado.registros:
            hechos[f"registro.hash_declarado[{serie}]"] = generado.registros[serie].sha256_canonico
            hechos[f"foto.antes[{serie}]"] = 1
            hechos[f"foto.despues[{serie}]"] = 1
        else:
            hechos[f"foto.antes[{serie}]"] = 1
            hechos[f"foto.despues[{serie}]"] = 1
    return hechos


def _conflictos(generado: CasoGenerado) -> list[dict[str, object]]:
    caso = generado.caso
    conflictos = []
    for m in caso.motores:
        if m.num_serie_motor not in caso.variaciones.pm_certificado:
            continue
        fiable = _localizar(generado, "ficha_tecnica_motor", m.num_serie_motor)
        certificado = _localizar(generado, "certificado_instalador", m.num_serie_motor)
        conflictos.append(
            {
                "variable": "PM",
                "num_serie_motor": m.num_serie_motor,
                "valor_consumido": None,
                "evidencias": [
                    {**(fiable or {}), "valor": str(m.PM), "texto_literal": f"{m.PM} kW"},
                    {
                        **(certificado or {}),
                        "valor": str(caso.pm_en_certificado(m)),
                        "texto_literal": f"{caso.pm_en_certificado(m)} kW",
                    },
                ],
                "nota": (
                    "La placa (OCR, 0,75) coincide con la ficha técnica; el conflicto es entre dos fuentes "
                    "fiables."
                ),
            }
        )
    return conflictos


def _documentos(generado: CasoGenerado) -> list[dict[str, object]]:
    salida = []
    for f in generado.ficheros:
        d: dict[str, object] = {"fichero": f.nombre, "tipo": f.tipo, "formato": f.formato, "sha256": f.sha256}
        if f.tipo == "combinado":
            d["partes"] = f.partes
        elif f.secciones:
            d["paginas"] = f.secciones[0].pagina_fin
        if f.subtipo:
            d["subtipo"] = f.subtipo
        if f.irrelevante:
            d["irrelevante"] = True
        if f.num_serie_motor:
            d["num_serie_motor"] = f.num_serie_motor
        if f.num_serie_variador:
            d["num_serie_variador"] = f.num_serie_variador
        salida.append(d)
    return salida


def _avisos(generado: CasoGenerado) -> list[dict[str, object]]:
    caso = generado.caso
    if not caso.variaciones.desordenado:
        return []
    avisos: list[dict[str, object]] = []
    for f in generado.ficheros:
        if f.irrelevante:
            avisos.append({"tipo": "documento_no_clasificado", "fichero": f.nombre})
        elif f.tipo == "combinado":
            avisos.append(
                {"tipo": "pdf_separado", "fichero": f.nombre, "partes": [p["tipo"] for p in f.partes]}
            )
        elif f.subtipo == "escaneo_girado":
            avisos.append(
                {"tipo": "escaneo_ocr", "fichero": f.nombre, "confianza": CONFIANZA_OCR, "giro_grados": 90}
            )
        elif f.formato == "xlsx":
            m = caso.motor(f.num_serie_motor or "")
            avisos.append(
                {
                    "tipo": "registro_vinculado_por_hash",
                    "fichero": f.nombre,
                    "nombre_declarado": caso.nombre_registro(m),
                    "sha256_canonico": generado.registros[m.num_serie_motor].sha256_canonico,
                }
            )
        elif f.formato == "imagen":
            avisos.append(
                {"tipo": "foto_suelta_clasificada_por_exif", "fichero": f.nombre, "subtipo": f.subtipo}
            )
    return avisos


def _registro(generado: CasoGenerado) -> dict[str, object]:
    caso = generado.caso
    if caso.variaciones.sin_registro:
        return {
            "ausente": True,
            "formato_canonico": FORMATO_CANONICO,
            "nota": "B: sin registro; N2 y P_prom solo declarados",
        }
    por_motor = {}
    for serie, r in generado.registros.items():
        fichero = next(f for f in generado.ficheros if f.formato == "xlsx" and f.num_serie_motor == serie)
        por_motor[serie] = {
            "fichero": fichero.nombre,
            "nombre_declarado": caso.nombre_registro(r.motor),
            "sha256_canonico": r.sha256_canonico,
            "sha256_fichero": fichero.sha256,
            "filas": len(r.filas),
            "filas_marcha": r.n_marcha,
            "N2_derivado": str(r.media_velocidad_marcha),
            "P_prom_derivado": str(r.media_potencia_marcha),
            "h_despues_derivado": str(r.h_despues_extrapolada),
        }
    return {
        "formato_canonico": FORMATO_CANONICO,
        "intervalo_min": INTERVALO_MIN,
        "inicio": caso.fechas.registro_inicio.isoformat(),
        "fin": caso.fechas.registro_fin.isoformat(),
        "dias": caso.fechas.dias_registro,
        "hoja_datos": "registro",
        "hoja_metadatos": "metadatos",
        "por_motor": por_motor,
    }


def _motores(generado: CasoGenerado) -> list[dict[str, object]]:
    caso = generado.caso
    resultado = a_dict(generado.calculo)
    motores = []
    for unidad in resultado["por_unidad"]:
        m = caso.motor(unidad["num_serie_motor"])
        datos: dict[str, object] = {
            "num_serie_motor": m.num_serie_motor,
            "num_serie_variador": m.num_serie_variador,
            "tipo_equipo_accionado": m.tipo_equipo_accionado,
            "regimen_previo": m.regimen_previo,
            **unidad["entradas"],
            **unidad["derivadas"],
            "AEM": unidad["salida"],
            "controles": unidad["controles"],
            "interpretaciones": unidad["interpretaciones"],
            "fuentes": unidad["fuentes"],
        }
        if caso.variaciones.sin_registro:
            datos["h_despues"] = None
            datos["nota"] = "sin registro: h_despues no derivable; cálculo provisional con h = h_antes"
        motores.append(datos)
    return motores


def _trampas(generado: CasoGenerado) -> dict[str, object]:
    caso = generado.caso
    return {
        "ficha_variador_declara_perdidas_kw": {
            m.num_serie_motor: str(m.perdidas_declaradas_variador) for m in caso.motores
        },
        "perdidas_ref_correctas_kw": {m["num_serie_motor"]: m["perdidas_ref_kw"] for m in _motores(generado)},
        "factura_menciona_motor_existente": True,
        "ficha_y_convenio_declaran_ahorro_fuera_de_ambito": caso.variaciones.ficha_declara_ahorro,
        "registro_renombrado": caso.variaciones.desordenado,
        "menor_h_es_h_despues": [m.num_serie_motor for m in caso.motores if m.h_despues < m.h_antes],
        "n2_solo_declarado": caso.variaciones.sin_registro,
        "placa_ocr": True,
    }


def construir(generado: CasoGenerado, spec: Spec) -> dict[str, object]:
    caso = generado.caso
    calculo = generado.calculo
    resultado = a_dict(calculo)
    publica = caso.calcula
    aetotal: dict[str, object] = {
        "exacto": resultado["total"] if publica else None,
        "cae": calculo.total_cae if publica else None,
        "provisional": bool(calculo.provisional),
    }
    if not publica:
        aetotal["referencia_no_publicada"] = resultado["total"]
    return {
        "caso": caso.carpeta,
        "id": caso.id,
        "descripcion": caso.descripcion,
        "marca": MARCA,
        "ficha": spec.codigo,
        "version_ficha": spec.version_ficha,
        "version_spec": spec.version_spec,
        "fecha_evaluacion": caso.fechas.evaluacion.isoformat(),
        "veredicto_esperado": caso.veredicto_esperado,
        "reglas_falladas_esperadas": list(caso.reglas_falladas_esperadas),
        "reglas_no_evaluables_esperadas": list(caso.reglas_no_evaluables_esperadas),
        "aetotal_esperado": aetotal,
        "interpretaciones_esperadas": resultado["interpretaciones"] if publica else [],
        "n_motores": caso.n_motores,
        "motores": _motores(generado),
        "variables_consolidadas": {
            "actuacion": _variables_actuacion(generado, spec),
            "motores": {m.num_serie_motor: _variables_motor(generado, spec, m) for m in caso.motores},
        },
        "hechos_documentales": _hechos(generado, spec),
        "conflictos_esperados": _conflictos(generado),
        "documentos": _documentos(generado),
        "avisos_esperados": _avisos(generado),
        "registro": _registro(generado),
        "trampas": _trampas(generado),
    }


def variables_de_calculo() -> list[str]:
    """Las seis variables de cálculo con evidencia que cuenta `evaluar_casos.py` (docs/05 §1; ADR-002)."""
    return ["PM", "N1", "N2", "h_antes", "h_despues", "P_prom"]


def motores_como_unidades(ground_truth: dict) -> dict[str, dict[str, str]]:
    """`motores[]` del ground truth como `unidades` para `engine.calculo.calcular` (B: h_despues =
    h_antes)."""
    unidades = {}
    for m in ground_truth["motores"]:
        valores = {n: m[n] for n in variables_de_calculo() if m.get(n) is not None}
        if m.get("h_despues") is None:
            valores["h_despues"] = m["h_antes"]
        unidades[m["num_serie_motor"]] = valores
    return unidades
