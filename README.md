# ModelTrace

ModelTrace 是一个本地运行的主动模型归因工具。它通过三条独立的长整数生成挑战提取多视角输出指纹，在统一候选库中自动判断模型家族和具体版本，并对未收录的库外模型自动拒绝归因。

## 运行

### Python 后端版

```powershell
python -m pip install -r requirements.txt
python start.py
```

页面地址为 `http://127.0.0.1:7860/`。

### 纯静态浏览器本地版（GitHub Pages）

`static/index.html` 是不依赖后端的手动测试版本，特征提取、归因计算和指纹库读取都在浏览器本地完成：

```powershell
python -m http.server 8080 -d static
```

## MCP 服务（本 fork 新增）

本 fork 在上游基础上增加了 MCP（Model Context Protocol）服务 `mcp_server.py`，以 Docker 承载、stdio 传输，供 Codex 等 MCP 客户端直接调用。镜像由 GitHub Actions 自动构建并发布到 GitHub Packages：

```text
ghcr.io/fairyliuying/modeltrace:latest
```

> 首次发布后，如需公开拉取，请在 GitHub 仓库的 Packages 设置中把该容器包的可见性改为 Public（或将其与本仓库关联并继承仓库可见性）。

### 工具一览

| 工具 | 作用 |
| --- | --- |
| `get_challenges` | 生成 3 条归因挑战题，供会话内主代理亲自作答 |
| `attribute_outputs` | 对 1~3 份挑战回答做指纹归因，返回家族与具体模型概率 |
| `fingerprint_model` | 给定 Base URL / API Key / 模型名，自动调用 API 完成探测与归因 |
| `list_bank_models` | 查看内置统一指纹库收录的家族与模型 |

### 在 Codex 中安装

在 Codex 的 `~/.codex/config.toml` 中加入：

```toml
[mcp_servers.modeltrace]
command = "docker"
args = ["run", "-i", "--rm", "ghcr.io/fairyliuying/modeltrace:latest"]
```

重启 Codex 后即可调用。例如直接对它说：

> 用 modeltrace 的 get_challenges 给我 3 道挑战题，你亲自逐题作答（不要调用任何工具生成数字），然后把你的答案提交给 attribute_outputs，告诉我检测结果。

这种用法不需要任何 API Key——作答的就是当前会话主代理本人，测的正是它所使用的模型指纹。

如需让 `fingerprint_model` 免参数调用（自动探测某个 API 端点），在配置中传入环境变量，容器启动时读取：

```toml
[mcp_servers.modeltrace]
command = "docker"
args = ["run", "-i", "--rm",
        "-e", "MODELTRACE_BASE_URL",
        "-e", "MODELTRACE_API_KEY",
        "-e", "MODELTRACE_MODEL",
        "ghcr.io/fairyliuying/modeltrace:latest"]
env = { MODELTRACE_BASE_URL = "https://api.example.com/v1", MODELTRACE_API_KEY = "sk-...", MODELTRACE_MODEL = "your-model-name" }
```

### 本地运行（不经 Codex）

```bash
python -m pip install -r requirements-mcp.txt
python mcp_server.py   # stdio 模式，等待 MCP 客户端连接
```

或用 Docker 本地构建：

```bash
docker build -t modeltrace-mcp .
docker run -i --rm modeltrace-mcp
```

## 使用

- **手动测试**：复制三条挑战，分别发送给同一个待测模型，再粘贴每次完整输出。
- **API 自动测试**：填写 Base URL、API Key、模型名及并发数（默认 `3`）。程序会自动尝试 OpenAI Chat Completions 与 Anthropic Messages 格式，以三份有效回答为目标并发完成归因。
- **指纹库管理**：可以新建指纹库，或通过 API 为现有指纹库添加模型指纹。

API Key 只用于当前页面发起请求，不写入磁盘。

## 指纹库覆盖范围（2 大家族 · 22 个模型）

```text
gpt-5.4
gpt-5.5
gpt-5.6-sol
gpt-5.6-terra
gpt-5.6-luna
gpt-6-astra
gpt-6-sol
gpt-6-luna
gpt-6.1-sol
gpt-6.1-terra
gpt-6.2-astra
gpt-6.2-sol
claude-haiku-4-5-20251001
claude-haiku-5-5
claude-sonnet-4-6
claude-sonnet-5
claude-sonnet-5-5
claude-opus-4-6
claude-opus-4-7
claude-opus-4-8
claude-opus-5
claude-opus-5-5
```

GPT 采集自官方订阅 Codex，Claude 采集自 [OAIPro](https://api.oaipro.com/)。

## 项目结构

```text
app.py                  Web 接口
v6_portable.py          双精度多视角特征提取与开集归因推理引擎
v6_builder.py           指纹库训练、校准与紧凑量化构建器
fingerprint.py          指纹归因入口与挑战生成
bank_builder.py         单库构建入口
challenge_suite.py      自动建库挑战套件
enrollment.py           API 调用与指纹采集
rebuild_unified_bank.py 重建统一全局库
data/                   参考数据与指纹库
static/                 纯静态页面与浏览器本地推理核心 (fingerprint-core.js)
templates/              页面模板
```

## 声明

测试结果仅供参考，并非判断模型的决定性证据。

若待测模型不在指纹库中或置信度不足，系统将拒绝归因。`gpt-6.1-sol` 与 `gpt-6-astra` 的输出分布非常接近，两者之间的分辨结果可能不准确（在高推理强度下尤为明显），请谨慎参考。Claude Code 的系统提示词会影响模型偏好，测试结果存在较大偏差，建议不要在 Claude Code 中测试。

## 致谢

感谢 [hanlinwenyuan/hlwy-ai-checker](https://github.com/hanlinwenyuan/hlwy-ai-checker)。该项目较早将语言模型的随机数字生成偏差用于第三方 API 渠道一致性检查，为 ModelTrace 提供了重要参考。

[LINUX DO](https://linux.do/)
