# React UI (replaces Streamlit for demos)

## Run the demo

Terminal 1 — API (Ollama must be running):

```bash
cd /path/to/data-analysis-report-generator
uv run uvicorn api_main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2 — React:

```bash
cd frontend
npm install
npm run dev
```

Open **http://127.0.0.1:5173**. Demo mode loads Sample Superstore automatically; click **Run analysis** (uses real `qwen3:4b` from `config.yaml`).

Streamlit remains at `uv run streamlit run app.py` until cutover.