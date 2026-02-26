from langchain.agents import create_agent
from langchain.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
import psycopg2
from fastapi import FastAPI,Form,BackgroundTasks
from fastapi.responses import JSONResponse
import uvicorn
import os
from dotenv import load_dotenv
import requests
load_dotenv()

app=FastAPI(title="AI Slack Bot")
system_prompt='''You are a PostgreSQL SQL generator.
You have access to exactly ONE table:

Table name: sales_daily

Columns:
- date (DATE) — date of record
- region (TEXT) — region name
- category (TEXT) — product category
- revenue (NUMERIC(12,2)) — revenue amount
- orders (INTEGER) — number of orders
- created_at (TIMESTAMPTZ) — row creation timestamp

Instructions:

1. Generate ONLY a single valid PostgreSQL SELECT query.
2. Do NOT include explanations.
3. Do NOT include markdown formatting.
4. Do NOT include comments.
5. Do NOT include multiple queries.
6. NEVER use INSERT, UPDATE, DELETE, DROP, ALTER, or CREATE.
7. Only query the table: sales_daily.
8. Use correct PostgreSQL syntax.
9. When aggregation is requested, use proper GROUP BY.
10. When filtering by date, use single quotes: 'YYYY-MM-DD'.
11. If the question asks for totals, use SUM().
12. If the question asks for counts, use COUNT().
13. If sorting is implied (e.g., highest, lowest), use ORDER BY.
14. If limiting results makes sense, use LIMIT.

Return only the SQL statement.
If the question cannot be answered using this table, return  short message as to why query is not supported in the format:
SELECT 'Query not supported:{reason query not supported}' AS message;'''

agent=create_agent(
    model="gpt-5-nano",
    system_prompt=system_prompt,
    )

def get_response(user_message):
    question=HumanMessage(content=[
        {"type":"text","text": user_message }
        ])
    response=agent.invoke({"messages":[question]})
    agent_query=response['messages'][-1].content


    hostname='localhost'
    database='analytics'
    username='postgres'
    pwd='ss29320#'
    port_id=5432
    conn=None
    cur=None
    try:
        conn=psycopg2.connect(
            host=hostname,
            dbname=database,
            user=username,
            password=pwd,
            port=port_id
        )

        cur=conn.cursor()
        # query='SELECT * FROM sales_daily'
        cur.execute(agent_query)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        data = [dict(zip(columns, row)) for row in rows]
        print(data)
        return data, columns
    except Exception as error:
        return error, None
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def process_query(text: str, response_url: str):
    try:
        result = get_response(text)
        if isinstance(result, tuple) and len(result) == 2:
            data, columns = result
        else:
            # Error case
            data = result
            columns = None
        
        if columns and isinstance(data, list) and data:
            # Format as markdown table
            header = "| " + " | ".join(columns) + " |"
            # separator = "| " + " | ".join(["---"] * len(columns)) + " |"
            rows = []
            for row in data:
                row_str = "| " + " | ".join([str(row[col]) for col in columns]) + " |"
                rows.append(row_str)
            response_text = "\n".join([header] + rows)
        elif isinstance(data, list) and not data:
            response_text = "No data found for your query."
        else:
            response_text = str(data)
        
        payload = {
            "response_type": "in_channel",
            "text": f"📊 Query result:\n{response_text}"
        }
        requests.post(response_url, json=payload)
    except Exception as e:
        payload = {
            "response_type": "ephemeral",
            "text": f"Error processing query: {str(e)}"
        }
        requests.post(response_url, json=payload)

@app.post("/ask-data")
async def get_data(background_tasks: BackgroundTasks,text: str = Form(...),user_id: str = Form(...),channel_id: str = Form(...), response_url: str = Form(...)):
    background_tasks.add_task(process_query, text, response_url)
    return {
        "response_type": "ephemeral",
        "text": "Processing your query..."
    }

    
if __name__ == "__main__":
    # For production, use environment variable PORT (set by hosting platforms)
    port = int(os.environ.get("PORT", 8000))
    # Only enable reload in development
    reload = os.environ.get("ENVIRONMENT","development") == "development"
    uvicorn.run("main:app", host="127.0.0.1", port=port, reload=reload)