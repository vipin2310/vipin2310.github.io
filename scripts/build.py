# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "pillow"]
# ///
"""Build the website and CVs from content.yaml.

    uv run scripts/build.py          # index.html, cv.md, llms.txt, publications.bib, sitemap.xml, robots.txt
    uv run scripts/build.py --pdf    # also cv/Vipin_Singh_CV.pdf and cv/Vipin_Singh_CV_short.pdf (LuaLaTeX)
"""
import datetime
import html
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
C = yaml.safe_load((ROOT / "content.yaml").read_text(encoding="utf-8"))
P, SITE = C["person"], C["site"]
SITE["updated"] = datetime.date.today()          # "last updated" everywhere = the day of the build
BASE = SITE["url"].rstrip("/") + "/"
CV_PDF, CV_SHORT_PDF = "cv/Vipin_Singh_CV.pdf", "cv/Vipin_Singh_CV_short.pdf"
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
TYPE_ORDER = {"Journal": 0, "Conference": 1, "Demo": 2, "Workshop": 3}
TOPICS = {"soil": "Soil science", "sewer": "Urban water", "groundwater": "Groundwater"}

# ---------------------------------------------------------------- inline markup ([text](url), *italic*)
LINK, ITAL = re.compile(r"\[([^\]]+)\]\(([^)]+)\)"), re.compile(r"\*([^*]+)\*")


def md_html(s):
    s = html.escape(s, quote=False)
    s = LINK.sub(lambda m: f'<a href="{m[2]}">{m[1]}</a>', s)
    return ITAL.sub(r"<em>\1</em>", s)


def md_plain(s):
    return ITAL.sub(r"\1", LINK.sub(r"\1", s))


def tex(s):
    rep = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
           "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(rep.get(ch, ch) for ch in s)


def md_tex(s):
    out, pos = [], 0
    for m in LINK.finditer(s):
        out += [tex(s[pos:m.start()]), rf"\href{{{m[2]}}}{{{tex(m[1])}}}"]
        pos = m.end()
    out.append(tex(s[pos:]))
    return ITAL.sub(r"\\textit{\1}", "".join(out))


# ---------------------------------------------------------------- icons (Font Awesome Free, CC BY 4.0)
def icon(name, cls="ic"):
    svg = (ROOT / "assets/icons" / f"{name}.svg").read_text()
    svg = re.sub(r"<!--.*?-->", "", svg)
    return svg.replace("<svg ", f'<svg class="{cls}" aria-hidden="true" focusable="false" fill="currentColor" ', 1)


# ---------------------------------------------------------------- isolines: the site's signature motif
def contours(w=360, h=900, seed=3):
    """Closed, wobbly isolines around two 'wells', like a groundwater contour map."""
    paths = []
    for (cx, cy, n, r0, step, ph) in [(40, 760, 11, 26, 30, seed), (330, 150, 8, 18, 26, seed + 1.7)]:
        for k in range(n):
            r = r0 + k * step
            pts = []
            for i in range(97):
                t = 2 * math.pi * i / 96
                rr = r * (1 + 0.10 * math.sin(2 * t + ph + 0.15 * k) + 0.06 * math.sin(3 * t - ph * 0.7)
                          + 0.035 * math.sin(5 * t + k * 0.4))
                pts.append(f"{cx + rr * math.cos(t):.1f},{cy + rr * 0.82 * math.sin(t):.1f}")
            paths.append(f'<path d="M{" L".join(pts)}Z"/>')
    return (f'<svg class="iso" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice" aria-hidden="true">'
            f'<g fill="none" stroke="currentColor" stroke-width="1">{"".join(paths)}</g></svg>')


# ---------------------------------------------------------------- publications
def authors_html(p):
    out = []
    for i, a in enumerate(p["authors"]):
        mark = ("*" if i in p.get("equal", []) else "") + ("†" if i in p.get("supervision", []) else "")
        name = html.escape(a) + (f"<sup>{mark}</sup>" if mark else "")
        out.append(f'<strong class="me">{name}</strong>' if a == P["name"] else name)
    return ", ".join(out)


def pub_notes(p):
    notes = []
    if p.get("equal"):
        notes.append("*equal contribution")
    if p.get("supervision"):
        notes.append("†equal supervision")
    return notes


def pub_links(p):
    L = []
    if p.get("doi"):
        L.append(("DOI", f"https://doi.org/{p['doi']}"))
    if p.get("url") and not p.get("doi"):
        L.append(("PDF", p["url"]))
    if p.get("arxiv"):
        L.append(("arXiv", f"https://arxiv.org/abs/{p['arxiv']}"))
    if p.get("code"):
        L.append(("Code", p["code"]))
    if p.get("demo"):
        L.append(("Live demo", p["demo"]))
    return L


def bib_name(a):
    first, last = a.rsplit(" ", 1)
    return f"{last}, {first}".replace("ß", r"{\ss}").replace("ü", r'{\"u}')


def bibtex(p):
    f = {"author": " and ".join(bib_name(a) for a in p["authors"]), "title": "{" + p["title"] + "}"}
    if p["bibtype"] == "article":
        f.update(journal=p["journal"], volume=p["volume"], pages=p["bibpages"])
    else:
        f["booktitle"] = p["booktitle"]
        for k in ("series", "volume"):
            if p.get(k):
                f[k] = p[k]
        if p.get("pages"):
            f["pages"] = p["pages"].replace("–", "--")
    if p.get("place"):
        f["address"] = p["place"]
    if p.get("publisher"):
        f["publisher"] = p["publisher"]
    f["year"] = str(p["year"])
    f["month"] = MONTHS[p["month"] - 1]
    if p.get("doi"):
        f["doi"] = p["doi"]
    if p.get("url"):
        f["url"] = p["url"]
    if p.get("arxiv"):
        f.update(eprint=p["arxiv"], archivePrefix="arXiv")
    body = ",\n".join(f"  {k:<13} = {{{v}}}" if k != "month" else f"  {k:<13} = {v}" for k, v in f.items())
    return f"@{p['bibtype']}{{{p['key']},\n{body}\n}}"


