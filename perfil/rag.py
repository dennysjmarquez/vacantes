#!/usr/bin/env python3
"""RAG local sobre el corpus de perfil. Cero dependencias, cero red, cero modelos.

  python3 perfil/rag.py build
  python3 perfil/rag.py q "consulta en espanol o ingles" [-k 5] [--full]

Recuperacion hibrida: BM25 (lexical) + coseno TF-IDF (semantico suave), fundidos por RRF.
Los chunks conservan la fuente de origen, asi que toda respuesta es citable.
"""
import sys, re, json, math, pathlib, collections, unicodedata

BASE = pathlib.Path(__file__).resolve().parent
RAW = BASE / "cv_full.txt"
IDX = BASE / "rag_index.json"
CHUNK = 1400          # caracteres por chunk
STOP = set("""de la que el en y a los del se las por un para con no una su al lo como mas pero sus le ya
o esta yo tengo tengo entre cuando fue ser son ser sido the and of to in for is on with that this by
from at it as be are was were have has had you your i we they their our an or not can will""".split())
SUF = ("ando", "iendo", "ados", "idas", "acion", "iones", "mente", "idad", "es", "ar", "er", "ir",
       "ar", "se", "la", "el", "os", "as", "es", "s")

def norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")

def stem(w):
    for s in SUF:
        if len(w) > len(s) + 3 and w.endswith(s):
            return w[:-len(s)]
    return w

def toks(t):
    return [stem(w) for w in re.findall(r"[a-zñ0-9+#\.]{3,}", norm(t)) if w not in STOP]

def chunks():
    text = RAW.read_text(encoding="utf-8", errors="replace")
    out, n = [], 0
    for b in re.split(r"^### FUENTE:\s*", text, flags=re.M)[1:]:
        lines = b.split("\n")
        titulo = re.sub(r"\s*###\s*$", "", lines[0]).strip()
        head = "\n".join(lines[1:4])
        tipo = (re.search(r"TIPO:\s*([^|]+)", head) or [None, "?"])[1].strip()
        url = (re.search(r"URL:\s*(\S+)", head) or [None, ""])[1].strip()
        cuerpo = re.split(r"^=== FIN_FUENTE ===", "\n".join(lines[1:]), flags=re.M)[0]
        cuerpo = re.sub(r"^###.*?###\s*$", "", cuerpo, flags=re.M).strip()
        for i in range(0, len(cuerpo), CHUNK):
            piece = cuerpo[i:i + CHUNK]
            if len(piece) < 120:
                continue
            n += 1
            out.append({"id": n, "fuente": titulo[:110], "tipo": tipo, "url": url, "text": piece})
    return out

def build():
    cs = chunks()
    df = collections.Counter()
    docs = []
    for c in cs:
        tf = collections.Counter(toks(c["text"]))
        for t in tf:
            df[t] += 1
        docs.append({"id": c["id"], "fuente": c["fuente"], "tipo": c["tipo"], "url": c["url"],
                     "text": c["text"], "tf": dict(tf), "len": sum(tf.values())})
    N = len(docs)
    # PPMI por coocurrencia intra-chunk: la capa "semantica" sin embeddings.
    co = {}
    if "--ppmi" not in sys.argv:
        IDX.write_text(json.dumps({"N": N, "df": dict(df), "docs": docs}), encoding="utf-8")
        print(f"indice: {N} chunks ({IDX.stat().st_size/1e6:.1f} MB, lexico puro)")
        return
    pairs = collections.Counter()
    common = {t for t, c in df.items() if 3 <= c <= 200}
    for doc in docs:
        ts = sorted(doc["tf"], key=lambda t: -doc["tf"][t])
        ts = [t for t in ts if t in common][:110]
        for i, a in enumerate(ts):
            for b in ts[i + 1:]:
                pairs[(a, b) if a < b else (b, a)] += 1
    co = collections.defaultdict(dict)
    tot = sum(pairs.values()) or 1
    for (a, b), c in pairs.items():
        if c < 3:
            continue
        ppmi = max(0.0, math.log((c / tot) * (N * N) / max(df[a], 1) / max(df[b], 1)) / math.log(2))
        for k, o in ((a, b), (b, a)):
            if len(co[k]) < 10 or ppmi > min(co[k].values()):
                co[k][o] = round(ppmi, 3)
        for k in list(co):
            if len(co[k]) > 10:
                co[k] = dict(sorted(co[k].items(), key=lambda x: -x[1])[:10])
    IDX.write_text(json.dumps({"N": N, "df": dict(df), "docs": docs,
                               "co": {k: v for k, v in co.items()}}), encoding="utf-8")
    print(f"indice: {N} chunks de {len(df)} terminos ({IDX.stat().st_size/1e6:.1f} MB cache)")

