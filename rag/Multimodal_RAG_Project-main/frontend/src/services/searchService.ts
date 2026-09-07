import { searchApi } from "../api/searchApi";
import { type SearchRequest, type SearchResult } from "../types/search";

export const searchService = {
  async search(payload: SearchRequest): Promise<SearchResult[]> {
    return searchApi.search(payload);
  },
};
