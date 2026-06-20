import io
import os
from datetime import datetime, timezone

from minio import Minio
from minio.error import S3Error
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

MONGO_URI = os.getenv("MONGO_URI", "mongodb://admin:REPLACE_PASSWORD@mongodb:27017/?authSource=admin")
MONGO_DB = os.getenv("MONGO_DB", "examen_api")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "REPLACE_PASSWORD")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "examen-parcial")
MINIO_PREFIX = os.getenv("MINIO_PREFIX", "examen-api/uploads")

_mongo_client: AsyncIOMotorClient | None = None
_minio_client: Minio | None = None


def get_mongo() -> AsyncIOMotorDatabase:
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(MONGO_URI)
    return _mongo_client[MONGO_DB]


def get_minio() -> Minio:
    global _minio_client
    if _minio_client is None:
        _minio_client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,
        )
    return _minio_client


async def init_indices() -> None:
    db = get_mongo()
    await db.papers.create_index("paper_id", unique=True)
    await db.papers.create_index("score_final")
    await db.papers.create_index([("score_breakdown.weighted", -1)])
    await db.jobs.create_index("job_id", unique=True)
    await db.jobs.create_index("created_at")


def ensure_bucket() -> None:
    client = get_minio()
    try:
        if not client.bucket_exists(MINIO_BUCKET):
            client.make_bucket(MINIO_BUCKET)
    except S3Error:
        pass


def put_pdf(paper_id: str, data: bytes, content_type: str = "application/pdf") -> str:
    client = get_minio()
    key = f"{MINIO_PREFIX}/{paper_id}.pdf"
    client.put_object(
        MINIO_BUCKET,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return key


def get_pdf(minio_key: str) -> bytes:
    client = get_minio()
    resp = client.get_object(MINIO_BUCKET, minio_key)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


SEED_PAPERS: list[dict] = [
    {
        "paper_id": "PAPER_1841",
        "title": "Zero-trust security architecture in the AI era",
        "abstract": "We propose a zero-trust security architecture for enterprise cybersecurity using AI-driven threat detection across multi-cloud environments.",
        "year": 2024,
        "score_final": 5,
        "score_breakdown": {"keyword": 0.92, "tfidf": 0.88, "sbert": 0.95, "weighted": 0.92},
        "decision": "Gold — muy relacionado",
        "justification": "Mock — Fase 4 la genera con Ollama.",
        "created_at": "2026-06-20T14:25:00Z",
        "minio_key": None,
        "embedding": None,
    },
    {
        "paper_id": "PAPER_1597",
        "title": "Zero Trust in Practice: Multi-Cloud Systems",
        "abstract": "Implementation patterns for zero trust network access in hybrid cloud security with NIST 800-207 alignment.",
        "year": 2024,
        "score_final": 5,
        "score_breakdown": {"keyword": 0.87, "tfidf": 0.81, "sbert": 0.91, "weighted": 0.86},
        "decision": "Gold — muy relacionado",
        "justification": None,
        "created_at": "2026-06-20T14:25:01Z",
        "minio_key": None,
        "embedding": None,
    },
    {
        "paper_id": "PAPER_1475",
        "title": "Adaptive Cybersecurity Architectures Using Zero Trust and AI",
        "abstract": "A deep learning approach to intrusion detection within zero trust microsegmentation frameworks.",
        "year": 2025,
        "score_final": 5,
        "score_breakdown": {"keyword": 0.84, "tfidf": 0.79, "sbert": 0.89, "weighted": 0.84},
        "decision": "Gold — muy relacionado",
        "justification": None,
        "created_at": "2026-06-20T14:25:02Z",
        "minio_key": None,
        "embedding": None,
    },
]


SEED_CONFIG: dict = {
    "_id": "current",
    "topic_name": "Zero Trust + IA en Ciberseguridad",
    "query_text": (
        "Zero trust architecture for cybersecurity threat detection using "
        "artificial intelligence machine learning in cloud and hybrid environments. "
        "Includes NIST 800-207, ZTNA, microsegmentation, intrusion detection, "
        "anomaly detection, and AI-powered security."
    ),
    "axes": {
        "zero_trust": [
            "zero trust", "zero-trust", "zero trust architecture", "ztna",
            "beyondcorp", "nist 800-207", "software defined perimeter", "sdp",
            "sase", "microsegmentation", "micro-segmentation",
            "arquitectura zero trust", "seguridad zero trust",
        ],
        "cybersecurity": [
            "cybersecurity", "cyber security", "information security",
            "computer security", "network security", "cloud security",
            "hybrid cloud security", "cloud-native security",
            "seguridad informatica", "seguridad en la nube", "ciberseguridad",
        ],
        "detection": [
            "threat detection", "intrusion detection", "anomaly detection",
            "attack detection", "early threat detection", "malware detection",
            "intrusion prevention", "ids",
            "deteccion de amenazas", "deteccion de intrusos",
            "deteccion de anomalias", "deteccion temprana de ataques",
        ],
        "ai": [
            "artificial intelligence", "machine learning", "deep learning",
            "neural network", "large language model", "llm", "transformer",
            "reinforcement learning", "graph neural network",
            "ai", "ai-driven", "ai-powered", "ai-based",
            "inteligencia artificial", "aprendizaje automatico",
        ],
    },
    "weights": {"keyword": 0.40, "tfidf": 0.30, "sbert": 0.30},
    "year_range": [2016, 2026],
    "thresholds": {
        "gold_muy": 0.65,
        "gold_claro": 0.50,
        "revisar": 0.35,
        "no_prioritario": 0.20,
    },
    "query_embedding": None,
    "updated_at": None,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def seed_if_empty() -> int:
    db = get_mongo()
    if await db.papers.count_documents({}) == 0:
        await db.papers.insert_many([dict(p) for p in SEED_PAPERS])
        return len(SEED_PAPERS)
    return 0


async def upsert_seeds(embed_fn) -> int:
    """Idempotente: si un seed no existe lo inserta; si existe pero le falta abstract o
    text, lo completa. Recalcula embedding cuando agrega texto nuevo."""
    db = get_mongo()
    touched = 0
    for seed in SEED_PAPERS:
        existing = await db.papers.find_one({"paper_id": seed["paper_id"]})
        text = f"{seed['title']} {seed.get('abstract', '')}".strip()
        if not existing:
            doc = dict(seed)
            doc["text"] = text
            doc["embedding"] = embed_fn(text)
            await db.papers.insert_one(doc)
            touched += 1
        elif not existing.get("abstract") or not existing.get("text"):
            await db.papers.update_one(
                {"paper_id": seed["paper_id"]},
                {"$set": {
                    "abstract": seed.get("abstract", ""),
                    "text": text,
                    "embedding": embed_fn(text),
                }},
            )
            touched += 1
    return touched


async def seed_config_if_empty(embed_fn) -> bool:
    """Seed config. embed_fn es una callable (text -> list[float]) que pasamos para no
    crear ciclo de imports con app.pipeline."""
    db = get_mongo()
    if await db.config.count_documents({}) == 0:
        doc = dict(SEED_CONFIG)
        doc["query_embedding"] = embed_fn(SEED_CONFIG["query_text"])
        doc["updated_at"] = _now_iso()
        await db.config.insert_one(doc)
        return True
    return False
