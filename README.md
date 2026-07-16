# SmartInspect Self-Optimizing Claims Agent

A FastAPI web app that inspects vehicle damage photos and answers coverage/repair
questions, combining image damage classification, VIN/label OCR, a RAG-grounded
knowledge base, and a policy/VIN registry lookup behind a small tool-calling agent.

## Requirements

- Python 3.12
- [Ollama](https://ollama.com) running locally, with these models pulled:

  ```bash
  ollama pull llama3.2:1b
  ollama pull qwen2.5:0.5b
  ollama pull qwen2.5:1.5b
  ```

## Install

```bash
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # macOS/Linux

pip install -r requirements.txt
```



## Run

Make sure Ollama is running (`ollama serve`), then start the app from the
`webapp` directory:

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 in a browser.

On first startup the app auto-builds the RAG vector index (`data/rag_index/`)
from the knowledge base docs in `data/rag/*.md` — no manual chunking step is
needed. It's cached after that; delete `data/rag_index/` to force a rebuild
(e.g. after editing the docs in `data/rag/`).
