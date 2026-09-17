import re


def normalize_phone(raw):
    """Reduce a phone number to a canonical digits-only form for duplicate matching.

    '+27 11 903 2602', '011 903 2602' and '0119032602' all normalise to '0119032602';
    '+1 972-677-9560' and '(972) 677-9560' both normalise to '9726779560'.
    """
    digits = re.sub(r'\D', '', raw or '')
    if digits.startswith('27') and len(digits) == 11:
        return '0' + digits[2:]
    if digits.startswith('1') and len(digits) == 11:
        return digits[1:]
    return digits
