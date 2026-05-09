"""Benchmark task suite.

Each task is a (request, expected_substring) pair plus a deterministic id.
The eval harness scores success by whether the final stdout from the sandbox
contains every expected substring (case-sensitive).

Keep this small (~10 tasks) so a full sweep is affordable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalTask:
    id: str
    request: str
    expected: tuple[str, ...]


TASKS: list[EvalTask] = [
    EvalTask(
        id="primes_10",
        request="Print the first 10 prime numbers separated by spaces.",
        expected=("2", "3", "5", "7", "11", "13", "17", "19", "23", "29"),
    ),
    EvalTask(
        id="fibonacci_15",
        request="Print the first 15 Fibonacci numbers (starting 0, 1) separated by spaces.",
        expected=("0", "1", "1", "2", "3", "5", "8", "13", "21", "34", "55", "89", "144", "233", "377"),
    ),
    EvalTask(
        id="factorial_10",
        request="Print 10! (ten factorial).",
        expected=("3628800",),
    ),
    EvalTask(
        id="reverse_string",
        request="Reverse the string 'self-healing' and print it.",
        expected=("gnilaeh-fles",),
    ),
    EvalTask(
        id="word_count",
        request="Count the number of words in 'the quick brown fox jumps over the lazy dog' and print the count.",
        expected=("9",),
    ),
    EvalTask(
        id="sum_squares",
        request="Compute the sum of squares from 1 to 100 inclusive and print it.",
        expected=("338350",),
    ),
    EvalTask(
        id="palindrome",
        request="Check if 'racecar' is a palindrome and print True or False.",
        expected=("True",),
    ),
    EvalTask(
        id="anagram",
        request="Determine whether 'listen' and 'silent' are anagrams and print True or False.",
        expected=("True",),
    ),
    EvalTask(
        id="json_parse",
        request='Parse the JSON string \'{"a": 1, "b": [2, 3]}\' and print the value of key "b" as a Python list.',
        expected=("[2, 3]",),
    ),
    EvalTask(
        id="csv_inline",
        request="Given the CSV string 'name,age\\nAlice,30\\nBob,25', print only the names, one per line.",
        expected=("Alice", "Bob"),
    ),
]
