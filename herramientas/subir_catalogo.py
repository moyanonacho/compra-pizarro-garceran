"""Sube un catálogo (JSON + láminas .jpg) a la carpeta pública «catalogo» de Supabase
y borra allí las láminas que ya no use.

Uso:  python herramientas/subir_catalogo.py <carpeta local> <tienda>
      p. ej.  python herramientas/subir_catalogo.py catalogo/mercadona.nuevo mercadona

Entra con la cuenta «robot» (variables ROBOT_EMAIL y ROBOT_PASSWORD), que solo
puede tocar esa carpeta: no ve ni cambia los datos de la familia.
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

SB_URL = "https://eralhpnstnbyznwthkmz.supabase.co"
SB_KEY = "sb_publishable_8_hwEm1tK5NS3G0iRbj9kw_CZMsvBbu"
BUCKET = "catalogo"


def main(src: Path, store: str):
    tok = requests.post(f"{SB_URL}/auth/v1/token?grant_type=password", headers={"apikey": SB_KEY}, timeout=60,
                        json={"email": os.environ["ROBOT_EMAIL"], "password": os.environ["ROBOT_PASSWORD"]})
    tok.raise_for_status()
    h = {"apikey": SB_KEY, "Authorization": "Bearer " + tok.json()["access_token"]}

    data = json.loads((src / f"{store}.json").read_text(encoding="utf-8"))
    wanted = {p.name for p in src.glob("*.jpg")}
    if any("f" in s for s in data["subs"].values()):          # catálogo empaquetado: p<n>.jpg
        used = {f"p{s['f']}.jpg" for s in data["subs"].values()}
    else:                                                       # láminas sueltas: s<id>.jpg
        used = {f"s{k}.jpg" for k in data["subs"]}
    missing = used - wanted
    if missing:
        sys.exit(f"Faltan láminas: {sorted(missing)[:5]}")

    def put(name, ctype, cache):
        body = (src / name).read_bytes()
        for _ in range(3):
            r = requests.post(f"{SB_URL}/storage/v1/object/{BUCKET}/{store}/{name}", data=body, timeout=120,
                              headers={**h, "Content-Type": ctype, "x-upsert": "true", "cache-control": f"max-age={cache}"})
            if r.ok:
                return
        raise RuntimeError(f"No se pudo subir {name}: {r.status_code} {r.text[:200]}")

    # primero las láminas, al final el JSON, para que nunca apunte a fotos que aún no están
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda n: put(n, "image/jpeg", 300), sorted(used)))
    put(f"{store}.json", "application/json", 300)

    r = requests.post(f"{SB_URL}/storage/v1/object/list/{BUCKET}", headers=h, timeout=60,
                      json={"prefix": f"{store}/", "limit": 1000})
    r.raise_for_status()
    stale = [f"{store}/{o['name']}" for o in r.json() if o["name"].endswith(".jpg") and o["name"] not in used]
    if stale:
        requests.delete(f"{SB_URL}/storage/v1/object/{BUCKET}", headers=h, json={"prefixes": stale}, timeout=60).raise_for_status()
    print(f"{store}: {len(data['p'])} productos, {len(used)} láminas subidas, {len(stale)} antiguas borradas")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
