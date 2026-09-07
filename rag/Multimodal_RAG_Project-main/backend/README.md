# 🚀 Multimodal Hybrid RAG System

A production-grade **Multimodal Semantic Search + Hybrid Retrieval-Augmented Generation (RAG)** backend built with:

- **FastAPI**
- **FAISS**
- **BM25**
- **Cross-Encoder Reranking**
- **CLIP Multimodal Embeddings**
- **Groq LLM**
- **Hybrid Retrieval**
- **Explainable Ranking**
- **Structured Logging**

This project is designed as a scalable, clean-architecture backend for:

- Semantic Search
- Hybrid Information Retrieval
- Multimodal Retrieval (Text + Image)
- Retrieval-Augmented Generation (RAG)
- Explainable AI Search Systems

---

# ✨ Features

## 🔎 Hybrid Retrieval System

Combines:

- Dense semantic retrieval (FAISS)
- Sparse keyword retrieval (BM25)
- CLIP image retrieval

using:

- Reciprocal Rank Fusion (RRF)
- Cross-Encoder reranking

---

## 🧠 Multimodal Support

Supports:

- Text document ingestion
- Image embedding ingestion
- CLIP-based image retrieval
- Cross-modal search

---

## ⚡ Production-Grade RAG Pipeline

Features:

- Hybrid context retrieval
- Adaptive web search fallback
- Groq-powered response generation
- Streaming responses
- Confidence scoring

---

## 📊 Explainability Layer

Provides:

- Individual retriever scores
- Fusion ranking details
- RRF contributions
- Retrieval traceability
- Ranking transparency

---

## 🏗️ Clean Architecture

Fully modular backend with separation between:

- APIs
- Services
- ML pipelines
- Retrieval systems
- Database layer
- Utilities

---

# 🧱 Tech Stack

| Category | Technology |
|---|---|
| Backend | FastAPI |
| Database | PostgreSQL |
| ORM | SQLAlchemy 2.0 Async |
| Vector Search | FAISS |
| Keyword Search | BM25 |
| Embeddings | Sentence Transformers |
| Multimodal | OpenAI CLIP |
| Reranking | Cross-Encoder |
| LLM | Groq |
| Logging | Structlog |
| Validation | Pydantic v2 |

---

# 📁 Project Structure

```plaintext
project-root/
├── app/
│   ├── api/
│   ├── core/
│   ├── db/
│   ├── ml/
│   ├── schemas/
│   ├── services/
│   └── utils/
│
├── data/
│   ├── indexes/
|   └── uploads/
│     
├── logs/
├── tests/
|
│
├── main.py
├── myproject.toml
└── README.md
```

---

# 🧠 System Architecture

```mermaid
flowchart TD

    USER[User Query]
        --> API[FastAPI API Layer]

    API --> SERVICE[Query/RAG Service]

    SERVICE --> HYBRID[Hybrid Retriever]

    HYBRID --> FAISS[Semantic Retrieval]
    HYBRID --> BM25[Keyword Retrieval]
    HYBRID --> CLIP[Image Retrieval]

    FAISS --> RRF[RRF Fusion]
    BM25 --> RRF
    CLIP --> RRF

    RRF --> RERANK[Cross Encoder Reranker]

    RERANK --> CONTEXT[Top Context Selection]

    CONTEXT --> LLM[Groq LLM]

    LLM --> RESPONSE[Final RAG Response]
```

---

# 🔄 Ingestion Pipeline

```mermaid
flowchart LR

    FILE[Uploaded File]
        --> EXTRACT[Text Extraction]

    EXTRACT --> CHUNK[Document Chunking]

    CHUNK --> EMBED[Embedding Generation]

    EMBED --> FAISS_STORE[FAISS Index]
    CHUNK --> BM25_STORE[BM25 Index]

    FILE --> IMAGE[Image Processing]
    IMAGE --> CLIP_EMBED[CLIP Embeddings]
    CLIP_EMBED --> IMAGE_INDEX[Image FAISS Index]
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

# 🧠 RAG Pipeline

```mermaid
flowchart TD

    QUERY[User Question]
        --> RETRIEVE[Hybrid Retrieval]

    RETRIEVE --> RERANK[Reranking]

    RERANK --> WEB[Adaptive Web Search]

    WEB --> CONTEXT[Context Construction]

    CONTEXT --> GROQ[Groq LLM]

    GROQ --> ANSWER[Generated Answer]
