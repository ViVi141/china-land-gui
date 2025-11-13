"""Markdown 导出与文本处理工具。"""

from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from typing import Iterable

BASE_DATA_URL = "http://szb.iziran.net/dataFile"


def normalise_whitespace(value: str) -> str:
    text = clean_html(value)
    return re.sub(r"\n{3,}", "\n\n", text)


def clean_html(text: Optional[str]) -> str:
    if not text:
        return ""
    value = text
    replacements = {
        "<br>": "\n",
        "<br/>": "\n",
        "<br />": "\n",
    }
    for key, val in replacements.items():
        value = value.replace(key, val)
    value = re.sub(r"</p\s*>", "\n\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<p\b[^>]*>", "", value, flags=re.IGNORECASE)
    value = re.sub(r"<li\b[^>]*>", "- ", value, flags=re.IGNORECASE)
    value = re.sub(r"</li\s*>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<(script|style)\b.*?>.*?</\1>", "", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<img\b[^>]*>", "", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("<%basePath%>", "")
    value = re.sub(r"/batch/[\w\-/\.%]+", "", value)
    value = re.sub(r"images/[\w\-/\.%]+", "", value)
    value = value.replace('">', "")
    value = unescape(value)
    lines = [line.strip(" \t\u3000") for line in value.splitlines()]
    cleaned_lines = []
    for line in lines:
        if not line:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def extract_images(html: str | None) -> list[dict[str, str]]:
    if not html:
        return []
    images: List[Dict[str, str]] = []
    for match in re.finditer(r'<img\b[^>]*src=["\']([^"\']+)["\'][^>]*>', html, flags=re.IGNORECASE):
        src = match.group(1)
        src = src.replace("<%basePath%>", BASE_DATA_URL)
        alt_match = re.search(r'alt=["\']([^"\']*)["\']', match.group(0), flags=re.IGNORECASE)
        alt_text = unescape(alt_match.group(1)) if alt_match else ""
        images.append({"url": src.strip(), "alt": alt_text.strip()})
    return images


def render_article(article: dict[str, any]) -> str:
    index_raw = article.get("index")
    try:
        index_str = f"{int(index_raw):03d}"
    except (TypeError, ValueError):
        index_str = str(index_raw)
    title = normalise_whitespace(article.get("titleHtml") or article.get("title") or "")
    author = normalise_whitespace(article.get("authorHtml") or article.get("author") or "")
    column = normalise_whitespace(article.get("column") or "")
    page_number = article.get("pageNumber")
    body_html = article.get("html") or ""
    body_text = normalise_whitespace(body_html)
    if not body_text:
        body_text = normalise_whitespace(article.get("text") or "")
    lines: List[str] = []
    lines.append(f"## {index_str} {title}")
    meta_lines = []
    if column:
        meta_lines.append(f"栏目：{column}")
    if author:
        meta_lines.append(f"作者：{author}")
    if page_number:
        meta_lines.append(f"页码：{page_number}")
    if meta_lines:
        for meta in meta_lines:
            lines.append(f"- {meta}")
        lines.append("")
    images = extract_images(article.get("html"))
    if images:
        for idx, image in enumerate(images, start=1):
            caption = image["alt"] or f"图片{idx}"
            lines.append(f"![{caption}]({image['url']})")
        lines.append("")
    lines.append(body_text)
    return "\n".join(lines).strip()


def write_issue_markdown(
    magazine_meta: dict[str, any],
    articles: list[dict[str, any]],
    output_dir: Path,
    prefix: str,
    fallback_name: str | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    year = magazine_meta.get("year") or ""
    page_name = magazine_meta.get("pageName") or ""
    date = magazine_meta.get("date") or ""
    full_title = normalise_whitespace(magazine_meta.get("title") or "")
    header_title = full_title or f"{prefix}{year}{page_name}"
    safe_page = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff\-（）()第期年月日]", "_", page_name)
    identifier = fallback_name or magazine_meta.get("id") or "magazine"
    filename = f"{year}_{safe_page or identifier}.md"
    output_path = output_dir / filename
    lines: List[str] = []
    lines.append(f"# {header_title.strip()}")
    if date:
        lines.append("")
        lines.append(f"- 出版日期：{date}")
    for article in articles:
        lines.append("")
        lines.append(render_article(article))
        lines.append("")
        lines.append("---")
    if lines and lines[-1] == "---":
        lines.pop()
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return output_path


def generate_markdown(input_path: Path, output_dir: Path, prefix: str) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    magazines: dict[str, dict[str, any]] = {}
    articles_by_mag: dict[str, list[dict[str, any]]] = {}
    with input_path.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            record = json.loads(line)
            magazine = record["magazine"]
            magazine_id = magazine["id"]
            if magazine_id not in magazines:
                magazines[magazine_id] = {
                    "id": magazine_id,
                    "year": record.get("year"),
                    "pageName": magazine.get("pageName"),
                    "date": magazine.get("date"),
                    "title": magazine.get("title") or magazine.get("subject") or "",
                }
            articles_by_mag.setdefault(magazine_id, []).append(record["article"])
    output_files: list[Path] = []
    for magazine_id, meta in magazines.items():
        articles = sorted(articles_by_mag.get(magazine_id, []), key=lambda x: x.get("index") or 0)
        output_files.append(write_issue_markdown(meta, articles, output_dir, prefix))
    return output_files

