/**
 * Lo que la vista de revision pide a `api/` y como queda lo que llega. **Ni una decision de negocio.**
 *
 * Las tres lecturas de `T-REV-revision` §5, y el reparto:
 *
 * - `CAP-03` trae la actuacion entera: identificacion, documentos, evidencias, conflictos, calculo,
 *   veredicto e historial. Sin ella no hay pantalla, y por eso es la unica que la tumba.
 * - `CAP-04` trae las carencias con su mensaje y el documento que las subsana.
 * - `CAP-14` trae el estado de ciclo, el de plataforma, el requerimiento abierto y los rechazos.
 *
 * `CAP-04` y `CAP-14` **fallan por su cuenta** y dejan su bloque con el motivo del servidor, igual que en
 * la cola: una lectura caida no tumba la revision entera. Lo que no se hace es dar por bueno lo que no se
 * ha podido leer — ver `escribiblePor` mas abajo.
 *
 * Tres cosas que aqui no pasan, y no por falta de sitio:
 *
 * 1. **No se calcula ni se convierte ninguna cifra** (`R-UI-11`, `CLAUDE.md` §2). Cada magnitud llega dos
 *    veces, exacta y presentable, y se transporta como cadena. Ni un `Number`.
 * 2. **No se nombra ninguna variable ni ninguna unidad.** El nombre legible de `PM`, su definicion, su
 *    referencia y la unidad del ahorro los declara la ficha y los sirve `api/` (`GAP-REV-05`,
 *    `GAP-REV-10`): aqui solo se leen.
 * 3. **No se deduce el veredicto.** Llega hecho y se pinta; lo unico que la pantalla mira para saber si
 *    queda algo abierto es lo que el servidor declara abierto: sus conflictos y sus carencias.
 */

import { bloque, type Cliente, type Contexto, type Respuesta } from "@cae/compartido/api";
import type { OrigenDatos } from "@cae/compartido";

import { falloDe, type FalloServidor } from "../fallos";
import { booleano, campo, entero, lista, objeto, texto, textos } from "../json";
import { origenDeclarado } from "../origen";

/** La pantalla, tal y como la declara `engine/capacidades.yaml` (`superficies.workspace.pantallas`). */
export const PANTALLA = "vista_revision";

export const CAPACIDAD_ACTUACION = "CAP-03";
export const CAPACIDAD_CARENCIAS = "CAP-04";
export const CAPACIDAD_ESTADOS = "CAP-14";

/** Los comandos de `T-REV-revision` §4. Nombrarlos no es concederlos: eso lo decide el servidor. */
export const CAPACIDAD_SUBIR = "CAP-02";
export const CAPACIDAD_CORREGIR = "CAP-05";
/**
 * `CAP-06` es **el mismo formulario** que `CAP-05` cuando lo que discrepa son dos extractores sobre el
 * mismo documento; lo que cambia es el `motivo` que se escribe en el log, no la pantalla
 * (`T-REV-revision` §6). Hoy no se dispara desde aquí: ninguna lectura distingue un desacuerdo entre
 * extractores de un conflicto entre fuentes, y elegir la capacidad por nuestra cuenta seria escribir en
 * el log un motivo que nadie ha comprobado. Queda nombrada porque el contrato la tiene.
 */
export const CAPACIDAD_DESACUERDO = "CAP-06";
export const CAPACIDAD_OBSERVACION = "CAP-07";
export const CAPACIDAD_DESCARTE = "CAP-08";
export const CAPACIDAD_SUBSANACION = "CAP-09";
export const CAPACIDAD_APROBAR = "CAP-10";
export const CAPACIDAD_INTERPRETACION = "CAP-15";
export const CAPACIDAD_DISCREPANCIA = "CAP-16";

/**
 * Las capacidades del **flujo de requerimiento oficial** (`R-UI-05`).
 *
 * Son las unicas que siguen activas cuando hay un requerimiento abierto sobre una actuacion ya firmada:
 * confirmar la interpretacion de lo que nos piden y contestar con la subsanacion. Lo demas sigue cerrado,
 * porque lo revisado y firmado solo se modifica por requerimiento oficial (`docs/02` §5.4).
 */
export const CAPACIDADES_DE_REQUERIMIENTO: readonly string[] = [
  CAPACIDAD_INTERPRETACION,
  CAPACIDAD_SUBSANACION,
];

