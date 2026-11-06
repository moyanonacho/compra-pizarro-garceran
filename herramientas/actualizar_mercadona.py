"""Descarga el catálogo de Mercadona para La Compra de Casa.

Uso:  .venv\\Scripts\\python.exe herramientas\\actualizar_mercadona.py catalogo\\mercadona

Genera en la carpeta indicada:
  - mercadona.json  (secciones, subsecciones y productos con precio)
  - s<id>.jpg       (una lámina de fotos por subsección, 8 columnas de 256 px)
Los precios son los del almacén del código postal 28760 (mad2).
"""
import json
import math
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from io import BytesIO
from pathlib import Path

from PIL import Image

POSTAL = "28760"
WH = "mad2"
BASE = "https://tienda.mercadona.es/api"
TILE = 256
COLS = 8
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def get(url, tries=4):
    for t in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read()
        except Exception:
            if t == tries - 1:
                raise
            time.sleep(1.5 * (t + 1))


def jget(path):
    return json.loads(get(f"{BASE}{path}?lang=es&wh={WH}"))


def size_text(pi):
    size, fmt = pi.get("unit_size"), pi.get("size_format")
    if not size or not fmt:
        return ""
    if fmt == "kg" and size < 1:
        return f"{round(size * 1000):g} g"
    if fmt == "l" and size < 1:
        return f"{round(size * 1000):g} ml"
    return f"{size:g} {fmt}".replace(".", ",")


def tile(url):
    if not url:
        return None
    url = url.split("?")[0] + f"?fit=crop&h={TILE}&w={TILE}"
    try:
        img = Image.open(BytesIO(get(url))).convert("RGB")
        if img.size != (TILE, TILE):
            img = img.resize((TILE, TILE))
        return img
    except Exception:
        return None


def main(out):
    out.mkdir(parents=True, exist_ok=True)
    tops = jget("/categories/")["results"]
    data = {"store": "mercadona", "pc": POSTAL, "wh": WH, "updated": date.today().isoformat(),
            "cols": COLS, "tops": [], "subs": {}, "p": []}
    jobs = []
    for top in tops:
        data["tops"].append({"id": top["id"], "name": top["name"], "subs": [s["id"] for s in top["categories"]]})
        for sub in top["categories"]:
            detail = jget(f"/categories/{sub['id']}/")
            leaves, items, seen = [], [], set()
            for leaf in detail.get("categories", []):
                li = len(leaves)
                leaves.append(leaf["name"])
                for p in leaf.get("products", []):
                    if p["id"] in seen or not p.get("published", True):
                        continue
                    seen.add(p["id"])
                    items.append((li, p))
            rows = max(1, math.ceil(len(items) / COLS))
            data["subs"][str(sub["id"])] = {"name": sub["name"], "top": top["id"], "rows": rows, "n": len(items), "leaves": leaves}
            for i, (li, p) in enumerate(items):
                pi = p.get("price_instructions") or {}
                ref = f"{pi.get('reference_price')} €/{pi.get('reference_format')}" if pi.get("reference_price") else ""
                data["p"].append([p["id"], p.get("display_name", ""), p.get("packaging") or "", size_text(pi),
                                  float(pi.get("unit_price") or 0), ref.replace(".", ","), sub["id"], i, li])
            jobs.append((sub["id"], rows, [p.get("thumbnail") for _, p in items]))
            print(f"{top['name']} > {sub['name']}: {len(items)}", flush=True)
            time.sleep(0.1)

    failed = 0
    with ThreadPoolExecutor(max_workers=10) as pool:
        for sid, rows, urls in jobs:
            sheet = Image.new("RGB", (COLS * TILE, rows * TILE), "white")
            for i, img in enumerate(pool.map(tile, urls)):
                if img is None:
                    failed += 1
                    continue
                sheet.paste(img, ((i % COLS) * TILE, (i // COLS) * TILE))
            sheet.save(out / f"s{sid}.jpg", "JPEG", quality=70, optimize=True, progressive=True)

    (out / "mercadona.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    total = sum(f.stat().st_size for f in out.iterdir())
    print(f"OK: {len(data['p'])} productos, {len(jobs)} láminas, {failed} fotos fallidas, {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
