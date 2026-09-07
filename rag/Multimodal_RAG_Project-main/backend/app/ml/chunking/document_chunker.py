from typing import List, Dict, Any
import re


class DocumentChunker:
      """
            Improved semantic-aware chunking with sentence - safe overlap.
      """

      def __init__(self, chunk_size: int = 300, chunk_overlap: int = 40):
            self.chunk_size = chunk_size
            self.chunk_overlap = chunk_overlap

      def chunk_text(self, text: str, metadata: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
            """Split text into overlapping chunks using simple regex + sliding window."""

            if not text or not text.strip():
                  return []

            # Clean and split into sentences/paragraphs
            text = re.sub(r'\s+', ' ', text).strip()
            sentences = re.split(r'(?<=[.!?])\s+', text)

            chunks: List[Dict[str, Any]] = []
            current_sentences: List[str] = []
            chunk_index = 0

            def word_count(s : str) -> int:
                  return len(s.split())

            current_length = 0
            max_words = self.chunk_size
            overlap_words = self.chunk_overlap

            for sentence in sentences:
                  sentence_words = word_count(sentence)

                  #IF ADDING SENTENCE EXCEEDS CHUNK SIZE -> FINALIZE CHUNK
                  if current_length + sentence_words > max_words and current_sentences:
                        chunk_text = " ".join(current_sentences).strip()

                        if word_count(chunk_text) > 20:
                              chunks.append({
                                    "content": chunk_text,
                                    "chunk_index": chunk_index,
                                    "chunk_type": "text",
                                    "metadata": metadata or {}
                              })
                              chunk_index += 1
                        
                        overlap_buffer = []
                        overlap_len = 0

                        #TAKE SENTENCE FROM END UNTIL OVERLAP WORDS ARE REACHED
                        for s in reversed(current_sentences):
                              overlap_buffer.insert(0, s)
                              overlap_len += word_count(s)
                              if overlap_len >= overlap_words:
                                    break
                        current_sentences = overlap_buffer.copy()
                        current_length += sum(word_count(s) for s in current_sentences)
                  
                  current_sentences.append(sentence)
                  current_length += sentence_words

            if current_sentences:
                  chunk_text = ' '.join(current_sentences).strip()
                  if word_count(chunk_text) > 20:
                              chunks.append({
                                    "content": chunk_text,
                                    "chunk_index": chunk_index,
                                    "chunk_type": "text",
                                    "metadata": metadata or {}
                              })
            
            return chunks
                  

            

      def chunk_image_description(self, description: str, image_path: str, metadata: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
            """Create single chunk for image with description."""
            if not description or not description.strip():
                  return []
            return [{
                  "content": description.strip(),
                  "chunk_index": 0,
                  "chunk_type": "image",
                  "metadata": {
                  **(metadata or {}),
                  "image_path": image_path
                  }
            }]