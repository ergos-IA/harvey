"""BORME acts from the BOE open-data API, matched to tracked accounts.

The summary and section shapes follow the BOE API (checked October 2026);
the companies, people and acts are fictional.
"""

from datetime import date

import httpx
import pytest

from harvey.collectors.spain.borme import (
    classify, collect_borme, parse_section_xml, parse_sumario, recent_days, split_acts,
)

SUMARIO = {"status": {"code": "200", "text": "ok"}, "data": {"sumario": {
    "metadatos": {"publicacion": "BORME", "fecha_publicacion": "20261023"},
    "diario": [{"numero": "205", "seccion": [
        {"codigo": "A", "nombre": "SECCIÓN PRIMERA. Empresarios. Actos inscritos", "item": [
            {"identificador": "BORME-A-2026-205-50", "titulo": "ZARAGOZA",
             "url_pdf": {"texto": "https://www.boe.es/borme/dias/2026/10/23/pdfs/BORME-A-2026-205-50.pdf"},
             "url_html": "https://www.boe.es/diario_borme/txt.php?id=BORME-A-2026-205-50",
             "url_xml": "https://www.boe.es/diario_borme/xml.php?id=BORME-A-2026-205-50"},
            {"identificador": "BORME-A-2026-205-28", "titulo": "MADRID",
             "url_pdf": {"texto": "https://www.boe.es/borme/dias/2026/10/23/pdfs/BORME-A-2026-205-28.pdf"},
             "url_html": "https://www.boe.es/diario_borme/txt.php?id=BORME-A-2026-205-28",
             "url_xml": "https://www.boe.es/diario_borme/xml.php?id=BORME-A-2026-205-28"},
        ]},
        # Section C is announcements, not acts: ignored. A single item is a dict.
        {"codigo": "C", "item": {"identificador": "BORME-C-2026-1", "titulo": "x",
                                 "url_xml": "https://www.boe.es/x"}},
    ]}]}}}

SECTION_XML = """<?xml version="1.0" encoding="UTF-8"?>
<documento><metadatos><identificador>BORME-A-2026-205-50</identificador></metadatos><texto>
<p class="articulo">900001 - INDUSTRIAS EJEMPLO SL.</p>
<p class="parrafo">Ceses/Dimisiones. Adm. Unico: PRUEBA PRUEBA ANA. Nombramientos. Apoderado: EJEMPLO
EJEMPLO LUIS. Adm. Unico: FICTICIO FICTICIO JUAN. Datos registrales. T 100 , F 1, S 8, H Z 1, I/A 5 (16.10.26).</p>
<p class="articulo">900002 - DISTRIBUCIONES PRUEBA SOCIEDAD ANONIMA.</p>
<p class="parrafo">Nombramientos. Apoderado: OTRO OTRO PEDRO. Ampliación de capital. Capital: 120.000,00 Euros.
Resultante Suscrito: 900.000,00 Euros. Datos registrales. T 200 , F 2, S 8, H Z 2, I/A 9 (16.10.26).</p>
<p class="articulo">900003 - TALLERES MUESTRA, S.L.</p>
<p class="parrafo">Fusión por absorción. Sociedades absorbidas: MUESTRA AUXILIAR SL. Datos registrales. T 3 (16.10.26).</p>
<p class="articulo">900004 - INDUSTRIAS EJEMPLO NORTE SL.</p>
<p class="parrafo">Nombramientos. Adm. Unico: ALGUIEN ALGUIEN EVA. Datos registrales. T 4 (16.10.26).</p>
<p class="articulo">900005 - CONSTRUCCIONES MODELO SL.</p>
<p class="parrafo">Declaración de unipersonalidad. Socio único: GRUPO MODELO SL. Otros conceptos: Cambio del Organo
de Administración. Datos registrales. T 5 (16.10.26).</p>
</texto></documento>""".encode()


def test_parse_sumario_section_a_only():
    items = parse_sumario(SUMARIO)
    assert [(i["province"], i["id"]) for i in items] == [
        ("ZARAGOZA", "BORME-A-2026-205-50"), ("MADRID", "BORME-A-2026-205-28")]
    assert parse_sumario({"data": None}) == [] and parse_sumario([]) == []


