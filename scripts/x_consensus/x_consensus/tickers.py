"""股票代碼解析：把貼文裡寫的代碼／公司名對應到唯一的 ticker_key。

ticker_key 格式是 `<市場>:<代碼>`，例如 NASDAQ:AMD、KRX:005930。
用市場當前綴是因為六碼數字在韓國、上海、深圳都存在，只看數字會撞在一起。

這一層刻意做成確定性的（不呼叫模型），所以可以單獨測試，
也讓模型的職責縮小到「判斷立場」而不是「猜這是哪一檔」。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HOME = Path(__file__).resolve().parent.parent
ALIAS_PATH = HOME / "ticker_aliases.json"

# 美股 cashtag：$AMD。X 的 entities.symbols 已經幫我們抓好，這裡是備援。
CASHTAG_RE = re.compile(r"\$([A-Za-z]{1,5})(?:\.[A-Z])?\b")
# 亞股數字代碼：韓股／陸股六碼、台股四碼
KR_CN_RE = re.compile(r"\b(\d{6})\b")
TW_RE = re.compile(r"\b(\d{4})\b")

# 美股統一用 US，不細分 NASDAQ/NYSE：我們沒有可靠的交易所對照表，
# 硬猜只會在報告上印出錯的交易所（例如把 NYSE 的 PM 標成 NASDAQ）。
# yfinance 查價也不需要交易所前綴。
MARKET_SUFFIX = {
    "US": "",
    "KRX": ".KS", "KOSDAQ": ".KQ",
    "SSE": ".SS", "SZSE": ".SZ",
    "TWSE": ".TW", "TSE": ".T", "HKEX": ".HK",
    "STO": ".ST", "LSE": ".L", "EPA": ".PA", "TSXV": ".V",
    "XETRA": ".DE", "TPEX": ".TWO", "TADAWUL": ".SR", "AMS": ".AS", "HEL": ".HE",
    "SWX": ".SW", "VI": ".VI",
}
NUMERIC_MARKET_SYMBOLS = {
    'KRX': r'\d{6}', 'KOSDAQ': r'\d{6}', 'SSE': r'\d{6}',
    'SZSE': r'\d{6}', 'TWSE': r'\d{4}', 'TPEX': r'\d{4}',
    'HKEX': r'\d{4,5}', 'TADAWUL': r'\d{4}',
    'TSE': r'(?:\d{4}|\d{3}[A-Z])',
}

# 六碼數字的市場，用開頭幾碼判斷。這個規則不完美但涵蓋絕大多數常見標的。
def market_for_numeric(code: str) -> str | None:
    if len(code) != 6:
        return None
    if code[0] == "6":
        return "SSE"        # 上海（含 688 科創板）
    if code[0] in "03":
        # 000/002/300 是深圳，但韓股也有 000660(SK 海力士)、005930(三星)
        return "KRX" if code[:2] in {"00", "01", "03", "05", "06", "09"} and code[0] == "0" else "SZSE"
    return None


def _load_aliases() -> dict[str, str]:
    """別名 → ticker_key。檔案不存在就回空表，不讓管線因為缺設定而掛掉。"""
    if not ALIAS_PATH.exists():
        return {}
    raw = json.loads(ALIAS_PATH.read_text(encoding="utf-8"))
    return {alias.lower(): key for key, aliases in raw.items() for alias in aliases}


ALIASES = _load_aliases()


def resolve(symbol_as_written: str, company_name: str | None, market_guess: str | None) -> str | None:
    """回傳 ticker_key；解不出來回 None（交給人工補別名，不亂猜）。"""
    token = (symbol_as_written or "").strip().lstrip("$").upper()

    # Nasdaq's verified SKHY ADS is distinct from the Korean ordinary share.
    # A generic issuer-name alias must not replace an explicitly written ADS
    # ticker. Conflicting numeric-market guesses stay unresolved for review.
    if token == 'SKHY':
        supplied = (market_guess or '').upper()
        return 'US:SKHY' if supplied in {'', 'US', 'NASDAQ', 'NYSE', 'AMEX'} else None

    if company_name:
        hit = ALIASES.get(company_name.strip().lower())
        if hit:
            return hit
    if token and ALIASES.get(token.lower()):
        return ALIASES[token.lower()]

    if not token:
        return None

    # An explicit provider suffix carries its market; a conflicting supplied
    # market remains unresolved. Never infer a market from bare digits.
    for market, suffix in MARKET_SUFFIX.items():
        if suffix and token.endswith(suffix.upper()):
            supplied = (market_guess or '').upper()
            if supplied in MARKET_SUFFIX and supplied != market:
                return None
            return resolve(token[:-len(suffix)], None, market)

    if token.isdigit():
        if (market_guess or '').upper() == 'HKEX' and 1 <= len(token) <= 5:
            return f'HKEX:{token.zfill(4)}'
        if len(token) == 6:
            market = (market_guess or "").upper()
            if market not in NUMERIC_MARKET_SYMBOLS or not re.fullmatch(NUMERIC_MARKET_SYMBOLS[market], token):
                return None
            return f"{market}:{token}"
        # 四碼：台股與日股都用四碼，靠 market_guess 區分
        if len(token) == 4 and (market_guess or "").upper() in {"TWSE", "TPEX", "TSE", "HKEX", "TADAWUL"}:
            return f"{market_guess.upper()}:{token}"
        return None

    # Japanese exchanges now also use alphanumeric four-character codes.
    if (market_guess or '').upper() == 'TSE' and re.fullmatch(r'[0-9]{3}[A-Z]',token):
        return f'TSE:{token}'

    if re.fullmatch(r"[A-Z]{1,5}", token):
        market = (market_guess or "").upper()
        if market in NUMERIC_MARKET_SYMBOLS:
            return None
        if token == 'SIVE' and market != 'STO':
            return None
        if market in MARKET_SUFFIX:
            return f"{market}:{token}"
        if market and market not in {'NASDAQ', 'NYSE', 'AMEX'}:
            return None
        return f"US:{token}"

    return None


def yfinance_symbol(ticker_key: str) -> str | None:
    if ":" not in ticker_key:
        return None
    market, symbol = ticker_key.split(":", 1)
    if market in NUMERIC_MARKET_SYMBOLS and not re.fullmatch(NUMERIC_MARKET_SYMBOLS[market], symbol):
        return None
    suffix = MARKET_SUFFIX.get(market)
    return None if suffix is None else f"{symbol}{suffix}"


def extract_candidates(text: str, entity_symbols: list[str]) -> list[str]:
    """regex 候選層：只負責找出「可能是代碼」的字串，不判立場。"""
    found = {s.upper() for s in entity_symbols}
    found.update(m.group(1).upper() for m in CASHTAG_RE.finditer(text))
    found.update(m.group(1) for m in KR_CN_RE.finditer(text))
    return sorted(found)
