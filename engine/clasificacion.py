"""Clasificacion lexica de documentos (A1 en la Fase 0): que tipo de la spec es cada fichero, con confianza.

`clasificar(doc, spec) -> Documento` asigna `tipo`, `confianza_tipo` y, cuando procede, `subtipo`. Los tipos
posibles son exactamente los `documentacion[].tipo` de la spec activa: este modulo **no** conoce la ficha,
un lexico por tipo de documento (titulos y campos caracteristicos) que vive aqui y que en el Sprint 3
sustituye o contrasta el agente A1 (LLM) detras de la misma funcion.

Como se decide (heuristicas declaradas; van a `docs/03` §8):

1. **Titulo**: la linea de mayor cuerpo de la primera pagina (`ingesta.titulo_de_pagina`). Un tipo casa si
   todos los terminos de alguno de sus grupos aparecen en el titulo normalizado y ninguno de sus terminos
   excluidos. Gana el grupo mas especifico (mas terminos), que es como se separa "Registro de horas de
   funcionamiento previo" de "Registro de funcionamiento".
2. **Campos caracteristicos**: etiquetas que ese tipo de documento suele traer, buscadas en las tablas y en
   el texto. Aportan la parte proporcional de la confianza.
3. `confianza = PESO_TITULO * titulo + PESO_CAMPOS * (campos hallados / campos del tipo)`, con `Decimal`.
   Por debajo de `CONFIANZA_MINIMA` el documento queda **sin clasificar** (`tipo = None`,
   `confianza_tipo = 0`) y deja aviso `documento_no_clasificado`: es el `notas.pdf` del caso G. Nunca se
   fuerza un tipo para "colocar" un fichero.
4. **Imagenes sueltas**: se clasifican por el EXIF `ImageDescription` (papel de la foto), no por el nombre
   del fichero; el papel da el `subtipo` (`foto_antes`, `foto_despues`, `placa`). Un papel desconocido deja
   la imagen sin clasificar (la foto irrelevante del caso G).
5. **xlsx**: por su estructura (hojas y cabecera que `ingesta` dejo en `exif`), no por el nombre: `datos.xlsx`
   se clasifica igual que `06_registro_funcionamiento_MTR-SYN-0001.xlsx` (regla de oro: nunca por nombre).
6. Un PDF ya marcado `combinado` por la ingesta conserva su tipo; sus partes se clasifican una a una.

La clasificacion no lee `_resultados_esperados/` ni usa el `/Info` del PDF (que en un documento sintetico
llevaria el titulo servido en bandeja): solo contenido.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from engine.ingesta import (
    FORMATO_IMAGEN,
    FORMATO_PDF,
    FORMATO_XLSX,
    TIPO_COMBINADO,
    Documento,
)

PESO_TITULO = Decimal("0.6")
PESO_CAMPOS = Decimal("0.4")
PESO_CAMPOS_SIN_TITULO = Decimal("0.5")
CONFIANZA_MINIMA = Decimal("0.3")
CONFIANZA_EXIF = Decimal("0.9")
CONFIANZA_ESTRUCTURA = Decimal("0.9")
AVISO_NO_CLASIFICADO = "documento_no_clasificado"

SUBTIPO_FOTO_ANTES = "foto_antes"
SUBTIPO_FOTO_DESPUES = "foto_despues"
SUBTIPO_PLACA = "placa"

TIPO_INFORME_FOTOGRAFICO = "informe_fotografico"
TIPO_REGISTRO_FUNCIONAMIENTO = "registro_funcionamiento"


@dataclass(frozen=True)
class Lexico:
    """Senales de un tipo de documento: grupos de terminos del titulo, exclusiones y campos tipicos."""

    titulos: tuple[frozenset[str], ...]
    campos: tuple[str, ...]
    excluye: frozenset[str] = frozenset()


def normalizar(texto: str) -> str:
    """Minusculas, sin tildes y con los espacios colapsados (comparacion de etiquetas y titulos)."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn"
    )
    return " ".join(sin_tildes.lower().replace("º", "o").replace("°", "o").split())


