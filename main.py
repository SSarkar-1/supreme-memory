from langchain.agents import create_agent
from langchain.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
import psycopg2
from fastapi import FastAPI,Form,BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
import uvicorn
import os
from dotenv import load_dotenv
import requests
import csv
import io
import uuid
import json
load_dotenv()

app=FastAPI(title="AI Slack Bot")

# In-memory cache for last query results
last_query_cache = {}
# In-memory cache for CSV files
csv_cache = {}

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
            # Check if query is not supported
            is_unsupported = (len(columns) == 1 and columns[0] == "message" and 
                            "Query not supported:" in str(data[0].get("message", "")))
            
            # Format as markdown table
            header = "| " + " | ".join(columns) + " |"
            # separator = "| " + " | ".join(["---"] * len(columns)) + " |"
            rows = []
            for row in data:
                row_str = "| " + " | ".join([str(row[col]) for col in columns]) + " |"
                rows.append(row_str)
            response_text = "\n".join([header] + rows)
            
            if is_unsupported:
                # Don't create CSV for unsupported queries
                payload = {
                    "response_type": "in_channel",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"⚠️ Query Error:\n```{response_text}```"
                            }
                        }
                    ]
                }
            else:
                # Cache the query result
                cache_id = str(uuid.uuid4())
                last_query_cache[cache_id] = {
                    "data": data,
                    "columns": columns
                }
                
                # Create payload with button
                payload = {
                    "response_type": "in_channel",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"📊 Query result:\n```{response_text}```"
                            }
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "📥 Export as CSV"
                                    },
                                    "action_id": f"export_csv_{cache_id}",
                                    "value": cache_id
                                }
                            ]
                        }
                    ]
                }
        elif isinstance(data, list) and not data:
            response_text = "No data found for your query."
            payload = {
                "response_type": "in_channel",
                "text": response_text
            }
        else:
            payload = {
                "response_type": "in_channel",
                "text": str(data)
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

@app.post("/slack/interactive")
async def handle_slack_interaction(payload: str = Form(...)):
    """
    Handle Slack interactive button clicks
    Slack sends the payload as form-encoded data
    """
    try:
        # Parse the JSON payload from the form data
        payload_data = json.loads(payload)
        actions = payload_data.get("actions", [{}])
        action_id = actions[0].get("action_id", "")
        
        if action_id.startswith("export_csv_"):
            cache_id = action_id.split("export_csv_")[1]
            
            if cache_id in last_query_cache:
                cached = last_query_cache[cache_id]
                data = cached["data"]
                columns = cached["columns"]
                
                # Generate CSV in memory
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=columns)
                writer.writeheader()
                writer.writerows(data)
                csv_content = output.getvalue()
                
                # Store CSV in cache with unique ID
                csv_file_id = str(uuid.uuid4())
                csv_cache[csv_file_id] = {
                    "filename": f"query_results_{csv_file_id}.csv",
                    "content": csv_content
                }
                
                # Send message with download link
                response_url = payload_data.get("response_url")
                # Get the base URL from the request (you may need to set this as env variable)
                base_url = os.environ.get("BASE_URL")
                download_link = f"{base_url}/download-csv/{csv_file_id}"
                
                requests.post(response_url, json={
                    "response_type": "ephemeral",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"✅ CSV file ready with {len(data)} rows\n<{download_link}|📥 Download CSV>"
                            }
                        }
                    ]
                })
                
                # Clean up query cache
                del last_query_cache[cache_id]
                
                return {"ok": True}
            else:
                return {"ok": False, "error": "Cache expired"}
        
        return {"ok": False}
    except Exception as e:
        print(f"Error handling interaction: {str(e)}")
        return {"ok": False, "error": str(e)}

@app.get("/download-csv/{file_id}")
async def download_csv(file_id: str):
    """
    Download CSV file by ID
    """
    try:
        if file_id in csv_cache:
            csv_data = csv_cache[file_id]
            filename = csv_data["filename"]
            content = csv_data["content"]
            
            # Clean up cache
            del csv_cache[file_id]
            
            # Return CSV as downloadable file using StreamingResponse
            return StreamingResponse(
                iter([content]),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        else:
            return {"error": "File not found or already downloaded"}
    except Exception as e:
        print(f"Error downloading CSV: {str(e)}")
        return {"error": str(e)}

    
if __name__ == "__main__":
    # For production, use environment variable PORT (set by hosting platforms)
    port = int(os.environ.get("PORT", 8000))
    # Only enable reload in development
    reload = os.environ.get("ENVIRONMENT","development") == "development"
    uvicorn.run("main:app", host="127.0.0.1", port=port, reload=reload)