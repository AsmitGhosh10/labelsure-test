import { Link } from "react-router-dom";

export default function HomePage() {
  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="space-y-8 text-center">
        <div>
          <h1 className="text-6xl font-bold tracking-tight">
            Multimodal Hybrid RAG
          </h1>

          <p className="mt-4 text-lg text-muted">
            Semantic Search + Explainable AI Retrieval
          </p>
        </div>

        <Link
          to="/upload"
          className="
                                    inline-flex
                                    rounded-2xl
                                    bg-primary
                                    px-8
                                    py-4
                                    font-medium
                                    transition-all
                                    hover:scale-[1.02]
                                    hover:opacity-90
                              "
        >
          Start Uploading
        </Link>

        <Link
          to="/search"
          className="
                                    inline-flex
                                    rounded-2xl
                                    bg-primary
                                    px-8
                                    py-4
                                    font-medium
                                    transition-all
                                    hover:scale-[1.02]
                                    hover:opacity-90
                              "
        >
          Search 
        </Link>
      </div>
    </div>
  );
}
