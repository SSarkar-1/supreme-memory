# Supreme Memory

An application that converts natural language questions into SQL using LangChain, executes the query against a PostgreSQL database, and sends the results back to a Slack channel.

## 🚀 Features

- **Natural Language to SQL**: Leverages LangChain to translate user questions into SQL queries.
- **Database Integration**: Executes generated queries against a PostgreSQL table.
- **Slack Notifications**: Sends formatted query results to a configured Slack workspace.
- **Extensible**: Designed for easy customization of database schemas and Slack workflows.
- **Query Guardrails**: Generated SQL is parsed with `pglast` to enforce a single `SELECT` on the `sales_daily` table; semicolons and references to other tables are rejected.
- **Prompt Validation**: User input is checked for obvious SQL keywords/characters before it's even sent to the LLM, preventing prompt‑injection attacks.

## 🛠️ Requirements

- Python 3.10 or later
- PostgreSQL database
- Slack workspace with a bot token
- `pglast` for SQL parsing

## ⚙️ Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/supreme-memory.git
   cd supreme-memory
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # or .\venv\Scripts\Activate.ps1 on Windows
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure environment variables (e.g., `.env` file):
   ```env
   DATABASE_URL=postgresql://user:password@localhost:5432/yourdb
   SLACK_BOT_TOKEN=xoxb-your-token
   SLACK_CHANNEL=#your-channel
   OPENAI_API_KEY=your-openai-key
   ```

## 🏃 Running the Application

```bash
python main.py
```

This script initializes the Slack listener and the natural language processing flow. It listens for incoming messages, translates them into SQL, and responds with query results.

## 🧪 Testing

A Jupyter notebook `test.ipynb` is included for exploratory testing of the LangChain and database logic. Open it with:

```bash
jupyter notebook test.ipynb
```

## 📁 Project Structure

```
LICENSE
main.py            # Entry point for various utilities and launcher
slack_bot.py       # Slack integration and query handling
requirements.txt   # Python dependencies
test.ipynb         # Notebook for experimenting with queries
```

## 📝 Contributing

Contributions are welcome! Please open issues or submit pull requests.

## 📄 License

This project is licensed under the MIT License. See `LICENSE` for details.


An application that converts natural language questions into SQL using LangChain, executes the query against a PostgreSQL database, and sends the results back to a Slack channel.

## 🚀 Features

- **Natural Language to SQL**: Leverages LangChain to translate user questions into SQL queries.
- **Database Integration**: Executes generated queries against a PostgreSQL table.
- **Slack Notifications**: Sends formatted query results to a configured Slack workspace.
- **Extensible**: Designed for easy customization of database schemas and Slack workflows.

## 🛠️ Requirements

- Python 3.10 or later
- PostgreSQL database
- Slack workspace with a bot token

## ⚙️ Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/supreme-memory.git
   cd supreme-memory
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # or .\venv\Scripts\Activate.ps1 on Windows
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure environment variables (e.g., `.env` file):
   ```env
   DATABASE_URL=postgresql://user:password@localhost:5432/yourdb
   SLACK_BOT_TOKEN=xoxb-your-token
   SLACK_CHANNEL=#your-channel
   OPENAI_API_KEY=your-openai-key
   ```
5. Cloudflare tunneling
    ```Run cloudflared tunnel --url http://localhost:(your_localhost 5000 or 3000 0r 8000) on CMD```

## 🏃 Running the Bot

```bash
python main.py
```

The bot will listen for incoming messages and respond to natural language queries by sending SQL-derived answers back to Slack.

## 🧪 Testing

A Jupyter notebook `test.ipynb` is included for exploratory testing of the LangChain and database logic. Open it with:

```bash
jupyter notebook test.ipynb
```

## 📁 Project Structure

```
LICENSE
main.py            # Entry point for various utilities
slack_bot.py        # Slack integration and query handling
requirements.txt    # Python dependencies
test.ipynb          # Notebook for experimenting with queries
```

## 📝 Contributing

Contributions are welcome! Please open issues or submit pull requests.

## 📄 License

This project is licensed under the MIT License. See `LICENSE` for details.

