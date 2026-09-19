"""Contrato C17 (`ADR-012` §2): servir el documento, y las cuatro condiciones que lo rodean.

Un test por condicion del ADR, y despues lo que se intento para romperlo:

1. **Aislamiento por tenant**: un documento de otro tenant es `ErrorPermiso` explicito, no un vacio.
2. **Por huella y nunca por ruta**: la peticion no admite `ruta`; un `doc_id` que no es una huella se
   rechaza antes de tocar nada; una huella real de **otra** actuacion no se sirve.
3. **La huella se comprueba al servir**: si los bytes del disco cambiaron, no se sirve y se dice que el
   documento fue alterado.
4. **`R-UI-12`**: un perfil sin ambito de contenido documental no recibe los bytes, por los dos lados (la
   capacidad no proyecta el bloque, o el ambito del rol no lo admite).

Y la regla que no se negocia: **se sirve lo que entro en ingesta, byte a byte**. Hay un test que compara el
contenido servido con el fichero del banco de casos, y otro que comprueba la huella de lo servido.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

import pytest

from api.contrato import Peticion
from api.lecturas.documentos import (
    BLOQUE_CONTENIDO,
    CLAVE_DOCUMENTO,
    MEDIO_DESCONOCIDO,
    Documento,
    ErrorIntegridad,
    documento_a_transporte,
    leer_documento,
)
from api.permisos import Contexto, ErrorApi, ErrorPermiso, Principal, matriz
from api.proyeccion import CONSTRUCTORES, Vista, proyectar_vista
from api.repositorio import RepositorioMemoria
from api.servicios import Servicios
from engine.ingesta import Documento as DocumentoIngestado
from engine.ingesta import Pagina, doc_id_parte, ingestar, sha256_bytes

RAIZ = Path(__file__).resolve().parents[1]
CASO = RAIZ / "expedientes" / "EXP001-A_completo"
RUTA_YAML = RAIZ / "engine" / "capacidades.yaml"
INSTANTE = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

TENANT_PROPIO = "T-001"
TENANT_AJENO = "T-002"
PDF = b"%PDF-1.7\n1 0 obj\nDOCUMENTO SINTETICO - SOLO PRUEBAS\n%%EOF\n"
FOTO = b"\xff\xd8\xff\xe0 foto sintetica de prueba"


@dataclass
class ActuacionFalsa:
    """Lo unico que `leer_documento` necesita de una actuacion: su lista de documentos ingestados.

    Se usa un doble y no el caso A entero porque estos tests van sobre la puerta, no sobre el motor; el
    caso A real tiene su propio test al final, con sus PDF de verdad.
    """

    documentos: list[object] = field(default_factory=list)


def documento_falso(ruta: Path, contenido: bytes, **extra: object) -> DocumentoIngestado:
    """Un `Documento` de ingesta con el fichero escrito en disco y la huella de sus bytes."""
    ruta.write_bytes(contenido)
    huella = sha256_bytes(contenido)
    campos: dict[str, object] = {
        "doc_id": huella,
        "sha256": huella,
        "ruta": ruta,
        "nombre": ruta.name,
        "bytes": len(contenido),
        "formato": "pdf" if ruta.suffix == ".pdf" else "imagen",
        "paginas": [Pagina(numero=1, texto="pagina", tablas=[], metodo="pdf_nativo")],
    }
    campos.update(extra)
    return DocumentoIngestado(**campos)  # type: ignore[arg-type]


@pytest.fixture
def factura(tmp_path: Path) -> DocumentoIngestado:
    return documento_falso(tmp_path / "factura.pdf", PDF, tipo="factura")


@pytest.fixture
def foto(tmp_path: Path) -> DocumentoIngestado:
    return documento_falso(tmp_path / "placa.jpg", FOTO, tipo="foto_placa")


@pytest.fixture
def repositorio(factura: DocumentoIngestado, foto: DocumentoIngestado) -> RepositorioMemoria:
    repo = RepositorioMemoria()
    repo.anadir("A-PROPIA", TENANT_PROPIO, actuacion=ActuacionFalsa([factura, foto]))
    repo.anadir("A-AJENA", TENANT_AJENO, actuacion=ActuacionFalsa([factura]))
    repo.anadir("A-VECINA", TENANT_PROPIO, actuacion=ActuacionFalsa([]))
    return repo


@pytest.fixture
def servicios(repositorio: RepositorioMemoria) -> Servicios:
    return Servicios(repositorio=repositorio, instante=INSTANTE)


def revisor(tenant: str = TENANT_PROPIO) -> Principal:
    return Principal("u-rev", ("T-REV",), tenant)


def contexto(actuacion: str = "A-PROPIA", tenant: str = TENANT_PROPIO) -> Contexto:
    return Contexto("cola_revision", tenant, actuacion)


def peticion_de(doc_id: str, capacidad: str = "CAP-03", **resto: object) -> Peticion:
    return Peticion(capacidad, revisor(), contexto(), {"doc_id": doc_id, **resto})


# ---------------------------------------------------------------------------
# Lo que tiene que funcionar: el revisor ve el papel, tal cual entro
# ---------------------------------------------------------------------------


def test_el_revisor_recibe_el_documento_tal_cual_entro(
    servicios: Servicios, factura: DocumentoIngestado
) -> None:
    respuesta = leer_documento(peticion_de(factura.doc_id), servicios=servicios)
    documento = respuesta.datos[CLAVE_DOCUMENTO]

    assert respuesta.capacidad == "CAP-03"
    assert respuesta.rol == "T-REV"
    assert respuesta.eventos == (), "una lectura no escribe eventos"
    assert isinstance(documento, Documento)
    assert documento.contenido == PDF, "ni recorte, ni compresion, ni un byte de mas"
    assert sha256_bytes(documento.contenido) == factura.sha256
    assert (documento.doc_id, documento.tipo, documento.medio) == (
        factura.doc_id,
        "factura",
        "application/pdf",
    )
    assert (documento.bytes, documento.paginas) == (len(PDF), 1)
    assert (documento.origen, documento.rango_paginas, documento.es_parte) == (None, None, False)


def test_el_medio_se_declara_segun_lo_que_registro_la_ingesta(
    servicios: Servicios, foto: DocumentoIngestado, tmp_path: Path, repositorio: RepositorioMemoria
) -> None:
    """El medio sale del nombre que guardo la ingesta; lo que no se reconoce no se adivina."""
    raro = documento_falso(tmp_path / "medicion.dat", b"datos", tipo=None)
    repositorio.anadir("A-RARA", TENANT_PROPIO, actuacion=ActuacionFalsa([foto, raro]))

    assert (
        leer_documento(peticion_de(foto.doc_id), servicios=servicios).datos[CLAVE_DOCUMENTO].medio
        == "image/jpeg"
    )
    peticion = Peticion("CAP-03", revisor(), contexto("A-RARA"), {"doc_id": raro.doc_id})
    assert leer_documento(peticion, servicios=servicios).datos[CLAVE_DOCUMENTO].medio == (MEDIO_DESCONOCIDO)


def test_una_parte_de_un_pdf_combinado_se_sirve_entera_y_se_dice(
    servicios: Servicios, repositorio: RepositorioMemoria, tmp_path: Path
) -> None:
    """Recortar el PDF para servir solo la parte seria transformarlo: se sirve el combinado y se explica."""
    combinado = documento_falso(tmp_path / "combinado.pdf", PDF, tipo="combinado")
    parte = documento_falso(
        tmp_path / "combinado.pdf",
        PDF,
        doc_id=doc_id_parte(combinado.sha256, 3, 5),
        tipo="factura",
        origen=combinado.sha256,
        rango_paginas=(3, 5),
    )
    repositorio.anadir("A-COMBI", TENANT_PROPIO, actuacion=ActuacionFalsa([combinado, parte]))

    peticion = Peticion("CAP-03", revisor(), contexto("A-COMBI"), {"doc_id": parte.doc_id})
    documento = leer_documento(peticion, servicios=servicios).datos[CLAVE_DOCUMENTO]
    assert documento.contenido == PDF
    assert (documento.origen, documento.rango_paginas) == (combinado.sha256, (3, 5))
    avisos = leer_documento(peticion, servicios=servicios).avisos
    assert len(avisos) == 1
    assert "paginas 3-5" in avisos[0]


# ---------------------------------------------------------------------------
# 1. Aislamiento por tenant
# ---------------------------------------------------------------------------


def test_un_documento_de_otro_tenant_es_error_de_permiso_y_no_un_vacio(
    servicios: Servicios, factura: DocumentoIngestado
) -> None:
    peticion = Peticion(
        "CAP-03", revisor(), Contexto("cola_revision", TENANT_PROPIO, "A-AJENA"), {"doc_id": factura.doc_id}
    )
    with pytest.raises(ErrorPermiso, match="cruce de tenant"):
        leer_documento(peticion, servicios=servicios)


def test_declarar_el_tenant_ajeno_en_el_contexto_tampoco_abre_la_puerta(
    servicios: Servicios, factura: DocumentoIngestado
) -> None:
    """El tenant lo fija la autenticacion: si el contexto dice otro, se deniega, no se elige."""
    peticion = Peticion(
        "CAP-03", revisor(), Contexto("cola_revision", TENANT_AJENO, "A-AJENA"), {"doc_id": factura.doc_id}
    )
    with pytest.raises(ErrorPermiso, match="cruce de tenant"):
        leer_documento(peticion, servicios=servicios)


# ---------------------------------------------------------------------------
# 2. Por huella, nunca por ruta
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "intento",
    [
        "../../../../etc/passwd",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "expedientes/EXP001-A_completo/01_factura.pdf",
        "factura.pdf",
        "%2e%2e%2fetc%2fpasswd",
        "",
        "   ",
        "A" * 64,  # hexadecimal, pero en mayusculas: tampoco
        "0" * 63,
        "0" * 65,
        "0" * 63 + "g",
    ],
)
def test_lo_que_no_es_una_huella_no_llega_ni_al_repositorio(servicios: Servicios, intento: str) -> None:
    """Ni rutas, ni nombres, ni huellas mal formadas. Se rechaza antes de mirar en ningun sitio."""
    with pytest.raises(ErrorApi) as fallo:
        leer_documento(peticion_de(intento), servicios=servicios)
    assert "huella" in str(fallo.value) or "falta el dato" in str(fallo.value)


def test_una_ruta_en_la_peticion_se_rechaza_aunque_venga_con_una_huella_valida(
    servicios: Servicios, factura: DocumentoIngestado
) -> None:
    """El intento evidente: colar la ruta al lado del `doc_id`, por si alguien la usa."""
    for clave in ("ruta", "nombre"):
        peticion = peticion_de(factura.doc_id, **{clave: "/etc/passwd"})
        with pytest.raises(ErrorApi, match="nunca por ruta"):
            leer_documento(peticion, servicios=servicios)


def test_una_huella_real_de_otra_actuacion_no_se_sirve(
    servicios: Servicios, factura: DocumentoIngestado
) -> None:
    """Acertar la huella no basta: el documento tiene que ser de **esta** actuacion."""
    peticion = Peticion("CAP-03", revisor(), contexto("A-VECINA"), {"doc_id": factura.doc_id})
    with pytest.raises(ErrorApi, match="no tiene ningun documento con la huella"):
        leer_documento(peticion, servicios=servicios)


def test_al_repositorio_solo_le_llega_la_huella_que_registro_la_ingesta(
    servicios: Servicios, factura: DocumentoIngestado, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lo que el repositorio recibe no depende de la peticion: es la huella del registro de la actuacion."""
    visto: list[tuple[str, str]] = []
    original = servicios.repositorio.bytes_de_documento

    def espiado(actuacion_id: str, sha256: str):
        visto.append((actuacion_id, sha256))
        return original(actuacion_id, sha256)

    monkeypatch.setattr(servicios.repositorio, "bytes_de_documento", espiado)
    leer_documento(peticion_de(factura.doc_id), servicios=servicios)
    assert visto == [("A-PROPIA", factura.sha256)]


