"""ZurixAI Eval — __init__.py for eval package."""

from __future__ import annotations

from zurixai.eval.prompt_eval import PromptEvaluator
from zurixai.eval.auto_select import select_best_prompt

__all__ = ["PromptEvaluator", "select_best_prompt"]
