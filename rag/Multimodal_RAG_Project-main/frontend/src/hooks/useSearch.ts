import { useState } from "react";
import { searchService } from "../services/searchService";
import { type SearchRequest, type SearchResult } from "../types/search";

export function useSearch() {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = async (payload: SearchRequest) => {
    try {
      setIsLoading(true);
      setError(null);

      const response = await searchService.search(payload);

      setResults(response);

      return response;
    } catch (err: any) {
      setError(err?.response?.data?.detail?.[0]?.msg || "Search Failed");
    } finally {
      setIsLoading(false);
    }
  };

  return {
    search,
    results,
    isLoading,
    error,
  };
}
