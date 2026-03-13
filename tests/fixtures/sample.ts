/**
 * Sample TypeScript file with documented complexity values for testing.
 */

// add: cognitive=0, cyclomatic=1, params=2
function add(a: number, b: number): number {
    return a + b;
}

// nestedIfs: cognitive=6 (1 + 2 + 3), cyclomatic=4, max_nesting=3
function nestedIfs(x: number, y: number, z: number): boolean {
    if (x > 0) {           // +1 (nesting=0)
        if (y > 0) {       // +2 (1 + nesting=1)
            if (z > 0) {   // +3 (1 + nesting=2)
                return true;
            }
        }
    }
    return false;
}

// findItem: cognitive=4 (1 + 2 + 1), cyclomatic=3
function findItem(items: number[], target: number): number {
    for (let i = 0; i < items.length; i++) {  // +1 (nesting=0)
        if (items[i] === target) {             // +2 (1 + nesting=1)
            break;                             // +1
        }
    }
    return -1;
}

// validate: cognitive=2 (1 + 1), cyclomatic=3
function validate(a: boolean, b: boolean): boolean {
    if (a && b) {  // +1 (if) + 1 (&&)
        return true;
    }
    return false;
}

// elseIfChain: cognitive=3 (1 + 1 + 1, flat), max_nesting=1
function elseIfChain(x: number): string {
    if (x < 0) {
        return "negative";
    } else if (x === 0) {
        return "zero";
    } else if (x < 10) {
        return "small";
    } else {
        return "large";
    }
}

// withArrow: cognitive=2, max_nesting=2
function withArrow(items: number[]): void {
    items.forEach((item: number) => {  // arrow: nesting+1
        if (item > 0) {                // +1 + nesting=1 = +2
            console.log(item);
        }
    });
}

// tryCatch: cognitive=2 (1 for if + 1 for catch)
function tryCatch(s: string | null): void {
    try {
        if (s === null) {   // +1 (nesting=0)
            return;
        }
    } catch (e: unknown) {  // +1 (nesting=0)
        console.error(e);
    }
}

// Interface — should not produce any function metrics
interface Shape {
    area(): number;
    perimeter(): number;
}

// Type alias — should not produce any function metrics
type Result<T> = { ok: true; value: T } | { ok: false; error: string };

// Enum — should not produce any function metrics
enum Color {
    Red,
    Green,
    Blue,
}