/**
 * La severidad con la que una carencia deja la actuacion fuera de ambito (`CLAUDE.md` §3).
 *
 * Es vocabulario de `engine/` —la severidad que declara la ficha para esa regla—, no un veredicto: aqui
 * no se deduce ninguno. Se usa para **ensenar u ocultar** el control de descarte, que es lo que
 * `T-REV-revision` §8 pide, y ocultarlo no autoriza ni impide nada: la maquina de estados exige
 * igualmente que la actuacion sea no elegible para admitir el descarte (`R-UI-01`).
 *
 * `GAP-REV-12`: `api/` no dice que acciones caben sobre una actuacion. El dia que lo diga, esto sobra.
 */
export const SEVERIDAD_FUERA_DE_AMBITO = "BLOQUEANTE_AMBITO";

/** Tipos de evento del catalogo (`engine/eventos/catalogo.py`) que abren un bloque de la pantalla. */
export const EVENTO_OBSERVACION = "ObservacionRegistrada";
export const EVENTO_DISCREPANCIA = "DiscrepanciaCalculoPlataforma";
export const EVENTO_CORRECCION = "DatoCorregidoPorHumano";

/**
 * Lo que `CAP-05` devuelve para decir si el motor llego a recalcular (`ADR-014` C24).
 *
 * No es un bloque de proyeccion: es lo que el manejador del comando puso en `Salida.datos`, y la
 * pantalla lo lee para no presentar como actualizado un veredicto que no lo esta (`CA-REV-09`).
 */
export const CLAVE_RECALCULADA = "recalculada";

/** El metodo con el que llega una evidencia que no sale de un papel sino del log (`engine/`). */
export const METODO_CORRECCION_HUMANA = "correccion_humana";

/** Una lectura que salio bien, o el fallo del servidor tal cual. Nunca "no hay datos". */
export type Resultado<T> =
  | { readonly estado: "LISTO"; readonly valor: T }
  | { readonly estado: "ERROR"; readonly fallo: FalloServidor };

/**
 * Una evidencia: el valor, y **de donde se leyo** (`R-UI-09`).
 *
 * `docId`, `pagina` y `textoLiteral` son la cita. Una correccion humana llega por este mismo camino, con
 * `metodo` = `correccion_humana`, el identificador del evento en `docId` y la justificacion escrita en
 * `textoLiteral`: no sale de un papel, y la pantalla lo dice en vez de ensenar "pagina 0".
 */
export interface Cita {
  readonly valor: string | null;
  readonly docId: string | null;
  readonly tipoDoc: string | null;
  readonly pagina: number | null;
  readonly textoLiteral: string | null;
  readonly metodo: string | null;
  readonly confianza: string | null;
  readonly tipoEvidencia: string | null;
  readonly extractorVersion: string | null;
  readonly unidad: string | null;
}

/** Un dato consolidado con sus tres capas: la evidencia, la interpretacion y lo que consumio el calculo. */
export interface Dato {
  readonly variable: string;
  readonly numSerieMotor: string | null;
  /** Lo que la ficha dice de la variable (`GAP-REV-05`). Nulo si la spec no lo declara: no se inventa. */
  readonly descripcion: string | null;
  readonly definicion: string | null;
  readonly referencia: string | null;
  readonly unidad: string | null;
  readonly valorConsumido: string | null;
  readonly valorNormalizado: string | null;
  readonly tipoEvidencia: string | null;
  readonly fuentePrimaria: string | null;
  readonly interpretacion: string | null;
  readonly conflicto: boolean;
  /** Fuente documental → valor que aporta. Existe con calculo y sin el (`T-REV-revision` §6). */
  readonly valoresPorFuente: readonly (readonly [string, string])[];
  readonly avisos: readonly string[];
  readonly citas: readonly Cita[];
}

/** Un conflicto entre fuentes fiables: el motor no elige y no calcula (regla de oro 6). */
export interface Conflicto {
  readonly variable: string;
  readonly numSerieMotor: string | null;
  readonly citas: readonly Cita[];
}

