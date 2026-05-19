# Coding Philosophy

Rules for writing and reviewing code in this project.
Each rule includes a detection signal so it can be applied mechanically during code review.

---

### One function, one thing

A function should have a single subject — one actor, one phase, one level of abstraction.

**Flag when**: the function has two or more distinct phases separated by a blank line where each phase has a different subject (e.g. one resolves data, the next starts a process), or the function name requires "and" or "then" to describe it accurately.

**Instead**: split at the phase boundary; name each piece after what it does.

---

### Orchestrators route — they don't reason

Entry-point and dispatch functions should branch and delegate. Business logic does not belong in them.

**Flag when**: a function named `main`, `run`, or one that contains a command-dispatch `if/elif` chain also contains logic that resolves ambiguity, validates state, or computes a result.

**Instead**: move the logic into a dedicated function; leave the orchestrator with only branching and calls.

---

### Converge parallel flows

When two branches of a conditional end with identical or structurally equivalent statements, those statements belong after the conditional — not duplicated inside each branch.

**Flag when**: two or more branches of an if/elif/else each end with the same function call or sequence of statements.

**Instead**: hoist the shared tail after the conditional, or extract it into a shared helper called by both branches.

---

### Single-caller wrappers add nothing

A function that is called from exactly one place and contains no logic beyond delegating to another function is dead weight.

**Flag when**: a function has one call site and its entire body is a guard check plus a single call, or is a direct pass-through with renamed arguments.

**Instead**: inline it at the call site, or merge it into the caller.

---

### Name opaque conditions

A boolean expression used directly in a branch condition that requires parsing to understand should be a named variable.

**Flag when**: an `if` or `while` condition contains three or more terms (operators, comparisons, negations).

**Instead**: assign the expression to a descriptive name above the branch: `bare = x is None and y is None and not z`.

---

### Guard clauses over nesting

Handle edge cases and early exits at the top of the function, then write the main path unindented.

**Flag when**: an `if/elif/elif/else` chain where one or more branches end with `return`, `sys.exit`, or `raise` — those branches can become early returns, flattening the rest.

**Instead**: convert terminal branches to guard clauses at the top; the main path flows naturally at the base indent level.

---

### Tests assert on outcomes, not intermediaries

A test that only verifies which internal function was called proves routing, not behavior.

**Flag when**: an assertion uses `assert_called_once()` or `assert_called_with()` on a mock without also asserting the specific arguments, return value, or observable side effect.

**Instead**: assert the arguments the function was called with, or assert the value returned to the caller — whatever represents the actual outcome.

---

### Delete dead code

Dead code misleads readers and creates maintenance surface with no benefit.

**Flag when**: a branch condition is provably False given earlier guards; a local variable is assigned but never read; a function has no callers; a test helper method is never invoked by any test.

**Instead**: delete it. Do not comment it out.

---

### Prefer existing libraries for solved problems

Custom implementations of well-solved problems carry hidden bugs and maintenance cost.

**Flag when**: the code contains a hand-rolled implementation of: terminal raw-mode I/O, HTTP clients, argument parsing, config file parsing, date/time arithmetic, UUID generation, or JSON serialisation.

**Instead**: identify the standard library module or well-known package that solves it and use that. For anything outside these domains, note the pattern but do not flag blindly — library availability varies.
