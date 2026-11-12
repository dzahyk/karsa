"""Demo requirement extractor (rule-based, deterministic).

This is NOT a language model. It is a transparent parser used when no AI provider is configured,
so the product works offline and every behaviour is reproducible. Its limits are measured in the
Evaluation Lab.

Contract (spec AC-01, §4.6): every extracted value carries the exact quote and the character offsets
in the source text, so ``text[start:end] == quote`` always holds. When nothing is found the field is
MISSING with no source — we never invent a span. Brief text is treated as untrusted data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .catalog import BY_KEY  # frozen copy of demo-rules-1.1 (commit b84571b) for comparison only

EXTRACTOR_VERSION = "demo-rules-1.1"


@dataclass
class Span:
    start: int
    end: int
    quote: str


@dataclass
class ExtractedField:
    key: str
    state: str  # DRAFT | MISSING | CONFLICTING
    value: str | None = None
    span: Span | None = None
    note: str | None = None
    candidates: list[dict] = field(default_factory=list)  # for CONFLICTING: [{value, span}]


@dataclass
class Flag:
    kind: str  # prompt_injection | unsupported_claim
    message: str
    span: Span


@dataclass
class ExtractionResult:
    extractor: str
    fields: dict[str, ExtractedField]
    flags: list[Flag]
    action_hints: list[str]


NUM = r"\d+(?:[.,]\d+)*"
_F = re.IGNORECASE


def _span(m: re.Match, group: int | str = 0) -> Span:
    return Span(m.start(group), m.end(group), m.group(group))


def _int_from(num: str) -> int | None:
    digits = num.replace(".", "").replace(",", "")
    return int(digits) if digits.isdigit() else None


def _amount_with_unit(num: str, unit: str | None) -> int | None:
    unit = (unit or "").lower()
    mult = {"juta": 10**6, "jt": 10**6, "million": 10**6, "mn": 10**6,
            "miliar": 10**9, "milyar": 10**9, "billion": 10**9, "m": 10**9}.get(unit)
    if mult is None:
        return _int_from(num)
    # with a unit word, a single [.,] followed by 1–2 digits is a decimal separator ("1,5 miliar")
    dm = re.fullmatch(r"(\d+)(?:[.,](\d{1,2}))?", num)
    if dm:
        whole, frac = dm.group(1), dm.group(2) or ""
        return int(whole) * mult + (int(frac.ljust(len(frac), "0")) * mult // (10 ** len(frac)) if frac else 0)
    base = _int_from(num)
    return base * mult if base is not None else None


def _resolve(key: str, found: list[tuple[str, Span]], note: str | None = None) -> ExtractedField:
    if not found:
        return ExtractedField(key, "MISSING", note="Not found in the brief.")
    distinct = {v for v, _ in found}
    if len(distinct) == 1:
        value, span = found[0]
        return ExtractedField(key, "DRAFT", value, span, note)
    seen: dict[str, Span] = {}
    for v, s in found:
        seen.setdefault(v, s)
    return ExtractedField(
        key, "CONFLICTING", None, None,
        f"The brief contains {len(seen)} different values. Ask the client which one applies.",
        [{"value": v, "span": s.__dict__} for v, s in seen.items()],
    )


_EN = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
       "seventeen eighteen nineteen")
EN_UNITS = {w: i for i, w in enumerate(_EN.split())}  # noqa: SIM905
EN_TENS = {w: 10 * (i + 2) for i, w in enumerate(["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"])}
ID_UNITS = {w: i + 1 for i, w in enumerate(["satu", "dua", "tiga", "empat", "lima", "enam", "tujuh", "delapan", "sembilan"])}
NUMBER_WORD = (r"(?:" + "|".join(list(EN_UNITS) + list(EN_TENS) + list(ID_UNITS)) +
               r"|hundred|thousand|and|sepuluh|sebelas|belas|puluh|ratus|seratus|ribu|seribu|a)")
WORDS_NUM = rf"(?:{NUMBER_WORD}(?:[\s-]+{NUMBER_WORD})*)"


def words_to_int(phrase: str) -> int | None:
    """Parse English or Indonesian number words ('three thousand', 'dua ribu lima ratus')."""
    tokens = [t for t in re.split(r"[\s-]+", phrase.lower()) if t and t not in ("and", "a")]
    total = current = 0
    i = 0
    seen = False
    while i < len(tokens):
        t = tokens[i]
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if t in EN_UNITS:
            current += EN_UNITS[t]
        elif t in EN_TENS:
            current += EN_TENS[t]
        elif t in ID_UNITS and nxt in ("belas", "puluh", "ratus", "ribu"):
            current += {"belas": ID_UNITS[t] + 10, "puluh": ID_UNITS[t] * 10, "ratus": ID_UNITS[t] * 100}.get(nxt, 0)
            if nxt == "ribu":
                total += (current + ID_UNITS[t]) * 1000
                current = 0
            i += 1
        elif t in ID_UNITS:
            current += ID_UNITS[t]
        elif t == "sepuluh":
            current += 10
        elif t == "sebelas":
            current += 11
        elif t == "seratus":
            current += 100
        elif t == "seribu":
            total += 1000
        elif t == "hundred":
            current = max(current, 1) * 100
        elif t in ("thousand", "ribu"):
            total += max(current, 1) * 1000
            current = 0
        else:
            return None
        seen = True
        i += 1
    n = total + current
    return n if seen and n > 0 else None


LEADS = r"(?:qualified\s+|marketing[- ]qualified\s+)?(?:leads?\b|prospek\b|MQLs?\b)"


def _target_leads(text: str) -> ExtractedField:
    found = []
    taken: list[tuple[int, int]] = []
    rng = re.compile(rf"(?:between|antara)\s+(?P<a>{NUM})\s+(?:and|dan|to|sampai)\s+(?P<b>{NUM})\s*{LEADS}"
                     rf"|(?P<c>{NUM})\s*(?:-|–|to|sampai)\s*(?P<d>{NUM})\s*{LEADS}", _F)
    for m in rng.finditer(text):  # a range is ambiguous: surface both ends as a conflict
        for g in (("a", "b") if m.group("a") else ("c", "d")):
            n = _int_from(m.group(g))
            if n:
                found.append((str(n), _span(m, g)))
        taken.append((m.start(), m.end()))
    pat = re.compile(rf"(?P<n>{NUM})\s*{LEADS}", _F)
    for m in pat.finditer(text):
        if any(a <= m.start() < b for a, b in taken):
            continue
        n = _int_from(m.group("n"))
        if n and n > 0:
            found.append((str(n), _span(m)))
    words = re.compile(rf"\b(?P<w>{WORDS_NUM})\s+{LEADS}", _F)
    for m in words.finditer(text):
        n = words_to_int(m.group("w"))
        if n:
            found.append((str(n), _span(m)))
    return _resolve("target_leads", found)


def _budget(text: str) -> ExtractedField:
    pat = re.compile(
        rf"(?:Rp\.?|IDR)\s?(?P<n>{NUM})(?:\s*(?P<u>juta|jt|million|mn|miliar|milyar|billion|M\b))?", _F
    )
    found = []
    for m in pat.finditer(text):
        tail = text[m.end(): m.end() + 14].lower()
        if re.match(r"\s*(?:/|per\s)", tail):  # "Rp35.000 per lead" is a rate, not a budget
            continue
        amount = _amount_with_unit(m.group("n"), m.group("u"))
        if amount and amount > 0:
            found.append((str(amount), _span(m)))
    return _resolve("budget", found)


def _timeline(text: str) -> ExtractedField:
    pat = re.compile(rf"(?P<n>\d{{1,3}}|{WORDS_NUM})\s*(?P<u>weeks?|minggu|months?|bulan|days?|hari)\b", _F)
    found, notes = [], set()
    for m in pat.finditer(text):
        raw = m.group("n")
        n = int(raw) if raw.isdigit() else words_to_int(raw)
        if not n:
            continue
        unit = m.group("u").lower()
        if unit.startswith(("month", "bulan")):
            weeks = n * 4
            notes.add("Months converted to weeks at 4 weeks per month (demo assumption).")
        elif unit.startswith(("day", "hari")):
            weeks = -(-n // 7)
            notes.add("Days converted to whole weeks, rounded up (demo assumption).")
        else:
            weeks = n
        found.append((str(weeks), _span(m)))
    for m in re.finditer(r"\b(?:one|a|1|satu)\s+(?:quarter|kuartal)\b", text, _F):
        found.append(("13", _span(m)))
        notes.add("One quarter converted to 13 weeks (demo assumption).")
    return _resolve("timeline", found, " ".join(sorted(notes)) or None)


OPEN_VALUE = re.compile(
    r"^(?:tbd|tbc|n/?a|-+|open|to be (?:determined|confirmed|decided)|not (?:yet )?(?:defined|decided|confirmed)"
    r"|belum\b.*|akan dikonfirmasi.*|unknown)\.?$", _F,
)

LABELS = {
    "lead_definition": r"qualified lead definition|lead definition|definisi (?:qualified )?lead|lead criteria"
                       r"|mql criteria|kriteria lead",
    "geography": r"geography|geografi|target geography|region|wilayah|target market|lokasi",
    "target_segment": r"target segment|segment|industry|industri|target industry|target audience",
    "reporting": r"reporting|pelaporan|laporan",
    "deliverables": r"deliverables?|channels?|kanal|scope|lingkup",
    "start_date": r"start date|start|kick-?off(?: date)?|tanggal mulai|mulai",
    "constraints": r"constraints?|exclusions?|batasan|pengecualian|restrictions?",
}

PLACES = (r"Indonesia|Malaysia|Singapore|Singapura|Vietnam|Thailand|Philippines|Filipina|Brunei|Australia|Japan|"
          r"India|APAC|ASEAN|Southeast Asia|Asia Tenggara|Jakarta|Jabodetabek|Surabaya|Bandung|Medan|Bali|Java|Jawa|"
          r"Sumatra|Sumatera|Kalimantan|Sulawesi|Yogyakarta|Semarang|Makassar")
GEO_PHRASE = re.compile(rf"\b(?:{PLACES})\b(?:\s*(?:,|and|dan|&|or|atau)\s*\b(?:{PLACES})\b)*", re.IGNORECASE)
GEO_CUE = re.compile(r"\b(?:target\w*|focus\w*|in|di|across|wilayah|region|market|pasar|area|located|based)\b",
                     re.IGNORECASE)


def _geography(text: str) -> ExtractedField:
    f = _labelled(text, "geography")
    if f.state != "MISSING" or f.span is not None:
        return f
    for sentence in re.finditer(r"[^.\n]+", text):  # unlabelled: a place name in a targeting sentence
        s = sentence.group(0)
        m = GEO_PHRASE.search(s)
        if m and GEO_CUE.search(s[: m.start()]):
            start = sentence.start() + m.start()
            quote = m.group(0)
            return ExtractedField("geography", "DRAFT", quote, Span(start, start + len(quote), quote),
                                  "Found in a sentence without a label; confirm it is the target geography.")
    return f


def _start_date(text: str) -> ExtractedField:
    from .catalog import parse_date

    f = _labelled(text, "start_date")
    if f.state != "DRAFT":
        return f
    iso = parse_date(f.value or "")
    if iso is None:
        return ExtractedField("start_date", "MISSING", None, f.span,
                              "A start is mentioned but not as a recognisable date; confirm with the client.")
    f.value = iso
    return f


def _labelled(text: str, key: str) -> ExtractedField:
    pat = re.compile(rf"^[ \t\-•*]*(?:{LABELS[key]})[ \t]*[:：][ \t]*(?P<v>[^\n]+?)[ \t]*$", _F | re.MULTILINE)
    m = pat.search(text)
    if not m:
        return ExtractedField(key, "MISSING", note="Not found in the brief.")
    value = m.group("v").strip()
    span = _span(m, "v")
    if OPEN_VALUE.match(value):
        return ExtractedField(key, "MISSING", None, span, "The brief says this is still open.")
    return ExtractedField(key, "DRAFT", value, span)


def _reporting(text: str) -> ExtractedField:
    f = _labelled(text, "reporting")
    if f.state != "MISSING" or f.span is not None:
        return f
    m = re.search(r"[^.\n]*\b(?:dashboard|CRM)\b[^.\n]*", text, _F)
    if m:
        quote = m.group(0).strip()
        start = m.start() + m.group(0).index(quote)
        return ExtractedField("reporting", "DRAFT", quote, Span(start, start + len(quote), quote),
                              "Taken from a sentence that mentions dashboard/CRM; confirm wording.")
    return f


INJECTION = re.compile(
    r"ignore (?:all |any )?(?:previous|prior|above) instructions|disregard (?:the )?(?:rules|instructions)"
    r"|abaikan (?:semua )?instruksi|system prompt|you are now"
    r"|approve (?:this |it |the )?(?:proposal |request |offer )?(?:now|immediately)"
    r"|langsung setujui|auto-?approve",
    _F,
)
CLAIM = re.compile(
    r"guarantee(?:d|s)?\b[^.\n]*|dijamin[^.\n]*|menjamin[^.\n]*|\bpasti\s+(?:menghasilkan|mendapat)[^.\n]*"
    r"|\d+(?:[.,]\d+)?\s*x\s*(?:ROI|return)|ROI (?:of )?\d+\s*%|\d+\s*%\s*ROI"
    r"|(?:returned|returns?|delivered|generated|menghasilkan)\b[^.\n]{0,30}?\b(?:\d+|two|three|four|five|six|seven|"
    r"eight|nine|ten|dua|tiga|empat|lima)\s*(?:x|times|kali)\b[^.\n]*",
    _F,
)
SPEC_DOC = r"(?:spec|specification|scope document|dokumen spesifikasi|SOW|statement of work)"
ATTACH_VERB = r"(?:attach|lampirkan|lampiran|include|file[ds]?|upload|link|sertakan|simpan)"
ATTACH_SPEC = re.compile(
    rf"\b{ATTACH_VERB}\b[^.\n]{{0,60}}\b{SPEC_DOC}\b|\b{SPEC_DOC}\b[^.\n]{{0,60}}\b{ATTACH_VERB}\b", _F
)


def scan_flags(text: str) -> list[Flag]:
    flags = [Flag("prompt_injection",
                  "Instruction-like text found in the brief. It is treated as data and grants no permissions.",
                  _span(m)) for m in INJECTION.finditer(text)]
    flags += [Flag("unsupported_claim",
                   "Outcome claim without supporting data. Shown as a client claim, never as a fact.",
                   _span(m)) for m in CLAIM.finditer(text)]
    return flags


def plan_actions(text: str) -> list[str]:
    actions = ["crm.create_opportunity", "tracker.create_project"]
    if ATTACH_SPEC.search(text):
        actions.append("tracker.attach_spec")
    return actions


def extract(text: str) -> ExtractionResult:
    fields = {
        "target_leads": _target_leads(text),
        "budget": _budget(text),
        "timeline": _timeline(text),
        "lead_definition": _labelled(text, "lead_definition"),
        "geography": _geography(text),
        "target_segment": _labelled(text, "target_segment"),
        "deliverables": _labelled(text, "deliverables"),
        "start_date": _start_date(text),
        "constraints": _labelled(text, "constraints"),
        "reporting": _reporting(text),
    }
    assert set(fields) == set(BY_KEY)
    return ExtractionResult(EXTRACTOR_VERSION, fields, scan_flags(text), plan_actions(text))
