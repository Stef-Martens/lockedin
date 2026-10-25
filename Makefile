PY := .venv/bin/python

.PHONY: install dev test samples owner db-up

install:
	python3 -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -e '.[dev]'
	npm --prefix web install

db-up:
	supabase status >/dev/null 2>&1 || supabase start -x realtime,storage-api,imgproxy,edge-runtime,logflare,vector,supavisor

dev:
	./scripts/dev.sh

test: db-up
	$(PY) -m pytest

samples:
	$(PY) scripts/make_samples.py

owner:
	@test -n "$(EMAIL)" -a -n "$(PASSWORD)" || (echo "usage: make owner EMAIL=you@example.com PASSWORD=..." && exit 1)
	$(PY) scripts/create_owner.py --email "$(EMAIL)" --password "$(PASSWORD)"