/** Una comprobacion, tal y como la sirve `veredicto.reglas[]` (`GAP-REV-02`). */
export interface Regla {
  readonly id: string;
  readonly resultado: string | null;
  readonly severidad: string | null;
  readonly fase: string | null;
  readonly nivel: string | null;
  readonly descripcion: string | null;
  readonly referencia: string | null;
  readonly interpretacion: string | null;
  readonly motivo: string | null;
}

export interface Veredicto {
  readonly valor: string | null;
  readonly semaforo: string | null;
  readonly mensaje: string | null;
  /** El descargo del servidor. Se muestra literal y entero, y **no** es texto del front (§11 bis). */
  readonly descargo: string | null;
  readonly reglas: readonly Regla[];
  readonly interpretaciones: readonly string[];
  readonly hashReglas: string | null;
}

/** Una magnitud del calculo: exacta, presentable y con lo que la ficha dice de ella. */
export interface Magnitud {
  readonly nombre: string;
  readonly exacto: string | null;
  readonly presentable: string | null;
  readonly descripcion: string | null;
  readonly referencia: string | null;
  readonly unidad: string | null;
  /** De donde sale una derivada (`derivado`, `tabla:REG1781_CUADRO6`). Una entrada no la trae. */
  readonly fuente: string | null;
}

export interface UnidadCalculo {
  readonly numSerieMotor: string | null;
  readonly salida: string | null;
  readonly salidaPresentable: string | null;
  readonly salidaUnidad: string | null;
  readonly motivoNoCalculo: string | null;
  readonly entradas: readonly Magnitud[];
  readonly derivadas: readonly Magnitud[];
  /** Identificador → lo que dio: `true`, `false` o el centinela `"NO_EVALUABLE"` (`GAP-REV-09`). */
  readonly controles: readonly (readonly [string, string])[];
  readonly precondiciones: readonly (readonly [string, string])[];
  readonly interpretaciones: readonly string[];
  readonly avisos: readonly string[];
}

export interface Calculo {
  readonly totalExacto: string | null;
  readonly totalPresentable: string | null;
  readonly totalCae: string | null;
  readonly totalCaePresentable: string | null;
  readonly unidad: string | null;
  readonly provisional: boolean | null;
  readonly motivoNoCalculo: string | null;
  readonly traza: readonly string[];
  readonly porUnidad: readonly UnidadCalculo[];
}

export interface Documento {
  readonly docId: string;
  readonly nombre: string | null;
  readonly tipo: string | null;
  readonly paginas: number | null;
  readonly origen: string | null;
  readonly rangoPaginas: readonly [number, number] | null;
}

export interface Carencia {
  readonly id: string | null;
  readonly severidad: string | null;
  readonly mensaje: string | null;
  readonly documentos: readonly string[];
}

export interface Evento {
  readonly tipo: string;
  readonly ocurridoEn: string | null;
  readonly actor: string | null;
  readonly rol: string | null;
  readonly payload: Readonly<Record<string, unknown>>;
}

export interface Estados {
  readonly ciclo: string | null;
  readonly plataforma: string | null;
  readonly requerimientoAbierto: string | null;
  readonly afectadaDirectamente: boolean | null;
  readonly revisadaPorHumano: boolean | null;
  readonly firmada: boolean | null;
  readonly rechazos: readonly string[];
  readonly literalesDesconocidos: readonly string[];
}

export interface Identificacion {
  readonly actuacionId: string | null;
  readonly codigo: string | null;
  readonly ficha: string | null;
  readonly fechaEvaluacion: string | null;
}

export interface Revision {
  /** `Respuesta.rol_nombre`: el nombre del rol, resuelto y nombrado por el servidor. */
  readonly rolNombre: string | null;
  readonly origen: OrigenDatos;
  readonly avisos: readonly string[];
  readonly identificacion: Identificacion;
  readonly veredicto: Veredicto;
  readonly conflictos: readonly Conflicto[];
  readonly calculo: Calculo;
  readonly datos: readonly Dato[];
  readonly documentos: readonly Documento[];
  readonly historial: readonly Evento[];
  readonly carencias: Resultado<readonly Carencia[]>;
  readonly estados: Resultado<Estados>;
}

// ---------------------------------------------------------------------------
// De lo que llega a lo que se pinta
// ---------------------------------------------------------------------------

