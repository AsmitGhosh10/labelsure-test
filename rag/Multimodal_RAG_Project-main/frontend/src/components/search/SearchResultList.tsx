import SearchResultCard from "./SearchResultCard";
import { type SearchResult } from "../../types/search";

interface SearchResultListProps {
      results: SearchResult[];
}

export default function SearchResultList({ results }: SearchResultListProps) {
      return (
            <div className="space-y-6">
                  {results.map((result) => (
                        <SearchResultCard
                              key={result.chunk_id}
                              result={result}
                        ></SearchResultCard>

                  ))}
            </div>
      );
}