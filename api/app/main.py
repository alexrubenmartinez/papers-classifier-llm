import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, File, HTTPException, Path, Query, Request, UploadFile
from sse_starlette.sse import EventSourceResponse

from app import pipeline, repos
from app.db import (
    copy_to_tier,
    ensure_bucket,
    get_pdf,
    init_indices,
    list_objects,
    put_pdf,
    remove_object,
    seed_config_if_empty,
    seed_if_empty,
    tier_for_score,
    tier_key,
    upsert_seeds,
)
from app.schemas import (
    ChatRequest,
    ChatResponse,
    ImportRequest,
    ImportResponse,
    JobStatus,
    JustifyBatchResponse,
    JustifyRequest,
    JustifyResponse,
    Paper,
    PaperSummary,
    QueryConfig,
    QueryConfigUpdate,
    ReclassifyResponse,
    UploadResponse,
)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_DEFAULT_MODEL = os.getenv("OLLAMA_DEFAULT_MODEL", "qwen2.5:1.5b")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_bucket()
    await init_indices()
    await repos.init_counters()
    pipeline.get_model()
    print("[startup] SBERT model loaded")
    seeded = await seed_if_empty()
    if seeded:
        print(f"[startup] seeded {seeded} papers")
    patched = await upsert_seeds(pipeline.embed_text)
    if patched:
        print(f"[startup] upserted {patched} seed papers (abstract/text/embedding)")
    if await seed_config_if_empty(pipeline.embed_text):
        print("[startup] seeded config")
    # Fit del vectorizer sobre el corpus existente para que los uploads tempranos
    # ya tengan TF-IDF real.
    papers = await repos.list_papers_full()
    corpus = [(p.get("text") or p.get("title") or "") for p in papers]
    pipeline.fit_vectorizer(corpus)
    print(f"[startup] TF-IDF fit sobre {len(corpus)} papers; vectorizer={'on' if pipeline.has_vectorizer() else 'off'}")
    yield


app = FastAPI(
    title="Examen API",
    version="0.3.0",
    description=(
        "API del examen de Bases de Datos Avanzados y Big Data (UNMSM 2026-I).\n\n"
        "**Fase 3 — pipeline real**: PyMuPDF extrae metadata, SBERT genera embeddings, "
        "score hibrido (keyword + TF-IDF + SBERT cosine) vs query configurable. "
        "Endpoint `/reclassify` reprocesa todos los papers cuando cambias el tema o keywords.\n\n"
        "Auth: header `X-API-Key` validado por nginx upstream."
    ),
    lifespan=lifespan,
)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "examen-api",
        "phase": "Fase 3 — pipeline real + reclassify",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }


@app.get("/health")
async def health() -> dict[str, str | int | bool]:
    return {
        "status": "ok",
        "service": "examen-api",
        "version": "0.3.0",
        "papers": await repos.count_papers(),
        "jobs_in_flight": await repos.count_jobs_in_flight(),
        "sbert_loaded": pipeline._model is not None,
        "tfidf_fitted": pipeline.has_vectorizer(),
    }


# ---------------------------------------------------------------------------
# Papers + upload
# ---------------------------------------------------------------------------


@app.post("/papers", response_model=UploadResponse, status_code=202)
async def upload_paper(
    file: UploadFile = File(...),
    justify: str = Query("none", regex="^(none|lazy|auto)$", description="none|lazy|auto. auto = dispara Ollama justification tras scoring (+5-7s)."),
) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Solo se aceptan archivos .pdf")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Archivo vacio")

    paper_id = await repos.next_paper_id()
    job_id = str(uuid.uuid4())
    minio_key = put_pdf(paper_id, data)

    job = {
        "job_id": job_id,
        "paper_id": paper_id,
        "type": "ingest",
        "status": "queued",
        "stage": "queued",
        "filename": file.filename,
        "size_bytes": len(data),
        "minio_key": minio_key,
        "justify_mode": justify,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "error": None,
    }
    await repos.insert_job(job)
    asyncio.create_task(_run_pipeline_real(job_id, paper_id, minio_key, justify_mode=justify))

    return UploadResponse(
        job_id=job_id,
        paper_id=paper_id,
        status="queued",
        stream_url=f"/stream?job_id={job_id}",
    )


@app.get("/papers", response_model=list[PaperSummary])
async def list_papers_endpoint(
    limit: int = Query(20, ge=1, le=5000),
    min_score: int = Query(0, ge=0, le=5),
) -> list[dict]:
    return await repos.list_papers(limit=limit, min_score=min_score)


