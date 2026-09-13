"""Generate the five fixture archetype sites.

The committed files under each archetype's ``site/`` directory are the fixture;
this script is how they were produced, kept so that a change to a fixture is a
reviewable change to one function here rather than a hand edit across dozens of
HTML files. ``tests/test_archetypes.py`` regenerates into a temporary directory
and fails if the result differs from what is committed, so the two cannot drift.

Every site is fictional. Text is assembled deterministically from fixed
sentences, so no fixture depends on randomness, and it deliberately contains no
calendar dates or currency amounts except where an archetype puts one on purpose.
All absolute URLs use ``http://localhost:8000``; the test server rewrites that
origin to its own.

    python tests/fixtures/archetypes/generate.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ORIGIN = "http://localhost:8000"

SENTENCES = [
    "The workshop keeps every pattern on paper before any fabric is cut.",
    "Each batch is inspected by the person who will later answer questions about it.",
    "A repair request is logged with the order number and a short description of the fault.",
    "Our field team visits partner studios to review how the materials hold up in daily use.",
    "The guide explains which settings matter first and which can safely wait.",
    "Readers who follow the steps in order finish the setup without needing support.",
    "Configuration files are read once at start-up and validated before any work begins.",
    "A missing value falls back to the documented default and is reported in the log.",
    "Teams usually adopt the recommended layout and change it only when a project grows.",
    "The reference lists every option with its type, its default and a short example.",
    "Shipping partners collect parcels each weekday and share tracking details the same evening.",
    "Returns are accepted within the stated window when the item is unused and complete.",
    "The editorial desk checks each claim against a primary source before publication.",
    "Interviews are recorded with consent and transcribed by the reporting team.",
    "Local councils publish their meeting minutes, which reporters read in full.",
    "Analysts compare the new figures with the previous series to explain the change.",
]


def prose(words, offset=0):
    out, count, i = [], 0, offset
    while count < words:
        sentence = SENTENCES[i % len(SENTENCES)]
        out.append(sentence)
        count += len(sentence.split())
        i += 1
    return out


def paragraphs(words, offset=0, per=4):
    sentences = prose(words, offset)
    return "\n".join("<p>%s</p>" % " ".join(sentences[i:i + per]) for i in range(0, len(sentences), per))


def jsonld(obj):
    return '<script type="application/ld+json">%s</script>' % json.dumps(obj, ensure_ascii=False)


def page(path, title, body, head_extra="", scripts="", lang="en", canonical=True, robots=None, nav="", footer=""):
    head = ['<meta charset="utf-8">', "<title>%s</title>" % title,
            '<meta name="viewport" content="width=device-width, initial-scale=1">']
    if robots:
        head.append('<meta name="robots" content="%s">' % robots)
    if canonical:
        href = canonical if isinstance(canonical, str) else ORIGIN + path
        head.append('<link rel="canonical" href="%s">' % href)
    head.append(head_extra)
    return ("<!doctype html>\n<html lang=\"%s\">\n<head>\n%s\n</head>\n<body>\n%s\n<main>\n%s\n</main>\n%s\n%s\n"
            "</body>\n</html>\n" % (lang, "\n".join(h for h in head if h), nav, body, footer, scripts))


def write(root, rel, content):
    path = os.path.join(root, *rel.strip("/").split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def sitemap(paths):
    urls = "\n".join("  <url><loc>%s%s</loc></url>" % (ORIGIN, p) for p in paths)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s\n</urlset>\n' % urls)


# ---------------------------------------------------------------------------
# 1. healthy-minimal: a small, well-built site that should produce no defects
# ---------------------------------------------------------------------------

def healthy_minimal(root):
    org = {"@context": "https://schema.org", "@type": "Organization", "@id": ORIGIN + "/#org",
           "name": "Harbor Lane Studio", "url": ORIGIN + "/", "logo": ORIGIN + "/logo.png",
           "foundingDate": "2011",
           "sameAs": ["https://www.linkedin.com/company/harbor-lane-studio",
                      "https://github.com/harbor-lane-studio"]}
    pages = ["/", "/about", "/contact", "/blog/launch-notes", "/blog/materials-explained",
             "/blog/care-guide", "/docs/getting-started", "/docs/configuration", "/privacy-policy"]
    nav = "<header><nav>%s</nav></header>" % " ".join(
        '<a href="%s">%s</a>' % (p, p.strip("/") or "Home") for p in pages)
    footer = '<footer><p>Harbor Lane Studio. Made in small batches.</p></footer>'
    write(root, "robots.txt", "User-agent: *\nDisallow: /cart\n\nSitemap: %s/sitemap.xml\n" % ORIGIN)
    write(root, "sitemap.xml", sitemap(pages))
    write(root, "llms.txt", "# Harbor Lane Studio\n\nSmall-batch outdoor gear. Guides: %s/docs/getting-started\n"
          % ORIGIN)
    write(root, "index.html", page("/", "Harbor Lane Studio", "<h1>Harbor Lane Studio</h1>\n" + paragraphs(260),
                                   head_extra=jsonld(org), nav=nav, footer=footer))
    write(root, "about.html", page("/about", "About Harbor Lane Studio",
                                   "<h1>About us</h1>\n" + paragraphs(320, 2), nav=nav, footer=footer))
    write(root, "contact.html", page("/contact", "Contact", "<h1>Contact</h1>\n<p>12 Harbor Lane, Pune.</p>\n"
                                     + paragraphs(120, 4), nav=nav, footer=footer))
    for i, slug in enumerate(["launch-notes", "materials-explained", "care-guide"]):
        post = {"@context": "https://schema.org", "@type": "BlogPosting", "headline": slug.replace("-", " "),
                "datePublished": "2026-03-0%d" % (i + 2), "dateModified": "2026-03-0%d" % (i + 3),
                "author": {"@type": "Organization", "@id": ORIGIN + "/#org"}}
        body = "<h1>%s</h1>\n<p>Published 2026-03-0%d</p>\n" % (slug.replace("-", " ").title(), i + 2)
        body += "".join("<h2>Part %d</h2>\n%s\n" % (n + 1, paragraphs(230, i * 3 + n)) for n in range(3))
        write(root, "blog/%s.html" % slug, page("/blog/" + slug, slug, body, head_extra=jsonld(post), nav=nav,
                                                footer=footer))
    for i, slug in enumerate(["getting-started", "configuration"]):
        body = "<h1>%s</h1>\n" % slug.replace("-", " ").title()
        body += "".join('<h2 id="s%d">Step %d</h2>\n%s\n' % (n, n + 1, paragraphs(300, i + n)) for n in range(6))
        write(root, "docs/%s.html" % slug, page("/docs/" + slug, slug, body, nav=nav, footer=footer))
    write(root, "privacy-policy.html", page("/privacy-policy", "Privacy policy",
                                            "<h1>Privacy policy</h1>\n" + paragraphs(400, 10), nav=nav,
                                            footer=footer))


# ---------------------------------------------------------------------------
# 2. spa-shell: a client-rendered storefront whose server answers every path
#    with one empty application shell
# ---------------------------------------------------------------------------

SHELL_SCRIPT = """<script>
(function () {
  var routes = %s;
  var path = location.pathname.replace(/\\/$/, "") || "/";
  var route = routes[path];
  var root = document.getElementById("root");
  if (!route) { root.innerHTML = "<h1>Page not found</h1>"; return; }
  var nav = Object.keys(routes).map(function (p) { return '<a href="' + p + '">' + routes[p].title + '</a>'; });
  root.innerHTML = "<header><nav>" + nav.join(" ") + "</nav></header><h1>" + route.title + "</h1>" + route.body;
})();
</script>"""


def spa_shell(root):
    routes = {"/": {"title": "Nimbus Devices", "body": paragraphs(80, 1)},
              "/aboutus": {"title": "About Nimbus", "body": paragraphs(260, 3)},
              "/warranty": {"title": "Warranty", "body": paragraphs(300, 5)},
              "/grievance": {"title": "Grievance redressal", "body": paragraphs(240, 7)},
              "/extended-warranty": {"title": "Extended warranty", "body": paragraphs(320, 9)}}
    shell = ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n<title>Nimbus Devices</title>\n"
             "<link rel=\"canonical\" href=\"%s/\">\n</head>\n<body>\n<div id=\"root\"></div>\n%s\n</body>\n</html>\n"
             % (ORIGIN, SHELL_SCRIPT % json.dumps(routes)))
    write(root, "shell.html", shell)


# ---------------------------------------------------------------------------
# 3. storefront-defects: a server-rendered shop with template-level defects
#    next to legitimate patterns that look like defects
# ---------------------------------------------------------------------------

PRICE_SCRIPT = """<script>
document.querySelectorAll("[data-price]").forEach(function (el) {
  el.textContent = "\\u20b9" + el.getAttribute("data-price") + ".00";
});
</script>"""

REVIEWS_SCRIPT = """<script>
document.getElementById("reviews").innerHTML = "<h2>Customer reviews</h2><p>%s</p>";
</script>"""


def storefront_defects(root):
    org = {"@context": "https://schema.org", "@type": "Organization", "name": "Northwind Threads",
           "url": ORIGIN + "/", "logo": ORIGIN + "/logo.png", "sameAs": ["", "", ""]}
    products = ["trail-tee", "harbor-hoodie", "summit-cap", "delta-socks", "canyon-jacket",
                "meadow-scarf", "ridge-gloves"]
    live = ["/", "/collections/all", "/collections/graphic-tees", "/pages/about-us", "/policies/refund-policy"] + \
        ["/products/" + p for p in products]
    dead = ["/products/retired-classic-tee", "/products/retired-logo-tee"]
    nav = "<header><nav>%s</nav></header>" % " ".join('<a href="%s">%s</a>' % (p, p) for p in live[:5])
    drawer = '<div role="dialog" aria-modal="true" hidden><p>Your cart is empty.</p></div>'
    footer = "<footer><p>Northwind Threads</p></footer>" + drawer
    write(root, "robots.txt", "User-agent: *\nDisallow: /cart\nDisallow: /checkout\n\nSitemap: %s/sitemap.xml\n"
          % ORIGIN)
    write(root, "sitemap.xml", sitemap(live + dead))
    grid = "".join('<li><a href="/products/%s">%s</a></li>' % (p, p.replace("-", " ")) for p in products)
    write(root, "index.html", page("/", "Northwind Threads", "<h1>Northwind Threads</h1>\n" + paragraphs(220)
                                   + "<ul>%s</ul>" % grid, head_extra=jsonld(org), nav=nav, footer=footer))
    write(root, "collections/all.html", page("/collections/all", "All products",
                                             "<h1>All products</h1><ul>%s</ul>\n%s" % (grid, paragraphs(90, 2)),
                                             nav=nav, footer=footer))
    write(root, "collections/graphic-tees.html", page("/collections/graphic-tees", "Graphic tees",
                                                      "<h1>Graphic tees</h1><ul>%s</ul>\n%s"
                                                      % (grid, paragraphs(80, 3)),
                                                      robots="noindex, follow", nav=nav, footer=footer))
    write(root, "pages/about-us.html", page("/pages/about-us", "About us", "<h1>About us</h1>\n" + paragraphs(280, 4),
                                            nav=nav, footer=footer))
    write(root, "policies/refund-policy.html", page("/policies/refund-policy", "Refund policy",
                                                    "<h1>Refund policy</h1>\n" + paragraphs(260, 11), nav=nav,
                                                    footer=footer))
    for i, slug in enumerate(products):
        name = slug.replace("-", " ").title()
        product = {"@context": "https://schema.org", "@type": "Product", "name": name,
                   "description": SENTENCES[i], "brand": {"@type": "Brand", "name": "Northwind Threads"}}
        if i < 5:
            price = '<p class="price">Price: <span data-price="999"></span></p>'
            scripts = PRICE_SCRIPT
        else:
            product["offers"] = {"@type": "Offer", "price": "1499.00", "priceCurrency": "INR"}
            price = '<p class="price">Price: ₹999.00</p>'
            scripts = REVIEWS_SCRIPT % " ".join(prose(45, i))
        body = "<h1>%s</h1>\n%s\n%s\n<div id=\"reviews\"></div>" % (name, price, paragraphs(230, i))
        write(root, "products/%s.html" % slug, page("/products/" + slug, name, body, head_extra=jsonld(product),
                                                    robots="noindex, max-snippet:-1", scripts=scripts, nav=nav,
                                                    footer=footer))


# ---------------------------------------------------------------------------
# 4. publisher-docs: a content-heavy publisher with documentation, built to
#    tempt every text-shape metric the audit deliberately does not use
# ---------------------------------------------------------------------------

def publisher_docs(root):
    org = {"@context": "https://schema.org", "@type": "NewsMediaOrganization", "name": "Lumen Field Notes",
           "url": ORIGIN + "/", "logo": ORIGIN + "/logo.png", "foundingDate": "2004",
           "sameAs": ["https://en.wikipedia.org/wiki/Lumen_Field_Notes"]}
    news = ["council-budget-vote", "river-survey-results", "rail-link-hearing"]
    blog = ["notes-from-the-desk", "how-we-verify", "reader-questions"]
    docs = ["style-guide", "sourcing-handbook", "corrections-process"]
    live = ["/", "/about", "/privacy-policy", "/tag/field-guides"] + ["/news/" + n for n in news] + \
        ["/blog/" + b for b in blog] + ["/docs/" + d for d in docs]
    nav = "<header><nav>%s</nav><nav>%s</nav></header>" % (
        " ".join('<a href="%s">%s</a>' % (p, p) for p in live), " ".join('<a href="%s">more</a>' % p for p in live))
    footer = ("<footer><nav>%s</nav><p>Lumen Field Notes. Independent reporting.</p>"
              '<div style="display: none"><p>%s</p></div></footer>'
              % (" ".join('<a href="%s">%s</a>' % (p, p) for p in live), " ".join(prose(60, 5))))
    write(root, "robots.txt", "User-agent: *\nDisallow: /search\n\nSitemap: %s/sitemap.xml\nSitemap: %s/news-sitemap.xml\n"
          % (ORIGIN, ORIGIN))
    write(root, "sitemap.xml", sitemap(live + ["/news/withdrawn-story"]))
    write(root, "index.html", page("/", "Lumen Field Notes", "<h1>Lumen Field Notes</h1>\n" + paragraphs(300),
                                   head_extra=jsonld(org), nav=nav, footer=footer))
    write(root, "about.html", page("/about", "About", "<h1>About</h1>\n<h1>Our newsroom</h1>\n" + paragraphs(300, 6),
                                   nav=nav, footer=footer))
    policy = "<br>\n".join(prose(900, 8))
    write(root, "privacy-policy.html", page("/privacy-policy", "Privacy", "<h1>Privacy</h1>\n<div>%s</div>" % policy,
                                            nav=nav, footer=footer))
    write(root, "tag/field-guides.html", page("/tag/field-guides", "Field guides", "<h1>Field guides</h1><ul>%s</ul>"
                                              % "".join('<li><a href="/docs/%s">%s</a></li>' % (d, d) for d in docs),
                                              robots="noindex, follow", nav=nav, footer=footer))
    for i, slug in enumerate(news):
        article = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": slug.replace("-", " "),
                   "datePublished": "2026-02-1%d" % i, "dateModified": "2026-02-1%d" % (i + 1)}
        body = ('<article><h1>%s</h1>\n<p>Published 2026-02-1%d</p>\n<div class="paywall-container">%s</div>'
                "</article>" % (slug.replace("-", " ").title(), i, paragraphs(1650, 12 + i, per=6)))
        write(root, "news/%s.html" % slug, page("/news/" + slug, slug, body, head_extra=jsonld(article), nav=nav,
                                                footer=footer))
    for i, slug in enumerate(blog):
        post = {"@context": "https://schema.org", "@type": "BlogPosting", "headline": slug.replace("-", " ")}
        body = "<h1>%s</h1>\n<h2>Background</h2>\n%s\n<h2>What changed</h2>\n%s" % (
            slug.replace("-", " ").title(), paragraphs(260, 4 + i), paragraphs(260, 8 + i))
        write(root, "blog/%s.html" % slug, page("/blog/" + slug, slug, body, head_extra=jsonld(post), nav=nav,
                                                footer=footer))
    broken = ('<script type="application/ld+json">{"@context": "https://schema.org", "@type": "TechArticle", '
              '"headline": "handbook",}</script>')
    for i, slug in enumerate(docs):
        body = "<h1>%s</h1>\n%s" % (slug.replace("-", " ").title(), paragraphs(1700, 6 + i, per=5))
        write(root, "docs/%s.html" % slug, page("/docs/" + slug, slug, body, head_extra=broken, robots="nosnippet",
                                                nav=nav, footer=footer))


# ---------------------------------------------------------------------------
# 5. crawler-restricted: a real site whose robots.txt admits only named crawlers,
#    or whose robots.txt endpoint is failing; its pages must never be requested
# ---------------------------------------------------------------------------

def crawler_restricted(root):
    write(root, "robots.txt", "User-agent: *\nDisallow: /\n\nUser-agent: Googlebot\nAllow: /\n\n"
          "User-agent: PerplexityBot\nDisallow: /\n\nUser-agent: GPTBot\nDisallow: /\n\n"
          "Sitemap: %s/sitemap.xml\n" % ORIGIN)
    write(root, "sitemap.xml", sitemap(["/", "/about"]))
    nav = '<header><nav><a href="/">Home</a> <a href="/about">About</a></nav></header>'
    write(root, "index.html", page("/", "Quarry Analytics", "<h1>Quarry Analytics</h1>\n" + paragraphs(240), nav=nav))
    write(root, "about.html", page("/about", "About", "<h1>About</h1>\n" + paragraphs(240, 3), nav=nav))


ARCHETYPES = {
    "healthy-minimal": healthy_minimal,
    "spa-shell": spa_shell,
    "storefront-defects": storefront_defects,
    "publisher-docs": publisher_docs,
    "crawler-restricted": crawler_restricted,
}


def generate(out_dir):
    for name, build in ARCHETYPES.items():
        build(os.path.join(out_dir, name, "site"))


if __name__ == "__main__":
    generate(sys.argv[1] if len(sys.argv) > 1 else HERE)
