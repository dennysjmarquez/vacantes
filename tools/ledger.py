#!/usr/bin/env python3
"""Ledger de vacantes: dedupe, estado y conteos. 100% offline, cero dependencias.

Filosofia: la red es cara, el disco es barato. Este script NUNCA sale a internet.
Recibe lo que el agente ya traje (fetch_page / web_search) y mantiene la verdad local.
"""
import json, sys, collections, pathlib, argparse

DB = pathlib.Path(__file__).resolve().parent.parent / "data" / "vacantes_vistas.jsonl"

def load():
    rows = {}
    if DB.exists():
        for line in DB.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                r = json.loads(line)
                rows[r["key"]] = r
    return rows

def key_of(url, title=None, company=None):
    """Identidad estable: la URL manda. Si no hay URL, fallback titulo|empresa."""
    if url:
        return url.split("#")[0].rstrip("/").lower()
    return f"{(title or '').strip().lower()}|{(company or '').strip().lower()}"

def upsert(incoming):
    rows = load()
    nuevos, repetidas = [], []
    for r in incoming:
        k = r.get("key") or key_of(r.get("url"), r.get("title"), r.get("company"))
        r["key"] = k
        if k in rows:
            repetidas.append(k)
            rows[k].update({kk: vv for kk, vv in r.items() if vv})  # no pisar con vacios
        else:
            r.setdefault("estado", "nueva")
            nuevos.append(k)
            rows[k] = r
    DB.parent.mkdir(parents=True, exist_ok=True)
    with DB.open("w", encoding="utf-8") as f:
        for k in sorted(rows):
            f.write(json.dumps(rows[k], ensure_ascii=False, sort_keys=True) + "\n")
    return len(rows), nuevos, repetidas

def stats():
    rows = load()
    print(f"total registradas: {len(rows)}")
    for campo in ("fuente", "estado"):
        c = collections.Counter(r.get(campo, "?") for r in rows.values())
        print(f"  {campo}: " + ", ".join(f"{k}={v}" for k, v in c.most_common()))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="stats", choices=["stats", "ingest"])
    a = ap.parse_args()
    if a.cmd == "stats":
        stats()
    else:
        incoming = json.load(sys.stdin)
        total, nuevos, reps = upsert(incoming)
        print(f"total={total} nuevas={len(nuevos)} descartadas_por_repetida={len(reps)}")
