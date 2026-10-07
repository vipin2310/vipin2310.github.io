# vipin2310.github.io

Personal academic website of Vipin Singh, served by GitHub Pages at <https://vipin-singh.bio> (repo `vipin2310.github.io`, custom domain via `CNAME`).

Plain static HTML/CSS/JS, no Jekyll, no external requests (fonts and icons are self-hosted, no cookies or tracking).

## Edit

Everything (bio, projects, publications, CV) lives in **`content.yaml`**. After editing:

```bash
uv run scripts/build.py --pdf   # rebuilds index.html, cv.md, llms.txt, publications.bib, sitemap.xml and both CV PDFs
python3 -m http.server          # preview at http://localhost:8000
```

`--pdf` needs LuaLaTeX (MacTeX / TeX Live). Without it, the website files are still rebuilt.

News posts copied from LinkedIn may contain short links (`https://lnkd.in/...`); `uv run --no-project python scripts/resolve_lnkd.py`
replaces them in `content.yaml` with the real URLs.
Do not edit the generated files (`index.html`, `cv.md`, `llms.txt`, `publications.bib`, `sitemap.xml`, `cv/*.tex`) by hand.

## Deploy

1. Create a public repository named `vipin2310.github.io` on GitHub.
2. `git add -A && git commit -m "Initial site" && git push -u origin main`
3. Repository → Settings → Pages → Source: *Deploy from a branch*, branch `main`, folder `/ (root)`.

The domain comes from `site.url` in `content.yaml`; the build writes `CNAME` from it. DNS is set at IONOS (see below).

## DNS (IONOS)

| Host | Type | Value |
|---|---|---|
| `@` | A | `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153` |
| `@` | AAAA | `2606:50c0:8000::153`, `2606:50c0:8001::153`, `2606:50c0:8002::153`, `2606:50c0:8003::153` |
| `www` | CNAME | `vipin2310.github.io` |

Remove the IONOS default A/AAAA records for `@` and `www` first.

## For humans and for agents

- Human visitors: browsable CV, publication filters, BibTeX copy, light/dark theme following the OS (toggle remembered per browser).
- Machines: schema.org JSON-LD (`Person`, `ScholarlyArticle`) in `index.html`, [`llms.txt`](llms.txt), a Markdown CV [`cv.md`](cv.md),
  [`publications.bib`](publications.bib), `sitemap.xml` and `robots.txt`. All content is in the static HTML, so it works without JavaScript.

## Credits

Fonts: Ubuntu (Ubuntu Font Licence 1.0, `assets/fonts/UFL.txt`). Icons: Font Awesome Free (CC BY 4.0).
