---
name: python-codestyle
description: "Use when writing, modifying, or reviewing Python code in this repository. Apply the Google Python Style Guide plus local rules for functional blocks, lowercase comments, function docstrings, import ordering, and test placement."
---

# Python codestyle

## Base style

Follow the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
for all Python code. The local rules below take precedence where they differ.

## Functional blocks and comments

- A functional block is a logical step, not an entire function or just code
  already surrounded by blank lines. Examples include validating one constraint,
  loading configuration, writing settings, executing setup, and reporting results.
- Start a new block whenever the responsibility changes. Independent validation
  checks are separate blocks, even when both use consecutive `if` statements.
- Start each block with a one-line purpose comment immediately followed by its
  code. Put one empty line between the preceding block's last code line and this
  comment: `previous code -> empty line -> purpose comment -> next code`.
- Apply this structure inside functions and nested scopes too. For example,
  separate writing configuration from the subsequent `if written` reporting.
- Keep related statements together; do not make every statement a separate block.
  Keep attached clauses (`elif`, `else`, `except`, `finally`) with their compound
  statement, and keep decorators attached to their definitions.
- Write all comments in lowercase, preserving case-sensitive identifiers and
  required tool directives.
- Keep docstrings in Google's format; docstrings are not comments.

Example of two independent validation blocks:

```python
# reject empty model selections before writing settings.
if not models:
    raise ValueError("At least one model is required.")

# web search requires the web interface to be enabled.
if enable_internet_access and not enable_web_interface:
    raise ValueError("Internet access requires the web interface.")
```

## Line wrapping

- Break long expressions at meaningful boundaries, preferably before operators
  such as `or` and `and`, using parentheses for implicit continuation.
- Keep short calls such as `.strip()` intact. Do not split an empty argument
  list across lines merely to satisfy the line limit.
- Preserve evaluation order and behavior when changing wrapping.
- If formatting produces an awkward split, restructure the parentheses or use
  a meaningful intermediate variable rather than accepting the awkward result.

Prefer:

```python
    return result.returncode == 0, (
        result.stderr.strip()
        or result.stdout.strip()
    )
```

Not:

```python
    return result.returncode == 0, result.stderr.strip() or result.stdout.strip(
    )
```

## Final return and raise

- Put an empty line immediately before a function's final `return` or `raise`
  statement, including a bare `return`, with one exception: if a purpose comment
  introduces the `return`, keep the comment directly above it without an empty
  line between them. Put the block-separating empty line before the comment.
- Keep this separation even when the preceding code is a validation, cleanup,
  or control-flow block.
- The final exit may finish the preceding functional block; it does not need a
  redundant comment solely to avoid the empty-line requirement.

Example inside a function:

```python
    # require the installed executable to be discoverable on the host path.
    executable = shutil.which("ollama")
    if executable is None:
        raise click.ClickException("Ollama is not on PATH.")

    return executable
```

When a comment introduces the return:

```python
    # delegate platform-specific config placement to click.
    return pathlib.Path(click.get_app_dir("punk")) / "config.json"
```

## Function docstrings

- Every key function must have a Google-style docstring immediately after its
  definition. Key functions include public entry points, core business logic,
  and nontrivial helpers.
- Start with a concise summary of its purpose and behavior.
- Include `Args:` for parameters, `Returns:` for returned values (or `Yields:`
  for generators), and `Raises:` for exceptions callers need to handle.
  Omit sections that do not apply; do not add empty sections.
- Document important side effects and constraints when relevant. Keep the
  description consistent with the implementation.
- Use normal capitalization in docstrings; the lowercase rule applies to
  comments, not docstrings. Docstrings do not replace functional-block comments.

Example:

```python
"""Run an external command, reporting actionable CLI errors.

Args:
    command: Executable and arguments.
    action: Human-readable action used in error messages.
    capture_output: Whether to capture standard output and error.
    timeout: Maximum run time in seconds, or None for no limit.

Returns:
    The completed process, including any captured output.

Raises:
    click.ClickException: The process cannot start, fails, or times out.
"""
```

## Imports

Use the following group order, separating nonempty groups with a blank line.
Start each group with its corresponding comment:

1. Builtin / standard library: `# builtin`
2. Third-party: `# third-party`
3. Internal / project-local: `# internal`

Within each group:

- Sort statements by length, shortest first, then alphabetically for equal lengths.
- Measure the complete statement without indentation; treat a multiline statement
  as one space-separated line.

Keep any `from __future__` imports before these groups, as Python requires.

## Test placement

- Put tests in a local `tests/` subfolder beside the source files they cover.
- Name test files `test_<module>.py`.
- For example: `src/punk/cli.py` pairs with `src/punk/tests/test_cli.py`.
- Do not use a root-level `tests/` directory.

## Verification

- Check changed Python code against the base style and all local rules above.
- Identify logical steps from their responsibilities, not just existing blank
  lines. Verify each step has its own heading comment and blank-line separation.
- Recheck these boundaries after formatting; a formatter does not identify
  functional blocks or enforce the custom comment rules.
- Verify key functions have accurate docstrings with all applicable sections.
- Verify each function's final `return` or `raise` has an empty line immediately
  above it, except when a purpose comment directly introduces the `return`.
  Never separate such a comment from its `return` with an empty line.
- Check wrapping uses natural expression boundaries and keeps short calls intact.
- Run the relevant existing checks and tests.
- Do not reformat unrelated code.
