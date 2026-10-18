# printer-care - dev and deploy helpers.
#   make test                     shellcheck (if installed) + tests/run.sh
#   make install HOST=printer     install onto an ssh host (needs sudo there)
#   make uninstall HOST=printer   remove binary + units (keeps config and state)
#
# Bash: the script and tests run on bash >= 3.2 (macOS /bin/bash included). Tests use
# whichever `bash` is first on PATH; override with `make test BASH=/bin/bash`.
BASH ?= bash
HOST ?=
BIN  := /usr/local/bin/printer-care
CONF := /etc/printer-care.conf
UNIT := /etc/systemd/system

.PHONY: test lint install uninstall

lint:
	@if command -v shellcheck >/dev/null 2>&1; then shellcheck -x printer-care tests/run.sh && echo "shellcheck ok"; \
	else echo "shellcheck not installed - skipped"; fi

test: lint
	$(BASH) tests/run.sh

# Files are copied to a private temp dir on the target and installed with `install`
# (never executed from there: /tmp is often mounted noexec).
install:
	@test -n "$(HOST)" || { echo "usage: make install HOST=<sshhost>"; exit 1; }
	@d=$$(ssh $(HOST) mktemp -d) && \
	scp -q printer-care printer-care.conf.example systemd/printer-care.service systemd/printer-care.timer $(HOST):$$d/ && \
	ssh $(HOST) "set -e; cd $$d; \
	  sudo install -m 755 printer-care $(BIN); \
	  if [ -e $(CONF) ]; then echo 'keeping existing $(CONF)'; else sudo install -m 600 printer-care.conf.example $(CONF); echo 'installed example $(CONF) - edit it'; fi; \
	  sudo install -m 644 printer-care.service printer-care.timer $(UNIT)/; \
	  sudo systemctl daemon-reload; sudo systemctl enable --now printer-care.timer; \
	  cd /; rm -rf $$d; systemctl list-timers printer-care.timer --no-pager"

uninstall:
	@test -n "$(HOST)" || { echo "usage: make uninstall HOST=<sshhost>"; exit 1; }
	ssh $(HOST) "sudo systemctl disable --now printer-care.timer; \
	  sudo rm -f $(BIN) $(UNIT)/printer-care.service $(UNIT)/printer-care.timer; sudo systemctl daemon-reload; \
	  echo 'left in place: $(CONF) and /var/lib/printer-care'"
