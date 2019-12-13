#!make

NAME := akkeluukkonen/rubus
COMMIT := $$(git rev-parse HEAD)
IMAGE := ${NAME}:${COMMIT}
LATEST := ${NAME}:latest
RELEASE := ${NAME}:release

build:
	@docker build -t ${IMAGE} --label git-commit=${COMMIT} -f docker/app/Dockerfile .
	@docker tag ${IMAGE} ${LATEST}

latest:
	@echo "Pushing latest image to remote"
	@docker push ${LATEST}

release:
	@echo "Tagging latest build as release and pushing it to remote"
	@docker tag ${LATEST} ${RELEASE}
	@docker push ${RELEASE}
