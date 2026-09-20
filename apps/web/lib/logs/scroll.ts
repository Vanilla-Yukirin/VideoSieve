interface ScrollPosition {
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
}

export function isNearScrollBottom(position: ScrollPosition, threshold = 32): boolean {
  const distance = position.scrollHeight - position.clientHeight - position.scrollTop;
  return distance <= threshold;
}
