"""Agentic retrieval sources.

This package hosts self-contained, side-effect-safe "agentic" retrieval
add-ons: features that decide, per-query, whether to pull in a piece of
context from a source outside the normal KG/vector retrieval path and
inject it into the LLM prompt. Every module here must fail closed — an
add-on failing (missing DB, malformed LLM output, etc.) must never break
the main query path.
"""
