import { scoreBadge } from "../api/client";

export default function ScoreBadge({ score }: { score: number | null | undefined }) {
  const level = scoreBadge(score);
  if (score == null) return <span className="badge badge-gray">—</span>;
  return <span className={`badge badge-${level}`}>{score}%</span>;
}
