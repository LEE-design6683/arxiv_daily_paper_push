# 📚 ArXiv 每日论文推送助手

自动抓取 ArXiv 最新 AI 论文，使用 DeepSeek 进行深度分析，并推送到飞书。

## ✨ 功能特性

- 🔍 **自动抓取**：每日自动获取 ArXiv 最新 LLM / AI Agent / Deep Learning 相关论文
- 🤖 **AI 深度分析**：调用 DeepSeek API 生成结构化中文解读：
  - 【快速抓要点】核心问题与方法
  - 【逻辑推导】起承转合还原作者思路
  - 【技术细节】关键实现细节
  - 【局限性】潜在不足
  - 【专业知识解释】术语科普
- 💻 **代码链接**：自动从 PapersWithCode 匹配开源代码
- 📱 **飞书推送**：生成精美富文本卡片推送至飞书群

## 🚀 快速开始

### 方式一：GitHub Actions 自动运行（推荐）

使用 GitHub Actions 可以免费、全自动地每天运行推送，无需本地机器长期开机。

#### 1. Fork 或克隆本仓库到你的 GitHub 账户

#### 2. 配置 GitHub Secrets（安全存储密钥）

> ⚠️ **绝对不要**将 API Key 或 Webhook 直接写入代码并提交到仓库！

进入仓库页面 → **Settings** → **Secrets and variables** → **Actions** → 点击 **New repository secret**，依次添加以下三个 Secret：

| Secret 名称 | 说明 |
|---|---|
| `FEISHU_WEBHOOK` | 飞书机器人 Webhook 完整地址 |
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `DEEPSEEK_API_URL` | DeepSeek API 地址（如 `https://api.deepseek.com/v1/chat/completions`）|

#### 3. 启用 GitHub Actions

进入仓库 → **Actions** 标签页 → 点击 **Enable workflows**（如果提示的话）。

Workflow 默认在每天北京时间 **09:00** 自动运行。也可以在 Actions 页面点击 **Run workflow** 手动触发。

#### 4. 查看运行日志

Actions → 选择对应的 workflow run → 查看输出日志，确认是否推送成功。

---

### 方式二：本地手动运行 / Windows 任务计划程序

#### 1. 环境准备

```bash
pip install arxiv requests
```

#### 2. 配置（本地运行）

可以通过环境变量设置，避免密钥明文出现在代码中：

```bash
# Windows (PowerShell)
$env:FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/你的Webhook地址"
$env:DEEPSEEK_API_KEY="你的DeepSeek API Key"
$env:DEEPSEEK_API_URL="https://api.deepseek.com/v1/chat/completions"
python daily_paper.py
```

或直接编辑 `daily_paper.py` 中的默认值（**不要提交到公开仓库**）。

- 飞书 Webhook：在飞书群设置 → 添加机器人 → 自定义机器人 → 获取 Webhook 地址
- DeepSeek API Key：在 DeepSeek 开放平台 获取

#### 3. 设置每日自动运行（Windows 任务计划程序）

1. 搜索打开「任务计划程序」
2. 点击右侧「创建基本任务」
3. 名称：ArXiv每日论文推送
4. 触发器：选择「每天」，设置运行时间（如 09:00）
5. 操作：选择「启动程序」
6. 程序或脚本：`C:\Users\你的用户名\Desktop\run_arxiv.bat`（或实际路径）
7. 起始于（可选）：`C:\Users\你的用户名\Desktop`
8. 完成：勾选「当单击"完成"时，打开此任务属性的对话框」
9. 高级设置（可选）：
   「条件」→ 取消勾选「只有在计算机使用交流电源时才启动」
   「设置」→ 勾选「如果任务失败，按以下频率重新启动」

### 注意事项

- 确保网络可访问 ArXiv、DeepSeek API 和飞书服务器
- 建议先手动运行测试，确认配置无误后再设置定时任务
- 如需修改论文查询关键词，编辑 `daily_paper.py` 中的 `query` 参数
- **不要将 API Key、Webhook 等敏感信息提交到公开仓库**，请使用 GitHub Secrets 或环境变量管理
