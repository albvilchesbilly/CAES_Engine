import type { Cliente, Contexto, DocumentoServido } from "@cae/compartido/api";
import { useEffect, useState, type ReactElement } from "react";

import { AvisoServidor } from "../AvisoServidor";
import {
  CARGANDO_DOCUMENTO,
  COLUMNA_TEXTO_LITERAL,
  DOCUMENTO_ES_PARTE,
  DOCUMENTO_INTACTO,
  ETIQUETA_BYTES,
  ETIQUETA_PAGINA,
  ETIQUETA_PAGINA_DE,
  ETIQUETA_RANGO_PAGINAS,
  SIN_DOCUMENTO_ELEGIDO,
  SIN_VISOR,
  TITULO_DOCUMENTO,
} from "../textos";
import { useLectura } from "../useLectura";
import { CAPACIDAD_ACTUACION, type Documento } from "./datos";

/**
 * El panel izquierdo: **el papel original**, servido por su huella y sin tocar (contrato C17).
 *
 * Existe por lo que dice `ADR-012` §1: una pantalla de revision que solo ensena el texto extraido le
 * pide al revisor que se fie de nuestra extraccion, que es justo lo que la revision existe para
 * comprobar. Por eso el documento se sirve entero y sin transformar —ni recorte, ni rotacion, ni
 * resaltado— y el servidor recalcula su sha256 antes de servirlo. Si no casa, no se sirve: entonces sale
 * el aviso del servidor y **no se ensena nada en su lugar** (`CA-REV-16`).
 *
 * El resaltado de la cita es del navegador. Aqui se ensena el texto literal al lado del documento, que
 * es lo que se puede hacer sin retocar los bytes.
 *
 * **Lo que este panel no bloquea**: el panel derecho. Revisar el veredicto no espera a un PDF
 * (`T-REV-revision` §9), y por eso el documento tiene su propia lectura y su propio estado.
 */

export interface PropsPanelDocumento {
  readonly cliente: Cliente;
  readonly contexto: Contexto;
  /** El documento elegido, con el `doc_id` que dio la lectura. La pantalla no compone ninguno. */
  readonly documento: Documento | null;
  /** La pagina de la cita que se esta comprobando, para decir en cual hay que mirar. */
  readonly pagina: number | null;
  /** El texto literal de esa cita, tal cual lo leyo el extractor. */
  readonly textoLiteral: string | null;
}

/**
 * El documento incrustado, cuando el navegador puede.
 *
 * Los bytes que llegaron se le dan al navegador **tal cual**, sin convertir nada. Donde no hay
 * `createObjectURL` —un entorno de pruebas, por ejemplo— no se finge un visor: se dice que no se puede
 * ensenar y se deja constancia de que los bytes llegaron igualmente.
 */
function Visor({ servido }: { readonly servido: DocumentoServido }): ReactElement {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    const crear = globalThis.URL?.createObjectURL;
    if (typeof crear !== "function" || typeof globalThis.Blob !== "function") {
      setUrl(null);
      return;
    }
    const objeto = crear.call(
      globalThis.URL,
      new globalThis.Blob([servido.contenido as unknown as BlobPart], { type: servido.medio }),
    );
    setUrl(objeto);
    return () => {
      globalThis.URL.revokeObjectURL(objeto);
    };
  }, [servido]);

  if (url === null) {
    return (
      <p className="cae-revision__sin-visor" data-bytes={servido.bytes}>
        {SIN_VISOR}
      </p>
    );
  }
  return (
    <object
      className="cae-revision__visor"
      data={url}
      type={servido.medio}
      aria-label={TITULO_DOCUMENTO}
    />
  );
}

function Identidad({
  documento,
  pagina,
}: {
  readonly documento: Documento;
  readonly pagina: number | null;
}): ReactElement {
  return (
    <header className="cae-revision__documento-cabecera">
      <p className="cae-revision__documento-nombre">{documento.nombre ?? documento.docId}</p>
      {documento.tipo === null ? null : (
        <p className="cae-revision__documento-tipo">{documento.tipo}</p>
      )}
      {pagina === null ? null : (
        <p className="cae-revision__documento-pagina">
          {`${ETIQUETA_PAGINA} ${pagina}`}
          {documento.paginas === null
            ? null
            : ` ${ETIQUETA_PAGINA_DE} ${documento.paginas}`}
        </p>
      )}
      {documento.origen === null ? null : (
        <p className="cae-revision__documento-parte" data-origen={documento.origen}>
          {DOCUMENTO_ES_PARTE}
          {documento.rangoPaginas === null
            ? null
            : ` ${ETIQUETA_RANGO_PAGINAS}: ${documento.rangoPaginas[0]}-${documento.rangoPaginas[1]}`}
        </p>
      )}
    </header>
  );
}

export function PanelDocumento({
  cliente,
  contexto,
  documento,
  pagina,
  textoLiteral,
}: PropsPanelDocumento): ReactElement {
  const docId = documento?.docId ?? null;
  const { lectura, recargar } = useLectura(
    CAPACIDAD_ACTUACION,
    async () =>
      docId === null ? null : await cliente.leerDocumento(CAPACIDAD_ACTUACION, contexto, docId),
    [docId, contexto.actuacion_id],
  );

  return (
    <section className="cae-revision__panel-documento" aria-label={TITULO_DOCUMENTO}>
      {documento === null ? (
        <p className="cae-revision__sin-documento">{SIN_DOCUMENTO_ELEGIDO}</p>
      ) : (
        <>
          <Identidad documento={documento} pagina={pagina} />
          {textoLiteral === null ? null : (
            <p className="cae-revision__documento-cita">
              <span className="cae-revision__etiqueta">{COLUMNA_TEXTO_LITERAL}</span>
              <q className="cae-revision__literal">{textoLiteral}</q>
            </p>
          )}
          {lectura.estado === "CARGANDO" ? (
            <p className="cae-revision__documento-cargando" role="status">
              {CARGANDO_DOCUMENTO}
            </p>
          ) : null}
          {lectura.estado === "ERROR" ? (
            <AvisoServidor fallo={lectura.fallo} onReintentar={recargar} />
          ) : null}
          {lectura.estado === "LISTO" && lectura.valor !== null ? (
            <>
              <Visor servido={lectura.valor} />
              <p className="cae-revision__documento-huella" data-doc={lectura.valor.doc_id}>
                {DOCUMENTO_INTACTO}
              </p>
              <p className="cae-revision__documento-bytes">
                {`${ETIQUETA_BYTES}: ${lectura.valor.bytes}`}
              </p>
            </>
          ) : null}
        </>
      )}
    </section>
  );
}
