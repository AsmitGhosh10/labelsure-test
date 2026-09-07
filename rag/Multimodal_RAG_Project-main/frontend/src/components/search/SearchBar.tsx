import { useState } from "react";
import { Search } from "lucide-react";

interface SearchBarProps {
      onSearch: (query: string, useReranker: boolean) => void;
      loading: boolean;
}

export default function SearchBar({ onSearch, loading }: SearchBarProps) {
      const [query, setQuery] = useState("");
      const [useReranker, setUseReranker] = useState(false);

      return (
            <div className="space-y-4">
                  <div className="
                        flex
                        items-center
                        gap-4
                        rounded-3xl
                        border
                        border-border
                        bg-card/50
                        p-4
                        backdrop-blur
                        "
                  >

                        <Search className="h-5 w-5 text-muted"></Search>

                        <input 
                              type="text" 
                              placeholder="Search Anything"
                              value={query}
                              onChange={ (e) => setQuery(e.target.value) }
                              className="
                                    flex-1
                                    bg-transparent
                                    outline-none
                              "
                        />

                        <button 
                              disabled={ loading || !query.trim() }
                              onClick={ () =>  onSearch(query, useReranker) }
                              className="
                                    rounded-xl
                                    bg-primary
                                    px-5
                                    py-2
                                    text-sm
                                    font-medium
                                    transition-all
                                    hover:opacity-90
                                    disabled:opacity-50
                              "
                        >
                              Search
                       </button>
                  </div>

                  <label className="flex items-center gap-3 text-sm text-muted">
                        <input
                        type="checkbox"
                        checked={useReranker}
                        onChange={(e) =>
                              setUseReranker(e.target.checked)
                        }
                  />
                        Enable Cross-Encoder Reranker
                  </label>
            </div>
      );
}

