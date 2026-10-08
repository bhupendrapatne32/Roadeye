from datetime import datetime, timezone
import math

# Baseline confidence values by severity
SEVERITY_BASE_CONFIDENCE = {
    "Low": 35,
    "Moderate": 45,
    "Critical": 60
}

# Exponential decay half-life in hours
DECAY_HALF_LIFE_HOURS = 12.0

def calculate_confidence(
    base_confidence: int,
    confirm_count: int,
    reject_count: int,
    created_at_iso: str,
    reporter_reputation: int = 50,
    has_photo: bool = False
) -> int:
    """
    Computes real-time dynamic confidence score:
    1. Base confidence influenced by reporter reputation and photo evidence.
    2. Crowdsourced upvotes (+15 each) and downvotes (-25 each).
    3. Half-life exponential time decay since last update / creation.
    """
    try:
        created_dt = datetime.fromisoformat(created_at_iso.replace("Z", "+00:00"))
        now_dt = datetime.now(timezone.utc)
        age_hours = max(0.0, (now_dt - created_dt).total_seconds() / 3600.0)
    except Exception:
        age_hours = 0.0

    # Reputation adjustment (-10 to +15)
    rep_bonus = (reporter_reputation - 50) * 0.2
    photo_bonus = 10 if has_photo else 0

    raw_score = base_confidence + rep_bonus + photo_bonus

    # Crowdsource impacts
    raw_score += (confirm_count - 1) * 15 # First confirm is original author
    raw_score -= reject_count * 30

    # Time decay multiplier: e^(-0.693 * t / half_life)
    decay_factor = math.exp(-0.693 * (age_hours / DECAY_HALF_LIFE_HOURS))
    score = raw_score * decay_factor

    # Bound between 0 and 100
    final_score = int(max(0, min(100, round(score))))
    return final_score

def determine_status(confidence_score: int, reject_count: int, confirm_count: int) -> str:
    """
    Returns hazard status:
    - 'RESOLVED' if confirmed gone by majority
    - 'EXPIRED' if confidence decayed below 15
    - 'LOW_CONFIDENCE' if score in [15, 39]
    - 'ACTIVE' if score >= 40
    """
    if reject_count >= 3 and reject_count > confirm_count:
        return "RESOLVED"
    if confidence_score < 15:
        return "EXPIRED"
    if confidence_score < 40:
        return "LOW_CONFIDENCE"
    return "ACTIVE"
