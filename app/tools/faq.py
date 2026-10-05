"""Build docs/faq.html from docs/faq.md.

  python3 tools/faq.py ../docs

faq.md is the source: people, search engines and agents can read it as it is.
This script turns it into the FAQ page with the site's header and footer, an anchor
for every question and schema.org FAQPage data (JSON-LD) built from the same text,
so the page and the structured data never disagree. It understands only the bit of
Markdown faq.md uses: ## sections, ### questions with {#id}, paragraphs, "- " lists,
`code`, **bold**, *italic*, [links](url) and bare https:// URLs.
"""
import html
import json
import os
import re
import sys

SITE = "https://claudegotchi.lottes.dev"


def inline(text):
    out, pos = [], 0
    # code spans first, so nothing inside them is touched
    for m in re.finditer(r"`([^`]+)`", text):
        out.append(_inline_plain(text[pos:m.start()]))
        out.append(f"<code>{html.escape(m.group(1), quote=False)}</code>")
        pos = m.end()
    out.append(_inline_plain(text[pos:]))
    return "".join(out)


def _inline_plain(text):
    links = []

    def keep(label, url):
        links.append(f'<a href="{html.escape(url)}">{html.escape(label, quote=False)}</a>')
        return f"\0{len(links) - 1}\0"

    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", lambda m: keep(m.group(1), m.group(2)), text)
    text = re.sub(r"https://[^\s)<]*[^\s).,;:<]", lambda m: keep(m.group(0), m.group(0)), text)
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)
    return re.sub(r"\0(\d+)\0", lambda m: links[int(m.group(1))], text)


def blocks(lines):
    """Paragraphs and lists → HTML."""
    out, para, items = [], [], []

    def flush():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>")
            items.clear()

    for line in lines:
        line = line.rstrip()
        if not line:
            flush()
        elif line.startswith("- "):
            if para:
                flush()
            items.append(line[2:])
        else:
            if items:
                flush()
            para.append(line)
    flush()
    return "\n".join(out)


def parse(md):
    title, intro, sections = "", [], []
    q = None
    for line in md.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            name = line[3:].strip()
            sections.append({"name": name, "id": re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"),
                             "questions": []})
            q = None
        elif line.startswith("### "):
            m = re.match(r"### (.+?)\s*\{#([\w-]+)\}\s*$", line)
            if not m:
                sys.exit(f"faq.md: question without {{#id}}: {line}")
            q = {"q": m.group(1), "id": m.group(2), "lines": []}
            sections[-1]["questions"].append(q)
        elif q is not None:
            q["lines"].append(line)
        elif not sections:
            intro.append(line)
    return title, intro, sections


def text_of(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment))


def build(docs):
    with open(os.path.join(docs, "faq.md"), encoding="utf-8") as f:
        title, intro, sections = parse(f.read())
    with open(os.path.join(docs, "docs.html"), encoding="utf-8") as f:
        template = f.read()
    head = template[:template.index("<main")]
    foot = template[template.index("  <footer"):]

    ids = [q["id"] for s in sections for q in s["questions"]]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        sys.exit(f"faq.md: duplicate ids {sorted(dupes)}")

    entities, body, toc = [], [], []
    for n, s in enumerate(sections, 1):
        toc.append(f'<li><a href="#{s["id"]}">{html.escape(s["name"])}</a></li>')
        body.append(f'      <h2 id="{s["id"]}" data-n="{n:02d}">{html.escape(s["name"])}</h2>')
        for q in s["questions"]:
            answer = blocks(q["lines"])
            # links inside the page become absolute for the structured data
            absolute = re.sub(r'href="#', f'href="{SITE}/faq.html#', answer)
            entities.append({"@type": "Question", "name": text_of(inline(q["q"])),
                             "url": f"{SITE}/faq.html#{q['id']}",
                             "acceptedAnswer": {"@type": "Answer", "text": absolute}})
            body.append(f'      <section class="faq-q" id="{q["id"]}">\n'
                        f'        <h3><a class="anchor" href="#{q["id"]}">{inline(q["q"])}</a></h3>\n'
                        f'        {answer}\n      </section>')

    ld = {"@context": "https://schema.org", "@type": "FAQPage", "name": title,
          "url": f"{SITE}/faq.html", "inLanguage": "en", "mainEntity": entities}
    ld_json = json.dumps(ld, ensure_ascii=False, indent=1).replace("</", "<\\/")

    head = re.sub(r"<title>.*?</title>", "<title>FAQ · Claudegotchi</title>", head)
    head = re.sub(r'<meta name="description" content="[^"]*">',
                  '<meta name="description" content="Answers to setup questions and problems with '
                  'Claudegotchi on macOS, Linux and Windows: USB, drivers, Python, the Claude Code '
                  'plugin, Wi-Fi, the cloud relay, battery and updates.">', head)
    head = head.replace('<link rel="stylesheet" href="style.css">',
                        '<link rel="stylesheet" href="style.css">\n'
                        f'  <link rel="canonical" href="{SITE}/faq.html">\n'
                        '  <link rel="alternate" type="text/markdown" href="faq.md" title="FAQ as Markdown">\n'
                        f'  <script type="application/ld+json">\n{ld_json}\n  </script>')
    head = head.replace(' aria-current="page"', "")
    head = head.replace('<a href="faq.html">', '<a href="faq.html" aria-current="page">')

    # the Markdown points readers to this page; the page itself does not need to
    lead = re.sub(r"\s*The same text is on \S+", "", " ".join(l for l in intro if l.strip()))
    page = (head
            + '<main class="wrap docs">\n'
            + '    <nav class="toc" aria-label="On this page">\n      <ul>\n        '
            + "\n        ".join(toc) + "\n      </ul>\n    </nav>\n\n"
            + '    <div class="docs-body">\n'
            + "      <h1>FAQ</h1>\n"
            + f'      <p class="lead">{inline(lead)}</p>\n'
            + '      <p class="mono faq-src">Also as plain Markdown: <a href="faq.md">faq.md</a> · '
              'for agents: <a href="llms.txt">llms.txt</a></p>\n\n'
            + "\n".join(body) + "\n    </div>\n  </main>\n\n"
            + foot)
    with open(os.path.join(docs, "faq.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print(f"faq.html: {len(entities)} questions in {len(sections)} sections")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "../docs")