@app.get("/papers/{paper_id}", response_model=Paper)
async def get_paper_endpoint(paper_id: str = Path(...)) -> dict:
    paper = await repos.get_paper(paper_id)
    if not paper:
        raise HTTPException(404, f"Paper {paper_id} no encontrado")
    return paper


@app.get("/ranking", response_model=list[PaperSummary])
async def ranking_endpoint(top: int = Query(10, ge=1, le=50)) -> list[dict]:
    return await repos.ranking(top=top)


@app.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_endpoint(job_id: str = Path(...)) -> dict:
    job = await repos.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} no encontrado")
    return job


# ---------------------------------------------------------------------------
# Config + reclassify
# ---------------------------------------------------------------------------


@app.get("/config", response_model=QueryConfig)
async def get_config_endpoint() -> dict:
    cfg = await repos.get_config()
    if not cfg:
        raise HTTPException(500, "Config no inicializada")
    # No expongo el embedding al cliente (es ruido).
    cfg.pop("query_embedding", None)
    cfg.pop("_id", None)
    return cfg


@app.put("/config", response_model=QueryConfig)
async def update_config_endpoint(
    body: QueryConfigUpdate,
    reclassify: bool = Query(False, description="Si true, dispara reclassify_all en background."),
) -> dict:
    update: dict = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(400, "Body vacio: nada que actualizar")
    # Si cambia query_text, recalcular el embedding.
    if "query_text" in update:
        update["query_embedding"] = pipeline.embed_text(update["query_text"])
    cfg = await repos.update_config(update)
    if not cfg:
        raise HTTPException(500, "Config no inicializada")
    if reclassify:
        asyncio.create_task(_run_reclassify(str(uuid.uuid4())))
    cfg.pop("query_embedding", None)
    cfg.pop("_id", None)
    return cfg


@app.post("/reclassify", response_model=ReclassifyResponse, status_code=202)
async def reclassify_endpoint(
    reextract: bool = Query(False, description="Si true, ademas re-extrae title/abstract/year desde el PDF en MinIO."),
    justify: str = Query("none", regex="^(none|gold_only|all)$", description="none|gold_only|all. gold_only: Ollama justifica papers con score>=4 tras scoring."),
) -> ReclassifyResponse:
    total = await repos.count_papers()
    if total == 0:
        raise HTTPException(400, "No hay papers para reclasificar")
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "paper_id": "ALL",
        "type": "reclassify_all",
        "status": "queued",
        "stage": f"0/{total}",
        "filename": None,
        "size_bytes": 0,
        "minio_key": None,
        "total": total,
        "processed": 0,
        "reextract": reextract,
        "justify_mode": justify,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "error": None,
    }
    await repos.insert_job(job)
    asyncio.create_task(_run_reclassify(job_id, reextract=reextract, justify_mode=justify))
    return ReclassifyResponse(
        job_id=job_id,
        type="reclassify_all",
        total=total,
        stream_url=f"/stream?job_id={job_id}",
    )


# ---------------------------------------------------------------------------
# Justify (Ollama) — Fase 4
# ---------------------------------------------------------------------------


async def _justify_paper(paper: dict) -> tuple[str, int]:
    """Llama a Ollama y devuelve (justification, ms). NO escribe en Mongo — el caller decide."""
    cfg = await repos.get_config()
    topic = (cfg or {}).get("topic_name", "el tema activo")
    sb = paper.get("score_breakdown", {})
    prompt_system = (
        "Sos un asistente experto en revision bibliografica. Respondes SIEMPRE en espanol neutro, "
        "en una o dos oraciones, justificando la decision asignada a un paper academico. "
        "No saludes ni agregues comentarios fuera de la justificacion."
    )
    prompt_user = (
        f"Tema activo del corpus: {topic}\n"
        f"Paper:\n  Titulo: {paper.get('title', '')}\n"
        f"  Abstract: {(paper.get('abstract') or '(sin abstract disponible)')[:1200]}\n"
        f"Scoring automatico:\n"
        f"  - keyword coverage: {sb.get('keyword', 0):.2f}\n"
        f"  - tfidf vs query:   {sb.get('tfidf', 0):.2f}\n"
        f"  - sbert cosine:     {sb.get('sbert', 0):.2f}\n"
        f"  - weighted total:   {sb.get('weighted', 0):.2f}\n"
        f"Decision asignada: {paper.get('decision', '?')} (score {paper.get('score_final', '?')}/5).\n\n"
        f"Justifica en una o dos oraciones por que esa decision tiene sentido para este paper "
        f"frente al tema activo."
    )
    payload = {
        "model": OLLAMA_DEFAULT_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": prompt_system},
            {"role": "user", "content": prompt_user},
        ],
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0)) as client:
        try:
            r = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        except httpx.RequestError as exc:
            raise HTTPException(502, f"Ollama unreachable: {exc}") from exc
    if r.status_code != 200:
        raise HTTPException(502, f"Ollama error {r.status_code}: {r.text[:200]}")
    data = r.json()
    text = (data.get("message", {}).get("content") or "").strip()
    ms = int(data.get("total_duration", 0) / 1_000_000)
    return text, ms


