/**
 * Lo que el empaquetador anade al lenguaje, declarado a mano y no por `vite/client`.
 *
 * Son dos cosas y las dos caben aqui: la variable con el principal y el hecho de que una hoja de
 * estilos se pueda importar. Arrastrar los tipos globales de Vite metería en el proyecto declaraciones
 * de cosas que esta pagina no usa.
 */

interface ImportMetaEnv {
  /** El principal de desarrollo, en JSON. Sin valor por defecto (ver `configuracion.ts`). */
  readonly VITE_CAE_PRINCIPAL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module "*.css";
