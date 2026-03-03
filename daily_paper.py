import json
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List

import requests
from bs4 import BeautifulSoup


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

# Example: "astro-ph,gr-qc,hep-th,hep-ph,math-ph"
ARXIV_NEW_CATEGORIES = os.getenv("ARXIV_NEW_CATEGORIES", "astro-ph,gr-qc,hep-th,hep-ph,math-ph")
SEND_EMPTY_DIGEST = os.getenv("SEND_EMPTY_DIGEST", "true").lower() == "true"

PWC_BASE_URL = "https://arxiv.paperswithcode.com/api/v0/papers/"
BASE_ARXIV_URL = "https://arxiv.org"

EMRI_KEYWORDS = [
    "emri",
    "imri",
    "extreme mass ratio inspiral",
    "mass-ratio inspiral",
    "extreme mass-ratio inspiral",
    "lisa",
    "taiji",
    "tianqin",
    "millihertz",
    "mhz",
    "self-force",
    "second-order self-force",
    "adiabatic",
    "two-timescale",
    "teukolsky",
    "kerr geodesic",
    "osculating",
    "flux",
    "aak",
    "ak",
    "kludge",
    "analytic kludge",
    "loss cone",
    "relaxation",
    "resonant relaxation",
    "schwarzschild barrier",
    "nuclear star cluster",
    "cusp",
    "bahcall-wolf",
    "mass segregation",
]


def parse_categories() -> List[str]:
    return [c.strip() for c in ARXIV_NEW_CATEGORIES.split(",") if c.strip()]


def extract_arxiv_id(arxiv_url: str) -> str:
    tail = arxiv_url.rstrip("/").split("/")[-1]
    return tail.split("v")[0]


def get_code_link(arxiv_url: str):
    arxiv_id = extract_arxiv_id(arxiv_url)
    try:
        r = requests.get(f"{PWC_BASE_URL}{arxiv_id}", timeout=10).json()
        if "official" in r and r["official"]:
            return r["official"].get("url")
    except Exception:
        pass
    return None


def normalize_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def is_emri_related(text: str) -> bool:
    norm = normalize_text(text)
    return any(k in norm for k in EMRI_KEYWORDS)


def fetch_new_listings(category: str) -> List[Dict[str, str]]:
    url = f"{BASE_ARXIV_URL}/list/{category}/new"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    entries = []
    dl = soup.find("dl")
    if not dl:
        return entries

    dts = dl.find_all("dt")
    dds = dl.find_all("dd")
    for dt, dd in zip(dts, dds):
        abs_link = dt.find("a", title="Abstract")
        if not abs_link:
            continue

        abs_path = abs_link.get("href", "")
        abs_url = f"{BASE_ARXIV_URL}{abs_path}" if abs_path.startswith("/") else abs_path
        paper_id = extract_arxiv_id(abs_url)

        title_div = dd.find("div", class_="list-title")
        authors_div = dd.find("div", class_="list-authors")
        subjects_div = dd.find("div", class_="list-subjects")
        comments_div = dd.find("div", class_="list-comments")

        title = title_div.get_text(" ", strip=True).replace("Title:", "").strip() if title_div else ""
        authors = authors_div.get_text(" ", strip=True).replace("Authors:", "").strip() if authors_div else ""
        subjects = subjects_div.get_text(" ", strip=True).replace("Subjects:", "").strip() if subjects_div else ""
        comments = comments_div.get_text(" ", strip=True).replace("Comments:", "").strip() if comments_div else ""

        entries.append(
            {
                "id": paper_id,
                "entry_id": abs_url,
                "title": title,
                "authors": authors,
                "subjects": subjects,
                "comments": comments,
                "category": category,
            }
        )

    return entries


def fetch_abstract(abs_url: str) -> str:
    resp = requests.get(abs_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    block = soup.find("blockquote", class_="abstract")
    if not block:
        return ""
    text = block.get_text(" ", strip=True)
    return text.replace("Abstract:", "", 1).strip()


def filter_emri_papers(entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
    unique = {}
    for p in entries:
        text = " ".join([p.get("title", ""), p.get("subjects", ""), p.get("comments", "")])
        if is_emri_related(text) and p["id"] not in unique:
            unique[p["id"]] = p
    return list(unique.values())


def summarize_with_deepseek(paper):
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


def build_report_html(results):
    sections = []
    for i, p in enumerate(results, start=1):
        print(f"正在分析第 {i}/{len(results)} 篇: {p['title']}")

        summary = p.get("summary", "")
        if not summary:
            summary = fetch_abstract(p["entry_id"])
            p["summary"] = summary

        code_url = get_code_link(p["entry_id"])
        code_html = f' | <a href="{code_url}">💻 代码</a>' if code_url else ""

        deepseek_text = summarize_with_deepseek({"title": p["title"], "summary": summary}).replace("\n", "<br>")

        section = (
            f"<h3>{i}. {p['title']}</h3>"
            f"<p>分类: {p.get('category','')} | 作者: {p.get('authors','')}</p>"
            f"<p>🔗 <a href=\"{p['entry_id']}\">原文</a>{code_html}</p>"
            f"<p><b>原始摘要:</b> {summary}</p>"
            f"<p>{deepseek_text}</p><hr>"
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

    print("正在抓取各分类 arXiv/new 并筛选 EMRI...")
    all_entries = []
    for cat in parse_categories():
        try:
            entries = fetch_new_listings(cat)
            print(f"分类 {cat} 抓取 {len(entries)} 篇")
            all_entries.extend(entries)
        except Exception as e:
            print(f"分类 {cat} 抓取失败: {e}")

    emri_results = filter_emri_papers(all_entries)

    if not emri_results:
        print("今日 new 列表中未检索到 EMRI 相关新论文。")
        if SEND_EMPTY_DIGEST:
            subject = f"ArXiv EMRI Daily Digest {datetime.now().strftime('%Y-%m-%d')}"
            body = "<p>今日所选分类的 arXiv new 列表中未检索到 EMRI 相关新论文。</p>"
            send_email_smtp(subject, body)
            print("已发送空结果通知邮件。")
        return

    report_html = build_report_html(emri_results)
    subject = f"ArXiv EMRI Daily Digest {datetime.now().strftime('%Y-%m-%d')}"
    send_email_smtp(subject, report_html)
    print(f"推送成功，共发送 {len(emri_results)} 篇。")


if __name__ == "__main__":
    main()
