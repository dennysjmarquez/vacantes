#!/usr/bin/env python3
"""Indexador del corpus de perfil. Local, sin red. Produce un mapa del territorio
para decidir que vale la pena leer completo en vez de tragar 1.47 MB a ciegas."""
import re, json, collections, pathlib

SRC = pathlib.Path(__file__).resolve().parent / "cv_full.txt"
OUT = pathlib.Path(__file__).resolve().parent / "indice.md"
text = SRC.read_text(encoding="utf-8", errors="replace")

# Separar fuentes: empiezan en "### FUENTE: ..." y terminan en "=== FIN_FUENTE ==="
blocks = re.split(r"^### FUENTE:\s*", text, flags=re.M)[1:]
fuentes = []
for b in blocks:
    lines = b.split("\n")
    titulo = re.sub(r"\s*###\s*$", "", lines[0]).strip()
    cuerpo = "\n".join(lines[1:])
    cuerpo = re.split(r"^=== FIN_FUENTE ===", cuerpo, flags=re.M)[0]
    def field(pat):
        m = re.search(pat, b, flags=re.M)
        return m.group(1).strip() if m else ""
    tipo = field(r"### TIPO:\s*([^|]+)")
    url = field(r"URL:\s*([^\s|]+)")
    chars = field(r"CARACTERES:\s*(\d+)")
    kw = field(r"### KEYWORDS:\s*(.+)")
    fuentes.append({
        "titulo": titulo, "tipo": tipo, "url": url,
        "chars": int(chars) if chars.isdigit() else len(cuerpo),
        "keywords": [k.strip() for k in kw.split(",") if k.strip()],
        "n_lineas": cuerpo.count("\n"),
    })

por_tipo = collections.Counter(f["tipo"] for f in fuentes)
por_dominio = collections.Counter(
    (re.sub(r"^www\.", "", re.match(r"https?://([^/]+)", f["url"]).group(1)) if re.match(r"https?://", f["url"] or "") else "sin-url")
    for f in fuentes)
tech = collections.Counter(k.lower() for f in fuentes for k in f["keywords"])
totales = collections.Counter()

dup = collections.Counter(re.sub(r"[^a-z0-9]", "", f["titulo"].lower())[:60] for f in fuentes)
repetidas = {k: v for k, v in dup.items() if v > 1}

L = [f"# Indice del corpus de perfil\n",
     f"- **Tamano:** {len(text):,} caracteres / {text.count(chr(10)):,} lineas",
     f"- **Fuentes detectadas:** {len(fuentes)}",
     f"- **Caracteres de contenido:** {sum(f['chars'] for f in fuentes):,}",
     f"- **Titulos duplicados:** {len(repetidas)}\n",
     "## Tipos de fuente\n"]
L += [f"- {t or '(vacio)'}: {c}" for t, c in por_tipo.most_common()]
L += ["\n## Dominios de origen\n"]
L += [f"- {d}: {c}" for d, c in por_dominio.most_common(14)]
L += ["\n## Conceptos mas frecuentes en KEYWORDS (top 40)\n"]
L += [f"- {k}: {c}" for k, c in tech.most_common(40)]
L += ["\n## Las fuentes mas grandes (candidatas a leer completas)\n"]
for f in sorted(fuentes, key=lambda x: -x["chars"])[:18]:
    L.append(f"- `{f['chars']:>6}` chars · {f['tipo']:<14} · {f['titulo'][:88]}")
L += ["\n## Las 20 fuentes mas cortas (probable relleno / low signal)\n"]
for f in sorted(fuentes, key=lambda x: x["chars"])[:20]:
    L.append(f"- `{f['chars']:>6}` chars · {f['tipo']:<14} · {f['titulo'][:80]}")

OUT.write_text("\n".join(L), encoding="utf-8")
print(f"fuentes={len(fuentes)} tipos={dict(por_tipo)}")
print(f"chars_totales={sum(f['chars'] for f in fuentes):,} duplicados={len(repetidas)}")
print("dominios:", dict(por_dominio.most_common(8)))
print("\nTOP TECH:", ", ".join(f"{k}({c})" for k, c in tech.most_common(28)))
pathlib.Path(__file__).with_name("fuentes.json").write_text(
    json.dumps(fuentes, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\nindice -> {OUT.name}   ({len(OUT.read_text()):,} chars)")
