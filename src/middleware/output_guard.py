"""Output guard: checks any model-written wording before it is shown to a member or staff.

If wording breaks a rule (diagnosis, judging a reading, medication advice, posing as a clinician, predictions),
the orchestrator throws the model wording away and uses a safe template instead.
"""
import re

# Phrases that are allowed because they NEGATE the forbidden idea (e.g. "this is not a diagnosis").
_ALLOWED_PHRASES = [
    r"not a diagnosis", r"no diagnosis", r"not diagnos\w*", r"cannot diagnose", r"can't diagnose", r"can not diagnose",
    r"does not diagnose", r"do not diagnose", r"doesn't diagnose", r"not medical advice", r"never diagnose",
    r"not a clinician", r"not a doctor",
]

FORBIDDEN_PATTERNS = {
    "diagnosis": r"\bdiagnos\w*",
    "judging_a_reading": r"\b(dangerous|abnormal|life[- ]threatening|worrying|alarming|concerning)\b",
    "judging_a_reading_2": r"\b(is|are|was|were|looks?|seems?|appears?)\s+(normal|healthy|unhealthy|critical|serious|too high|too low|high|low|bad|good|fine|okay|ok)\b",
    "normal_range": r"\bnormal range\b|\bhealthy range\b|\btarget range\b",
    "medication_advice": r"\byou should (take|stop|increase|decrease|reduce|skip|start|double)\b|\b(increase|decrease|reduce|double|stop|skip|raise|lower) (your|the) (dose|dosage|medication|medicine|insulin|tablets?|pills?)\b",
    "posing_as_clinician": r"\bi am (a|your) (doctor|clinician|nurse|physician)\b|\bas your (doctor|clinician|nurse)\b",
    "prediction": r"\b(will|likely to|going to|could) (get worse|worsen|deteriorate)\b|\brisk of\b",
}


def _neutralise(text: str) -> str:
    t = text.lower()
    for p in _ALLOWED_PHRASES:
        t = re.sub(p, " ", t)
    return t


def check_text(text: str) -> list[str]:
    """Returns the list of violated rule names (empty list = text is acceptable)."""
    t = _neutralise(text or "")
    return [name for name, pattern in FORBIDDEN_PATTERNS.items() if re.search(pattern, t)]


_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def numbers_are_grounded(text: str, allowed: set[float]) -> bool:
    """Every number in the wording must come from the supplied facts. Dates, times and IDs are ignored."""
    t = re.sub(r"\b[A-Za-z]{1,4}-\d+\b", " ", text)          # IDs such as R-201, CP-301, EDU-401
    t = re.sub(r"\d{4}-\d{2}-\d{2}", " ", t)                  # ISO dates
    t = re.sub(r"\b\d{1,2}:\d{2}\b", " ", t)                  # times
    for token in _NUMBER_RE.findall(t):
        if float(token) not in allowed:
            return False
    return True
