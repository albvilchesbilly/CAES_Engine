"""Tests de las entidades de perfiles y capacidades (S3.1b, `ADR-006` con A8 aprobada el 19/09/2026).

Lo que se protege aqui:

1. **Las cinco entidades existen y son tontas**: inmutables, sin validar nada al construirse. Se puede
   construir una `PoliticaTenant` imposible a proposito; quien la rechaza es `validar`, no el constructor.
2. **Cada una tiene su JSON Schema versionado** y valida contra el; un campo mal puesto falla con su ruta.
3. **Ninguna entidad copia la matriz de permisos.** `engine/modelo/entidades.py` no contiene ningun `CAP-nn`
   ni ningun codigo de perfil: quien concede que es `engine/capacidades.yaml`, que es configuracion. Este es
   el test que impide que aparezca una segunda fuente el dia que alguien tenga prisa.
4. **`Parte.rol` y `actor.rol` no se mezclan**: son dos vocabularios distintos y no comparten valores.

Las listas esperadas se escriben aqui, leidas de `ADR-006`; no se importan del modulo que se prueba.
"""

from __future__ import annotations

import dataclasses
import json
import re
from datetime import date
from pathlib import Path

import pytest

from engine.modelo import (
    AMBITOS_PERFIL,
    ESQUEMA_POR_ENTIDAD,
    ESQUEMAS,
    ROLES_PARTE,
    TIPOS_CAPACIDAD,
    AsignacionPerfil,
    Capacidad,
    ErrorModelo,
    Perfil,
    PoliticaTenant,
    Tenant,
    Usuario,
    a_dict,
    validar,
)
from engine.modelo.validacion import CARPETA_ESQUEMAS

RAIZ = Path(__file__).resolve().parents[1]
FUENTE_ENTIDADES = RAIZ / "engine" / "modelo" / "entidades.py"

#: Las cinco entidades que pide `ADR-006` en "Consecuencias / Modelo canonico".
ENTIDADES_S31B = (Usuario, Perfil, Capacidad, AsignacionPerfil, PoliticaTenant)

USUARIO = Usuario(
    id="USR-001",
    nombre="Ana Revisora",
    email="ana@tenant.es",
    tenant_id="TEN-001",
    alta=date(2026, 9, 19),
)
PERFIL = Perfil(
    id="T-REV",
    nombre="Revisor tecnico",
    ambito="tenant",
    capacidades=("CAP-05", "CAP-06", "CAP-10"),
    superficie="workspace",
)
CAPACIDAD = Capacidad(
    id="CAP-10",
    nombre="Aprobar el paso a LISTA_PARA_ENVIO",
    tipo="comando",
    eventos=("RevisionAprobada",),
    proceso="P6",
)
ASIGNACION = AsignacionPerfil(
    usuario_id="USR-001",
    perfil_id="T-REV",
    desde=date(2026, 9, 19),
    tenant_id="TEN-001",
    asignado_por="USR-000",
)
POLITICA = PoliticaTenant(tenant_id="TEN-001")

EJEMPLARES = (USUARIO, PERFIL, CAPACIDAD, ASIGNACION, POLITICA)


# ---------------------------------------------------------------------------
# 1. Entidades tontas e inmutables
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entidad", ENTIDADES_S31B, ids=lambda e: e.__name__)
def test_las_cinco_entidades_son_dataclasses_inmutables(entidad: type) -> None:
    assert dataclasses.is_dataclass(entidad)
    assert entidad.__dataclass_params__.frozen, f"{entidad.__name__} tiene que ser frozen"


@pytest.mark.parametrize("ejemplar", EJEMPLARES, ids=lambda e: type(e).__name__)
def test_una_entidad_no_se_puede_modificar(ejemplar: object) -> None:
    campo = dataclasses.fields(ejemplar)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(ejemplar, campo, "otra cosa")


