# CIRA CDRP Decision Search Engine

Full-text boolean search across all publicly available Canadian Internet Registration Authority (CIRA) domain dispute decisions.

## What it does

Search 427 CIRA domain dispute decisions using boolean operators. Useful for legal research on Canadian domain name disputes.

## Search syntax

| Syntax | Example | What it does |
|--------|---------|--------------|
| Single word | `trademark` | Find decisions mentioning this word |
| Phrase | `"bad faith"` | Find exact phrase |
| AND | `trademark AND transfer` | Both terms must appear |
| OR | `complainant OR registrant` | Either term |
| NOT | `domain NOT parking` | Exclude a term |
| Prefix | `trade*` | Matches trademark, trade-mark, etc. |
| NEAR | `NEAR(domain complainant, 10)` | Terms within 10 words of each other |
| Group | `(trademark OR "trade-mark") AND "bad faith"` | Combine operators |

## Running locally

```
python3 search_server.py
```

Then open `http://localhost:8642` in your browser.

## Data

- 427 decisions indexed
- Decisions sourced from [CIRA's public website](https://www.cira.ca)
- 19 scanned PDFs processed via OCR
