# LightRAG Unified CLI - Design Summary

## Overview

This document summarizes the key design decisions for the unified CLI interface that simplifies the LightRAG user experience.

## Key Design Decisions

### 1. File Sequencing Requires Human Confirmation

**Decision**: Document sequencing cannot be fully automated and requires SME (Subject Matter Expert) knowledge.

**Rationale**: 
- Only humans understand the true chronological relationships between documents
- Automated heuristics (dates, versions) can suggest but not decide
- Incorrect sequencing leads to wrong version relationships in the knowledge graph

**Implementation**:
```bash
# Default: Interactive with suggestions
lightrag build --input ./contracts
# Shows suggested order, user confirms or modifies

# Explicit: User specifies exact order
lightrag build --files base.pdf amendment1.pdf amendment2.pdf

# Suggested: System suggests, user must confirm
lightrag build --input ./contracts --suggest-order
```

**User Flow**:
1. System scans directory and finds files
2. System analyzes filenames for date/version patterns
3. System presents suggested order with reasoning
4. User reviews and either:
   - Accepts (press Y)
   - Rejects and manually specifies order
   - Edits the suggested order

### 2. Working Directory Switching

**Decision**: Allow switching between different knowledge graphs via `--working-dir` flag in all commands.

**Rationale**:
- Users may maintain multiple knowledge graphs (different projects, datasets)
- Need ability to query different graphs without changing directories
- Interactive mode should support switching graphs mid-session

**Implementation**:

**Query Command**:
```bash
# Query specific graph
lightrag query "What is the fee?" --working-dir ./contracts_rag

# List available graphs
lightrag query --list-graphs
```

**Interactive Mode**:
```bash
# Start with specific graph
lightrag interactive --working-dir ./contracts_rag

# Switch during session
[temporal] Query: /graph ./documents_rag
✓ Switched to working directory: ./documents_rag

# List available graphs
[temporal] Query: /graphs
Available graphs:
  - ./rag_storage (default)
  - ./contracts_rag
  - ./documents_rag
```

**Build Command**:
```bash
# Build into specific directory
lightrag build --input ./docs --working-dir ./docs_rag
```

## Command Structure

### Main Commands

```bash
lightrag build              # Build knowledge graph with interactive sequencing
lightrag query "question"   # Query with working directory support
lightrag interactive        # Interactive mode with graph switching
lightrag info               # Show graph statistics
lightrag config             # Manage configuration
```

### Key Options

**Build**:
- `--files FILE [FILE ...]` - Explicit file order (recommended)
- `--input DIR` - Input directory (triggers interactive sequencing)
- `--suggest-order` - Show suggested order with reasoning
- `--working-dir DIR` - Target working directory

**Query**:
- `--working-dir DIR` - Query specific graph
- `--list-graphs` - List available graphs
- `--as-of DATE` - Temporal query at specific date
- `--mode MODE` - Query mode (local/global/hybrid/temporal)

**Interactive**:
- `--working-dir DIR` - Start with specific graph
- `/graph DIR` - Switch graph during session
- `/graphs` - List available graphs

## User Workflows

### Workflow 1: First-Time User (Explicit Files)

```bash
# 1. Specify files in order
lightrag build --files base.pdf amendment1.pdf amendment2.pdf

# 2. Query
lightrag query "What is the fee?"
```

### Workflow 2: Interactive Sequencing

```bash
# 1. Build with suggestions
lightrag build --input ./contracts

# Output:
# 🔍 Scanning ./contracts... found 4 files
# 
# 📋 Suggested order (please review):
#   1. base-contract.pdf (detected: base document)
#   2. amendment-q1.pdf (detected: 2024-Q1 date)
#   3. amendment-q2.pdf (detected: 2024-Q2 date)
#   4. update-2024.pdf (detected: 2024 date)
# 
# ❓ Accept this order? [Y/n/edit]: Y

# 2. Query
lightrag query "What is the fee?"
```

### Workflow 3: Multiple Graphs

```bash
# Build multiple graphs
lightrag build --files contract1.pdf --working-dir ./contract1_rag
lightrag build --files contract2.pdf --working-dir ./contract2_rag

# Query different graphs
lightrag query "What is the fee?" --working-dir ./contract1_rag
lightrag query "What is the fee?" --working-dir ./contract2_rag

# Or use interactive mode
lightrag interactive
[hybrid] Query: What is the fee?
# Response from default graph

[hybrid] Query: /graph ./contract2_rag
✓ Switched to working directory: ./contract2_rag

[hybrid] Query: What is the fee?
# Response from contract2_rag
```

## Error Handling

### Missing Working Directory

```bash
$ lightrag query "test" --working-dir ./missing
Error: Working directory not found: ./missing

Available graphs:
  - ./rag_storage (default)
  - ./contracts_rag
  - ./documents_rag

Use: lightrag query "test" --working-dir ./rag_storage
Or:  lightrag query "test" --list-graphs
```

### No Documents Found

```bash
$ lightrag build --input ./empty
Error: No documents found in ./empty

Supported formats: .md, .txt, .pdf, .docx
Place documents in ./empty and try again
```

## Benefits

1. **Human-in-the-Loop Sequencing**: Ensures correct version relationships
2. **Flexible Graph Management**: Easy switching between multiple knowledge graphs
3. **Clear User Feedback**: Suggestions with reasoning, not black-box automation
4. **Safety**: User confirmation prevents incorrect sequencing
5. **Discoverability**: `--list-graphs` and `/graphs` help users find available graphs

## Implementation Priority

### Phase 1 (Core)
- [x] Design document with human-confirmed sequencing
- [ ] Implement build command with interactive sequencing
- [ ] Implement query command with working-dir support
- [ ] Basic error handling

### Phase 2 (Enhanced)
- [ ] Implement interactive mode with graph switching
- [ ] Add --list-graphs functionality
- [ ] Implement suggestion heuristics
- [ ] Rich terminal output

### Phase 3 (Polish)
- [ ] Comprehensive error messages
- [ ] Graph discovery and management
- [ ] Configuration persistence
- [ ] Documentation and examples

## Next Steps

1. Review this design summary
2. Confirm approach for sequencing (interactive with suggestions)
3. Confirm working directory switching implementation
4. Proceed to implementation phase

---

**Full Design**: See [`CLI_DESIGN.md`](CLI_DESIGN.md) for complete specification.