/**
 * Workspace del tenant (`ADR-050`): la superficie de `T-RES`, `T-OPE` y `T-REV`.
 *
 * Lo que sale por aqui son **pantallas y andamiaje**, nunca logica de negocio (`R-UI-11`). Cada pantalla
 * recibe un `Cliente` de `@cae/compartido/api` ya construido con su transporte: este paquete no crea
 * clientes, no conoce ninguna URL y no habla con `engine/` — la dependencia va hacia dentro y se para en
 * `api/`.
 *
 * `FR1.c` entrega `T-REV-cola`. La vista de revision (`T-REV-revision`) entra como otra carpeta al lado
 * de `cola/` y reutiliza el mismo andamiaje: `Pantalla`, `AvisoServidor`, `useLectura`, los lectores de
 * `json.ts`, `fallos.ts`, `fechas.ts` y el catalogo de `textos.ts`.
 */

export { AvisoServidor, type PropsAvisoServidor } from "./AvisoServidor";
export { Pantalla, type PropsPantalla } from "./Pantalla";
export { falloDe, type ClaseFallo, type FalloServidor } from "./fallos";
export { diasDesde, fechaAbsoluta, textoAntiguedad } from "./fechas";
export { booleano, campo, entero, lista, objeto, texto, textos } from "./json";
export { CAMPO_ORIGEN, origenDeclarado } from "./origen";
export { useLectura, type Lectura, type UsoLectura } from "./useLectura";
export * as textosWorkspace from "./textos";

export { ColaRevision, type PropsColaRevision } from "./cola/ColaRevision";
export { Fila, type PropsFilaCola } from "./cola/FilaCola";
export {
  CAPACIDAD_ACTUACION,
  CAPACIDAD_CARENCIAS,
  CAPACIDAD_COLA,
  CAPACIDAD_ESTADOS,
  PANTALLA,
  cargarCola,
  filaDe,
  type CalculoCola,
  type Carencia,
  type Cola,
  type DetalleFila,
  type EstadosCola,
  type FilaCola,
  type MotivoCola,
  type Resultado,
} from "./cola/datos";
export { ROTULOS, rotuloDe } from "./cola/motivos";
