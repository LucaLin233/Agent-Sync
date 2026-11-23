export interface TaskFacts {
  id: string;
  workspaceId?: string | null;
  lastUserMessageAt?: string | null;
  background?: boolean;
  labels?: Readonly<Record<string, string>>;
}

export interface FirstTaskFact extends TaskFacts {
  text: string;
  turnId: string | null;
  at: string;
}

/**
 * Orders real first tasks by their timeline timestamp. Creation order and an
 * empty earlier session never decide the winner; the earliest task wins, and
 * an exact tie is resolved by agent id for determinism.
 */
export function pickFirstTask(candidates: readonly FirstTaskFact[]): FirstTaskFact | null {
  const ordered = [...candidates].sort((left, right) => {
    const leftTime = Date.parse(left.at);
    const rightTime = Date.parse(right.at);
    if (Number.isFinite(leftTime) && Number.isFinite(rightTime) && leftTime !== rightTime) {
      return leftTime - rightTime;
    }
    return left.id.localeCompare(right.id);
  });
  return ordered[0] ?? null;
}
