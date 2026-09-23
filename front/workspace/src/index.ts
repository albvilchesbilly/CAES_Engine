/**
 * Workspace del tenant (`ADR-050`): la superficie de `T-RES`, `T-OPE` y `T-REV`.
 *
 * Lo que sale por aqui son **pantallas y andamiaje**, nunca logica de negocio (`R-UI-11`). Cada pantalla
 * recibe un `Cliente` de `@cae/compartido/api` ya construido con su transporte: este paquete no crea
 * clientes, no conoce ninguna URL y no habla con `engine/` — la dependencia va hacia dentro y se para en
 * `api/`.
 *
 * `FR1.c` entrega las dos pantallas de `T-REV`: la cola (`cola/`) y la vista de revision (`revision/`).
 * Las dos comparten el mismo andamiaje —`Pantalla`, `AvisoServidor`, `useLectura`, los lectores de
 * `json.ts`, `fallos.ts`, `fechas.ts` y el catalogo de `textos.ts`— y no comparten ni un fichero de
 * pantalla: anadir la segunda no ha exigido tocar la primera mas que para lo que `api/` empezo a servir
 * (el nombre del rol y la unidad del ahorro).
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

export { VistaRevision, type PropsVistaRevision } from "./revision/VistaRevision";
export { Acciones, type PropsAcciones } from "./revision/Acciones";
export { Ahorro, type PropsAhorro } from "./revision/Ahorro";
export { Citas, TablaCitas, esCorreccionHumana, type PropsCitas } from "./revision/Citas";
export { Correccion, type DatosCorreccion, type PropsCorreccion } from "./revision/Correccion";
export { Datos as DatosConsolidados, type PropsDatos } from "./revision/Datos";
export { Impedimentos, type PropsImpedimentos } from "./revision/Impedimentos";
export { PanelDocumento, type PropsPanelDocumento } from "./revision/PanelDocumento";
export {
  CAPACIDADES_DE_REQUERIMIENTO,
  CAPACIDAD_APROBAR,
  CAPACIDAD_CORREGIR,
  CAPACIDAD_DESACUERDO,
  CAPACIDAD_DESCARTE,
  CAPACIDAD_DISCREPANCIA,
  CAPACIDAD_INTERPRETACION,
  CAPACIDAD_OBSERVACION,
  CAPACIDAD_SUBIR,
  CAPACIDAD_SUBSANACION,
  CLAVE_RECALCULADA,
  METODO_CORRECCION_HUMANA,
  PANTALLA as PANTALLA_REVISION,
  SEVERIDAD_FUERA_DE_AMBITO,
  cargarRevision,
  carenciasDeclaradas,
  datoDeVariable,
  escribiblePor,
  escrituraPermitida,
  fueraDeAmbito,
  quedaAlgoAbierto,
  type Calculo,
  type Carencia as CarenciaRevision,
  type Cita,
  type Conflicto,
  type Dato,
  type Documento,
  type Escritura,
  type Estados,
  type Evento,
  type Identificacion,
  type Magnitud,
  type Regla,
  type Revision,
  type UnidadCalculo,
  type Veredicto,
} from "./revision/datos";