def figure(name, caption, cls, fit="contain"):
    """Figure markup. SVGs are inlined so they follow the color theme; raster images open full size on click."""
    path = ROOT / "assets/img/figures" / name
    cap = f"<figcaption>{html.escape(caption)}</figcaption>"
    if name.endswith(".svg"):
        return f'<figure class="{cls} is-svg">{path.read_text()}{cap}</figure>'
    w, h = Image.open(path).size
    src = f"assets/img/figures/{name}"
    return (f'<figure class="{cls}"><a class="plate fit-{fit}" href="{src}" title="{html.escape(caption)}"><img src="{src}" width="{w}" height="{h}" '
            f'loading="lazy" decoding="async" alt="{html.escape(caption)}"></a>{cap}</figure>')


def figure_views(figs, cls):
    """Several figures as switchable views. Without JavaScript all of them are shown, one below the other."""
    tabs = "".join(f'<button type="button" class="view-tab{" is-on" if i == 0 else ""}" data-view="{i}" '
                   f'aria-pressed="{str(i == 0).lower()}">{html.escape(f["label"])}</button>' for i, f in enumerate(figs))
    views = "".join(f'<div class="view" data-view="{i}">{figure(f["file"], f["caption"], cls)}</div>' for i, f in enumerate(figs))
    return f'<div class="views"><div class="view-tabs" role="group" aria-label="Figure">{tabs}</div>{views}</div>'


def lab_icon():
    return '<img class="lab-ic" src="assets/img/calgo-lab.png" alt="" width="22" height="22">'


def news_thumb(name, width=640):
    """Small copy of a news image for the tiles (the full image is only loaded on the detail page)."""
    src, out = ROOT / "assets/img/news" / name, ROOT / "assets/img/news/thumbs" / name
    if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
        out.parent.mkdir(exist_ok=True)
        im = Image.open(src).convert("RGB")
        im.thumbnail((width, width * 2), Image.LANCZOS)
        im.save(out, quality=85, optimize=True, progressive=True)
    return f"thumbs/{name}"


def news_html():
    items = []
    for n in C.get("news", []):
        d = n["date"]
        thumb = news_thumb(n["image"])
        w, h = Image.open(ROOT / "assets/img/news" / thumb).size
        items.append(f"""
      <li class="news-item">
        <a class="news-card" href="news/{n['slug']}.html">
          <span class="news-img fit-{n.get('fit', 'cover')}"><img src="assets/img/news/{thumb}" width="{w}" height="{h}" loading="lazy" decoding="async" alt=""></span>
          <time datetime="{d}">{d.strftime('%b %Y')}</time>
          <span class="news-title">{html.escape(n['title'])}</span>
        </a>
      </li>""")
    return "".join(items)


URL = re.compile(r"https?://[^\s)<>\]]+")


def post_body_html(text):
    paras = [x.strip() for x in text.strip().split("\n\n") if x.strip()]
    out = []
    for para in paras:
        s = html.escape(para, quote=False)
        s = URL.sub(lambda m: f'<a href="{m[0]}" rel="noopener" target="_blank">{m[0]}</a>', s)
        out.append("<p>" + s.replace("\n", "<br>") + "</p>")
    return "\n".join(out)


def news_page(n, newer, older):
    """Detail page for one news item: all images, the full post text, and a link to the original."""
    d, L = n["date"], P["links"]
    url = f"{BASE}news/{n['slug']}.html"
    imgs = n.get("images") or [n["image"]]
    sizes = [Image.open(ROOT / "assets/img/news" / f).size for f in imgs]
    hero = (f'<div class="plate"><img id="hero" src="../assets/img/news/{imgs[0]}" width="{sizes[0][0]}" '
            f'height="{sizes[0][1]}" alt="{html.escape(n["title"])}"></div>')
    # thumbnails: with JS they swap the large image; without JS they link to the image file
    rest = "".join(f'<a class="plate thumb{" is-on" if k == 0 else ""}" href="../assets/img/news/{f}" data-w="{w}" data-h="{h}" '
                   f'aria-label="Show image {k + 1}"><img src="../assets/img/news/{f}" width="{w}" height="{h}" loading="lazy" alt=""></a>'
                   for k, (f, (w, h)) in enumerate(zip(imgs, sizes))) if len(imgs) > 1 else ""
    author = n.get("author") or P["name"]
    who = (f'<a href="{n["author_url"]}" rel="noopener" target="_blank">{html.escape(author)}</a>'
           if n.get("author_url") else html.escape(author))
    nav = ""
    if newer:
        nav += f'<a class="pager newer" href="{newer["slug"]}.html"><span>Newer</span>{html.escape(newer["title"])}</a>'
    if older:
        nav += f'<a class="pager older" href="{older["slug"]}.html"><span>Older</span>{html.escape(older["title"])}</a>'
    ld = {"@context": "https://schema.org", "@type": "Article", "headline": n["title"], "datePublished": str(d),
          "url": url, "image": [f"{BASE}assets/img/news/{f}" for f in imgs], "sameAs": n["url"],
          "author": {"@type": "Person" if author == P["name"] else "Organization", "name": author},
          "about": {"@id": BASE + "#me"}}
    desc = html.escape(n["title"] + ". " + " ".join(n.get("body", "").split())[:150])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(n['title'])} · {P['name']}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="article">
