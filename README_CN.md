<p align="right">
  <a href="README_CN.md"><strong>中文</strong></a> | <a href="README.md"><strong>English</strong></a>
</p>

<h1 align="center">Statistical-Yearbook-DataFiller</h1>

<p align="center">
  Traceable evidence collection and verification tool for filling or validating missing values in city/county-level statistical yearbook panels.
</p>

`Statistical-Yearbook-DataFiller` is not an "auto-fill" tool that replaces researcher judgment. It is an **evidence-chain assistant** for city/county-level panel data research: it generates traceable, verifiable, and citable search evidence for missing-value verification, supplementation, and outlier review.

---

## Positioning

In Chinese city and county panel data research, common statistical yearbook issues include:

- Missing years or inconsistent disclosure
- Changes in metric definitions over time
- Administrative boundary adjustments
- Numerical discrepancies between sources
- Confusing units and measurement scales

Traditional methods (linear interpolation, mean imputation, multiple imputation) can serve as auxiliary control-variable treatments. However, for core variables, reviewers often demand stronger empirical evidence. This project's goal is to turn "why I filled this value this way" into an inspectable evidence chain.

---

## What It Does

- Automatically constructs researcher-relevant search queries for missing values
- Uses browser automation to scrape search result page text
- Preserves the first candidate source's title, link, domain, and evidence level
- Extracts numeric candidates, unit clues, and conflict markers from evidence snippets
- Outputs a human-reviewable CSV rather than overwriting raw data

The default metric is `rural_income` (per capita disposable income of rural residents), but the architecture is designed for extension to other indicators.

---

## Project Structure

```text
statistical_yearbook_datafiller/
├─ cli.py          # CLI entry point
├─ config.py       # Parameter & runtime configuration
├─ constants.py    # Metric & output field constants
├─ scraping.py     # Browser automation & search extraction
├─ evidence.py     # Rule-based evidence parsing, unit detection, candidate extraction
├─ llm.py          # OpenAI-compatible LLM classification layer
└─ pipeline.py     # Main workflow orchestration
```

---

## Quick Start

### 1. Install

```bash
pip install pandas playwright playwright-stealth
playwright install chromium
```

Or install as a local CLI tool:

```bash
pip install -e .
```

### 2. Prepare input data

Place your input CSV in the project directory. It must include at least these columns:

- `year`
- `ent_county`
- `ent_code`
- `rural_income`

Example `data.csv`:

```csv
year,ent_county,ent_code,rural_income
2021,曹县,371721,
2022,延安市宝塔区,610602,
2020,遂宁市安居区,510904,
```

### 3. First-time setup: resolve Google CAPTCHA

Google has anti-bot detection for automated browsers. On the first run, you need to manually solve the CAPTCHA once. After that, the session is persisted for reuse.

```bash
python main.py --resolve-captcha
```

This opens the browser in **headed (visible) mode**. Complete the verification in the browser, then close the window. The verified session is saved to `./browser_profile/`.

> If you are in mainland China, you need to configure a proxy to access Google (see **Proxy Configuration** below).

### 4. Run evidence collection

After the session is saved, daily use is just one command:

```bash
python main.py --headless
```

Or:

```bash
sydf --headless
```

### Proxy Configuration

If you need a proxy to access Google (e.g., using Clash/V2Ray from mainland China):

**Option A: Environment variables (recommended)**

```bash
set HTTP_PROXY=http://127.0.0.1:7892
set HTTPS_PROXY=http://127.0.0.1:7892
python main.py --headless
```

**Option B: Command-line argument**

```bash
python main.py --headless --proxy-ports 7892
```

Multiple port rotation:

```bash
python main.py --headless --proxy-ports 7890,7891,7892
```

> The default port is `7892`, suitable for Clash mixed ports. Node switching is managed by your proxy client — no code changes needed.

### Common Parameters

```bash
# Limit rows (for testing)
python main.py --headless --max-rows 10

# Custom input/output files
python main.py --headless --input my_data.csv --output my_result.csv

# Generate review sheet only (no browser)
python main.py --prepare-only

# Custom browser profile path
python main.py --headless --user-data-dir ./my_profile

# Re-authenticate when session expires
python main.py --resolve-captcha --user-data-dir ./my_profile
```

### 5. Enable optional LLM classification

If you want LLM-based structural classification of scraped content, configure an OpenAI-compatible Chat Completions API:

```bash
set LLM_API_BASE=https://api.openai.com/v1
set LLM_API_KEY=your_api_key
set LLM_MODEL=gpt-4.1-mini
python main.py --headless
```

Or via command-line:

```bash
python main.py --headless ^
  --llm-api-base https://api.openai.com/v1 ^
  --llm-api-key your_api_key ^
  --llm-model gpt-4.1-mini
```

When enabled, the output table adds these columns:

- `llm_provider`
- `llm_model`
- `llm_status`
- `llm_structured_output`

The LLM layer is used for:

- Source type classification
- Evidence level judgment
- Candidate value ranking
- Unit & metric conflict detection
- Review necessity suggestions

---

## Evidence Philosophy

Evidence is classified into three levels:

- **A**: Local statistics bureau, National Bureau of Statistics, government websites, official statistical bulletins
- **B**: Yearbook PDFs, government reports, authoritative secondary databases
- **C**: Search snippets, AI Overviews, general web pages

AI Overviews should only serve as entry points or auxiliary clues, not as final authoritative sources.

---

## Output Schema

The tool generates `evidence_review_output.csv`. Key columns include:

- `search_query`: Actual query executed
- `search_url`: Corresponding search link
- `fetch_status`: Fetch status (success / failed / prepared_only)
- `evidence_text`: Evidence snippet for manual review
- `source_title`, `source_url`, `source_domain`: Candidate source info
- `source_type`, `evidence_level`: Source classification & evidence level
- `value_candidates`: Numeric candidates extracted from text
- `suggested_fill_value`: Suggested fill value
- `unit`, `unit_flag`: Unit detection result & risk marker
- `metric_conflict_flag`: Metric inconsistency alert
- `confidence`: high / medium / low
- `need_manual_check`: Whether manual review is needed
- `manual_review_status`, `review_notes`: Review status & notes

---

## Limitations

- The scraped data still depends on Google search result pages — search snippets should not be treated as final sources
- Google has anti-bot detection. First use requires `--resolve-captcha` for one-time manual verification; subsequent runs can be fully headless thanks to persistent sessions
- Users in mainland China need to configure a proxy (see Proxy Configuration above)
- Numeric extraction is rule-based (picks the first ≥4-digit number in text order), which may select the year instead of the actual value — always manually verify `suggested_fill_value`
- It is not recommended to automatically write suggested values back to core explanatory or dependent variables without manual review
- For long-term use, consider extending to multi-mode retrieval: direct official site access, PDF parsing, and search APIs

---

## Recommended Workflow

1. Keep the original data file
2. Use this tool to generate an evidence review table
3. Manually verify `suggested_fill_value`, units, and source
4. Backfill into the formal panel only after confirmation
5. Document the fill rules and review method in your paper or appendix

---

## Roadmap

- [x] Multi-metric configuration (metrics no longer hardcoded)
- [x] CAPTCHA auto-detection & recovery (playwright-stealth + persistent session)
- [x] Proxy support & port rotation
- [ ] Priority fetching from official sources & page-level extraction
- [ ] PDF / statistical bulletin parsing
- [ ] Finer-grained LLM-assisted field extraction (with manual review preserved)
- [ ] Excel review template or lightweight review UI

---

## License

MIT
