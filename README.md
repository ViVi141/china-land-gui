# 中国土地期刊爬虫 GUI

## 作者与版本
- 作者：ViVi141 (747384120@qq.com)
- 版本：1.1.0
- 许可证：GNU GPL v2.0 (详见 LICENSE 文件)

一个使用 tkinter 图形界面封装的爬虫小工具，用于浏览和导出 “中国土地” 期刊文章。项目按照常见 Python 包结构组织，网络访问、数据清洗、界面逻辑分层清晰，并默认在 Markdown 中保留原站点图片的在线引用，方便后续接入 RAG 或其他文本处理流程。

## 功能概览

- 账号免登录：通过 `ipLogin` 接口建立会话、获取年份列表；
- GUI 浏览：在界面中按 “年份 → 期刊 → 文章” 三级选择，查看文章正文与图片；
- 导出能力：
  - 单篇文章 Markdown；
  - 当前期刊所有文章 Markdown（每期一个文件）；
  - 当前年份所有期刊 Markdown；
  - 全部年份批量导出 Markdown；
- Markdown 内自动保留原站在线图片：例如 `![图注](http://szb.iziran.net/dataFile/...)`；
- 代码层面提供 `ChinaLandCrawler` 与 Markdown 工具函数，可独立复用。

**注意：全量导出（全部年份）可能因目标网站访问限制或网络不稳定而不可用，建议优先使用“导出所选年份”或“导出所选期刊”方式，分批进行，以确保稳定性。**

## 项目结构

```
CHINA LAND/
├── README.md              项目说明（当前文件）
├── requirements.txt       运行依赖（requests）
├── pyproject.toml         项目元信息，可用于构建 wheel/安装
├── run_gui.py             GUI 启动脚本（执行 python run_gui.py 即可）
└── china_land/            核心包
    ├── __init__.py        暴露统一入口与 __all__
    ├── client.py          网络请求封装（登录、年份/期刊/文章获取）
    ├── export.py          Markdown 渲染、HTML/图片解析工具
    └── gui.py             tkinter 图形界面
```

## 环境要求

- Python ≥ 3.10（已在 3.13/3.14 环境测试）
- 仅需第三方库：`requests`

## 安装与运行

1. 安装依赖：
   ```powershell
   python -m pip install -r requirements.txt
   ```
   若机器上存在多个 Python 版本，请使用与运行 GUI 相同的解释器执行。

2. 运行 GUI：
   ```powershell
   python run_gui.py
   ```
   首次点击 “登录 / 刷新” 会建立会话并加载年份列表，随后即可浏览与导出文章。

3. 导出结果：
   - 导出的 Markdown 文件按 “年 + 期” 命名，例如 `2025_第10期.md`；
   - 若需要导入 RAG，可直接读取 Markdown 中的 `![...]()` 行，或二次解析为结构化文本。

## 开发指南

- `china_land.client.ChinaLandCrawler`：提供同步接口，可在脚本中直接调用；
- `china_land.export.render_article` / `write_issue_markdown`：负责 HTML 清洗、Markdown 生成；
- `china_land.gui.main`：GUI 主入口，`run_gui.py` 仅做薄封装；
- 如需扩展功能（例如图片本地下载、JSONL 存储），可在 `export.py` 中新增相应工具函数；
- 项目已有基础 `pyproject.toml` 配置，执行 `python -m build` 可生成 wheel 进行分发。

## 免责声明

本工具仅用于学习与技术研究，请在符合目标网站的服务条款、robots 协议及相关法律法规的前提下使用，并控制访问频率，避免对对方服务器造成压力。

欢迎在此基础上扩展更多期刊/站点或接入更复杂的数据处理流程。祝使用愉快！
