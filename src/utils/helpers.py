def calculate_risk_band(score: float) -> str:
    """
    Translates a float probability (0-1) to a risk band.
    0.0 - 0.3: Low Risk
    0.3 - 0.7: Medium Risk
    0.7 - 1.0: High Risk
    """
    if score < 0.3:
        return "Low Risk"
    elif score < 0.7:
        return "Medium Risk"
    else:
        return "High Risk"

def format_percentage(value: float) -> str:
    """Formats a decimal value to percentage string."""
    return f"{value * 100:.1f}%"
