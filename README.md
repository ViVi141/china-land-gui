# 中国土地期刊爬虫 GUI

作者：ViVi141  
邮箱：747384120@qq.com  
版本：1.0  
许可证：GPL v2.0（详见 `LICENSE`）  
版权所有 (C) 2025 ViVi141

这个项目提供一个基于 tkinter 的桌面工具，用来浏览和导出“中国土地”期刊内容。界面支持按年份、期刊、文章三级筛选，导出的 Markdown 会保留官网图片的在线引用，适合后续做文本分析或接入 RAG。

## 功能

- 登录并读取年份、期刊、文章列表；
- 在 GUI 中查看文章正文和图片；
- 导出 Markdown：
  * 单篇文章；
  * 当前期刊（每期期刊一个文件）；
  * 当前年份全部期刊；
  * 所有年份；
- Markdown 中自动插入图片链接（`http://szb.iziran.net/dataFile/...`）。

## 目录结构

```
CHINA LAND/
├── README.md
├── requirements.txt
├── pyproject.toml
├── run_gui.py
└── china_land/
    ├── __init__.py
    ├── client.py      # 网络请求
    ├── export.py      # HTML 清洗、Markdown 生成
    └── gui.py         # tkinter 界面
```

## 环境

- Python 3.10 及以上（已在 3.13/3.14 测试）
- 第三方库：`requests`

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

运行界面：

```powershell
python run_gui.py
```

点击“登录 / 刷新”后会加载年份列表，再选择期刊与文章即可浏览或导出。过程中若出现网络错误、超时或站点返回空数据，界面会弹出提示，请稍后重试。导出的 Markdown 默认以 `2025_第10期.md` 这类格式命名，里面的 `![...]()` 可以直接用于 RAG 解析。

## 开发提示

- `china_land.client.ChinaLandCrawler`：封装所有 HTTP 接口；
- `china_land.export.render_article` / `write_issue_markdown`：Markdown 生成；
- `china_land.gui.main`：GUI 主函数，`run_gui.py` 只是入口脚本；
- 若想扩展图片本地下载或 JSONL 存储，可在 `export.py` 中添加函数；
- 项目附带基础 `pyproject.toml`，需要时可以执行 `python -m build` 打包。

## 注意事项

本工具仅供学习、研究使用。请遵守目标网站的服务条款和 robots 协议，合理控制访问频率，避免对服务器造成压力。
