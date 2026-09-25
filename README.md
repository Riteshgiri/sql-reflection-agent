# SQL Reflection Agent

An agentic AI workflow that turns natural-language questions into SQL and uses the **reflection pattern with external feedback** to fix its own mistakes.

1. **Extract schema** from the SQLite database.
2. **Generate (V1)** — an LLM writes a SQL query for the question.
3. **Execute V1** against the database.
4. **Reflect** — the LLM reviews the question, the SQL, *and the actual query output*, then returns feedback plus a refined query.
5. **Execute V2** — the refined query produces the final answer.

Reviewing the query output is the key step: a query can look correct on paper but return wrong results.

## Example

**Question:** *Which color of product has the highest total sales?*

| | SQL | Result |
|---|---|---|
| V1 | `SUM(qty_delta * unit_price)` | blue, −190,571 ❌ |
| V2 | `SUM(ABS(qty_delta) * unit_price)` | white, 358,315 ✅ |

Sales are stored with negative `qty_delta`, so V1's totals were all negative. Sorting them descending also picked the lowest seller. The reflection step spotted the negative output and corrected the sign.

## Data

`utils.create_transactions_db()` builds `products.db` on each run: a single event-sourced `transactions` table (insert, restock, sale, price_update events) for 100 products. It uses a fixed random seed, so the data is the same every time.

## Setup

Requires Python 3.10+.

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file with your API key:

```
ANTHROPIC_API_KEY=...
```

## Run

```bash
python sql_reflection.py
```

To ask a different question, edit the question at the bottom of `sql_reflection.py`. Models are set there too (default `anthropic:claude-sonnet-4-6`). The workflow calls models through [aisuite](https://github.com/andrewyng/aisuite), so OpenAI models such as `openai:gpt-4.1` also work with an `OPENAI_API_KEY`.

## Files

| File | Purpose |
|---|---|
| `sql_reflection.py` | The end-to-end generate → execute → reflect → refine workflow |
| `utils.py` | Database creation, schema extraction, and SQL execution helpers |
| `requirements.txt` | Python dependencies |
