#include <vector>
#include <string>

// add: cognitive=0, cyclomatic=1, params=2
int add(int a, int b) {
    return a + b;
}

// nestedIfs: cognitive=6 (1 + 2 + 3), cyclomatic=4, max_nesting=3
bool nestedIfs(int x, int y, int z) {
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
int findItem(const std::string* items, int size, const std::string& target) {
    for (int i = 0; i < size; i++) {  // +1 (nesting=0)
        if (items[i] == target) {      // +2 (1 + nesting=1)
            break;                     // +1
        }
    }
    return -1;
}

// classify: cognitive=1 (switch), cyclomatic=4 (1 + 3 cases)
std::string classify(int n) {
    switch (n) {  // +1
    case 0:
        return "zero";
    case 1:
        return "one";
    default:
        return "other";
    }
}

// validate: cognitive=2 (1 + 1), cyclomatic=3
bool validate(bool a, bool b) {
    if (a && b) {  // +1 (if) + 1 (&&)
        return true;
    }
    return false;
}

// elseIfChain: cognitive=3 (1 + 1 + 1, flat), max_nesting=1
std::string elseIfChain(int x) {
    if (x < 0) {
        return "negative";
    } else if (x == 0) {
        return "zero";
    } else if (x < 10) {
        return "small";
    } else {
        return "large";
    }
}

class MyClass {
public:
    // constructor: cognitive=0, cyclomatic=1, params=1
    MyClass(int x) : x_(x) {}

    // process: cognitive=1, cyclomatic=2, params=1
    int process(int val) {
        if (val > 0) {  // +1
            return val * x_;
        }
        return 0;
    }

private:
    int x_;
};

// tryCatch: cognitive=2 (1 for if + 1 for catch)
void tryCatch(int x) {
    try {
        if (x < 0) {   // +1 (nesting=0)
            return;
        }
    } catch (...) {     // +1 (nesting=0)
        return;
    }
}

// withLambda: cognitive=2, max_nesting=2
void withLambda(std::vector<int>& items) {
    auto f = [](int item) {  // lambda: nesting+1
        if (item > 0) {      // +1 + nesting=1 = +2
            return item;
        }
        return 0;
    };
}
