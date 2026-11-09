"""Bundle the dependency-free site into an HTML file users can open directly."""
from __future__ import annotations

import base64
from pathlib import Path
import re


def build(destination: Path | None = None) -> Path:
    site = Path(__file__).resolve().parents[1]
    destination = destination or site.parent / "web" / "onda-sin-instalar-v1.html"
    html = (site / "index.html").read_text()
    css = (site / "assets/styles.css").read_text()
    scripts = [(site / "assets" / name).read_text() for name in ["audio-engine.js", "app.js"]]
    assert "</style" not in css.lower()
    assert all("</script" not in code.lower() for code in scripts)
    html, count = re.subn(r'<link\b[^>]*href=["\']\./assets/styles\.css["\'][^>]*>',
                          lambda _: "<style>\n" + css + "\n</style>", html)
    assert count == 1, "Expected exactly one local stylesheet"
    html, count = re.subn(r'<script\b[^>]*src=["\']\./assets/(?:audio-engine|app)\.js["\'][^>]*>\s*</script>',
                          "", html)
    assert count == 2, "Expected the two browser-only scripts"
    favicon = base64.b64encode((site / "assets/favicon.svg").read_bytes()).decode()
    html = html.replace("./assets/favicon.svg", "data:image/svg+xml;base64," + favicon)
    html = html.replace('href="./"', 'href="#"')
    assert html.count("</body>") == 1
    html = html.replace("</body>", "\n" + "\n".join("<script>\n" + code + "\n</script>" for code in scripts) + "\n</body>")
    assert not re.search(r'<(?:script|link)\b[^>]*(?:src|href)=["\']\./assets/', html)
    html = re.sub(r"(?m)^[ \t]+$", "", html)
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(html)
    return destination


if __name__ == "__main__":
    path = build()
    print(f"Standalone HTML: {path} ({path.stat().st_size} bytes)")
