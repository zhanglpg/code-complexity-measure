package sample;

/**
 * Sample Java file with documented complexity values for testing.
 */
public class Sample {

    // add: cognitive=0, cyclomatic=1, params=2
    public static int add(int a, int b) {
        return a + b;
    }

    // nestedIfs: cognitive=6 (1 + 2 + 3), cyclomatic=4, max_nesting=3
    public static boolean nestedIfs(int x, int y, int z) {
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
    public static int findItem(String[] items, String target) {
        for (int i = 0; i < items.length; i++) {  // +1 (nesting=0)
            if (items[i].equals(target)) {          // +2 (1 + nesting=1)
                break;                              // +1
            }
        }
        return -1;
    }

    // validate: cognitive=2 (1 + 1), cyclomatic=3
    public static boolean validate(boolean a, boolean b) {
        if (a && b) {  // +1 (if) + 1 (&&)
            return true;
        }
        return false;
    }

    // elseIfChain: cognitive=3 (1 + 1 + 1, flat), max_nesting=1
    public static String elseIfChain(int x) {
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

    // constructor: cognitive=0, cyclomatic=1, params=1
    public Sample(int x) {
    }

    // withLambda: cognitive=2, max_nesting=2
    public void withLambda(java.util.List<Integer> items) {
        items.forEach(item -> {  // lambda: nesting+1
            if (item > 0) {      // +1 + nesting=1 = +2
                System.out.println(item);
            }
        });
    }

    // tryCatch: cognitive=2 (1 for if + 1 for catch)
    public static void tryCatch(String s) {
        try {
            if (s == null) {   // +1 (nesting=0)
                return;
            }
        } catch (Exception e) {  // +1 (nesting=0)
            System.err.println(e);
        }
    }
}