def test_sin_doc_id_no_se_sirve_nada(servicios: Servicios) -> None:
    with pytest.raises(ErrorApi, match="falta el dato 'doc_id'"):
        leer_documento(Peticion("CAP-03", revisor(), contexto()), servicios=servicios)


# ---------------------------------------------------------------------------
# 3. La huella se comprueba al servir
# ---------------------------------------------------------------------------


def test_si_los_bytes_del_disco_cambiaron_no_se_sirve_y_se_dice_que_fue_alterado(
    servicios: Servicios, factura: DocumentoIngestado
) -> None:
    alterado = PDF.replace(b"SINTETICO", b"RETOCADO!")
    factura.ruta.write_bytes(alterado)

    with pytest.raises(ErrorIntegridad) as fallo:
        leer_documento(peticion_de(factura.doc_id), servicios=servicios)
    mensaje = str(fallo.value)
    assert "fue alterado" in mensaje
    assert factura.sha256 in mensaje and hashlib.sha256(alterado).hexdigest() in mensaje
    assert isinstance(fallo.value, ErrorApi), "quien lo captura como error de API se entera igual"


def test_un_documento_registrado_sin_bytes_no_se_inventa(
    servicios: Servicios, factura: DocumentoIngestado
) -> None:
    factura.ruta.unlink()
    with pytest.raises(ErrorApi, match="no tiene los bytes"):
        leer_documento(peticion_de(factura.doc_id), servicios=servicios)


