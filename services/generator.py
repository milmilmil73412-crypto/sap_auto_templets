from models.schema import DraftDocument

_CIRCLES = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def _circle(n: int) -> str:
    return _CIRCLES[n - 1] if 1 <= n <= len(_CIRCLES) else f"({n})"


def _is_construction(line_items: list) -> bool:
    """사업내역에 공사 관련 항목이 하나라도 있으면 공사 건으로 판단."""
    keywords = ['일반관리비 및 기업이윤', '재료비', '노무비']
    return any(any(kw in item for kw in keywords) for item in line_items)


def generate_draft_text(draft: DraftDocument) -> str:
    # 2. 구매품목
    if draft.line_items and _is_construction(draft.line_items):
        # 공사 건: RFx명(괄호 제외)을 단일 품목으로 표기
        item_block = f" {draft.item_name}"
    elif draft.line_items:
        # 일반 자재 건: 자재내역 ①②③ 목록
        items = "\n".join(f"{_circle(i+1)} {item}" for i, item in enumerate(draft.line_items))
        item_block = f"\n{items}"
    else:
        item_block = f" {draft.item_name}"

    # 6. 입찰 업체 순위 (항상 줄바꿈)
    rank_lines = "\n".join(
        f"   {row['순위']}순위: {row['업체명']} {row['입찰금액']}"
        for row in draft.vendor_rank_table
    )
    rank_block = f"\n{rank_lines}"

    lines = [
        f"1. 발주업체: {draft.order_vendor}",
        f"2. 구매품목:{item_block}",
        f"3. 대금지급조건: {draft.payment_terms or ''}",
        f"4. 납기일: {draft.delivery_date or ''}",
        f"5. 구매요청사유:\n{draft.purchase_reason}",
        f"6. 입찰 업체 순위:{rank_block}",
        f"7. 첨부 자료: {draft.attachments}",
    ]
    return "\n".join(lines)
