#!make
include .env

NAME := akkeluukkonen/rubus
TAG := $$(git rev-parse HEAD)
IMAGE := ${NAME}:${TAG}
LATEST := ${NAME}:latest
RELEASE := ${NAME}:release

all: build push

build:
	@docker build -t ${IMAGE} -f docker/app/Dockerfile --build-arg poetry_version=${POETRY_VERSION} .
	@docker tag ${IMAGE} ${LATEST}

push:
	@echo "Pushing all images for ${NAME} to remote"
	@docker push ${NAME}

release:
	@echo "Tagging latest build as release and pushing it to remote"
	@docker tag ${LATEST} ${RELEASE}
	@docker push ${RELEASE}
