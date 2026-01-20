# LightRAG Profiling Guide

This guide explains how to use the profiling and performance analysis tools available in LightRAG.

## Overview

The profiling infrastructure provides three main capabilities:

1. **cProfile-based Function Profiling** - Detailed call stack analysis
2. **Timing Breakdown Analysis** - Phase-by-phase performance tracking
3. **Memory Profiling** - Memory usage statistics

## Quick Start

### Query Profiling

#### With Timing Breakdown
```bash
python query_graph.py --query "Your question here" --mode hybrid --timing
```

#### With Full cProfile Analysis
```bash
python query_graph.py --query "Your question here" --mode hybrid --profile
```

#### Combined Profiling
```bash
python query_graph.py --query "Your question here" --mode hybrid --profile --timing
```

### Build/Ingestion Profiling

#### With Timing Breakdown
```bash
python build_graph.py --timing
```

#### With Full cProfile Analysis
```bash
python build_graph.py --profile
```

## Profiling Modules

### `lightrag.profiling` Module

#### 1. `TimingBreakdown` Class

Tracks execution time across multiple named phases.

**Basic Usage:**
```python
from lightrag.profiling import TimingBreakdown

timing = TimingBreakdown("My Process")

# Mark start of a phase
timing.mark("phase1")
# ... do work ...
timing.mark("phase1")  # Mark end

# Mark another phase
timing.mark("phase2")
# ... do more work ...
timing.mark("phase2")

# Display results
timing.report()
```

**Context Manager Usage:**
```python
timing = TimingBreakdown("My Process")

with timing.section("data_loading"):
    # ... load data ...
    pass

with timing.section("processing"):
    # ... process data ...
    pass

timing.report()
```

**Output Example:**
```
============================================================
My Process
============================================================
  data_loading                     1.234s ( 45.67%) [1 calls]
  processing                       1.456s ( 53.67%) [1 calls]
  cleanup                          0.102s (  3.76%) [1 calls]
------------------------------------------------------------
  Total: 2.792s
============================================================
```

#### 2. `ProfileContext` Context Manager

Profiles a code block with cProfile and optionally saves results.

**Basic Usage:**
```python
from lightrag.profiling import ProfileContext

with ProfileContext("My Operation", output_file="profile.prof"):
    # ... your code here ...
    pass
```

**Output:**
- `profile.prof` - Binary cProfile data (can be analyzed with `pstats`)
- Console output showing top functions by cumulative time

#### 3. `profile_function` Decorator

Profiles a synchronous function.

```python
from lightrag.profiling import profile_function

@profile_function(output_file="my_function.prof", sort_by="cumulative", top_n=20)
def expensive_operation():
    # ... your code ...
    pass

expensive_operation()  # Profiling runs automatically
```

#### 4. `profile_async_function` Decorator

Profiles an async function.

```python
from lightrag.profiling import profile_async_function

@profile_async_function(output_file="my_async_func.prof")
async def my_async_operation():
    # ... your async code ...
    pass

await my_async_operation()  # Profiling runs automatically
```

#### 5. `ProfileStats` Class

Analyzes and manipulates cProfile results.

```python
from lightrag.profiling import ProfileStats
import cProfile

prof = cProfile.Profile()
prof.enable()
# ... your code ...
prof.disable()

stats = ProfileStats(prof=prof)

# Print stats to console
stats.print_stats(sort_by="cumulative", top_n=20)

# Get top functions programmatically
top_funcs = stats.get_top_functions(n=10)
for filename, lineno, funcname, ncalls, tottime, cumtime in top_funcs:
    print(f"{funcname}: {cumtime:.3f}s")

# Save results
stats.save_stats("results.prof", format_type="prof")
stats.save_stats("results.txt", format_type="txt")
```

## Analyzing cProfile Results

### Using pstats Interactive Mode

```bash
python -m pstats profile_output.prof
```

Common commands:
```
> sort cumulative        # Sort by cumulative time
> stats 20              # Show top 20 functions
> stats lightrag         # Show only lightrag functions
> quit                  # Exit
```

### Programmatic Analysis

```python
import pstats

# Load saved profile
stats = pstats.Stats('profile_output.prof')

# Sort by cumulative time
stats.sort_stats('cumulative')

# Show top 30 functions
stats.print_stats(30)

# Filter to specific module
stats.print_callers('lightrag.utils')
```

## Query Mode Examples

### Temporal Query with Profiling
```bash
python query_graph.py \
  --query "What is the service fee?" \
  --mode temporal \
  --date 2023-06-01 \
  --timing \
  --profile
```

### Interactive Mode with Timing
```bash
python query_graph.py --interactive --mode temporal --timing
```

### Streaming Query with Profiling
```bash
python query_graph.py \
  --query "Summarize the document" \
  --mode hybrid \
  --stream \
  --profile
```

## Build/Ingestion Examples

### Profile Document Ingestion
```bash
python build_graph.py --profile --timing
```

