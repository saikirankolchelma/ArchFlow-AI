Mermaid rules (diagrams must render without errors):
- Use `flowchart TD` or `flowchart LR` for flows and architecture (preferred), `sequenceDiagram` only when message order matters, `erDiagram` for data models.
- Node IDs are short alphanumeric words (A, login, db1). Always quote labels: login["User logs in"], check{"Valid?"}, db[("Orders DB")].
- Edge labels: A -->|"yes"| B. Never put quotes, brackets or parentheses unescaped inside labels.
- Put each statement on its own line; use real newlines in the JSON string (\n).
