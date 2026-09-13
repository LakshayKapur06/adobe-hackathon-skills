"""HTML extraction with html.parser only. Standard library only.

One parser serves both layers: the server response and, when a browser is
available, the rendered DOM. Every value produced here is a measurement of the
document. Nothing is interpreted, and nothing in the document can change what
this module does: text is counted and hashed, never read as an instruction.
"""

import datetime
import hashlib
import json
import re
from html.parser import HTMLParser

import urls

LINK_CAP = 500
IMAGE_CAP = 200
EXCERPT_CHARS = 500              # well inside the 2000-character contract cap
JSONLD_VALUES_CAP_BYTES = 4096

VOID = frozenset("area base br col embed hr img input link meta param source track wbr keygen".split())
SKIP_TEXT = frozenset({"script", "style", "template", "svg", "math", "head", "title"})
BLOCK = frozenset("""address article aside blockquote caption dd details dialog div dl dt
    fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6 header hr legend li main nav
    ol option p pre section summary table tbody td tfoot th thead tr ul""".split())
HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
P_CLOSERS = frozenset("""address article aside blockquote details div dl fieldset figure
    footer form h1 h2 h3 h4 h5 h6 header hr main nav ol p pre section table ul""".split())
ANCHOR_CONTAINERS = frozenset({"section", "article"})
BOILERPLATE_ROLES = frozenset({"navigation", "banner", "contentinfo", "complementary"})
# Consent-manager interfaces. A cookie banner or consent wall is injected into
# the page by script on almost every European site, often with a partner list
# tens of thousands of characters long, and it is not the page's content. Read
# as text, it made a server-rendered article look JavaScript-dependent: one
# publisher's consent wall added 31,188 identical characters to every rendered
# page. Its text is excluded from both the server response and the rendered
# DOM, so the comparison stays symmetric. Matched on id and class tokens: a
# consent-specific token alone, or "cookie" together with a banner-like token,
# so a "cookie-recipes" section on a bakery's site keeps its text.
_CONSENT_TOKENS = frozenset({"gdpr", "consent", "cmp", "tcf", "didomi", "onetrust", "optanon", "cookiebot",
                             "cybotcookiebotdialog", "usercentrics", "truste", "trustarc", "iubenda", "osano",
                             "cmplz", "axeptio", "quantcast", "cookieyes", "termly", "borlabs", "klaro",
                             "cookielaw", "cookieconsent"})
_COOKIE_COMPANIONS = frozenset({"banner", "notice", "bar", "wall", "popup", "modal", "dialog", "law", "overlay",
                                "prompt", "message", "settings", "preferences"})
_NEVER_CONSENT = frozenset({"html", "body", "main", "article", "head"})


def _is_consent_ui(tag, attrs):
    if tag in _NEVER_CONSENT:
        return False
    tokens = set(re.split(r"[^a-z0-9]+", ("%s %s" % (attrs.get("id") or "", attrs.get("class") or "")).lower()))
    tokens.discard("")
    if tokens & _CONSENT_TOKENS:
        return True
    return any(t.startswith("cookie") for t in tokens) and bool(tokens & _COOKIE_COMPANIONS)

TEXT_IMAGE_HINTS = ("spec", "chart", "infographic", "table", "menu", "price", "pricing",
                    "diagram", "size-guide", "sizeguide", "size_chart", "comparison",
                    "timetable", "schedule")
OBSTRUCTION_MARKERS = {
    "cookie_wall": ("onetrust", "cookiebot", "cookie-consent", "cookieconsent", "cookie-banner",
                    "cookie-wall", "cookiewall", "cc-banner", "didomi", "usercentrics",
                    "trustarc", "qc-cmp", "cmp-container"),
    "paywall": ("paywall", "pay-wall", "metered-content", "subscriber-only"),
    "age_gate": ("age-gate", "agegate", "age-verification", "age_verification", "age-check"),
}
COOKIE_SCRIPT_HOSTS = ("cookielaw.org", "onetrust.com", "cookiebot.com", "consensu.org",
                       "didomi.io", "usercentrics.eu", "trustarc.com")

_MONTHS = {m: i for i, m in enumerate(
    "january february march april may june july august september october november december".split(), 1)}
