# 🧪 周报"注水"净化器

> 零代码 AI Web 应用 —— 从流水账到价值叙事的自动化转化。
> 运营人 2 小时的周报，30 秒搞定。

## ✨ 核心功能

| 功能 | 说明 |
|---|---|
| 碎碎念结构化 | 接收零散工作记录（含语音转文字口水话），AI 自动按 **用户增长 / 留存 / 转化 / 内容** 四大维度归类 |
| 价值升华引擎 | 将「发了5篇推文，改了3次标题」升华为「通过A/B测试标题策略，预估提升点击率约10%-20%」，输出 **原始描述 → 价值叙事** 对照视图，推断数据基于行业公认基准并以"约/预估"标注 |
| 下周计划补全 | 自动识别未完成事项，生成含 **预期目标 + 关键动作** 的可编辑计划草稿 |
| 一键导出 | 支持导出 **Markdown**（.md 文件下载）与 **PDF**（浏览器打印面板另存） |
| 访客自带密钥 | 点击页面右上角 **「密钥设置」**，可填写魔搭 **API Key / 模型名（可选）/ Base URL（可选）** 三项（均仅保存在本地浏览器 localStorage，不上传/不存储到服务端）。带 **「连接自检」** 按钮，一键验证密钥能否真实调用大模型；带 **「清除」** 一键清空三项。即使空间没配环境变量，也能真实使用大模型 |

## 📁 文件结构

```
├── app.py            # 后端 API 与 AI 逻辑（FastAPI，监听 7860 端口）
├── index.html        # 前端页面（纯原生 HTML/CSS/JS，零外部依赖）
├── requirements.txt  # 依赖清单
├── Dockerfile        # 魔搭创空间 Docker 部署镜像构建（python:3.10-slim，监听 7860）
├── .dockerignore     # Docker 构建时排除无关文件（__pycache__/.git 等）
└── README.md         # 本文件
```

## 🚀 部署到魔搭创空间（ModelScope Studio）

### 1. 创建创空间

1. 登录 [魔搭社区](https://www.modelscope.cn/)，进入「创空间」→「创建创空间」；
2. **SDK 类型必须选择 `Docker`（容器）**。⚠️ **不要选 Gradio**：本应用是 FastAPI 自建 Web 服务（非 Gradio 应用），选 Gradio 后创空间会探测 `/config` 等 Gradio 专属路由导致 `404 Not Found` 部署失败。
   - 仓库根目录已提供 `Dockerfile`，构建时自动安装依赖并监听创空间约定的 `7860` 端口：
     ```dockerfile
     FROM python:3.10-slim
     WORKDIR /app
     COPY requirements.txt .
     RUN pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
     COPY . .
     EXPOSE 7860
     CMD ["python", "app.py"]
     ```
3. 将 `app.py`、`index.html`、`requirements.txt`、`README.md` 上传到创空间代码仓库。

### 2. 配置环境变量（启用大模型能力）

在创空间「设置 → 环境变量」中添加：

| 变量名 | 说明 |
|---|---|
| `MODELSCOPE_API_KEY` | 魔搭访问令牌（[获取地址](https://www.modelscope.cn/my/myaccesstoken)），用于免费调用魔搭 API-Inference |
| `MODEL_ID`（可选） | 默认 `Qwen/Qwen3-30B-A3B-Instruct-2507`，可换为其他支持 API-Inference 的模型 |

> 💡 **未配置 API Key 也能用**，有两条路径：
> 1. **访客自带密钥**：访问者点击页面右上角「密钥设置」，填入自己的魔搭 API Key（仅存于其本地浏览器 localStorage，不上传服务端，请求时透传给魔搭官方接口）。密钥优先级：访客密钥 > 空间环境变量。
> 2. **规则引擎兜底**：完全没有密钥时使用本地规则引擎，分类 / 升华 / 计划功能全部可用，仅话术精细度略低。AI 调用失败（超时/限频/无效密钥）也会自动降级并在页面提示原因，服务永不白屏。

### 3. 启动

创空间构建完成后自动运行 `python app.py`，访问空间地址即可使用。

## 💻 本地运行

```bash
pip install -r requirements.txt
# 可选：启用大模型
export MODELSCOPE_API_KEY=你的魔搭访问令牌
python app.py
# 浏览器打开 http://localhost:7860
```

## 🔌 API 说明

| 接口 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 前端页面 |
| `/api/health` | GET | 健康检查，返回 AI 启用状态 |
| `/api/purify` | POST | 核心净化接口，Body: `{"text": "...", "api_key": "...", "model": "...", "base_url": "..."}`（后三项可选，访客自带） |
| `/api/check` | POST | 连接自检，Body: `{"api_key": "...", "model": "...", "base_url": "..."}`，返回 `{"ok": true/false, "model": "...", "error": "..."}` |

`/api/purify` 返回结构：

```json
{
  "mode": "ai | rule",
  "key_source": "visitor | server",
  "summary": "一句话周报总结",
  "items": [
    {"category": "内容", "raw": "原始描述", "refined": "价值叙事"}
  ],
  "next_week": [
    {"task": "任务名", "goal": "预期目标", "actions": ["关键动作1", "关键动作2"]}
  ]
}
```

## ⚠️ 使用提醒

价值升华中的数据推断基于行业公开基准（如公众号打开率 3%-5%、标题 A/B 测试提升 10%-20% 等），均以「约 / 预估」标注。请在提交周报前核对，确保叙事与事实相符。
