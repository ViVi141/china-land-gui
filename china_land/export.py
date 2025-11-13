"""Markdown 导出与文本处理工具。"""

from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import defaultdict

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


def extract_images(html: str | None) -> list[Dict[str, str]]:
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


def render_article(article: Dict[str, Any]) -> str:
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
    magazine_meta: Dict[str, Any],
    articles: List[Dict[str, Any]],
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


def write_article_separately(
    article: Dict[str, Any],
    magazine_meta: Dict[str, Any],
    output_dir: Path,
    prefix: str,
) -> Path:
    year = magazine_meta.get("year", "")
    page_name = magazine_meta.get("pageName", "")
    index_raw = article.get("index")
    try:
        index_str = f"{int(index_raw):03d}"
    except (TypeError, ValueError):
        index_str = str(index_raw)
    title = normalise_whitespace(article.get("title") or "")
    safe_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff\-（）()第期年月日 ]", "_", f"{year}_{page_name}_{index_str}_{title}".strip())
    filename = f"{prefix}_{safe_name}.md"
    output_path = output_dir / filename
    content = render_article(article)
    output_path.write_text(content + "\n", encoding="utf-8")
    return output_path


def write_issue_articles_separately(
    magazine_meta: Dict[str, Any],
    articles: List[Dict[str, Any]],
    output_dir: Path,
    prefix: str,
) -> List[Path]:
    paths = []
    for article in articles:
        article["magazine_meta"] = magazine_meta  # For consistency, though used in call
        paths.append(write_article_separately(article, magazine_meta, output_dir, prefix))
    return paths


def write_year_markdown(
    year: str,
    magazines: List[Dict[str, Any]],
    all_articles: List[Dict[str, Any]],
    output_dir: Path,
    prefix: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    lines: List[str] = [f"# {prefix} {year} 全年文章"]
    # Group articles by magazine
    articles_by_mag: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for article in all_articles:
        mag_id = article.get("magazine_id")
        if mag_id:
            articles_by_mag[mag_id].append(article)
    for mag in sorted(magazines, key=lambda m: m.get("date", "")):
        mag_lines = [f"\n## {normalise_whitespace(mag.get('title') or '')} ({mag.get('date', '')})"]
        mag_articles = sorted(articles_by_mag.get(mag["id"], []), key=lambda x: x.get("index") or 0)
        for article in mag_articles:
            mag_lines.append(render_article(article))
            mag_lines.append("---")
        if mag_lines and mag_lines[-1] == "---":
            mag_lines.pop()
        lines.extend(mag_lines)
    safe_year = re.sub(r"[^0-9A-Za-z]", "_", year)
    filename = f"{prefix}_{safe_year}_full.md"
    output_path = output_dir / filename
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return output_path


def write_all_markdown(
    years: List[str],
    year_magazines: List[tuple[str, List[Dict[str, Any]]]],
    all_articles: List[Dict[str, Any]],
    output_dir: Path,
    prefix: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    lines: List[str] = [f"# {prefix} 全量文章"]
    # Group by year then magazine
    articles_by_year_mag: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for article in all_articles:
        year = article.get("year")
        mag_id = article.get("magazine_id")
        if year and mag_id:
            articles_by_year_mag[year][mag_id].append(article)
    for year in years:
        year_lines = [f"\n# {year} 年"]
        mags = [m for y, ms in year_magazines if y == year for m in ms]
        for mag in sorted(mags, key=lambda m: m.get("date", "")):
            mag_lines = [f"\n## {normalise_whitespace(mag.get('title') or '')} ({mag.get('date', '')})"]
            mag_articles = sorted(articles_by_year_mag[year].get(mag["id"], []), key=lambda x: x.get("index") or 0)
            for article in mag_articles:
                mag_lines.append(render_article(article))
                mag_lines.append("---")
            if mag_lines and mag_lines[-1] == "---":
                mag_lines.pop()
            year_lines.extend(mag_lines)
        lines.extend(year_lines)
    filename = f"{prefix}_all_full.md"
    output_path = output_dir / filename
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return output_path


def generate_markdown(input_path: Path, output_dir: Path, prefix: str) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    magazines: Dict[str, Dict[str, Any]] = {}
    articles_by_mag: Dict[str, List[Dict[str, Any]]] = {}
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
    output_files: List[Path] = []
    for magazine_id, meta in magazines.items():
        articles = sorted(articles_by_mag.get(magazine_id, []), key=lambda x: x.get("index") or 0)
        output_files.append(write_issue_markdown(meta, articles, output_dir, prefix))
    return output_files

