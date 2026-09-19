/**
 * Contrato C18 (`ADR-012` §3): lo unico que el front usa para hablar con `api/`.
 *
 * Se publica como subcamino (`@cae/compartido/api`) y no desde el indice del paquete a proposito: los
 * tres rotulos de `FR0` son componentes de presentacion puros, sin red, y tienen que poder seguir
 * siendolo. Quien importa `@cae/compartido` no se lleva un cliente HTTP de regalo.
 */

export {
  bloque,
  crearCliente,
  ErrorApi,
  ErrorPermiso,
  type Cliente,
  type Contexto,
  type DocumentoServido,
  type Respuesta,
} from "./cliente";
export {
  transporteHttp,
  type Buscador,
  type PeticionTransporte,
  type RespuestaTransporte,
  type Transporte,
} from "./transporte";
export {
  BLOQUES,
  COMANDOS,
  LECTURAS,
  type Bloque,
  type CapacidadComando,
  type CapacidadLectura,
  type Datos,
} from "./contrato.generado";
