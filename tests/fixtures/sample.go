package sample

// Simple function with no branching
func Add(a int, b int) int {
	return a + b
}

// Nested ifs: cognitive = 1 + 2 + 3 = 6
func NestedIfs(x, y, z int) bool {
	if x > 0 { // +1
		if y > 0 { // +2 (1 + nesting=1)
			if z > 0 { // +3 (1 + nesting=2)
				return true
			}
		}
	}
	return false
}

// For loop with break: cognitive = 1 + 2 + 1 = 4
func FindItem(items []string, target string) int {
	for i, item := range items { // +1
		if item == target { // +2 (1 + nesting=1)
			break // +1
		}
		_ = i
	}
	return -1
}

// Switch statement: cognitive = 1 (switch) + nesting cases
func Classify(n int) string {
	switch { // +1
	case n < 0:
		return "negative"
	case n == 0:
		return "zero"
	default:
		return "positive"
	}
}

// Boolean operators: cognitive = 1 (if) + 1 (&&)
func Validate(a, b bool) bool {
	if a && b { // +1 (if) + 1 (&&)
		return true
	}
	return false
}

type Server struct {
	Name string
}

// Method with receiver: qualified name = Server.Start
func (s *Server) Start(port int) error {
	if port <= 0 { // +1
		return nil
	}
	return nil
}

// Goroutine and defer
func Process(items []int) {
	for _, item := range items { // +1
		go func(v int) { // +1 (go)
			if v > 0 { // +2 (1 + nesting=1)  -- inside func_literal nesting=1, then if adds nesting
				handle(v)
			}
		}(item)
	}
	defer cleanup() // +1 (defer)
}

func handle(v int) {}
func cleanup()     {}
