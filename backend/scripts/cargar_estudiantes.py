"""
Carga (o actualiza) las cuentas reales de estudiantes desde una carpeta con una
subcarpeta por grado. Cada subcarpeta trae:
  - el listado:       *.csv sin "credenciales" en el nombre -> nombre,apellido,grado_id
  - las credenciales: *credenciales*.csv                     -> nombre,apellido,username,password
  - la lista:         *.txt -> "Apellidos, Nombres" completos, una línea por estudiante
Listado y credenciales deben coincidir fila por fila (mismo nombre y apellido).
Los CSV traen apellidos abreviados ("ArchilaO"); el nombre que se guarda es el
completo del .txt, emparejado por nombre y, si hace falta, por apellido.

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
import re
import sys
import unicodedata
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


def _clave(s: str) -> str:
    """Minúsculas, sin tildes ni espacios: "De la Cruz" -> "delacruz"."""
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower().replace(" ", "")


def _empieza_por_palabras(completo: str, inicio: str) -> bool:
    """ "Luis Emilio" empieza por "Luis"; "Analie" no empieza por "Ana"."""
    c, i = _clave(completo.replace(" ", "|")), _clave(inicio.replace(" ", "|"))
    return c == i or c.startswith(i + "|")


def emparejar_nombres_completos(filas: list[dict], lista_txt: list[str], grado: str) -> None:
    """Pone en cada fila el nombre y apellido completos de la lista .txt.

    Candidatos: líneas cuyo nombre empieza por el del CSV ("Luis" -> "Luis Emilio");
    si hay más de uno, se exige además que el apellido completo empiece por el
    abreviado sin su sufijo en mayúsculas ("ArchilaV" -> "archila"). Aborta si
    alguna fila no queda emparejada con exactamente una línea distinta.
    """
    completos = []
    for linea in lista_txt:
        apellido, _, nombre = linea.partition(",")
        completos.append((nombre.strip(), apellido.strip()))
    usados: set[int] = set()
    for f in filas:
        cands = [i for i, (n, _) in enumerate(completos) if _empieza_por_palabras(n, f["nombre"])]
        if len(cands) > 1:
            base = _clave(re.sub(r"(?<=[a-záéíóúñ])[A-Z]+[a-z]?$", "", f["apellido"]))
            cands = [i for i in cands if _clave(completos[i][1]).startswith(base)]
        if len(cands) != 1 or cands[0] in usados:
            sys.exit(f"{grado}: no se pudo emparejar '{f['nombre']} {f['apellido']}' con la lista .txt")
        usados.add(cands[0])
        f["nombre"], f["apellido"] = completos[cands[0]]


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
        txts = list(sub.glob("*.txt"))
        if len(txts) != 1:
            sys.exit(f"{sub.name}: se esperaba 1 lista .txt, hay {len(txts)}")
        lista_txt = [l.strip() for l in txts[0].read_text(encoding="utf-8-sig").splitlines() if l.strip()]
        if len(lista_txt) != len(listado):
            sys.exit(f"{sub.name}: la lista .txt ({len(lista_txt)}) y el listado ({len(listado)}) no coinciden")
        de_grado = []
        for i, (l, c) in enumerate(zip(listado, credenciales), start=2):
            if (l["nombre"], l["apellido"]) != (c["nombre"], c["apellido"]):
                sys.exit(f"{sub.name}: la fila {i} no coincide entre listado y credenciales")
            if not c["username"] or not c["password"] or not l["grado_id"].isdigit():
                sys.exit(f"{sub.name}: la fila {i} no tiene usuario, contraseña o grado_id válido")
            de_grado.append({"carpeta": sub.name, "nombre": l["nombre"], "apellido": l["apellido"],
                             "grado_id": int(l["grado_id"]), "username": c["username"], "password": c["password"]})
        emparejar_nombres_completos(de_grado, lista_txt, sub.name)
        filas.extend(de_grado)
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
