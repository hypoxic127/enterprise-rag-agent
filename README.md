# 🚀 Enterprise RAG Agent Workflow

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)
![Next.js 15](https://img.shields.io/badge/Next.js-15-black)
![Gemini 2.5 Pro](https://img.shields.io/badge/LLM-Gemini_2.5_Pro-purple)
![Qdrant](https://img.shields.io/badge/VectorDB-Qdrant-red)

An advanced, production-ready Enterprise Retrieval-Augmented Generation (RAG) system powered by **Google Gemini 2.5 Pro**, **LlamaIndex**, and **Next.js**. This architecture introduces an autonomous `ReActAgent` capable of intelligent routing between local corporate knowledge bases and real-time internet research.

## ✨ Core Features

- 🧠 **Dual-Routing Agentic Workflow:** An advanced `ReActAgent` that intelligently routes queries between a local `Qdrant` vector database (for internal knowledge) and `Tavily` (for real-time web search).
- 🛡️ **Anti-Arrogance Prompting:** System-level prompt injection guarantees the LLM strictly prioritizes internal documents over its pre-trained parametric memory, overcoming "commonsense arrogance" (e.g., retrieving details about an unreleased internal product).
- 🔗 **Google Ecosystem Native:** Fully utilizes the Gemini API for both inference (`models/gemini-2.5-pro`) and dense vector embeddings (`models/gemini-embedding-001`), ensuring 768-dimensional consistency.
- ⚡ **Real-time SSE Streaming:** Provides a buttery-smooth typewriter effect by strictly filtering ReAct thought processes (`Thought:`, `Action:`) backend-side, delivering only the final parsed answer to the frontend.
- 🎨 **Premium UI/UX:** A stunning, responsive Next.js frontend built with TailwindCSS, featuring glassmorphism, dynamic auto-scrolling, distinct message bubbles, and full React-Markdown parsing.

---

## 🏗️ System Architecture

```mermaid
graph TD
    %% Styling
    classDef frontend fill:#000000,stroke:#3b82f6,stroke-width:2px,color:#fff
    classDef backend fill:#18181b,stroke:#a855f7,stroke-width:2px,color:#fff
    classDef agent fill:#27272a,stroke:#eab308,stroke-width:2px,color:#fff
    classDef tool fill:#1e1e1e,stroke:#10b981,stroke-width:2px,color:#fff
    classDef external fill:#f8fafc,stroke:#64748b,stroke-width:2px,color:#000

    User((User)) -->|Query| UI[Next.js App Router]
    UI:::frontend -- SSE Stream --> FastAPI[FastAPI Backend]
    FastAPI:::backend --> Router[ReAct Agent Workflow]
    Router:::agent -->|Thought Process| Intercept[SSE Interceptor & Filter]
    Intercept -->|Yields only 'Answer: '| UI
    
    Router -->|Decision: Local Doc?| LocalDocTool[Local Document Tool]
    LocalDocTool:::tool --> Qdrant[(Qdrant Vector DB)]
    Qdrant:::external --> GeminiEmbeddings[Gemini Embedding-001]
    
    Router -->|Decision: Web Search?| TavilyTool[Tavily Search Tool]
    TavilyTool:::tool --> TavilyAPI((Tavily API)):::external
    
    LocalDocTool --> LLM
    TavilyTool --> LLM
    LLM[Gemini 2.5 Pro]:::external --> Router
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Docker & Docker Compose
- Node.js 18+ (for frontend)
- Python 3.11+ (for local ingestion/debug)

### 2. Environment Configuration
Create a `.env` file in the root directory:
```env
GOOGLE_API_KEY=your_gemini_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
QDRANT_HOST=localhost
```

### 3. Start Backend & Database
Use Docker Compose to spin up the Qdrant Vector DB and the FastAPI backend:
```bash
docker-compose up -d
```
*(If running backend locally via Uvicorn for development: `uvicorn app.main:app --host 0.0.0.0 --port 8000`)*

### 4. Data Ingestion
Ingest internal documents into the Qdrant database using Gemini Embeddings:
```bash
python scripts/ingest_data.py
```

### 5. Start Frontend
Navigate to the `frontend` directory and start the Next.js app:
```bash
cd frontend
npm install
npm run dev
```

### 6. Experience the Agent
Open your browser and navigate to `http://localhost:3000`. Try asking:
- *"苹果最新的全息手机叫什么？卖多少钱？"* (Tests strict local document retrieval)
- *"今天吉隆坡的天气如何？"* (Tests Tavily web search fallback)

---
*Developed with Next.js, FastAPI, LlamaIndex, and ❤️*