<meta property="og:title" content="{html.escape(n['title'])}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{BASE}assets/img/news/{imgs[0]}">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="../assets/img/favicon-32.png" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="../assets/img/apple-touch-icon.png">
<link rel="stylesheet" href="../assets/css/style.css">
<script>document.documentElement.classList.add("js");try{{var t=localStorage.getItem("theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")}</script>
</head>
<body class="subpage">
<header class="topbar">
  <a class="home" href="../index.html"><img src="../assets/img/avatar.jpg" width="36" height="36" alt="">{P['name']}</a>
  <nav class="topnav"><a href="../index.html#news">All news</a>
  <button class="theme" type="button" aria-label="Toggle color theme" title="Toggle color theme">{icon('moon', 'ic moon')}{icon('sun', 'ic sun')}</button></nav>
</header>
<main class="post">
  <p class="eyebrow">News · <time datetime="{d}">{d.strftime('%-d %B %Y')}</time></p>
  <h1>{html.escape(n['title'])}</h1>
  <p class="post-meta"><span>Originally posted on LinkedIn by {who}</span>
    <a class="btn" href="{n['url']}" rel="noopener" target="_blank">View on LinkedIn {icon('arrow-up-right-from-square', 'ic sm')}</a></p>
  <figure class="post-hero">{hero}</figure>
  {f'<div class="post-gallery">{rest}</div>' if rest else ''}
  <div class="post-body">{post_body_html(n.get('body', ''))}</div>
  <nav class="pagers" aria-label="More news">{nav}</nav>
  <footer class="foot"><p><a href="../index.html">{P['name']}</a> · {P['headline']}, {P['affiliation']} · <a href="mailto:{P['email']}">{P['email']}</a></p></footer>
</main>
<script src="../assets/js/site.js" defer></script>
</body>
</html>
"""


def pub_html(p):
    links = "".join(f'<a class="chip" href="{u}">{l}</a>' for l, u in pub_links(p))
    first = p["authors"][0] == P["name"] or 0 in p.get("equal", []) and P["name"] in p["authors"][:2]
    notes = " · ".join(pub_notes(p))
    place = f", {html.escape(p['place'])}" if p.get("place") else ""
    oa = ' <span class="oa">Open access</span>' if p.get("open_access") else ""
    return f"""
      <li class="pub" data-topic="{p['topic']}" data-first="{str(first).lower()}" id="{p['key']}">
        {figure(p['figure'], p['caption'], 'pub-fig', p.get('fit', 'contain')) if p.get('figure') else ''}
        <div class="pub-body">
        <div class="pub-meta"><span class="badge b-{p['type'].lower()}">{p['type']}</span>{f'<span class="badge b-track">{html.escape(p["track"])}</span>' if p.get("track") else ''}<span class="pub-venue">{html.escape(p['venue_short'])}</span></div>
        <h3 class="pub-title">{html.escape(p['title'])}</h3>
        <p class="pub-authors">{authors_html(p)}</p>
        <p class="pub-where"><em>{html.escape(p['venue'])}</em>{place}, {p['year']}.{oa}{f' <span class="note">{notes}</span>' if notes else ''}</p>
        <p class="pub-sum">{html.escape(p['summary'])}</p>
        <div class="pub-actions">{links}
          <details class="bib"><summary class="chip">BibTeX</summary>
            <div class="bib-box"><button class="copy" type="button" data-copy="bib-{p['key']}">Copy</button><pre id="bib-{p['key']}">{html.escape(bibtex(p))}</pre></div>
          </details>
        </div>
        </div>
      </li>"""


# ---------------------------------------------------------------- CV (HTML)
def dates(e):
    return e["start"] if e["start"] == e["end"] else f"{e['start']} – {e['end']}"


def cv_html():
    exp = "".join(f"""
        <li class="tl-item"><div class="tl-when">{dates(e)}</div><div class="tl-body">
          <h4>{html.escape(e['role'])}</h4><p class="tl-org">{html.escape(e['org'])} · {html.escape(e['place'])}</p>
          {('<ul>' + ''.join(f'<li>{md_html(i)}</li>' for i in e['items']) + '</ul>') if e['items'] else ''}
        </div></li>""" for e in C["experience"])
    edu = "".join(f"""
        <li class="tl-item"><div class="tl-when">{dates(e)}</div><div class="tl-body">
          <h4>{html.escape(e['degree'])}</h4><p class="tl-org">{html.escape(e['org'])}</p>
          <ul>{''.join(f'<li>{md_html(i)}</li>' for i in e['items'])}</ul>
        </div></li>""" for e in C["education"])
    svc = "".join(f"""
        <li class="tl-item"><div class="tl-when">{html.escape(s['when'])}</div><div class="tl-body">
          <h4>{html.escape(s['role'])}</h4><p class="tl-org">{html.escape(s['org'])}</p><p>{html.escape(s['text'])}</p>
        </div></li>""" for s in C["service"])
    kv = lambda rows: "".join(f"<div><dt>{html.escape(r['label'])}</dt><dd>{html.escape(r['value'])}</dd></div>" for r in rows)
    return f"""
      <div class="cv-actions">
        <a class="btn primary" href="{CV_PDF}" target="_blank" rel="noopener">{icon('file-pdf')} Full CV (PDF)</a>
        <a class="btn" href="{CV_SHORT_PDF}" target="_blank" rel="noopener">{icon('file-pdf')} Short CV (PDF)</a>
        <a class="btn" href="cv.md">{icon('file-lines')} CV as Markdown</a>
      </div>
      <h3 class="sub">Experience</h3><ol class="timeline">{exp}</ol>
      <h3 class="sub">Education</h3><ol class="timeline">{edu}</ol>
      <h3 class="sub">Service</h3><ol class="timeline">{svc}</ol>
      <div class="kv-grid">
        <div><h3 class="sub">Skills</h3><dl class="kv">{kv(C['skills'])}</dl></div>
        <div><h3 class="sub">Languages</h3><dl class="kv">{kv(C['languages'])}</dl></div>
      </div>"""


# ---------------------------------------------------------------- structured data for search engines and agents
def json_ld():
    L = P["links"]
    person = {
        "@type": "Person", "@id": BASE + "#me", "name": P["name"], "givenName": P["given_name"],
        "familyName": P["family_name"], "url": BASE, "image": BASE + "assets/img/avatar.jpg",
        "jobTitle": P["headline"], "email": "mailto:" + P["email"],
        "worksFor": {"@type": "CollegeOrUniversity", "name": "Berliner Hochschule für Technik", "url": P["affiliation_url"]},
        "alumniOf": [{"@type": "CollegeOrUniversity", "name": "Berliner Hochschule für Technik"},
                     {"@type": "CollegeOrUniversity", "name": "Hochschule für Technik Stuttgart"}],
        "workLocation": {"@type": "Place", "name": f"{P['address'][0]}, {P['address'][1]}",
                         "address": {"@type": "PostalAddress", "streetAddress": "Luxemburger Straße 10",
                                     "postalCode": "13353", "addressLocality": "Berlin", "addressCountry": "DE"}},
        "sameAs": [L["github"], L["linkedin"], L["scholar"], L["orcid"], L["bht_profile"]],
        "knowsAbout": C["interests"], "knowsLanguage": ["de", "en", "hi"],
        "description": md_plain(C["about"][1]),
    }
    works = []
    for p in C["publications"]:
        w = {"@type": "ScholarlyArticle", "headline": p["title"], "name": p["title"],
             "author": [{"@type": "Person", "name": a} | ({"@id": BASE + "#me"} if a == P["name"] else {})
                        for a in p["authors"]],
             "datePublished": f"{p['year']}-{p['month']:02d}", "isPartOf": p["venue"], "abstract": p["summary"]}
        if p.get("doi"):
            w["identifier"] = {"@type": "PropertyValue", "propertyID": "DOI", "value": p["doi"]}
            w["url"] = f"https://doi.org/{p['doi']}"
        elif p.get("url"):
            w["url"] = p["url"]
        if p.get("arxiv"):
            w["sameAs"] = f"https://arxiv.org/abs/{p['arxiv']}"
        works.append(w)
    graph = {"@context": "https://schema.org",
             "@graph": [{"@type": "ProfilePage", "@id": BASE, "url": BASE, "name": f"{P['name']}, {P['headline']}",
                         "dateModified": str(SITE["updated"]), "mainEntity": {"@id": BASE + "#me"}}, person] + works}
    return json.dumps(graph, ensure_ascii=False, indent=1).replace("</", "<\\/")


# ---------------------------------------------------------------- page
def page():
    L = P["links"]
    socials = [("github", "GitHub", L["github"]), ("linkedin", "LinkedIn", L["linkedin"]),
               ("google-scholar", "Google Scholar", L["scholar"]), ("orcid", "ORCID", L["orcid"]),
               ("calgo-lab", "Cognitive Algorithms Lab", L["lab"]),
               ("envelope", "Email", "mailto:" + P["email"])]
    social_html = "".join(f'<li><a href="{u}" title="{t}" aria-label="{t}"' + ('' if u.startswith("mailto") else ' rel="me noopener" target="_blank"')
                          + f'>{lab_icon() if i == "calgo-lab" else icon(i)}</a></li>' for i, t, u in socials)
    nav = [("about", "About")] + ([("news", "News")] if C.get("news") else []) + [("research", "Research"), ("publications", "Publications"), ("cv", "CV"), ("contact", "Contact")]
    nav_html = "".join(f'<li><a href="#{k}">{v}</a></li>' for k, v in nav)
    about = "".join(f"<p>{md_html(x)}</p>" for x in C["about"]).replace(
        f'<a href="{L["lab"]}">', f'<a class="lab-link" href="{L["lab"]}"><img class="inline-ic" src="assets/img/calgo-lab.png" alt="" width="20" height="20">')
    interests = "".join(f"<li>{html.escape(x)}</li>" for x in C["interests"])
    projects = "".join(f"""
      <article class="card" id="project-{pr['id']}">
        {figure_views(pr['figures'], 'card-fig') if pr.get('figures') else figure(pr['figure'], pr['caption'], 'card-fig') if pr.get('figure') else ''}
        <div class="card-body">
        <p class="card-kicker">{html.escape(pr['years'])} · {html.escape(pr['partner'])}</p>
        <h3>{html.escape(pr['title'])}</h3>
        <p>{html.escape(pr['text'])}</p>
        <ul class="tags">{''.join(f'<li>{html.escape(t)}</li>' for t in pr['tags'])}</ul>
        {('<p class="card-links">' + ''.join(f'<a href="{l["url"]}">{html.escape(l["label"])} {icon("arrow-up-right-from-square", "ic sm")}</a>' for l in pr['links']) + '</p>') if pr['links'] else ''}
        </div>
      </article>""" for pr in C["projects"])
    pubs = C["publications"]
    years = sorted({p["year"] for p in pubs}, reverse=True)
    pub_groups = "".join(f'<h3 class="year">{y}</h3><ol class="pubs">' + "".join(pub_html(p) for p in pubs if p["year"] == y) + "</ol>" for y in years)
    topics_used = [t for t in TOPICS if any(p["topic"] == t for p in pubs)]
    filters = ('<button type="button" class="filter is-on" data-filter="all" aria-pressed="true">All</button>'
               + "".join(f'<button type="button" class="filter" data-filter="{t}" aria-pressed="false">{TOPICS[t]}</button>' for t in topics_used)
               + '<button type="button" class="filter" data-filter="first" aria-pressed="false">First author</button>')
    addr = "<br>".join(html.escape(a) for a in P["address"])
    desc = (f"{P['name']} is a {P['headline']} at {P['affiliation']}, Berlin, working on robust machine learning and "
            "holistic model evaluation for environmental applications: time series forecasting, soil horizon classification "
            "and groundwater level prediction.")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{P['name']} · {P['headline']}</title>
<meta name="description" content="{html.escape(desc)}">
<meta name="author" content="{P['name']}">
<link rel="canonical" href="{BASE}">
<meta property="og:type" content="profile">
<meta property="og:title" content="{P['name']} · {P['headline']}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:url" content="{BASE}">
<meta property="og:image" content="{BASE}assets/img/og.jpg">
<meta property="profile:first_name" content="{P['given_name']}">
<meta property="profile:last_name" content="{P['family_name']}">
<meta name="twitter:card" content="summary_large_image">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#f6f7fb" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0d1220" media="(prefers-color-scheme: dark)">
<link rel="icon" href="assets/img/favicon-32.png" sizes="32x32" type="image/png">
<link rel="icon" href="assets/img/favicon-192.png" sizes="192x192" type="image/png">
<link rel="apple-touch-icon" href="assets/img/apple-touch-icon.png">
<link rel="alternate" type="text/markdown" href="cv.md" title="CV (Markdown)">
<link rel="alternate" type="text/plain" href="llms.txt" title="llms.txt">
<link rel="me" href="{L['github']}"><link rel="me" href="{L['orcid']}">
<link rel="preload" href="assets/fonts/Ubuntu-L.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="assets/css/style.css">
<script>document.documentElement.classList.add("js");try{{var t=localStorage.getItem("theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<script type="application/ld+json">
{json_ld()}
</script>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<aside class="side">
  {contours()}
  <div class="side-inner">
    <img class="avatar" src="assets/img/avatar.jpg" width="240" height="240" alt="Portrait of {P['name']}">
    <h1 class="name">{P['name']}</h1>
    <p class="role">{P['headline']}</p>
    <p class="aff"><a href="{P['affiliation_url']}">Berliner Hochschule für Technik</a><br>{P['location']}</p>
    <nav aria-label="Sections"><ul class="nav">{nav_html}</ul></nav>
    <ul class="social">{social_html}</ul>
    <button class="theme" type="button" aria-label="Toggle color theme" title="Toggle color theme">{icon('moon', 'ic moon')}{icon('sun', 'ic sun')}<span>Theme</span></button>
  </div>
</aside>
<main id="main">
  <section id="about">
    <p class="eyebrow">About</p>
    <h2>Robust machine learning for environmental applications</h2>
    {about}
    <h3 class="sub">Research interests</h3>
    <ul class="tags big">{interests}</ul>
  </section>

  {f"""<section id="news">
    <p class="eyebrow">News</p>
    <h2>Talks &amp; updates</h2>
    <ol class="news">{news_html()}</ol>
  </section>
""" if C.get("news") else ""}
  <section id="research">
    <p class="eyebrow">Research</p>
    <h2>Projects</h2>
    <div class="cards">{projects}</div>
  </section>

  <section id="publications">
    <p class="eyebrow">Publications</p>
    <h2>Papers</h2>
    <p class="lede">Also on <a href="{L['scholar']}">Google Scholar</a> and <a href="{L['orcid']}">ORCID</a>. All entries as <a href="publications.bib">BibTeX</a>.</p>
    <div class="filters" role="group" aria-label="Filter publications">{filters}</div>
    {pub_groups}
  </section>

  <section id="cv">
    <p class="eyebrow">Curriculum Vitae</p>
    <h2>CV</h2>
    {cv_html()}
  </section>

  <section id="contact">
    <p class="eyebrow">Contact</p>
    <h2>Get in touch</h2>
    <div class="contact">
      <a class="mail" href="mailto:{P['email']}">{icon('envelope')} {P['email']}</a>
      <p class="addr">{icon('location-dot')}<span>{addr}</span></p>
      <ul class="social inline">{social_html}</ul>
    </div>
  </section>

  <footer class="foot">
    <p>© {str(SITE['updated'])[:4]} {P['name']} · Updated {SITE['updated']} · No cookies, no tracking.</p>
    <p>Machine-readable: <a href="llms.txt">Plain-text profile</a> · <a href="cv.md">CV (Markdown)</a> · <a href="publications.bib">BibTeX</a> · Icons: <a href="https://fontawesome.com/license/free">Font Awesome Free</a> (CC BY 4.0)</p>
  </footer>
</main>
<script src="assets/js/site.js" defer></script>
</body>
</html>
"""


# ---------------------------------------------------------------- Markdown CV and llms.txt
def pub_md(p):
    names = []
    for i, a in enumerate(p["authors"]):
        mark = ("\\*" if i in p.get("equal", []) else "") + ("†" if i in p.get("supervision", []) else "")
        names.append((f"**{a}**" if a == P["name"] else a) + mark)
    links = " · ".join(f"[{l}]({u})" for l, u in pub_links(p))
    notes = "; ".join(pub_notes(p)).replace("*", "\\*")
    return (f"- {', '.join(names)}. *{p['title']}*. {p['venue']}{', ' + p['track'] if p.get('track') else ''}{', ' + p['place'] if p.get('place') else ''}, {p['year']}. "
            f"{links}{' (' + notes + ')' if notes else ''}\n  - Summary: {p['summary']}\n  - My contribution (CRediT): {p['contribution']}")


def cv_md():
    L = P["links"]
    out = [f"# {P['name']}, {P['headline']}", "",
           f"{P['affiliation']} · {P['location']} · <{P['email']}>", "",
           f"Web: <{BASE}> · GitHub: <{L['github']}> · LinkedIn: <{L['linkedin']}> · Google Scholar: <{L['scholar']}> · ORCID: <{L['orcid']}>",
           "", "## Profile", "", C["profile"], "", "## Research interests", "", ", ".join(C["interests"]), "", "## Experience", ""]
    for e in C["experience"]:
        out.append(f"### {e['role']}, {e['org']} ({dates(e)}, {e['place']})")
        out += [f"- {md_plain(i)}" for i in e["items"]] + [""]
    out += ["## Education", ""]
    for e in C["education"]:
        out.append(f"### {e['degree']}, {e['org']} ({dates(e)})")
        out += [f"- {i}" for i in e["items"]] + [""]
    out += ["## Research projects", ""]
    for pr in C["projects"]:
        links = " · ".join(f"[{l['label']}]({l['url']})" for l in pr["links"])
        out += [f"### {pr['title']} ({pr['years']}, {pr['partner']})", "", pr["text"] + (f" {links}" if links else ""), ""]
    out += ["## Publications", ""] + [pub_md(p) for p in C["publications"]] + [""]
    if C.get("news"):
        out += ["## News and talks", ""] + [f"- {n['date']}: [{n['title']}]({BASE}news/{n['slug']}.html) (LinkedIn: {n['url']})" for n in C["news"]] + [""]
    out += ["## Service", ""] + [f"- {s['role']}, {s['org']} ({s['when']}): {s['text']}" for s in C["service"]] + [""]
    out += ["## Skills", ""] + [f"- {s['label']}: {s['value']}" for s in C["skills"]] + [""]
    out += ["## Languages", ""] + [f"- {s['label']}: {s['value']}" for s in C["languages"]] + [""]
    out += [f"_Last updated {SITE['updated']}. PDF: <{BASE}{CV_PDF}>_", ""]
    return "\n".join(out)


def llms_txt():
    """Plain-text profile for AI agents, following the llms.txt convention (https://llmstxt.org)."""
    L = P["links"]

    def pub_url(p):
        return f"https://doi.org/{p['doi']}" if p.get("doi") else p.get("url") or f"https://arxiv.org/abs/{p['arxiv']}"

    def role(p):
        i, eq = p["authors"].index(P["name"]), p.get("equal", [])
        if i in eq:
            pos = "listed first" if i == 0 else f"listed {['first', 'second', 'third'][i]}"
            return f"co-first author (equal contribution, {pos})"
        if i == 0:
            return "first author"
        return f"co-author (author {i + 1} of {len(p['authors'])})"

    out = [
        f"# {P['name']}", "",
        f"> {P['name']} is a {P['headline']} at {P['affiliation']} in Berlin, Germany, supervised by "
        f"Prof. Dr. Felix Bießmann in the Cognitive Algorithms Lab. The research develops machine learning for "
        f"environmental monitoring (urban sewer systems, soil science, groundwater) and evaluates it holistically: "
        f"predictive performance, model complexity and robustness when data are incomplete, noisy or sparse.", "",
        f"Website: {BASE}. Last updated: {SITE['updated']}.", "",
        "## Contact", "",
        f"- Email: {P['email']}",
        f"- Office: {', '.join(P['address'])}",
        f"- GitHub: {L['github']}", f"- LinkedIn: {L['linkedin']}",
        f"- Google Scholar: {L['scholar']}", f"- ORCID: {L['orcid']}", "",
        "## Key pages", "",
        f"- [CV in Markdown]({BASE}cv.md): experience, education, projects, publications with per-paper contribution "
        f"statements (CRediT), news and talks",
        f"- [CV as PDF]({BASE}{CV_PDF}): formatted for print; [short version]({BASE}{CV_SHORT_PDF})",
        f"- [Publications in BibTeX]({BASE}publications.bib): all {len(C['publications'])} publications",
        f"- [Homepage]({BASE}): the same content as HTML, with schema.org JSON-LD (Person, ScholarlyArticle)", "",
        "## Research interests", "", ", ".join(C["interests"]) + ".", "",
        "## Research projects", "",
    ]
    for pr in C["projects"]:
        links = "; ".join(f"{l['label']}: {l['url']}" for l in pr["links"])
        out.append(f"- {pr['title']} ({pr['years']}, {pr['partner']}). {' '.join(pr['text'].split())}"
                   + (f" {links}." if links else ""))
    out += ["", "## Publications", ""]
    for p in C["publications"]:
        out.append(f"- [{p['title']}]({pub_url(p)}). {', '.join(p['authors'])}. {p['venue']}, {p['year']}. "
                   f"{p['type']} paper{' (' + p['track'] + ')' if p.get('track') else ''}; {P['name']} is {role(p)}.")
    if C.get("news"):
        out += ["", "## News and talks", ""]
        out += [f"- {n['date']}: [{n['title']}]({BASE}news/{n['slug']}.html)" for n in C["news"]]
    out += ["", "## Optional", "",
            f"- [Cognitive Algorithms Lab]({L['lab']}): research group at BHT",
            f"- [Berlin Initiative for Applied Foundation Model Research profile]({L['bht_profile']})",
            "- [SoilNet live demo](https://soilnet.demo.calgo-lab.de/): AI-assisted soil horizon annotation",
            "- [RIWWER live demo](https://riwwer.demo.calgo-lab.de/): sewer overflow forecasting dashboard", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- LaTeX CVs
def tex_pub(p, full):
    names = []
    for i, a in enumerate(p["authors"]):
        mark = ("$^*$" if i in p.get("equal", []) else "") + (r"$^\dagger$" if i in p.get("supervision", []) else "")
        names.append((rf"\textbf{{{tex(a)}}}" if a == P["name"] else tex(a)) + mark)
    link = (rf" \href{{https://doi.org/{p['doi']}}}{{\nolinkurl{{doi:{p['doi']}}}}}" if p.get("doi")
            else rf" \href{{https://arxiv.org/abs/{p['arxiv']}}}{{\nolinkurl{{arXiv:{p['arxiv']}}}}}" if p.get("arxiv") else "")
    s = rf"  \item {', '.join(names)}. \textit{{{tex(p['title'])}}}. {tex(p['venue_short'] if not full else p['venue'])}{', ' + tex(p['track']) if p.get('track') else ''}, {p['year']}.{link}"
    notes = "; ".join(pub_notes(p)).replace("*", r"$^*$").replace("†", r"$^\dagger$")
    if notes:
        s += rf" {{\small\textcolor{{muted}}{{({notes})}}}}"
    if full:
        s += ("\n    \\begin{itemize}\n"
              rf"      \item \textit{{Summary:}} {tex(p['summary'])}" "\n"
              rf"      \item \textit{{My contribution:}} {tex(p['contribution'])}" "\n    \\end{itemize}")
    return s


def cv_tex(full=True):
    L = P["links"]
    exp = "\n".join(
        rf"\entry{{{tex(e['role'])}}}{{{tex(e['org'])}}}{{{dates(e)}}}{{{tex(e['place'])}}}" + "\n"
        + (("\\begin{itemize}\n" + "\n".join(rf"  \item {md_tex(i)}" for i in (e["items"] if full else e["items"][:3])) + "\n\\end{itemize}") if e["items"] else "")
        for e in C["experience"])
    edu = "\n".join(
        rf"\entry{{{tex(e['degree'])}}}{{{tex(e['org'])}}}{{{dates(e)}}}{{}}" + "\n"
        + "\\begin{itemize}\n" + "\n".join(rf"  \item {md_tex(i)}" for i in e["items"]) + "\n\\end{itemize}"
        for e in C["education"])
    projects = "\n".join(
        rf"\textbf{{{tex(pr['title'])}}} \textcolor{{muted}}{{({tex(pr['years'])}, {tex(pr['partner'])})}}"
        + ("\\\\\n" if full or pr["links"] else "")
        + (tex(pr["text"]) if full else "")
        + ((" " if full else "") + r" \textbf{\textperiodcentered} ".join(rf"\href{{{l['url']}}}{{{tex(l['label'])}}}" for l in pr["links"]) if pr["links"] else "")
        + "\\par\\smallskip"
        for pr in C["projects"])
    pubs = "\n".join(tex_pub(p, full) for p in C["publications"])
    service = ("\\section*{Service}\n" + "\n".join(rf"{tex(s['role'])}, {tex(s['org'])} \textcolor{{muted}}{{({tex(s['when'])})}}. {tex(s['text'])}" for s in C["service"])) if full else ""
    skills = "\\\\\n".join(rf"\textbf{{{tex(s['label'])}:}} {tex(s['value'])}" for s in C["skills"])
    langs = r" \quad\textbf{\textperiodcentered}\quad ".join(rf"\textbf{{{s['label']}:}} {s['value']}" for s in C["languages"])
    return rf"""% Generated by scripts/build.py from content.yaml. Do not edit by hand.
% !TEX program = lualatex
\documentclass[a4paper,10pt]{{article}}
\usepackage[margin=1.4cm]{{geometry}}
\usepackage{{enumitem,titlesec,xcolor,fontspec,graphicx,fontawesome5,xurl,needspace}}
\urlstyle{{same}}
\usepackage[hidelinks]{{hyperref}}
\setlength{{\parindent}}{{0pt}}\setlength{{\parskip}}{{4pt}}
\setlist[itemize]{{noitemsep, topsep=0pt, leftmargin=1.5em}}
\setlist[enumerate]{{topsep=2pt, itemsep=3pt, leftmargin=1.6em}}
\renewcommand{{\baselinestretch}}{{1.05}}
\definecolor{{primary}}{{HTML}}{{27438D}}\definecolor{{muted}}{{HTML}}{{5A5A5A}}\definecolor{{headerbg}}{{HTML}}{{C3DFF1}}
\setmainfont{{Ubuntu}}[Path=fonts/, Extension=.ttf, UprightFont=Ubuntu-L, BoldFont=Ubuntu-B, ItalicFont=Ubuntu-LI, BoldItalicFont=Ubuntu-BI]
\hypersetup{{colorlinks=true, urlcolor=primary, linkcolor=primary,
  pdftitle={{{P['name']}, CV}}, pdfauthor={{{P['name']}}}, pdfsubject={{Curriculum Vitae}},
  pdfkeywords={{{', '.join(C['interests'])}}}}}
\titleformat{{\section}}{{\needspace{{6\baselineskip}}\Large\bfseries\color{{primary}}}}{{}}{{0em}}{{}}[\color{{primary}}\titlerule]
\titlespacing*{{\section}}{{0pt}}{{{'10pt' if full else '7pt'}}}{{3pt}}
\newcommand{{\entry}}[4]{{\textbf{{#1}} \hfill \textcolor{{muted}}{{#3}}\\\textcolor{{muted}}{{#2\ifx&#4&\else\ \textbf{{\textperiodcentered}}\ #4\fi}}\par}}
\begin{{document}}
\setlength{{\fboxsep}}{{8pt}}
\noindent\colorbox{{headerbg}}{{\parbox{{\dimexpr\linewidth-2\fboxsep\relax}}{{%
  \begin{{minipage}}[c]{{0.2\linewidth}}\includegraphics[width=\linewidth]{{portrait.jpg}}\end{{minipage}}\hfill
  \begin{{minipage}}[c]{{0.76\linewidth}}
    {{\LARGE\textbf{{{P['name']}}}}}\\[3pt]
    \textbf{{{tex(P['cv_title'])}}}\\[1pt]
    {tex(P['headline'])}, {tex(P['affiliation'])}\\[5pt]
    \faMapMarker*\ {tex(P['location'])}\qquad \faEnvelope\ \href{{mailto:{P['email']}}}{{{P['email']}}}\\
    \faGlobe\ \href{{{BASE}}}{{{BASE.replace('https://', '').rstrip('/')}}}\qquad \faGithub\ \href{{{L['github']}}}{{{L['github'].replace('https://', '')}}}\\
    \faLinkedin\ \href{{{L['linkedin']}}}{{{L['linkedin'].replace('https://www.', '')}}}\\
    \faGraduationCap\ \href{{{L['scholar']}}}{{Google Scholar}}\qquad \faOrcid\ \href{{{L['orcid']}}}{{{L['orcid'].replace('https://', '')}}}
  \end{{minipage}}}}}}

\section*{{Profile}}
{tex(C['profile'] if full else C['profile_short'])}

\section*{{Experience}}
{exp}

\section*{{Education}}
{edu}

\section*{{Research Projects}}
{projects}

\section*{{Publications}}
\begin{{enumerate}}
{pubs}
\end{{enumerate}}
{service}

\section*{{{'Skills' if full else 'Skills and Languages'}}}
{skills}{'' if full else chr(92) + chr(92) + chr(10) + r'\textbf{Languages:} ' + ', '.join(f"{s['label']} ({s['value'].lower()})" for s in C['languages'])}
{('\\section*{Languages}' + chr(10) + langs) if full else ''}

\vfill{{\footnotesize\textcolor{{muted}}{{Last updated {SITE['updated']}. Current version: \href{{{BASE}}}{{{BASE.replace('https://', '').rstrip('/')}}}}}}}
\end{{document}}
"""


def build_pdfs():
    for name, full in [("Vipin_Singh_CV", True), ("Vipin_Singh_CV_short", False)]:
        (ROOT / "cv" / f"{name}.tex").write_text(cv_tex(full), encoding="utf-8")
        r = subprocess.run(["latexmk", "-lualatex", "-interaction=nonstopmode", "-halt-on-error", f"{name}.tex"],
                           cwd=ROOT / "cv", capture_output=True, text=True)
        if r.returncode:
            sys.exit(r.stdout[-3000:])
        subprocess.run(["latexmk", "-c", f"{name}.tex"], cwd=ROOT / "cv", capture_output=True)
        print("built", f"cv/{name}.pdf")


def main():
    for p in C["publications"]:
        assert p["topic"] in TOPICS and p["type"] in TYPE_ORDER, p["key"]
    (ROOT / "index.html").write_text(page(), encoding="utf-8")
    (ROOT / "cv.md").write_text(cv_md(), encoding="utf-8")
    (ROOT / "llms.txt").write_text(llms_txt(), encoding="utf-8")
    (ROOT / "publications.bib").write_text("\n\n".join(bibtex(p) for p in C["publications"]) + "\n", encoding="utf-8")
    news = C.get("news", [])
    (ROOT / "news").mkdir(exist_ok=True)
    for old in (ROOT / "news").glob("*.html"):
        old.unlink()
    for i, n in enumerate(news):
        (ROOT / "news" / f"{n['slug']}.html").write_text(
            news_page(n, news[i - 1] if i > 0 else None, news[i + 1] if i + 1 < len(news) else None), encoding="utf-8")
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {BASE}sitemap.xml\n")
    urls = ["", "cv.md", "llms.txt", "publications.bib", CV_PDF, CV_SHORT_PDF] + [f"news/{n['slug']}.html" for n in news]
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{BASE}{u}</loc><lastmod>{SITE['updated']}</lastmod></url>\n" for u in urls) + "</urlset>\n")
    (ROOT / ".nojekyll").write_text("")
    host = BASE.split("/")[2]
    if not host.endswith(".github.io"):  # custom domain for GitHub Pages
        (ROOT / "CNAME").write_text(host + "\n")
    for name, full in [("Vipin_Singh_CV", True), ("Vipin_Singh_CV_short", False)]:
        (ROOT / "cv" / f"{name}.tex").write_text(cv_tex(full), encoding="utf-8")
    print("built index.html, cv.md, llms.txt, publications.bib, sitemap.xml, robots.txt, cv/*.tex")
    if "--pdf" in sys.argv:
        if not shutil.which("latexmk"):
            sys.exit("latexmk not found: install TeX Live / MacTeX to build the PDFs")
        build_pdfs()


if __name__ == "__main__":
    main()
