"""Discovery, page-type classification and stratified sampling. Standard library only.

Sampling is stratified by page type rather than breadth-first, because a
breadth-first crawl of a large catalogue spends the whole budget inside one
template and then reports a site-wide conclusion from it. Each page type gets an
equal share of the page budget in turn, so no single template can consume it.
"""

import re
import urllib.parse
import zlib
import xml.etree.ElementTree as ET

import urls

PAGE_TYPES = ("home", "product", "category", "article", "about", "contact", "policy", "doc", "other")

# Checked in this order; the first type with a matching path segment wins.
# Policy comes first because storefronts nest policies under product-like
# paths (/policies/refund-policy); product comes before category because a
# product URL usually sits inside a collection (/collections/x/products/y).
_SEGMENTS = (
    ("policy", {"privacy", "privacy-policy", "terms", "terms-of-service", "terms-and-conditions",
                "tos", "legal", "cookie-policy", "cookies", "cookie", "policies", "policy",
                "returns", "return-policy", "refund", "refund-policy", "refunds", "shipping",
                "shipping-policy", "disclaimer", "imprint", "impressum", "warranty", "grievance",
                "grievances", "grievance-redressal"}),
    ("product", {"product", "products", "p", "item", "items", "dp", "sku"}),
    ("category", {"collections", "collection", "category", "categories", "c", "catalog",
                  "catalogue", "department", "departments", "browse", "shop"}),
    ("article", {"blog", "blogs", "news", "article", "articles", "post", "posts", "stories",
                 "story", "insights", "press", "press-releases", "magazine", "journal"}),
    ("doc", {"docs", "doc", "documentation", "help", "guide", "guides", "api", "reference",
             "manual", "faq", "faqs", "kb", "knowledge-base", "support", "learn", "tutorial",
             "tutorials"}),
    ("about", {"about", "about-us", "aboutus", "about_us", "company", "who-we-are", "our-story",
               "team", "our-team", "mission"}),
    ("contact", {"contact", "contact-us", "contactus", "locations", "store-locator", "find-us"}),
)
# Segments whose leading word is enough: /about-fixture-instruments is an about page.
_PREFIX_WORDS = {"about": "about", "contact": "contact", "privacy": "policy", "terms": "policy",
                 "blog": "article", "faq": "doc", "help": "doc", "docs": "doc",
                 "shipping": "policy", "returns": "policy", "refund": "policy"}
# Words that settle a page type wherever they sit inside a single segment, tried
# only after every whole-segment and leading-word match has failed, so that
# /products/privacy-screen stays a product. Kept to words that name a policy
# page in any position: /extended-warranty and /special-warranty-terms are both
# warranty policies. Added after the G2 check, where a client-rendered
# storefront with no JSON-LD had /warranty, /extended-warranty and /grievance
# all classified as other.
_POLICY_WORDS = frozenset({"warranty", "grievance", "grievances"})
# Policy words that are also the names of things a shop sells or lists: cookies,
# shipping boxes, return gifts, legal pads, warranty plans. Real policy pages sit
# near the root (/cookies, /pages/shipping, /legal/terms), so these words mark a
# policy page only within POLICY_DEPTH segments of it. A grocery category
# /pc/snacks/biscuits-cookies/cookies/ read as a policy page before this, found
# in the adjudication miss check.
_AMBIGUOUS_POLICY = frozenset({"cookies", "cookie", "shipping", "returns", "refund", "refunds", "legal",
                               "terms", "warranty", "grievance", "grievances"})
POLICY_DEPTH = 2
_HOME_PATHS = {"/", "/index.html", "/index.htm", "/index.php", "/home", "/default.aspx"}
_LOCALE = re.compile(r"^[a-z]{2}(?:[-_][a-z]{2})?$")
_DATED = re.compile(r"/(?:19|20)\d{2}/(?:0?[1-9]|1[0-2])(?:/|$)")
_EXTENSION = re.compile(r"\.(?:html?|php|aspx?|jsp)$")

# Addresses that are resources, not pages. The frontier is a frontier of pages:
# a sitemap is already catalogued in sitemaps[], and a PDF or an image extracted
# as a page yields an empty document that looks exactly like a thin one. They
# stay visible to any rule that wants them, as entries in raw.links.
_NON_PAGE = re.compile(r"\.(?:xml|xml\.gz|rss|atom|json|txt|gz|zip|pdf|docx?|xlsx?|csv"
                       r"|jpe?g|png|gif|svg|webp|avif|ico|mp[34]|m4a|webm|mov|css|js)$")