def test_sin_repositorio_configurado_se_dice_en_vez_de_devolver_vacio(
    factura: DocumentoIngestado,
) -> None:
    with pytest.raises(ErrorApi, match="no hay repositorio configurado"):
        leer_documento(peticion_de(factura.doc_id))


# ---------------------------------------------------------------------------
# 4. R-UI-12: sin ambito de contenido, no hay bytes
# ---------------------------------------------------------------------------


def test_una_capacidad_que_no_proyecta_documentos_no_da_los_bytes(
    servicios: Servicios, factura: DocumentoIngestado
) -> None:
    """CAP-04 es una lectura concedida al mismo revisor, pero no proyecta el contenido documental."""
    peticion = peticion_de(factura.doc_id, capacidad="CAP-04")
    with pytest.raises(ErrorPermiso, match=f"no proyecta el bloque '{BLOQUE_CONTENIDO}'"):
        leer_documento(peticion, servicios=servicios)


@pytest.fixture
def matriz_con_un_externo_que_ve_cap_03(tmp_path: Path):
    """La matriz con A1 y A2 decididas y CAP-03 concedida a un externo: el escenario que `R-UI-12` salva.

    Es deliberadamente exagerado, como en `test_api_aislamiento`: hoy el portal externo esta denegado
    entero, y lo que se comprueba es que el dia que Billy decida A1 y A2 los bytes sigan sin salir.
    """
    texto = RUTA_YAML.read_text(encoding="utf-8")
    texto = texto.replace(
        """    concede: [T-RES, T-OPE, T-REV]
    condicionada:""",
        """    concede: [T-RES, T-OPE, T-REV, EXT-INS]
    condicionada:""",
    )
    destino = tmp_path / "capacidades.yaml"
    destino.write_text(texto, encoding="utf-8")
    return matriz(destino)