function citaDe(origen: unknown): Cita {
  const cruda = objeto(origen);
  return {
    valor: texto(cruda?.["valor"]),
    docId: texto(cruda?.["doc_id"]),
    tipoDoc: texto(cruda?.["tipo_doc"]),
    pagina: entero(cruda?.["pagina"]),
    textoLiteral: texto(cruda?.["texto_literal"]),
    metodo: texto(cruda?.["metodo"]),
    confianza: texto(cruda?.["confianza"]),
    tipoEvidencia: texto(cruda?.["tipo_evidencia"]),
    extractorVersion: texto(cruda?.["extractor_version"]),
    unidad: texto(cruda?.["unidad"]),
  };
}

/** Pares `[clave, valor]` de un objeto del servidor, **en el orden en que llegaron** (`R-UI-11`). */
function pares(origen: unknown): readonly (readonly [string, string])[] {
  const mapa = objeto(origen);
  if (mapa === null) {
    return [];
  }
  return Object.entries(mapa).map(([clave, valor]) => [clave, String(valor)] as const);
}

function datoDe(origen: unknown): Dato | null {
  const crudo = objeto(origen);
  const variable = texto(crudo?.["variable"]);
  if (variable === null) {
    return null;
  }
  return {
    variable,
    numSerieMotor: texto(crudo?.["num_serie_motor"]),
    descripcion: texto(crudo?.["descripcion"]),
    definicion: texto(crudo?.["definicion"]),
    referencia: texto(crudo?.["referencia"]),
    unidad: texto(crudo?.["unidad"]),
    // Un valor que no es texto (una lista de requisitos, por ejemplo) se transporta tal cual lo
    // serializo el servidor; lo que no se hace es convertirlo ni resumirlo.
    valorConsumido: texto(crudo?.["valor_consumido"]),
    valorNormalizado: texto(crudo?.["valor_normalizado"]),
    tipoEvidencia: texto(crudo?.["tipo_evidencia"]),
    fuentePrimaria: texto(crudo?.["fuente_primaria"]),
    interpretacion: texto(crudo?.["interpretacion"]),
    conflicto: booleano(crudo?.["conflicto"]) === true,
    valoresPorFuente: pares(crudo?.["valores_por_fuente"]),
    avisos: textos(crudo?.["avisos"]),
    citas: lista(crudo?.["evidencias"]).map((cruda) => citaDe(cruda)),
  };
}

function reglaDe(origen: unknown): Regla | null {
  const cruda = objeto(origen);
  const id = texto(cruda?.["id"]);
  if (id === null) {
    return null;
  }
  return {
    id,
    resultado: texto(cruda?.["resultado"]),
    severidad: texto(cruda?.["severidad"]),
    fase: texto(cruda?.["fase"]),
    nivel: texto(cruda?.["nivel"]),
    descripcion: texto(cruda?.["descripcion"]),
    referencia: texto(cruda?.["referencia"]),
    interpretacion: texto(cruda?.["interpretacion"]),
    motivo: texto(cruda?.["motivo"]),
  };
}

function magnitudes(
  valores: unknown,
  presentables: unknown,
  fuentes: unknown,
  variables: unknown,
): readonly Magnitud[] {
  const legibles = objeto(presentables);
  const origenes = objeto(fuentes);
  const declaradas = objeto(variables);
  return pares(valores).map(([nombre, exacto]) => {
    const declarada = objeto(declaradas?.[nombre]);
    return {
      nombre,
      exacto,
      presentable: texto(legibles?.[nombre]),
      descripcion: texto(declarada?.["descripcion"]),
      referencia: texto(declarada?.["referencia"]),
      unidad: texto(declarada?.["unidad"]),
      fuente: texto(origenes?.[nombre]),
    };
  });
}

function unidadDe(origen: unknown, variables: unknown): UnidadCalculo {
  const cruda = objeto(origen);
  return {
    numSerieMotor: texto(cruda?.["num_serie_motor"]),
    salida: texto(cruda?.["salida"]),
    salidaPresentable: texto(cruda?.["salida_presentable"]),
    salidaUnidad: texto(cruda?.["salida_unidad"]),
    motivoNoCalculo: texto(cruda?.["motivo_no_calculo"]),
    entradas: magnitudes(cruda?.["entradas"], cruda?.["entradas_presentables"], null, variables),
    derivadas: magnitudes(
      cruda?.["derivadas"],
      cruda?.["derivadas_presentables"],
      cruda?.["fuentes"],
      variables,
    ),
    controles: pares(cruda?.["controles"]),
    precondiciones: pares(cruda?.["precondiciones"]),
    interpretaciones: textos(cruda?.["interpretaciones"]),
    avisos: textos(cruda?.["avisos"]),
  };
}

