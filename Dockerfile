# ModelTrace MCP 服务镜像（stdio 传输，供 Codex 等 MCP 客户端以
# `docker run -i --rm <image>` 方式拉起）。
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-mcp.txt ./
RUN pip install --no-cache-dir -r requirements-mcp.txt

# MCP 服务入口与归因核心（fingerprint/enrollment 及其依赖模块）
# v6 起 fingerprint/enrollment 依赖 v6_portable，bank_builder 依赖 v6_builder，缺一即启动失败
COPY mcp_server.py fingerprint.py enrollment.py bank_builder.py challenge_suite.py v6_portable.py v6_builder.py ./
# 指纹库与参考数据
COPY data/ ./data/

# stdio 模式不需要监听端口。
ENTRYPOINT ["python", "mcp_server.py"]
