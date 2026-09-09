#!/usr/bin/env python3
"""
Verifier benchmark — 40 test cases across 5 categories.

Tests hybrid support scoring (cosine × 0.70 + bigram-Jaccard × 0.30)
against a fixed Korean fact corpus using the project's SentenceTransformer embedder.

Usage:
    python3 scripts/verifier_bench.py
    python3 scripts/verifier_bench.py --threshold 0.55   # try a different threshold
"""
from __future__ import annotations

import argparse
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np

from backend.rag.embeddings.embedder import SentenceTransformerEmbedder

# ── Config ────────────────────────────────────────────────────────────────────
SEMANTIC_WEIGHT = 0.70
LEXICAL_WEIGHT  = 0.30

# ── Ground fact corpus ────────────────────────────────────────────────────────
FACTS = [
    "아리아는 미래의 행동을 에란과 논의한다.",
    "칼루아는 에란을 신뢰하지 않는다.",
    "에란은 동맹을 배신했다.",
    "아리아는 고독을 두려워한다.",
    "세계는 전쟁 상태에 있다.",
    "칼루아는 마법사다.",
    "아리아의 아버지는 에란이다.",
    "기사단은 왕국을 지킨다.",
    "에란은 죽었다.",
    "아리아는 검을 소지하고 있다.",
]

# ── Test cases ────────────────────────────────────────────────────────────────
# (answer_sentence, category, expected_supported)
TESTS: list[tuple[str, str, bool]] = [

    # ── 1. EXACT MATCH (10 cases) ─────────────────────────────────────────────
    ("아리아는 미래의 행동을 에란과 논의한다.",   "Exact",         True),
    ("칼루아는 에란을 신뢰하지 않는다.",          "Exact",         True),
    ("에란은 동맹을 배신했다.",                   "Exact",         True),
    ("아리아는 고독을 두려워한다.",               "Exact",         True),
    ("세계는 전쟁 상태에 있다.",                  "Exact",         True),
    ("칼루아는 마법사다.",                        "Exact",         True),
    ("아리아의 아버지는 에란이다.",               "Exact",         True),
    ("기사단은 왕국을 지킨다.",                   "Exact",         True),
    ("에란은 죽었다.",                            "Exact",         True),
    ("아리아는 검을 소지하고 있다.",              "Exact",         True),

    # ── 2. PARAPHRASE / SYNONYM (10 cases) ───────────────────────────────────
    # Same meaning, different vocabulary or word order
    ("아리아는 앞으로의 행동을 에란과 의논했다.", "Paraphrase",    True),   # 미래→앞으로, 논의→의논
    ("칼루아는 에란을 믿지 않는다.",              "Paraphrase",    True),   # 신뢰하지 않는다→믿지 않는다
    ("에란은 동맹을 저버렸다.",                   "Paraphrase",    True),   # 배신→저버리다
    ("아리아는 혼자가 되는 것을 두려워한다.",     "Paraphrase",    True),   # 고독→혼자가 되는 것
    ("세계는 전쟁 중이다.",                       "Paraphrase",    True),   # 전쟁 상태에 있다→전쟁 중
    ("칼루아는 마법을 사용하는 사람이다.",        "Paraphrase",    True),   # 마법사→마법을 사용하는 사람
    ("에란은 아리아의 아버지다.",                 "Paraphrase",    True),   # reversed subject but same fact
    ("기사단이 왕국을 보호하고 있다.",            "Paraphrase",    True),   # 지킨다→보호하다
    ("에란은 이미 사망했다.",                     "Paraphrase",    True),   # 죽었다→사망했다
    ("아리아는 칼을 가지고 있다.",                "Paraphrase",    True),   # 검→칼

    # ── 3. WRONG / UNRELATED (8 cases) ────────────────────────────────────────
    # Factually incorrect relative to the corpus
    ("에란은 아리아를 신뢰한다.",                 "Wrong",         False),
    ("칼루아는 전사다.",                          "Wrong",         False),  # facts say 마법사
    ("아리아는 행복하다.",                        "Wrong",         False),
    ("기사단은 적군과 동맹을 맺었다.",            "Wrong",         False),
    ("칼루아는 아리아의 아버지다.",               "Wrong",         False),
    ("세계는 평화롭다.",                          "Wrong",         False),  # facts say 전쟁 상태
    ("아리아는 마법을 사용한다.",                 "Wrong",         False),
    ("에란은 기사단을 이끈다.",                   "Wrong",         False),

    # ── 4. HALLUCINATION (7 cases) ────────────────────────────────────────────
    # Plausible-sounding but absent from facts
    ("아리아는 용과 함께 여행했다.",              "Hallucination", False),
    ("에란은 바다를 건넜다.",                     "Hallucination", False),
    ("칼루아는 숲속 마을 출신이다.",              "Hallucination", False),
    ("기사단은 세 개의 성을 보유하고 있다.",      "Hallucination", False),
    ("아리아는 요정과 협력했다.",                 "Hallucination", False),
    ("에란의 동생은 왕자다.",                     "Hallucination", False),
    ("칼루아는 도서관에서 연구한다.",             "Hallucination", False),

    # ── 5. COUNTERFACTUAL (5 cases) ────────────────────────────────────────────
    # Directly contradicts a known fact
    ("에란은 살아있다.",                          "Counterfact",   False),  # facts: 에란은 죽었다
    ("칼루아는 에란을 신뢰한다.",                 "Counterfact",   False),  # facts: 신뢰하지 않는다
    ("에란은 동맹을 지켰다.",                     "Counterfact",   False),  # facts: 배신했다
    ("아리아는 고독을 두려워하지 않는다.",        "Counterfact",   False),  # negation of fact
    ("칼루아는 마법사가 아니다.",                 "Counterfact",   False),  # facts: 마법사다
]