def test_el_constructor_no_valida_nada() -> None:
    """Construir una entidad imposible tiene que salir bien: validar es otra cosa (`ADR-004` C1)."""
    imposible = PoliticaTenant(tenant_id="", minimo_responsables=-3, version="")
    assert imposible.minimo_responsables == -3
    perfil_raro = Perfil(id="NO-EXISTE", nombre="", ambito="galactico")
    assert perfil_raro.ambito == "galactico"


def test_los_valores_por_defecto_son_los_que_recomienda_el_adr() -> None:
    """A6 es una recomendacion de `ADR-006`, no una decision de Billy: si cambia, cambia aqui y en el ADR."""
    politica = PoliticaTenant(tenant_id="TEN-001")
    assert politica.quien_prepara_puede_aprobar is True  # A6, "permitido y senalado"
    assert politica.minimo_responsables == 2  # regla de continuidad
    assert politica.acceso_soporte_permitido is True
    assert politica.vigencia_acceso_soporte_horas is None  # sin decidir: no se inventa un plazo


def test_un_usuario_global_no_tiene_tenant() -> None:
    """`ADM-MOD` y `ADM-OPS` no pertenecen a ningun tenant: el campo es opcional, no se rellena con vacio."""
    admin = Usuario(id="USR-ADM", nombre="Billy", email="billy@cae.es")
    assert admin.tenant_id is None
    validar(admin)


def test_el_tenant_referencia_a_sus_usuarios_solo_por_id() -> None:
    """`ADR-006`: el tenant referencia a sus usuarios. Solo los `id`, no el `Usuario` entero."""
    tenant = Tenant(
        id="TEN-001", tipo="delegado", razon_social="Delegado SL", nif="B00000000", usuarios=("USR-001",)
    )
    assert tenant.usuarios == ("USR-001",)
    assert all(isinstance(uid, str) for uid in tenant.usuarios)


# ---------------------------------------------------------------------------
# 2. Esquemas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entidad", ENTIDADES_S31B, ids=lambda e: e.__name__)
def test_cada_entidad_nueva_tiene_su_esquema_registrado(entidad: type) -> None:
    nombre = ESQUEMA_POR_ENTIDAD.get(entidad)
    assert nombre is not None, f"{entidad.__name__} no esta en ESQUEMA_POR_ENTIDAD"
    ruta = CARPETA_ESQUEMAS / ESQUEMAS[nombre]
    assert ruta.is_file(), f"falta el fichero {ruta.name}"
    esquema = json.loads(ruta.read_text(encoding="utf-8"))
    assert esquema["title"] == entidad.__name__
    assert esquema["additionalProperties"] is False, "un campo de mas tiene que fallar, no colarse"


@pytest.mark.parametrize("ejemplar", EJEMPLARES, ids=lambda e: type(e).__name__)
def test_los_ejemplares_validan_y_serializan_a_json_puro(ejemplar: object) -> None:
    validar(ejemplar)
    datos = a_dict(ejemplar)
    json.dumps(datos)  # sin default=: si hace falta uno, el modelo esta mal (`ADR-004` C1)


@pytest.mark.parametrize("ejemplar", EJEMPLARES, ids=lambda e: type(e).__name__)
def test_todos_los_campos_son_requeridos_en_el_esquema(ejemplar: object) -> None:
    """Un campo opcional en la dataclass sigue saliendo en el JSON (como `null`): tiene que estar declarado.

    Si no, un consumidor no sabe si el campo no existe o es que nadie lo puso.
    """
    nombre = ESQUEMA_POR_ENTIDAD[type(ejemplar)]
    esquema = json.loads((CARPETA_ESQUEMAS / ESQUEMAS[nombre]).read_text(encoding="utf-8"))
    campos = {campo.name for campo in dataclasses.fields(ejemplar)}
    assert set(esquema["required"]) == campos
    assert set(esquema["properties"]) == campos


