#!make
include .env

NAME := akkeluukkonen/rubus
TAG := $$(git rev-parse HEAD)
IMAGE := ${NAME}:${TAG}
LATEST := ${NAME}:latest

all: build push

build:
	@docker build -t ${IMAGE} -f docker/app/Dockerfile --build-arg poetry_version=${POETRY_VERSION} .
	@docker tag ${IMAGE} ${LATEST}

push:
	@docker push ${NAME}
