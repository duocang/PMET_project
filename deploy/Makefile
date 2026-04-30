# PMET - Paired Motif Enrichment Tool

.PHONY: help start stop build-images rebuild rebuild-frontend rebuild-backend \
        restart restart-worker restart-nginx clean logs \
        api worker frontend test install-frontend install-backend init \
        fetch-data

# PMET binaries are built from the in-repo core/ sources during
# `docker build` (apps/pmet_backend/Dockerfile copies core/ and builds
# core/indexing + core/pairing with CMake). No upstream-SHA pinning is
# needed; the layer cache busts when core/ changes.

help:
	@echo "PMET commands"
	@echo ""
	@echo "  First-time / full reset"
	@echo "    make fetch-data         - Download TAIR10 reference + indexing archives (run ONCE, ~GBs)"
	@echo "    make build-images       - Build all docker images (5-10 min first time)"
	@echo "    make start              - Start all services in the background"
	@echo "    make stop               - Stop all services"
	@echo "    make clean              - Stop services, remove volumes, wipe result/"
	@echo ""
	@echo "  After changing code (most common)"
	@echo "    make rebuild-frontend   - Rebuild + restart ONLY the frontend container"
	@echo "                              (use after editing anything in pmet_frontend/)"
	@echo "    make restart-worker     - Restart ONLY the celery worker"
	@echo "                              (use after editing pmet_backend/worker or services)"
	@echo "    make restart-nginx      - Restart ONLY nginx (after editing nginx/nginx.conf)"
	@echo "    make rebuild            - Rebuild + restart EVERYTHING (nuclear option)"
	@echo ""
	@echo "  Note: editing pmet_backend/api/ requires NO action — the API auto-reloads."
	@echo ""
	@echo "  Other"
	@echo "    make logs               - Tail logs from all services"
	@echo "    make rebuild-backend    - Rebuild + restart api + worker"
	@echo "    make api / worker / frontend - Run a single service locally (no Docker)"
	@echo "    make test               - Run backend smoke tests"

# -------------------------------------------------------------------------
# Lifecycle
# -------------------------------------------------------------------------

start:
	docker-compose up -d

stop:
	docker-compose down

build-images:
	@echo "Building docker images from local core/"
	docker-compose build

clean:
	docker-compose down -v
	rm -rf result/*

logs:
	docker-compose logs -f

# -------------------------------------------------------------------------
# Rebuild / restart helpers (use these after editing code)
# -------------------------------------------------------------------------

# Rebuild and restart everything. Always correct, just slower.
rebuild:
	@echo "Building images from local core/"
	docker-compose build
	docker-compose up -d

# Rebuild and restart only the frontend image.
# Use this after editing anything under pmet_frontend/.
# The frontend is baked into its image at build time (no bind mount),
# so code changes require a rebuild to take effect.
rebuild-frontend:
	docker-compose build frontend
	docker-compose up -d frontend

# Rebuild and restart only the backend image (shared by api + worker).
# Only needed when pmet_backend/Dockerfile or requirements.txt change.
# For normal Python edits use restart-worker (or nothing, for api).
rebuild-backend:
	@echo "Building images from local core/"
	docker-compose build api
	docker-compose up -d api worker

# Restart the celery worker so it picks up edited Python code.
# The backend source is bind-mounted into the container, so no rebuild
# is needed — but celery does not auto-reload, hence the explicit restart.
restart-worker:
	docker-compose restart worker

# Restart nginx after editing nginx/nginx.conf (the file is mounted, so
# no rebuild is needed; a restart just reloads the config).
restart-nginx:
	docker-compose restart nginx

# Restart every running container without rebuilding images.
restart:
	docker-compose restart

# -------------------------------------------------------------------------
# Local (non-Docker) dev
# -------------------------------------------------------------------------

api:
	cd ../apps/pmet_backend && uvicorn api.main:app --reload --port 8000

worker:
	cd ../apps/pmet_backend && celery -A worker.celery_app worker --loglevel=info

frontend:
	cd ../apps/pmet_frontend && npm run dev

test:
	cd ../apps/pmet_backend && python test_api.py

install-frontend:
	cd ../apps/pmet_frontend && npm install

install-backend:
	pip install -r ../apps/pmet_backend/requirements.txt

init:
	make install-backend
	make install-frontend

# Download reference genomes (TAIR10) and pre-computed indexing archives
# into data/. Safe to re-run — already-present files are skipped. Run on
# the host (not inside Docker): data/ is bind-mounted into the api and
# worker containers, so the downloads appear there without rebuilding.
fetch-data:
	bash ../pipeline/data/download_pmet_data.sh
