/* Sample C file for testing complexity analysis */

#include <stdio.h>

/* add: cognitive=0, cyclomatic=1, params=2 */
int add(int a, int b) {
    return a + b;
}

/* findMax: cognitive=3 (1 + 2), cyclomatic=3, params=2 */
int findMax(int* arr, int size) {
    int max = arr[0];
    for (int i = 1; i < size; i++) {  // +1 (nesting=0)
        if (arr[i] > max) {            // +2 (1 + nesting=1)
            max = arr[i];
        }
    }
    return max;
}

/* doWhileExample: cognitive=1, cyclomatic=2, params=1 */
void doWhileExample(int n) {
    do {       // +1 (nesting=0)
        n--;
    } while (n > 0);
}
