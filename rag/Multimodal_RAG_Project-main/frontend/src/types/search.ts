export interface SearchRequest {
      query: string;
      k: number;
      use_reranker: boolean;
}

export interface SearchScores {
      faiss: number | null;
      bm25: number | null;
      clip: number | null;
      rrf: number | null;
}

export interface RetrievalInfo {
      retrievers_used: string[];
      rank_positions: Record<string, number>;
}

export interface SearchResult {
      document_id: number;
      chunk_id: number;
      title: string;
      file_name: string;
      content: string;
      chunk_type: string;
      metadata: Record<string, any>;
      score: number;
      scores: SearchScores;
      retrieval: RetrievalInfo;
}