This will:
1. Show timing breakdown for: setup, initialization, ingestion, finalization
2. Generate `profile_output.prof` with detailed function call statistics
3. Show top 20 functions by cumulative time

## Understanding the Output

### Timing Breakdown Output

```
============================================================
Ingestion Phases
============================================================
  setup                          0.500s ( 10.50%) [1 calls]
  initialization                 1.234s ( 25.87%) [1 calls]
  ingestion                       2.567s ( 53.89%) [1 calls]
  finalization                   0.399s (  8.37%) [1 calls]
------------------------------------------------------------
  Total: 4.700s
============================================================
```

**Reading the output:**
- `0.500s` - Actual execution time for this phase
- `10.50%` - Percentage of total time
- `[1 calls]` - Number of times this section was called

### cProfile Output

```
         123456 function calls (123400 primitive calls) in 2.500 seconds

   Ordered by: cumulative time
   List reduced from 1000 to 20 due to restriction <'20'>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.001    0.001    2.500    2.500 query_graph.py:45(query_rag)
      100    0.050    0.001    2.300    0.023 lightrag.py:120(aquery)
      500    0.100    0.000    1.800    0.004 utils.py:200(embedding_func)
       10    0.005    0.001    1.200    0.120 kg/graph.py:50(traverse)
        ...
```

**Column meanings:**
- `ncalls` - Number of function calls
- `tottime` - Time spent in this function alone
- `percall` (tottime) - Average time per call (tottime / ncalls)
- `cumtime` - Cumulative time (including called functions)
- `percall` (cumtime) - Average cumulative time per call

## Performance Analysis Workflow

### 1. Identify Bottlenecks

Run with `--timing` to see which phases take longest:
```bash
python query_graph.py --query "test" --timing
```

### 2. Profile Specific Phase

If ingestion is slow, profile it:
```bash
python build_graph.py --profile --timing
```

### 3. Analyze Function Calls

Use `pstats` to drill into specific functions:
```bash
python -m pstats profile_output.prof
> sort cumulative
> stats 50
> print_callers embedding_func
```

### 4. Track Changes

Keep baseline profiles:
```bash
python query_graph.py --query "test" --profile
cp profile_output.prof baseline.prof
```

After optimization:
```bash
python query_graph.py --query "test" --profile
# Compare with: python -m pstats profile_output.prof
```

## Memory Profiling

Check current memory usage:

```python
from lightrag.profiling import get_memory_usage, report_memory

# Get memory stats
mem = get_memory_usage()
print(f"RSS: {mem['rss_mb']:.1f} MB")
print(f"VMS: {mem['vms_mb']:.1f} MB")
print(f"Percent: {mem['percent']:.2f}%")

# Or use helper
report_memory()
```

**Note:** Requires `psutil` package:
```bash
pip install psutil
```

## Integration in Custom Code

### Adding Profiling to Custom Scripts

```python
import asyncio
from lightrag.profiling import TimingBreakdown, ProfileContext
from lightrag import LightRAG

async def my_query_script():
    timing = TimingBreakdown("Custom Query Script")
    
    with ProfileContext("Initialization", output_file="init.prof"):
        timing.mark("setup")
        # Initialize RAG
        timing.mark("setup")
    
    with ProfileContext("Query Execution", output_file="query.prof"):
        timing.mark("query")
        # Execute query
        timing.mark("query")
    
    timing.report()

# Run with profiling
asyncio.run(my_query_script())
```

## Best Practices

1. **Profile in Production-like Environment** - Use representative data and queries
2. **Run Multiple Times** - Average results to avoid outliers
3. **Profile Whole Workflows** - Understand end-to-end performance
4. **Focus on High-Impact Areas** - Use `--timing` first, then drill into slow phases
5. **Keep Baselines** - Compare before/after optimization
6. **Profile Different Query Modes** - Performance may vary by mode (temporal vs. hybrid)
7. **Combine Approaches** - Use `--timing` for phases and `--profile` for function details

## Troubleshooting

### `psutil not installed` warning
```bash
pip install psutil
```

### Profile file too large
Limit captured functions in `ProfileContext`:
```python
with ProfileContext(..., top_n=10):
    # Only save top 10 functions
    pass
```

### Can't read binary profile file
Use text format instead:
```python
stats.save_stats("results.txt", format_type="txt")
```

## Command Reference

| Command | Purpose |
|---------|---------|
| `--profile` | Enable cProfile and save results |
| `--timing` | Enable timing breakdown by phases |
| `--stream` | Stream responses (reduces memory usage) |
| `python -m pstats <file>` | Analyze saved profile interactively |
| `python -m cProfile -o out.prof script.py` | Profile a whole script |

## Related Documentation

- [Python cProfile Documentation](https://docs.python.org/3/library/profile.html)
- [pstats Module Reference](https://docs.python.org/3/library/pstats.html)
- [psutil Documentation](https://psutil.readthedocs.io/)
