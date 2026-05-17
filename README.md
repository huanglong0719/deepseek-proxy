# DeepSeek Protocol Converter

将 OpenAI Responses API 协议转换为 DeepSeek Chat API 协议的代理服务器。

支持 [Codex](https://github.com/openai/codex) 等使用 OpenAI Responses API 的工具通过 DeepSeek 模型运行。

## 功能

- 🔄 **协议转换**：OpenAI Responses API → DeepSeek Chat API
- 📡 **流式响应**：完整支持 SSE 流式输出
- 🔧 **工具调用**：自动转换 function calling 格式
- 🛠️ **工具过滤**：自动过滤非 function 类型工具（custom、namespace 等）
- 💬 **消息合并**：智能合并连续 assistant 消息，符合 DeepSeek API 要求
- ⚙️ **配置灵活**：支持环境变量和命令行参数

## 安装

```bash
# 克隆仓库
git clone https://github.com/<your-username>/deepseek-proxy.git
cd deepseek-proxy

# 安装依赖（仅需要 Python 3.8+）
pip install -r requirements.txt
```

## 使用

### 1. 设置环境变量

```bash
# Windows (PowerShell)
$env:DEEPSEEK_API_KEY = "your-deepseek-api-key"

# Linux / macOS
export DEEPSEEK_API_KEY="your-deepseek-api-key"
```

### 2. 启动代理服务器

```bash
python deepseek_proxy.py
```

默认监听 `http://127.0.0.1:8765`

### 3. 配置客户端

将客户端的 API 地址设置为：
- Base URL: `http://127.0.0.1:8765`
- API Key: `any-value`（代理会忽略）

## 配置 Codex 使用 DeepSeek

在 Codex 设置中：

```json
{
  "api_base": "http://127.0.0.1:8765/v1",
  "model": "deepseek-v4-flash"
}
```

## 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--host` | `127.0.0.1` | 监听地址 |
| `--port` | `8765` | 监听端口 |
| `--model` | `deepseek-v4-flash` | 默认模型 |

## 支持的模型

- `deepseek-v4-flash` - 推荐，快速且经济
- `deepseek-chat` - DeepSeek V3
- `deepseek-reasoner` - 推理模型

## 技术细节

### 协议转换映射

| OpenAI Responses API | DeepSeek Chat API |
|---------------------|-------------------|
| `/v1/responses` | `/v1/chat/completions` |
| `input[]` 数组 | `messages[]` 数组 |
| `function_call` output item | `tool_calls` in message |
| `function_call_output` input item | `role: tool` message |
| `response.output_text.delta` SSE | `choices[0].delta.content` SSE |

### 已知限制

1. 非 `function` 类型的工具会被自动过滤（DeepSeek 不支持）
2. 多轮工具调用的上下文长度会累积增长
3. 流式响应中的 reasoning content 可能不完整显示

## License

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
