CONTAINER_ENGINE ?= podman
IMAGE ?= ttl-lama
GHCR_IMAGE ?= ghcr.io/remiv1/ttl-lama
TAG ?= latest
TEST_ARGS ?=

.PHONY: help build run test push

help:
	@printf '%s\n' \
	  'Targets:' \
	  '  build  Build $(IMAGE):$(TAG)' \
	  '  run    Run $(IMAGE):$(TAG) on port 8080' \
	  '  test   Run scripts/test-launcher.sh (pass options with TEST_ARGS="...")' \
	  '  push   Push $(GHCR_IMAGE):$(TAG) to GHCR'

build:
	$(CONTAINER_ENGINE) build -f src/Dockerfile -t $(IMAGE):$(TAG) .

run:
	$(CONTAINER_ENGINE) run --rm -p 8080:8080 po$(IMAGE):$(TAG)

test:
	./scripts/test-launcher.sh $(TEST_ARGS)

push:
	$(CONTAINER_ENGINE) tag $(IMAGE):$(TAG) $(GHCR_IMAGE):$(TAG)
	$(CONTAINER_ENGINE) push $(GHCR_IMAGE):$(TAG)
