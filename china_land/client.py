"""网络层：封装中国土地期刊站点的接口调用。"""

from __future__ import annotations

import json
import random
import time
import uuid
from typing import Any

import requests

BASE_URL = "http://szb.iziran.net"
COLUMN_ID = 2  # “中国土地”栏目

COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
    ),
    "SITE": "iziran",
    "BROWER_LANGUAGE": "zh-CN",
    "SCREEN": "1080x1920",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/zazhi-pc/html/index.html?cid={COLUMN_ID}",
}


class ChinaLandCrawler:
    """中国土地期刊数据抓取客户端。"""

    def __init__(self, delay: float = 1.5) -> None:
        self.session = requests.Session()
        self.session.headers.update(COMMON_HEADERS)
        self.session.headers["myIdentity"] = self._generate_identity()
        self.delay = delay

    @staticmethod
    def _generate_identity() -> str:
        return f"crawler-{uuid.uuid4()}"

    def _respect_delay(self) -> None:
        sleep_time = max(0.0, self.delay + random.uniform(-0.3, 0.3))
        time.sleep(sleep_time)

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{BASE_URL}{path}"
        try:
            response = self.session.request(method, url, data=data, params=params, timeout=15)
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as exc:
            raise RuntimeError(f"请求超时: {url}") from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"网络错误: {url}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"解析 JSON 失败: {url}") from exc

        if not payload.get("success"):
            message = payload.get("message", "未知错误")
            raise RuntimeError(f"接口返回失败: {url} -> {message}")
        return payload

    # --- 登录 / 初始化 -------------------------------------------------
    def login(self) -> None:
        params = {"rd": int(time.time() * 1000)}
        self._request("GET", "/user/ipLogin", params=params)
        self._respect_delay()

    # --- 数据接口 -----------------------------------------------------
    def fetch_years(self) -> list[str]:
        data = {"columnId": COLUMN_ID}
        payload = self._request("POST", "/magazine/queryYearByColumn", data=data)
        years = payload.get("data", [])
        if not isinstance(years, list):
            raise RuntimeError("年份接口返回格式不正确")
        return years

    def fetch_magazines(self, year: str) -> list[dict[str, Any]]:
        data = {"columnId": COLUMN_ID, "year": year}
        payload = self._request("POST", "/magazine/queryMagazineByColumn", data=data)
        magazines = payload.get("data", [])
        if not isinstance(magazines, list):
            raise RuntimeError("期刊接口返回格式不正确")
        self._respect_delay()
        return magazines

    def fetch_articles(self, magazine_id: str) -> list[dict[str, Any]]:
        data = {"magazineId": magazine_id}
        payload = self._request("POST", "/magazine/getArticleByMagazineId", data=data)
        articles = payload.get("data", [])
        if not isinstance(articles, list):
            raise RuntimeError("文章列表接口返回格式不正确")
        self._respect_delay()
        return articles

    def fetch_article_detail(self, article_id: str) -> dict[str, Any]:
        data = {"articleId": article_id}
        payload = self._request("POST", "/magazine/getArticleById", data=data)
        article = payload.get("data")
        if not isinstance(article, dict):
            raise RuntimeError("文章详情接口返回格式不正确")
        self._respect_delay()
        return article

