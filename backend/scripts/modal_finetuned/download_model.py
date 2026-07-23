"""Descarga el checkpoint fine-tuned (tar.zst) desde la URL firmada de Together AI
directo a un Modal Volume (cloud-to-cloud, sin pasar por la máquina local) y lo
descomprime ahí mismo.

Uso:
    modal run backend/scripts/modal_finetuned/download_model.py --url "<url-firmada>"
    VOLUME_NAME=tutor-finetuned-weights-v2 modal run .../download_model.py --url "..."
"""
import os

import modal

VOLUME_NAME = os.environ.get("VOLUME_NAME", "tutor-finetuned-weights")

app = modal.App("tutor-finetuned-download")

model_vol = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

download_image = modal.Image.debian_slim(python_version="3.12").apt_install("curl", "zstd")

MODEL_DIR = "/vol/model"


@app.function(image=download_image, volumes={"/vol": model_vol}, timeout=1800)
def download_and_extract(url: str):
    import os
    import subprocess

    subprocess.run(["mkdir", "-p", MODEL_DIR], check=True)

    curl = subprocess.Popen(["curl", "-sS", url], stdout=subprocess.PIPE)
    zstd = subprocess.Popen(["zstd", "-dc"], stdin=curl.stdout, stdout=subprocess.PIPE)
    curl.stdout.close()
    tar = subprocess.run(["tar", "-x", "-C", MODEL_DIR], stdin=zstd.stdout, check=True)
    zstd.stdout.close()
    for p, name in ((curl, "curl"), (zstd, "zstd")):
        p.wait()
        if p.returncode != 0:
            raise RuntimeError(f"{name} salió con código {p.returncode}")

    model_vol.commit()

    listado = subprocess.run(["find", MODEL_DIR, "-maxdepth", "1"], capture_output=True, text=True)
    print(listado.stdout)
    return listado.stdout