_MONTH_ALT = "|".join(sorted(set(list(_MONTHS) + [m[:3] for m in _MONTHS] + ["sept"]), key=len, reverse=True))
_ISO_DATE = re.compile(r"\b((?:19|20)\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b")
_DMY = re.compile(r"\b([0-3]?\d)(?:st|nd|rd|th)?\s+(%s)\.?,?\s+((?:19|20)\d{2})\b" % _MONTH_ALT, re.I)
# Numeric dates. Day-first and month-first cannot be told apart when both parts
# are 12 or less; those are read day-first, as most of the world writes them.
# No rule relies on which day such a date names, only on a date being shown.
_NUMERIC_DATE = re.compile(r"(?<![\d./-])([0-3]?\d)([/.])([0-3]?\d)\2((?:19|20)\d{2})(?!\d|[./-]\d)")
_YMD_SLASH = re.compile(r"(?<![\d./-])((?:19|20)\d{2})([/.])(0?[1-9]|1[0-2])\2([0-3]?\d)(?!\d|[./-]\d)")
_TIME_DATETIME = re.compile(r"^\s*((?:19|20)\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")
_MDY = re.compile(r"\b(%s)\.?\s+([0-3]?\d)(?:st|nd|rd|th)?,?\s+((?:19|20)\d{2})\b" % _MONTH_ALT, re.I)
# The amount after a currency sign, with either grouping convention: 1,499.00
# and 1.499,00 both reach _readings, which tries each.
_CURRENCY_AMOUNT = re.compile(
    r"([$€£¥₹]|\bRs\.?|\bINR|\bUSD|\bEUR|\bGBP)\s?(\d(?:[\d.,]*\d)?)")
# The ISO 4217 codes each written sign can stand for. "$" is many currencies, so
# it matches any of them; an amount is compared with a marked-up price only when
# its sign can denote the currency the markup declares.
_SIGN_CURRENCIES = {
    "$": {"USD", "CAD", "AUD", "NZD", "SGD", "HKD", "TWD", "MXN", "ARS", "CLP", "COP", "BRL"},
    "€": {"EUR"}, "£": {"GBP"}, "¥": {"JPY", "CNY"}, "₹": {"INR"},
    "RS": {"INR", "PKR", "LKR", "NPR"}, "RS.": {"INR", "PKR", "LKR", "NPR"},
    "INR": {"INR"}, "USD": {"USD"}, "EUR": {"EUR"}, "GBP": {"GBP"},
}
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _norm_space(value):
    return " ".join(value.split())


