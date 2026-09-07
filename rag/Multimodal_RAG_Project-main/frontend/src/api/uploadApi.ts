import { apiClient } from "./client";
import { type UploadResponse } from "../types/upload";

export const uploadApi = {
  uploadFile: async (
    formData: FormData,
    onProgress?: (progress: number) => void
  ) => {
    const response = await apiClient.post<UploadResponse>(
      "/v2/upload/file",
      formData,
      {
        headers: {
          "Content-Type": "multipart/form-data",
        },

        onUploadProgress: (progressEvent) => {
          if (!progressEvent.total) return;

          const progress = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          );

          onProgress?.(progress);
        },
      }
    );

    return response.data;
  },

  uploadImage: async (
    formData: FormData,
    onProgress?: (progress: number) => void
  ) => {
    const response = await apiClient.post<UploadResponse>(
      "/v2/upload/image",
      formData,
      {
        headers: {
          "Content-Type": "multipart/form-data",
        },

        onUploadProgress: (progressEvent) => {
          if (!progressEvent.total) return;

          const progress = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          );

          onProgress?.(progress);
        },
      }
    );

    return response.data;
  },
};
