/**
 * La composicion del front: el unico fichero que conoce a la vez el entorno, el transporte y el DOM.
 *
 * Mismo reparto que `servidor_desarrollo.py` hace del lado de Python: las pantallas no crean clientes
 * y no conocen ninguna URL; quien las junta con el servidor es este fichero, y solo este.
 */

import { crearCliente, type Cliente } from "@cae/compartido/api";
import "@cae/compartido/estilos.css";
import "@cae/workspace/estilos.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { Aplicacion } from "./Aplicacion";
import { BASE_API, configuracionDe } from "./configuracion";
import "./estilos.css";
import { transporteConPrincipal } from "./transporte";

const configuracion = configuracionDe(import.meta.env.VITE_CAE_PRINCIPAL);
const cliente: Cliente | null =
  configuracion.estado === "LISTA"
    ? crearCliente(transporteConPrincipal(BASE_API, configuracion.cabecera))
    : null;

const anfitrion = document.getElementById("cae-raiz");
if (anfitrion === null) {
  throw new Error("falta el elemento #cae-raiz en index.html");
}

createRoot(anfitrion).render(
  <StrictMode>
    <Aplicacion configuracion={configuracion} cliente={cliente} />
  </StrictMode>,
);
