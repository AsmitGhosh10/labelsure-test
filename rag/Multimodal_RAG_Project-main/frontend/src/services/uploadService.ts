import { uploadApi } from "../api/uploadApi";
import { type UploadPayload } from "../types/upload";

export const uploadService = {
      async upload(
            payload: UploadPayload,
            onProgress?: (progress: number) => void
      ) {
            const formData = new FormData();
            formData.append("title", payload.title);

            if(payload.type === "image") {
                  formData.append("image", payload.file);

                  return uploadApi.uploadImage(formData, onProgress);
            }

            formData.append("file", payload.file);

            return uploadApi.uploadFile(formData, onProgress);
      },
};



