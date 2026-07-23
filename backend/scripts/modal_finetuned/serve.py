"""Sirve el checkpoint fine-tuned (Qwen2.5-7B + LoRA mergeado) como endpoint
OpenAI-compatible via vLLM sobre GPU A10G en Modal, con scale-to-zero.

El checkpoint debe existir ya en el Volume VOLUME_NAME en /vol/model (ver
download_model.py). La caché de compilación de vLLM (torch_compile_cache)
persiste en un Volume de caché para no recompilar los CUDA graphs en cada
cold start.

Requiere el secret "tutor-finetuned-api-key" (una sola env var VLLM_API_KEY) ya
creado en Modal — protege el endpoint: sin este flag cualquiera con la URL
pública puede disparar cómputo de GPU a nuestra cuenta.

Deploy (v1, valores por defecto):
    modal deploy backend/scripts/modal_finetuned/serve.py
Deploy en paralelo (v2, app/volume/modelo servido distintos, no pisa el v1):
    APP_NAME=tutor-finetuned-server-v2 VOLUME_NAME=tutor-finetuned-weights-v2 \\
    CACHE_VOLUME_NAME=tutor-finetuned-vllm-cache-v2 SERVED_MODEL_NAME=tutor-finetuned-v2 \\
    modal deploy backend/scripts/modal_finetuned/serve.py
"""
import os

import modal

APP_NAME = os.environ.get("APP_NAME", "tutor-finetuned-server")
VOLUME_NAME = os.environ.get("VOLUME_NAME", "tutor-finetuned-weights")
CACHE_VOLUME_NAME = os.environ.get("CACHE_VOLUME_NAME", "tutor-finetuned-vllm-cache")
SERVED_MODEL_NAME = os.environ.get("SERVED_MODEL_NAME", "tutor-finetuned")

app = modal.App(APP_NAME)

model_vol = modal.Volume.from_name(VOLUME_NAME, create_if_missing=False)
vllm_cache_vol = modal.Volume.from_name(CACHE_VOLUME_NAME, create_if_missing=True)
api_key_secret = modal.Secret.from_name("tutor-finetuned-api-key")

MODEL_DIR = "/vol/model"
VLLM_PORT = 8000
MINUTES = 60

vllm_image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .pip_install("vllm")
)


@app.server(
    image=vllm_image,
    gpu="A10G",
    volumes={"/vol": model_vol, "/root/.cache/vllm": vllm_cache_vol},
    secrets=[api_key_secret],
    # SERVED_MODEL_NAME es una variable de módulo evaluada en el proceso REMOTO de
    # Modal (que re-importa este archivo al arrancar el contenedor), no en el shell
    # local que corre `modal deploy` — así que un env var local NO le llega al
    # contenedor a menos que se pase acá explícitamente.
    env={"SERVED_MODEL_NAME": SERVED_MODEL_NAME},
    scaledown_window=5 * MINUTES,
    startup_timeout=10 * MINUTES,
    port=VLLM_PORT,
    unauthenticated=True,
)
class Server:
    @modal.enter()
    def start(self):
        import os
        import subprocess

        served_model_name = os.environ["SERVED_MODEL_NAME"]
        cmd = [
            "vllm", "serve", MODEL_DIR,
            "--served-model-name", served_model_name,
            "--host", "0.0.0.0",
            "--port", str(VLLM_PORT),
            "--api-key", os.environ["VLLM_API_KEY"],
        ]
        print("vllm serve", MODEL_DIR, "--served-model-name", served_model_name, "...")
        self.process = subprocess.Popen(cmd)

    @modal.exit()
    def stop(self):
        self.process.terminate()
