# Stage 2: Test Code & Helper Methods Extraction

This stage parses Java/Groovy source files inside project ZIPs to extract the method body of the flaky test, discover calls to local helper methods, and retrieve their bodies recursively.

---

## Key Extraction Mechanisms

1. **Brace counting**: Finds the bounds of a method by matching the opening `{` and counting nested braces until the corresponding closing `}` is reached (depth drops to 0).
2. **Comment and String Stripping**: Strips Java/Groovy line comments, block comments, and string literals during parsing so that braces contained inside them (e.g., `String s = "}";`) do not interfere with brace counting.
3. **Recursive Class Inheritance Traversal**: If a test method or a helper method is inherited from a parent test case, the script parses the `extends` clause, resolves the FQN (fully qualified name) using package declarations and import statements, and recursively checks parent source files inside the ZIP.
4. **Generics Support**: Handles generic class declarations (e.g., `class MyClass<T> extends Parent<T>`) when extracting inheritance chains.
5. **Groovy & Java Support**: Resolves both `.java` and `.groovy` files.
6. **JUnit Parameterized Clean-Up**: Strips parameterized test name annotations (like `[...]` or `:...`) from the report method name before searching the source file.

---

## Extraction Example

### 1. Source Class Definition (`MyTestClass.java`):
```java
public class MyTestClass extends BaseTestClass {
    @Test
    public void testCompute() {
        int result = helperAdd(5, 10);
        Assert.assertEquals(15, result);
    }
    
    private int helperAdd(int a, int b) {
        return a + b;
    }
}
```

### 2. Extraction Results:

* **`flaky_test_code`**:
```java
@Test
    public void testCompute() {
        int result = helperAdd(5, 10);
        Assert.assertEquals(15, result);
    }
```

* **`flaky_helper_methods_json`**:
```json
{
  "helperAdd": "private int helperAdd(int a, int b) {\n        return a + b;\n    }"
}
```
