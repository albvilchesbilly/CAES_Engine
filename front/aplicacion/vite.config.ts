/**
 * El empaquetador de desarrollo (`GAP-HTTP-03`).
 *
 * Vite y no otro: es el estandar de facto para React con TypeScript y **ya esta en el arbol**, porque
 * es sobre lo que corre `vitest`, que entro en `FR0`. Elegir otro anadiria una segunda cadena de
 * transformacion para el mismo codigo, con la posibilidad de que las pruebas y el navegador dejen de
 * ver lo mismo.
 *
 * Dos decisiones que conviene leer antes de tocarlo:
 *
 * 1. **Sin plugin de React.** Vite transforma `.tsx` con esbuild respetando `jsx: "react-jsx"` del
 *    `tsconfig`, igual que hace `vitest` (ver `front/vitest.config.ts`). El plugin solo anadiria
 *    recarga en caliente, y no a cambio de nada: es una dependencia mas.
 * 2. **El servidor se alcanza por `/api`, reenviado desde aqui.** Asi el navegador habla con un solo
 *    origen y **no hace falta abrir CORS** en `servidor_desarrollo.py`, que lo tiene desactivado a
 *    proposito y sin comodin (`ADR-015` §7). La peticion le llega desde el bucle local, que es lo unico
 *    que el autenticador de desarrollo atiende (C29).
 */

import { defineConfig } from "vite";

/** A donde se reenvia `/api`. Es la direccion del servidor, no una credencial: puede tener defecto. */
const SERVIDOR = process.env["CAE_SERVIDOR"] ?? "http://127.0.0.1:8000";

export default defineConfig({
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: SERVIDOR,
        changeOrigin: false,
        rewrite: (ruta) => ruta.replace(/^\/api/, ""),
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
