/**
 * Sample JavaScript file with documented complexity values for testing.
 */

// add: cognitive=0, cyclomatic=1, params=2
function add(a, b) {
    return a + b;
}

// nestedIfs: cognitive=6 (1 + 2 + 3), cyclomatic=4, max_nesting=3
function nestedIfs(x, y, z) {
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
function findItem(items, target) {
    for (let i = 0; i < items.length; i++) {  // +1 (nesting=0)
        if (items[i] === target) {             // +2 (1 + nesting=1)
            break;                             // +1
        }
    }
    return -1;
}

// validate: cognitive=2 (1 + 1), cyclomatic=3
function validate(a, b) {
    if (a && b) {  // +1 (if) + 1 (&&)
        return true;
    }
    return false;
}

// elseIfChain: cognitive=3 (1 + 1 + 1, flat), max_nesting=1
function elseIfChain(x) {
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
function withArrow(items) {
    items.forEach(item => {  // arrow: nesting+1
        if (item > 0) {      // +1 + nesting=1 = +2
            console.log(item);
        }
    });
}

// tryCatch: cognitive=2 (1 for if + 1 for catch)
function tryCatch(s) {
    try {
        if (s === null) {   // +1 (nesting=0)
            return;
        }
    } catch (e) {           // +1 (nesting=0)
        console.error(e);
    }
}
