import json
import yaml
import os
from openai import OpenAI, APIError
from models.schema import ExtractedData, VendorBid
from services.cleaner import clean_rfx_name, clean_price, clean_vendor_name

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
    _CONFIG = yaml.safe_load(f)

_MODEL = _CONFIG['llm']['model']
_MAX_TOKENS = _CONFIG['llm']['max_tokens']

_SYSTEM_PROMPT = """당신은 SAP 입찰 결과 HTML에서 구조화된 데이터를 추출하는 전문가입니다.
주어진 HTML 텍스트에서 아래 JSON 구조로 정확히 추출하세요.
숫자 금액은 쉼표와 '원' 단위 없이 순수 정수로 반환하세요.
업체가 여러 개이면 vendors 배열에 모두 포함하세요.

반환 형식 (JSON만 반환, 다른 텍스트 없음):
{
  "rfx_name": "RFx 명 또는 입찰명",
  "vendors": [
    {"name": "업체명", "unit_price": 1234000, "is_excluded": false}
  ],
  "selected_vendor": "낙찰 업체명",
  "final_price": 1234000,
  "payment_terms": "대금지급조건"
}"""


class LLMFallbackError(Exception):
    pass


def extract_with_llm(html_content: str, api_key: str, model: str = "") -> tuple:
    """Returns (ExtractedData, warnings). Raises LLMFallbackError on failure."""
    if not api_key:
        raise LLMFallbackError("OpenAI API 키가 설정되지 않았습니다.")

    use_model = model.strip() or _MODEL
    # Truncate HTML to avoid token limits (keep first ~8000 chars)
    text_content = html_content[:8000]

    client = OpenAI(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=use_model,
            max_tokens=_MAX_TOKENS,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"다음 내용에서 입찰 데이터를 추출해 주세요:\n\n{text_content}"},
            ],
        )
    except APIError as e:
        raise LLMFallbackError(f"OpenAI API 오류: {e}")

    raw = response.choices[0].message.content.strip()

    # Extract JSON block if wrapped in markdown
    import re
    match = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', raw)
    if match:
        raw = match.group(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise LLMFallbackError(f"LLM 응답 JSON 파싱 실패: {e}\n응답: {raw[:200]}")

    vendors = []
    for v in data.get('vendors', []):
        vendors.append(VendorBid(
            name=clean_vendor_name(v.get('name', '')),
            unit_price=clean_price(v.get('unit_price', 0)),
            is_excluded=v.get('is_excluded', False),
        ))

    rfx_name = data.get('rfx_name', '')
    if not rfx_name:
        raise LLMFallbackError("LLM이 rfx_name을 추출하지 못했습니다.")

    extracted = ExtractedData(
        rfx_name=rfx_name,
        rfx_name_clean=clean_rfx_name(rfx_name),
        vendors=vendors,
        selected_vendor=clean_vendor_name(data.get('selected_vendor', '')),
        final_price=clean_price(data.get('final_price', 0)),
        payment_terms=data.get('payment_terms', ''),
        extraction_method='llm_fallback',
    )
    return extracted, ["LLM 폴백으로 데이터를 추출했습니다. 결과를 검토해 주세요."]
