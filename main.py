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
import time
import hashlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
load_dotenv()

# Use non-interactive backend for matplotlib in headless environment
import matplotlib
matplotlib.use('Agg')

app=FastAPI(title="AI Slack Bot")

# In-memory cache for last query results
last_query_cache = {}
# In-memory cache for CSV files
csv_cache = {}
# In-memory cache for chart images
chart_cache = {}
# TTL cache for LLM query results (300 seconds)
query_cache = {}
QUERY_CACHE_TTL = 300  # 5 minutes

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

1. Generate ONLY a single valid PostgreSQL SELECT query and DO NOT PUT SEMICOLON AT THE END.
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
SELECT 'Query not supported:{reason query not supported}' AS message;
If the Question asks to update,alter,delete,insert,drop,create data in the database, do not do thus and instead return short message
SELECT 'Query not supported:Database cannot be altered' AS message; '''

agent=create_agent(
    model="gpt-5-nano",
    system_prompt=system_prompt,
    )


def validate_user_input(text: str):
    """Basic filtering of user prompt to avoid SQL injection or malicious content.

    This runs before sending the message to the LLM. It flags obvious
    SQL keywords or semicolons which are not needed in natural language
    questions and could be used to manipulate the agent.
    """
    lowered = text.lower()
    forbidden = [';', 'drop ', 'delete ', 'insert ', 'update ', 'alter ', 'truncate ', 'create ']
    for token in forbidden:
        if token in lowered:
            raise ValueError("User input contains forbidden token: %s" % token.strip())
    return True

def get_response(user_message):
    # Check cache first
    question_hash = hashlib.md5(user_message.lower().strip().encode()).hexdigest()
    current_time = time.time()
    
    # Check if query is in cache and not expired
    if question_hash in query_cache:
        cached_entry = query_cache[question_hash]
        age = current_time - cached_entry["timestamp"]
        if age < QUERY_CACHE_TTL:
            print(f"Cache hit! Using cached result (age: {age:.1f}s)")
            return cached_entry["result"]
        else:
            # Cache expired, remove it
            del query_cache[question_hash]
    
    # basic user message validation
    try:
        validate_user_input(user_message)
    except ValueError as ve:
        return f"Input validation failed: {ve}", None

    # Cache miss or expired, proceed with LLM call
    question=HumanMessage(content=[
        {"type":"text","text": user_message }
        ])
    response=agent.invoke({"messages":[question]})
    agent_query=response['messages'][-1].content


    hostname = os.getenv("DB_HOST")
    database = os.getenv("DB_NAME")
    username = os.getenv("DB_USER")
    pwd = os.getenv("DB_PASSWORD")
    port_id = int(os.getenv("DB_PORT", 5432))
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
        
        # Cache the result
        result = (data, columns)
        query_cache[question_hash] = {
            "result": result,
            "timestamp": current_time
        }
        
        return result
    except Exception as error:
        return error, None
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def generate_and_upload_chart(data, columns, channel_id):
    """
    Generate a chart from data with date column and upload to Slack
    Returns the image URL for embedding in Slack message
    """
    try:
        # Find date column and numeric columns
        date_col = None
        numeric_cols = []
        
        for col in columns:
            if col.lower() == 'date':
                date_col = col
            # Check if column contains numeric data
            if all(isinstance(row.get(col), (int, float)) or row.get(col) is None for row in data):
                numeric_cols.append(col)
        
        if not date_col or not numeric_cols:
            return None
        
        # Prepare data for charting
        dates = []
        for row in data:
            date_val = row.get(date_col)
            if isinstance(date_val, str):
                try:
                    dates.append(datetime.strptime(date_val, '%Y-%m-%d'))
                except:
                    dates.append(date_val)
            else:
                dates.append(date_val)
        
        # Create figure with subplots if multiple numeric columns
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Plot each numeric column
        for col in numeric_cols[:3]:  # Limit to 3 columns for clarity
            values = [row.get(col, 0) for row in data]
            ax.plot(dates, values, marker='o', label=col, linewidth=2)
        
        ax.set_xlabel('Date', fontsize=12, fontweight='bold')
        ax.set_ylabel('Value', fontsize=12, fontweight='bold')
        ax.set_title('Query Results Over Time', fontsize=14, fontweight='bold')
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)
        
        # Format x-axis dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        
        # Save to BytesIO
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        plt.close(fig)
        
        # Store chart image in cache instead of uploading to Slack
        chart_id = str(uuid.uuid4())
        chart_cache[chart_id] = {
            "image_data": img_buffer.getvalue(),
            "filename": f"chart_{chart_id}.png"
        }
        
        # Get base URL from environment
        base_url = os.environ.get("BASE_URL", "http://localhost:8000")
        image_url = f"{base_url}/chart-image/{chart_id}"
        print(f"Chart generated and cached: {image_url}")
        return image_url
    except Exception as e:
        print(f"Chart generation failed: {str(e)}")
        return None


def process_query(text: str, response_url: str, channel_id: str = None):
    try:
        result = get_response(text)
        if isinstance(result, tuple) and len(result) == 2:
            data, columns = result
        else:
            # Error case
            data = result
            columns = None
        
        chart_image_url = None
        
        if columns and isinstance(data, list) and data:
            # Check if query is not supported
            is_unsupported = (len(columns) == 1 and columns[0] == "message" and 
                            "Query not supported:" in str(data[0].get("message", "")))
            
            # Check if date column exists and generate chart
            has_date_column = 'date' in columns
            if has_date_column and not is_unsupported and channel_id:
                try:
                    chart_image_url = generate_and_upload_chart(data, columns, channel_id)
                except Exception as chart_error:
                    print(f"Chart generation error: {str(chart_error)}")
                    # Continue without chart if generation fails
            
            total_rows = len(data)
            display_limit = 10
            
            # Prepare data for display (limit to 10 rows)
            display_data = data[:display_limit]
            
            # Format as markdown table for display
            header = "| " + " | ".join(columns) + " |"
            # separator = "| " + " | ".join(["---"] * len(columns)) + " |"
            rows = []
            for row in display_data:
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
                # Cache the query result (all rows for export)
                cache_id = str(uuid.uuid4())
                last_query_cache[cache_id] = {
                    "data": data,
                    "columns": columns
                }
                
                # Build blocks array
                blocks = []
                
                # Add row count info
                if total_rows > display_limit:
                    info_text = f"📊 Query result - Showing {display_limit} of {total_rows} rows"
                else:
                    info_text = f"📊 Query result - {total_rows} row(s)"
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": info_text
                    }
                })
                
                # Add chart if available
                if chart_image_url:
                    blocks.append({
                        "type": "image",
                        "image_url": chart_image_url,
                        "alt_text": "Query Result Chart"
                    })
                
                # Add table
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"```{response_text}```"
                    }
                })
                
                # Add note if rows are limited
                if total_rows > display_limit:
                    blocks.append({
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f" Showing first {display_limit} rows. Click 'Export as CSV' to download all {total_rows} rows."
                            }
                        ]
                    })
                
                # Add export button
                blocks.append({
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
                })
                
                # Create payload with button
                payload = {
                    "response_type": "in_channel",
                    "blocks": blocks
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
    background_tasks.add_task(process_query, text, response_url, channel_id)
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

@app.get("/chart-image/{chart_id}")
async def get_chart_image(chart_id: str):
    """
    Serve chart image by ID
    """
    try:
        if chart_id in chart_cache:
            chart_data = chart_cache[chart_id]
            image_data = chart_data["image_data"]
            filename = chart_data["filename"]
            
            # Don't delete - keep for Slack to download
            # Return image for embedding in Slack
            return StreamingResponse(
                iter([image_data]),
                media_type="image/png",
                headers={"Content-Disposition": f"inline; filename={filename}"}
            )
        else:
            return {"error": "Chart not found"}
    except Exception as e:
        print(f"Error serving chart: {str(e)}")
        return {"error": str(e)}

    
if __name__ == "__main__":
    # For production, use environment variable PORT (set by hosting platforms)
    port = int(os.environ.get("PORT", 8000))
    # Only enable reload in development
    reload = os.environ.get("ENVIRONMENT","development") == "development"
    uvicorn.run("main:app", host="127.0.0.1", port=port, reload=reload)