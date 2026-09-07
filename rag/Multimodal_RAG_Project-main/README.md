# 🚀 Multimodal Hybrid RAG System

A production-grade **Multimodal Semantic Search + Hybrid Retrieval-Augmented Generation (RAG)** platform featuring:

* 🔎 Hybrid Retrieval (FAISS + BM25 + RRF)
* 🧠 Multimodal Search (Text + Image via CLIP)
* ⚡ Real-time RAG Chat Interface
* 🌐 Adaptive Web Search Fallback
* 📊 Explainable Retrieval & Ranking
* 🎨 Modern AI-first Frontend
* 🏗️ Clean Modular Architecture

Built as a scalable AI systems project focused on:

* Retrieval engineering
* Multimodal AI
* Explainable search systems
* Production-ready RAG pipelines
* Modern frontend UX

---

# ✨ Features

## 🔎 Hybrid Retrieval Engine

Combines multiple retrieval strategies:

* Dense semantic retrieval using FAISS
* Sparse keyword retrieval using BM25
* CLIP-based multimodal image retrieval

Fusion strategies include:

* Reciprocal Rank Fusion (RRF)
* Cross-Encoder reranking

---

## 🧠 Multimodal Support

Supports:

* TXT ingestion
* PDF ingestion
* DOCX ingestion
* Image ingestion
* Text-to-image retrieval
* Cross-modal search

Powered using:

* Sentence Transformers
* OpenAI CLIP embeddings

---

## 💬 AI RAG Assistant

Modern chat-based RAG interface with:

* Streaming AI responses
* Retrieved source panels
* Confidence scoring
* Adaptive web search fallback
* Context-aware generation

LLM generation powered by:

* Groq LLM APIs

---

## 📊 Retrieval Explainability

Every retrieval result exposes:

* FAISS similarity scores
* BM25 keyword scores
* CLIP similarity scores
* RRF fusion scores
* Retriever contributions
* Rank positions
* Reranker influence

Designed to make retrieval:

* transparent
* debuggable
* explainable

---

## 🎨 Modern Frontend UX

Frontend inspired by:

* ChatGPT
* Perplexity
* Linear
* Vercel

Features:

* Responsive layout
* Dark mode
* Glassmorphism-inspired UI
* Chat-style AI interface
* Expandable source panels
* Multimodal upload flow
* Smooth animations

---

# 🧱 Tech Stack

## Backend

| Category         | Technology            |
| ---------------- | --------------------- |
| Framework        | FastAPI               |
| ORM              | SQLAlchemy 2.0 Async  |
| Database         | PostgreSQL            |
| Vector Search    | FAISS                 |
| Sparse Retrieval | BM25                  |
| Embeddings       | Sentence Transformers |
| Multimodal       | OpenAI CLIP           |
| Reranking        | Cross-Encoder         |
| LLM              | Groq                  |
| Validation       | Pydantic v2           |
| Logging          | Structlog             |

---

## Frontend

| Category         | Technology      |
| ---------------- | --------------- |
| Framework        | React           |
| Build Tool       | Vite            |
| Styling          | Tailwind CSS v3 |
| Animations       | Framer Motion   |
| Icons            | Lucide React    |
| State Management | React Hooks     |
| HTTP Client      | Axios           |
| Language         | TypeScript      |

---

# 📁 Project Structure

```plaintext
project-root/
├── backend/
│   ├── app/
│   ├── data/
│   ├── logs/
│   ├── tests/
│   └── README.md
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── layouts/
│   │   ├── pages/
│   │   ├── services/
│   │   ├── store/
│   │   ├── types/
│   │   └── utils/
│   │
│   ├── public/
│   └── package.json
│
└── README.md
```

---

# 🧠 System Architecture

```mermaid
flowchart TD

    USER[User Query]
        --> FRONTEND[React Frontend]

    FRONTEND --> API[FastAPI API Layer]

    API --> SERVICE[Query/RAG Service]

    SERVICE --> HYBRID[Hybrid Retriever]

    HYBRID --> FAISS[Semantic Retrieval]
    HYBRID --> BM25[Keyword Retrieval]
    HYBRID --> CLIP[Image Retrieval]

    FAISS --> RRF[RRF Fusion]
    BM25 --> RRF
    CLIP --> RRF

    RRF --> RERANK[Cross Encoder Reranker]

    RERANK --> CONTEXT[Context Construction]

    CONTEXT --> LLM[Groq LLM]

    LLM --> RESPONSE[Streaming AI Response]

    RESPONSE --> FRONTEND
```

---

# 🔄 Ingestion Pipeline

```mermaid
flowchart LR

    FILE[Uploaded File/Image]
        --> EXTRACT[Text/Image Processing]

    EXTRACT --> CHUNK[Document Chunking]

    CHUNK --> EMBED[Embedding Generation]

    EMBED --> FAISS_STORE[FAISS Index]
    CHUNK --> BM25_STORE[BM25 Index]

    FILE --> CLIP[CLIP Embeddings]

    CLIP --> IMAGE_INDEX[Image Vector Index]
```

---

# 🔎 Retrieval Pipeline