@app.post("/justify/{paper_id}", response_model=JustifyResponse)
async def justify_paper_endpoint(paper_id: str = Path(...)) -> JustifyResponse:
    """Genera (o regenera) la justificacion de UN paper. Sincrono. Tarda ~5-7s con qwen2.5:1.5b warm."""
    paper = await repos.get_paper(paper_id)
    if not paper:
        raise HTTPException(404, f"Paper {paper_id} no encontrado")
    text, ms = await _justify_paper(paper)
    await repos.update_paper(paper_id, {"justification": text})
    return JustifyResponse(paper_id=paper_id, justification=text, generated_in_ms=ms)


@app.post("/justify", response_model=JustifyBatchResponse, status_code=202)
async def justify_batch_endpoint(body: JustifyRequest) -> JustifyBatchResponse:
    """Justifica un batch de papers en background. Filtros: paper_ids | top | min_score."""
    if body.paper_ids:
        paper_ids = list(body.paper_ids)
    elif body.top is not None:
        rank = await repos.ranking(top=body.top)
        paper_ids = [p["paper_id"] for p in rank]
    elif body.min_score is not None:
        papers = await repos.list_papers(limit=10000, min_score=body.min_score)
        paper_ids = [p["paper_id"] for p in papers]
    else:
        raise HTTPException(400, "Body vacio: pasar 'paper_ids', 'top' o 'min_score'")
    if not paper_ids:
        raise HTTPException(400, "No hay papers que matcheen el filtro")

    job_id = str(uuid.uuid4())
    total = len(paper_ids)
    job = {
        "job_id": job_id,
        "paper_id": "ALL",
        "type": "justify_batch",
        "status": "queued",
        "stage": f"0/{total}",
        "filename": None,
        "size_bytes": 0,
        "minio_key": None,
        "total": total,
        "processed": 0,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "error": None,
    }
    await repos.insert_job(job)
    asyncio.create_task(_run_justify_batch(job_id, paper_ids))
    return JustifyBatchResponse(
        job_id=job_id,
        type="justify_batch",
        total=total,
        stream_url=f"/stream?job_id={job_id}",
    )


async def _run_justify_batch(job_id: str, paper_ids: list[str]) -> None:
    total = len(paper_ids)
    try:
        for i, pid in enumerate(paper_ids, start=1):
            paper = await repos.get_paper(pid)
            if not paper:
                continue
            try:
                text, _ms = await _justify_paper(paper)
                await repos.update_paper(pid, {"justification": text})
            except Exception as exc:
                print(f"[justify_batch] {pid} fallo: {type(exc).__name__}: {exc}")
            await repos.update_job(job_id, {
                "stage": f"{i}/{total}",
                "status": "running",
                "processed": i,
                "total": total,
            })
        await repos.update_job(job_id, {"status": "completed", "stage": f"{total}/{total}"})
    except Exception as exc:
        await repos.update_job(job_id, {"status": "failed", "error": f"{type(exc).__name__}: {exc}"})


# ---------------------------------------------------------------------------
# Workers (background tasks)
# ---------------------------------------------------------------------------


