.PHONY: all docs README project_proposal clean

SPHINX = sphinx-build
SPHINX_SOURCE_DIR = docs/src
SPHINX_BUILD_DIR  = docs/build


all: docs

docs: README project_proposal

README:
	SPHINX_BUILD=README $(SPHINX) -b html $(SPHINX_SOURCE_DIR) $(SPHINX_BUILD_DIR)/README

project_proposal:
	SPHINX_BUILD=project_proposal $(SPHINX) -b revealjs $(SPHINX_SOURCE_DIR) $(SPHINX_BUILD_DIR)/project_proposal

clean:
	rm -rf $(SPHINX_BUILD_DIR)
