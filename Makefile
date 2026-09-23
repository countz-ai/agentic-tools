# Package plugins for upload to Claude Cowork.
# Install: Cowork -> Customize -> Plugins -> upload -> dist/<name>-<version>.zip

PLUGINS := $(patsubst %/.claude-plugin/,%,$(wildcard */.claude-plugin/))
PLUGIN  ?= $(PLUGINS)
DIST    := dist

# Cowork plugin package limits.
MAX_FILES := 5000
MAX_BYTES := 209715200

.DEFAULT_GOAL := help
.PHONY: help validate check zip clean ci smoke-dso smoke-dso-room smoke-dso-validate

help:
	@echo "make validate [PLUGIN=<name>]  claude plugin validate (the manifest)"
	@echo "make check    [PLUGIN=<name>]  structural checks validate does not make"
	@echo "make zip      [PLUGIN=<name>]  validate + check, then package into $(DIST)/"
	@echo "              [RECIPES=\"a.md b.md\"]  also bundle these recipes; the run uses them, not the connector's"
	@echo "make clean                     remove $(DIST)/"
	@echo "make smoke-dso                 LIVE PAID DISPATCH: full DSO run on a synthetic room, then validate"
	@echo "make smoke-dso-room            generate + verify the synthetic room only"
	@echo "make smoke-dso-validate RUN=<dir>  re-validate a finished smoke run"
	@echo
	@echo "plugins: $(PLUGINS)"

validate:
	@for p in $(PLUGIN); do claude plugin validate ./$$p || exit 1; done

# Frontmatter keys the loader would drop silently, a fork with no agent, an agent nothing
# declares, a goal name leaking into the goal-agnostic skills, a cap default copied out of
# goal.json, a pipeline referencing a skill or need that does not exist, a hook that is not
# executable. None of these is visible to `claude plugin validate`, and each one fails at
# run time rather than at package time.
check:
	@python3 check-plugin.py $(PLUGIN)

# `playbook-recipes/` is authored here and served by the Countz connector
# (docs/arch/AUTH_MCP_OAUTH.md § 6.1); it never ships in the package. check-plugin.py
# refuses a zip recipe (check 8u) so the exclusion cannot rot silently.
# RECIPES="<file.md> ..." is the one exception, by hand: each file is validated and staged
# into the zip as `<plugin>/bundled-recipes/<frontmatter name>.md`, never into the source
# tree, and a run of that recipe pins the bundled copy instead of fetching it
# (scripts/bundled_recipe.py, PLAYBOOK_RECIPES.md § 2).
zip: validate check
	@mkdir -p $(DIST)
	@for p in $(PLUGIN); do \
		n=$$(find $$p -type f ! -name .DS_Store ! -path '*/__pycache__/*' ! -path '*/.venv/*' ! -path '*/playbook-recipes/*' | wc -l | tr -d ' '); \
		b=$$(find $$p -type f ! -name .DS_Store ! -path '*/__pycache__/*' ! -path '*/.venv/*' ! -path '*/playbook-recipes/*' -exec cat {} + | wc -c | tr -d ' '); \
		if [ $$n -gt $(MAX_FILES) ]; then echo "$$p: $$n files exceeds Cowork limit $(MAX_FILES)" >&2; exit 1; fi; \
		if [ $$b -gt $(MAX_BYTES) ]; then echo "$$p: $$b bytes uncompressed exceeds Cowork limit $(MAX_BYTES)" >&2; exit 1; fi; \
		v=$$(python3 -c "import json;print(json.load(open('$$p/.claude-plugin/plugin.json')).get('version','0.0.0'))"); \
		out=$(DIST)/$$p-$$v.zip; \
		rm -f $$out; \
		zip -qr $$out $$p -x '*.DS_Store' '*/__pycache__/*' '*.pyc' '*/.venv/*' '*/playbook-recipes/*'; \
		echo "$$out  ($$n files, $$b bytes uncompressed)"; \
		if [ -n "$(RECIPES)" ]; then \
			stage=$(DIST)/.stage; rm -rf $$stage; mkdir -p $$stage/$$p/bundled-recipes; \
			for r in $(RECIPES); do \
				python3 $$p/scripts/validate_recipe.py $$r || { rm -f $$out; exit 1; }; \
				rn=$$(python3 -c "import sys;sys.path.insert(0,'$$p/scripts');import bundled_recipe as b;print(b.frontmatter_name(open('$$r').read()) or '')"); \
				if [ -z "$$rn" ]; then echo "$$r: no frontmatter name" >&2; rm -f $$out; exit 1; fi; \
				cp $$r $$stage/$$p/bundled-recipes/$$rn.md; \
				echo "  bundled recipe $$rn  <- $$r"; \
			done; \
			(cd $$stage && zip -qr $(abspath $(DIST))/$$(basename $$out) $$p); \
			rm -rf $$stage; \
		fi; \
	done

# `make -C models ci` fans out to this. Packaging is deliberately NOT part of it: `zip`
# writes into dist/ and needs the `zip` binary, neither of which belongs in a check run.
ci: check

# The full smoke dispatches a real agent through the whole pipeline - long and paid.
# Room and results are gitignored (data_rooms/, results/).
smoke-dso:
	@bash smoke/run_smoke.sh

smoke-dso-room:
	@uv run --with openpyxl python smoke/gen_room.py data_rooms/smoke_dso

smoke-dso-validate:
	@test -n "$(RUN)" || { echo "usage: make smoke-dso-validate RUN=<run_dir>" >&2; exit 2; }
	@python3 smoke/validate_run.py "$(RUN)"

clean:
	@rm -rf $(DIST)
