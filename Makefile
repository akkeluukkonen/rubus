#!make

NAME := akkeluukkonen/rubus
COMMIT := $$(git rev-parse HEAD)
LATEST := ${NAME}:latest
RELEASE := ${NAME}:release
VERSION := patch # Default

git-dirty-check:
	# Will fail if the repository is dirty to avoid mislabeling images
	git diff --quiet || exit 1
	# Also fail from untracked files inside rubus/ as this affects image building
	git status --short -- rubus/ || exit 1

build: git-dirty-check
	@docker build -t ${LATEST} --label git-commit=${COMMIT} -f docker/app/Dockerfile .

run: build
	@docker-compose up

push:
	@docker push ${LATEST}

version: git-dirty-check
	@poetry version ${VERSION} | rev | cut -d' ' -f1 | rev > .release-version
	@git commit -a -m "Bump version to $$(cat .release-version)"

release: version build
	@docker tag ${LATEST} ${NAME}:$$(cat .release-version)
	@docker tag ${LATEST} ${RELEASE}
	@docker push ${LATEST}
	@docker push ${RELEASE}
	@docker push ${NAME}:$$(cat .release-version)
	@rm .release-version
