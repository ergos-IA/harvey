"""Text helpers for Spanish company names, CIFs and untrusted snippets.

Matching a company named in the BORME, an InfoJobs offer or a headline to an
account is the step most likely to go wrong, so it is deliberately strict:
names are compared after folding accents and case and dropping the legal form
("S.A.", "S.L.U.", "Sociedad Limitada"), and must then be EQUAL. A fuzzy match
that attaches another company's administrator change to an account is worse
than missing one.
"""

import re
import unicodedata

# Legal forms, written out or abbreviated, as they end a company name. Longest
# first, so "sociedad limitada unipersonal" wins over "sociedad limitada".
_LEGAL_FORMS = (
    "sociedad de responsabilidad limitada laboral",
    "sociedad de responsabilidad limitada profesional",
    "sociedad de responsabilidad limitada unipersonal",
    "sociedad de responsabilidad limitada",
    "sociedad limitada laboral",
    "sociedad limitada profesional",
    "sociedad limitada unipersonal",
    "sociedad limitada nueva empresa",
    "sociedad limitada",
    "sociedad anonima laboral",
    "sociedad anonima unipersonal",
    "sociedad anonima deportiva",
    "sociedad anonima",
    "sociedad cooperativa andaluza",
    "sociedad cooperativa",
    "sociedad comanditaria",
    "sociedad civil",
    "slne", "slu", "sll", "slp", "sl",
    "sau", "sal", "sad", "sa",
    "scoop", "scl", "sc", "sccl", "aie",
)
_LEGAL_TAIL = re.compile(
    r"(?:\s|^)(?:" + "|".join(re.escape(f) for f in _LEGAL_FORMS) + r")$")
_ZERO_WIDTH = re.compile("[​-‏⁠﻿]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def fold(text: str) -> str:
    """Lowercase, accents removed ("Ñ" → "n"), whitespace collapsed."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.lower()).strip()


def _dotted_forms(text: str) -> str:
    # "S.L.U." / "S. A." / "S.Coop." → "slu" / "sa" / "scoop", so the
    # dotted and undotted spellings strip the same way.
    return re.sub(r"\b((?:[a-z]{1,4}\.\s?){1,4})(?=\s|$|,)",
                  lambda m: m.group(1).replace(".", "").replace(" ", ""), text)


def company_key(name: str) -> str:
    """The comparable core of a company name.

    "Industrias Ejemplo, S.L." / "INDUSTRIAS EJEMPLO SL" / "Industrias
    Ejemplo Sociedad Limitada" all become "industrias ejemplo".
    """
    text = _dotted_forms(fold(name))
    text = re.sub(r"[\"'`´“”‘’()\[\]]", " ", text)
    text = re.sub(r"[,;:.]+", " ", text)
    text = re.sub(r"\s*&\s*", " y ", text)
    text = re.sub(r"[^a-z0-9ñ ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # "s l" / "s l u" / "s a" left by "S.L" (a final dot already taken as the
    # sentence's, as the BORME prints names) → "sl" / "slu" / "sa".
    text = re.sub(r"(?:^|(?<= ))(?:[a-z] ){1,3}[a-z]$", lambda m: m.group(0).replace(" ", ""), text)
    # Drop the legal form, repeatedly ("..., S.L. en liquidacion" is rare;
    # "sociedad limitada" after "s l" is not).
    text = re.sub(r"\s+en liquidacion$", "", text)
    for _ in range(3):
        stripped = _LEGAL_TAIL.sub("", text).strip()
        if stripped == text or not stripped:
            break
        text = stripped
    return text


def same_company(a: str, b: str) -> bool:
    """Do two names name the same company? Equal cores only, never a
    substring: "Ejemplo" is not "Ejemplo Logistica"."""
    ka, kb = company_key(a), company_key(b)
    return bool(ka) and len(ka) >= 3 and ka == kb


def name_in_text(name: str, text: str) -> bool:
    """Is the company's core name in ``text`` as whole words?"""
    key = company_key(name)
    if len(key) < 3:
        return False
    hay = " " + re.sub(r"[^a-z0-9ñ]+", " ", fold(text)) + " "
    return f" {key} " in hay


_CIF_RE = re.compile(r"^[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]$")


def normalize_cif(value: str) -> str:
    """"B-12.345.678" → "B12345678"; "" for anything that isn't CIF-shaped.

    Only the shape is checked (letter, seven digits, control character), not
    the control digit: a typo here costs one missed match, a strict check
    would reject legitimate older forms.
    """
    raw = re.sub(r"[\s.\-/]", "", str(value or "")).upper()
    if raw.startswith("ES") and len(raw) == 11:
        raw = raw[2:]
    return raw if _CIF_RE.match(raw) else ""


def clean_snippet(text: str, limit: int = 300) -> str:
    """Untrusted text made safe to store: tags, control and zero-width
    characters dropped, whitespace collapsed, length capped."""
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = re.sub(r"(?s)<[^>]*>", " ", text)
    text = _ZERO_WIDTH.sub("", _CONTROL.sub(" ", text))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].rstrip()


# Provinces as the BORME titles them, with the spellings people type.
_PROVINCE_ALIASES = {
    "alava": "araba", "araba alava": "araba",
    "vizcaya": "bizkaia", "biscay": "bizkaia",
    "guipuzcoa": "gipuzkoa",
    "baleares": "illes balears", "islas baleares": "illes balears", "balears": "illes balears",
    "la coruna": "a coruna", "coruna": "a coruna",
    "gerona": "girona", "lerida": "lleida", "orense": "ourense",
    "castellon de la plana": "castellon", "castello": "castellon",
    "valencia": "valencia", "valencia valencia": "valencia",
    "alacant": "alicante",
    "tenerife": "santa cruz de tenerife",
    "gran canaria": "las palmas",
}


def province_key(name: str) -> set[str]:
    """Every comparable form of a province name: "ALICANTE/ALACANT" →
    {"alicante", "alacant"}; "Vizcaya" → {"bizkaia", "vizcaya"}."""
    out = set()
    for part in re.split(r"[/()]", fold(name)):
        part = re.sub(r"[^a-z ]+", " ", part)
        part = re.sub(r"\s+", " ", part).strip()
        if not part:
            continue
        out.add(part)
        if part in _PROVINCE_ALIASES:
            out.add(_PROVINCE_ALIASES[part])
    return out


def same_province(a: str, b: str) -> bool:
    return bool(province_key(a) & province_key(b))
