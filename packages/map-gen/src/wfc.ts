/**
 * Wave Function Collapse core implementation.
 *
 * Operates on "meta-tiles" — higher-level tile types that represent
 * functional areas (corridors, department interiors, walls, etc.).
 * Each meta-tile maps to actual tile IDs in the output TMJ.
 */

/** Seeded PRNG (mulberry32) for deterministic generation. */
export function createRng(seed: number): () => number {
  let s = seed | 0;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export type MetaTile = string;
export type AdjacencyRules = Map<MetaTile, Set<MetaTile>[]>;

export interface WFCOptions {
  width: number;
  height: number;
  rules: AdjacencyRules;
  allTiles: MetaTile[];
  seed?: number;
  maxRetries?: number;
}

interface Cell {
  collapsed: boolean;
  options: Set<MetaTile>;
}

export class WFCGrid {
  readonly width: number;
  readonly height: number;
  private cells: Cell[];
  private rules: AdjacencyRules;
  private allTiles: MetaTile[];
  private rng: () => number;
  private maxRetries: number;

  constructor(opts: WFCOptions) {
    this.width = opts.width;
    this.height = opts.height;
    this.rules = opts.rules;
    this.allTiles = opts.allTiles;
    this.rng = createRng(opts.seed ?? 42);
    this.maxRetries = opts.maxRetries ?? 10;
    this.cells = [];
    this.reset();
  }

  private reset(): void {
    this.cells = [];
    for (let i = 0; i < this.width * this.height; i++) {
      this.cells.push({
        collapsed: false,
        options: new Set(this.allTiles),
      });
    }
  }

  private idx(x: number, y: number): number {
    return y * this.width + x;
  }

  /** Get the 4 cardinal neighbors as [index, directionIndex] tuples. */
  private neighbors(x: number, y: number): [number, number][] {
    const result: [number, number][] = [];
    // 0=up, 1=right, 2=down, 3=left
    if (y > 0) result.push([this.idx(x, y - 1), 0]);
    if (x < this.width - 1) result.push([this.idx(x + 1, y), 1]);
    if (y < this.height - 1) result.push([this.idx(x, y + 1), 2]);
    if (x > 0) result.push([this.idx(x - 1, y), 3]);
    return result;
  }

  /** Find the cell with the lowest entropy (fewest options, not yet collapsed). */
  private observe(): number | null {
    let minEntropy = Infinity;
    const candidates: number[] = [];

    for (let i = 0; i < this.cells.length; i++) {
      const cell = this.cells[i];
      if (cell.collapsed) continue;
      if (cell.options.size < minEntropy) {
        minEntropy = cell.options.size;
        candidates.length = 0;
        candidates.push(i);
      } else if (cell.options.size === minEntropy) {
        candidates.push(i);
      }
    }

    if (candidates.length === 0) return null;
    return candidates[Math.floor(this.rng() * candidates.length)];
  }

  /** Collapse a cell to a single option. */
  private collapse(cellIdx: number): boolean {
    const cell = this.cells[cellIdx];
    if (cell.options.size === 0) return false;

    const options = Array.from(cell.options);
    const chosen = options[Math.floor(this.rng() * options.length)];
    cell.options = new Set([chosen]);
    cell.collapsed = true;
    return true;
  }

  /** Propagate constraints from a collapsed cell outward. */
  private propagate(startIdx: number): boolean {
    const stack: number[] = [startIdx];
    const visited = new Set<number>();

    while (stack.length > 0) {
      const current = stack.pop()!;
      if (visited.has(current)) continue;
      visited.add(current);

      const cx = current % this.width;
      const cy = Math.floor(current / this.width);

      for (const [neighborIdx, dir] of this.neighbors(cx, cy)) {
        const neighbor = this.cells[neighborIdx];
        if (neighbor.collapsed) continue;

        const oppositeDir = (dir + 2) % 4;
        const validOptions = new Set<MetaTile>();

        for (const nOption of neighbor.options) {
          // Check if nOption is compatible with any option in current cell
          const currentCell = this.cells[current];
          let compatible = false;
          for (const cOption of currentCell.options) {
            const allowed = this.rules.get(cOption)?.[dir];
            if (allowed?.has(nOption)) {
              compatible = true;
              break;
            }
          }
          if (compatible) {
            validOptions.add(nOption);
          }
        }

        if (validOptions.size < neighbor.options.size) {
          if (validOptions.size === 0) return false; // Contradiction
          neighbor.options = validOptions;
          stack.push(neighborIdx);
        }
      }
    }

    return true;
  }

  /**
   * Run WFC to completion with backtracking retries.
   * Returns the collapsed grid or null if convergence fails.
   */
  run(): MetaTile[][] | null {
    for (let retry = 0; retry < this.maxRetries; retry++) {
      if (retry > 0) {
        this.rng = createRng((retry + 1) * 7919 + (this.width * this.height));
        this.reset();
      }

      let success = true;
      while (true) {
        const cellIdx = this.observe();
        if (cellIdx === null) break; // All collapsed

        if (!this.collapse(cellIdx)) {
          success = false;
          break;
        }

        if (!this.propagate(cellIdx)) {
          success = false;
          break;
        }
      }

      if (success) {
        // Build result grid
        const result: MetaTile[][] = [];
        for (let y = 0; y < this.height; y++) {
          const row: MetaTile[] = [];
          for (let x = 0; x < this.width; x++) {
            const cell = this.cells[this.idx(x, y)];
            const options = Array.from(cell.options);
            row.push(options[0] ?? 'floor');
          }
          result.push(row);
        }
        return result;
      }
    }

    return null;
  }
}
