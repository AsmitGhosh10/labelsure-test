import { useRef } from "react";
import { UploadCloud } from "lucide-react";


interface UploadDropzoneProps {
      onFileSelect: (file: File) => void;
}

export default function UploadDropzone({
      onFileSelect,
}: UploadDropzoneProps) {
      const inputRef = useRef<HTMLInputElement | null>(null);

      const handleFile = (file?: File) => {
            if (!file) return;

            onFileSelect(file);
      };

      return (
            <div
                  onClick={() => inputRef.current?.click()}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                        e.preventDefault();
                        handleFile(e.dataTransfer.files[0]);
                  }}
                  className="
                        flex
                        cursor-pointer
                        flex-col
                        items-center
                        justify-center
                        rounded-3xl
                        border
                        border-dashed
                        border-border
                        bg-card/40
                        p-12
                        text-center
                        transition-all
                        hover:border-primary
                        hover:bg-card/70
                  "
            >
                  <UploadCloud className="mb-4 h-12 w-12 text-primary"></UploadCloud>

                  <h3 className="text-xl font-semibold">
                        Upload documents or Images
                  </h3>
                  
                  <p className="mt-2 text-sm text-muted">
                        Drag & Drop  or click to browse
                  </p>

                  <input 
                        ref={inputRef}
                        type="file" 
                        hidden
                        onChange={(e) => 
                              handleFile(e.target.files?.[0])
                        }
                  />
            </div>
      );
}