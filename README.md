# Statistical-Yearbook-DataFiller

Statistical-Yearbook-DataFiller is a traceable evidence collection and verification tool for filling or validating missing values in city/county-level statistical yearbook panels.

`Statistical-Yearbook-DataFiller` 不是“自动替代研究者判断”的填值器，而是一个面向城市/区县/县域面板数据研究的证据链助手：它为缺失值核验、补充和异常值复核生成可追溯、可复核、可引用的搜索证据。

## Positioning

在中国城市与县域面板数据研究中，统计年鉴常见的问题包括：

- 年份缺失或披露不连续
- 指标口径变化
- 行政区划调整
- 不同来源之间数值不一致
- 单位和量纲混乱

传统线性插值、均值填补、多重插补可以作为控制变量处理的辅助手段，但对于核心变量，审稿时往往需要更强的现实依据。这个项目的目标，是把“我为什么这样补这个值”变成一条可检查的证据链。

## What It Does

- 为缺失值自动构造更接近研究场景的查询语句
- 用浏览器自动化抓取搜索结果页文本
- 保留首个候选来源的标题、链接、域名和证据级别
- 从证据片段中提取数值候选、单位线索和冲突标记
- 输出可人工复核的 CSV，而不是直接覆盖原始数据

当前默认场景是 `rural_income`（农村居民人均可支配收入），但脚本结构已经按“证据采集与复核”设计，可以继续扩展到其他指标。

## Project Structure

项目现在不再是单一 `main.py` 脚本，而是一个可继续扩展的包：

```text
statistical_yearbook_datafiller/
├─ cli.py          # CLI 入口
├─ config.py       # 参数与运行配置
├─ constants.py    # 指标与输出字段常量
├─ scraping.py     # 浏览器抓取与搜索结果提取
├─ evidence.py     # 规则法证据解析、单位识别、候选值提取
├─ llm.py          # OpenAI-compatible LLM 分类层
└─ pipeline.py     # 主流程编排
```

这样拆分后，后续要做的扩展会更容易：

- 增加新的指标配置
- 增加新的搜索源
- 调整证据抽取规则
- 替换或升级 LLM 提示词
- 加入 PDF / 公报专用解析器

## Evidence Philosophy

项目默认将证据分成三个等级：

- `A`: 地方统计局、国家统计局、政府官网、官方统计公报
- `B`: 年鉴 PDF、政府报告、较权威二手数据库
- `C`: 搜索摘要、AI Overview、普通网页

`AI Overview` 只能作为入口或辅助线索，不能默认视为最终权威来源。

## Output Schema

运行后会生成 `evidence_review_output.csv`。核心字段包括：

- `search_query`: 实际执行的查询语句
- `search_url`: 对应搜索链接
- `fetch_status`: 抓取状态
- `evidence_text`: 用于人工复核的证据片段
- `source_title`, `source_url`, `source_domain`: 候选来源信息
- `source_type`, `evidence_level`: 来源分类与证据等级
- `value_candidates`: 从文本中提取的数值候选
- `suggested_fill_value`: 建议补充值
- `unit`, `unit_flag`: 单位识别结果与风险标记
- `metric_conflict_flag`: 指标口径冲突提示
- `confidence`: `high` / `medium` / `low`
- `need_manual_check`: 是否需要人工确认
- `manual_review_status`, `review_notes`: 复核状态与备注

这个输出表的设计目标，是让研究者保留原始数据，同时记录每个建议值背后的证据。

## Quick Start

### 1. Install

```bash
pip install pandas playwright playwright-stealth
playwright install chromium
```

也可以直接安装为本地命令行工具：

```bash
pip install -e .
```

### 2. Prepare input data

将输入 CSV 放在仓库目录，至少包含以下列：

- `year`
- `ent_county`
- `ent_code`
- `rural_income`

示例 `data.csv`：

```csv
year,ent_county,ent_code,rural_income
2021,曹县,371721,
2022,延安市宝塔区,610602,
2020,遂宁市安居区,510904,
```

### 3. First-time setup: resolve Google CAPTCHA