async def _run_pipeline_real(job_id: str, paper_id: str, minio_key: str, justify_mode: str = "none") -> None:
    """Pipeline real para un PDF recien subido."""
    try:
        cfg = await repos.get_config()
        if not cfg:
            raise RuntimeError("Config no inicializada")

        # 1) Extract metadata.
        await repos.update_job(job_id, {"status": "running", "stage": "extracting_metadata"})
        pdf_bytes = get_pdf(minio_key)
        meta = await asyncio.to_thread(pipeline.extract_metadata, pdf_bytes)

        # 2) SBERT embedding del title + abstract.
        await repos.update_job(job_id, {"stage": "embedding_sbert"})
        emb = await asyncio.to_thread(pipeline.embed_text, meta["text"] or meta["title"])

        # 3) Scoring vs config actual.
        await repos.update_job(job_id, {"stage": "scoring"})
        breakdown = pipeline.compute_score(
            text=meta["text"] or meta["title"],
            paper_emb=emb,
            axes=cfg["axes"],
            query_text=cfg["query_text"],
            query_emb=cfg.get("query_embedding"),
            weights=cfg["weights"],
        )
        score, decision = pipeline.score_to_decision(
            breakdown["weighted"], meta["year"], cfg["year_range"], cfg.get("thresholds"),
        )

        # 4) Copy PDF al folder del tier (gold/silver/bronze/out_of_range).
        tier_minio_key: str | None = None
        try:
            tier_minio_key = copy_to_tier(paper_id, minio_key, score)
        except Exception as exc:
            print(f"[tier copy] {paper_id} fallo: {type(exc).__name__}: {exc}")

        # 5) Persist paper.
        paper_doc = {
            "paper_id": paper_id,
            "title": meta["title"],
            "abstract": meta["abstract"],
            "year": meta["year"],
            "text": meta["text"],
            "embedding": emb,
            "score_final": score,
            "score_breakdown": breakdown,
            "decision": decision,
            "justification": None,
            "minio_key": minio_key,
            "tier_minio_key": tier_minio_key,
            "created_at": _now_iso(),
        }
        await repos.insert_paper(paper_doc)

        # 5) Re-fit del TF-IDF para que el proximo paper aproveche este texto.
        papers_all = await repos.list_papers_full()
        pipeline.fit_vectorizer([(p.get("text") or p.get("title") or "") for p in papers_all])

        # 6) (Opcional) Justification con Ollama.
        if justify_mode == "auto":
            await repos.update_job(job_id, {"stage": "ollama_justify"})
            try:
                fresh = await repos.get_paper(paper_id) or paper_doc
                text, _ms = await _justify_paper(fresh)
                await repos.update_paper(paper_id, {"justification": text})
            except Exception as exc:
                print(f"[justify auto] {paper_id} fallo: {type(exc).__name__}: {exc}")

        await repos.update_job(job_id, {"status": "completed", "stage": "completed"})
    except Exception as exc:
        await repos.update_job(job_id, {"status": "failed", "error": f"{type(exc).__name__}: {exc}"})