```mermaid
flowchart TD

    QUERY[User Query]
        --> EMBEDDING[Text Embedding]

    QUERY --> BM25_SEARCH[BM25 Search]

    EMBEDDING --> FAISS_SEARCH[FAISS Search]

    QUERY --> CLIP_QUERY[CLIP Text Embedding]

    CLIP_QUERY --> IMAGE_SEARCH[Image Retrieval]

    FAISS_SEARCH --> FUSION[RRF Fusion]
    BM25_SEARCH --> FUSION
    IMAGE_SEARCH --> FUSION

    FUSION --> RERANK[Cross Encoder Reranker]

    RERANK --> RESULTS[Final Ranked Results]
```

---

# 💬 RAG Pipeline

```mermaid
flowchart TD

    QUERY[User Question]
        --> RETRIEVE[Hybrid Retrieval]

    RETRIEVE --> RERANK[Reranking]

    RERANK --> WEB[Adaptive Web Search]

    WEB --> CONTEXT[Context Construction]

    CONTEXT --> GROQ[Groq LLM]

    GROQ --> ANSWER[Generated AI Response]
```

---

# 📡 API Overview

| Endpoint         | Description                 |
| ---------------- | --------------------------- |
| `/upload/file`   | Upload and ingest documents |
| `/upload/image`  | Upload and ingest images    |
| `/search/search` | Hybrid semantic retrieval   |
| `/rag/rag`       | Full RAG generation         |

---

# 📂 Supported Inputs

| Type   | Supported |
| ------ | --------- |
| TXT    | ✅         |
| PDF    | ✅         |
| DOCX   | ✅         |
| Images | ✅         |

---

# 🎯 Current Capabilities

## Retrieval

* Dense semantic retrieval
* Sparse keyword retrieval
* Hybrid retrieval
* Multimodal retrieval
* RRF fusion
* Cross-encoder reranking

---

## RAG

* Context retrieval
* Adaptive web search fallback
* AI answer generation
* Confidence estimation
* Streaming-ready architecture

---

## Frontend

* AI chat interface
* Retrieval visualization
* Source panels
* Upload workflows
* Responsive UI
* Dark mode

---

# ⚡ Key Engineering Highlights

## ✅ Hybrid Retrieval Architecture

Designed to overcome limitations of:

* semantic-only retrieval
* keyword-only retrieval

using:

* dense + sparse fusion
* reranking
* adaptive retrieval strategies

---

## ✅ Explainable AI Retrieval

Provides transparent ranking information for:

* debugging
* evaluation
* retrieval inspection
* ranking analysis

---

## ✅ Modular Clean Architecture

Strict separation between:

* APIs
* services
* retrieval systems
* ML modules
* frontend UI
* business logic

---

## ✅ Async-First Backend

Features:

* Async SQLAlchemy
* Async ingestion
* Async retrieval
* Async RAG generation
* Streaming-ready responses

---

## ✅ Modern AI UX

Frontend focuses heavily on:

* usability
* interaction quality
* minimal clutter
* AI-native experience

---

# 📦 Installation

# 1️⃣ Clone Repository

```bash
git clone <repository-url>
cd project-root
```

---

# 2️⃣ Backend Setup

```bash
cd backend

python -m venv venv
```

Activate environment:

### Windows

```bash
venv\Scripts\activate
```

### Linux / Mac

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create `.env`

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost/dbname

GROQ_API_KEY=your_key
TAVILY_API_KEY=your_key

EMBEDDING_MODEL=all-MiniLM-L6-v2
CLIP_MODEL=openai/clip-vit-base-patch32
```

Run backend:

```bash
uvicorn main:app --reload
```

---

# 3️⃣ Frontend Setup

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Run frontend:

```bash
npm run dev
```

---

# 🌟 Why This Project Matters

Traditional RAG systems often struggle because:

* semantic retrieval misses exact keyword matches
* keyword retrieval misses contextual meaning
* rankings are opaque
* multimodal retrieval is unsupported
* retrieval quality is difficult to debug

This project addresses those challenges through:

* hybrid retrieval
* explainable ranking
* multimodal embeddings
* adaptive retrieval strategies
* reranking pipelines
* modern AI-first UX

---

# 🚧 Future Improvements

Planned enhancements:

* Query expansion
* MMR retrieval diversification
* Context compression
* Metadata filtering
* GPU FAISS acceleration
* Advanced reranking
* Retrieval evaluation suite
* Agentic workflows
* Real-time streaming tokens
* Vector database integration

---

# 🛠️ Engineering Goals

This system was built with emphasis on:

* Scalability
* Explainability
* Retrieval quality
* Production readiness
* Modularity
* Clean architecture
* AI system transparency

---

# 👨‍💻 Author Notes

This project was built as:

* a production-style AI systems project
* a retrieval engineering exploration
* a multimodal search system
* a scalable RAG platform
* a modern AI product prototype

The focus was not only on “making RAG work”, but on understanding:

* retrieval failures
* ranking behavior
* reranking quality
* retrieval fusion
* context engineering
* explainability
* AI UX design
* production engineering tradeoffs

---
