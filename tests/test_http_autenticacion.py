"""Contratos C28 y C29 (`ADR-015` §4): el puerto del principal, y la pieza que no puede salir de local.

Todo el aislamiento por tenant descansa en que el `Principal` sea verdadero, asi que lo que se comprueba
aqui no es comodidad de uso: es que **no hay forma de obtener un principal sin haberlo declarado**, que el
valor por defecto del servidor deniega, y que el autenticador de desarrollo se niega a construirse sin una
senal explicita que nadie pone por descuido.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

pytest.importorskip("starlette", reason="`FR-HTTP` es un extra: pip install -e '.[http]'")

from api.http.autenticacion import (  # noqa: E402
    ANFITRIONES_LOCALES,
    AVISO_DESARROLLO,
    CABECERA_PRINCIPAL,
    CONFIRMACION_DESARROLLO,
    AutenticadorAusente,
    AutenticadorDeDesarrollo,
    ErrorArranque,
    ErrorAutenticacion,
)
from api.permisos import ErrorPermiso, Principal  # noqa: E402


@dataclass
class ClienteFalso:
    host: str


@dataclass
class PeticionFalsa:
    """Lo unico que el autenticador mira de una peticion: sus cabeceras y de donde viene."""

    headers: dict[str, str]
    client: ClienteFalso | None = None


def _peticion(principal: object = None, *, desde: str = "127.0.0.1") -> PeticionFalsa:
    cabeceras = {} if principal is None else {CABECERA_PRINCIPAL: json.dumps(principal)}
    return PeticionFalsa(headers=cabeceras, client=ClienteFalso(desde))


def _de_desarrollo() -> AutenticadorDeDesarrollo:
    return AutenticadorDeDesarrollo(confirmacion=CONFIRMACION_DESARROLLO, anfitrion="127.0.0.1")


# ---------------------------------------------------------------------------
# C28 · el puerto
# ---------------------------------------------------------------------------


class TestElPuerto:
    def test_el_ausente_es_un_autenticador_y_deniega_todo(self) -> None:
        ausente = AutenticadorAusente()

        assert callable(ausente.principal)
        with pytest.raises(ErrorAutenticacion, match="no hay autenticador configurado"):
            ausente.principal(_peticion({"usuario_id": "u", "perfiles": ["T-REV"]}))

    def test_el_ausente_cita_el_adr_que_explica_por_que(self) -> None:
        with pytest.raises(ErrorAutenticacion, match="ADR-015"):
            AutenticadorAusente().principal(_peticion())

    def test_una_denegacion_de_autenticacion_es_una_denegacion(self) -> None:
        """Hereda de `ErrorPermiso` para que el sobre tenga las dos salidas que declara, y no tres."""
        assert issubclass(ErrorAutenticacion, ErrorPermiso)

    def test_el_puerto_declara_avisos(self) -> None:
        """Sin `avisos` no hay forma de que una autenticacion de mentira lo diga en la pantalla."""
        assert AutenticadorAusente().avisos == ()
        assert _de_desarrollo().avisos == (AVISO_DESARROLLO,)


# ---------------------------------------------------------------------------
# C29 · la de desarrollo no se instancia sin la senal
# ---------------------------------------------------------------------------


class TestNoSeInstanciaSinLaSenal:
    def test_sin_argumentos_no_se_construye(self) -> None:
        with pytest.raises(TypeError):
            AutenticadorDeDesarrollo()  # type: ignore[call-arg]

    def test_sin_la_confirmacion_no_se_construye(self) -> None:
        with pytest.raises(ErrorArranque, match="no se construye sin decir"):
            AutenticadorDeDesarrollo(confirmacion="", anfitrion="127.0.0.1")

    @pytest.mark.parametrize("casi", ["si", "true", "1", "desarrollo", CONFIRMACION_DESARROLLO.upper()])
    def test_ni_con_algo_parecido(self, casi: str) -> None:
        """La senal es una sola cadena, no un booleano: un `True` se pone sin leerlo, esto no."""
        with pytest.raises(ErrorArranque):
            AutenticadorDeDesarrollo(confirmacion=casi, anfitrion="127.0.0.1")

    @pytest.mark.parametrize("fuera", ["0.0.0.0", "10.0.0.7", "cae.example.com", "", "::"])
    def test_fuera_del_bucle_local_no_se_construye(self, fuera: str) -> None:
        with pytest.raises(ErrorArranque, match="bucle local"):
            AutenticadorDeDesarrollo(confirmacion=CONFIRMACION_DESARROLLO, anfitrion=fuera)

    @pytest.mark.parametrize("local", sorted(ANFITRIONES_LOCALES))
    def test_en_el_bucle_local_si(self, local: str) -> None:
        assert AutenticadorDeDesarrollo(confirmacion=CONFIRMACION_DESARROLLO, anfitrion=local)


# ---------------------------------------------------------------------------
# C28 · nunca `None`, nunca anonimo
# ---------------------------------------------------------------------------


class TestNuncaUnPrincipalVacio:
    def test_el_principal_declarado_se_construye_tal_cual(self) -> None:
        quien = _de_desarrollo().principal(
            _peticion({"usuario_id": "u-rev", "perfiles": ["T-REV"], "tenant_id": "T-001"})
        )

        assert quien == Principal("u-rev", ("T-REV",), "T-001")

    @pytest.mark.parametrize(
        "declarado",
        [
            None,
            {},
            {"perfiles": ["T-REV"]},
            {"usuario_id": "u", "perfiles": []},
            {"usuario_id": "u", "perfiles": "T-REV"},
            {"usuario_id": "u", "perfiles": ["T-REV", "T-REV"]},
            {"usuario_id": "u", "perfiles": [1]},
            {"usuario_id": "", "perfiles": ["T-REV"]},
            {"usuario_id": "u", "perfiles": ["T-REV"], "tenant_id": 7},
            ["u", ["T-REV"]],
        ],
    )
    def test_lo_que_no_es_un_principal_levanta_en_vez_de_devolver_algo(self, declarado: object) -> None:
        with pytest.raises(ErrorAutenticacion):
            _de_desarrollo().principal(_peticion(declarado))

    def test_una_cabecera_que_no_es_json_levanta(self) -> None:
        with pytest.raises(ErrorAutenticacion, match="no es JSON"):
            _de_desarrollo().principal(PeticionFalsa(headers={CABECERA_PRINCIPAL: "{u-rev"}))

    def test_nunca_devuelve_none(self) -> None:
        """La garantia entera del puerto, dicha como la dice el contrato: o `Principal`, o levanta."""
        autenticador = _de_desarrollo()
        intentos = [
            _peticion(),
            _peticion({}),
            _peticion({"usuario_id": "u-rev", "perfiles": ["T-REV"], "tenant_id": "T-001"}),
        ]

        obtenidos = []
        for intento in intentos:
            try:
                obtenidos.append(autenticador.principal(intento))
            except ErrorAutenticacion:
                continue
        assert obtenidos and all(isinstance(quien, Principal) for quien in obtenidos)

    def test_una_peticion_que_no_viene_del_bucle_local_se_deniega(self) -> None:
        """Segunda barrera: aunque alguien lo ponga detras de algo, no atiende a quien no es local."""
        with pytest.raises(ErrorAutenticacion, match="bucle local"):
            _de_desarrollo().principal(
                _peticion({"usuario_id": "u", "perfiles": ["T-REV"]}, desde="10.0.0.7")
            )