# ── Scoring helpers ───────────────────────────────────────────────────────────

def bigram_jaccard(a: str, b: str) -> float:
    ba = {a[i:i+2] for i in range(len(a) - 1)}
    bb = {b[i:i+2] for i in range(len(b) - 1)}
    union = ba | bb
    return len(ba & bb) / len(union) if union else 0.0


def cosine(u: list[float], v: list[float]) -> float:
    a, b = np.array(u, dtype=float), np.array(v, dtype=float)
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    return float(a @ b) / (na * nb) if na > 0 and nb > 0 else 0.0


def compute_scores(
    sent_vec: list[float],
    fact_vecs: list[list[float]],
    sent: str,
    fact_sents: list[str],
) -> tuple[float, float, float]:
    lex_scores = [bigram_jaccard(sent, fs) for fs in fact_sents]
    max_lex = max(lex_scores) if lex_scores else 0.0

    cos_scores = [cosine(sent_vec, fv) for fv in fact_vecs]
    max_cos = max(cos_scores) if cos_scores else 0.0

    hybrid = SEMANTIC_WEIGHT * max_cos + LEXICAL_WEIGHT * max_lex
    return max_cos, max_lex, hybrid


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.65,
                        help="support_score threshold (default: 0.65)")
    args = parser.parse_args()
    threshold = args.threshold

    print(f"\nLoading embedder (jhgan/ko-sroberta-multitask)...")
    embedder = SentenceTransformerEmbedder()

    # Batch-encode facts
    print(f"Encoding {len(FACTS)} facts + {len(TESTS)} test sentences...")
    fact_vecs: list[list[float]] = [embedder.embed(f) for f in FACTS]

    all_sents = [t[0] for t in TESTS]
    sent_vecs: list[list[float]] = [embedder.embed(s) for s in all_sents]

    # ── Header ────────────────────────────────────────────────────────────────
    TRESH_STR = f"threshold={threshold:.2f}"
    SEP = "─" * 120
    HEADER = (
        f"{'#':>3}  "
        f"{'Category':<14} "
        f"{'Cosine':>7} "
        f"{'Lexical':>7} "
        f"{'Hybrid':>7}  "
        f"{'Supported':>9}  "
        f"{'Expected':>8}  "
        f"{'OK?':>4}  "
        f"Query"
    )
    print(f"\n{'NarrativeOS Verifier Benchmark':^120}")
    print(f"{'Model: jhgan/ko-sroberta-multitask  |  ' + TRESH_STR:^120}")
    print(SEP)
    print(HEADER)
    print(SEP)

    # ── Results ───────────────────────────────────────────────────────────────
    category_stats: dict[str, dict] = {}
    total_correct = 0

    for i, ((sent, cat, expected), sent_vec) in enumerate(zip(TESTS, sent_vecs), 1):
        cos, lex, hybrid = compute_scores(sent_vec, fact_vecs, sent, FACTS)
        supported = hybrid >= threshold
        correct = supported == expected

        ok_mark = "✓" if correct else "✗"
        sup_mark = "✓" if supported else "✗"
        exp_mark = "✓" if expected else "✗"

        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "correct": 0, "cos": [], "lex": [], "hyb": []}
        category_stats[cat]["total"] += 1
        category_stats[cat]["cos"].append(cos)
        category_stats[cat]["lex"].append(lex)
        category_stats[cat]["hyb"].append(hybrid)
        if correct:
            category_stats[cat]["correct"] += 1
            total_correct += 1

        print(
            f"{i:>3}.  "
            f"{cat:<14} "
            f"{cos:>7.3f} "
            f"{lex:>7.3f} "
            f"{hybrid:>7.3f}  "
            f"{sup_mark:>9}  "
            f"{exp_mark:>8}  "
            f"{ok_mark:>4}  "
            f"{sent[:48]}"
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    print(SEP)
    print(f"\n{'Category Summary':^120}")
    print(f"{'─'*80}")
    print(
        f"{'Category':<14}  "
        f"{'N':>3}  "
        f"{'Acc':>6}  "
        f"{'AvgCos':>7}  "
        f"{'AvgLex':>7}  "
        f"{'AvgHyb':>7}"
    )
    print(f"{'─'*60}")
    for cat, s in category_stats.items():
        n = s["total"]
        acc = s["correct"] / n
        print(
            f"{cat:<14}  "
            f"{n:>3}  "
            f"{acc:>6.0%}  "
            f"{sum(s['cos'])/n:>7.3f}  "
            f"{sum(s['lex'])/n:>7.3f}  "
            f"{sum(s['hyb'])/n:>7.3f}"
        )
    print(f"{'─'*60}")
    overall_acc = total_correct / len(TESTS)
    print(f"{'OVERALL':<14}  {len(TESTS):>3}  {overall_acc:>6.0%}")

    # ── Failure cases ─────────────────────────────────────────────────────────
    failures = [
        (i+1, TESTS[i][0], TESTS[i][1], TESTS[i][2], *compute_scores(sent_vecs[i], fact_vecs, TESTS[i][0], FACTS))
        for i in range(len(TESTS))
        if (compute_scores(sent_vecs[i], fact_vecs, TESTS[i][0], FACTS)[2] >= threshold) != TESTS[i][2]
    ]
    if failures:
        print(f"\n{'Failure Analysis':^80}")
        print(f"{'─'*80}")
        for idx, sent, cat, exp, cos, lex, hyb in failures:
            pred = hyb >= threshold
            print(
                f"  #{idx:02d} [{cat}]  cos={cos:.3f} lex={lex:.3f} hyb={hyb:.3f}  "
                f"pred={'✓' if pred else '✗'} exp={'✓' if exp else '✗'}"
            )
            print(f"       → \"{sent}\"")

    print(f"\nThreshold={threshold:.2f}  |  Overall accuracy: {overall_acc:.0%}  ({total_correct}/{len(TESTS)})")
    print()


if __name__ == "__main__":
    main()
