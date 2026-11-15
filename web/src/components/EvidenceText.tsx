import { useEffect, useRef } from "react";
import { splitSegments } from "../segments";

// The contract text with the selected field's evidence wrapped in <mark>.
// Line breaks are kept by CSS (white-space: pre-wrap on .evidence-text).

interface Props {
  text: string;
  spans: [number, number][];
}

export default function EvidenceText({ text, spans }: Props) {
  const firstMark = useRef<HTMLElement | null>(null);

  // Runs after render, when the new <mark> exists. `?.()`: jsdom has no scrollIntoView.
  useEffect(() => {
    if (spans.length > 0) firstMark.current?.scrollIntoView?.({ block: "center" });
  }, [spans]);

  const segments = splitSegments(text, spans);
  const firstIdx = segments.findIndex((s) => s.highlighted);
  return (
    <article className="evidence-text" aria-label="Contract text">
      {segments.map((s, i) =>
        s.highlighted ? (
          <mark key={i} ref={i === firstIdx ? firstMark : undefined}>
            {s.text}
          </mark>
        ) : (
          <span key={i}>{s.text}</span>
        ),
      )}
    </article>
  );
}
