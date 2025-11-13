"""GUI 窗口入口。"""

from __future__ import annotations

import concurrent.futures
import threading
import time
import tkinter as tk
from collections import defaultdict
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Any, Dict, List, Tuple

from .client import ChinaLandCrawler
from .export import (
    extract_images,
    normalise_whitespace,
    render_article,
    write_all_markdown,
    write_article_separately,
    write_issue_markdown,
    write_year_markdown,
)


class ChinaLandGUI(tk.Tk):
    """主界面。"""

    def __init__(self) -> None:
        super().__init__()
        self.title("中国土地期刊爬虫")
        self.resizable(False, False)

        self.crawler: ChinaLandCrawler | None = None
        self.current_year: str | None = None
        self.current_magazine_id: str | None = None
        self.magazines_by_year: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.articles_by_mag: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.article_details: dict[str, dict[str, Any]] = {}
        self.progress_total = 1
        self.progress_current = 0
        self.progress_text = ""
        self.export_mode_var = tk.StringVar(value="按期 (每期MD)")
        self.is_exporting = False
        self.pause_event: threading.Event | None = None
        self.cancel_flag = False
        self.pause_button: tk.Button | None = None
        self.cancel_button: tk.Button | None = None

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
        self.export_article_btn = tk.Button(frame_actions, text="导出所选文章", command=self.export_selected_article)
        self.export_article_btn.pack(side=tk.LEFT)
        self.export_issue_btn = tk.Button(frame_actions, text="导出所选期刊", command=self.export_selected_issue)
        self.export_issue_btn.pack(side=tk.LEFT, padx=5)
        self.export_year_btn = tk.Button(frame_actions, text="导出所选年份", command=self.export_selected_year)
        self.export_year_btn.pack(side=tk.LEFT, padx=5)
        self.export_all_btn = tk.Button(frame_actions, text="全量导出", command=self.export_all)
        self.export_all_btn.pack(side=tk.LEFT)

        frame_mode = tk.Frame(self)
        frame_mode.pack(fill=tk.X, **padding)
        tk.Label(frame_mode, text="导出模式：").pack(side=tk.LEFT)
        self.export_mode_combo = ttk.Combobox(
            frame_mode,
            textvariable=self.export_mode_var,
            values=["按文章 (每个MD)", "按期 (每期MD)", "按年 (每年MD)", "单文件 (合并)"],
            state="readonly",
            width=15,
        )
        self.export_mode_combo.pack(side=tk.LEFT, padx=5)

        frame_export_control = tk.Frame(self)
        frame_export_control.pack(fill=tk.X, **padding)
        self.pause_button = tk.Button(frame_export_control, text="暂停", command=self.toggle_pause, state=tk.DISABLED)
        self.pause_button.pack(side=tk.LEFT, padx=5)
        self.cancel_button = tk.Button(frame_export_control, text="取消", command=self.cancel_export, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.LEFT)

        frame_progress = tk.Frame(self)
        frame_progress.pack(fill=tk.X, **padding)
        self.progress_label_var = tk.StringVar(value="进度：待命")
        tk.Label(frame_progress, textvariable=self.progress_label_var, anchor="w").pack(fill=tk.X)
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(frame_progress, maximum=1, variable=self.progress_var)
        self.progress_bar.pack(fill=tk.X, pady=(2, 0))

        frame_prefix = tk.Frame(self)
        frame_prefix.pack(fill=tk.X, **padding)
        tk.Label(frame_prefix, text="导出文件前缀：").pack(side=tk.LEFT)
        self.prefix_var = tk.StringVar(value="中国土地")
        self.prefix_entry = tk.Entry(frame_prefix, width=20, textvariable=self.prefix_var)
        self.prefix_entry.pack(side=tk.LEFT, padx=5)

        frame_log = tk.Frame(self)
        frame_log.pack(fill=tk.BOTH, expand=True, **padding)
        tk.Label(frame_log, text="日志：").pack(anchor=tk.W)
        self.log_widget = scrolledtext.ScrolledText(frame_log, width=80, height=10, state=tk.DISABLED)
        self.log_widget.pack(fill=tk.BOTH, expand=True)
        self.reset_progress()

    def disable_export_controls(self, disable: bool) -> None:
        state = "disabled" if disable else "normal"
        self.export_article_btn.configure(state=state)
        self.export_issue_btn.configure(state=state)
        self.export_year_btn.configure(state=state)
        self.export_all_btn.configure(state=state)
        self.export_mode_combo.configure(state=state)
        self.year_combo.configure(state=state if not disable and self.year_combo["values"] else "disabled")
        self.issue_combo.configure(state=state if not disable and self.issue_combo["values"] else "disabled")
        self.article_list.configure(state=state)
        self.prefix_entry.configure(state=state)
        if self.pause_button:
            self.pause_button.configure(state="normal" if disable else "disabled")
        if self.cancel_button:
            self.cancel_button.configure(state="normal" if disable else "disabled")

    def set_loading(self, loading: bool) -> None:
        if not self.is_exporting:
            state = tk.DISABLED if loading else "readonly"
            self.year_combo.configure(state=state if self.year_combo["values"] else tk.DISABLED)
            self.issue_combo.configure(state=state if self.issue_combo["values"] else tk.DISABLED)
            self.article_list.configure(state=tk.DISABLED if loading else tk.NORMAL)

    def toggle_pause(self) -> None:
        if self.pause_event is None:
            return
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_button.configure(text="恢复")
            self.log("导出已暂停")
        else:
            self.pause_event.set()
            self.pause_button.configure(text="暂停")
            self.log("导出已恢复")

    def cancel_export(self) -> None:
        self.cancel_flag = True
        if self.pause_event:
            self.pause_event.set()  # Resume to check cancel
        self.log("导出取消中...")
        self.after(1000, self._finish_cancel)

    def _finish_cancel(self) -> None:
        self.is_exporting = False
        self.disable_export_controls(False)
        self.finish_progress("导出已取消")
        self.log("导出已取消")
        messagebox.showinfo("取消", "导出已取消")

    # region log helpers
    def log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_widget.see(tk.END)
        self.log_widget.configure(state=tk.DISABLED)

    def reset_progress(self) -> None:
        self.progress_total = 1
        self.progress_current = 0
        self.progress_text = "进度：待命"
        self.progress_label_var.set(self.progress_text)
        self.progress_bar["maximum"] = 1
        self.progress_var.set(0)

    def start_progress(self, total: int, text: str) -> None:
        total = max(total, 1)
        self.progress_total = total
        self.progress_current = 0
        self.progress_text = text
        self.progress_bar["maximum"] = total
        self.progress_var.set(0)
        self.progress_label_var.set(f"{text} (0/{total})")
        self.progress_bar.update_idletasks()

    def update_progress(self, step: int = 1, text: str | None = None) -> None:
        if self.progress_total <= 0:
            return
        self.progress_current = min(self.progress_total, self.progress_current + step)
        display_text = text or self.progress_text
        self.progress_label_var.set(f"{display_text} ({self.progress_current}/{self.progress_total})")
        self.progress_var.set(self.progress_current)
        self.progress_bar.update_idletasks()

    def finish_progress(self, text: str | None = None) -> None:
        if text:
            self.progress_label_var.set(text)
        else:
            self.progress_label_var.set(f"{self.progress_text} 完成")
        self.progress_var.set(self.progress_total)
        self.progress_bar.update_idletasks()
        self.after(1500, self.reset_progress)

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

    def populate_issues(self, magazines: list[dict[str, Any]]) -> None:
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

    def populate_articles(self, articles: list[dict[str, Any]]) -> None:
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

    def find_article_metadata(self, article_id: str) -> dict[str, Any] | None:
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

    def get_articles_for_magazine(self, magazine_id: str) -> list[dict[str, Any]]:
        if magazine_id in self.articles_by_mag:
            return self.articles_by_mag[magazine_id]
        articles = self.crawler.fetch_articles(magazine_id)  # type: ignore[union-attr]
        self.articles_by_mag[magazine_id] = articles
        return articles

    def get_article_detail(self, article_id: str, base: dict[str, Any] | None = None) -> dict[str, Any]:
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

    def display_article(self, detail: dict[str, Any]) -> None:
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

    def get_current_magazine(self) -> dict[str, Any] | None:
        if not self.current_year or not self.current_magazine_id:
            return None
        magazines = self.magazines_by_year.get(self.current_year, [])
        for magazine in magazines:
            if magazine["id"] == self.current_magazine_id:
                return magazine
        return None

    def get_magazines_for_year(self, year: str) -> list[dict[str, Any]]:
        if year in self.magazines_by_year:
            return self.magazines_by_year[year]
        magazines = self.crawler.fetch_magazines(year)  # type: ignore[union-attr]
        self.magazines_by_year[year] = magazines
        return magazines

    def collect_issue_payload(
        self, magazine: dict[str, Any], need_detail: bool = True
    ) -> list[dict[str, Any]]:
        articles = self.get_articles_for_magazine(magazine["id"])
        result: List[Dict[str, Any]] = []
        for article in articles:
            base = article.copy()
            base["magazine_id"] = magazine["id"]
            base["magazine_meta"] = magazine
            if need_detail:
                detail = self.get_article_detail(article["id"], base=base)
                detail["magazine_id"] = magazine["id"]
                detail["magazine_meta"] = magazine
                result.append(detail)
            else:
                result.append(base)
        return result

    def get_mode_key(self) -> str:
        mode_map = {
            "按文章 (每个MD)": "per_article",
            "按期 (每期MD)": "per_issue",
            "按年 (每年MD)": "per_year",
            "单文件 (合并)": "all_in_one",
        }
        return mode_map.get(self.export_mode_var.get(), "per_issue")

    def confirm_full_export(self, range_name: str, selected_count: int) -> bool:
        if selected_count > 0 and range_name != "文章":
            return messagebox.askyesno(
                "确认导出范围",
                f"当前选择了 {selected_count} 篇文章，但 {range_name} 导出将包含完整范围的所有文章/期刊。是否继续？",
            )
        return True

    # endregion
    # region export actions
    def _start_export(self, func: callable) -> None:
        if self.is_exporting:
            messagebox.showwarning("警告", "已有导出任务进行中，请等待完成或取消。")
            return
        self.is_exporting = True
        self.cancel_flag = False
        self.pause_event = threading.Event()
        self.pause_event.set()  # Initially resumed
        self.pause_button.configure(text="暂停", state="normal")
        self.cancel_button.configure(state="normal")
        self.disable_export_controls(True)
        threading.Thread(target=func, daemon=True).start()

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
        magazine = self.get_current_magazine()
        if magazine:
            detail["magazine_meta"] = magazine
        directory = filedialog.asksaveasfilename(
            title="保存文章",
            defaultextension=".md",
            filetypes=[("Markdown 文件", "*.md"), ("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile=f"{detail.get('title', 'article')}.md",
        )
        if not directory:
            return
        path = Path(directory)
        self.start_progress(1, "导出文章")

        def worker() -> None:
            try:
                if magazine:
                    write_article_separately(detail, magazine, path.parent, self.prefix_var.get())
                else:
                    content = render_article(detail)
                    path.write_text(content + "\n", encoding="utf-8")
                self.after(0, self.update_progress, 1, "导出文章")
            except Exception as exc:  # pylint: disable=broad-except
                self.after(0, self.export_failed, exc)
                return
            self.after(0, self.export_success, f"文章已保存至：{path}")

        threading.Thread(target=worker, daemon=True).start()
        self.is_exporting = False  # Single, no need for controls
        self.disable_export_controls(False)

    def export_selected_issue(self) -> None:
        magazine = self.get_current_magazine()
        if not magazine:
            messagebox.showinfo("提示", "请先选择期刊。")
            return
        selected_count = len(self.article_list.curselection()) if self.article_list.curselection() else 0
        if not self.confirm_full_export("期刊", selected_count):
            return
        output_dir = self.ensure_output_dir()
        if not output_dir:
            return
        prefix = self.prefix_var.get().strip() or "中国土地"
        mode = self.get_mode_key()
        self.log(f"导出期刊（模式：{mode}）……")
        articles = self.get_articles_for_magazine(magazine["id"])
        if not articles:
            messagebox.showinfo("提示", "该期刊暂无文章。")
            return
        issue_name = magazine.get("pageName") or magazine["id"]

        def worker_func() -> None:
            try:
                pause_event = self.pause_event
                cancel_flag = self.cancel_flag
                if mode == "per_article":
                    self.after(0, self.start_progress, len(articles), f"导出期刊文章：{issue_name}")
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                        future_to_art = {executor.submit(self.get_article_detail, art["id"], art): art for art in articles}
                        completed = 0
                        for future in concurrent.futures.as_completed(future_to_art):
                            if cancel_flag:
                                break
                            pause_event.wait()
                            try:
                                detail = future.result()
                                art = future_to_art[future]
                                art["magazine_meta"] = magazine
                                detail["magazine_id"] = magazine["id"]
                                detail["magazine_meta"] = magazine
                                write_article_separately(detail, magazine, output_dir, prefix)
                                completed += 1
                                self.after(0, lambda: self.update_progress(1, f"导出期刊文章：{issue_name}"))
                            except Exception as exc:
                                self.log(f"文章详情失败：{exc}")
                                completed += 1
                                self.after(0, lambda: self.update_progress(1, f"导出期刊文章：{issue_name}"))
                else:
                    self.after(0, self.start_progress, len(articles), f"导出期刊：{issue_name}")
                    issue_articles = []
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                        future_to_base = {executor.submit(self.get_article_detail, art["id"], art): art for art in articles}
                        for future in concurrent.futures.as_completed(future_to_base):
                            if cancel_flag:
                                break
                            pause_event.wait()
                            try:
                                detail = future.result()
                                issue_articles.append(detail)
                                self.after(0, lambda: self.update_progress(1, f"导出期刊：{issue_name}"))
                            except Exception as exc:
                                self.log(f"文章详情失败：{exc}")
                                self.after(0, lambda: self.update_progress(1, f"导出期刊：{issue_name}"))
                    write_issue_markdown(
                        magazine,
                        sorted(issue_articles, key=lambda x: x.get("index") or 0),
                        output_dir,
                        prefix,
                        fallback_name=magazine["id"],
                    )
                if not cancel_flag:
                    self.after(0, self.export_success, f"已导出期刊至 {output_dir}")
                else:
                    self.after(0, self._finish_cancel)
            except Exception as exc:
                if not cancel_flag:
                    self.after(0, self.export_failed, exc)
                else:
                    self.after(0, self._finish_cancel)

        self._start_export(worker_func)

    def export_selected_year(self) -> None:
        if not self.current_year:
            messagebox.showinfo("提示", "请先选择年份。")
            return
        selected_count = len(self.article_list.curselection()) if self.article_list.curselection() else 0
        if not self.confirm_full_export("年份", selected_count):
            return
        output_dir = self.ensure_output_dir()
        if not output_dir:
            return
        prefix = self.prefix_var.get().strip() or "中国土地"
        year = self.current_year
        mode = self.get_mode_key()
        self.log(f"导出 {year} 年（模式：{mode}）……")
        magazines = self.get_magazines_for_year(year)
        if not magazines:
            messagebox.showinfo("提示", f"{year} 年暂无期刊。")
            return

        def worker_func() -> None:
            try:
                pause_event = self.pause_event
                cancel_flag = self.cancel_flag
                all_articles: List[Dict[str, Any]] = []
                total_items = 0
                if mode == "per_article":
                    # Pre-count articles
                    for mag in magazines:
                        mag_articles = self.get_articles_for_magazine(mag["id"])
                        total_items += len(mag_articles)
                    self.after(0, self.start_progress, total_items, f"导出 {year} 年文章")
                    for mag in magazines:
                        if cancel_flag:
                            break
                        pause_event.wait()
                        mag_articles = self.get_articles_for_magazine(mag["id"])
                        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                            future_to_art = {executor.submit(self.get_article_detail, art["id"], art): art for art in mag_articles}
                            for future in concurrent.futures.as_completed(future_to_art):
                                if cancel_flag:
                                    break
                                pause_event.wait()
                                try:
                                    detail = future.result()
                                    art = future_to_art[future]
                                    art["magazine_meta"] = mag
                                    write_article_separately(detail, mag, output_dir, prefix)
                                    self.after(0, self.update_progress, 1, f"导出 {year} 年文章")
                                except Exception as exc:
                                    self.log(f"文章详情失败：{exc}")
                                    self.after(0, self.update_progress, 1, f"导出 {year} 年文章")
                elif mode in ["per_year", "all_in_one"]:
                    # Collect all
                    for mag in magazines:
                        if cancel_flag:
                            break
                        pause_event.wait()
                        mag_articles_base = self.get_articles_for_magazine(mag["id"])
                        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                            future_to_base = {executor.submit(self.get_article_detail, art["id"], art): art for art in mag_articles_base}
                            mag_articles = []
                            for future in concurrent.futures.as_completed(future_to_base):
                                if cancel_flag:
                                    break
                                pause_event.wait()
                                try:
                                    detail = future.result()
                                    mag_articles.append(detail)
                                    self.after(0, self.update_progress, 1, f"导出 {year} 年")
                                except Exception as exc:
                                    self.log(f"文章详情失败：{exc}")
                                    self.after(0, self.update_progress, 1, f"导出 {year} 年")
                        all_articles.extend(mag_articles)
                    write_year_markdown(year, magazines, all_articles, output_dir, prefix)
                else:  # per_issue
                    self.after(0, self.start_progress, len(magazines), f"导出 {year} 年")
                    for mag in magazines:
                        if cancel_flag:
                            break
                        pause_event.wait()
                        issue_articles = self.collect_issue_payload(mag)
                        write_issue_markdown(
                            mag,
                            sorted(issue_articles, key=lambda x: x.get("index") or 0),
                            output_dir,
                            prefix,
                            fallback_name=mag["id"],
                        )
                        self.after(0, self.update_progress, 1, f"导出 {year} 年")
                if not cancel_flag:
                    self.after(0, self.export_success, f"{year} 年导出完成。")
                else:
                    self.after(0, self._finish_cancel)
            except Exception as exc:
                if not cancel_flag:
                    self.after(0, self.export_failed, exc)
                else:
                    self.after(0, self._finish_cancel)

        self._start_export(worker_func)

    def export_all(self) -> None:
        if not self.year_combo["values"]:
            messagebox.showinfo("提示", "请先登录并加载年份。")
            return
        selected_count = len(self.article_list.curselection()) if self.article_list.curselection() else 0
        if not self.confirm_full_export("全量", selected_count):
            return
        output_dir = self.ensure_output_dir()
        if not output_dir:
            return
        prefix = self.prefix_var.get().strip() or "中国土地"
        years = list(self.year_combo["values"])
        mode = self.get_mode_key()
        self.log(f"全量导出（模式：{mode}）……")

        def worker_func() -> None:
            try:
                pause_event = self.pause_event
                cancel_flag = self.cancel_flag
                year_magazines: List[Tuple[str, List[Dict[str, Any]]]] = []
                all_articles: List[Dict[str, Any]] = []
                total_items = 0
                if mode == "per_article":
                    # Pre-count
                    for year in years:
                        magazines = self.get_magazines_for_year(year)
                        for mag in magazines:
                            mag_articles = self.get_articles_for_magazine(mag["id"])
                            total_items += len(mag_articles)
                    self.after(0, self.start_progress, total_items, "全量导出文章")
                    for year in years:
                        if cancel_flag:
                            break
                        pause_event.wait()
                        magazines = self.get_magazines_for_year(year)
                        for mag in magazines:
                            if cancel_flag:
                                break
                            pause_event.wait()
                            mag_articles = self.get_articles_for_magazine(mag["id"])
                            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                                future_to_art = {executor.submit(self.get_article_detail, art["id"], art): art for art in mag_articles}
                                for future in concurrent.futures.as_completed(future_to_art):
                                    if cancel_flag:
                                        break
                                    pause_event.wait()
                                    try:
                                        detail = future.result()
                                        art = future_to_art[future]
                                        art["magazine_meta"] = mag
                                        write_article_separately(detail, mag, output_dir, prefix)
                                        self.after(0, self.update_progress, 1, "全量导出文章")
                                    except Exception as exc:
                                        self.log(f"文章详情失败：{exc}")
                                        self.after(0, self.update_progress, 1, "全量导出文章")
                elif mode == "all_in_one":
                    for year in years:
                        if cancel_flag:
                            break
                        pause_event.wait()
                        magazines = self.get_magazines_for_year(year)
                        year_magazines.append((year, magazines))
                        year_all_articles = []
                        for mag in magazines:
                            if cancel_flag:
                                break
                            pause_event.wait()
                            mag_articles_base = self.get_articles_for_magazine(mag["id"])
                            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                                future_to_base = {executor.submit(self.get_article_detail, art["id"], art): art for art in mag_articles_base}
                                for future in concurrent.futures.as_completed(future_to_base):
                                    if cancel_flag:
                                        break
                                    pause_event.wait()
                                    try:
                                        detail = future.result()
                                        year_all_articles.append(detail)
                                        self.after(0, self.update_progress, 1, "全量导出")
                                    except Exception as exc:
                                        self.log(f"文章详情失败：{exc}")
                                        self.after(0, self.update_progress, 1, "全量导出")
                        all_articles.extend(year_all_articles)
                    write_all_markdown(years, year_magazines, all_articles, output_dir, prefix)
                elif mode == "per_year":
                    total_years = len(years)
                    self.after(0, self.start_progress, total_years, "全量导出（按年）")
                    for year in years:
                        if cancel_flag:
                            break
                        pause_event.wait()
                        magazines = self.get_magazines_for_year(year)
                        year_all_articles: List[Dict[str, Any]] = []
                        for mag in magazines:
                            if cancel_flag:
                                break
                            pause_event.wait()
                            mag_articles_base = self.get_articles_for_magazine(mag["id"])
                            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                                future_to_base = {executor.submit(self.get_article_detail, art["id"], art): art for art in mag_articles_base}
                                for future in concurrent.futures.as_completed(future_to_base):
                                    if cancel_flag:
                                        break
                                    pause_event.wait()
                                    try:
                                        detail = future.result()
                                        year_all_articles.append(detail)
                                    except Exception as exc:
                                        self.log(f"文章详情失败：{exc}")
                        write_year_markdown(year, magazines, year_all_articles, output_dir, prefix)
                        self.after(0, self.update_progress, 1, "全量导出（按年）")
                else:  # per_issue
                    total_magazines = 0
                    for year in years:
                        magazines = self.get_magazines_for_year(year)
                        total_magazines += len(magazines)
                    self.after(0, self.start_progress, total_magazines, "全量导出")
                    for year in years:
                        if cancel_flag:
                            break
                        pause_event.wait()
                        magazines = self.get_magazines_for_year(year)
                        for mag in magazines:
                            if cancel_flag:
                                break
                            pause_event.wait()
                            issue_articles = self.collect_issue_payload(mag)
                            write_issue_markdown(
                                mag,
                                sorted(issue_articles, key=lambda x: x.get("index") or 0),
                                output_dir,
                                prefix,
                                fallback_name=mag["id"],
                            )
                            self.after(0, self.update_progress, 1, "全量导出")
                        self.log(f"{year} 年导出完成。")
                if not cancel_flag:
                    self.after(0, self.export_success, "全量导出完成。")
                else:
                    self.after(0, self._finish_cancel)
            except Exception as exc:
                if not cancel_flag:
                    self.after(0, self.export_failed, exc)
                else:
                    self.after(0, self._finish_cancel)

        self._start_export(worker_func)

    def export_failed(self, exc: Exception) -> None:
        self.is_exporting = False
        self.disable_export_controls(False)
        self.finish_progress("导出失败")
        self.log(f"导出失败：{exc}")
        messagebox.showerror("错误", f"导出失败：{exc}")

    def export_success(self, message: str) -> None:
        self.is_exporting = False
        self.disable_export_controls(False)
        self.finish_progress(message)
        self.log(message)
        messagebox.showinfo("完成", message)

    # endregion


def main() -> None:
    app = ChinaLandGUI()
    app.mainloop()