async def _run_reclassify(job_id: str, reextract: bool = False, justify_mode: str = "none") -> None:
    """Re-scoring sobre TODOS los papers con la config actual. Si reextract=True,
    ademas vuelve a extraer metadata + embedding desde el PDF original en MinIO
    (solo para papers con minio_key). Util para aplicar mejoras del extractor sin
    re-subir manualmente cada PDF."""
    try:
        cfg = await repos.get_config()
        if not cfg:
            raise RuntimeError("Config no inicializada")

        papers = await repos.list_papers_full()
        total = len(papers)
        if total == 0:
            await repos.update_job(job_id, {"status": "completed", "stage": "0/0"})
            return

        # Si vamos a re-extraer, primero refrescamos el doc en Mongo y la copia en memoria.
        if reextract:
            await repos.update_job(job_id, {"status": "running", "stage": f"reextract 0/{total}"})
            for i, paper in enumerate(papers, start=1):
                if paper.get("minio_key"):
                    try:
                        pdf_bytes = get_pdf(paper["minio_key"])
                        meta = await asyncio.to_thread(pipeline.extract_metadata, pdf_bytes)
                        emb = await asyncio.to_thread(pipeline.embed_text, meta["text"] or meta["title"])
                        await repos.update_paper(paper["paper_id"], {
                            "title": meta["title"],
                            "abstract": meta["abstract"],
                            "year": meta["year"],
                            "text": meta["text"],
                            "embedding": emb,
                        })
                        # Refrescar la copia local para el scoring que sigue.
                        paper.update({
                            "title": meta["title"],
                            "abstract": meta["abstract"],
                            "year": meta["year"],
                            "text": meta["text"],
                            "embedding": emb,
                        })
                    except Exception as exc:
                        # Reextract de un paper individual no aborta el job entero.
                        print(f"[reextract] {paper['paper_id']} fallo: {exc}")
                await repos.update_job(job_id, {"stage": f"reextract {i}/{total}"})

        # Re-fit TF-IDF sobre los textos (ahora actualizados si hubo reextract).
        await repos.update_job(job_id, {"status": "running", "stage": f"fit_tfidf {total}/{total}"})
        corpus = [(p.get("text") or p.get("title") or "") for p in papers]
        await asyncio.to_thread(pipeline.fit_vectorizer, corpus)

        for i, paper in enumerate(papers, start=1):
            text = paper.get("text") or paper.get("title") or ""
            emb = paper.get("embedding")
            if not emb and text:
                emb = await asyncio.to_thread(pipeline.embed_text, text)
                await repos.update_paper(paper["paper_id"], {"embedding": emb})

            breakdown = pipeline.compute_score(
                text=text,
                paper_emb=emb,
                axes=cfg["axes"],
                query_text=cfg["query_text"],
                query_emb=cfg.get("query_embedding"),
                weights=cfg["weights"],
            )
            score, decision = pipeline.score_to_decision(
                breakdown["weighted"], paper.get("year", 2024), cfg["year_range"], cfg.get("thresholds"),
            )

            # Copiar/mover al folder del tier (solo papers con minio_key).
            # Copia siempre que: (a) el paper no tenga tier_minio_key aun, o
            #                    (b) el tier nuevo difiera del actual.
            update_fields: dict = {
                "score_breakdown": breakdown,
                "score_final": score,
                "decision": decision,
            }
            mk = paper.get("minio_key")
            old_tier_key = paper.get("tier_minio_key")
            expected_tier_key = tier_key(paper["paper_id"], score) if mk else None
            if mk and expected_tier_key != old_tier_key:
                try:
                    new_tier_key = copy_to_tier(paper["paper_id"], mk, score)
                    if old_tier_key and old_tier_key != new_tier_key:
                        remove_object(old_tier_key)
                    update_fields["tier_minio_key"] = new_tier_key
                except Exception as exc:
                    print(f"[tier move] {paper['paper_id']} fallo: {type(exc).__name__}: {exc}")

            await repos.update_paper(paper["paper_id"], update_fields)

            await repos.update_job(job_id, {
                "stage": f"{i}/{total}",
                "status": "running",
                "processed": i,
                "total": total,
            })

        # (Opcional) Justification con Ollama tras scoring.
        if justify_mode in ("gold_only", "all"):
            fresh_papers = await repos.list_papers_full()
            if justify_mode == "gold_only":
                targets = [p for p in fresh_papers if (p.get("score_final") or 0) >= 4]
            else:
                targets = fresh_papers
            n = len(targets)
            for j, paper in enumerate(targets, start=1):
                try:
                    text, _ms = await _justify_paper(paper)
                    await repos.update_paper(paper["paper_id"], {"justification": text})
                except Exception as exc:
                    print(f"[justify {justify_mode}] {paper['paper_id']} fallo: {type(exc).__name__}: {exc}")
                await repos.update_job(job_id, {"stage": f"justify {j}/{n}", "status": "running"})

        await repos.update_job(job_id, {"status": "completed", "stage": f"{total}/{total}"})
    except Exception as exc:
        await repos.update_job(job_id, {"status": "failed", "error": f"{type(exc).__name__}: {exc}"})


# ---------------------------------------------------------------------------
# Import batch desde MinIO
# ---------------------------------------------------------------------------


@app.post("/papers/import", response_model=ImportResponse, status_code=202)
async def import_papers_endpoint(body: ImportRequest) -> ImportResponse:
    """Importa todos los PDFs bajo un prefijo del bucket. Cada PDF se copia a
    `examen-api/uploads/PAPER_X.pdf` con un paper_id nuevo y se pasa por el
    pipeline real (extract + embed + score + tier copy)."""
    try:
        keys = list_objects(body.source_prefix)
    except Exception as exc:
        raise HTTPException(500, f"No se pudo listar el prefix: {exc}") from exc
    if not keys:
        raise HTTPException(404, f"No se encontraron PDFs bajo '{body.source_prefix}'")
    if body.limit:
        keys = keys[: body.limit]

    job_id = str(uuid.uuid4())
    total = len(keys)
    job = {
        "job_id": job_id,
        "paper_id": "ALL",
        "type": "import_batch",
        "status": "queued",
        "stage": f"0/{total}",
        "filename": None,
        "size_bytes": 0,
        "minio_key": None,
        "total": total,
        "processed": 0,
        "source_prefix": body.source_prefix,
        "justify_mode": body.justify,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "error": None,
    }
    await repos.insert_job(job)
    asyncio.create_task(_run_import_batch(job_id, keys, body.justify))
    return ImportResponse(
        job_id=job_id,
        type="import_batch",
        total=total,
        stream_url=f"/stream?job_id={job_id}",
    )


