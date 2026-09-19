// Fichero GENERADO por `api/tipos_front.py`. No se edita a mano.
//
// Sale de `api/proyeccion.py` (los bloques que el servidor sabe construir) y de
// `engine/capacidades.yaml` (que capacidad es lectura y cual es comando, y que bloques proyecta cada
// una). `tests/test_api_tipos_front.py` lo regenera y compara: si `api/` cambia y esto no, el banco de
// pruebas de Python se pone rojo; cuando se regenera, la compilacion de TypeScript senala cada sitio del
// front que usaba un bloque o una capacidad que ya no existe. De eso se trata (`ADR-012` §3, regla 4).
//
// Esto NO es una tabla de permisos. Que una capacidad exista aqui no significa que quien mira la pantalla
// pueda ejercerla: eso lo decide el servidor en cada peticion (`R-UI-01`).

/** Los bloques que una lectura puede traer. Los construye `api/proyeccion.py` y nadie mas. */
export const BLOQUES = [
  "identificacion",
  "estado_simplificado",
  "que_te_falta",
  "documentos",
  "evidencias",
  "conflictos",
  "calculo",
  "veredicto",
  "historial",
  "estados_plataforma",
  "actividad_usuarios",
  "metadatos_auditoria",
  "agregados",
] as const;

export type Bloque = (typeof BLOQUES)[number];

/**
 * Lo que viaja en `Respuesta.datos` de una lectura: **algunos** de los bloques, nunca todos.
 *
 * Todos son opcionales a proposito, y esa es la parte importante. `R-UI-12` dice que un bloque fuera del
 * ambito del rol **no se construye**; si aqui fueran obligatorios, el front creeria que siempre estan y
 * acabaria pintando `undefined` o, peor, inventandose un valor por defecto.
 */
export type Datos = { readonly [B in Bloque]?: unknown };

/** Las lecturas del contrato y los bloques que proyecta cada una. */
export const LECTURAS = {
  "CAP-03": ["identificacion", "documentos", "evidencias", "conflictos", "calculo", "veredicto", "historial"],
  "CAP-04": ["identificacion", "que_te_falta", "estado_simplificado"],
  "CAP-14": ["identificacion", "estados_plataforma"],
  "CAP-31": ["actividad_usuarios"],
  "CAP-35": [],
  "CAP-36": [],
  "CAP-40": ["identificacion", "estado_simplificado"],
  "CAP-58": ["agregados"],
  "CAP-64": [],
  "CAP-65": ["metadatos_auditoria"],
  "CAP-66": [],
  "CAP-67": [],
} as const satisfies Readonly<Record<string, readonly Bloque[]>>;

export type CapacidadLectura = keyof typeof LECTURAS;

/** Los comandos del contrato. Lo que escriben lo decide el servidor, no esta lista. */
export const COMANDOS = [
  "CAP-01",
  "CAP-02",
  "CAP-05",
  "CAP-06",
  "CAP-07",
  "CAP-08",
  "CAP-09",
  "CAP-10",
  "CAP-11",
  "CAP-12",
  "CAP-13",
  "CAP-15",
  "CAP-16",
  "CAP-20",
  "CAP-21",
  "CAP-22",
  "CAP-23",
  "CAP-30",
  "CAP-32",
  "CAP-33",
  "CAP-34",
  "CAP-50",
  "CAP-51",
  "CAP-52",
  "CAP-53",
  "CAP-54",
  "CAP-55",
  "CAP-56",
  "CAP-57",
  "CAP-60",
  "CAP-61",
  "CAP-62",
  "CAP-63",
  "CAP-70",
] as const;

export type CapacidadComando = (typeof COMANDOS)[number];
