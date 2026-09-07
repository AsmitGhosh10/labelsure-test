interface RetrievalBadgeProps {
  type: string;
}

const badgeStyles: Record<string, string> = {
  faiss: "bg-violet-500/10 text-violet-300 border-violet-500/20",

  bm25: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20",

  clip: "bg-cyan-500/10 text-cyan-300 border-cyan-500/20",

  rrf: "bg-orange-500/10 text-orange-300 border-orange-500/20",
};

export default function RetrievalBadge({ type }: RetrievalBadgeProps) {
  return (
    <div
      className={`
                  rounded-full
                  border
                  px-3
                  py-1
                  text-sm
                  font-medium
                  capitalize
                  ${badgeStyles[type]}
            `}
    >
      {type}
    </div>
  );
}
