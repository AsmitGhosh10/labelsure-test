# Ingestion Pipeline Module

## Overview

The `IngestionPipeline` is responsible for converting processed document chunks into searchable vector and keyword indexes.

This module acts as the bridge between:

```plaintext
Raw Documents
        ↓
Chunking
        ↓
Embeddings
        ↓
Vector Indexes
        ↓
Searchable Knowledge Base
```

It is one of the core components of the Hybrid RAG architecture.

---

# File Location

```plaintext
app/
└── ml/
    └── pipelines/
        ├── ingestion_pipeline.py
        └── README.md
```

---

# Primary Responsibilities

The ingestion pipeline handles:

- Chunk ingestion
- Embedding generation
- FAISS indexing
- BM25 indexing
- Image embedding ingestion
- Batch processing
- Fault tolerance
- Incremental indexing

---

# High-Level Architecture

```plaintext
                ┌─────────────────┐
                │ DocumentChunker │
                └────────┬────────┘
                         ↓
                ┌─────────────────┐
                │IngestionPipeline│
                └────────┬────────┘
                         ↓
       ┌────────────────────────────────────────────────────────────┐
       │                                                            │
       ↓                                                            ↓
┌──────────────┐                                            ┌──────────────┐
│ TextEmbedder │                                            │ ImageEmbedder│
└──────┬───────┘                                            └──────┬───────┘
       │──────────────────────────┐                                │
       ↓                          ↓                                ↓
┌──────────────┐           ┌──────────────┐                 ┌──────────────┐
│ FAISSManager │           │ BM25Manager  │                 │ FAISSManager │
└──────────────┘           └──────────────┘                 └──────────────┘

```

---

# Supported Modalities

## Text Ingestion

Uses:

- SentenceTransformer embeddings
- BM25 sparse indexing
- FAISS dense vector indexing

---

## Image Ingestion

Uses:

- CLIP image embeddings
- FAISS image vector index

---

# Core Components

## 1. DocumentChunker

Responsible for:

- Splitting documents
- Overlap generation
- Semantic segmentation

---

## 2. TextEmbedder

Generates dense semantic embeddings.

Used for:

- FAISS semantic retrieval
- Dense vector search

---

## 3. ImageEmbedder

Uses CLIP to generate image embeddings.

Enables:

- Multimodal retrieval
- Text-to-image semantic search

---

## 4. FAISSManager

Handles:

- Dense vector indexing
- Similarity search
- Persistent storage

---

## 5. BM25Manager

Handles:

- Sparse keyword indexing
- Exact term matching
- Lexical retrieval

---

# Ingestion Flow

## Text Ingestion Pipeline

```plaintext
Document
    ↓
Chunking
    ↓
Text Embeddings
    ↓
FAISS Index
    ↓
BM25 Index
```

---

# Batch Processing Strategy

The pipeline uses batch ingestion:

```python
BATCH_SIZE = 32
```

Benefits:

- Lower memory usage
- Faster GPU utilization
- Better throughput
- Stable ingestion

---

# Text Embedding Workflow

```python
embeddings = await self.text_embedder.embed_text(batch_texts)
```

Generated embeddings are then:

```python
await self.faiss_manager.add_embeddings(...)
await self.bm25_manager.add_documents(...)
```

---

# Incremental FAISS Saving

Instead of saving after every vector insertion:

```python
save=False
```

The system performs:

```python
await self.faiss_manager.save_index("text")
```

after batching completes.

Benefits:

- Reduced disk I/O
- Faster ingestion
- Better scalability

---

# Image Ingestion Workflow

## Step 1 — Extract Paths

```python
img_path = chunk.get("metadata", {}).get("path")
```

---

## Step 2 — Generate CLIP Embeddings

```python
embeddings, valid_indices = await self.image_embedder.embed_image(batch_paths)
```

---

## Step 3 — Store in FAISS

```python
await self.faiss_manager.add_embeddings(
    embeddings=embeddings,
    chunk_ids=filtered_indices,
    index_type="image",
)
```

---

# Error Handling

The ingestion pipeline is fault tolerant.

Example:

```python
try:
    ...
except Exception as e:
    traceback.print_exc()
```

This prevents:

- Entire ingestion failure
- Corrupt indexing sessions
- Batch crashes

---

# Logging System

Uses structured logging via:

```python
import structlog
```

Example:

```python
logger.info(
    "Batch Processed",
    size=len(batch_texts),
    time=time.time() - start,
)
```

Benefits:

- Better observability
- Performance tracking
- Easier debugging

---

# Returned Statistics

Each ingestion operation returns:

```python
{
    "total_chunks": ...,
    "faiss_vectors": ...,
    "vectors_added": ...
}
```

These metrics help monitor:

- Index growth
- Ingestion performance
- Vector consistency

---

# Design Philosophy

The ingestion pipeline follows:

## DB-First Ingestion

Workflow:

```plaintext
Save chunks in DB
        ↓
Get real chunk IDs
        ↓
Generate embeddings
        ↓
Index vectors
```

This ensures:

- Stable references
- Consistent retrieval
- Easier synchronization

---

# Why Hybrid Indexing Matters

The system combines:

| Retrieval Type | Strength |
|---|---|
| FAISS | Semantic understanding |
| BM25 | Exact keyword matching |

This enables robust Hybrid RAG retrieval.

---

# Production-Oriented Features

## Async Processing

Uses:

```python
async/await
```

for scalable ingestion.

---

## Batch Optimization

Reduces:

- GPU overhead
- Memory spikes
- Disk operations

---

## Persistent Indexing

Indexes survive server restarts.

---

## Modular Architecture

Each subsystem is isolated:

- Chunking
- Embedding
- Vector storage
- Sparse indexing

---

# Future Improvements

Potential upgrades:

- Distributed ingestion
- Queue-based pipelines
- Streaming ingestion
- GPU batching
- Parallel embedding workers
- Async FAISS persistence
- Deduplication during ingestion
- Metadata-aware indexing

---

# Role in Hybrid RAG System

The ingestion pipeline is the foundation of retrieval quality.

Poor ingestion leads to:

- Weak embeddings
- Bad retrieval
- Poor reranking
- Hallucinated RAG responses

Good ingestion creates:

- High semantic precision
- Better hybrid recall
- Stronger reranking
- Better answer grounding

---

# Summary

The `IngestionPipeline` is the central indexing engine of the Hybrid RAG architecture.

It transforms processed chunks into:

- Dense semantic vectors
- Sparse keyword indexes
- Multimodal searchable representations

while maintaining:

- Scalability
- Fault tolerance
- Modularity
- Production readiness