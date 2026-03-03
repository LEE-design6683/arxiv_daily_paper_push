import json
import os
import smtplib
import re
from html import escape
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def getenv_nonempty(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = getenv_nonempty("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
DEEPSEEK_MODEL = getenv_nonempty("DEEPSEEK_MODEL", "deepseek-chat")

SMTP_HOST = getenv_nonempty("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(getenv_nonempty("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "")
TO_EMAIL = os.getenv("TO_EMAIL", "")
SMTP_USE_SSL = getenv_nonempty("SMTP_USE_SSL", "true").lower() == "true"

# Example: "astro-ph,gr-qc,hep-th,hep-ph,math-ph"
ARXIV_NEW_CATEGORIES = getenv_nonempty("ARXIV_NEW_CATEGORIES", "astro-ph,gr-qc,hep-th,hep-ph,math-ph")
SEND_EMPTY_DIGEST = getenv_nonempty("SEND_EMPTY_DIGEST", "true").lower() == "true"
MAX_DEEPSEEK_PAPERS = int(getenv_nonempty("MAX_DEEPSEEK_PAPERS", "20"))
MAX_DEEPSEEK_CONCURRENCY = int(getenv_nonempty("MAX_DEEPSEEK_CONCURRENCY", "5"))
USE_ANNOUNCEMENT_WINDOW = getenv_nonempty("USE_ANNOUNCEMENT_WINDOW", "true").lower() == "true"
ANNOUNCEMENT_WINDOWS_BACK = int(getenv_nonempty("ANNOUNCEMENT_WINDOWS_BACK", "2"))
STRICT_EMRI_ONLY = getenv_nonempty("STRICT_EMRI_ONLY", "true").lower() == "true"

PWC_BASE_URL = "https://arxiv.paperswithcode.com/api/v0/papers/"
BASE_ARXIV_URL = "https://arxiv.org"
ET_TZ = ZoneInfo("America/New_York")

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
CORE_EMRI_TERMS = {
    "emri",
    "imri",
    "extreme mass ratio inspiral",
    "mass-ratio inspiral",
    "extreme mass-ratio inspiral",
}
DETECTOR_TERMS = {"lisa", "taiji", "tianqin", "millihertz", "mhz"}
DYNAMICS_TERMS = {
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
}
COMPACT_OBJECT_TERMS = {"black hole", "kerr", "mass ratio", "inspiral"}
LVK_NOISE_TERMS = {"lvk", "ligo", "virgo", "kagra", "binary neutron star", "bbh", "bns"}
HIGHLIGHT_EXCLUDE_KEYWORDS = {"ak", "flux"}


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


HTTP_SESSION = make_session()


def parse_categories() -> List[str]:
    return [c.strip() for c in ARXIV_NEW_CATEGORIES.split(",") if c.strip()]


def extract_arxiv_id(arxiv_url: str) -> str:
    tail = arxiv_url.rstrip("/").split("/")[-1]
    return tail.split("v")[0]


def get_code_link(arxiv_url: str):
    arxiv_id = extract_arxiv_id(arxiv_url)
    try:
        resp = HTTP_SESSION.get(f"{PWC_BASE_URL}{arxiv_id}", timeout=10)
        resp.raise_for_status()
        r = resp.json()
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
    resp = HTTP_SESSION.get(url, timeout=30)
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
    resp = HTTP_SESSION.get(abs_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    block = soup.find("blockquote", class_="abstract")
    if not block:
        return ""
    text = block.get_text(" ", strip=True)
    return text.replace("Abstract:", "", 1).strip()


def fetch_abstract_and_updated(abs_url: str) -> tuple[str, Optional[datetime]]:
    resp = HTTP_SESSION.get(abs_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    abstract = ""
    block = soup.find("blockquote", class_="abstract")
    if block:
        abstract = block.get_text(" ", strip=True).replace("Abstract:", "", 1).strip()

    updated_at = None
    hist = soup.find("div", class_="submission-history")
    if hist:
        text = hist.get_text(" ", strip=True)
        matches = re.findall(r"\[v\d+\]\s*([^()]+?UTC)", text)
        if matches:
            try:
                updated_at = datetime.strptime(matches[-1].strip(), "%a, %d %b %Y %H:%M:%S %Z").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                updated_at = None
    return normalize_abstract_text(abstract), updated_at


def normalize_abstract_text(text: str) -> str:
    """Make arXiv abstract text more readable in email clients."""
    if not text:
        return ""
    out = text
    out = out.replace("\n", " ")
    out = re.sub(r"\$([^$]+)\$", r"\1", out)
    out = re.sub(r"\\text\{([^}]*)\}", r"\1", out)
    out = re.sub(r"\\mathrm\{([^}]*)\}", r"\1", out)
    out = re.sub(r"\\mathbf\{([^}]*)\}", r"\1", out)
    out = re.sub(r"\\[a-zA-Z]+\b", "", out)
    out = out.replace("{", "").replace("}", "")
    return " ".join(out.split())


def filter_emri_papers(entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
    unique = {}
    for p in entries:
        text = " ".join([p.get("title", ""), p.get("subjects", ""), p.get("comments", "")])
        if is_emri_related(text) and p["id"] not in unique:
            unique[p["id"]] = p
    return list(unique.values())


def is_strict_emri_related(text: str) -> bool:
    norm = normalize_text(text)
    has_core = any(t in norm for t in CORE_EMRI_TERMS)
    if STRICT_EMRI_ONLY:
        return has_core
    if has_core:
        return True
    has_detector = any(t in norm for t in DETECTOR_TERMS)
    has_dynamics = any(t in norm for t in DYNAMICS_TERMS)
    has_compact = any(t in norm for t in COMPACT_OBJECT_TERMS)
    has_lvk_noise = any(t in norm for t in LVK_NOISE_TERMS)

    # Detector-only papers (LISA/Taiji/TianQin) must explicitly mention EMRI/IMRI.
    if has_detector:
        return False

    # Keep dynamics/compact-related candidates, but suppress obvious LVK/LIGO/Virgo/KAGRA noise.
    if (has_dynamics or has_compact) and not has_lvk_noise:
        return True
    return False


def strict_filter_emri_papers(entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
    kept = []
    for p in entries:
        text = " ".join(
            [
                p.get("title", ""),
                p.get("subjects", ""),
                p.get("comments", ""),
                p.get("summary", ""),
            ]
        )
        if is_strict_emri_related(text):
            kept.append(p)
    return kept


def _latest_announcement_time_et(now_et: datetime) -> datetime:
    at_20 = now_et.replace(hour=20, minute=0, second=0, microsecond=0)
    if now_et >= at_20:
        latest = at_20
    else:
        latest = at_20 - timedelta(days=1)
    while latest.weekday() >= 5:
        latest -= timedelta(days=1)
    return latest


def announcement_window_utc(now_utc: Optional[datetime] = None) -> tuple[datetime, datetime]:
    now_utc = now_utc or datetime.now(timezone.utc)
    now_et = now_utc.astimezone(ET_TZ)
    end_et = _latest_announcement_time_et(now_et)

    start_et = end_et - timedelta(days=1)
    while start_et.weekday() >= 5:
        start_et -= timedelta(days=1)
    return start_et.astimezone(timezone.utc), end_et.astimezone(timezone.utc)


def announcement_windows_utc(now_utc: Optional[datetime] = None, back_windows: int = 1) -> List[tuple[datetime, datetime]]:
    now_utc = now_utc or datetime.now(timezone.utc)
    windows = []
    end_now = now_utc
    for _ in range(max(1, back_windows)):
        start_utc, end_utc = announcement_window_utc(end_now)
        windows.append((start_utc, end_utc))
        end_now = start_utc - timedelta(seconds=1)
    return windows


def filter_by_announcement_window(
    results: List[Dict[str, str]], now_utc: Optional[datetime] = None, back_windows: int = 1
) -> List[Dict[str, str]]:
    windows = announcement_windows_utc(now_utc, back_windows=back_windows)
    kept = []
    for p in results:
        updated_at = p.get("updated_at")
        if not updated_at:
            kept.append(p)
            continue
        if any(start_utc < updated_at <= end_utc for start_utc, end_utc in windows):
            kept.append(p)
    return kept


def summarize_with_deepseek(paper):
    prompt_text = f"""你是一个学术分析专家。请根据以下论文的标题和摘要提供中文深度分析。
    论文标题: {paper['title']}
    论文摘要: {paper['summary']}

    要求：
    1）必须使用中文输出；
    2）避免输出 LaTeX 公式源码，公式请转为文字解释；
    3）不要输出英文小标题。

    请严格按此格式输出（每段都要有内容）：
    【摘要翻译】: （把论文摘要翻译成准确、通顺的中文）
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
        response = HTTP_SESSION.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=90)
        response.raise_for_status()
        res_json = response.json()
        if "error" in res_json:
            return f"DeepSeek API 报错: {res_json['error'].get('message', res_json['error'])}"
        if "choices" not in res_json:
            return f"API 未预期响应: {json.dumps(res_json, ensure_ascii=False)}"
        content = res_json["choices"][0]["message"].get("content", "").strip()
        if not content:
            return "DeepSeek 返回空内容。"
        return content
    except Exception as e:
        return f"网络或系统错误: {str(e)}"


def find_matched_keywords(paper: Dict[str, str], summary: str) -> Dict[str, List[str]]:
    fields = {
        "title": normalize_text(paper.get("title", "")),
        "subjects": normalize_text(paper.get("subjects", "")),
        "comments": normalize_text(paper.get("comments", "")),
        "abstract": normalize_text(summary),
    }
    matched = {k: [] for k in fields}
    for kw in EMRI_KEYWORDS:
        k = normalize_text(kw)
        for field_name, field_value in fields.items():
            if k and k in field_value:
                matched[field_name].append(kw)
    return matched


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def highlight_keywords_html(text: str, keywords: List[str]) -> str:
    safe = escape(text)
    sorted_keywords = sorted(
        _dedupe_keep_order(
            [k for k in keywords if k and normalize_text(k) not in HIGHLIGHT_EXCLUDE_KEYWORDS]
        ),
        key=len,
        reverse=True,
    )
    for kw in sorted_keywords:
        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        safe = pattern.sub(lambda m: f"<mark style='background:#fff3a3'>{escape(m.group(0))}</mark>", safe)
    return safe


def render_deepseek_html(raw_text: str) -> str:
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return "<p style='color:#b00020'><b>DeepSeek 解释缺失：</b>返回为空。</p>"
    if "DeepSeek API 报错" in raw_text or "网络或系统错误" in raw_text or "API 未预期响应" in raw_text:
        return f"<p style='color:#b00020'><b>DeepSeek 解释失败：</b>{escape(raw_text)}</p>"

    matches = list(re.finditer(r"【([^】]+)】[:：]?", raw_text))
    if not matches:
        return f"<p>{escape(raw_text).replace(chr(10), '<br>')}</p>"

    blocks = []
    for idx, m in enumerate(matches):
        title = escape(m.group(1))
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw_text)
        body = raw_text[start:end].strip()
        body_html = escape(body).replace("\n", "<br>")
        blocks.append(f"<p><b>{title}</b><br>{body_html}</p>")
    return "".join(blocks)


def build_report_html(results):
    def process_one(idx_paper):
        idx, p = idx_paper
        summary, updated_at = fetch_abstract_and_updated(p["entry_id"])
        p["summary"] = summary
        p["updated_at"] = updated_at
        code_url = get_code_link(p["entry_id"])
        deepseek_raw = summarize_with_deepseek({"title": p["title"], "summary": summary})
        matched_map = find_matched_keywords(p, summary)
        return idx, p, code_url, deepseek_raw, matched_map

    sections = []
    total = min(len(results), MAX_DEEPSEEK_PAPERS)
    subset = list(enumerate(results[:MAX_DEEPSEEK_PAPERS], start=1))
    rendered = {}
    with ThreadPoolExecutor(max_workers=MAX_DEEPSEEK_CONCURRENCY) as pool:
        futures = [pool.submit(process_one, item) for item in subset]
        for fut in as_completed(futures):
            i, p, code_url, deepseek_raw, matched_map = fut.result()
            print(f"正在分析第 {i}/{total} 篇: {p['title']}")
            code_html = f' | <a href="{code_url}">💻 代码</a>' if code_url else ""
            summary = p.get("summary", "")
            keyword_union = _dedupe_keep_order(
                matched_map["title"] + matched_map["subjects"] + matched_map["comments"] + matched_map["abstract"]
            )
            keyword_display = [k for k in keyword_union if normalize_text(k) not in HIGHLIGHT_EXCLUDE_KEYWORDS]
            highlighted_title = highlight_keywords_html(p["title"], keyword_union)
            highlighted_summary = highlight_keywords_html(summary, keyword_union)
            deepseek_html = render_deepseek_html(deepseek_raw)
            rendered[i] = (
                p,
                code_html,
                deepseek_html,
                highlighted_summary,
                highlighted_title,
                matched_map,
                keyword_display,
            )

    for i in range(1, total + 1):
        p, code_html, deepseek_html, highlighted_summary, highlighted_title, matched_map, keyword_union = rendered[i]
        keyword_chips = " ".join(
            [f"<span style='background:#e8f0ff;padding:2px 6px;border-radius:10px'>{escape(k)}</span>" for k in keyword_union]
        )
        where_hits = []
        if matched_map["title"]:
            where_hits.append("标题")
        if matched_map["subjects"]:
            where_hits.append("分类")
        if matched_map["comments"]:
            where_hits.append("注释")
        if matched_map["abstract"]:
            where_hits.append("摘要")
        where_text = "、".join(where_hits) if where_hits else "未定位"
        section = (
            f"<h3>{i}. {highlighted_title}</h3>"
            f"<p>分类: {escape(p.get('category',''))} | 作者: {escape(p.get('authors',''))}</p>"
            f"<p>🔗 <a href=\"{p['entry_id']}\">原文</a>{code_html}</p>"
            f"<p><b>命中关键词:</b> {keyword_chips or '无'}</p>"
            f"<p><b>命中位置:</b> {escape(where_text)}</p>"
            f"<details><summary>关键词命中片段（英文原文）</summary><p>{highlighted_summary}</p></details>"
            f"{deepseek_html}<hr>"
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

    # Fetch abstract/update time before announcement-window filtering.
    for p in emri_results:
        if "summary" not in p or "updated_at" not in p:
            summary, updated_at = fetch_abstract_and_updated(p["entry_id"])
            p["summary"] = summary
            p["updated_at"] = updated_at

    emri_results = strict_filter_emri_papers(emri_results)

    if USE_ANNOUNCEMENT_WINDOW:
        emri_results = filter_by_announcement_window(emri_results, back_windows=ANNOUNCEMENT_WINDOWS_BACK)

    if not emri_results:
        print("今日 new 列表中未检索到 EMRI 相关新论文。")
        if SEND_EMPTY_DIGEST:
            subject = f"ArXiv EMRI Daily Digest {datetime.now().strftime('%Y-%m-%d')}"
            body = "<p>今日所选分类的 arXiv new 列表中未检索到 EMRI 相关新论文。</p>"
            send_email_smtp(subject, body)
            print("已发送空结果通知邮件。")
        return

    report_html = build_report_html(emri_results)
    if len(emri_results) > MAX_DEEPSEEK_PAPERS:
        report_html += (
            f"<p>注：命中 {len(emri_results)} 篇，仅对前 {MAX_DEEPSEEK_PAPERS} 篇生成详细解释。"
            "其余论文可在后续版本按需扩展。</p>"
        )
    subject = f"ArXiv EMRI Daily Digest {datetime.now().strftime('%Y-%m-%d')}"
    send_email_smtp(subject, report_html)
    print(f"推送成功，共发送 {len(emri_results)} 篇。")


if __name__ == "__main__":
    main()
