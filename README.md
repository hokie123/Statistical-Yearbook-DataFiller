# Statistical-Yearbook-DataFiller (统计年鉴数据填补器)

A data augmentation tool designed for empirical researchers to extract evidence and cross-verify or fill missing values in statistical yearbooks using Google AI Overviews.

专为实证学术研究打造的统计年鉴数据缺失填补工具。通过自动化检索 Google AI Overview 及官方统计公报，构建“可溯源、高可信度”的宏观经济指标文本证据链。

---

## 📌 项目背景 (Background)

在经济学、社会学、区域科学以及城市规划等领域的实证研究中，宏观面板数据（如各级统计年鉴、县志中的区县经济指标）经常存在不同程度的结构性缺失。传统的统计学填补方法（如线性插值、均值填补、多重插补法）在面对政策突发冲击或年份宏观经济大幅波动时，往往由于缺乏现实依据而导致填补值失真，难以说服论文评审专家。

本项目针对这一学术痛点，利用自动化技术动态构建精准的年鉴检索式（例如：`[年份]年 [区县/城市] 农村居民人均可支配收入`），模拟学者检索行为，深入挖掘 Google AI Overview 整合的内容以及官方公开的《国民经济和社会发展统计公报》等高可信度原始文本。通过提取并保存最原始的数字依据，为学术研究的数据回填提供坚实的“证据链（Evidence Chain）”。笔者在此抛砖引玉，欢迎各位学者拓展更多应用场景。

---

## 🚀 核心功能 (Features)

- **🔍 年鉴检索式动态构建**：根据输入的结构化表格，自动将年份、区县、目标指标合成为高命中率的学术检索 Query。
- **🛡️ 动态反爬机制集成**：基于 `Playwright` 异步架构，内置自动化特征擦除 (`AutomationControlled`)、随机延迟分布以及 User-Agent 伪装，稳定模拟人类正常的检索行为。
- **📄 证据链智能截取**：系统自动定位页面中含有 “AI 概览/AI Overview”、“统计公报”、“可支配收入” 的核心语境，抓取前后关联的上下文证据并保存。
- **💾 高强韧度断点续传**：数据保存机制置于核心循环内部，遇到网络中断或风控时，已爬取的数据会自动完好保存，适合大规模面板数据清洗。

---

## 🛠️ 快速上手 (Quick Start)

### 1. 安装依赖环境 (Installation)
本项目基于 Python 3.10+ 开发，利用 Playwright 驱动浏览器。请在终端执行以下命令安装依赖：

```bash
pip install pandas playwright
playwright install

### 2. 准备数据 (Data Setup)
在项目根目录下放置一个 data.csv 文件（本仓库已提供样例数据供参考）。确保数据表格中包含以下必需列：
year: 目标年份
ent_county: 地区/城市/区县名称
rural_income: 存在缺失值的目标指标列 (程序会自动识别其中的空值行并进行循证检索)

### 3. 启动程序 (Usage)

```bash
python main.py

程序运行后，会在当前目录下自动生成 experimental_group_google_evidence.csv。

### 输出结果说明 (Output)
运行成功后，系统会在表格中新增以下字段供人工复核或大模型提取：

google_query: 系统自动生成的年鉴检索词。

google_evidence_text: 截取到的核心证据块（包含 AI 概览内容与官方统计公报片段）。

google_fetch_status: 记录该行数据的提取状态（success 或 failed）。

## 🗺️ 未来路线图 (Roadmap)
[ ] LLM 结构化数据自动回填：未来计划接入 OpenAI 或 DeepSeek API，直接从提取到的文本片段中将纯数字解析出来，实现全自动无缝回填。

[ ] 多源 AI 搜索适配：增加对微软 Bing AI、百度等平台的检索适配。

## 📄 开源许可证 (License)
本项目采用 MIT License 协议开源。
