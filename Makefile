# PMET monorepo top-level Makefile

.PHONY: help build build-core clean-core-binaries build-indexing build-pairing baseline clean \
        clean-results clean-results-app clean-results-cli \
        fetch-data build-app up down logs ps rebuild \
        test test-core test-pairing test-indexing test-unit test-integration test-audit

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
BUILD := $(ROOT)/build
CMAKE ?= cmake

help:
	@echo "PMET monorepo targets:"
	@echo ""
	@echo "  Local CLI / dev — host-side, no docker"
	@echo "    build            - compile core C/C++ engines into ./build/  (NOT the web app)"
	@echo "    fetch-data       - download TAIR10 + per-species indexes (run ONCE, ~16 GB)"
	@echo "    clean            - remove ./build/ (compiled core binaries)"
	@echo "    clean-results-app - wipe results/app/ (web-app task outputs)"
	@echo "    clean-results-cli - wipe results/cli/ (CLI / pipeline outputs)"
	@echo "    clean-results    - both of the above"
	@echo ""
	@echo "  Tests — every track has a make target; 'make test' chains the fast ones"
	@echo "    test             - test-core + test-unit + test-integration  (~10 s, gate before commit)"
	@echo "    test-core        - C/C++ math kernels (test-pairing + test-indexing, ~5 s)"
	@echo "    test-pairing     - just the pairing kernel tests"
	@echo "    test-indexing    - just the indexing kernel tests"
	@echo "    test-unit        - repo-wide unit tests (Python / R / bash / TS, ~5 s)"
	@echo "    test-integration - integration smoke + heatmap consistency (~3-10 s; other tests/integration/*.sh need real data)"
	@echo "    test-audit       - workflow audit; renders docs/workflows/*.md (minutes)"
	@echo "    baseline         - CLI baseline fingerprints to tests/baseline/fingerprints.txt"
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
	@rm -f $(BUILD)/indexing_fimo_fused $(BUILD)/pairing_parallel

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

# Pairing C++ unit tests. Configures a separate build dir with
# -DPMET_BUILD_TESTS=ON, builds the `test_pairing` binary into
# build/test_pairing, and runs it. Math kernels only — see
# core/pairing/tests/ for what's covered.
test-pairing:
	@$(CMAKE) -S $(ROOT)/core/pairing -B $(BUILD)/cmake/pairing-tests \
		-DCMAKE_BUILD_TYPE=Release \
		-DPMET_BUILD_TESTS=ON \
		-DCMAKE_RUNTIME_OUTPUT_DIRECTORY=$(BUILD)
	@$(CMAKE) --build $(BUILD)/cmake/pairing-tests --target test_pairing --parallel
	@$(BUILD)/test_pairing

# Indexing C unit tests. Same shape as test-pairing but builds the
# `test_indexing` binary against the PMET-side sources (the FIMO
# sources are excluded — they're upstream MEME C and not what we
# wrote). See core/indexing/tests/ for coverage.
test-indexing:
	@$(CMAKE) -S $(ROOT)/core/indexing -B $(BUILD)/cmake/indexing-tests \
		-DCMAKE_BUILD_TYPE=Release \
		-DPMET_BUILD_TESTS=ON \
		-DCMAKE_RUNTIME_OUTPUT_DIRECTORY=$(BUILD)
	@$(CMAKE) --build $(BUILD)/cmake/indexing-tests --target test_indexing --parallel
	@$(BUILD)/test_indexing

# Run both core test suites end-to-end.
test-core: test-pairing test-indexing

# Repo-wide unit tests — Python / R / bash / TS, < 5 s, no docker.
# Auto-skips R / TS rows when their toolchains aren't installed.
test-unit:
	@bash tests/unit/run.sh

# Integration smoke — bedtools / samtools invariants on tiny fixtures,
# plus a TAIR10 strand check that auto-skips when the reference isn't
# present. The other scripts under tests/integration/ are heavier (need
# the full pipeline) and stay opt-in — see tests/integration/README.md.
test-integration:
	@bash tests/integration/run_smoke.sh

# Workflow audit — runs each workflow against canonical inputs and
# renders the per-workflow docs at docs/workflows/*.md. Minutes
# (pair_only ~15 s, intervals ~16 s, promoter ~2 min, elements ~5 min),
# so kept out of the default `make test` aggregator.
test-audit:
	@python3 tests/audit/generate.py

# Default aggregator: all the fast tracks. Audit + baseline write
# files to disk, so they remain explicit opt-ins.
test: test-core test-unit test-integration

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
