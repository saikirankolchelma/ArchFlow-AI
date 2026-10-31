Canvas syntax: use ONLY these constructs, because the canvas cannot display anything else:
flowchart TD   (use flowchart LR for architecture)
  id(["Start / End"])      id["Process step"]        id{"Decision?"}
  id(("Actor / User"))     id[["Service / component"]]  id[("Database")]
  id[/"Queue / topic"/]    id>"External system"]     id["Note text"] plus a line: class id note
  a --> b                  a -->|"label"| b
No subgraph, style, classDef or linkStyle lines; no sequence or ER diagrams; one statement per line; always quote labels.
