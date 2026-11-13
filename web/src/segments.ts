// YOUR TASK (pure function, no React): split `text` into plain and highlighted pieces.
// Spec, checked by components/__tests__/segments.test.ts:
//   - spans are [start, end) character offsets into text (end exclusive)
//   - spans may be unsorted, overlapping or touching: merge them
//   - spans may run past the text: clamp to [0, text.length]; drop empty spans
//   - joining all segment texts must give back exactly `text`
//   - no empty segments
// Hint: sort by start, merge into a list of non-overlapping ranges, then walk the text once.

export interface Segment {
  text: string;
  highlighted: boolean;
}

export function splitSegments(text: string, spans: [number, number][]): Segment[] {
  void spans; // remove when implemented
  return text ? [{ text, highlighted: false }] : [];
}
