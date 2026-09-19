/**
 * Sistema de diseno minimo del CAE Engine (`ADR-011` §5, contrato C16).
 *
 * En FR0 solo viven aqui los tres rotulos que impiden que la interfaz mienta. Son componentes de
 * presentacion puros: no llaman a la red, no importan nada de `engine/` ni de `api/` y no contienen
 * logica de negocio (`R-UI-11`). El contrato con `api/` llega en FR1.
 */

export { MarcaOrigen, type OrigenDatos, type PropsMarcaOrigen } from "./MarcaOrigen";
export {
  RotuloPrevalidado,
  type PropsRotuloPrevalidado,
  type TipoRotulo,
} from "./RotuloPrevalidado";
export { ValorMetrica, type PropsValorMetrica } from "./ValorMetrica";
export {
  resolverPresentacion,
  type MetricaPresentable,
  type Presentacion,
} from "./valores";
export * as textos from "./textos";
