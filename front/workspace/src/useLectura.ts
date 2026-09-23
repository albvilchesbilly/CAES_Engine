/**
 * Una lectura de `api/` con sus tres estados, y ninguno mas: cargando, listo o fallido.
 *
 * Los tres son distintos a proposito (`T-REV-cola` §7): el hueco de carga no es `SIN DATO`, `SIN DATO`
 * no es un cero, y un error **no** se sustituye por "no hay datos" (`ADR-012` §3, regla 2). Que los tres
 * vivan en un tipo cerrado es lo que impide que una pantalla se olvide de uno.
 *
 * Este hook no sabe nada de la cola ni de ninguna pantalla: es el andamiaje que comparten las del
 * workspace. No decide nada (`R-UI-11`); pide, espera y cuenta lo que paso.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { falloDe, type FalloServidor } from "./fallos";

export type Lectura<T> =
  | { readonly estado: "CARGANDO" }
  | { readonly estado: "LISTO"; readonly valor: T }
  | { readonly estado: "ERROR"; readonly fallo: FalloServidor };

export interface UsoLectura<T> {
  readonly lectura: Lectura<T>;
  /** Vuelve a pedir lo mismo. Es la accion del aviso de error; no cambia nada en el servidor. */
  readonly recargar: () => void;
}

const CARGANDO = { estado: "CARGANDO" } as const;

/**
 * Ejecuta `cargar` al montar y cada vez que cambie `dependencias`, y expone en que va.
 *
 * `capacidad` es solo para el aviso: si lo que falla no es un error del contrato, el aviso dice al menos
 * que se estaba pidiendo. Un resultado que llega tarde, cuando las dependencias ya han cambiado o la
 * pantalla se ha desmontado, se descarta: pintar la respuesta de una peticion que ya no vale seria
 * ensenar el expediente de otra actuacion.
 */
export function useLectura<T>(
  capacidad: string,
  cargar: () => Promise<T>,
  dependencias: readonly unknown[],
): UsoLectura<T> {
  const [intento, setIntento] = useState(0);
  const [lectura, setLectura] = useState<Lectura<T>>(CARGANDO);

  // La funcion se guarda en una referencia que se refresca **antes** del efecto que carga (los efectos
  // corren en orden de declaracion), para que las dependencias sean las que manda quien llama y no la
  // identidad de una funcion que cambia en cada render.
  const pendiente = useRef(cargar);
  useEffect(() => {
    pendiente.current = cargar;
  });

  useEffect(() => {
    let vigente = true;
    setLectura(CARGANDO);
    pendiente.current().then(
      (valor) => {
        if (vigente) {
          setLectura({ estado: "LISTO", valor });
        }
      },
      (causa: unknown) => {
        if (vigente) {
          setLectura({ estado: "ERROR", fallo: falloDe(capacidad, causa) });
        }
      },
    );
    return () => {
      vigente = false;
    };
  }, [capacidad, intento, ...dependencias]);

  const recargar = useCallback(() => {
    setIntento((anterior) => anterior + 1);
  }, []);

  return { lectura, recargar };
}
