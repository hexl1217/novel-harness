SHELL := /bin/bash
.PHONY: install test test-rag test-agent lint run build clean check-draft verify verify-full benchmark baseline help

DRAFT ?=

help:
	@echo "novel-harness 开发命令"
	@echo "  make install    安装 RAG 依赖"
	@echo "  make test       运行所有测试"
	@echo "  make test-rag   仅 RAG 测试"
	@echo "  make test-agent 仅 Agent 引擎测试"
	@echo "  make check-draft 正文机器预检 (DRAFT=projects/项目/正文/第N章.md)"
	@echo "  make verify     RAG 端到端验收（复用现有索引，需 remote 知识包）"
	@echo "  make verify-full 端到端验收（先重建索引）"
	@echo "  make benchmark  检索基准测试（Recall@5 + 延迟）"
	@echo "  make baseline   重新记录检索质量基线"
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
	find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev
ull || true
	find . -type d -name '.pytest_cache' -exec rm -rf {} + 2>/dev
ull || true
	find . -type f -name '*.pyc' -delete
	@echo "清理完成"

# 以下三个目标依赖 .harness/knowledge/remote/ 知识包，而该目录被 .gitignore
# 排除（远程包属本地产物），因此无法在 CI 运行，只能本地执行。

verify:
	@test -d .harness/knowledge/remote || (echo "缺少 .harness/knowledge/remote/ 知识包：先运行 python rag/scripts/sync_packs.py"; exit 2)
	python rag/test/verify.py --no-build

verify-full:
	python rag/test/verify.py

benchmark:
	python rag/test/benchmark.py

baseline:
	python rag/test/benchmark.py --save-baseline rag/test/baseline.json
	@echo "基线已更新，记得连同本次改动一起提交"
