"""
Carga (o actualiza) las cuentas reales de estudiantes desde una carpeta con una
subcarpeta por grado. Cada subcarpeta trae:
  - el listado:       *.csv sin "credenciales" en el nombre -> nombre,apellido,grado_id
  - las credenciales: *credenciales*.csv                     -> nombre,apellido,username,password
Ambos archivos deben coincidir fila por fila (mismo nombre y apellido).

Idempotente: si el username ya existe, actualiza nombre, apellido, grado y
contraseña (solo re-hashea si cambió) y lo reactiva; si no, lo crea. La contraseña
se guarda solo como hash y NUNCA se imprime.

Uso (dentro del contenedor; la carpeta se copia antes con `docker cp`):
  python scripts/cargar_estudiantes.py /tmp/estudiantes [--dry-run]
"""
import argparse
import asyncio
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from sqlalchemy import select  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.grado import Grado  # noqa: E402
from app.models.usuario import RolUsuario, Usuario  # noqa: E402
from app.security import hash_password, verify_password  # noqa: E402


def _leer(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def leer_carpeta(carpeta: Path) -> list[dict]:
    """Devuelve una fila por estudiante; aborta si listado y credenciales no coinciden."""
    filas: list[dict] = []
    for sub in sorted(p for p in carpeta.iterdir() if p.is_dir()):
        csvs = list(sub.glob("*.csv"))
        cred = [p for p in csvs if "credenciales" in p.name.lower()]
        lst = [p for p in csvs if "credenciales" not in p.name.lower()]
        if len(cred) != 1 or len(lst) != 1:
            sys.exit(f"{sub.name}: se esperaba 1 listado y 1 credenciales, hay {len(lst)} y {len(cred)}")
        listado, credenciales = _leer(lst[0]), _leer(cred[0])
        if len(listado) != len(credenciales):
            sys.exit(f"{sub.name}: listado ({len(listado)}) y credenciales ({len(credenciales)}) no coinciden")
        for i, (l, c) in enumerate(zip(listado, credenciales), start=2):
            if (l["nombre"], l["apellido"]) != (c["nombre"], c["apellido"]):
                sys.exit(f"{sub.name}: la fila {i} no coincide entre listado y credenciales")
            if not c["username"] or not c["password"] or not l["grado_id"].isdigit():
                sys.exit(f"{sub.name}: la fila {i} no tiene usuario, contraseña o grado_id válido")
            filas.append({"carpeta": sub.name, "nombre": l["nombre"], "apellido": l["apellido"],
                          "grado_id": int(l["grado_id"]), "username": c["username"], "password": c["password"]})
    usernames = [f["username"] for f in filas]
    repetidos = {u for u in usernames if usernames.count(u) > 1}
    if repetidos:
        sys.exit(f"usuarios repetidos entre archivos: {sorted(repetidos)}")
    return filas


async def cargar(filas: list[dict], dry_run: bool) -> None:
    async with AsyncSessionLocal() as db:
        grados = set((await db.execute(select(Grado.id))).scalars())
        faltan = {f["grado_id"] for f in filas} - grados
        if faltan:
            sys.exit(f"grado_id inexistentes en la BD: {sorted(faltan)}")
        creados = actualizados = sin_cambios = 0
        por_grado: dict[str, int] = {}
        for f in filas:
            por_grado[f["carpeta"]] = por_grado.get(f["carpeta"], 0) + 1
            u = (await db.execute(select(Usuario).where(Usuario.username == f["username"]))).scalar_one_or_none()
            if u is None:
                db.add(Usuario(nombre=f["nombre"], apellido=f["apellido"], username=f["username"],
                               password_hash=hash_password(f["password"]), rol=RolUsuario.estudiante,
                               grado_id=f["grado_id"]))
                creados += 1
                continue
            if u.rol != RolUsuario.estudiante:
                sys.exit(f"'{f['username']}' ya existe con rol {u.rol.value}; no se toca")
            cambio = (u.nombre, u.apellido, u.grado_id, u.activo) != (f["nombre"], f["apellido"], f["grado_id"], True)
            if not verify_password(f["password"], u.password_hash):
                u.password_hash = hash_password(f["password"])
                cambio = True
            u.nombre, u.apellido, u.grado_id, u.activo = f["nombre"], f["apellido"], f["grado_id"], True
            actualizados += cambio
            sin_cambios += not cambio
        for carpeta, n in por_grado.items():
            print(f"  {carpeta}: {n}")
        print(f"total {len(filas)}: {creados} creados, {actualizados} actualizados, {sin_cambios} sin cambios")
        if dry_run:
            await db.rollback()
            print("(dry-run: no se guardó nada)")
        else:
            await db.commit()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("carpeta", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    asyncio.run(cargar(leer_carpeta(args.carpeta), args.dry_run))


if __name__ == "__main__":
    main()
