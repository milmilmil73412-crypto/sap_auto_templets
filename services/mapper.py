import yaml
import os
from models.schema import ExtractedData, DraftDocument
from services.cleaner import format_price
from services.sorter import sort_vendors

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
    _CONFIG = yaml.safe_load(f)

PURCHASE_REASON = _CONFIG['fixed_texts']['purchase_reason']
ATTACHMENTS = _CONFIG['fixed_texts']['attachments']


def map_to_draft(data: ExtractedData) -> tuple:
    """Returns (DraftDocument, warnings)."""
    warnings = []

    # '입찰정보 및 낙찰업체' 표에서 추출된 원본 순위·금액이 있으면 그대로 사용.
    # 없으면(fallback 경로) 가격 기준으로 재정렬·재번호 부여.
    active = [v for v in data.vendors if not v.is_excluded and v.unit_price > 0]
    has_html_ranks = bool(active) and all(
        v.rank is not None and v.rank > 0 for v in active
    )

    if has_html_ranks:
        sorted_vendors = sorted(active, key=lambda v: v.rank)
    else:
        sorted_vendors = sort_vendors(data.vendors)

    # 발주업체: 1순위 업체명
    rank1 = next((v for v in sorted_vendors if v.rank == 1), None)
    order_vendor = rank1.name if rank1 else (sorted_vendors[0].name if sorted_vendors else data.selected_vendor)

    vendor_rank_table = [
        {
            '순위': v.rank,
            '업체명': v.name,
            '입찰금액': format_price(v.unit_price),
        }
        for v in sorted_vendors
    ]

    missing = []
    if not order_vendor:
        missing.append('발주업체')
    if not data.rfx_name_clean:
        missing.append('구매품목')
    if not data.final_price:
        missing.append('발주금액')

    if missing:
        warnings.append(f"매핑 누락 항목이 있습니다: {', '.join(missing)} — 기안문 생성은 계속 진행됩니다.")

    draft = DraftDocument(
        order_vendor=order_vendor,
        item_name=data.rfx_name_clean,
        order_amount=format_price(data.final_price),
        payment_terms=data.payment_terms,
        delivery_date='',
        purchase_reason=PURCHASE_REASON,
        attachments=ATTACHMENTS,
        vendor_rank_table=vendor_rank_table,
        line_items=list(data.line_items),
    )
    return draft, warnings
