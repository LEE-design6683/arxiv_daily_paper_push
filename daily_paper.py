import json
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import arxiv
import requests


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "")
TO_EMAIL = os.getenv("TO_EMAIL", "")
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "true").lower() == "true"

MAX_RESULTS = int(os.getenv("MAX_RESULTS", "200"))
PWC_BASE_URL = "https://arxiv.paperswithcode.com/api/v0/papers/"


def build_arxiv_query() -> str:
    return (
        'ti:EMRI OR abs:EMRI OR '
        'ti:"extreme mass ratio inspiral" OR abs:"extreme mass ratio inspiral" OR '
        'ti:"extreme-mass-ratio inspiral" OR abs:"extreme-mass-ratio inspiral"'
    )


def extract_arxiv_id(arxiv_url: str) -> str:
    tail = arxiv_url.split("/")[-1]
    return tail.split("v")[0]


def get_code_link(arxiv_url: str):
    """从 PapersWithCode 获取代码链接"""
    arxiv_id = extract_arxiv_id(arxiv_url)
    try:
        r = requests.get(f"{PWC_BASE_URL}{arxiv_id}", timeout=10).json()
        if "official" in r and r["official"]:
            return r["official"]["url"]
    except Exception:
        pass
    return None


def summarize_with_deepseek(paper):
    """使用 DeepSeek 进行论文摘要深度总结"""
    prompt_text = f"""你是一个学术分析专家。请根据以下论文的标题和摘要提供中文深度分析。
    论文标题: {paper['title']}
    论文摘要: {paper['summary']}

    请严格按此格式输出：
    【快速抓要点】: （简练的语言说明该研究解决了什么问题？提出了什么新的方法？得出了什么结果结论？）
    【逻辑推导】：（按“背景-破局-拆解”讲解作者思路，并给出1/2/3步骤）
    【技术细节】: （补充最关键的1-2个技术实现细节）
    【局限性】: （潜在不足）
    【专业知识解释】: （解释核心名词概念）
    """

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个学术分析专家，擅长将复杂论文总结得清晰易懂。"},
            {"role": "user", "content": prompt_text},
        ],
        "stream": False,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }

    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=90)
        res_json = response.json()

        if "error" in res_json:
            return f"DeepSeek API 报错: {res_json['error'].get('message', res_json['error'])}"

        if "choices" not in res_json:
            return f"API 未预期响应: {json.dumps(res_json, ensure_ascii=False)}"

        return res_json["choices"][0]["message"]["content"]
    except Exception as e:
        return f"网络或系统错误: {str(e)}"


def filter_today_and_deduplicate(results, now=None):
    """只保留今天提交的论文，并按 arXiv id 去重。"""
    now = now or datetime.now(timezone.utc)
    today = now.date()

    unique = {}
    for res in results:
        published_date = res.published.astimezone(timezone.utc).date()
        if published_date != today:
            continue
        paper_id = extract_arxiv_id(res.entry_id)
        if paper_id not in unique:
            unique[paper_id] = res

    return list(unique.values())


def build_report_html(results):
    sections = []
    for i, res in enumerate(results, start=1):
        print(f"正在分析第 {i}/{len(results)} 篇: {res.title}")

        code_url = get_code_link(res.entry_id)
        code_html = f' | <a href="{code_url}">💻 代码</a>' if code_url else ""

        paper_info = {
            "title": res.title,
            "summary": res.summary.replace("\n", " "),
            "url": res.entry_id,
        }

        summary = summarize_with_deepseek(paper_info).replace("\n", "<br>")
        section = (
            f"<h3>{i}. {res.title}</h3>"
            f"<p>🔗 <a href=\"{res.entry_id}\">原文</a>{code_html}</p>"
            f"<p>{summary}</p><hr>"
        )
        sections.append(section)

    return "\n".join(sections)


def send_email_smtp(subject: str, html_content: str):
    if not all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, FROM_EMAIL, TO_EMAIL]):
        raise RuntimeError("SMTP/邮箱配置不完整")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = TO_EMAIL
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    if SMTP_USE_SSL:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, [TO_EMAIL], msg.as_string())
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, [TO_EMAIL], msg.as_string())


def main():
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("未设置 DEEPSEEK_API_KEY")

    print("正在搜集 EMRI 最新论文...")
    client = arxiv.Client()
    search = arxiv.Search(
        query=build_arxiv_query(),
        max_results=MAX_RESULTS,
        sort_by=arxiv.SortCriterion.SubmittedDate,
    )

    raw_results = list(client.results(search))
    results = filter_today_and_deduplicate(raw_results)

    if not results:
        print("今日暂无 EMRI 新论文。")
        return

    report_html = build_report_html(results)
    subject = f"ArXiv EMRI Daily Digest {datetime.now().strftime('%Y-%m-%d')}"
    send_email_smtp(subject, report_html)
    print(f"推送成功，共发送 {len(results)} 篇。")


if __name__ == "__main__":
    main()