```

---

# 📊 Explainability Features

The system exposes detailed retrieval metadata including:

- FAISS similarity score
- BM25 keyword score
- CLIP similarity score
- RRF fusion score
- Retriever contribution
- Rank positions
- Reranker score

This makes retrieval transparent and debuggable.

---

# ⚡ Key Engineering Highlights

## ✅ Async-First Backend

- Async SQLAlchemy
- Async ingestion
- Async embedding generation
- Async streaming responses

---

## ✅ Structured Logging

Features:

- Colored console logs
- JSON file logs
- Request tracing
- Retrieval debugging
- Error observability

---

## ✅ Adaptive Retrieval Strategy

System dynamically decides whether to:

- use only internal retrieval
- trigger external web search
- merge web + internal retrieval

based on retrieval confidence.

---

## ✅ Multimodal Retrieval

Supports:

- text-to-text retrieval
- text-to-image retrieval
- image embedding search

using CLIP embeddings.

---

# 📦 Installation

## 1️⃣ Clone Repository

```bash
git clone <repository-url>
cd backend
```

---

## 2️⃣ Create Virtual Environment

```bash
python -m venv venv
```

Activate:

### Windows

```bash
venv\Scripts\activate
```

### Linux / Mac

```bash
source venv/bin/activate
```

---

## 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 4️⃣ Configure Environment Variables

Create `.env`

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost/dbname

GROQ_API_KEY=your_key
TAVILY_API_KEY=your_key

EMBEDDING_MODEL=all-MiniLM-L6-v2
CLIP_MODEL=openai/clip-vit-base-patch32
```

---

## 5️⃣ Run Server

```bash
uvicorn main:app --reload
```

---

# 📡 API Overview

| Endpoint | Description |
|---|---|
| `/upload` | Upload & Ingest documents/images |
| `/search` | Hybrid retrieval search |
| `/rag` | Full RAG generation |


---

# 📂 Supported Inputs

| Type | Supported |
|---|---|
| TXT | ✅ |
| PDF | ✅ |
| DOCX | ✅ |
| Images | ✅ |

---

# 🎯 Current Capabilities

## Retrieval

- Dense semantic retrieval
- Sparse keyword retrieval
- Hybrid retrieval
- Image retrieval
- RRF fusion
- Cross-encoder reranking

---

## RAG

- Context retrieval
- Adaptive web search
- LLM generation
- Confidence estimation
- Streaming output

---

# 🚧 Future Improvements

Planned enhancements:

- Query expansion
- Agentic retrieval
- Multi-vector indexing
- Metadata filtering
- Distributed vector search
- Evaluation benchmark suite
- GPU FAISS acceleration
- Hybrid score calibration
- Advanced reranking strategies

---

# 📈 Why This Project Matters

Traditional RAG systems often fail because:

- semantic retrieval alone misses exact matches
- keyword retrieval alone misses meaning
- rankings are opaque
- image retrieval is unsupported

This system solves those problems through:

- hybrid retrieval
- explainable ranking
- multimodal support
- adaptive retrieval strategies

---

# 🛠️ Engineering Goals

This backend was built with emphasis on:

- Scalability
- Modularity
- Explainability
- Production readiness
- Retrieval quality
- Clean architecture
- Maintainability

---

# 👨‍💻 Author Notes

This project was built as:

- a production-style ML systems project
- a deep retrieval engineering exploration
- a scalable RAG backend architecture
- a multimodal information retrieval system

The focus was not only on "making RAG work", but on understanding:

- retrieval failures
- ranking quality
- fusion strategies
- reranking behavior
- explainability
- production engineering tradeoffs

---