LEXICO: dict[str, Lexico] = {
    "ficha_cumplimentada": Lexico(
        titulos=(frozenset({"ficha", "cumplimentada"}),),
        campos=(
            "codigo de ficha",
            "nif del titular",
            "fecha de inicio de la actuacion",
            "fecha de fin de la actuacion",
            "numero de motores incluidos",
            "firma del representante legal",
        ),
    ),
    "declaracion_responsable": Lexico(
        titulos=(frozenset({"declaracion", "responsable"}),),
        campos=(
            "razon social del titular",
            "declara bajo su responsabilidad",
            "ayudas publicas",
            "propietario inicial del ahorro",
        ),
    ),
    "factura": Lexico(
        titulos=(frozenset({"factura"}),),
        campos=(
            "numero de factura",
            "fecha de factura",
            "nif del emisor",
            "nif del receptor",
            "base imponible",
            "total factura",
        ),
        excluye=frozenset({"proforma"}),
    ),
    "informe_fotografico": Lexico(
        titulos=(frozenset({"informe", "fotografico"}),),
        campos=(
            "numero de motores fotografiados",
            "placa de caracteristicas",
            "antes",
            "despues",
        ),
    ),
    "certificado_instalador": Lexico(
        titulos=(
            frozenset({"certificado", "instaladora"}),
            frozenset({"certificado", "instalador"}),
        ),
        campos=(
            "empresa instaladora",
            "fecha de puesta en marcha",
            "sha-256 del registro",
            "certifica",
            "velocidad media con variador",
        ),
        excluye=frozenset({"competente"}),
    ),
    "certificado_tecnico_competente": Lexico(
        titulos=(frozenset({"certificado", "tecnico", "competente"}),),
        campos=("tecnico competente", "personal propio", "colegiado"),
    ),
    "registro_funcionamiento": Lexico(
        titulos=(frozenset({"registro", "funcionamiento"}),),
        campos=("velocidad", "potencia", "marcha", "intervalo"),
        excluye=frozenset({"previo", "horas"}),
    ),
    "registro_horas_previo": Lexico(
        titulos=(frozenset({"registro", "horas", "previo"}), frozenset({"registro", "horas"})),
        campos=(
            "horas anuales de funcionamiento",
            "periodo representativo",
            "regimen de funcionamiento",
            "origen del dato",
        ),
    ),
    "ficha_tecnica_motor": Lexico(
        titulos=(frozenset({"ficha", "tecnica", "motor"}),),
        campos=(
            "potencia nominal",
            "velocidad nominal",
            "no de serie del motor",
            "clase de eficiencia",
            "numero de polos",
        ),
        excluye=frozenset({"variador", "accionado"}),
    ),
    "ficha_tecnica_variador": Lexico(
        titulos=(frozenset({"ficha", "tecnica", "variador"}),),
        campos=(
            "no de serie del variador",
            "perdidas declaradas",
            "rendimiento a carga nominal",
            "tension de alimentacion",
        ),
        excluye=frozenset({"accionado"}),
    ),
    "ficha_tecnica_equipo_accionado": Lexico(
        titulos=(
            frozenset({"ficha", "tecnica", "equipo", "accionado"}),
            frozenset({"ficha", "tecnica", "bomba"}),
            frozenset({"ficha", "tecnica", "ventilador"}),
            frozenset({"ficha", "tecnica", "compresor"}),
        ),
        campos=(
            "tipo de equipo",
            "principio de funcionamiento",
            "motor asociado",
            "rotodinamico",
        ),
    ),
    "convenio_cae": Lexico(
        titulos=(frozenset({"convenio"}),),
        campos=(
            "sujeto delegado",
            "ahorro anual",
            "vida util de la actuacion",
            "referencia catastral",
            "tipo de contraprestacion",
        ),
    ),
    "pedido": Lexico(
        titulos=(frozenset({"pedido"}), frozenset({"presupuesto", "aceptado"})),
        campos=("numero de pedido", "fecha de pedido", "proveedor"),
    ),
}

# Papel declarado en el EXIF `ImageDescription` → (tipo de documento, subtipo)
PAPELES_EXIF: tuple[tuple[str, str, str], ...] = (
    ("placa de caracteristicas", TIPO_INFORME_FOTOGRAFICO, SUBTIPO_PLACA),
    ("foto antes", TIPO_INFORME_FOTOGRAFICO, SUBTIPO_FOTO_ANTES),
    ("foto despues", TIPO_INFORME_FOTOGRAFICO, SUBTIPO_FOTO_DESPUES),
)

# Estructura de un xlsx (hojas y cabecera) → tipo de documento
COLUMNAS_REGISTRO = ("estado", "velocidad", "potencia")


def _grupo_coincide(titulo: str, grupo: frozenset[str]) -> bool:
    return all(termino in titulo for termino in grupo)


def tipo_por_titulo(titulo: str) -> tuple[str | None, Decimal]:
    """Tipo que sugiere un titulo de pagina y su confianza (solo titulo). Gana el grupo mas especifico.

    Lo usa tambien `ingesta.separar` para detectar los cortes de un PDF combinado.
    """
    normalizado = normalizar(titulo)
    if not normalizado:
        return None, Decimal(0)
    mejor_tipo: str | None = None
    mejor_tamano = 0
    for tipo, lexico in LEXICO.items():
        if any(excluido in normalizado for excluido in lexico.excluye):
            continue
        for grupo in lexico.titulos:
            if _grupo_coincide(normalizado, grupo) and len(grupo) > mejor_tamano:
                mejor_tipo, mejor_tamano = tipo, len(grupo)
    if mejor_tipo is None:
        return None, Decimal(0)
    return mejor_tipo, PESO_TITULO


