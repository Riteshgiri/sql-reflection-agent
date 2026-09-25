"""
M2 Agentic AI - Improving SQL Generation with Reflection

Workflow:
  1) Extract the database schema
  2) Generate an initial SQL query (V1) from a natural-language question
  3) Execute V1
  4) Reflect on V1 using its execution output (external feedback) -> refined SQL (V2)
  5) Execute V2 -> final answer

Run:
  source venv/bin/activate
  python sql_reflection.py
"""

import json
import utils
import pandas as pd
from dotenv import load_dotenv

_ = load_dotenv()

import aisuite as ai

client = ai.Client()


def show(content, title=None):
    """Terminal replacement for utils.print_html (which only renders in Jupyter)."""
    if title:
        print(f"\n=== {title} ===")
    if isinstance(content, pd.DataFrame):
        print(content.to_markdown(index=False))
    else:
        print(content)


def strip_code_fences(text: str) -> str:
    """Remove ```json / ```sql fences that Claude often wraps around its answer."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()


# ---------------------------------------------------------------------------
# 3.1 Use an LLM to query a database (V1)
# ---------------------------------------------------------------------------
def generate_sql(question: str, schema: str, model: str) -> str:
    prompt = f"""
    You are a SQL assistant. Given the schema and the user's question, write a SQL query for SQLite.

    Schema:
    {schema}

    User question:
    {question}

    Respond with the SQL only.
    """
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# 3.2.1 First attempt: refine a SQL query (reviews the SQL text only)
# ---------------------------------------------------------------------------
def refine_sql(
    question: str,
    sql_query: str,
    schema: str,
    model: str,
) -> tuple[str, str]:
    """
    Reflect on whether a query's *shown output* answers the question,
    and propose an improved SQL if needed.
    Returns (feedback, refined_sql).
    """
    prompt = f"""
You are a SQL reviewer and refiner.

User asked:
{question}

Original SQL:
{sql_query}

Table Schema:
{schema}

Step 1: Briefly evaluate if the SQL OUTPUT fully answers the user's question.
Step 2: If improvement is needed, provide a refined SQL query for SQLite.
If the original SQL is already correct, return it unchanged.

Return STRICT JSON with two fields:
{{
  "feedback": "<1-3 sentences explaining the gap or confirming correctness>",
  "refined_sql": "<final SQL to run>"
}}
"""
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    content = response.choices[0].message.content
    try:
        obj = json.loads(strip_code_fences(content))
        feedback = str(obj.get("feedback", "")).strip()
        refined_sql = str(obj.get("refined_sql", sql_query)).strip()
        if not refined_sql:
            refined_sql = sql_query
    except Exception:
        # Fallback if model doesn't return valid JSON
        feedback = content.strip()
        refined_sql = sql_query

    return feedback, refined_sql


# ---------------------------------------------------------------------------
# 3.2.2 Final approach: refine a SQL query with external feedback
# ---------------------------------------------------------------------------
def refine_sql_external_feedback(
    question: str,
    sql_query: str,
    df_feedback: pd.DataFrame,
    schema: str,
    model: str,
) -> tuple[str, str]:
    """
    Evaluate whether the SQL result answers the user's question and,
    if necessary, propose a refined version of the query.
    Returns (feedback, refined_sql).
    """
    prompt = f"""
    You are a SQL reviewer and refiner.

    User asked:
    {question}

    Original SQL:
    {sql_query}

    SQL Output:
    {df_feedback.to_markdown(index=False)}

    Table Schema:
    {schema}

    Step 1: Briefly evaluate if the SQL output answers the user's question.
    Step 2: If the SQL could be improved, provide a refined SQL query.
    If the original SQL is already correct, return it unchanged.

    Return a strict JSON object with two fields:
    - "feedback": brief evaluation and suggestions
    - "refined_sql": the final SQL to run
    """

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=1.0,
    )

    content = response.choices[0].message.content
    try:
        obj = json.loads(strip_code_fences(content))
        feedback = str(obj.get("feedback", "")).strip()
        refined_sql = str(obj.get("refined_sql", sql_query)).strip()
        if not refined_sql:
            refined_sql = sql_query
    except Exception:
        # Fallback if the model does not return valid JSON:
        # use the raw content as feedback and keep the original SQL
        feedback = content.strip()
        refined_sql = sql_query

    return feedback, refined_sql


# ---------------------------------------------------------------------------
# 3.3 Putting it all together — the database query workflow
# ---------------------------------------------------------------------------
def run_sql_workflow(
    db_path: str,
    question: str,
    model_generation: str = "anthropic:claude-sonnet-4-6",
    model_evaluation: str = "anthropic:claude-sonnet-4-6",
):
    """
    End-to-end workflow to generate, execute, evaluate, and refine SQL queries.

    Steps:
      1) Extract database schema
      2) Generate SQL (V1)
      3) Execute V1 → show output
      4) Reflect on V1 with execution feedback → propose refined SQL (V2)
      5) Execute V2 → show final answer
    """

    # 1) Schema
    schema = utils.get_schema(db_path)
    show(schema, title="📘 Step 1 — Extract Database Schema")

    # 2) Generate SQL (V1)
    sql_v1 = generate_sql(question, schema, model_generation)
    show(sql_v1, title="🧠 Step 2 — Generate SQL (V1)")

    # 3) Execute V1
    df_v1 = utils.execute_sql(sql_v1, db_path)
    show(df_v1, title="🧪 Step 3 — Execute V1 (SQL Output)")

    # 4) Reflect on V1 with execution feedback → refine to V2
    feedback, sql_v2 = refine_sql_external_feedback(
        question=question,
        sql_query=sql_v1,
        df_feedback=df_v1,          # external feedback: real output of V1
        schema=schema,
        model=model_evaluation,
    )
    show(feedback, title="🧭 Step 4 — Reflect on V1 (Feedback)")
    show(sql_v2, title="🔁 Step 4 — Refined SQL (V2)")

    # 5) Execute V2
    df_v2 = utils.execute_sql(sql_v2, db_path)
    show(df_v2, title="✅ Step 5 — Execute V2 (Final Answer)")


# ---------------------------------------------------------------------------
# 3.4 Run the SQL workflow
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # 2.2 Set up the database (creates products.db with generated product data)
    utils.create_transactions_db()

    run_sql_workflow(
        "products.db",
        "Which color of product has the highest total sales?",
        model_generation="anthropic:claude-sonnet-4-6",   # lab default: "openai:gpt-4.1"
        model_evaluation="anthropic:claude-sonnet-4-6",   # lab default: "openai:gpt-4.1"
    )
