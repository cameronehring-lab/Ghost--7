SHELL := /bin/bash

.PHONY: setup up down restart logs ps health rebuild clean recovery-watch recovery-status recovery-stop recovery-install recovery-uninstall expert-guide

setup:
	bash scripts/setup_dev.sh

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f backend

ps:
	docker compose ps

health:
	bash scripts/healthcheck.sh

rebuild:
	docker compose up -d --build

clean:
	docker compose down -v

recovery-watch:
	python3 scripts/docker_recovery_watchdog.py watch --interval-seconds 20

recovery-status:
	python3 scripts/docker_recovery_watchdog.py status

recovery-stop:
	python3 scripts/docker_recovery_watchdog.py stop

recovery-install:
	bash scripts/install_docker_recovery_watchdog.sh install

recovery-uninstall:
	bash scripts/install_docker_recovery_watchdog.sh uninstall

expert-guide:
	python3 scripts/omega_expert_tool.py