async def _run_import_batch(job_id: str, source_keys: list[str], justify_mode: str) -> None:
    """Itera keys del bucket, copia cada PDF a examen-api/uploads/ y dispara
    el pipeline real. Errores individuales no abortan el batch."""
    from app.db import MINIO_BUCKET, MINIO_PREFIX, get_minio  # local import para mantener el namespace
    from minio.commonconfig import CopySource

    client = get_minio()
    total = len(source_keys)
    try:
        for i, src_key in enumerate(source_keys, start=1):
            try:
                paper_id = await repos.next_paper_id()
                dst_key = f"{MINIO_PREFIX}/{paper_id}.pdf"
                # Copy server-side (no transfiere bytes al cliente).
                client.copy_object(MINIO_BUCKET, dst_key, CopySource(MINIO_BUCKET, src_key))

                # Crear job hijo de tipo ingest y lanzar pipeline. NO esperamos:
                # el SSE del job batch ya muestra X/N, no necesitamos progreso
                # per-paper acá.
                child_job_id = str(uuid.uuid4())
                await repos.insert_job({
                    "job_id": child_job_id,
                    "paper_id": paper_id,
                    "type": "ingest",
                    "status": "queued",
                    "stage": "queued",
                    "filename": src_key.rsplit("/", 1)[-1],
                    "size_bytes": 0,
                    "minio_key": dst_key,
                    "imported_from": src_key,
                    "justify_mode": justify_mode,
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                    "error": None,
                })
                # await sequencial para no saturar SBERT con N tasks paralelas
                # (el modelo es CPU-bound; paralelismo no ayuda en CPU).
                await _run_pipeline_real(child_job_id, paper_id, dst_key, justify_mode=justify_mode)
            except Exception as exc:
                print(f"[import] {src_key} fallo: {type(exc).__name__}: {exc}")

            await repos.update_job(job_id, {
                "stage": f"{i}/{total}",
                "status": "running",
                "processed": i,
                "total": total,
            })

        await repos.update_job(job_id, {"status": "completed", "stage": f"{total}/{total}"})
    except Exception as exc:
        await repos.update_job(job_id, {"status": "failed", "error": f"{type(exc).__name__}: {exc}"})


# ---------------------------------------------------------------------------
# SSE + chat
# ---------------------------------------------------------------------------


@app.get("/stream")
async def stream(request: Request, job_id: str | None = Query(None)) -> EventSourceResponse:
    async def event_generator():
        last_stage: str | None = None
        while True:
            if await request.is_disconnected():
                break
            if job_id:
                job = await repos.get_job(job_id)
                if not job:
                    yield {"event": "error", "data": json.dumps({"detail": "job not found"})}
                    break
                if job.get("stage") != last_stage:
                    last_stage = job.get("stage")
                    yield {"event": "job.progress", "data": json.dumps(job)}
                if job.get("status") in ("completed", "failed"):
                    final_event = "job.completed" if job["status"] == "completed" else "job.failed"
                    yield {"event": final_event, "data": json.dumps(job)}
                    break
            else:
                yield {
                    "event": "heartbeat",
                    "data": json.dumps({
                        "time": _now_iso(),
                        "jobs_in_flight": await repos.count_jobs_in_flight(),
                    }),
                }
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    model = req.model or OLLAMA_DEFAULT_MODEL
    payload = {
        "model": model,
        "stream": False,
        "messages": [m.model_dump() for m in req.messages],
    }
    timeout = httpx.Timeout(120.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        except httpx.RequestError as exc:
            raise HTTPException(502, f"Ollama unreachable: {exc}") from exc
    if r.status_code != 200:
        raise HTTPException(502, f"Ollama upstream error {r.status_code}: {r.text[:200]}")
    data = r.json()
    return ChatResponse(
        model=model,
        message=data.get("message", {}).get("content", ""),
        total_duration_ms=int(data.get("total_duration", 0) / 1_000_000),
        eval_count=data.get("eval_count", 0),
    )
