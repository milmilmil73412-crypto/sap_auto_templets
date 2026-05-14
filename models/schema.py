from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VendorBid:
    name: str
    unit_price: int
    rank: Optional[int] = None
    is_excluded: bool = False


@dataclass
class ExtractedData:
    rfx_name: str
    rfx_name_clean: str
    vendors: list = field(default_factory=list)   # list[VendorBid]
    selected_vendor: str = ""
    final_price: int = 0
    payment_terms: str = ""
    extraction_method: str = "dom"               # 'dom' | 'llm_fallback'
    line_items: list = field(default_factory=list)  # 사업내역 목록


@dataclass
class DraftDocument:
    order_vendor: str
    item_name: str       # RFx 명 (파일명 등 내부용)
    order_amount: str
    payment_terms: str
    delivery_date: str
    purchase_reason: str
    attachments: str
    vendor_rank_table: list = field(default_factory=list)  # list[dict]
    line_items: list = field(default_factory=list)          # 사업내역 목록 (구매품목 출력용)
    raw_text: str = ""
