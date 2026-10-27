"""Who decides at a Spanish company, read off its own site.

Fictional markup only: accented names, Spanish job titles, Spanish menus.
"""

import pytest

from harvey.collectors import people
from harvey.collectors.profile import ProfileCollector, title_looks_like_role

detect_people = ProfileCollector(state=None).detect_people


def names(found):
    return [(p["first_name"], p["last_name"]) for p in found]


@pytest.mark.parametrize("text, expected", [
    ("José Martínez", ("José", "Martínez")),
    ("Ángela Núñez Peña", ("Ángela", "Peña")),
    ("María de la Fuente", ("María", "de la Fuente")),
    ("Íñigo Ibáñez", ("Íñigo", "Ibáñez")),
])
def test_accented_names_are_people(text, expected):
    assert people.split_person_name(text) == expected


@pytest.mark.parametrize("text", [
    "Nuestro Equipo", "Quiénes Somos", "Atención Cliente", "Dirección Comercial",
])
def test_spanish_headings_are_not_people(text):
    assert not people.is_person_name(text)


@pytest.mark.parametrize("title", [
    "Gerente", "Consejero Delegado", "Fundadora", "Directora Comercial",
    "Responsable de Oficina Técnica", "Jefe de Ventas", "Presidenta",
])
def test_spanish_titles_read_as_roles(title):
    assert title_looks_like_role(title)


@pytest.mark.parametrize("title, owner", [
    ("Gerente", True), ("Consejera Delegada", True), ("Fundador y CEO", True),
    ("Propietario", True), ("Administrador Único", True),
    ("Vicepresidente", False), ("Adjunta a Gerencia", False), ("Jefe de Ventas", False),
])
def test_spanish_owner_titles(title, owner):
    assert people.is_owner_title(title) is owner


EQUIPO = """
<h2>Nuestro Equipo</h2>
<h3>Lucía Herrero</h3><p>Responsable de Oficina Técnica</p>
<h3>Andrés Gómez</h3><p>Gerente</p>
"""


def test_the_gerente_ranks_first():
    found = people.find_people([("https://fabrica.test/equipo", EQUIPO)], "fabrica.test")
    assert names(found)[0] == ("Andrés", "Gómez")
    assert ("Lucía", "Herrero") in names(found)


def test_spanish_cards_are_detected():
    found = detect_people(EQUIPO, domain="fabrica.test")
    assert ("Andrés", "Gómez") in names(found)


def test_spanish_menu_links_are_scored():
    home = """<nav><a href="/productos/">Productos</a>
      <a href="/quienes-somos/">Quiénes somos</a>
      <a href="/contacto/">Contacto</a>
      <a href="/noticias/feria/">Noticias</a>
      <a href="/equipo/">Equipo</a></nav>"""
    assert people.menu_links(home, "https://fabrica.test/") == [
        "https://fabrica.test/equipo/",
        "https://fabrica.test/quienes-somos/",
        "https://fabrica.test/contacto/",
    ]
