SHELL := /bin/bash
.DEFAULT_GOAL := help

ROOT := $(shell cd .. && pwd)
PY := $(ROOT)/.venv/bin/python

# Acceso SSH al VPS (idénticos flags al tunnel.sh)
SSH := SSHPASS='$(shell grep ^VPS_PASS $(ROOT)/.env | cut -d= -f2)' sshpass -e ssh \
       -o StrictHostKeyChecking=no -o PreferredAuthentications=password \
       -o PubkeyAuthentication=no
SCP := SSHPASS='$(shell grep ^VPS_PASS $(ROOT)/.env | cut -d= -f2)' sshpass -e scp \
       -o StrictHostKeyChecking=no -o PreferredAuthentications=password \
       -o PubkeyAuthentication=no
RSYNC_FLAGS := -avz --exclude '__pycache__' --exclude '.venv' --exclude 'outputs/embeddings.npy' \
               --exclude '.cache' --exclude '*.parquet' --exclude '*.xlsx'
VPS_USER := $(shell grep ^VPS_USER $(ROOT)/.env | cut -d= -f2)
VPS_HOST := $(shell grep ^VPS_HOST $(ROOT)/.env | cut -d= -f2)
REMOTE := /root/proyecto_papers/grupo3_ciberseguridad

.PHONY: help upload extract score silver gold ranking report run pipeline \
        deploy build-vps up-vps run-vps logs-vps stop-vps

help: ## Lista targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ───── Fases del pipeline (LOCAL) ─────
upload: ## Fase 1: sube los 2000 PDFs a MinIO Bronze
	$(PY) -m classifier.src.upload_bronze --workers 24

extract: ## Fase 2: extrae metadata con PyMuPDF
	$(PY) -m classifier.src.extract_metadata --workers 8

score: ## Fase 3: scoring híbrido (kw + tfidf + sbert)
	$(PY) -m classifier.src.score

silver: ## Fase 4a: silver.xlsx
	$(PY) -m classifier.src.build_silver

gold: ## Fase 4b: gold.parquet + gold.xlsx
	$(PY) -m classifier.src.build_gold

ranking: ## Fase 5: ranking.xlsx
	$(PY) -m classifier.src.ranking

report: ## Fase 6: report.md
	$(PY) -m classifier.src.reporter

run: ## Pipeline completo end-to-end
	$(PY) -m classifier.src.pipeline run

# ───── Deploy y run en VPS ─────
deploy: ## rsync del clasificador al VPS bajo /root/proyecto_papers/grupo3_ciberseguridad
	@$(SSH) $(VPS_USER)@$(VPS_HOST) "mkdir -p $(REMOTE)"
	@SSHPASS='$(shell grep ^VPS_PASS $(ROOT)/.env | cut -d= -f2)' sshpass -e rsync $(RSYNC_FLAGS) \
		-e 'ssh -o StrictHostKeyChecking=no -o PreferredAuthentications=password -o PubkeyAuthentication=no' \
		Dockerfile docker-compose.classifier.yml requirements.txt \
		search_query.py score_rubric.md Makefile \
		src \
		$(VPS_USER)@$(VPS_HOST):$(REMOTE)/

build-vps: deploy ## Build de la imagen en el VPS
	@$(SSH) $(VPS_USER)@$(VPS_HOST) "cd $(REMOTE) && docker compose -f docker-compose.classifier.yml build"

up-vps: build-vps ## Levanta el container en VPS (sleep infinity)
	@$(SSH) $(VPS_USER)@$(VPS_HOST) "cd $(REMOTE) && docker compose -f docker-compose.classifier.yml up -d"
	@$(SSH) $(VPS_USER)@$(VPS_HOST) "docker ps --filter name=classifier-g3"

run-vps: ## Corre el pipeline completo dentro del container del VPS
	@$(SSH) -t $(VPS_USER)@$(VPS_HOST) "docker exec -it classifier-g3 python -m classifier.src.pipeline run"

logs-vps: ## Tail de logs del container
	@$(SSH) -t $(VPS_USER)@$(VPS_HOST) "docker logs classifier-g3 --tail 100 -f"

stop-vps: ## Apaga el container
	@$(SSH) $(VPS_USER)@$(VPS_HOST) "cd $(REMOTE) && docker compose -f docker-compose.classifier.yml down"
