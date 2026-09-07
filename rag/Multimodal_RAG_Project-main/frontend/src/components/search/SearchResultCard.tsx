import { useState } from "react";
import { motion } from "framer-motion";
import { ChevronDown } from "lucide-react";

import { type SearchResult } from "../../types/search";
import ScorePill from "./ScorePill";
import RetrievalBadge from "./RetrievalBadge";

interface SearchResultCardProps {
      result: SearchResult;
}

export default function SearchResultCard({ result }: SearchResultCardProps) {
      const [expanded, setExpanded] = useState(false);

      return (
            <motion.div 
                  initial = {{ opacity: 0, y: 20}}
                  animate = {{ opacity: 1, y: 0}}
                  className="rounded-3xl border border-border bg-card/50 p-6 backdrop-blur"
            >
                  <div className="space-y-5">
                        <div className="flex items-start justify-between gap-4">
                              <div>
                                    <h1 className="text-xl font-semibold">
                                          {result.title}
                                    </h1>

                                    <p className="mt-1 text-sm text-muted">
                                          {result.file_name}
                                    </p>
                              </div>

                              <div className="flex flex-wrap gap-2">
                                    {result.retrieval.retrievers_used.map(
                                          (retriever) => (
                                                <RetrievalBadge
                                                      key={retriever}
                                                      type={retriever}
                                                ></RetrievalBadge>
                                          )
                                    )}
                              </div>
                        </div>

                        <p className="leading-7 text-zinc-300">
                              {expanded ? result.content : `${result.content.slice(0, 300)}...`}
                        </p>

                        <button 
                              onClick={ () => 
                                    setExpanded(!expanded)
                              } 
                              className="
                                    flex 
                                    items-center
                                    text-sm
                                    gap-2
                                    text-primary
                              "
                        >
                              <ChevronDown 
                                    className={`h-4 w-4 transition-transform ${ 
                                          expanded ? "rotate-180" : "" 
                                    }`}
                              ></ChevronDown>

                              {expanded ? "Show less" : "Show more"}
                        </button>

                        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                              <ScorePill label="faiss" value={result.scores.faiss}></ScorePill>

                              <ScorePill label="bm25" value={result.scores.bm25}></ScorePill>

                              <ScorePill label="clip" value={result.scores.clip}></ScorePill>

                              <ScorePill label="rrf" value={result.scores.rrf}></ScorePill>
                        </div>

                        <div className="rounded-2xl bg-background/50 p-4">
                              <p className="mb-3 text-sm font-medium">
                                    Retrieval Ranking
                              </p>
                              
                              <div className="flex flex-wrap gap-3 text-sm text-muted">
                                    {Object.entries(
                                          result.retrieval.rank_positions
                                    ).map(([retriever, rank]) => (
                                          <div 
                                                key={retriever}
                                                className="
                                                rounded-xl 
                                                border 
                                                border-border 
                                                px-3 
                                                py-2"
                                          >
                                                {retriever.toUpperCase()} Rank: 
                                                {" "}
                                                #{rank}
                                          </div>
                                    ))}
                              </div>
                        </div>
                  </div>
            </motion.div>
      )
}