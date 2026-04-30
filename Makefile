# PMET monorepo top-level Makefile

.PHONY: help build build-core clean-core-binaries build-indexing build-pairing demo demo-indexing demo-pairing baseline clean \
        clean-results clean-results-app clean-results-cli \
        fetch-data build-app up down logs ps rebuild

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
BUILD := $(ROOT)/build
CMAKE ?= cmake

help:
	@echo "PMET monorepo targets:"
	@echo ""
	@echo "  Local CLI / dev — host-side, no docker"
	@echo "    build        - compile core C/C++ engines into ./build/  (NOT the web app)"
	@echo "    demo         - run demo indexing + pairing against data/"
	@echo "    baseline     - capture fingerprints to tests/baseline/fingerprints.txt"
	@echo "    fetch-data   - download TAIR10 + per-species indexes (run ONCE, ~16 GB)"
	@echo "    clean        - remove ./build/ (compiled core binaries)"
	@echo "    clean-results-app - wipe results/app/ (web-app task outputs)"
	@echo "    clean-results-cli - wipe results/cli/ (CLI / pipeline outputs)"
	@echo "    clean-results     - both of the above"
	@echo ""
	@echo "  Web app stack — docker-compose, exposes nginx on http://localhost:5960"
	@echo "    build-app    - build the docker images only (api + worker + frontend)"
	@echo "    up           - build + start the full stack (api + worker + frontend + nginx + redis)"
	@echo "    down         - stop the stack"
	@echo "    rebuild      - rebuild images and restart"
	@echo "    logs         - tail logs from all services"
	@echo "    ps           - show service status"
	@echo ""
	@echo "  Note: 'build' (above) compiles host binaries for CLI; 'build-app' / 'up'"
	@echo "        build docker images. They are independent — host CLI does not need"
	@echo "        the docker stack and vice versa."
	@echo ""
	@echo "  More deploy targets: cd deploy && make help"

# ---- Local CLI / dev ----

build: build-core

build-core: clean-core-binaries build-indexing build-pairing

clean-core-binaries:
	@mkdir -p $(BUILD)
	@rm -f $(BUILD)/index_c $(BUILD)/index_cpp $(BUILD)/pair_original
	@rm -f $(BUILD)/index_fimo_fused $(BUILD)/pair_parallel

build-indexing:
	@$(CMAKE) -S $(ROOT)/core/indexing -B $(BUILD)/cmake/indexing \
		-DCMAKE_BUILD_TYPE=Release \
		-DCMAKE_RUNTIME_OUTPUT_DIRECTORY=$(BUILD)
	@$(CMAKE) --build $(BUILD)/cmake/indexing --parallel

build-pairing:
	@$(CMAKE) -S $(ROOT)/core/pairing -B $(BUILD)/cmake/pairing \
		-DCMAKE_BUILD_TYPE=Release \
		-DCMAKE_RUNTIME_OUTPUT_DIRECTORY=$(BUILD)
	@$(CMAKE) --build $(BUILD)/cmake/pairing --parallel

demo: demo-indexing demo-pairing

demo-indexing:
	@bash apps/cli/scripts/run_indexing.sh -v fused

demo-pairing:
	@bash apps/cli/scripts/run_pairing.sh

baseline:
	@bash tests/baseline/capture.sh > tests/baseline/fingerprints.txt
	@echo "wrote tests/baseline/fingerprints.txt"

fetch-data:
	@bash scripts/fetch_data.sh

clean:
	@rm -rf $(BUILD)

clean-results-app:
	@rm -rf $(ROOT)/results/app/*
	@echo "wiped results/app/"

clean-results-cli:
	@rm -rf $(ROOT)/results/cli/*
	@echo "wiped results/cli/"

clean-results: clean-results-app clean-results-cli

# ---- Web app (proxies into deploy/) ----
# These shortcuts run docker-compose from deploy/ so you don't need to cd.
# All targets accept the same env vars as the underlying compose commands.
#
# Naming: this section's `build-app` builds *docker images* via docker-compose.
# The unrelated top-level `build` target above compiles host C/C++ binaries
# for CLI use — same word, very different artifact.

build-app:
	@$(MAKE) -C deploy build-images

up:
	@# 1. Stop our own compose project cleanly (no-op if nothing running).
	@$(MAKE) -C deploy stop 2>/dev/null || true
	@# 2. If any *other* docker container is still publishing :5960 — typically
	@#    a leftover from the pre-monorepo `pmet_shiny_app` compose project —
	@#    stop and remove it so the new stack can bind the port.
	@blockers=$$(docker ps --filter "publish=5960" --format "{{.Names}}" 2>/dev/null); \
	if [ -n "$$blockers" ]; then \
		echo "Stopping leftover containers on :5960 — $$blockers"; \
		echo "$$blockers" | xargs -n1 docker stop >/dev/null; \
		echo "$$blockers" | xargs -n1 docker rm   >/dev/null 2>&1 || true; \
	fi
	@# 3. If the port is *still* bound (some non-docker host process), bail
	@#    out with a clear diagnostic instead of failing inside docker.
	@if lsof -nP -iTCP:5960 -sTCP:LISTEN >/dev/null 2>&1; then \
		echo "ERROR: port 5960 is held by a non-docker host process:"; \
		lsof -nP -iTCP:5960 -sTCP:LISTEN; \
		echo ""; \
		echo "Free it manually, or change the host port in deploy/docker-compose.yml."; \
		exit 1; \
	fi
	@$(MAKE) -C deploy build-images
	@$(MAKE) -C deploy start
	@echo ""
	@echo "PMET stack is up — http://localhost:5960"

down:
	@$(MAKE) -C deploy stop

rebuild:
	@$(MAKE) -C deploy rebuild

logs:
	@$(MAKE) -C deploy logs

ps:
	@cd deploy && docker-compose ps
