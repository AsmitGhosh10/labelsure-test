import { type UploadResponse } from "../../types/upload";

interface UploadResultCardProps {
      result: UploadResponse;
}

export default function UploadResultCard ({
      result,
}: UploadResultCardProps) {
      return (
            <div className="rounded-2xl border border-border bg-card/60 p-6 backdrop-blur">
                  <div className="space-y-4">
                        <div>
                              <h3 className="text-xl font-semibold">
                                    {result.title}
                              </h3>

                              <p className="text-sm text-green-400">
                                    {result.message}
                              </p>
                        </div>

                        <div className="grid grid-cols-2 gap-4 text-sm">
                              <div className="rounded-xl bg-background/60 p-4">
                                    <p className="text-muted">Chunks Created</p>

                                    <p className="mt-1 text-lg font-semibold">
                                          {result.chunks_created}
                                    </p>
                              </div>

                              <div className="rounded-xl bg-background/60 p-4">
                                    <p className="text-muted">Vectors Added</p>

                                    <p className="mt-1 text-lg font-semibold">
                                          {result.vectors_added}
                                    </p>
                              </div>

                              <div className="rounded-xl bg-background/60 p-4">
                                    <p className="text-muted">Total FAISS Vectors</p>

                                    <p className="mt-1 text-lg font-semibold">
                                          {result.faiss_vectors_total}
                                    </p>
                              </div>

                              <div className="rounded-xl bg-background/60 p-4">
                                    <p className="text-muted">Status</p>

                                    <p className="mt-1 text-lg font-semibold capitalize">
                                          {result.status}
                                    </p>
                              </div>
                              
                        </div>
                  </div>
            </div>
      )
}