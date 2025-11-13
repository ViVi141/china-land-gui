"""GUI 窗口入口。"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from collections import defaultdict
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from .client import ChinaLandCrawler
from .export import extract_images, normalise_whitespace, render_article, write_issue_markdown


class ChinaLandGUI(tk.Tk):
    """主界面。"""

    def __init__(self) -> None:
        super().__init__()
        self.title("中国土地期刊爬虫")
        self.resizable(False, False)

        self.crawler: ChinaLandCrawler | None = None
        self.current_year: str | None = None
        self.current_magazine_id: str | None = None
        self.magazines_by_year: dict[str, list[dict[str, any]]] = defaultdict(list)
        self.articles_by_mag: dict[str, list[dict[str, any]]] = defaultdict(list)
        self.article_details: dict[str, dict[str, any]] = {}

        self._build_widgets()

    def _build_widgets(self) -> None:
        padding = {"padx": 10, "pady": 5}

        frame_controls = tk.Frame(self)
        frame_controls.pack(fill=tk.X, **padding)
        tk.Button(frame_controls, text="登录 / 刷新", command=self.login_and_load).pack(side=tk.LEFT)
        tk.Label(frame_controls, text="  请求间隔（秒）：").pack(side=tk.LEFT)
        self.delay_var = tk.DoubleVar(value=1.5)
        tk.Entry(frame_controls, width=5, textvariable=self.delay_var).pack(side=tk.LEFT)

        frame_select = tk.Frame(self)
        frame_select.pack(fill=tk.X, **padding)
        tk.Label(frame_select, text="年份：").pack(side=tk.LEFT)
        self.year_var = tk.StringVar()
        self.year_combo = ttk.Combobox(frame_select, width=10, textvariable=self.year_var, state="disabled")
        self.year_combo.pack(side=tk.LEFT, padx=5)
        self.year_combo.bind("<<ComboboxSelected>>", self.on_year_selected)

        tk.Label(frame_select, text="期刊：").pack(side=tk.LEFT)
        self.issue_var = tk.StringVar()
        self.issue_combo = ttk.Combobox(frame_select, width=25, textvariable=self.issue_var, state="disabled")
        self.issue_combo.pack(side=tk.LEFT, padx=5)
        self.issue_combo.bind("<<ComboboxSelected>>", self.on_issue_selected)

        frame_list = tk.Frame(self)
        frame_list.pack(fill=tk.BOTH, expand=True, **padding)
        tk.Label(frame_list, text="文章列表：").pack(anchor=tk.W)
        self.article_list = tk.Listbox(frame_list, width=60, height=12, exportselection=False)
        self.article_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.article_list.bind("<<ListboxSelect>>", self.on_article_selected)
        scrollbar = tk.Scrollbar(frame_list, orient=tk.VERTICAL, command=self.article_list.yview)
        scrollbar.pack(side=tk.LEFT, fill=tk.Y)
        self.article_list.configure(yscrollcommand=scrollbar.set)

        frame_view = tk.Frame(self)
        frame_view.pack(fill=tk.BOTH, expand=True, **padding)
        tk.Label(frame_view, text="文章内容：").pack(anchor=tk.W)
        self.content_widget = scrolledtext.ScrolledText(frame_view, width=80, height=20, state=tk.DISABLED)
        self.content_widget.pack(fill=tk.BOTH, expand=True)

        frame_actions = tk.Frame(self)
        frame_actions.pack(fill=tk.X, **padding)
        tk.Button(frame_actions, text="导出所选文章", command=self.export_selected_article).pack(side=tk.LEFT)
        tk.Button(frame_actions, text="导出所选期刊", command=self.export_selected_issue).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_actions, text="导出所选年份", command=self.export_selected_year).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_actions, text="全量导出", command=self.export_all).pack(side=tk.LEFT)

        frame_prefix = tk.Frame(self)
        frame_prefix.pack(fill=tk.X, **padding)
        tk.Label(frame_prefix, text="导出文件前缀：").pack(side=tk.LEFT)
        self.prefix_var = tk.StringVar(value="中国土地")
        tk.Entry(frame_prefix, width=20, textvariable=self.prefix_var).pack(side=tk.LEFT, padx=5)

        frame_log = tk.Frame(self)
        frame_log.pack(fill=tk.BOTH, expand=True, **padding)
        tk.Label(frame_log, text="日志：").pack(anchor=tk.W)
        self.log_widget = scrolledtext.ScrolledText(frame_log, width=80, height=10, state=tk.DISABLED)
        self.log_widget.pack(fill=tk.BOTH, expand=True)

    # region log helpers
    def log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_widget.see(tk.END)
        self.log_widget.configure(state=tk.DISABLED)

    def set_loading(self, loading: bool) -> None:
        state = tk.DISABLED if loading else "readonly"
        self.year_combo.configure(state=state if self.year_combo["values"] else tk.DISABLED)
        self.issue_combo.configure(state=state if self.issue_combo["values"] else tk.DISABLED)
        self.article_list.configure(state=tk.DISABLED if loading else tk.NORMAL)

    # endregion
    # region login and loading
    def login_and_load(self) -> None:
        if self.crawler is None:
            self.crawler = ChinaLandCrawler(delay=self.delay_var.get())
        else:
            self.crawler.delay = self.delay_var.get()
        self.log("开始登录并加载年份……")
        self.set_loading(True)

        def worker() -> None:
            try:
                self.crawler.login()
                years = self.crawler.fetch_years()
            except Exception as exc:  # pylint: disable=broad-except
                self.after(0, self.on_login_failed, exc)
                return
            if not years:
                self.after(0, self.on_login_failed, RuntimeError("未获取到年份数据"))
                return
            self.after(0, self.on_login_success, years)

        threading.Thread(target=worker, daemon=True).start()

    def on_login_failed(self, exc: Exception) -> None:
        self.set_loading(False)
        self.log(f"登录失败：{exc}")
        messagebox.showerror("错误", f"登录失败：{exc}")

    def on_login_success(self, years: list[str]) -> None:
        self.set_loading(False)
        self.magazines_by_year.clear()
        self.articles_by_mag.clear()
        self.article_details.clear()
        self.year_combo.configure(state="readonly")
        self.year_combo["values"] = years
        self.year_var.set("")
        self.issue_combo.set("")
        self.issue_combo["values"] = []
        self.issue_combo.configure(state=tk.DISABLED)
        self.article_list.delete(0, tk.END)
        self.clear_content()
        self.log(f"登录成功，获取到 {len(years)} 个年份。")

    # endregion
    # region selections
    def on_year_selected(self, _event: tk.Event) -> None:  # type: ignore[override]
        year = self.year_var.get()
        if not year:
            return
        self.current_year = year
        if year in self.magazines_by_year:
            magazines = self.magazines_by_year[year]
            self.populate_issues(magazines)
            return

        self.log(f"加载 {year} 年期刊列表……")
        self.issue_combo.configure(state=tk.DISABLED)
        self.article_list.delete(0, tk.END)
        self.clear_content()

        def worker() -> None:
            try:
                magazines = self.crawler.fetch_magazines(year)  # type: ignore[union-attr]
            except Exception as exc:  # pylint: disable=broad-except
                self.after(0, self.on_year_failed, exc)
                return
            if not magazines:
                self.after(0, self.on_year_failed, RuntimeError(f"{year} 年暂无期刊数据"))
                return
            self.magazines_by_year[year] = magazines
            self.after(0, self.populate_issues, magazines)

        threading.Thread(target=worker, daemon=True).start()

    def on_year_failed(self, exc: Exception) -> None:
        self.log(f"加载期刊失败：{exc}")
        messagebox.showerror("错误", f"加载期刊失败：{exc}")

    def populate_issues(self, magazines: list[dict[str, any]]) -> None:
        if not magazines:
            self.log("没有找到期刊。")
            self.issue_combo["values"] = []
            self.issue_combo.configure(state=tk.DISABLED)
            return
        values = [f"{m.get('pageName', '')}（{m.get('date', '')}）|{m['id']}" for m in magazines]
        self.issue_combo.configure(state="readonly")
        self.issue_combo["values"] = values
        self.issue_var.set("")
        self.article_list.delete(0, tk.END)
        self.clear_content()

    def on_issue_selected(self, _event: tk.Event) -> None:  # type: ignore[override]
        selection = self.issue_var.get()
        if not selection:
            return
        magazine_id = selection.split("|")[-1]
        self.current_magazine_id = magazine_id
        if magazine_id in self.articles_by_mag:
            self.populate_articles(self.articles_by_mag[magazine_id])
            return

        self.log("加载文章列表……")
        self.article_list.delete(0, tk.END)
        self.clear_content()

        def worker() -> None:
            try:
                articles = self.crawler.fetch_articles(magazine_id)  # type: ignore[union-attr]
            except Exception as exc:  # pylint: disable=broad-except
                self.after(0, self.on_issue_failed, exc)
                return
            if not articles:
                self.after(0, self.on_issue_failed, RuntimeError("该期刊暂无文章"))
                return
            self.articles_by_mag[magazine_id] = articles
            self.after(0, self.populate_articles, articles)

        threading.Thread(target=worker, daemon=True).start()

    def on_issue_failed(self, exc: Exception) -> None:
        self.log(f"加载文章失败：{exc}")
        messagebox.showerror("错误", f"加载文章失败：{exc}")

    def populate_articles(self, articles: list[dict[str, any]]) -> None:
        self.article_list.delete(0, tk.END)
        for article in sorted(articles, key=lambda x: x.get("index") or 0):
            index_raw = article.get("index")
            try:
                index_str = f"{int(index_raw):03d}"
            except (TypeError, ValueError):
                index_str = str(index_raw)
            title = article.get("titleHtml") or article.get("title") or ""
            title = normalise_whitespace(title)
            self.article_list.insert(tk.END, f"{index_str} {title} | {article['id']}")
        self.article_list.selection_clear(0, tk.END)
        self.clear_content()

    # endregion
    # region article display
    def clear_content(self) -> None:
        self.content_widget.configure(state=tk.NORMAL)
        self.content_widget.delete("1.0", tk.END)
        self.content_widget.configure(state=tk.DISABLED)

    def find_article_metadata(self, article_id: str) -> dict[str, any] | None:
        for articles in self.articles_by_mag.values():
            for article in articles:
                if article["id"] == article_id:
                    return article
        return None

    def on_article_selected(self, _event: tk.Event) -> None:  # type: ignore[override]
        if not self.article_list.curselection():
            return
        selection = self.article_list.get(self.article_list.curselection()[0])
        article_id = selection.split("|")[-1].strip()
        base = self.find_article_metadata(article_id)
        if article_id in self.article_details:
            detail = self.article_details[article_id]
            if base:
                detail = self.get_article_detail(article_id, base=base)
            self.display_article(detail)
            return

        self.log("加载文章详情……")

        def worker() -> None:
            try:
                detail = self.get_article_detail(article_id, base=base)
            except Exception as exc:  # pylint: disable=broad-except
                self.after(0, self.on_article_failed, exc)
                return
            if not detail:
                self.after(0, self.on_article_failed, RuntimeError("文章详情为空"))
                return
            self.after(0, self.display_article, detail)

        threading.Thread(target=worker, daemon=True).start()

    def on_article_failed(self, exc: Exception) -> None:
        self.log(f"加载文章详情失败：{exc}")
        messagebox.showerror("错误", f"加载文章详情失败：{exc}")

    def get_articles_for_magazine(self, magazine_id: str) -> list[dict[str, any]]:
        if magazine_id in self.articles_by_mag:
            return self.articles_by_mag[magazine_id]
        articles = self.crawler.fetch_articles(magazine_id)  # type: ignore[union-attr]
        self.articles_by_mag[magazine_id] = articles
        return articles

    def get_article_detail(self, article_id: str, base: dict[str, any] | None = None) -> dict[str, any]:
        if article_id in self.article_details:
            detail = self.article_details[article_id].copy()
            if base:
                detail.setdefault("index", base.get("index"))
                for key in ("title", "titleHtml", "author", "authorHtml", "column", "text", "pageNumber"):
                    if key not in detail and key in base:
                        detail[key] = base[key]
            return detail
        detail = self.crawler.fetch_article_detail(article_id)  # type: ignore[union-attr]
        if base:
            enriched = detail.copy()
            enriched.setdefault("index", base.get("index"))
            for key in (
                "title",
                "titleHtml",
                "author",
                "authorHtml",
                "column",
                "text",
                "pageNumber",
                "coverImgPath",
            ):
                if key not in enriched and key in base:
                    enriched[key] = base[key]
            detail = enriched
        self.article_details[article_id] = detail
        return detail

    def display_article(self, detail: dict[str, any]) -> None:
        title = normalise_whitespace(detail.get("titleHtml") or detail.get("title") or "")
        author = normalise_whitespace(detail.get("authorHtml") or detail.get("author") or "")
        column = normalise_whitespace(detail.get("column") or "")
        body = normalise_whitespace(detail.get("html") or "") or normalise_whitespace(detail.get("text") or "")
        images = extract_images(detail.get("html"))
        meta = []
        if column:
            meta.append(f"栏目：{column}")
        if author:
            meta.append(f"作者：{author}")
        content_parts = [title, ""]
        if meta:
            content_parts.append("\n".join(meta))
            content_parts.append("")
        if images:
            for idx, image in enumerate(images, start=1):
                caption = image["alt"] or f"图片{idx}"
                content_parts.append(f"![{caption}]({image['url']})")
            content_parts.append("")
        content_parts.append(body)
        content = "\n".join(part for part in content_parts if part is not None)
        self.content_widget.configure(state=tk.NORMAL)
        self.content_widget.delete("1.0", tk.END)
        self.content_widget.insert(tk.END, content)
        self.content_widget.configure(state=tk.DISABLED)

    # endregion
    # region export helpers
    def ensure_output_dir(self) -> Path | None:
        directory = filedialog.askdirectory(title="选择导出目录")
        if not directory:
            return None
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_current_magazine(self) -> dict[str, any] | None:
        if not self.current_year or not self.current_magazine_id:
            return None
        magazines = self.magazines_by_year.get(self.current_year, [])
        for magazine in magazines:
            if magazine["id"] == self.current_magazine_id:
                return magazine
        return None

    def get_magazines_for_year(self, year: str) -> list[dict[str, any]]:
        if year in self.magazines_by_year:
            return self.magazines_by_year[year]
        magazines = self.crawler.fetch_magazines(year)  # type: ignore[union-attr]
        self.magazines_by_year[year] = magazines
        return magazines

    def collect_issue_payload(self, magazine: dict[str, any], need_detail: bool = True) -> list[dict[str, any]]:
        articles = self.get_articles_for_magazine(magazine["id"])
        result: List[Dict[str, any]] = []
        for article in articles:
            base = article.copy()
            if need_detail:
                detail = self.get_article_detail(article["id"], base=base)
                result.append(detail)
            else:
                result.append(base)
        return result

    # endregion
    # region export actions
    def export_selected_article(self) -> None:
        if not self.article_list.curselection():
            messagebox.showinfo("提示", "请先选择文章。")
            return
        selection = self.article_list.get(self.article_list.curselection()[0])
        article_id = selection.split("|")[-1].strip()
        base = self.find_article_metadata(article_id)
        try:
            detail = self.get_article_detail(article_id, base=base)
        except Exception as exc:  # pylint: disable=broad-except
            self.log(f"获取文章失败：{exc}")
            messagebox.showerror("错误", f"获取文章失败：{exc}")
            return
        directory = filedialog.asksaveasfilename(
            title="保存文章",
            defaultextension=".md",
            filetypes=[("Markdown 文件", "*.md"), ("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile=f"{detail.get('title', 'article')}.md",
        )
        if not directory:
            return
        path = Path(directory)
        content = render_article(detail)
        path.write_text(content + "\n", encoding="utf-8")
        self.log(f"文章已导出：{path}")
        messagebox.showinfo("完成", f"文章已保存至：{path}")

    def export_selected_issue(self) -> None:
        magazine = self.get_current_magazine()
        if not magazine:
            messagebox.showinfo("提示", "请先选择期刊。")
            return
        output_dir = self.ensure_output_dir()
        if not output_dir:
            return
        prefix = self.prefix_var.get().strip() or "中国土地"
        self.log("导出期刊中……")

        def worker() -> None:
            try:
                issue_articles = self.collect_issue_payload(magazine)
                write_issue_markdown(
                    {
                        "id": magazine["id"],
                        "year": self.current_year,
                        "pageName": magazine.get("pageName"),
                        "date": magazine.get("date"),
                        "title": magazine.get("title") or magazine.get("subject"),
                    },
                    sorted(issue_articles, key=lambda x: x.get("index") or 0),
                    output_dir,
                    prefix,
                    fallback_name=magazine["id"],
                )
            except Exception as exc:  # pylint: disable=broad-except
                self.after(0, self.export_failed, exc)
                return
            self.after(0, self.export_success, f"已导出期刊至 {output_dir}")

        threading.Thread(target=worker, daemon=True).start()

    def export_selected_year(self) -> None:
        if not self.current_year:
            messagebox.showinfo("提示", "请先选择年份。")
            return
        output_dir = self.ensure_output_dir()
        if not output_dir:
            return
        prefix = self.prefix_var.get().strip() or "中国土地"
        year = self.current_year
        self.log(f"导出 {year} 年全部期刊……")

        def worker() -> None:
            try:
                magazines = self.get_magazines_for_year(year)
                for magazine in magazines:
                    issue_articles = self.collect_issue_payload(magazine)
                    write_issue_markdown(
                        {
                            "id": magazine["id"],
                            "year": year,
                            "pageName": magazine.get("pageName"),
                            "date": magazine.get("date"),
                            "title": magazine.get("title") or magazine.get("subject"),
                        },
                        sorted(issue_articles, key=lambda x: x.get("index") or 0),
                        output_dir,
                        prefix,
                        fallback_name=magazine["id"],
                    )
            except Exception as exc:  # pylint: disable=broad-except
                self.after(0, self.export_failed, exc)
                return
            self.after(0, self.export_success, f"{year} 年期刊导出完成。")

        threading.Thread(target=worker, daemon=True).start()

    def export_all(self) -> None:
        if not self.year_combo["values"]:
            messagebox.showinfo("提示", "请先登录并加载年份。")
            return
        output_dir = self.ensure_output_dir()
        if not output_dir:
            return
        prefix = self.prefix_var.get().strip() or "中国土地"
        years = list(self.year_combo["values"])
        self.log("开始全量导出……")

        def worker() -> None:
            try:
                for year in years:
                    magazines = self.get_magazines_for_year(year)
                    for magazine in magazines:
                        issue_articles = self.collect_issue_payload(magazine)
                        write_issue_markdown(
                            {
                                "id": magazine["id"],
                                "year": year,
                                "pageName": magazine.get("pageName"),
                                "date": magazine.get("date"),
                                "title": magazine.get("title") or magazine.get("subject"),
                            },
                            sorted(issue_articles, key=lambda x: x.get("index") or 0),
                            output_dir,
                            prefix,
                            fallback_name=magazine["id"],
                        )
                    self.log(f"{year} 年导出完成。")
            except Exception as exc:  # pylint: disable=broad-except
                self.after(0, self.export_failed, exc)
                return
            self.after(0, self.export_success, "全量导出完成。")

        threading.Thread(target=worker, daemon=True).start()

    def export_failed(self, exc: Exception) -> None:
        self.log(f"导出失败：{exc}")
        messagebox.showerror("错误", f"导出失败：{exc}")

    def export_success(self, message: str) -> None:
        self.log(message)
        messagebox.showinfo("完成", message)

    # endregion


def main() -> None:
    app = ChinaLandGUI()
    app.mainloop()