function calculoDe(respuesta: Respuesta): Calculo {
  const crudo = objeto(bloque(respuesta, "calculo"));
  const variables = crudo?.["variables"];
  return {
    totalExacto: texto(crudo?.["total_exacto"]),
    totalPresentable: texto(crudo?.["total_exacto_presentable"]),
    // `total_cae` llega como entero (kWh truncados, INT-06) y se transporta como el texto que llego.
    totalCae: crudo?.["total_cae"] === null ? null : String(crudo?.["total_cae"] ?? ""),
    totalCaePresentable: texto(crudo?.["total_cae_presentable"]),
    unidad: texto(crudo?.["total_unidad"]),
    provisional: booleano(crudo?.["provisional"]),
    motivoNoCalculo: texto(crudo?.["motivo_no_calculo"]),
    traza: textos(crudo?.["traza"]),
    porUnidad: lista(crudo?.["por_unidad"]).map((unidad) => unidadDe(unidad, variables)),
  };
}

function veredictoDe(respuesta: Respuesta): Veredicto {
  const crudo = objeto(bloque(respuesta, "veredicto"));
  return {
    valor: texto(crudo?.["valor"]),
    semaforo: texto(crudo?.["semaforo"]),
    mensaje: texto(crudo?.["mensaje"]),
    descargo: texto(crudo?.["descargo"]),
    reglas: lista(crudo?.["reglas"])
      .map((regla) => reglaDe(regla))
      .filter((regla): regla is Regla => regla !== null),
    interpretaciones: textos(crudo?.["interpretaciones_aplicadas"]),
    hashReglas: texto(crudo?.["hash_reglas"]),
  };
}

function conflictoDe(origen: unknown): Conflicto | null {
  const conflicto = objeto(origen);
  const variable = texto(conflicto?.["variable"]);
  if (variable === null) {
    return null;
  }
  return {
    variable,
    numSerieMotor: texto(conflicto?.["num_serie_motor"]),
    citas: lista(conflicto?.["evidencias"]).map((evidencia) => citaDe(evidencia)),
  };
}

function conflictosDe(respuesta: Respuesta): readonly Conflicto[] {
  return lista(bloque(respuesta, "conflictos"))
    .map((cruda) => conflictoDe(cruda))
    .filter((conflicto): conflicto is Conflicto => conflicto !== null);
}

function documentosDe(respuesta: Respuesta): readonly Documento[] {
  return lista(bloque(respuesta, "documentos"))
    .map((cruda) => {
      const documento = objeto(cruda);
      const docId = texto(documento?.["doc_id"]);
      if (docId === null) {
        return null;
      }
      const rango = lista(documento?.["rango_paginas"]).map((pagina) => entero(pagina));
      const [desde, hasta] = rango;
      return {
        docId,
        nombre: texto(documento?.["nombre"]),
        tipo: texto(documento?.["tipo"]),
        paginas: entero(documento?.["paginas"]),
        origen: texto(documento?.["origen"]),
        rangoPaginas:
          desde === undefined || desde === null || hasta === undefined || hasta === null
            ? null
            : ([desde, hasta] as const),
      };
    })
    .filter((documento): documento is Documento => documento !== null);
}

function historialDe(respuesta: Respuesta): readonly Evento[] {
  return lista(bloque(respuesta, "historial"))
    .map((cruda) => {
      const evento = objeto(cruda);
      const tipo = texto(evento?.["tipo"]);
      if (tipo === null) {
        return null;
      }
      return {
        tipo,
        ocurridoEn: texto(evento?.["ocurrido_en"]),
        actor: texto(campo(evento, "actor", "id")),
        rol: texto(campo(evento, "actor", "rol")),
        payload: objeto(evento?.["payload"]) ?? {},
      };
    })
    .filter((evento): evento is Evento => evento !== null);
}

