"""URL normalisation and crawl scope. Standard library only."""

import ipaddress
import urllib.parse

# Two-label public suffixes common enough to matter. Without the Public Suffix
# List, which is not in the standard library and would have to be vendored, the
# registrable domain is approximated: the last two labels of the host, or the
# last three when the last two form one of these suffixes. A miss here merges
# or splits sites only for an unlisted two-label suffix; it never changes which
# URLs are fetched, because crawl scope is decided by host, not by this value.
MULTI_LABEL_SUFFIXES = frozenset("""
co.uk org.uk ac.uk gov.uk ltd.uk plc.uk me.uk net.uk sch.uk
com.au net.au org.au edu.au gov.au
co.in net.in org.in firm.in gen.in ind.in ac.in edu.in gov.in res.in
co.jp ne.jp or.jp ac.jp go.jp
co.nz org.nz net.nz ac.nz govt.nz
com.br net.br org.br gov.br
com.cn net.cn org.cn gov.cn edu.cn
com.mx org.mx gob.mx
co.za org.za gov.za
com.sg edu.sg gov.sg
com.tr org.tr gov.tr
co.kr or.kr go.kr
com.hk org.hk com.tw org.tw
co.id or.id go.id com.my org.my gov.my com.ph gov.ph
com.ar gob.ar com.pk org.pk co.il org.il ac.il com.sa gov.sa
com.eg com.ng co.th or.th ac.th go.th com.vn com.ua co.ke
com.co com.pe com.ec com.uy
""".split())

# Query parameters that identify a campaign or a click, never a resource.
_TRACKING_PREFIXES = ("utm_",)
_TRACKING_NAMES = frozenset({"gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "_ga", "yclid"})


def _is_ip(host):
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def registrable_domain(host):
    """The approximate registrable domain of a host; see MULTI_LABEL_SUFFIXES."""
    host = (host or "").lower().rstrip(".")
    if not host or _is_ip(host) or "." not in host:
        return host
    labels = host.split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in MULTI_LABEL_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _tracking(name):
    name = name.lower()
    return name in _TRACKING_NAMES or name.startswith(_TRACKING_PREFIXES)


def normalise(url, base=None):
    """Canonical form of an http(s) URL, or None for anything else.

    Resolves against ``base``, lower-cases the scheme and host, drops a default
    port, the fragment and tracking parameters, and turns an empty path into
    ``/``. Path case and every other query parameter are kept: they can name
    different resources.
    """
    try:
        if base:
            url = urllib.parse.urljoin(base, url.strip())
        parts = urllib.parse.urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if scheme not in ("http", "https") or not host:
        return None
    if ":" in host:
        host = "[%s]" % host
    default = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if port is None or default else "%s:%d" % (host, port)
    query = "&".join(p for p in parts.query.split("&") if p and not _tracking(p.split("=", 1)[0]))
    return urllib.parse.urlunsplit((scheme, netloc, parts.path or "/", query, ""))


def netloc(url):
    return urllib.parse.urlsplit(url).netloc.lower()


def host(url):
    return (urllib.parse.urlsplit(url).hostname or "").lower()


def path_and_query(url):
    """The part of a URL that robots.txt rules are matched against."""
    parts = urllib.parse.urlsplit(url)
    return (parts.path or "/") + ("?" + parts.query if parts.query else "")


def twin_netloc(value):
    """The www/apex twin of a netloc: www.example.com <-> example.com."""
    host_part, sep, port = value.partition(":")
    if _is_ip(host_part) or "." not in host_part:
        return None
    twin = host_part[4:] if host_part.startswith("www.") else "www." + host_part
    return twin + sep + port


def origin(url):
    parts = urllib.parse.urlsplit(url)
    return "%s://%s" % (parts.scheme, parts.netloc)


def with_netloc(url, new_netloc):
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parts.scheme, new_netloc, parts.path, parts.query, ""))