@pytest.mark.parametrize(
    ("entidad", "cambios", "senal"),
    [
        (PERFIL, {"ambito": "galactico"}, "ambito"),
        (CAPACIDAD, {"tipo": "conjuro"}, "tipo"),
        (POLITICA, {"minimo_responsables": 0}, "minimo_responsables"),
        (POLITICA, {"tenant_id": ""}, "tenant_id"),
        (USUARIO, {"nombre": ""}, "nombre"),
        (ASIGNACION, {"desde": "19/09/2026"}, "desde"),
    ],
    ids=["ambito", "tipo", "minimo", "tenant_vacio", "nombre_vacio", "fecha"],
)
def test_una_entidad_mal_formada_falla_con_la_ruta_del_campo(
    entidad: object, cambios: dict, senal: str
) -> None:
    with pytest.raises(ErrorModelo) as fallo:
        validar(dataclasses.replace(entidad, **cambios))
    assert senal in str(fallo.value), fallo.value


def test_un_campo_de_mas_no_se_cuela() -> None:
    from engine.modelo import validar_documento

    datos = a_dict(POLITICA) | {"puede_forzar_veredicto": True}
    with pytest.raises(ErrorModelo, match="no permitido"):
        validar_documento(datos, "politica_tenant")


# ---------------------------------------------------------------------------
# 3. El modelo no copia la matriz
# ---------------------------------------------------------------------------


def test_las_entidades_no_llevan_dentro_la_matriz_de_permisos() -> None:
    """Regla de oro 4 aplicada a los permisos: ni un `CAP-nn` ni un codigo de perfil en el fuente.

    Se descuentan los comentarios y las docstrings, que citan ejemplos para explicar de donde sale un campo;
    lo que no puede haber es un literal en una expresion.
    """
    codigo = FUENTE_ENTIDADES.read_text(encoding="utf-8")
    sin_docstrings = re.sub(r'"""(?:.|\n)*?"""', "", codigo)
    sin_comentarios = re.sub(r"#.*", "", sin_docstrings)
    assert not re.search(r"CAP-\d", sin_comentarios), "hay un CAP-nn en engine/modelo/entidades.py"
    for perfil in ("T-RES", "T-OPE", "T-REV", "EXT-INS", "EXT-CLI", "ADM-MOD", "ADM-OPS", "SYS-API"):
        assert perfil not in sin_comentarios, f"{perfil} esta escrito en engine/modelo/entidades.py"


def test_el_enumerado_de_perfil_solo_fija_el_ambito_no_los_perfiles() -> None:
    """`Perfil.id` no lleva enumerado a proposito: la lista de perfiles es configuracion."""
    esquema = json.loads((CARPETA_ESQUEMAS / ESQUEMAS["perfil"]).read_text(encoding="utf-8"))
    assert "enum" not in esquema["properties"]["id"]
    assert tuple(esquema["properties"]["ambito"]["enum"]) == AMBITOS_PERFIL


def test_los_ambitos_y_tipos_son_los_de_los_adr() -> None:
    assert AMBITOS_PERFIL == ("tenant", "externo", "global", "sistema")  # `ADR-006`, tabla de perfiles
    assert TIPOS_CAPACIDAD == ("comando", "lectura")  # `ADR-011` §2


# ---------------------------------------------------------------------------
# 4. Dos vocabularios distintos
# ---------------------------------------------------------------------------


def test_el_rol_de_una_parte_y_el_rol_de_un_actor_no_comparten_valores() -> None:
    """`Parte.rol` dice que pinta una empresa; `actor.rol` es el perfil con el que actua una persona.

    Si un dia se cruzaran, un instalador (parte) pasaria por un perfil de la plataforma. No se cruzan.
    """
    assert set(ROLES_PARTE).isdisjoint(set(AMBITOS_PERFIL))
    for rol in ROLES_PARTE:
        assert not rol.startswith(("T-", "EXT-", "ADM-", "SYS-"))
