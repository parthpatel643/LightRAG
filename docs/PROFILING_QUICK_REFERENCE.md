# LightRAG Profiling Quick Reference

## One-Liners

### Query with Timing
```bash
python query_graph.py --query "your question" --timing
```

### Query with Full Profile
```bash
python query_graph.py --query "your question" --profile
```

### Query with Both
```bash
python query_graph.py --query "your question" --profile --timing
```

### Ingest with Profiling
```bash
python build_graph.py --profile --timing
```

## Common Tasks

### Find Slowest Query Phase
```bash
python query_graph.py --query "test" --timing
```
Look for the phase with highest percentage in output.

### Profile Temporal Query
```bash
python query_graph.py --query "test" --mode temporal --date 2023-06-01 --profile
```

### Analyze Profiling Results
```bash
python -m pstats profile_output.prof
> sort cumulative
> stats 30
> quit
```

### Compare Profiles
```bash
# Baseline
python query_graph.py --query "test" --profile
cp profile_output.prof baseline.prof

# After optimization
python query_graph.py --query "test" --profile

# Compare timing
python -m pstats profile_output.prof
```

## Using in Code

### Add Timing to Your Script
```python
from lightrag.profiling import TimingBreakdown

timing = TimingBreakdown("My Process")
timing.mark("step1")
# ... do work ...
timing.mark("step1")
timing.report()
```

### Profile a Code Block
```python
from lightrag.profiling import ProfileContext

with ProfileContext("My Operation", output_file="prof.prof"):
    # your code here
    pass
```

### Profile a Function
```python
from lightrag.profiling import profile_function

@profile_function(output_file="func_prof.prof")
def my_function():
    pass

my_function()
```

## Interpreting Output

### Timing Output (percentages don't sum to 100%)
```
  phase1  1.234s (50.00%) [1 calls]
  phase2  1.234s (50.00%) [1 calls]
  Total: 2.468s
```

### Profile Output (sort by cumulative time)
```
ncalls tottime percall cumtime percall filename:lineno(function)
    10  0.001   0.0001  1.500   0.150  lightrag.py:120(aquery)
```

## Options Summary

| Flag | Purpose | Example |
|------|---------|---------|
| `--profile` | cProfile analysis | `query_graph.py --query "x" --profile` |
| `--timing` | Phase timing breakdown | `query_graph.py --query "x" --timing` |
| `--mode` | Query mode (temporal/hybrid/etc) | `--mode temporal` |
| `--date` | Temporal mode date | `--date 2023-06-01` |
| `--stream` | Stream response | `--stream` |

## Files Generated

| File | What It Is | How to View |
|------|-----------|------------|
| `profile_output.prof` | Binary cProfile data | `python -m pstats profile_output.prof` |
| Console output | Timing breakdown | Direct display |

## Pro Tips

1. **Always compare** - Run baseline before changes
2. **Use `--timing` first** - Quick way to find slow phases
3. **Then use `--profile`** - Drill into specific slow functions
4. **Combine with `--date`** - Profile temporal queries at different dates
5. **Stream large queries** - Reduces memory overhead during profiling

## Troubleshooting

- **"No module" error** → Check venv is activated
- **Large prof files** → Use `top_n=10` to limit functions
- **Can't read prof file** → Use text output format instead

## Documentation

Full details: [PROFILING_GUIDE.md](PROFILING_GUIDE.md)
