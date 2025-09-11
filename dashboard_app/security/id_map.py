"""Map ISIN/WKN codes to tradeable symbols.

This module provides a simple resolution layer converting an ISIN or WKN
into a tradeable ticker symbol. You should extend these dictionaries
with your own mappings as needed. For a production system you may
consult external services such as OpenFIGI to resolve identifiers on
the fly.
"""

from __future__ import annotations

from typing import Optional

# Example mappings. These should be expanded to cover the ETFs you
# follow. The keys should be uppercase. For ISINs this is always
# 12 alphanumeric characters. WKNs are typically six alphanumeric
# characters.
ISIN_TO_SYMBOL = {
    # iShares Edge MSCI World Momentum Factor UCITS ETF (Acc) – Xetra listing
    "IE00BP3QZ825": "IS3R.DE",
    # iShares Edge MSCI World Momentum Factor UCITS ETF (Acc) – LSE (GBP)
    "IE00BP3QZ825:GBP": "IWFM.L",
    # iShares Edge MSCI World Momentum Factor UCITS ETF (Acc) – LSE (USD)
    "IE00BP3QZ825:USD": "IWMO.L",
}

WKN_TO_SYMBOL = {
    # BYD Company (BYD) WKN (1211.HK not used on German exchanges). Example only.
    # "A0M4W9": "BYD.DE",
    # Add your own WKN mappings here.
}


def resolve_security(symbol_or_isin_or_wkn: str) -> Optional[str]:
    """Resolve a provided code into a tradeable symbol.

    If the input resembles an ISIN (12 alphanumeric characters) or is
    present in the ``ISIN_TO_SYMBOL`` or ``WKN_TO_SYMBOL`` dictionaries,
    the corresponding symbol is returned. Otherwise the input is
    returned unchanged, assuming it is already a trading symbol. ``None``
    indicates an unknown mapping.
    """
    if not symbol_or_isin_or_wkn:
        return None
    s = symbol_or_isin_or_wkn.strip().upper()
    # naive ISIN detection: 12 characters consisting of letters and numbers
    if len(s) == 12 and s.isalnum():
        if s in ISIN_TO_SYMBOL:
            return ISIN_TO_SYMBOL[s]
        return None
    # WKN detection: typical WKN codes are 6 alphanumeric characters
    if len(s) == 6 and s.isalnum():
        if s in WKN_TO_SYMBOL:
            return WKN_TO_SYMBOL[s]
        # Some ISINs embed WKN after the country code; handle DE000A... etc.
        # Add additional heuristics if needed.
    # Already a symbol
    return s