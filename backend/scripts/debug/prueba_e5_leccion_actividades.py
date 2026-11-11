"""
Prueba de humo con el índice e5 (correcciones del jurado): una micro-lección y una
actividad de cada tipo contra una instancia local del backend levantada con
EMBEDDING_MODEL=intfloat/multilingual-e5-small y CHROMA_COLLECTION=libros_texto_e5.

Crea un estudiante temporal (vía admin) y lo desactiva al terminar.

    docker compose exec -d -e EMBEDDING_MODEL=intfloat/multilingual-e5-small \
        -e CHROMA_COLLECTION=libros_texto_e5 backend \
        sh -c "uvicorn app.main:app --host 127.0.0.1 --port 8001 > /tmp/uvicorn_e5.log 2>&1"
    docker compose exec backend python scripts/debug/prueba_e5_leccion_actividades.py \
        [--asignatura "Ciencias Naturales"] [--orden 3]
"""
import argparse
import json
import os
import sys
import time
import uuid

import httpx

URL = "http://127.0.0.1:8001"
TIPOS = ["opcion_multiple", "verdadero_falso", "completar", "ordenar", "respuesta_corta"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asignatura", default="Ciencias Naturales")
    ap.add_argument("--grado", default="4to Primaria")
    ap.add_argument("--orden", type=int, default=3, help="nº de lección dentro de la ruta (1 = primera)")
    ap.add_argument("--salida", default="/app/scripts/debug/prueba_e5_resultado.json")
    args = ap.parse_args()

    c = httpx.Client(base_url=URL, timeout=300)
    adm = c.post("/auth/login", data={"username": os.environ.get("ADMIN_USERNAME", "admin"),
                                      "password": os.environ.get("ADMIN_PASSWORD", "admin123")}).json()["access_token"]
    H = {"Authorization": f"Bearer {adm}"}
    grado = next(g for g in c.get("/admin/grados", headers=H).json() if g["nombre"] == args.grado)
    user, pwd = f"prueba_e5_{uuid.uuid4().hex[:6]}", "PruebaE5_" + uuid.uuid4().hex[:8]
    est = c.post("/admin/estudiantes", headers=H, json={"nombre": "Prueba", "apellido": "E5",
                                                         "grado_id": grado["id"], "username": user, "password": pwd})
    est.raise_for_status()
    est_id = est.json()["id"]
    salida = {"estudiante_temporal": user, "grado": args.grado}
    try:
        tok = c.post("/auth/login", data={"username": user, "password": pwd}).json()["access_token"]
        E = {"Authorization": f"Bearer {tok}"}
        libro = next(l for l in c.get("/lecciones/mis-libros", headers=E).json()
                     if l["asignatura_nombre"] == args.asignatura)
        ruta = c.get("/lecciones/ruta", headers=E, params={"libro_id": libro["libro_id"]}).json()
        leccion = ruta["lecciones"][args.orden - 1]
        salida["leccion"] = {k: leccion[k] for k in ("id", "nombre", "paginas")}

        t = time.time()
        r = c.get(f"/lecciones/{leccion['id']}/micro-leccion", headers=E, params={"nivel": 1})
        r.raise_for_status()
        micro = r.json()
        salida["micro_leccion"] = {"segundos": round(time.time() - t, 1), "titulo": micro["titulo"],
                                   "n_tarjetas": len(micro["tarjetas"]), "fragment_ids": micro["fragment_ids"],
                                   "tarjetas": micro["tarjetas"]}
        print(f"micro-lección {leccion['id']} «{micro['titulo']}»: {len(micro['tarjetas'])} tarjetas, "
              f"{len(micro['fragment_ids'])} fragmentos, {salida['micro_leccion']['segundos']} s")

        salida["actividades"] = []
        # Flujo del cliente (fragment_ids de la micro-lección) para los 5 tipos, y uno más
        # SIN lección ni fragmentos: modo 3 del servicio = búsqueda semántica con e5.
        casos = [(tipo, micro["fragment_ids"]) for tipo in TIPOS] + [("opcion_multiple", [])]
        for tipo, frag_ids in casos:
            t = time.time()
            cuerpo = {"asignatura_id": libro["asignatura_id"], "tipo": tipo}
            cuerpo |= {"leccion_id": leccion["id"], "fragment_ids": frag_ids} if frag_ids else {"tema": leccion["tema_clave"]}
            r = c.post("/actividades/generar", headers=E, json=cuerpo)
            item = {"tipo": tipo, "con_fragment_ids": bool(frag_ids), "status": r.status_code,
                    "segundos": round(time.time() - t, 1)}
            item["respuesta"] = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:500]
            salida["actividades"].append(item)
            print(f"  {tipo:16} fragment_ids={'sí' if frag_ids else 'no (semántica)':15} HTTP {r.status_code} {item['segundos']} s")
    finally:
        c.put(f"/admin/estudiantes/{est_id}", headers=H, json={"activo": False})
        with open(args.salida, "w") as f:
            json.dump(salida, f, ensure_ascii=False, indent=1)
        print(f"estudiante {user} desactivado; detalle en {args.salida}")


if __name__ == "__main__":
    sys.exit(main())