def _texto_normalizado(doc: Documento) -> str:
    partes: list[str] = []
    for pagina in doc.paginas:
        if pagina.texto:
            partes.append(pagina.texto)
        if pagina.texto_ocr:
            partes.append(pagina.texto_ocr)
        for tabla in pagina.tablas:
            for fila in tabla:
                partes.append(" ".join(celda for celda in fila if celda))
    return normalizar(" \n ".join(partes))


def _titulo_de(doc: Documento) -> str:
    if not doc.paginas:
        return ""
    return doc.exif.get(f"titulo_pagina_{doc.paginas[0].numero}", "")


def puntuar(doc: Documento, tipos: tuple[str, ...]) -> list[tuple[str, Decimal]]:
    """Confianza de cada tipo candidato para el documento, de mayor a menor."""
    titulo = _titulo_de(doc)
    tipo_titulo, _ = tipo_por_titulo(titulo)
    cuerpo = _texto_normalizado(doc)
    puntuaciones: list[tuple[str, Decimal]] = []
    for tipo in tipos:
        lexico = LEXICO.get(tipo)
        if lexico is None:
            continue
        hallados = sum(1 for campo in lexico.campos if campo in cuerpo)
        proporcion = Decimal(hallados) / Decimal(len(lexico.campos)) if lexico.campos else Decimal(0)
        if tipo == tipo_titulo:
            confianza = PESO_TITULO + PESO_CAMPOS * proporcion
        elif any(excluido in cuerpo for excluido in lexico.excluye):
            continue
        else:
            confianza = PESO_CAMPOS_SIN_TITULO * proporcion
        if confianza > 0:
            puntuaciones.append((tipo, confianza))
    puntuaciones.sort(key=lambda par: (-par[1], par[0]))
    return puntuaciones


def tipos_de_spec(spec: object) -> tuple[str, ...]:
    """Tipos declarados en `documentacion` de la spec activa (la clasificacion no inventa tipos)."""
    documentacion = getattr(spec, "documentacion", None) or []
    tipos: list[str] = []
    for declaracion in documentacion:
        tipo = declaracion.get("tipo") if hasattr(declaracion, "get") else None
        if isinstance(tipo, str) and tipo not in tipos:
            tipos.append(tipo)
    return tuple(tipos)


def _clasificar_imagen(doc: Documento) -> bool:
    """Imagen suelta: el papel del EXIF manda. `True` si quedo clasificada."""
    descripcion = normalizar(doc.exif.get("descripcion", ""))
    if not descripcion:
        return False
    for papel, tipo, subtipo in PAPELES_EXIF:
        if papel in descripcion:
            doc.tipo = tipo
            doc.subtipo = subtipo
            doc.confianza_tipo = CONFIANZA_EXIF
            doc.avisar(
                f"foto_suelta_clasificada_por_exif: '{doc.nombre}' es {subtipo} ({tipo}) segun su EXIF"
            )
            return True
    return False


def _clasificar_xlsx(doc: Documento) -> bool:
    """xlsx: por hojas y cabecera, nunca por nombre de fichero."""
    hojas = normalizar(doc.exif.get("hojas", ""))
    columnas = normalizar(doc.exif.get("columnas", ""))
    if all(columna in columnas for columna in COLUMNAS_REGISTRO) or "registro" in hojas:
        doc.tipo = TIPO_REGISTRO_FUNCIONAMIENTO
        doc.confianza_tipo = CONFIANZA_ESTRUCTURA
        return True
    return False


def clasificar(doc: Documento, spec: object) -> Documento:
    """Asigna `tipo`, `confianza_tipo` y `subtipo`. Nunca lanza: lo no clasificable deja aviso."""
    if doc.tipo == TIPO_COMBINADO:
        return doc
    tipos = tipos_de_spec(spec) or tuple(LEXICO)
    clasificado = False
    if doc.formato == FORMATO_IMAGEN:
        clasificado = _clasificar_imagen(doc)
    elif doc.formato == FORMATO_XLSX:
        clasificado = _clasificar_xlsx(doc)
    elif doc.formato == FORMATO_PDF:
        puntuaciones = puntuar(doc, tipos)
        if puntuaciones and puntuaciones[0][1] >= CONFIANZA_MINIMA:
            doc.tipo, doc.confianza_tipo = puntuaciones[0]
            clasificado = True
    if clasificado and doc.tipo is not None and doc.tipo not in tipos and tipos:
        doc.avisar(
            f"tipo_fuera_de_spec: '{doc.nombre}' se leyo como {doc.tipo}, que la ficha activa no declara"
        )
    if not clasificado:
        doc.tipo = None
        doc.confianza_tipo = Decimal(0)
        doc.avisar(f"{AVISO_NO_CLASIFICADO}: '{doc.nombre}' no corresponde a ningun tipo de la ficha")
    return doc


def clasificar_todos(documentos: list[Documento], spec: object) -> list[Documento]:
    """Clasifica la lista completa (las partes de un combinado tambien, una a una)."""
    return [clasificar(doc, spec) for doc in documentos]