function carenciasDe(respuesta: Respuesta): readonly Carencia[] {
  return lista(campo(bloque(respuesta, "que_te_falta"), "carencias")).map((cruda) => {
    const carencia = objeto(cruda);
    return {
      id: texto(carencia?.["id"]),
      severidad: texto(carencia?.["severidad"]),
      mensaje: texto(carencia?.["mensaje"]),
      documentos: textos(carencia?.["documentos"]),
    };
  });
}

function estadosDe(respuesta: Respuesta): Estados {
  const crudo = objeto(bloque(respuesta, "estados_plataforma"));
  return {
    ciclo: texto(crudo?.["estado_ciclo"]),
    plataforma: texto(crudo?.["estado_plataforma"]),
    requerimientoAbierto: texto(crudo?.["requerimiento_abierto"]),
    afectadaDirectamente: booleano(crudo?.["afectada_directamente"]),
    revisadaPorHumano: booleano(crudo?.["revisada_por_humano"]),
    firmada: booleano(crudo?.["firmada"]),
    rechazos: lista(crudo?.["rechazos"]).map((rechazo) => JSON.stringify(rechazo)),
    literalesDesconocidos: textos(crudo?.["literales_desconocidos"]),
  };
}

function identificacionDe(respuesta: Respuesta): Identificacion {
  const crudo = objeto(bloque(respuesta, "identificacion"));
  return {
    actuacionId: texto(crudo?.["actuacion_id"]),
    codigo: texto(crudo?.["codigo_identificativo_propio"]),
    ficha: texto(crudo?.["ficha"]),
    fechaEvaluacion: texto(crudo?.["fecha_evaluacion"]),
  };
}

/** Pide una lectura y devuelve lo que trajo **o el fallo**, que tambien es informacion. */
async function intentar<T>(
  cliente: Cliente,
  capacidad: "CAP-04" | "CAP-14",
  contexto: Contexto,
  extraer: (respuesta: Respuesta) => T,
): Promise<Resultado<T>> {
  try {
    return { estado: "LISTO", valor: extraer(await cliente.leer(capacidad, contexto)) };
  } catch (causa) {
    return { estado: "ERROR", fallo: falloDe(capacidad, causa) };
  }
}

/**
 * La actuacion entera: lo que hace falta para decidir, y las dos lecturas que la acompanan.
 *
 * Si `CAP-03` falla, falla la pantalla: no hay ni veredicto ni datos que ensenar, y el aviso sale con el
 * motivo del servidor. Si falla `CAP-04` o `CAP-14`, falla su bloque y se dice cual.
 */
export async function cargarRevision(
  cliente: Cliente,
  tenantId: string,
  actuacionId: string,
): Promise<Revision> {
  const contexto: Contexto = {
    superficie: PANTALLA,
    tenant_id: tenantId,
    actuacion_id: actuacionId,
  };
  const respuesta = await cliente.leer(CAPACIDAD_ACTUACION, contexto);
  const [carencias, estados] = await Promise.all([
    intentar(cliente, CAPACIDAD_CARENCIAS, contexto, carenciasDe),
    intentar(cliente, CAPACIDAD_ESTADOS, contexto, estadosDe),
  ]);

  return {
    rolNombre: respuesta.rol_nombre,
    // `GAP-REV-07`: hoy ningun bloque lo declara y sale `ORIGEN DE DATOS SIN DECLARAR`.
    origen: origenDeclarado(bloque(respuesta, "identificacion")),
    avisos: respuesta.avisos,
    identificacion: identificacionDe(respuesta),
    veredicto: veredictoDe(respuesta),
    conflictos: conflictosDe(respuesta),
    calculo: calculoDe(respuesta),
    datos: lista(bloque(respuesta, "evidencias"))
      .map((dato) => datoDe(dato))
      .filter((dato): dato is Dato => dato !== null),
    documentos: documentosDe(respuesta),
    historial: historialDe(respuesta),
    carencias,
    estados,
  };
}

// ---------------------------------------------------------------------------
// Lo que la pantalla necesita saber para ensenar o inhabilitar, y de donde lo saca
// ---------------------------------------------------------------------------

/** Las carencias que llegaron, o ninguna si esa lectura fallo. El fallo se ensena aparte. */
export function carenciasDeclaradas(revision: Revision): readonly Carencia[] {
  return revision.carencias.estado === "LISTO" ? revision.carencias.valor : [];
}

