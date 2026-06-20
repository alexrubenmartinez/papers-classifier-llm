"""Cliente boto3 standalone para que el classifier funcione tanto en local
(reutilizando el .env del examen) como en el container del VPS (con env vars del compose).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def _load_env_if_needed():
    """Carga el .env del directorio examen/ si las env vars no están seteadas."""
    if "MINIO_ENDPOINT" in os.environ:
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    # Buscar examen/.env subiendo desde este archivo
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / ".env"
        if candidate.exists():
            load_dotenv(candidate, override=False)
            break


@lru_cache(maxsize=1)
def minio():
    """boto3 S3 client apuntando a MinIO (interno al VPS o vía tunnel local)."""
    _load_env_if_needed()
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=os.environ["MINIO_ENDPOINT"],
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
        config=Config(
            signature_version="s3v4",
            max_pool_connections=20,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )
