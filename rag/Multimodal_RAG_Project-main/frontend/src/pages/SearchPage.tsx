import SearchBar from "../components/search/SearchBar";
import SearchResultList from "../components/search/SearchResultList";
import { useSearch } from "../hooks/useSearch";

export default function SearchPage() {
  const { search, results, isLoading, error } = useSearch();

  const handleSearch = async (query: string, useReranker: boolean) => {
    await search({ query, k: 5, use_reranker: useReranker });
  };

  return (
    <div className="mx-auto max-w-6xl space-y-10 px-6 py-14">
      <div>
        <h1 className="text-5xl font-bold tracking-tight">Hybrid Search</h1>

        <p className="mt-3 text-muted">
          Semantic + keyword retrieval with explainable ranking.
        </p>
      </div>

      <SearchBar onSearch={handleSearch} loading={isLoading} />

      {isLoading && (
        <div className="text-muted">Searching retrieval pipelines...</div>
      )}

      {error && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-400">
          {error}
        </div>
      )}

      {!isLoading && results.length > 0 && (
        <SearchResultList results={results} />
      )}
    </div>
    
  );
}
