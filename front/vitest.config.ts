import { defineConfig } from "vitest/config";

// Sin plugin de Vite para React: vitest transforma .tsx con esbuild y respeta `jsx: react-jsx`
// del tsconfig, asi que el plugin seria una dependencia mas sin nada que aportar en FR0.
export default defineConfig({
  test: {
    // Los rotulos son componentes de presentacion: se comprueban sobre el DOM que ve la persona
    // (textContent), no sobre el marcado. Eso exige un DOM, y jsdom es el estandar del stack.
    environment: "jsdom",
    globals: true,
    include: ["*/tests/**/*.test.ts?(x)"],
  },
});
