// Simple function with no branching
fn add(a: i32, b: i32) -> i32 {
    a + b
}

// Nested ifs: cognitive = 1 + 2 + 3 = 6
fn nested_ifs(x: i32, y: i32, z: i32) -> bool {
    if x > 0 { // +1
        if y > 0 { // +2 (1 + nesting=1)
            if z > 0 { // +3 (1 + nesting=2)
                return true;
            }
        }
    }
    false
}

// For loop with break: cognitive = 1 + 2 + 1 = 4
fn find_item(items: &[String], target: &str) -> i32 {
    for (i, item) in items.iter().enumerate() { // +1
        if item == target { // +2 (1 + nesting=1)
            break; // +1
        }
        let _ = i;
    }
    -1
}

// Match expression: cognitive = 1 (match)
fn classify(n: i32) -> &'static str {
    match n { // +1
        x if x < 0 => "negative",
        0 => "zero",
        _ => "positive",
    }
}

// Boolean operators: cognitive = 1 (if) + 1 (&&)
fn validate(a: bool, b: bool) -> bool {
    if a && b { // +1 (if) + 1 (&&)
        return true;
    }
    false
}

struct Server {
    port: i32,
}

// Method with impl: qualified name = Server.start
impl Server {
    fn start(&self) -> bool {
        if self.port > 0 { // +1
            true
        } else {
            false
        }
    }
}

// Closure with nesting: cognitive = 2 (if inside closure at nesting=1)
fn with_closure() -> i32 {
    let f = |x: i32| -> i32 {
        if x > 0 { // +2 (1 + nesting=1 from closure)
            x
        } else {
            -x
        }
    };
    f(42)
}

// if-let: cognitive = 1 (treated as if)
fn with_if_let(x: Option<i32>) -> i32 {
    if let Some(v) = x { // +1
        v
    } else {
        0
    }
}

// Loop with break: cognitive = 1 (loop) + 2 (if nested) + 1 (break) = 4
fn with_loop() -> i32 {
    let mut i = 0;
    loop { // +1
        if i > 10 { // +2 (1 + nesting=1)
            break; // +1
        }
        i += 1;
    }
    i
}

// Try operator: cognitive = 1 (?)
fn with_try(x: Result<i32, String>) -> Result<i32, String> {
    let v = x?; // +1
    Ok(v + 1)
}
