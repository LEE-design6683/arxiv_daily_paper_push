# ArXiv EMRI Daily Digest

每日抓取指定 arXiv 分类的 `new` 列表，用关键词筛选 EMRI/IMRI 相关论文，调用 DeepSeek 生成中文解释，并通过 SMTP 发送邮件。

## 功能

- 按分类抓取 `https://arxiv.org/list/<category>/new`
- 基于 EMRI 关键词本地筛选（标题/主题/注释）
- 逐篇抓取原始摘要 + DeepSeek 结构化中文解读
- 可选 PapersWithCode 代码链接
- SMTP 邮件推送（QQ/163/Gmail 等）
- 无结果时可发送空日报通知
- HTTP 重试与退避（429/5xx）

## 环境变量

- `DEEPSEEK_API_KEY`：必填
- `DEEPSEEK_API_URL`：默认 `https://api.deepseek.com/v1/chat/completions`
- `DEEPSEEK_MODEL`：默认 `deepseek-chat`
- `SMTP_HOST`：如 `smtp.qq.com`
- `SMTP_PORT`：如 `465`
- `SMTP_USER`：邮箱账号
- `SMTP_PASS`：邮箱 SMTP 授权码
- `SMTP_USE_SSL`：`true/false`
- `FROM_EMAIL`：发件人邮箱
- `TO_EMAIL`：收件人邮箱
- `ARXIV_NEW_CATEGORIES`：默认 `astro-ph,gr-qc,hep-th,hep-ph,math-ph`
- `SEND_EMPTY_DIGEST`：默认 `true`
- `MAX_DEEPSEEK_PAPERS`：默认 `20`，每日最多生成解释的论文数

## 本地运行

```bash
pip install -r requirements.txt
python daily_paper.py
```

## GitHub Actions

仓库已包含工作流：`.github/workflows/daily_emri_email.yml`。

在仓库 `Settings -> Secrets and variables -> Actions` 中配置同名 Secrets 后即可定时运行。
