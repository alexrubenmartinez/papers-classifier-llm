"""CLI entrypoint del clasificador.

Uso:
    python -m classifier.src.pipeline run            # corre todas las fases en orden
    python -m classifier.src.pipeline upload         # solo Bronze
    python -m classifier.src.pipeline extract        # solo Silver-raw
    python -m classifier.src.pipeline score          # solo scoring (Silver final)
    python -m classifier.src.pipeline build-silver   # solo xlsx Silver
    python -m classifier.src.pipeline gold           # solo Gold
    python -m classifier.src.pipeline ranking        # solo ranking
    python -m classifier.src.pipeline report         # solo report.md
"""
from __future__ import annotations

import argparse
import sys
import time

from rich.console import Console

from classifier.src import (
    upload_bronze, extract_metadata, score,
    build_silver, build_gold, ranking, reporter,
)

console = Console()


PHASES = {
    "upload": ("Bronze upload", lambda args: upload_bronze.run(limit=args.limit, workers=args.workers)),
    "extract": ("Silver-raw extract", lambda args: extract_metadata.run(limit=args.limit, workers=args.extract_workers)),
    "score": ("Scoring", lambda args: score.run(skip_sbert=args.skip_sbert, use_cache=not args.no_cache)),
    "build-silver": ("Silver xlsx", lambda args: build_silver.run()),
    "gold": ("Gold", lambda args: build_gold.run()),
    "ranking": ("Ranking", lambda args: ranking.run()),
    "report": ("Reporte markdown", lambda args: reporter.run()),
}

FULL_ORDER = ["upload", "extract", "score", "build-silver", "gold", "ranking", "report"]
# `run` por defecto: el upload se asume hecho desde local. En el container del VPS
# no hay acceso a la carpeta Articulos/, así que arrancamos en extract.
RUN_DEFAULT = ["extract", "score", "build-silver", "gold", "ranking", "report"]
# `rescore` cuando solo cambiaron las keywords (no los PDFs): salta extract porque
# silver_metadata.parquet sigue valido. Usado por el API tras cada /reclassify.
RESCORE_ORDER = ["score", "build-silver", "gold", "ranking", "report"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["run", "rescore", *PHASES.keys()],
                    help="Fase a ejecutar. `run`=extract..report; `rescore`=score..report (skip extract)")
    ap.add_argument("--full", action="store_true",
                    help="incluir Fase 1 (upload local de PDFs) en `run`")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--extract-workers", type=int, default=8)
    ap.add_argument("--skip-sbert", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    if args.phase in ("run", "rescore"):
        if args.phase == "rescore":
            order = RESCORE_ORDER
        else:
            order = FULL_ORDER if args.full else RUN_DEFAULT
        global_started = time.perf_counter()
        for ph in order:
            name, fn = PHASES[ph]
            console.print(f"\n[bold magenta]» Fase: {name}[/bold magenta]\n")
            t0 = time.perf_counter()
            rc = fn(args)
            elapsed = time.perf_counter() - t0
            if rc != 0:
                console.print(f"[red]✗ {name} falló (rc={rc})[/red]")
                sys.exit(rc)
            console.print(f"[dim]{name}: {elapsed:.1f}s[/dim]")
        console.print(f"\n[bold green]✓ Pipeline completo en {time.perf_counter()-global_started:.1f}s[/bold green]")
        return

    name, fn = PHASES[args.phase]
    sys.exit(fn(args))


if __name__ == "__main__":
    main()