由于 Google 对自动化工具的反爬检测，首次运行需要手动解决一次 CAPTCHA。
只需做一次，之后永久复用。

```bash
python main.py --resolve-captcha
```

执行后浏览器会在**可见模式**弹出，你在浏览器中完成人机验证，然后关闭浏览器即可。
验证通过的 session 会自动保存到 `./browser_profile/`，后续不再需要重复验证。

> 如果你在中国大陆，需要配置代理才能访问 Google，见下方**代理配置**说明。

### 4. Run evidence collection

session 保存后，日常运行只需要一条命令：

```bash
python main.py --headless
```

或者：

```bash
sydf --headless
```

### Proxy configuration

如果你需要通过代理访问 Google（如在中国大陆使用 Clash/V2Ray 等）：

**方式一：环境变量（推荐）**

```bash
set HTTP_PROXY=http://127.0.0.1:7892
set HTTPS_PROXY=http://127.0.0.1:7892
python main.py --headless
```

**方式二：命令行参数**

```bash
python main.py --headless --proxy-ports 7892
```

多端口轮转：

```bash
python main.py --headless --proxy-ports 7890,7891,7892
```

> 默认端口为 `7892`，适合 Clash 混合端口。无需在代码中配置多个节点，由 Clash 面板管理节点切换。

### Common parameters

```bash
# 限制处理行数（调试用）
python main.py --headless --max-rows 10

# 指定输入/输出文件
python main.py --headless --input my_data.csv --output my_result.csv

# 只生成待复核表（不开浏览器）
python main.py --prepare-only

# 自定义浏览器 profile 路径
python main.py --headless --user-data-dir ./my_profile

# Session 过期后重新验证
python main.py --resolve-captcha --user-data-dir ./my_profile
```

### 5. Enable optional LLM classification

如果你希望对抓下来的内容再做一层结构化分类，可以配置兼容 OpenAI Chat Completions 的 API：

```bash
set LLM_API_BASE=https://api.openai.com/v1
set LLM_API_KEY=your_api_key
set LLM_MODEL=gpt-4.1-mini
python main.py --headless
```

也可以直接通过参数传入：

```bash
python main.py --headless ^
  --llm-api-base https://api.openai.com/v1 ^
  --llm-api-key your_api_key ^
  --llm-model gpt-4.1-mini
```

启用后，输出表会增加：

- `llm_provider`
- `llm_model`
- `llm_status`
- `llm_structured_output`

这层 LLM 主要用于：

- 来源类型分类
- 证据等级判断
- 候选值排序
- 单位与口径冲突标记
- 是否需要人工复核的建议

## Recommended Workflow

1. 保留原始数据文件
2. 用本工具生成证据复核表
3. 人工确认 `suggested_fill_value`、单位和来源
4. 仅在确认后回填到正式面板
5. 在论文或附录中说明补值规则和复核方式

## Limitations

- 当前抓取入口仍然依赖 Google 搜索结果页，不应把搜索摘要本身视为最终依据
- Google 对自动化工具有反爬检测，首次使用需通过 `--resolve-captcha` 手动验证一次，session 持久化后后续可完全无头运行
- 在中国大陆使用需要配置代理（见上方 Proxy configuration 章节）
- 当前数值提取是规则法（按文本顺序取第一个 ≥4 位数字），可能提取到年份而非数值，建议人工复核 `suggested_fill_value` 列
- 不建议直接将建议值自动写回核心解释变量或核心被解释变量
- 面向长期使用时，建议扩展为多模式检索：官方网页直连、PDF 解析、搜索 API

## Roadmap

- [x] 多指标配置（不再把指标写死在脚本里）
- [x] CAPTCHA 自动检测与恢复（playwright-stealth + 持久化 session）
- [x] 代理支持与端口轮转
- [ ] 官方来源优先抓取和页面级提取
- [ ] PDF / 统计公报解析
- [ ] 更细的 LLM 辅助字段抽取，但保留人工确认环节
- [ ] Excel 审核模板或轻量复核界面

## License

MIT
