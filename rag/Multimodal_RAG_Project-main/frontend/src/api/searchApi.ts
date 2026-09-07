import { apiClient } from "./client";
import { type SearchRequest, type SearchResult } from "../types/search";

export const searchApi = {
  async search(payload: SearchRequest) {
    const response = await apiClient.post<SearchResult[]>(
      "v1/search/search",
      payload
    );

    return response.data;
  },
};