# schema.org types that settle the question when the URL does not.
_SCHEMA_TYPES = {
    "Product": "product", "ProductGroup": "product", "IndividualProduct": "product",
    "Article": "article", "NewsArticle": "article", "BlogPosting": "article", "Report": "article",
    "CollectionPage": "category", "AboutPage": "about", "ContactPage": "contact",
    "FAQPage": "doc", "HowTo": "doc", "TechArticle": "doc",
    # A page whose declared entity is a list of other things is a listing page,
    # whatever its address says. Topic archives are the commonest page shape a
    # URL cannot classify: /about/<topic>/ reads as an about page and is an
    # archive of articles about that topic.
    "ItemList": "category",
}

# Types that name what the page is *about*, as opposed to how it is laid out.
# A listicle declares ItemList and NewsArticle both, and it is an article: the
# subject outranks the structure, and neither may depend on array order.
_SUBJECT_TYPES = ("product", "article")


def classify_url(url):
    """Page type and confidence from the URL alone."""
    path = urllib.parse.urlsplit(url).path.lower() or "/"
    segments = [_EXTENSION.sub("", s) for s in path.split("/") if s]
    if path in _HOME_PATHS or (len(segments) == 1 and _LOCALE.match(segments[0])):
        return "home", 0.95
    shallow = len(segments) <= POLICY_DEPTH

    def policy_word(word):
        return shallow or word not in _AMBIGUOUS_POLICY

    for page_type, names in _SEGMENTS:
        if any(s in names and (page_type != "policy" or policy_word(s)) for s in segments):
            return page_type, 0.6
    for s in segments:
        word = s.split("-", 1)[0]
        if word in _PREFIX_WORDS and (_PREFIX_WORDS[word] != "policy" or policy_word(word)):
            return _PREFIX_WORDS[word], 0.6
    if shallow:
        for s in segments:
            if _POLICY_WORDS.intersection(re.split(r"[-_]", s)):
                return "policy", 0.6
    if _DATED.search(path):
        return "article", 0.6
    return "other", 0.3


def refine(url_type, url_confidence, jsonld_types):
    """Combine the URL's verdict with the page's own structured data.

    The home page stays home whatever it declares. Otherwise a declared type
    that maps to a page type wins: agreement with the URL raises confidence, and
    a disagreement is resolved in favour of the markup at reduced confidence,
    because the page's own declaration is more direct evidence than its address.

    Among several declared types, one naming the page's subject beats one
    describing its structure, so that a listicle carrying both ItemList and
    NewsArticle is an article rather than a category. Otherwise the verdict
    would depend on the order the blocks happen to appear in.
    """
    if url_type == "home":
        return url_type, url_confidence
    mapped = [_SCHEMA_TYPES[d] for d in jsonld_types if d in _SCHEMA_TYPES]
    if not mapped:
        return url_type, url_confidence
    chosen = next((m for m in mapped if m in _SUBJECT_TYPES), mapped[0])
    if chosen == url_type:
        return chosen, 0.9
    return chosen, 0.8 if url_type == "other" else 0.7