class _Parser(HTMLParser):
    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.stack = []
        self.stream = []
        self.boiler_chars = 0
        self.total_chars = 0
        self.headings = []
        self.anchors = []
        self.links = []
        self.link_total = 0
        self.resolved_links = []
        self.images = []
        self.image_total = 0
        self.tables = self.iframes = self.forms = 0
        self.meta_robots = []
        self.canonical = None
        self.lang = None
        self.hreflang = []
        self.jsonld_scripts = []
        self.microdata_or_rdfa = False
        self.obstructions = {}
        # Text inside elements the markup hides (the hidden attribute or an
        # inline display:none). It is not visible text, so it never enters the
        # page text or its length, but a fetcher that ignores CSS extracts it,
        # so its size is recorded separately rather than lost.
        self.hidden_chars = 0
        # Dates from the datetime attribute of visible <time> elements, which
        # often show only "Sep 12" or "2 hours ago" as text.
        self.time_dates = []
        self._jsonld_buf = None
        self._open_link = None

    # -- stack helpers ---------------------------------------------------
    def _skipping(self):
        return any(e["skip"] for e in self.stack)

    def _never_text(self):
        return any(e["never_text"] for e in self.stack)

    def _in_boilerplate(self):
        return any(e["boiler"] for e in self.stack)

    def _push(self, tag, attrs):
        style = (attrs.get("style") or "").replace(" ", "").lower()
        hidden = "hidden" in attrs or "display:none" in style
        role = (attrs.get("role") or "").lower()
        page_level = not any(e["tag"] in ("article", "main", "section") for e in self.stack)
        boiler = role in BOILERPLATE_ROLES or tag in ("nav", "aside") or (
            tag in ("header", "footer") and page_level)
        consent = _is_consent_ui(tag, attrs)
        self.stack.append({
            "tag": tag, "id": attrs.get("id"), "paired": False,
            "skip": tag in SKIP_TEXT or hidden or consent, "never_text": tag in SKIP_TEXT or consent,
            "boiler": boiler,
            "heading": [] if tag in HEADINGS else None,
        })

    def _pop_to(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                while len(self.stack) > index:
                    self._close(self.stack.pop())
                return

    def _close(self, element):
        tag = element["tag"]
        if tag in BLOCK:
            self.stream.append("\n")
        if element["heading"] is not None and not element["skip"] and not self._skipping():
            text = _norm_space("".join(element["heading"]))
            self.headings.append({"level": int(tag[1]), "text": text})
            if element["id"]:
                self.anchors.append({"id": element["id"], "heading_text": text})
            for ancestor in reversed(self.stack):
                if ancestor["tag"] in ANCHOR_CONTAINERS and ancestor["id"] and not ancestor["paired"]:
                    ancestor["paired"] = True
                    self.anchors.append({"id": ancestor["id"], "heading_text": text})
                    break
        if tag == "a" and self._open_link is not None:
            self._finish_link()

    def _implicit_close(self, tag):
        if tag in P_CLOSERS and self.stack and self.stack[-1]["tag"] == "p":
            self._close(self.stack.pop())
        stops = {"li": ("ul", "ol"), "dt": ("dl",), "dd": ("dl",), "tr": ("table",),
                 "td": ("tr", "table"), "th": ("tr", "table"), "option": ("select",)}
        if tag in stops:
            siblings = {"dt": ("dt", "dd"), "dd": ("dt", "dd"), "td": ("td", "th"),
                        "th": ("td", "th")}.get(tag, (tag,))
            for index in range(len(self.stack) - 1, -1, -1):
                current = self.stack[index]["tag"]
                if current in stops[tag]:
                    return
                if current in siblings:
                    self._pop_to(current)
                    return

    # -- links -------------------------------------------------------------
    def _finish_link(self):
        link, self._open_link = self._open_link, None
        anchor = _norm_space("".join(link["text"])) or link["label"]
        self.link_total += 1
        if len(self.links) < LINK_CAP:
            self.links.append({"href": link["href"], "rel": link["rel"],
                               "anchor": anchor, "internal": link["internal"]})

    # -- parser callbacks ----------------------------------------------------
    def handle_starttag(self, tag, attr_list):
        attrs = {k.lower(): (v if v is not None else "") for k, v in attr_list}
        if "itemscope" in attrs or "itemtype" in attrs or "typeof" in attrs or "vocab" in attrs:
            self.microdata_or_rdfa = True
        self._scan_obstruction(tag, attrs)

        if tag == "html" and attrs.get("lang") and self.lang is None:
            self.lang = attrs["lang"].strip()
        elif tag == "base" and attrs.get("href"):
            self.base_url = urls.normalise(attrs["href"], self.base_url) or self.base_url
        elif tag == "meta":
            if (attrs.get("name") or "").lower() == "robots":
                self.meta_robots.extend(t.strip().lower() for t in (attrs.get("content") or "").split(",") if t.strip())
        elif tag == "link":
            rel = (attrs.get("rel") or "").lower().split()
            if "canonical" in rel and attrs.get("href") and self.canonical is None:
                self.canonical = urls.normalise(attrs["href"], self.base_url)
            if "alternate" in rel and attrs.get("hreflang"):
                self.hreflang.append(attrs["hreflang"].strip())
        elif tag == "script" and (attrs.get("type") or "").lower().strip() == "application/ld+json":
            self._jsonld_buf = []
        elif tag == "table":
            self.tables += 1
        elif tag == "iframe":
            self.iframes += 1
        elif tag == "form":
            self.forms += 1
        elif tag == "img" and not self._skipping():
            src = attrs.get("src") or attrs.get("data-src") or ""
            if src:
                self.image_total += 1
                if len(self.images) < IMAGE_CAP:
                    alt = attrs["alt"] if "alt" in attrs else None
                    hint = (src.rsplit("/", 1)[-1] + " " + (alt or "")).lower()
                    self.images.append({"src": src, "alt": alt,
                                        "text_likely": any(h in hint for h in TEXT_IMAGE_HINTS)})
        elif tag == "br":
            self.stream.append(" ")
        elif tag == "time" and not self._skipping() and "hidden" not in attrs:
            match = _TIME_DATETIME.match(attrs.get("datetime") or "")
            if match:
                self.time_dates.append("%s-%s-%s" % match.groups())

        if tag == "a" and attrs.get("href") is not None and not self._skipping():
            if self._open_link is not None:
                self._finish_link()
            resolved = urls.normalise(attrs["href"], self.base_url)
            if resolved is not None:
                page_domain = urls.registrable_domain(urls.host(self.base_url))
                internal = urls.registrable_domain(urls.host(resolved)) == page_domain
                self._open_link = {"href": attrs["href"], "rel": attrs.get("rel") or None,
                                   "text": [], "label": _norm_space(attrs.get("aria-label") or ""),
                                   "internal": internal}
                if internal:
                    self.resolved_links.append(resolved)

        if tag in VOID:
            if tag in BLOCK:
                self.stream.append("\n")
            return
        self._implicit_close(tag)
        if tag in BLOCK:
            self.stream.append("\n")
        self._push(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self._pop_to(tag)

    def handle_endtag(self, tag):
        if tag == "script" and self._jsonld_buf is not None:
            self.jsonld_scripts.append("".join(self._jsonld_buf))
            self._jsonld_buf = None
        if tag in VOID:
            return
        self._pop_to(tag)

    def handle_data(self, data):
        if self._jsonld_buf is not None:
            self._jsonld_buf.append(data)
            return
        if self._skipping():
            if not self._never_text():
                self.hidden_chars += len(_norm_space(data))
            return
        self.stream.append(data)
        size = len(_norm_space(data))
        self.total_chars += size
        if self._in_boilerplate():
            self.boiler_chars += size
        for element in self.stack:
            if element["heading"] is not None:
                element["heading"].append(data)
        if self._open_link is not None:
            self._open_link["text"].append(data)

    def _scan_obstruction(self, tag, attrs):
        tokens = ("%s %s" % (attrs.get("id") or "", attrs.get("class") or "")).lower()
        for kind, markers in OBSTRUCTION_MARKERS.items():
            if kind in self.obstructions:
                continue
            for marker in markers:
                if marker in tokens:
                    self.obstructions[kind] = "<%s> id/class contains '%s'" % (tag, marker)
                    break
        if tag == "script" and "cookie_wall" not in self.obstructions:
            src = (attrs.get("src") or "").lower()
            for host in COOKIE_SCRIPT_HOSTS:
                if host in src:
                    self.obstructions["cookie_wall"] = "consent script loaded from %s" % host
                    break
        if ("modal" not in self.obstructions and (attrs.get("role") or "").lower() == "dialog"
                and (attrs.get("aria-modal") or "").lower() == "true"
                and "hidden" not in attrs
                and "display:none" not in (attrs.get("style") or "").replace(" ", "").lower()):
            self.obstructions["modal"] = "<%s role=dialog aria-modal=true> visible in the initial HTML" % tag

    def finish(self):
        self.close()
        while self.stack:
            self._close(self.stack.pop())
        if self._open_link is not None:
            self._finish_link()


def _visible_text(stream):
    lines = [_norm_space(line) for line in "".join(stream).split("\n")]
    lines = [line for line in lines if line]
    return lines, ("\n".join(lines) + "\n" if lines else "")


def text_hash(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_document(html, base_url):
    """Parse one HTML document into its measurable parts."""
    parser = _Parser(base_url)
    try:
        parser.feed(html)
    except (AssertionError, ValueError):
        pass
    parser.finish()
    lines, text = _visible_text(parser.stream)
    words = len(text.split())
    truncations = []
    if parser.link_total > LINK_CAP:
        truncations.append(("raw.links", LINK_CAP, parser.link_total))
    if parser.image_total > IMAGE_CAP:
        truncations.append(("raw.images", IMAGE_CAP, parser.image_total))
    return {
        "text": text,
        "text_len": len(text),
        "text_hash": text_hash(text),
        "headings": parser.headings,
        "anchors": parser.anchors,
        "links": parser.links,
        "resolved_links": parser.resolved_links,
        "images": parser.images,
        "tables": parser.tables,
        "iframes": parser.iframes,
        "forms": parser.forms,
        "meta_robots": parser.meta_robots,
        "canonical": parser.canonical,
        "lang": parser.lang,
        "hreflang": parser.hreflang,
        "jsonld_scripts": parser.jsonld_scripts,
        "microdata_or_rdfa": parser.microdata_or_rdfa,
        "obstructions": [{"kind": k, "evidence": v} for k, v in sorted(parser.obstructions.items())],
        "hidden_text_len": parser.hidden_chars,
        "time_dates": parser.time_dates,
        "word_count": words,
        "boilerplate_ratio": round(parser.boiler_chars / parser.total_chars, 3) if parser.total_chars else None,
        "longest_block_words": max((len(line.split()) for line in lines), default=0),
        "heading_density_per_1k": round(len(parser.headings) / words * 1000, 1) if words else None,
        "truncations": truncations,
    }


def excerpt(text, limit=EXCERPT_CHARS):
    """The leading text, cut at a word boundary."""
    flat = _norm_space(text)
    if len(flat) <= limit:
        return flat
    cut = flat[:limit]
    return cut.rsplit(" ", 1)[0] if " " in cut else cut


def visible_dates(text, cap=20, time_dates=()):
    """Dates shown on the page, normalised to ISO 8601: first those carried by
    visible <time datetime> elements, then those written in the text, in order."""
    found = []

    def add(year, month, day):
        try:
            value = datetime.date(int(year), int(month), int(day)).isoformat()
        except ValueError:
            return
        if value not in found:
            found.append(value)

    for value in time_dates:
        add(*value.split("-"))
        if len(found) >= cap:
            return found
    events = []
    for m in _NUMERIC_DATE.finditer(text):
        first, second = int(m.group(1)), int(m.group(3))
        day, month = (second, first) if second > 12 >= first else (first, second)
        events.append((m.start(), m.group(4), month, day))
    for m in _YMD_SLASH.finditer(text):
        events.append((m.start(), m.group(1), m.group(3), m.group(4)))
    for m in _ISO_DATE.finditer(text):
        events.append((m.start(), m.group(1), m.group(2), m.group(3)))
    for m in _DMY.finditer(text):
        events.append((m.start(), m.group(3), _month(m.group(2)), m.group(1)))
    for m in _MDY.finditer(text):
        events.append((m.start(), m.group(3), _month(m.group(1)), m.group(2)))
    for _, year, month, day in sorted(events, key=lambda e: e[0]):
        if month:
            add(year, month, day)
        if len(found) >= cap:
            break
    return found


def _month(name):
    name = name.lower().rstrip(".")
    if name == "sept":
        return 9
    for full, number in _MONTHS.items():
        if full.startswith(name):
            return number
    return None


# -- JSON-LD -----------------------------------------------------------------

def _nodes(data):
    if isinstance(data, list):
        for item in data:
            yield from _nodes(item)
    elif isinstance(data, dict):
        if "@graph" in data and isinstance(data["@graph"], list):
            yield from _nodes(data["@graph"])
        else:
            yield data


def _flatten(value, prefix, fields, values):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "@context" or (key == "@type" and not prefix):
                continue
            path = "%s.%s" % (prefix, key) if prefix else key
            fields.add(path)
            _flatten(child, path, fields, values)
    elif isinstance(value, list):
        scalars = [v for v in value if not isinstance(v, (dict, list))]
        if scalars and prefix not in values:
            # A list of scalars keeps every member, joined with " | ", so that
            # for example every sameAs URL survives into the flat map.
            values[prefix] = " | ".join(_scalar(v) for v in scalars)
        for child in value:
            if isinstance(child, (dict, list)):
                _flatten(child, prefix, fields, values)
    elif prefix and prefix not in values:
        values[prefix] = _scalar(value)


def _scalar(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _as_number(value):
    match = _NUMBER.search(value or "")
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _readings(value):
    """Every number a written amount can mean under the two decimal conventions.

    "1,499.00" is 1499 where a comma groups thousands and 1.499 where it marks
    decimals; "1.499,00" is the reverse. A contradiction must hold under every
    reading, so an amount written in another locale's convention can never make
    a correct price look wrong.
    """
    digits = (value or "").strip()
    if not digits or not digits[0].isdigit():
        return set()
    found = set()
    for group, decimal in ((",", "."), (".", ",")):
        candidate = digits.replace(group, "")
        if candidate.count(decimal) > 1:
            continue
        try:
            found.add(float(candidate.replace(decimal, ".")))
        except ValueError:
            pass
    return found


def _price_contradicts(values, text):
    """True only when markup states a price and the visible text shows only other prices.

    Deliberately narrow. A price missing from the visible text is not a
    contradiction (it may be a render gap, which another rule owns); a
    contradiction needs the page to show currency amounts, none of which is the
    one the markup asserts.
    """
    marked = _NUMBER.search(values.get("offers.price") or values.get("price") or "")
    prices = _readings(marked.group(0)) if marked else set()
    if not prices:
        return False
    # A page showing an amount in another currency than the markup declares, as
    # a store localizing its display by visitor location does, is showing a
    # different fact, not contradicting the price. Only amounts whose sign can
    # denote the declared currency are compared; with none declared, all are.
    declared = (values.get("offers.priceCurrency") or values.get("priceCurrency") or "").strip().upper()
    shown = [_readings(m.group(2)) for m in _CURRENCY_AMOUNT.finditer(text)
             if not declared or declared in _SIGN_CURRENCIES.get(m.group(1).upper(), set())]
    shown = [s for s in shown if s]
    return bool(shown) and not any(abs(a - p) <= 0.005 for s in shown for a in s for p in prices)


def jsonld_entries(scripts, visible_text):
    """One entry per JSON-LD node, with values capped at 4KB for the page.

    Returns ``(entries, truncation)``, where truncation is None or
    ``("jsonld[].values", kept_pairs, total_pairs)``.
    """
    entries = []
    for script in scripts:
        cleaned = script.strip()
        if cleaned.startswith("<!--"):
            cleaned = cleaned[4:]
        if cleaned.endswith("-->"):
            cleaned = cleaned[:-3]
        try:
            data = json.loads(cleaned)
        except ValueError as exc:
            entries.append({"type": "", "valid": False, "errors": ["JSON parse error: %s" % exc],
                            "fields_present": [], "values": {}, "contradicts_visible_text": False})
            continue
        for node in _nodes(data):
            raw_type = node.get("@type")
            if isinstance(raw_type, list):
                raw_type = raw_type[0] if raw_type else ""
            node_type = str(raw_type or "")
            fields, values = set(), {}
            _flatten(node, "", fields, values)
            errors = [] if node_type else ["missing @type"]
            entries.append({"type": node_type, "valid": not errors, "errors": errors,
                            "fields_present": sorted(fields), "values": values,
                            "contradicts_visible_text": _price_contradicts(values, visible_text)})

    pairs = [(i, k, v) for i, e in enumerate(entries) for k, v in e["values"].items()]
    size = sum(len(k.encode("utf-8")) + len(v.encode("utf-8")) for _, k, v in pairs)
    if size <= JSONLD_VALUES_CAP_BYTES:
        return entries, None
    # Over the cap: keep the shortest values first. The fields worth checking
    # against visible text are short ones, a name, a price or a date, not prose.
    kept, used = set(), 0
    for i, k, v in sorted(pairs, key=lambda p: (len(p[2]), p[0], p[1])):
        cost = len(k.encode("utf-8")) + len(v.encode("utf-8"))
        if used + cost > JSONLD_VALUES_CAP_BYTES:
            continue
        kept.add((i, k))
        used += cost
    for i, entry in enumerate(entries):
        entry["values"] = {k: v for k, v in entry["values"].items() if (i, k) in kept}
    return entries, ("jsonld[].values", len(kept), len(pairs))


def schema_dates(entries):
    modified = published = None
    for entry in entries:
        values = entry["values"]
        modified = modified or values.get("dateModified")
        published = published or values.get("datePublished")
    return modified, published