/**
 * Que hay abierto, segun **el servidor**: sus conflictos y sus carencias. Nada mas.
 *
 * `T-REV-revision` §8 condiciona "Aprobar" a que no queden bloqueantes abiertos. La pantalla no lo
 * deduce del veredicto —no lo interpreta, no lo compara con ninguna lista y no lo escribe en ninguna
 * parte (`R-UI-02`, `CA-REV-01`)—: pregunta por lo que el propio servidor declara pendiente en
 * `conflictos` y en `que_te_falta`, que es lo unico que se puede ir a arreglar.
 *
 * Y si `CAP-04` no contesto, **no se da por bueno que no falte nada**: sin saberlo, no se aprueba.
 */
export function quedaAlgoAbierto(revision: Revision): boolean {
  if (revision.carencias.estado === "ERROR") {
    return true;
  }
  return revision.conflictos.length > 0 || revision.carencias.valor.length > 0;
}

/** Si alguna carencia deja la actuacion fuera de ambito: entonces cabe confirmar su descarte. */
export function fueraDeAmbito(revision: Revision): boolean {
  return carenciasDeclaradas(revision).some(
    (carencia) => carencia.severidad === SEVERIDAD_FUERA_DE_AMBITO,
  );
}

/**
 * Con que regla se puede escribir hoy en esta actuacion (`R-UI-05`).
 *
 * - `"TODO"`: nada lo impide.
 * - `"REQUERIMIENTO"`: la actuacion ya esta firmada y hay un requerimiento oficial abierto; solo se
 *   activan las capacidades de su flujo (`CAPACIDADES_DE_REQUERIMIENTO`).
 * - `"NADA"`: solo lectura.
 *
 * **Por que `firmada` y no solo el estado de ciclo.** `T-REV-revision` §9 describe el candado como
 * `estado_ciclo == "EN_PLATAFORMA"` y lo levanta a medias cuando hay requerimiento abierto. Esas dos
 * condiciones no se pueden dar a la vez: al anotar el requerimiento, `engine.estados` mueve el ciclo a
 * `PENDIENTE_SUBSANACION` (comprobado al generar los datos de prueba, `datos/generar.py`). Apoyar el
 * candado solo en el ciclo lo abriria entero justo cuando llega un requerimiento, que es lo contrario de
 * lo que la regla protege. Se apoya en `firmada`, que es la marca con la que el propio nucleo rechaza
 * una correccion posterior a la firma (`docs/02` §5.4, `CorreccionRechazadaPostFirma`), y el estado de
 * ciclo se sigue mirando para la actuacion que esta en la plataforma sin haberse firmado aqui.
 *
 * Y si `CAP-14` no contesto: **`"NADA"`**. No saber si se puede escribir no es poder escribir. El
 * servidor valida igualmente (`R-UI-01`); esto solo decide que se ensena activo.
 */
export type Escritura = "TODO" | "REQUERIMIENTO" | "NADA";

/** El estado de ciclo en el que la actuacion ya esta en manos de la plataforma (`engine/estados.py`). */
const ESTADO_EN_PLATAFORMA = "EN_PLATAFORMA";

export function escrituraPermitida(revision: Revision): Escritura {
  if (revision.estados.estado === "ERROR") {
    return "NADA";
  }
  const estados = revision.estados.valor;
  const cerrada = estados.firmada === true || estados.ciclo === ESTADO_EN_PLATAFORMA;
  if (!cerrada) {
    return "TODO";
  }
  return estados.requerimientoAbierto === null ? "NADA" : "REQUERIMIENTO";
}

/** Si una capacidad concreta se puede ejercer hoy desde la pantalla. Ensenar no es autorizar. */
export function escribiblePor(escritura: Escritura, capacidad: string): boolean {
  if (escritura === "TODO") {
    return true;
  }
  if (escritura === "NADA") {
    return false;
  }
  return CAPACIDADES_DE_REQUERIMIENTO.includes(capacidad);
}

/** El dato que corresponde a una variable y una unidad, o `undefined`. No se inventa ninguno. */
export function datoDeVariable(
  revision: Revision,
  variable: string,
  numSerieMotor: string | null,
): Dato | undefined {
  return revision.datos.find(
    (dato) => dato.variable === variable && dato.numSerieMotor === numSerieMotor,
  );
}
