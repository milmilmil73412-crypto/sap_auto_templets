import re


def clean_rfx_name(name: str) -> str:
    # 직책 키워드(+님) 및 앞 단어(이름) + 앞의 "/","(" 포함 해당 위치부터 뒤 전체 제거
    # 매칭 패턴: [/ 또는 ( 또는 공백]+ + 이름단어 + 공백 + 직책키워드 + [님] + 나머지
    _TITLES = r'(책임|선임|반장|수석|사원|PL|피엘)'
    name = re.sub(rf'[\s/\(]+\S+\s+{_TITLES}님?(\s.*)?$', '', name)
    # 괄호 제거
    cleaned = re.sub(r'\(.*?\)', '', name)
    cleaned = re.sub(r'（.*?）', '', cleaned)  # 전각 괄호
    return cleaned.strip()


def clean_price(price_str: str) -> int:
    if isinstance(price_str, (int, float)):
        return int(price_str)
    text = str(price_str)
    text = re.sub(r'[,\s원₩]', '', text)
    text = re.sub(r'[^\d.]', '', text)
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def clean_vendor_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r'\s+', ' ', name)
    return name


def format_price(amount: int) -> str:
    return f"{amount:,}원"
