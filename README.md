# DeepSeek Codex Proxy

让 Codex 桌面版通过代理使用 DeepSeek API 的解决方案，同时支持 DeepSeek 官方 API 的图片识别功能。

## 架构概览

```
用户/客户端
    │
    ▼
deepseek-proxy (端口 8765)  ← 本项目
    │
    ├── 无图片请求 ──────────→ DeepSeek 官方 API
    │
    └── 有图片请求 ──────────→ ds2api-browser (端口 8766)  ← 子模块
                                │
                                └── Chrome 浏览器自动化
                                    └── 登录 DeepSeek 网页 → 识图模式
                                    └── 捕获 SSE 响应 → 分离思考/回复内容
```

### 核心组件

| 组件 | 仓库 | 说明 |
|------|------|------|
| **deepseek-proxy** | 本仓库 | Python 协议转换代理，负责路由分发和响应转换 |
| **ds2api-browser** | [huanglong0719/ds2api-browser](https://github.com/huanglong0719/ds2api-browser) | Go + chromedp 浏览器自动化，处理图片识别 |

### 图片识别流程

1. 客户端发送请求到 `deepseek-proxy`（`/v1/responses`）
2. 检测**最后一条用户消息**是否包含图片（多轮对话中历史图片不触发）
3. 有图片 → 转发给 `ds2api-browser`
4. `ds2api-browser` 通过 Chrome 操控 DeepSeek 网页版执行识图
5. 捕获 SSE 响应，通过 `fragments[].type` 元数据分离思考内容和回复内容
6. `deepseek-proxy` 将结果转为 SSE 流式响应返回客户端

## 功能特性

- **零配置启动**：双击即可启动代理，无需手动修改 Codex 配置文件
- **自动配置注入**：启动时自动修改 Codex 配置，切到 DeepSeek 模型
- **自动配置还原**：关闭代理时自动恢复原始配置，不影响 Codex 原有设置
- **异常保护**：即使通过 X 按钮强制关闭，下次启动时也会自动还原残留配置
- **跨电脑迁移**：自动检测当前用户名，复制到新电脑可直接使用
- **智能图片路由**：只检测最后一条用户消息，避免历史图片污染后续纯文本请求
- **思考/回复分离**：通过解析 DeepSeek SSE 的 fragment type 标记，正确分离 thinking 和 content

## 系统要求

- Windows 操作系统
- Python 3.x（需要能运行 `python` 或 `py` 命令）
- Chrome 浏览器（用于 ds2api-browser 图片识别）
- DeepSeek 网页版账号（用于 ds2api-browser 登录）
- Git（用于版本管理，如需推送到 GitHub）
- OpenAI Codex 桌面版

## 快速开始

### 1. 克隆本仓库

```bash
git clone https://github.com/huanglong0719/deepseek-proxy.git
cd deepseek-proxy
```

### 2. 克隆子模块（ds2api-browser）

```bash
git submodule update --init --recursive
```

### 3. 配置并启动 ds2api-browser

```bash
cd vendor/ds2api-browser
cp browser_config.example.json browser_config.json
# 编辑 browser_config.json，填入 DeepSeek 账号信息
go build -o ds2api-browser.exe .
./ds2api-browser.exe
```

### 4. 启动 deepseek-proxy

```bash
python deepseek_proxy.py
```

服务启动后监听 `http://127.0.0.1:8765`。

## API 示例

### 图片识别（通过 ds2api-browser）

```bash
curl http://127.0.0.1:8765/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-v4-pro",
    "input": [{
      "role": "user",
      "content": [
        {"type": "input_text", "text": "这张图片里有什么？"},
        {"type": "input_image", "image_url": "data:image/png;base64,..."}
      ]
    }]
  }'
```

响应包含 SSE 流式事件，`reasoning` 事件携带思考内容，`output_text` 事件携带回复内容。

### 纯文本聊天（直连 DeepSeek API）

```bash
curl http://127.0.0.1:8765/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-chat",
    "input": [{"role": "user", "content": [{"type": "input_text", "text": "你好"}]}]
  }'
```

## 文件说明

```
deepseek-proxy/
├── deepseek_proxy.py              # 代理核心模块
├── README.md                      # 本说明文档
└── vendor/
    └── ds2api-browser/            # Git 子模块：浏览器图片识别服务
        ├── main.go
        ├── api/handler.go
        ├── browser/
        │   ├── chat.go            # 图片聊天核心逻辑
        │   ├── injector.go        # SSE 拦截器（思考/回复分离）
        │   └── session.go         # 浏览器会话管理
        ├── config/config.go
        └── browser_config.example.json
```

## 关联项目

- **[ds2api-browser](https://github.com/huanglong0719/ds2api-browser)** - Chrome 浏览器自动化图片识别服务（作为 git submodule 集成）
- **[ds2api](https://github.com/huanglong0719/ds2api)** - 主项目，完整的 DeepSeek API 代理服务
