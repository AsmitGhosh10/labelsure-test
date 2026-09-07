import { useState } from "react";

import { uploadService } from "../services/uploadService";
import { type UploadPayload, type UploadResponse } from "../types/upload";

export function useUpload() {
  const [progress, setProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const upload = async (payload: UploadPayload) => {
    try {
      setIsUploading(true);
      setError(null);
      setProgress(0);

      const response = await uploadService.upload(payload, setProgress);

      setResult(response);

      return response;
    } catch (err: any) {
      setError(err?.response?.data?.detail?.[0]?.msg || "Upload Failed");
      console.log(err?.response?.data);
    } finally {
      setIsUploading(false);
    }
  };

  return {
    upload,
    progress,
    isUploading,
    result,
    error,
  };
}
