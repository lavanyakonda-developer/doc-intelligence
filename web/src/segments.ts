// Split `text` into plain and highlighted pieces for <EvidenceText>.
// Spec (checked by components/__tests__/segments.test.ts):
//   - spans are [start, end) character offsets into text (end exclusive)
//   - spans may be unsorted, overlapping or touching: merge them
//   - spans may run past the text: clamp to [0, text.length]; drop empty spans
//   - joining all segment texts gives back exactly `text`; no empty segments
// Approach: "merge intervals". Clamp, sort by start, merge, then walk the text once.
// O(k log k) for k spans; the text is only sliced, never scanned character by character.

export interface Segment {
  text: string;
  highlighted: boolean;
}

type Range = [number, number];

export function splitSegments(text: string, spans: Range[]): Segment[] {
  // 1. Clamp into the text and drop empty spans (copies: never mutate the caller's arrays).
  const ranges = spans
    .map(([s, e]): Range => [Math.max(0, s), Math.min(text.length, e)])
    .filter(([s, e]) => e > s)
    .sort((a, b) => a[0] - b[0]);

  // 2. Merge. Sorted by start, a range overlaps or touches the previous merged one iff it
  //    starts at or before that one's end; touching ([1,3] + [3,5]) merges into one <mark>.
  const merged: Range[] = [];
  for (const [s, e] of ranges) {
    const last = merged.at(-1);
    if (last && s <= last[1]) last[1] = Math.max(last[1], e);
    else merged.push([s, e]);
  }

  // 3. Walk: plain gap before each range (if any), the range itself, then the tail.
  const out: Segment[] = [];
  let pos = 0;
  for (const [s, e] of merged) {
    if (s > pos) out.push({ text: text.slice(pos, s), highlighted: false });
    out.push({ text: text.slice(s, e), highlighted: true });
    pos = e;
  }
  if (pos < text.length) out.push({ text: text.slice(pos), highlighted: false });
  return out;
}