def parse_sitemap(body, content_type, url, truncated=False):
    """Parse a sitemap or sitemap index.

    Returns ``(kind, locations, lastmod_ratio, parse_ok)`` where kind is
    ``urlset``, ``index`` or None. A body that is not XML, such as the HTML
    shell some sites serve at every path, is ``parse_ok = False``, not an empty
    sitemap.

    ``truncated`` means the fetch stopped at its size cap. The protocol allows a
    sitemap of 50 MB, and a large catalogue's often exceeds the cap, so a cut
    file is not an unreadable one: it is parsed as far as it goes, and counts as
    readable when it opens as a sitemap and yields at least one complete entry.
    """
    data = body
    if url.lower().endswith(".gz") or (content_type or "").lower().startswith("application/x-gzip"):
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            data = decompressor.decompress(body)
        except zlib.error:
            return None, [], None, False
        if not truncated:
            try:
                data += decompressor.flush()
            except zlib.error:
                return None, [], None, False
            if not decompressor.eof:
                return None, [], None, False
    if len(data) > 50 * 1024 * 1024:
        return None, [], None, False
    if truncated:
        root = _partial_root(data)
        if root is None:
            return None, [], None, False
    else:
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            return None, [], None, False
    tag = root.tag.rsplit("}", 1)[-1].lower()
    if tag not in ("urlset", "sitemapindex"):
        return None, [], None, False
    child = "url" if tag == "urlset" else "sitemap"
    if truncated and not any(node.tag.rsplit("}", 1)[-1].lower() == child for node in root):
        return None, [], None, False
    locations, with_lastmod, total = [], 0, 0
    for node in root:
        if node.tag.rsplit("}", 1)[-1].lower() != child:
            continue
        total += 1
        loc = lastmod = None
        for field in node:
            name = field.tag.rsplit("}", 1)[-1].lower()
            if name == "loc" and field.text:
                loc = field.text.strip()
            elif name == "lastmod" and field.text and field.text.strip():
                lastmod = field.text.strip()
        if loc:
            locations.append(loc)
        if lastmod:
            with_lastmod += 1
    ratio = round(with_lastmod / total, 3) if total else None
    return ("urlset" if tag == "urlset" else "index"), locations, ratio, True


def _partial_root(data):
    """The root element of an XML document cut short, with its complete children.

    Children still open where the data ends are dropped, so a half-written entry
    is never read as a whole one.
    """
    parser = ET.XMLPullParser(events=("start", "end"))
    root, depth = None, 0
    complete = []
    try:
        parser.feed(data)
        for event, element in parser.read_events():
            if event == "start":
                depth += 1
                if root is None:
                    root = element
            else:
                depth -= 1
                if depth == 1:
                    complete.append(element)
    except ET.ParseError:
        pass
    if root is None:
        return None
    shell = ET.Element(root.tag)
    shell.extend(complete)
    return shell


class Frontier:
    """Every in-scope URL known to the crawl, in discovery order.

    Scope is the resolved origin's host and its www/apex twin. A twin URL is
    rewritten onto the origin host, so the crawl never needs the twin host's
    own robots.txt and never fetches the same page twice under two hosts.
    """

    def __init__(self, origin_netloc, cap=50000):
        self.origin = origin_netloc
        self.twin = urls.twin_netloc(origin_netloc)
        self.cap = cap
        self.order = []
        self.kind = {}
        self.sources = set()
        self.overflow = 0

    def add(self, url, source):
        normal = urls.normalise(url)
        if normal is None:
            return None
        if _NON_PAGE.search(urllib.parse.urlsplit(normal).path.lower()):
            return None
        where = urls.netloc(normal)
        if self.twin and where == self.twin:
            normal, where = urls.with_netloc(normal, self.origin), self.origin
        if where != self.origin:
            return None
        if normal in self.kind:
            return normal
        if len(self.order) >= self.cap:
            self.overflow += 1
            return None
        self.order.append(normal)
        self.kind[normal] = classify_url(normal)[0]
        self.sources.add(source)
        return normal

    def __len__(self):
        return len(self.order)


class Sampler:
    """Equal allocation across page types, deterministic given the frontier.

    Each pick goes to the page type sampled least so far; ties go to the type
    with more unsampled URLs, then alphabetically. Within a type, URLs without a
    query string come first (faceted and sorted variants are the least
    representative pages on a site), then shallower paths, then shorter ones.
    """

    def __init__(self, frontier):
        self.frontier = frontier
        self.attempted = set()
        self.picked = {}

    def mark(self, url):
        self.attempted.add(url)

    def next(self):
        candidates = {}
        for url in self.frontier.order:
            if url not in self.attempted:
                candidates.setdefault(self.frontier.kind[url], []).append(url)
        if not candidates:
            return None
        page_type = min(candidates, key=lambda t: (self.picked.get(t, 0), -len(candidates[t]), t))
        url = min(candidates[page_type], key=_sample_key)
        self.attempted.add(url)
        self.picked[page_type] = self.picked.get(page_type, 0) + 1
        return url


def _sample_key(url):
    parts = urllib.parse.urlsplit(url)
    return (bool(parts.query), parts.path.count("/"), len(url), url)
