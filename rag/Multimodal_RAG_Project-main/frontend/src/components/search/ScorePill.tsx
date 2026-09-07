interface ScorePillProps {
  label: string;
  value: number | null;
}

export default function ScorePill({ label, value }: ScorePillProps) {
  if (value == null) return null;

  return (
    <div className="rounded-xl bg-background/70 px-3 py-2">
      <p className="text-xs text-muted">{label}</p>

      <p className="mt-1 text-sm font-semibold">{value.toFixed(4)}</p>
    </div>
  );
}
