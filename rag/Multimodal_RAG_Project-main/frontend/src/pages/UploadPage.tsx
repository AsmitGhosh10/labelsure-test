import { useState } from "react";

import UploadDropzone from "../components/upload/UploadDropzone";
import UploadProgress from "../components/upload/UploadProgress";
import UploadResultCard from "../components/upload/UploadResultCard";
import { useUpload } from "../hooks/useUpload";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");

  const { upload, progress, isUploading, result, error } = useUpload();

  const handleUpload = async () => {
    if (!file) return;

    const isImage = file.type.startsWith("image/");

    await upload({
      title,
      file,
      type: isImage ? "image" : "file",
    });
  };

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-4xl flex-col gap-8 px-6 py-16">
      <div>
        <h1 className="text-5xl font-bold tracking-tight">
          Document Ingestion
        </h1>

        <p className="mt-3 text-muted">
          Upload documents and images into the multimodal retrieval system.
        </p>
      </div>

      <UploadDropzone onFileSelect={setFile}></UploadDropzone>

      {file && (
        <div className="rounded-2xl border border-border bg-card/40 p-6">
          <div className="space-y-4">
            <div>
              <p className="font-medium">{file.name}</p>

              <p className="text-sm text-muted">
                {(file.size / 1024 / 1024).toFixed(3)} MB
              </p>
            </div>

            <textarea
              placeholder="File title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="
                        min-h-[60px]
                        w-full
                        rounded-xl
                        border
                        border-border
                        bg-background/60
                        p-4
                        outline-none
            "
            ></textarea>

            <button
              onClick={handleUpload}
              disabled={isUploading}
              className="
                        rounded-xl
                        bg-primary
                        px-6
                        py-3
                        font-medium
                        transition-all
                        hover:opacity-90
                        disabled:opacity-50
            "
            >
              {isUploading ? "Uploading..." : "Start Ingestion"}
            </button>
          </div>
        </div>
      )}

      {isUploading && <UploadProgress progress={progress}></UploadProgress>}

      {error && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-400">
          {error}
        </div>
      )}

      {result && <UploadResultCard result={result}></UploadResultCard>}
    </div>
  );
}
