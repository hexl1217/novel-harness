SHELL := /bin/bash
.PHONY: install test lint run build clean check-draft help

DRAFT ?=

help:
	@echo "novel-harness 开发命令"
	@echo "  make install    安装 RAG 依赖"
	@echo "  make test       运行所有测试"
	@echo "  make test-rag   仅 RAG 测试"
	@echo "  make test-agent 仅 Agent 引擎测试"
	@echo "  make check-draft 正文机器预检 (DRAFT=projects/项目/正文/第N章.md)"
	@echo "  make lint       pyflakes + pycodestyle 检查"
	@echo "  make run        启动 RAG HTTP 服务 (localhost:3456)"
	@echo "  make build      构建 Docker 镜像"
	@echo "  make clean      清理缓存文件"

install:
	pip install --upgrade pip
	pip install -r rag/requirements.txt
	@echo "依赖安装完成"

test:
	python -m pytest rag/test/ agent_core/test/ -v --tb=short

test-rag:
	python -m pytest rag/test/ -v --tb=short

test-agent:
	python -m pytest agent_core/test/ -v --tb=short

check-draft:
	@test -n "$(DRAFT)" || (echo "用法：make check-draft DRAFT=projects/项目/正文/第N章.md"; exit 2)
	python -m agent_core.check_draft $(DRAFT)

lint:
	@echo "=== pyflakes ==="
	@python -m pyflakes rag/src/ agent_core/ 2>&1 || true
	@echo "=== pycodestyle ==="
	@python -m pycodestyle rag/src/ agent_core/ --max-line-length=120 --ignore=E402,W503 2>&1 || true
	@echo "=== Python syntax ==="
	@python -c "import ast, os; errors=[os.path.join(r,f) for r,_,fs in os.walk('.') for f in fs if f.endswith('.py') and '.git' not in r for error in [ast.parse(open(os.path.join(r,f)).read())] if False] or print('OK')"

run:
	python rag/scripts/query.py --server

build:
	docker compose build

up:
	docker compose up -d

clean:
	find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '.pytest_cache' -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	@echo "清理完成"
