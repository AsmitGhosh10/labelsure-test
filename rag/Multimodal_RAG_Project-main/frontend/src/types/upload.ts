export interface UploadResponse{
      document_id: string;
      title: string;
      status: string;
      chunks_created: number;
      faiss_vectors_total: number;
      vectors_added:number;
      message: string
}

export interface UploadPayload {
      title: string;
      file: File;
      type: "file" | "image";
}