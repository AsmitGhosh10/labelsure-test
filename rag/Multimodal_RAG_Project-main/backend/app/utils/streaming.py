from typing import AsyncGenerator


async def stream_rag_response(answer: str, chunk_size:int = 50) -> AsyncGenerator[str, None]:
      """Simple Streaming  Response generator for RAG answers."""
      for i in range(0, len(answer), chunk_size):
            yield answer[i: i + chunk_size]