def test_acts_split_and_classify():
    acts = parse_section_xml(SECTION_XML)
    assert [a.name for a in acts] == ["INDUSTRIAS EJEMPLO SL", "DISTRIBUCIONES PRUEBA SOCIEDAD ANONIMA",
                                      "TALLERES MUESTRA, S.L", "INDUSTRIAS EJEMPLO NORTE SL",
                                      "CONSTRUCCIONES MODELO SL"]
    first = classify(acts[0])
    assert set(first) == {"BORME_APPOINTMENT"}
    assert "Ceses/Dimisiones. Adm. Unico" in first["BORME_APPOINTMENT"]
    assert "Datos registrales" not in first["BORME_APPOINTMENT"]
    # Only a new proxy (apoderado) is not a change at the top; the capital increase is.
    assert set(classify(acts[1])) == {"BORME_CAPITAL"}
    assert classify(acts[1])["BORME_CAPITAL"].startswith("Ampliación de capital")
    assert set(classify(acts[2])) == {"BORME_MERGER"}
    assert set(classify(acts[4])) == {"BORME_CAPITAL"}


def test_a_new_companys_first_administrator_is_not_a_change():
    from harvey.collectors.spain.borme import Act
    text = ("Constitución. Comienzo de operaciones: 1.10.26. Objeto social: Fabricación. Capital: 3.000,00 "
            "Euros. Nombramientos. Adm. Unico: NUEVO NUEVO ANA. Datos registrales. T 1 (16.10.26).")
    act = Act(number="1", name="NUEVA EJEMPLO SL", text=text, segments=split_acts(text))
    assert classify(act) == {}


def test_split_acts_keeps_original_text():
    segs = split_acts("Nombramientos. Adm. Unico: ÑÚÑEZ X. Ampliación de capital. Capital: 1 Euros.")
    assert segs == [("nombramientos", "Nombramientos. Adm. Unico: ÑÚÑEZ X."),
                    ("ampliacion de capital", "Ampliación de capital. Capital: 1 Euros.")]


def test_entity_declarations_are_refused():
    assert parse_section_xml(b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "x">]><documento/>') == []


def test_recent_days_are_weekdays():
    # 2026-10-26 is a Monday: the three days back are Mon, (Sun, Sat skipped).
    assert recent_days(3, today=date(2026, 10, 26)) == [date(2026, 10, 26)]
    assert len(recent_days(7, today=date(2026, 10, 26))) == 5


ACCOUNTS = [
    {"id": "c1", "name": "Industrias Ejemplo", "legal_name": "", "domain": "industrias-ejemplo.example",
     "province": "Zaragoza"},
    {"id": "c2", "name": "Prueba Distribución", "legal_name": "Distribuciones Prueba, S.A.",
     "domain": "prueba.example", "province": "Zaragoza"},
    {"id": "c3", "name": "Talleres Muestra SL", "legal_name": "", "domain": "muestra.test", "province": ""},
]


def _boe(requests):
    def handler(request):
        url = str(request.url)
        requests.append(url)
        if "/api/borme/sumario/20261023" in url:
            assert request.headers["accept"] == "application/json"
            return httpx.Response(200, json=SUMARIO)
        if url.endswith("BORME-A-2026-205-50"):
            return httpx.Response(200, content=SECTION_XML, headers={"content-type": "application/xml"})
        return httpx.Response(404, text="")
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_collect_reads_only_tracked_provinces_and_matches_strictly():
    seen = []
    async with _boe(seen) as client:
        report = await collect_borme(ACCOUNTS, client, days=1, today=date(2026, 10, 23), pause=0)
    # One summary, one province (Zaragoza); Madrid isn't read.
    assert [u for u in seen if "xml.php" in u] == [
        "https://www.boe.es/diario_borme/xml.php?id=BORME-A-2026-205-50"]
    got = sorted((o["company_id"], o["signal_code"]) for o in report.observations)
    # c1 matches "INDUSTRIAS EJEMPLO SL" (not "... NORTE SL"); c2 by its legal
    # name; c3 has no province, but Zaragoza was read anyway and it matches.
    assert got == [("c1", "BORME_APPOINTMENT"), ("c2", "BORME_CAPITAL"), ("c3", "BORME_MERGER")]
    appointment = next(o for o in report.observations if o["company_id"] == "c1")
    assert appointment["value_text"].startswith("2026-10-23 · Ceses/Dimisiones.")
    assert appointment["evidence_url"] == "https://www.boe.es/diario_borme/txt.php?id=BORME-A-2026-205-50"
    assert appointment["collector"] == "borme"
    assert report.no_province == 1 and report.documents == 1 and report.entries == 5


@pytest.mark.asyncio
async def test_unwanted_codes_and_no_provinces_read_nothing():
    seen = []
    async with _boe(seen) as client:
        report = await collect_borme(ACCOUNTS, client, days=1, today=date(2026, 10, 23),
                                     wanted={"BORME_MERGER"}, pause=0)
        assert {o["signal_code"] for o in report.observations} == {"BORME_MERGER"}
        nothing = await collect_borme([dict(ACCOUNTS[2])], client, days=1, today=date(2026, 10, 23), pause=0)
    assert nothing.observations == [] and nothing.no_province == 1
