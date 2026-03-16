#!/usr/bin/env python3
"""SM-2 Spaced Repetition Algorithm implementation."""

from datetime import datetime, timedelta


def sm2(quality, repetitions=0, ease_factor=2.5, interval=0):
    """
    Calculate next review parameters using SM-2 algorithm.

    Args:
        quality: 0-5 rating of recall quality
            5 = perfect, instant recall
            4 = correct, slight hesitation
            3 = correct, serious difficulty
            2 = incorrect, seemed easy after seeing answer
            1 = incorrect, remembered after seeing answer
            0 = complete blackout
        repetitions: number of successful reviews (quality >= 3)
        ease_factor: current ease factor (starts at 2.5)
        interval: current interval in days

    Returns:
        dict with: repetitions, ease_factor, interval, next_review_date, status
    """
    quality = max(0, min(5, quality))

    # Update ease factor
    new_ef = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ef = max(1.3, new_ef)

    if quality < 3:
        # Failed — reset
        new_reps = 0
        new_interval = 1
    else:
        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = 6
        else:
            new_interval = round(interval * new_ef)
        new_reps = repetitions + 1

    next_review = datetime.now().date() + timedelta(days=new_interval)

    # Determine status
    if new_reps == 0:
        status = "Learning"
    elif new_interval >= 30:
        status = "Mastered"
    elif new_interval >= 6:
        status = "Review"
    else:
        status = "Learning"

    return {
        "repetitions": new_reps,
        "ease_factor": round(new_ef, 2),
        "interval_days": new_interval,
        "next_review": next_review.isoformat(),
        "status": status,
    }


def get_due_cards(cards):
    """Filter cards that are due for review today or earlier."""
    today = datetime.now().date()
    due = []
    for card in cards:
        next_review = card.get("next_review")
        if not next_review:
            due.append(card)  # New cards are always due
        else:
            review_date = datetime.fromisoformat(next_review).date() if isinstance(next_review, str) else next_review
            if review_date <= today:
                due.append(card)
    return due


if __name__ == "__main__":
    # Demo
    print("=== SM-2 Algorithm Demo ===\n")

    # Simulate reviewing a card multiple times
    reps, ef, interval = 0, 2.5, 0
    qualities = [4, 5, 3, 4, 5, 2, 4, 5]  # Simulated review scores

    for i, q in enumerate(qualities, 1):
        result = sm2(q, reps, ef, interval)
        print(f"Review {i}: quality={q} → interval={result['interval_days']}j, EF={result['ease_factor']}, status={result['status']}")
        reps = result["repetitions"]
        ef = result["ease_factor"]
        interval = result["interval_days"]