def test_un_perfil_sin_ambito_de_contenido_no_recibe_los_bytes(
    servicios: Servicios, factura: DocumentoIngestado, matriz_con_un_externo_que_ve_cap_03
) -> None:
    servicios.repositorio.anadir(
        "A-EXTERNA",
        TENANT_PROPIO,
        actuacion=ActuacionFalsa([factura]),
        partes=("inst-1",),
    )
    instalador = Principal("inst-1", ("EXT-INS",), TENANT_PROPIO)
    peticion = Peticion(
        "CAP-03",
        instalador,
        Contexto("mis_actuaciones", TENANT_PROPIO, "A-EXTERNA"),
        {"doc_id": factura.doc_id},
    )
    with pytest.raises(ErrorPermiso, match="no admite el bloque"):
        leer_documento(peticion, servicios=servicios, matriz_actual=matriz_con_un_externo_que_ve_cap_03)


def test_el_ambito_de_contenido_no_es_un_invento_de_este_modulo() -> None:
    """`documentos` es un bloque de la matriz y tiene constructor: no es una etiqueta escrita aqui."""
    assert BLOQUE_CONTENIDO in CONSTRUCTORES
    ambitos_que_lo_admiten = [
        ambito.id for ambito in matriz().ambitos.values() if BLOQUE_CONTENIDO in ambito.bloques
    ]
    assert ambitos_que_lo_admiten, "si ningun ambito lo admite, nadie podria ver un documento"
    capacidades = [c.id for c in matriz().capacidades.values() if BLOQUE_CONTENIDO in c.bloques]
    assert capacidades == ["CAP-03"], "hoy solo CAP-03 da acceso al contenido documental"


