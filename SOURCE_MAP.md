# Source map — 0.10.2.1

The accepted implementation remains a single source file. The following names are searchable in `TuxStudio.py` on GitHub.

| Component | Source symbol | Approximate line |
|---|---|---:|
| Language vocabulary | TuxLanguageRegistry | 32 |
| Tokens and diagnostics | TuxToken, TuxDiagnostic | 40 |
| Lexer | TuxLexer | 61 |
| AST | TuxAstNode | 158 |
| Parser | TuxParser | 173 |
| Semantic analysis | TuxSemanticAnalyzer | 669 |
| AST export | tux_ast_export | 810 |
| Runtime values and errors | TuxFault, TuxFunction, TuxClass, TuxObject | 822 |
| Capability policy | TuxCapabilityRegistry | 867 |
| Interpreter and standard library | TuxInterpreter | 905 |
| Worker protocol | tux_wire_write, tux_wire_read | 1729 |
| Resource limits | tux_os_limits | 1751 |
| Worker entry point | tux_worker_main | 1759 |
| Parent process bridge | tux_process_run | 1788 |
| Syntax highlighting | TuxSyntaxHighlighter | 1963 |
| Editor language integration | TuxEditorLanguage | 2003 |

Execution proceeds through lexing, parsing, semantic analysis, policy validation and interpretation. The GUI communicates with a separate runtime worker. The worker and resource restrictions are not a complete OS sandbox. Use trusted programs only.

The documentation distinguishes implemented and planned syntax. The current source is authoritative for actual runtime behavior. The alias regression tests are in `alias-tests.py`.
