"""Sirve el checkpoint fine-tuned (Qwen2.5-7B + LoRA mergeado) como endpoint
OpenAI-compatible via vLLM sobre GPU A10G en Modal, con scale-to-zero.

El checkpoint debe existir ya en el Volume "tutor-finetuned-weights" en /vol/model
(ver download_model.py). La caché de compilación de vLLM (torch_compile_cache)
persiste en el Volume "tutor-finetuned-vllm-cache" para no recompilar los CUDA
graphs en cada cold start.

Requiere el secret "tutor-finetuned-api-key" (una sola env var VLLM_API_KEY) ya
creado en Modal — protege el endpoint: sin este flag cualquiera con la URL
pública puede disparar cómputo de GPU a nuestra cuenta.

Deploy:
    modal deploy backend/scripts/modal_finetuned/serve.py
"""
import modal

app = modal.App("tutor-finetuned-server")

model_vol = modal.Volume.from_name("tutor-finetuned-weights", create_if_missing=False)
vllm_cache_vol = modal.Volume.from_name("tutor-finetuned-vllm-cache", create_if_missing=True)
api_key_secret = modal.Secret.from_name("tutor-finetuned-api-key")

MODEL_DIR = "/vol/model"
SERVED_MODEL_NAME = "tutor-finetuned"
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

        cmd = [
            "vllm", "serve", MODEL_DIR,
            "--served-model-name", SERVED_MODEL_NAME,
            "--host", "0.0.0.0",
            "--port", str(VLLM_PORT),
            "--api-key", os.environ["VLLM_API_KEY"],
        ]
        print("vllm serve", MODEL_DIR, "--served-model-name", SERVED_MODEL_NAME, "...")
        self.process = subprocess.Popen(cmd)

    @modal.exit()
    def stop(self):
        self.process.terminate()
