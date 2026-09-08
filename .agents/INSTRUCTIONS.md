# Coding Agent Instructions

These instructions apply to the coding agent working on Artificial Ecology.

## Communication

- Be direct.
- Lead with the result or the next concrete action.
- Explain only what is necessary to understand the change, decision, risk, or blocker.
- Avoid filler, repeated context, motivational language, and lengthy step-by-step narration.
- Ask a question only when a missing choice materially affects the implementation.

## Clean code principles

Use the practical principles associated with Robert C. Martin’s Clean Code approach:

- Give names enough precision that comments are rarely needed.
- Keep functions and modules small, focused, and cohesive.
- Make each unit do one thing at one level of abstraction.
- Prefer simple control flow and early returns over deeply nested logic.
- Keep dependencies explicit and minimize coupling.
- Separate policy from mechanism and domain rules from I/O.
- Avoid duplication, speculative abstractions, hidden global state, and clever code.
- Preserve clear boundaries between responsibilities.
- Make invalid states difficult to represent and validate inputs at boundaries.
- Keep public interfaces small and stable.
- Refactor nearby code when a change would otherwise make it harder to understand, but do not perform unrelated rewrites.

Clean code is not code with the fewest lines. Prefer readability, cohesion, testability, and an appropriate level of abstraction.

## Change discipline

- Inspect existing code before editing it.
- Make the smallest complete change that satisfies the request.
- Preserve unrelated user changes.
- Add or update tests when behavior changes.
- Verify the result with the narrowest relevant checks, then report what was verified.
- State assumptions briefly when they matter.
