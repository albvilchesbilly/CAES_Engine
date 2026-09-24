/**
 * `npm run e2e` — la comprobación que de verdad cierra `GAP-HTTP-03`: **un navegador de verdad contra
 * el servidor de verdad**.
 *
 * **No entra en la puerta de siempre** (`npm test`), y es a propósito: necesita los dos procesos
 * levantados y un Chromium, arranca en decenas de segundos y no depende solo de este repositorio. La
 * puerta la sigue guardando `aplicacion/tests/humo.test.tsx`, que monta la misma aplicación en jsdom y
 * corre en medio segundo. Lo que este script añade es justo lo que jsdom no es: enlaces que se pulsan,
 * peticiones que salen por un socket y un visor de PDF.
 *
 * Antes hay que tener, en dos terminales:
 *
 *     python servidor_desarrollo.py --desarrollo
 *     VITE_CAE_PRINCIPAL='{"usuario_id":…,"perfiles":[…],"tenant_id":…}' npm run dev
 *
 * Y un Chromium para Playwright (`npx playwright install chromium`, o `PLAYWRIGHT_BROWSERS_PATH`
 * apuntando a uno ya instalado).
 *
 * Es un script de Node y no un test de `vitest` por la misma razón por la que no entra en la puerta:
 * lo que comprueba no es el código de este paquete, es que dos procesos se entienden.
 */

import { chromium } from "playwright";

const FRONT = process.env["CAE_FRONT"] ?? "http://127.0.0.1:5173";

/** Lo que no debería aparecer nunca en la consola de una página que arranca bien. */
const RUIDO = ["error", "warning"];

function fallar(mensaje) {
  console.error(`✗ ${mensaje}`);
  process.exitCode = 1;
}

function bien(mensaje) {
  console.log(`✓ ${mensaje}`);
}

async function alcanzable(url) {
  try {
    const respuesta = await fetch(url, { method: "GET" });
    return respuesta.ok;
  } catch {
    return false;
  }
}

if (!(await alcanzable(FRONT))) {
  console.error(
    `no hay nada escuchando en ${FRONT}. Levanta el front (\`npm run dev\`, con VITE_CAE_PRINCIPAL) y ` +
      "el servidor (`python servidor_desarrollo.py --desarrollo`) antes de esto.",
  );
  process.exit(2);
}

const navegador = await chromium.launch();
const pagina = await navegador.newPage({ viewport: { width: 1400, height: 1100 } });

const quejas = [];
pagina.on("console", (mensaje) => {
  if (RUIDO.includes(mensaje.type())) {
    quejas.push(`${mensaje.type()}: ${mensaje.text()}`);
  }
});
pagina.on("pageerror", (fallo) => quejas.push(`pageerror: ${fallo.message}`));
pagina.on("requestfailed", (peticion) =>
  quejas.push(`requestfailed: ${peticion.url()} ${peticion.failure()?.errorText ?? ""}`),
);

try {
  // 1 · la cola se abre contra el servidor
  await pagina.goto(`${FRONT}/`, { waitUntil: "networkidle" });
  await pagina.waitForSelector("tbody tr", { timeout: 20_000 });
  const filas = await pagina.locator("tbody tr").count();
  bien(`la cola se abre con ${filas} actuación(es) servidas por HTTP`);

  // 2 · el aviso de que la autenticación es de mentira se ve, y el del servidor también
  const cuerpo = await pagina.locator("body").innerText();
  for (const frase of ["AUTENTICACIÓN DE DESARROLLO", "x-cae-principal-desarrollo"]) {
    if (!cuerpo.includes(frase)) {
      fallar(`la página no dice «${frase}»: la autenticación de mentira tiene que verse`);
    }
  }
  bien("se ve el aviso de la página y el que manda el servidor en `avisos`");

  // 3 · se navega a una actuación pulsando el enlace que compone la cola
  await pagina.getByRole("link", { name: "Revisar" }).first().click();
  await pagina.waitForSelector(".cae-revision__identificacion", { timeout: 20_000 });
  const url = pagina.url();
  if (!url.includes("#/revision/")) {
    fallar(`tras pulsar «Revisar» la dirección es ${url}`);
  }
  bien(`se navega a ${url.slice(url.indexOf("#"))}`);

  // 4 · el papel original llega y se incrusta por su huella (C17). Llega por su propia lectura, asi
  // que se espera: cuando aparece la cabecera de la actuacion, el documento todavia viene de camino.
  const visor = pagina.locator("object[type='application/pdf']").first();
  try {
    await visor.waitFor({ state: "attached", timeout: 20_000 });
    bien(`el panel del documento apunta a ${await visor.getAttribute("data")}`);
  } catch {
    fallar("la vista de revisión no ha incrustado ningún documento");
  }

  // 5 · nada de ruido en la consola
  if (quejas.length > 0) {
    fallar(`la consola del navegador no está limpia:\n  ${quejas.join("\n  ")}`);
  } else {
    bien("la consola del navegador está limpia");
  }
} finally {
  await navegador.close();
}

if (process.exitCode) {
  console.error("\ne2e en rojo");
} else {
  console.log("\ne2e en verde");
}