# ---------------------------------------------------------------------------
# La puerta es la misma que la del resto del contrato
# ---------------------------------------------------------------------------


def test_un_comando_no_se_sirve_como_documento(servicios: Servicios, factura: DocumentoIngestado) -> None:
    with pytest.raises(ErrorApi, match="se esta invocando como"):
        leer_documento(peticion_de(factura.doc_id, capacidad="CAP-05"), servicios=servicios)


def test_una_capacidad_pendiente_de_decision_se_deniega_diciendolo(
    servicios: Servicios, factura: DocumentoIngestado
) -> None:
    externo = Principal("inst-1", ("EXT-INS",), TENANT_PROPIO)
    peticion = Peticion(
        "CAP-04", externo, Contexto("mis_actuaciones", TENANT_PROPIO, "A-PROPIA"), {"doc_id": factura.doc_id}
    )
    with pytest.raises(ErrorPermiso, match="pendiente de decision"):
        leer_documento(peticion, servicios=servicios)


def test_servir_el_documento_no_anade_ningun_manejador_a_la_matriz() -> None:
    """La matriz vive en `engine/` y no se toca: `leer_documento` no es un manejador ni un bloque."""
    from api.lecturas import MANEJADORES

    assert "leer_documento" not in MANEJADORES
    assert CLAVE_DOCUMENTO not in CONSTRUCTORES


def test_la_lectura_normal_sigue_dando_la_ficha_del_documento_sin_los_bytes(
    factura: DocumentoIngestado, foto: DocumentoIngestado
) -> None:
    """El bloque `documentos` de `CAP-03` son metadatos; los bytes solo salen por la entrada del documento."""
    datos = proyectar_vista(
        (BLOQUE_CONTENIDO,),
        frozenset({BLOQUE_CONTENIDO}),
        Vista(actuacion=ActuacionFalsa([factura, foto])),
    )
    fichas = datos[BLOQUE_CONTENIDO]
    assert [ficha["doc_id"] for ficha in fichas] == [factura.doc_id, foto.doc_id]
    assert all("contenido" not in ficha and "ruta" not in ficha for ficha in fichas)


# ---------------------------------------------------------------------------
# El transporte al front: base64 y vuelta, sin tocar un byte
# ---------------------------------------------------------------------------


def test_el_sobre_de_transporte_devuelve_exactamente_los_mismos_bytes(
    servicios: Servicios, factura: DocumentoIngestado
) -> None:
    import base64

    documento = leer_documento(peticion_de(factura.doc_id), servicios=servicios).datos[CLAVE_DOCUMENTO]
    sobre = documento_a_transporte(documento)
    devueltos = base64.b64decode(str(sobre["contenido_base64"]))

    assert devueltos == PDF
    assert sha256_bytes(devueltos) == factura.sha256
    assert sobre["medio"] == "application/pdf"
    assert sobre["bytes"] == len(PDF)
    assert sobre["rango_paginas"] is None


# ---------------------------------------------------------------------------
# Con documentos de verdad: el caso A
# ---------------------------------------------------------------------------


@cache
def _documentos_del_caso_a() -> tuple[object, ...]:
    """La ingesta del caso A sin OCR: documentos reales, con sus huellas reales."""
    return tuple(ingestar(CASO, ocr=False))


@pytest.mark.skipif(not CASO.is_dir(), reason="el banco de casos no esta generado")
def test_el_caso_a_sirve_sus_pdf_reales_byte_a_byte() -> None:
    documentos = _documentos_del_caso_a()
    repositorio = RepositorioMemoria()
    repositorio.anadir("A-CASO", TENANT_PROPIO, actuacion=ActuacionFalsa(list(documentos)))
    servicios = Servicios(repositorio=repositorio, instante=INSTANTE)

    servidos = 0
    for documento in documentos:
        if documento.origen is not None:  # las partes se sirven con su combinado; ya hay test
            continue
        peticion = Peticion("CAP-03", revisor(), contexto("A-CASO"), {"doc_id": documento.doc_id})
        contenido = leer_documento(peticion, servicios=servicios).datos[CLAVE_DOCUMENTO].contenido
        assert contenido == documento.ruta.read_bytes()
        assert sha256_bytes(contenido) == documento.sha256
        servidos += 1
    assert servidos >= 5, "el caso A tiene varios documentos; si no, este test no prueba nada"