def load():
    if not IDX.exists():
        build()
    return json.loads(IDX.read_text(encoding="utf-8"))

def search(q, k=5):
    d = load()
    N, df = d["N"], d["df"]
    qt = collections.Counter(toks(q))
    avg = sum(x["len"] for x in d["docs"]) / max(N, 1)
    k1, b = 1.5, 0.75
    co = d.get("co", {})
    qv = {}
    for t, f in qt.items():
        idf = math.log(1 + (N - df.get(t, 0) + .5) / (df.get(t, 0) + .5))
        qv[t] = idf * f
        for o, w in sorted(co.get(t, {}).items(), key=lambda x: -x[1])[:4]:
            if o not in qt:
                qv[o] = max(qv.get(o, 0), idf * 0.35 * w)
    qn = math.sqrt(sum(v * v for v in qv.values())) or 1
    hits = []
    for doc in d["docs"]:
        s, tfd, ln = 0.0, doc["tf"], doc["len"]
        for t, qw in qv.items():
            f = tfd.get(t)
            if not f:
                continue
            idf = math.log(1 + (N - df.get(t, 0) + .5) / (df.get(t, 0) + .5))
            s += qw * (f * (k1 + 1) / (f + k1 * (1 - b + b * ln / avg)))
        cos = 0.0
        if s:
            dn = math.sqrt(sum((v * math.log(1 + (N - df.get(t, 0) + .5) / (df.get(t, 0) + .5))) ** 2
                               for t, v in tfd.items())) or 1
            cos = sum(qv[t] * tfd[t] * math.log(1 + (N - df.get(t, 0) + .5) / (df.get(t, 0) + .5))
                      for t in qv if t in tfd) / (qn * dn)
        if s > 0:
            hits.append((doc["id"], s, cos, doc))
    bm25rank = {h[0]: i for i, h in enumerate(sorted(hits, key=lambda x: -x[1]))}
    cosrank = {h[0]: i for i, h in enumerate(sorted(hits, key=lambda x: -x[2]))}
    fused = sorted(hits, key=lambda h: -(1 / (60 + bm25rank[h[0]]) + 1 / (60 + cosrank[h[0]])))
    return fused[:k]

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "build":
        build(); sys.exit(0)
    if a[0] == "q":
        q = a[1]; k = int(a[a.index("-k") + 1]) if "-k" in a else 5
        full = "--full" in a
        res = search(q, k)
        print(f"\n=== {len(res)} fragmentos para: {q}\n")
        if not res:
            print("(nada coincide - prueba con otros terminos o menos especificos)")
        for h in sorted(res, key=lambda x: -x[1])[:k]:
            _, s, cos, doc = h
            print(f"[bm25 {s:5.1f} | cos {cos:.3f}] {doc['tipo']:<13} {doc['fuente'][:78]}")
            print(f"   {doc['text'][:230] if not full else doc['text'][:1600]}")
            if doc["url"] and doc["url"] != "N/A":
                print(f"   url: {doc['url'][:110]}")
            print()
