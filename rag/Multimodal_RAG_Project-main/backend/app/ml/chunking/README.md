# Document Chunking Module

## Overview

The `DocumentChunker` is responsible for converting large raw documents into smaller, semantically meaningful chunks that can be efficiently indexed and retrieved inside the Hybrid RAG pipeline.

This module is a critical preprocessing stage because embedding models and retrieval systems perform significantly better when operating on focused semantic segments rather than entire documents.

The chunker supports:

- Semantic-aware text chunking
- Sliding window overlap
- Sentence-safe splitting
- Image description chunking
- Metadata preservation

---

# File Location

```plaintext
app/
└── ml/
    └── chunking/
        ├── document_chunker.py
        └── README.md
```

---

# Why Chunking is Important

Large documents create multiple problems in retrieval systems:

| Problem | Impact |
|---|---|
| Embedding entire document | Poor semantic focus |
| Token limits | Model truncation |
| Retrieval noise | Irrelevant matches |
| Context dilution | Weak RAG answers |

Chunking solves this by:

- Preserving semantic locality
- Improving embedding quality
- Increasing retrieval precision
- Enabling fine-grained ranking

---

# Chunking Strategy Used

The project uses a:

## Semantic-Aware Sliding Window Chunking Strategy

### Core Characteristics

- Splits based on sentence boundaries
- Maintains semantic continuity
- Uses overlap to preserve context flow
- Avoids abrupt chunk cuts

---

# Architecture

```plaintext
Raw Document
      ↓
Text Cleaning
      ↓
Sentence Segmentation
      ↓
Sliding Window Builder
      ↓
Overlap Preservation
      ↓
Structured Chunks
```

---

# Text Chunking Workflow

## Step 1 — Clean Text

The text is normalized using regex:

```python
text = re.sub(r'\s+', ' ', text).strip()
```

This removes:

- Extra whitespace
- Multiple newlines
- Formatting inconsistencies

---

## Step 2 — Sentence Segmentation

The document is split into sentences:

```python
sentences = re.split(r'(?<=[.!?])\s+', text)
```

This ensures:

- Chunks do not cut sentences mid-way
- Semantic flow remains intact

---

## Step 3 — Sliding Window Construction

Sentences are accumulated until:

```python
current_length + sentence_words > max_words
```

When the chunk limit is exceeded:

- Current chunk is finalized
- Overlap sentences are preserved
- New chunk begins

---

## Step 4 — Overlap Preservation

The overlap mechanism preserves semantic continuity.

Example:

```plaintext
Chunk 1:
Sentence A
Sentence B
Sentence C

Chunk 2:
Sentence C
Sentence D
Sentence E
```

This prevents:

- Information loss
- Broken context chains
- Retrieval fragmentation

---

# Chunk Structure

Each chunk is stored as:

```python
{
    "content": chunk_text,
    "chunk_index": chunk_index,
    "chunk_type": "text",
    "metadata": metadata or {}
}
```

---

# Chunk Parameters

## Default Configuration

```python
chunk_size = 300
chunk_overlap = 40
```

| Parameter | Meaning |
|---|---|
| `chunk_size` | Maximum words per chunk |
| `chunk_overlap` | Overlapping words between chunks |

---

# Image Chunking

The module also supports image ingestion.

Instead of splitting images, the system creates a single semantic chunk:

```python
{
    "content": description,
    "chunk_type": "image",
    "metadata": {
        "image_path": image_path
    }
}
```

This allows:

- CLIP embeddings
- Image-text retrieval
- Multimodal search

---

# Why Sentence-Safe Chunking Matters

Bad chunking example:

```plaintext
"The Eiffel Tower is located in"

[next chunk]

"Paris and was built in 1889."
```

Good chunking example:

```plaintext
"The Eiffel Tower is located in Paris and was built in 1889."
```

Sentence-safe chunking significantly improves:

- Embedding quality
- Semantic retrieval
- Reranker performance
- RAG generation quality

---

# Advantages of This Approach

## Lightweight

- No heavy NLP dependency
- Fast preprocessing
- Efficient memory usage

## Retrieval Friendly

- Optimized for FAISS
- Optimized for BM25
- Better semantic density

## Production Friendly

- Deterministic behavior
- Easy debugging
- Easy customization

---

# Current Limitations

## Regex-based sentence splitting

May fail on:

- Abbreviations
- Scientific text
- Complex punctuation

Example:

```plaintext
Dr. Smith went home.
```

Could split incorrectly.

---

# Future Improvements

Potential future upgrades:

- spaCy sentence tokenizer
- Recursive chunking
- Markdown-aware chunking
- Table-aware chunking
- Adaptive chunk sizing
- Token-based chunking
- Semantic boundary detection

---

# Integration in Pipeline

The chunker is used during ingestion:

```plaintext
Document Upload
      ↓
Chunking
      ↓
Embedding Generation
      ↓
FAISS Indexing
      ↓
BM25 Indexing
```

---

# Role in Hybrid RAG System

The chunker directly impacts:

| Component | Effect |
|---|---|
| FAISS Retrieval | Better semantic vectors |
| BM25 Retrieval | Better keyword locality |
| Hybrid Fusion | More relevant candidates |
| Cross-Encoder | Better reranking |
| RAG Output | More accurate answers |

---

# Summary

The `DocumentChunker` forms the semantic foundation of the retrieval pipeline.

It transforms raw documents into optimized retrieval units that improve:

- Embedding quality
- Retrieval accuracy
- Ranking precision
- Final RAG response quality

This module is intentionally lightweight, modular, and production-oriented for scalable Hybrid RAG systems.