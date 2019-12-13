#!make

NAME := akkeluukkonen/rubus
COMMIT := $$(git rev-parse HEAD)
LATEST := ${NAME}:latest
RELEASE := ${NAME}:release

build:
	@docker build -t ${LATEST} --label git-commit=${COMMIT} -f docker/app/Dockerfile .

clean:
	@docker-compose down --volume

run: build
	@docker-compose up

push:
	@echo "Pushing all relevant images to remote"
	@docker push ${NAME}

release:
	@docker tag ${LATEST} ${NAME}:$$(poetry version ${VERSION} | rev | cut -d' ' -f1 | rev)
	@docker tag ${LATEST} ${RELEASE}
	@docker push ${NAME}
