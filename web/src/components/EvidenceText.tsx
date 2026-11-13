import { splitSegments } from "../segments";

// YOUR TASK. Spec (tests: __tests__/EvidenceText.test.tsx):
//   - render the contract text with the spans wrapped in <mark> (use splitSegments)
//   - keep line breaks (CSS white-space: pre-wrap is already set on .evidence-text)
//   - when spans change and there is at least one, scroll the first <mark> into view
//     (useRef + useEffect; call scrollIntoView?.({ block: "center" }) — the ?. matters:
//     jsdom in tests has no scrollIntoView)
//   - with no spans, show the text without any <mark>
// Hint: a 100k-character contract is fine to render as a few hundred text nodes.

interface Props {
  text: string;
  spans: [number, number][];
}

export default function EvidenceText({ text, spans }: Props) {
  void splitSegments;
  void spans;
  return <article className="evidence-text">{text}</article>;
}
