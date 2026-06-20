from datetime import datetime, timezone
from typing import Any

from pymongo import ReturnDocument

from .db import get_mongo


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def next_paper_id() -> str:
    """Atomic counter sobre `examen_api.counters`. Race-safe entre uploads paralelos:
    Mongo garantiza que dos `findAndModify` con `$inc` simultaneos devuelven valores
    distintos. El doc se inicializa en `init_counters()` al startup."""
    db = get_mongo()
    counter = await db.counters.find_one_and_update(
        {"_id": "paper_id"},
        {"$inc": {"seq": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if counter is None:
        # Fallback defensivo: si el counter no existe, lo creamos sincronizado con
        # el max actual y reintentamos. NO deberia pasar si init_counters corrio.
        max_n = await _max_paper_n()
        await db.counters.update_one(
            {"_id": "paper_id"},
            {"$set": {"seq": max_n + 1}},
            upsert=True,
        )
        return f"PAPER_{max_n + 1}"
    return f"PAPER_{counter['seq']}"


async def _max_paper_n() -> int:
    """Devuelve el mayor sufijo numerico entre los paper_ids existentes, o 2000
    si la coleccion esta vacia. Solo uso interno (init_counters / fallback)."""
    db = get_mongo()
    cursor = db.papers.aggregate([
        {"$match": {"paper_id": {"$regex": "^PAPER_\\d+$"}}},
        {"$project": {
            "n": {"$toInt": {"$arrayElemAt": [{"$split": ["$paper_id", "_"]}, 1]}},
        }},
        {"$sort": {"n": -1}},
        {"$limit": 1},
    ])
    docs = await cursor.to_list(1)
    return docs[0]["n"] if docs else 2000


async def init_counters() -> None:
    """Idempotente: inserta el doc counter si no existe, sincronizandolo con el max
    de papers. Si ya existe pero quedo atras (ej. seed nuevo con PAPER_9999 manual),
    avanza el counter al max actual."""
    db = get_mongo()
    max_n = await _max_paper_n()
    existing = await db.counters.find_one({"_id": "paper_id"})
    if not existing:
        await db.counters.insert_one({"_id": "paper_id", "seq": max_n})
    elif existing.get("seq", 0) < max_n:
        await db.counters.update_one({"_id": "paper_id"}, {"$set": {"seq": max_n}})


async def insert_job(job: dict[str, Any]) -> None:
    db = get_mongo()
    await db.jobs.insert_one(job)


async def update_job(job_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    db = get_mongo()
    fields = {**fields, "updated_at": _now_iso()}
    return await db.jobs.find_one_and_update(
        {"job_id": job_id},
        {"$set": fields},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )


async def get_job(job_id: str) -> dict[str, Any] | None:
    db = get_mongo()
    return await db.jobs.find_one({"job_id": job_id}, projection={"_id": 0})


async def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    """Devuelve los jobs mas recientes ordenados por created_at desc."""
    db = get_mongo()
    cursor = db.jobs.find({}, projection={"_id": 0}).sort("created_at", -1).limit(limit)
    return await cursor.to_list(limit)


async def insert_paper(paper: dict[str, Any]) -> None:
    db = get_mongo()
    await db.papers.insert_one(paper)


async def update_paper(paper_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    db = get_mongo()
    return await db.papers.find_one_and_update(
        {"paper_id": paper_id},
        {"$set": fields},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )


async def get_paper(paper_id: str) -> dict[str, Any] | None:
    db = get_mongo()
    # Excluye embedding del response (es ruido para el cliente).
    return await db.papers.find_one({"paper_id": paper_id}, projection={"_id": 0, "embedding": 0})


async def list_papers(limit: int = 20, min_score: int = 0) -> list[dict[str, Any]]:
    db = get_mongo()
    cursor = db.papers.find(
        {"score_final": {"$gte": min_score}},
        projection={"_id": 0, "embedding": 0},
    ).sort("score_final", -1).limit(limit)
    return await cursor.to_list(limit)


async def list_papers_full() -> list[dict[str, Any]]:
    """Incluye embedding y text; uso interno para reclassify."""
    db = get_mongo()
    cursor = db.papers.find({}, projection={"_id": 0})
    return await cursor.to_list(None)


async def ranking(top: int = 10) -> list[dict[str, Any]]:
    db = get_mongo()
    cursor = db.papers.find(projection={"_id": 0, "embedding": 0}).sort(
        "score_breakdown.weighted", -1
    ).limit(top)
    return await cursor.to_list(top)


async def count_papers() -> int:
    db = get_mongo()
    return await db.papers.count_documents({})


async def count_jobs_in_flight() -> int:
    db = get_mongo()
    return await db.jobs.count_documents({"status": {"$ne": "completed"}})


async def get_config() -> dict[str, Any] | None:
    db = get_mongo()
    return await db.config.find_one({"_id": "current"})


async def update_config(fields: dict[str, Any]) -> dict[str, Any] | None:
    db = get_mongo()
    fields = {**fields, "updated_at": _now_iso()}
    return await db.config.find_one_and_update(
        {"_id": "current"},
        {"$set": fields},
        return_document=ReturnDocument.AFTER,
    )
