"""Ingesta (S1): de una carpeta de ficheros a `Documento`s con su huella, sus paginas y sus avisos.

Contrato de ADR-002 §2.2 (`Pagina`, `Documento`, `ingestar`). Lo que este modulo garantiza (docs/03 §9,
`CLAUDE.md` §2):

1. **SHA-256 de los bytes tal y como entraron, antes de cualquier transformacion.** Se calcula al leer el
   fichero y no se vuelve a tocar: abrir el PDF, rotar un escaneo o pasar OCR no cambia `Documento.sha256`.
2. **Vinculacion por hash y por numero de serie, nunca por nombre de fichero.** Este modulo no interpreta
   nombres: `datos.xlsx` y `06_registro_funcionamiento_MTR-SYN-0001.xlsx` se leen igual. El nombre solo
   aparece en avisos informativos.
3. **Separacion de PDF combinados** conservando el hash del original y el de cada parte:
   `doc_id` de una parte = `sha256(sha256_original + ":" + "p{ini}-{fin}")`, con `origen` = hash del original
   y `rango_paginas` en **numeracion absoluta del original** (una cita sigue apuntando a la pagina real).
4. **Ningun fichero rompe la ingesta**: lo que no se puede leer deja aviso y un documento sin paginas.

Formatos soportados:

| Formato | Como se lee | `Pagina.metodo` |
|---|---|---|
| `pdf` nativo | `pdfplumber`: texto y **tablas** (`extract_tables`) por pagina | `pdf_nativo` |
| `pdf` sin capa de texto | render (`page.to_image(resolution=200)`) + `tesseract -l spa` | `ocr` |
| `pdf` nativo con fotos | texto nativo **y** OCR en `Pagina.texto_ocr` (placa del informe) | `pdf_nativo` |
| `imagen` (jpg/png/tif) | EXIF (`ImageDescription`) a `exif`; OCR del contenido a su pagina | `ocr` |
| `xlsx` | sin paginas; hojas, cabecera y hoja `metadatos` a `exif` (lo lee `registro_xlsx`) | — |

Decisiones de lectura (heuristicas; van a `docs/03` §8):

- **Avisos**: `ingestar` devuelve `list[Documento]` (la firma del contrato) y cada aviso vive en
  `Documento.avisos`; `avisos_de(documentos)` los concatena en orden para `motor.py`. No se devuelve una
  tupla para no romper el contrato §2.2.
- **Titulo de pagina**: la linea compuesta por los caracteres verticales (`upright`) de mayor cuerpo de la
  pagina, si ese cuerpo es >= `FACTOR_TITULO` veces la mediana de la pagina y >= `CUERPO_TITULO_MINIMO`. Es
  la senal que usa la separacion de combinados; si el PDF no trae cuerpos (escaneo), se usan las primeras
  lineas del texto.
- **Corte de un PDF combinado**: una pagina empieza documento nuevo si su titulo se clasifica
  (`clasificacion.tipo_por_titulo`) con confianza >= `CONFIANZA_CORTE`. Solo se separa si hay **dos o mas**
  cortes (un PDF normal tiene titulo en la primera pagina y no debe partirse). El original se conserva en la
  lista con `tipo = "combinado"`, `partes` = `doc_id` de cada parte y aviso `pdf_separado`; las partes se
  anaden detras. Asi el motor puede citar el fichero original y, a la vez, clasificar y extraer por parte.
- **Escaneo girado**: se prueban las cuatro rotaciones y gana la que mas palabras reconocibles da
  (`palabras con confianza tesseract >= CONFIANZA_PALABRA_OCR`). Para no pagar cuatro pasadas en cada
  pagina, solo se buscan rotaciones si la pasada a 0 grados no llega a `PALABRAS_OCR_SUFICIENTES`.
  Empate → menor giro.
- **Sin `tesseract`** (Windows sin OCR): `ocr` se desactiva solo, la pagina queda vacia con aviso
  `ocr_no_disponible` y **nunca** se lanza una excepcion. Ningun caso obligatorio depende del OCR
  (ADR-002 §3, caso G).
- **Paginas**: los PDF numeran 1..n (numeracion absoluta, tambien en las partes). Una imagen suelta y un
  xlsx no estan paginados: su pagina es `0` ("no aplica"), igual que en el ground truth.

Dependencias hacia dentro: `ingesta` → `clasificacion` (lexico de titulos). No importa `agentes`, `salida`,
`generator` ni `tests`.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from statistics import median

FORMATO_PDF = "pdf"
FORMATO_XLSX = "xlsx"
FORMATO_IMAGEN = "imagen"
FORMATO_OTRO = "otro"
METODO_NATIVO = "pdf_nativo"
METODO_OCR = "ocr"
TIPO_COMBINADO = "combinado"
PAGINA_NO_APLICA = 0

EXTENSIONES: dict[str, str] = {
    ".pdf": FORMATO_PDF,
    ".xlsx": FORMATO_XLSX,
    ".xlsm": FORMATO_XLSX,
    ".jpg": FORMATO_IMAGEN,
    ".jpeg": FORMATO_IMAGEN,
    ".png": FORMATO_IMAGEN,
    ".tif": FORMATO_IMAGEN,
    ".tiff": FORMATO_IMAGEN,
    ".bmp": FORMATO_IMAGEN,
}

IDIOMA_OCR = "spa"
RESOLUCION_OCR = 200
CONFIANZA_PALABRA_OCR = Decimal(60)
LONGITUD_PALABRA_OCR = 3
PALABRAS_OCR_SUFICIENTES = 12  # por debajo de esto se buscan rotaciones
ROTACIONES = (0, 90, 180, 270)
TEXTO_NATIVO_MINIMO = 20  # caracteres; por debajo, la pagina se considera sin capa de texto
AREA_IMAGEN_MINIMA = Decimal("0.08")  # fraccion de la pagina para disparar OCR de una pagina con fotos
FACTOR_TITULO = Decimal("1.25")
CUERPO_TITULO_MINIMO = Decimal("11")
CONFIANZA_CORTE = Decimal("0.6")
LINEAS_TITULO_TEXTO = 4  # lineas de cabecera que se miran cuando no hay cuerpos de letra

EXIF_IMAGE_DESCRIPTION = 0x010E
EXIF_SOFTWARE = 0x0131
EXIF_DATETIME = 0x0132
EXIF_ARTIST = 0x013B
CLAVES_EXIF = {
    EXIF_IMAGE_DESCRIPTION: "descripcion",
    EXIF_SOFTWARE: "software",
    EXIF_DATETIME: "fecha",
    EXIF_ARTIST: "autor",
}

HOJA_METADATOS = "metadatos"


class ErrorIngesta(Exception):
    """Carpeta inexistente o ilegible. Un fichero ilegible **no** lanza: deja aviso."""


@dataclass
class Pagina:
    """Una pagina leida. `tablas` es lo que se lee **antes** que `texto` (docs/05 §4.4.1)."""

    numero: int  # 1-based en PDF; 0 si el documento no esta paginado (imagen suelta, xlsx)
    texto: str
    tablas: list[list[list[str]]]
    metodo: str  # "pdf_nativo" | "ocr"
    texto_ocr: str = ""  # OCR de las imagenes de una pagina que ademas tiene texto nativo (placa)

    @property
    def texto_reconocido(self) -> str:
        """Texto que procede de OCR (pagina escaneada o fotos dentro de una pagina nativa)."""
        if self.metodo == METODO_OCR:
            return self.texto
        return self.texto_ocr


@dataclass
class Documento:
    """Un fichero (o una parte de un PDF combinado) con su huella intacta."""

    doc_id: str  # sha256 del fichero, o sha256(sha256_original + ":p{ini}-{fin}") si es una parte
    sha256: str  # huella del contenido tal cual entro; nunca cambia
    ruta: Path
    nombre: str
    bytes: int
    formato: str  # "pdf" | "xlsx" | "imagen" | "otro"
    paginas: list[Pagina] = field(default_factory=list)
    exif: dict[str, str] = field(default_factory=dict)
    origen: str | None = None  # sha256 del PDF combinado del que se separo
    rango_paginas: tuple[int, int] | None = None  # absoluto sobre el original
    tipo: str | None = None  # lo rellena clasificacion
    confianza_tipo: Decimal | None = None
    subtipo: str | None = None  # "foto_antes" | "foto_despues" | "placa" | "escaneo_girado" | ...
    avisos: list[str] = field(default_factory=list)
    partes: tuple[str, ...] = ()  # doc_id de las partes, si este documento es un combinado

    @property
    def es_parte(self) -> bool:
        return self.origen is not None

    @property
    def es_combinado(self) -> bool:
        return bool(self.partes)

    def texto(self) -> str:
        return "\n".join(p.texto for p in self.paginas if p.texto)

    def avisar(self, aviso: str) -> None:
        if aviso not in self.avisos:
            self.avisos.append(aviso)

    def a_dict(self) -> dict[str, object]:
        return {
            "doc_id": self.doc_id,
            "sha256": self.sha256,
            "nombre": self.nombre,
            "bytes": self.bytes,
            "formato": self.formato,
            "paginas": len(self.paginas),
            "tipo": self.tipo,
            "confianza_tipo": str(self.confianza_tipo) if self.confianza_tipo is not None else None,
            "subtipo": self.subtipo,
            "origen": self.origen,
            "rango_paginas": list(self.rango_paginas) if self.rango_paginas else None,
            "partes": list(self.partes),
            "avisos": list(self.avisos),
        }


# ---------------------------------------------------------------------------
# Huellas
# ---------------------------------------------------------------------------


def sha256_bytes(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def doc_id_parte(sha256_original: str, pagina_inicio: int, pagina_fin: int) -> str:
    """`doc_id` de una parte de un PDF combinado (ADR-002 §2.2)."""
    return sha256_texto(f"{sha256_original}:p{pagina_inicio}-{pagina_fin}")


# ---------------------------------------------------------------------------
# OCR (tesseract por linea de ordenes; sin dependencia de pytesseract)
# ---------------------------------------------------------------------------


def hay_tesseract() -> bool:
    """`True` si `tesseract` esta en el PATH. En Windows sin OCR devuelve `False` y todo sigue."""
    return shutil.which("tesseract") is not None


def _tesseract(ruta_png: Path) -> tuple[str, int]:
    """Texto reconstruido desde el TSV de tesseract y numero de palabras reconocibles."""
    try:
        salida = subprocess.run(  # noqa: S603 - binario fijo, sin shell, entrada controlada
            ["tesseract", str(ruta_png), "stdout", "-l", IDIOMA_OCR, "tsv"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "", 0
    if salida.returncode != 0:
        return "", 0
    lineas: dict[tuple[str, str, str], list[str]] = {}
    reconocibles = 0
    for fila in salida.stdout.splitlines()[1:]:
        campos = fila.split("\t")
        if len(campos) < 12:
            continue
        try:
            confianza = Decimal(campos[10])
        except InvalidOperation:
            continue
        palabra = campos[11].strip()
        if not palabra:
            continue
        clave = (campos[2], campos[3], campos[4])  # bloque, parrafo, linea
        lineas.setdefault(clave, []).append(palabra)
        if confianza >= CONFIANZA_PALABRA_OCR and len(palabra) >= LONGITUD_PALABRA_OCR:
            reconocibles += 1
    texto = "\n".join(" ".join(palabras) for palabras in lineas.values())
    return texto, reconocibles


def reconocer(imagen, *, buscar_giro: bool = True) -> tuple[str, int, int]:
    """OCR de una imagen PIL. Devuelve (texto, palabras reconocibles, giro aplicado en grados).

    Criterio del giro: se prueba 0 grados y, si no llega a `PALABRAS_OCR_SUFICIENTES`, las otras tres
    rotaciones; gana la que **mas palabras reconocibles** da (confianza de tesseract >= 60 y >= 3 letras).
    En empate gana el giro menor. Es el escaneo girado 90 grados del caso G.
    """
    if not hay_tesseract():
        return "", 0, 0
    with tempfile.TemporaryDirectory(prefix="cae-ocr-") as tmp:
        carpeta = Path(tmp)
        mejor_texto, mejor_n, mejor_giro = "", -1, 0
        for giro in ROTACIONES:
            girada = imagen if giro == 0 else imagen.rotate(giro, expand=True)
            ruta = carpeta / f"p{giro}.png"
            try:
                girada.save(ruta)
            except OSError:
                continue
            texto, n = _tesseract(ruta)
            if n > mejor_n:
                mejor_texto, mejor_n, mejor_giro = texto, n, giro
            if giro == 0 and (not buscar_giro or n >= PALABRAS_OCR_SUFICIENTES):
                break
        return mejor_texto, max(mejor_n, 0), mejor_giro


# ---------------------------------------------------------------------------
# Lectura por formato
# ---------------------------------------------------------------------------


def _limpiar_tabla(tabla: Sequence[Sequence[object]]) -> list[list[str]]:
    return [[("" if celda is None else str(celda)) for celda in fila] for fila in tabla]


def _area_imagenes(pagina) -> Decimal:
    """Fraccion de la pagina cubierta por imagenes incrustadas (para decidir si se pasa OCR)."""
    try:
        ancho = Decimal(str(pagina.width))
        alto = Decimal(str(pagina.height))
        if ancho <= 0 or alto <= 0:
            return Decimal(0)
        total = Decimal(0)
        for imagen in pagina.images:
            total += Decimal(str(abs(imagen["x1"] - imagen["x0"]))) * Decimal(
                str(abs(imagen["bottom"] - imagen["top"]))
            )
        return total / (ancho * alto)
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return Decimal(0)


def _render(pagina):
    """Pagina de PDF a imagen PIL. `None` si el render no esta disponible."""
    try:
        return pagina.to_image(resolution=RESOLUCION_OCR).original
    except Exception:  # noqa: BLE001 - cualquier fallo de render degrada a "sin OCR", nunca rompe
        return None


def _cuerpo(valor: object) -> Decimal:
    """Medida de maquetacion (cuerpo de letra, coordenada) como `Decimal`: en `engine/` no entra `float`."""
    try:
        return Decimal(str(valor)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def titulo_de_pagina(pagina) -> str:
    """Linea de mayor cuerpo de la pagina (caracteres verticales), o "" si no destaca ninguna.

    Heuristica declarada: el titulo de un documento se compone en un cuerpo mayor que el texto corrido. Se
    exige `FACTOR_TITULO` veces la mediana de la pagina y `CUERPO_TITULO_MINIMO` puntos para no confundir un
    subtitulo con un titulo. La marca de agua girada queda fuera por `upright`.
    """
    try:
        caracteres = [c for c in pagina.chars if c.get("upright", True)]
    except (AttributeError, TypeError):
        return ""
    if not caracteres:
        return ""
    cuerpos = [_cuerpo(c.get("size", 0)) for c in caracteres]
    mayor = max(cuerpos)
    if mayor < CUERPO_TITULO_MINIMO or mayor < FACTOR_TITULO * Decimal(str(median(cuerpos))):
        return ""
    elegidos = [c for c, cuerpo in zip(caracteres, cuerpos, strict=True) if cuerpo >= mayor - Decimal("0.3")]
    elegidos.sort(key=lambda c: (_cuerpo(c.get("top", 0)), _cuerpo(c.get("x0", 0))))
    return "".join(str(c.get("text", "")) for c in elegidos).strip()


def cabecera_de_texto(texto: str) -> str:
    """Primeras lineas utiles del texto de una pagina (respaldo del titulo en paginas OCR)."""
    lineas = [linea.strip() for linea in texto.splitlines() if linea.strip()]
    return "\n".join(lineas[:LINEAS_TITULO_TEXTO])


def _leer_pdf(doc: Documento, datos: bytes, ocr: bool) -> None:
    import pdfplumber

    try:
        pdf = pdfplumber.open(BytesIO(datos))
    except Exception as exc:  # noqa: BLE001 - un PDF roto deja aviso, no rompe la ingesta
        doc.avisar(f"documento_ilegible: '{doc.nombre}' no se pudo abrir como PDF ({exc.__class__.__name__})")
        return
    con_ocr = ocr and hay_tesseract()
    aviso_ocr = False
    with pdf:
        doc.exif.update(_metadatos_pdf(pdf))
        for numero, pagina in enumerate(pdf.pages, 1):
            try:
                texto = pagina.extract_text() or ""
                tablas = [_limpiar_tabla(t) for t in pagina.extract_tables()]
            except Exception:  # noqa: BLE001
                texto, tablas = "", []
            titulo = titulo_de_pagina(pagina)
            nativa = len(texto.strip()) >= TEXTO_NATIVO_MINIMO
            metodo = METODO_NATIVO if nativa else METODO_OCR
            texto_ocr = ""
            if not nativa:
                if con_ocr:
                    imagen = _render(pagina)
                    if imagen is None:
                        doc.avisar(
                            f"ocr_sin_texto: '{doc.nombre}' pagina {numero} no se pudo convertir a imagen"
                        )
                    else:
                        texto_ocr, _, giro = reconocer(imagen)
                        texto = texto_ocr
                        texto_ocr = ""
                        if not texto.strip():
                            doc.avisar(
                                f"ocr_sin_texto: '{doc.nombre}' pagina {numero} no dio texto reconocible"
                            )
                        if giro:
                            doc.subtipo = doc.subtipo or "escaneo_girado"
                            doc.avisar(
                                f"escaneo_ocr: '{doc.nombre}' pagina {numero} leida por OCR "
                                f"con giro de {giro} grados (confianza 0,75)"
                            )
                        else:
                            doc.subtipo = doc.subtipo or "escaneo"
                            doc.avisar(
                                f"escaneo_ocr: '{doc.nombre}' pagina {numero} leida por OCR (confianza 0,75)"
                            )
                elif not aviso_ocr:
                    aviso_ocr = True
                    doc.avisar(
                        f"ocr_no_disponible: '{doc.nombre}' no tiene capa de texto y no hay tesseract; "
                        "la pagina queda vacia"
                    )
            elif con_ocr and _area_imagenes(pagina) >= AREA_IMAGEN_MINIMA:
                imagen = _render(pagina)
                if imagen is not None:
                    texto_ocr, _, _ = reconocer(imagen, buscar_giro=False)
            doc.paginas.append(
                Pagina(numero=numero, texto=texto, tablas=tablas, metodo=metodo, texto_ocr=texto_ocr)
            )
            if titulo:
                doc.exif.setdefault(f"titulo_pagina_{numero}", titulo)
            elif metodo == METODO_OCR and texto:
                doc.exif.setdefault(f"titulo_pagina_{numero}", cabecera_de_texto(texto))


def _metadatos_pdf(pdf) -> dict[str, str]:
    """`/Info` del PDF. Se guarda como trazabilidad; **no** se usa para clasificar (seria hacer trampa)."""
    metadatos: dict[str, str] = {}
    try:
        for clave, valor in (pdf.metadata or {}).items():
            if isinstance(valor, str) and valor.strip():
                metadatos[f"pdf_{str(clave).lower()}"] = valor.strip()
    except (AttributeError, TypeError):
        pass
    return metadatos


def _leer_imagen(doc: Documento, datos: bytes, ocr: bool) -> None:
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - pillow es dependencia declarada
        doc.avisar(f"documento_ilegible: '{doc.nombre}' necesita pillow")
        return
    try:
        imagen = Image.open(BytesIO(datos))
        imagen.load()
    except Exception as exc:  # noqa: BLE001
        doc.avisar(
            f"documento_ilegible: '{doc.nombre}' no se pudo abrir como imagen ({exc.__class__.__name__})"
        )
        return
    doc.exif.update(_leer_exif(imagen))
    texto = ""
    if ocr and hay_tesseract():
        texto, _, giro = reconocer(imagen, buscar_giro=False)
        if giro:
            doc.avisar(f"escaneo_ocr: '{doc.nombre}' leida por OCR con giro de {giro} grados")
    elif ocr:
        doc.avisar(f"ocr_no_disponible: '{doc.nombre}' es una imagen y no hay tesseract; sin texto")
    doc.paginas.append(
        Pagina(numero=PAGINA_NO_APLICA, texto=texto, tablas=[], metodo=METODO_OCR, texto_ocr="")
    )


def _decodificar_exif(valor: object) -> str:
    """`ImageDescription` se escribe en UTF-8; Pillow lo devuelve decodificado como latin-1."""
    if isinstance(valor, bytes):
        return valor.rstrip(b"\0").decode("utf-8", "replace")
    if not isinstance(valor, str):
        return str(valor)
    try:
        return valor.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return valor


def _leer_exif(imagen) -> dict[str, str]:
    datos: dict[str, str] = {}
    try:
        exif = imagen.getexif()
    except Exception:  # noqa: BLE001
        return datos
    for etiqueta, nombre in CLAVES_EXIF.items():
        valor = exif.get(etiqueta)
        if valor is None:
            continue
        texto = _decodificar_exif(valor).strip()
        if texto:
            datos[nombre] = texto
    return datos


def _leer_xlsx(doc: Documento, datos: bytes) -> None:
    """Un xlsx no tiene paginas: se guarda su estructura en `exif` para que la clasificacion decida.

    `registro_xlsx.leer_registro` es quien lee las filas; aqui solo se mira la superficie (hojas, cabecera
    de la primera hoja y pares clave/valor de la hoja `metadatos`).
    """
    try:
        from openpyxl import load_workbook
    except ImportError:  # pragma: no cover - openpyxl es dependencia declarada
        doc.avisar(f"documento_ilegible: '{doc.nombre}' necesita openpyxl")
        return
    try:
        libro = load_workbook(BytesIO(datos), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        doc.avisar(
            f"documento_ilegible: '{doc.nombre}' no se pudo abrir como xlsx ({exc.__class__.__name__})"
        )
        return
    try:
        doc.exif["hojas"] = ", ".join(libro.sheetnames)
        hoja = libro[libro.sheetnames[0]]
        cabecera = next(hoja.iter_rows(min_row=1, max_row=1, values_only=True), ())
        doc.exif["columnas"] = ", ".join(str(c).strip() for c in cabecera if c is not None)
        if HOJA_METADATOS in libro.sheetnames:
            for fila in libro[HOJA_METADATOS].iter_rows(values_only=True):
                if not fila or fila[0] is None:
                    continue
                clave = str(fila[0]).strip()
                valor = "" if len(fila) < 2 or fila[1] is None else str(fila[1]).strip()
                if clave:
                    doc.exif[clave] = valor
    except Exception as exc:  # noqa: BLE001
        doc.avisar(f"documento_ilegible: '{doc.nombre}' xlsx incompleto ({exc.__class__.__name__})")
    finally:
        libro.close()


# ---------------------------------------------------------------------------
# Separacion de PDF combinados
# ---------------------------------------------------------------------------


def _cortes(doc: Documento) -> list[tuple[int, str, Decimal]]:
    """Paginas que empiezan un documento nuevo: (numero, tipo, confianza)."""
    from engine.clasificacion import tipo_por_titulo

    cortes: list[tuple[int, str, Decimal]] = []
    for pagina in doc.paginas:
        titulo = doc.exif.get(f"titulo_pagina_{pagina.numero}", "")
        if not titulo:
            continue
        tipo, confianza = tipo_por_titulo(titulo)
        if tipo is not None and confianza >= CONFIANZA_CORTE:
            cortes.append((pagina.numero, tipo, confianza))
    return cortes


def separar(doc: Documento) -> list[Documento]:
    """Separa un PDF combinado en una parte por documento. Devuelve [] si no hay nada que separar.

    El original conserva su `sha256` y se marca `tipo = "combinado"` con `partes`; cada parte lleva su
    `doc_id` derivado, `origen` = hash del original y `rango_paginas` **absoluto**.
    """
    if doc.formato != FORMATO_PDF or len(doc.paginas) < 2:
        return []
    cortes = _cortes(doc)
    if len(cortes) < 2:
        return []
    partes: list[Documento] = []
    for indice, (inicio, tipo, confianza) in enumerate(cortes):
        fin = cortes[indice + 1][0] - 1 if indice + 1 < len(cortes) else len(doc.paginas)
        paginas = [p for p in doc.paginas if inicio <= p.numero <= fin]
        partes.append(
            Documento(
                doc_id=doc_id_parte(doc.sha256, inicio, fin),
                sha256=doc.sha256,
                ruta=doc.ruta,
                nombre=doc.nombre,
                bytes=doc.bytes,
                formato=FORMATO_PDF,
                paginas=paginas,
                exif=dict(doc.exif),
                origen=doc.sha256,
                rango_paginas=(inicio, fin),
                tipo=tipo,
                confianza_tipo=confianza,
            )
        )
    doc.tipo = TIPO_COMBINADO
    doc.confianza_tipo = min(c for _, _, c in cortes)
    doc.partes = tuple(p.doc_id for p in partes)
    doc.avisar(
        f"pdf_separado: '{doc.nombre}' contiene {len(partes)} documentos "
        f"({', '.join(p.tipo or 'sin tipo' for p in partes)})"
    )
    return partes


# ---------------------------------------------------------------------------
# Entrada publica
# ---------------------------------------------------------------------------


def ficheros_de(carpeta: Path) -> list[Path]:
    """Ficheros de la carpeta en orden estable (recursivo, sin ocultos ni auxiliares)."""
    if not carpeta.is_dir():
        raise ErrorIngesta(f"no es una carpeta: {carpeta}")
    ficheros = [
        ruta
        for ruta in sorted(carpeta.rglob("*"))
        if ruta.is_file() and not ruta.name.startswith(".") and not ruta.name.startswith("~$")
    ]
    return ficheros


def ingestar(carpeta: Path, ocr: bool = True) -> list[Documento]:
    """Lee la carpeta de una actuacion. Orden: huella → lectura → separacion de combinados.

    No clasifica (eso es `clasificacion.clasificar`), salvo el tipo que la separacion deduce del titulo de
    cada parte, que `clasificar` vuelve a comprobar contra la spec.
    """
    carpeta = Path(carpeta)
    documentos: list[Documento] = []
    for ruta in ficheros_de(carpeta):
        documentos.extend(ingestar_fichero(ruta, ocr=ocr))
    return documentos


def ingestar_fichero(ruta: Path, ocr: bool = True) -> list[Documento]:
    """Un fichero → su documento (y sus partes si es un PDF combinado). El hash va primero."""
    ruta = Path(ruta)
    try:
        datos = ruta.read_bytes()
    except OSError as exc:
        raise ErrorIngesta(f"no se pudo leer {ruta}: {exc}") from exc
    huella = sha256_bytes(datos)  # antes de cualquier transformacion
    formato = EXTENSIONES.get(ruta.suffix.lower(), FORMATO_OTRO)
    doc = Documento(
        doc_id=huella,
        sha256=huella,
        ruta=ruta,
        nombre=ruta.name,
        bytes=len(datos),
        formato=formato,
    )
    if formato == FORMATO_PDF:
        _leer_pdf(doc, datos, ocr)
    elif formato == FORMATO_IMAGEN:
        _leer_imagen(doc, datos, ocr)
    elif formato == FORMATO_XLSX:
        _leer_xlsx(doc, datos)
    else:
        doc.avisar(f"formato_no_soportado: '{doc.nombre}' ({ruta.suffix or 'sin extension'}) no se lee")
    partes = separar(doc)
    return [doc, *partes]


def avisos_de(documentos: Iterable[Documento]) -> list[str]:
    """Avisos de ingesta y clasificacion en orden de documento (los concatena `motor.py`)."""
    avisos: list[str] = []
    for doc in documentos:
        for aviso in doc.avisos:
            if aviso not in avisos:
                avisos.append(aviso)
    return avisos


def documentos_legibles(documentos: Iterable[Documento]) -> list[Documento]:
    """Documentos que la extraccion debe recorrer: las partes en lugar del combinado que las contiene."""
    return [doc for doc in documentos if not doc.es_combinado]
