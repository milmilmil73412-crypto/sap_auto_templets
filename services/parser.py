"""
SAP Ariba/SRM RFQ 결과 HTML 파서.

우선순위:
  1. 하단 "입찰 정보 및 낙찰업체" fieldset  ← 가장 신뢰성 높음
  2. 상단 업체별 입찰내역 표 (금액합계 행)
  3. 범용 테이블 파싱

RFx 명  : <td> - RFx 명 : <b>이름</b></td>
대금지급조건 : 기본정보 fieldset의 레이블-값 행
낙찰업체 : 하단 fieldset 순위 테이블 1순위 행
"""

import re
from bs4 import BeautifulSoup
from models.schema import ExtractedData, VendorBid
from services.cleaner import clean_rfx_name, clean_price, clean_vendor_name


# ── 예외 ────────────────────────────────────────────────────────────────────
class ParseError(Exception):
    def __init__(self, code: str, message: str, missing_fields: list = None):
        self.code = code
        self.message = message
        self.missing_fields = missing_fields or []
        super().__init__(message)


class MissingFieldsError(ParseError):
    def __init__(self, missing: list):
        super().__init__(
            'ERR_PARSE',
            f"필수 필드 추출 실패: {', '.join(missing)}",
            missing
        )


# ── RFx 명 ──────────────────────────────────────────────────────────────────
def _extract_rfx_name(soup: BeautifulSoup) -> str:
    # SAP: <td ...> - RFx 명 : <b>NAME</b></td>
    for td in soup.find_all('td'):
        txt = td.get_text()
        if 'RFx' in txt and ('명' in txt or 'Name' in txt) and ':' in txt:
            b = td.find('b')
            if b:
                val = b.get_text(strip=True)
                if len(val) > 3 and val not in ('RFQ', 'RFI', 'RFP', 'RFx'):
                    return val

    # 범용 fallback
    title = soup.find('title')
    if title:
        t = title.get_text(strip=True)
        if t:
            return t
    for tag in soup.find_all(['h1', 'h2', 'h3']):
        t = tag.get_text(strip=True)
        if t and len(t) > 3:
            return t
    return ''


# ── 대금지급조건 ─────────────────────────────────────────────────────────────
def _extract_payment_terms(soup: BeautifulSoup) -> str:
    # SAP: <tr> ... <td>- 대금지급조건</td><td>값</td> ...
    for tr in soup.find_all('tr'):
        cells = tr.find_all('td')
        for i, cell in enumerate(cells):
            if '대금지급조건' in cell.get_text(strip=True):
                for offset in range(1, 4):
                    j = i + offset
                    if j < len(cells):
                        val = cells[j].get_text(strip=True)
                        if val and not val.startswith('-') and len(val) > 1:
                            return val

    # 전체 텍스트 regex fallback
    text = soup.get_text(' ')
    m = re.search(r'대금지급조건\s*[-:：]?\s*([^\n-]{3,60})', text)
    if m:
        val = m.group(1).strip()
        if val and len(val) > 2:
            return val
    return ''


# ── 납기조건 ─────────────────────────────────────────────────────────────────
def _extract_delivery_condition(soup: BeautifulSoup) -> str:
    for tr in soup.find_all('tr'):
        cells = tr.find_all('td')
        for i, cell in enumerate(cells):
            txt = cell.get_text(strip=True)
            if txt in ('- 납기조건', '납기조건', '납기'):
                for offset in range(1, 4):
                    j = i + offset
                    if j < len(cells):
                        val = cells[j].get_text(strip=True)
                        if val and not val.startswith('-') and len(val) > 1:
                            return val
    return ''


# ── SAP 낙찰업체 섹션 ────────────────────────────────────────────────────────
def _parse_ranking_table(table) -> list:
    """
    '입찰정보 및 낙찰업체' 테이블 파싱.
    헤더 행(업체명 포함 행)을 먼저 찾아 '순위', '업체명', '입찰금액(최종)' 컬럼 위치를
    확정한 뒤, 데이터 행마다 해당 컬럼에서 값을 추출한다.
    Returns list[VendorBid]
    """
    rows = table.find_all('tr')
    if not rows:
        return []

    # ── 1. 헤더 행 탐색 (첫 5행 이내에서 '업체명' 포함 행) ──────────────────
    header_row_idx = None
    rank_col = 0
    name_col = None
    price_col = None
    header_texts = []

    for ri, row in enumerate(rows[:5]):
        texts = [c.get_text(strip=True) for c in row.find_all('td')]
        if '업체명' in texts:
            header_row_idx = ri
            header_texts = texts
            rank_col  = next((i for i, h in enumerate(texts) if '순위' in h), 0)
            name_col  = next((i for i, h in enumerate(texts) if h == '업체명'), None)
            # 입찰금액 컬럼 중 마지막(= 최종)
            price_idxs = [i for i, h in enumerate(texts) if '입찰금액' in h or ('금액' in h and '예정' not in h)]
            price_col = price_idxs[-1] if price_idxs else None
            break

    if name_col is None:
        # 헤더가 없는 경우: 업체코드 컬럼 다음을 업체명으로 추정
        # (순위=0, 업체코드=1, 업체명=2 기본 SAP 레이아웃)
        name_col = 2
    if price_col is None:
        price_col = -1  # 마지막 셀

    data_start = (header_row_idx + 1) if header_row_idx is not None else 0
    n_header = len(header_texts) if header_row_idx is not None else 0

    # ── 2. 데이터 행 추출 ────────────────────────────────────────────────────
    # 일부 SAP HTML은 첫 번째 컬럼('구분' 등)에 rowspan이 걸려 있어
    # 2순위+ 행은 TD가 1개 적다. n_header - len(cells) 만큼 인덱스를 앞으로 당긴다.
    vendors = []
    for row in rows[data_start:]:
        cells = row.find_all('td')
        if not cells:
            continue

        # 헤더 대비 셀 수 차이 → 컬럼 오프셋 계산
        offset = max(0, n_header - len(cells)) if n_header else 0
        adj_rank  = rank_col  - offset
        adj_name  = name_col  - offset
        adj_price = price_col - offset if price_col is not None else None

        if adj_rank < 0 or adj_rank >= len(cells):
            continue

        rank_text = cells[adj_rank].get_text(strip=True)
        rank_digits = re.sub(r'[^\d]', '', rank_text)
        if not rank_digits:
            continue
        rank = int(rank_digits)
        if rank <= 0:
            continue

        # 업체명: 오프셋 적용 후 name_col 사용
        if adj_name is not None and 0 <= adj_name < len(cells):
            name = clean_vendor_name(cells[adj_name].get_text(strip=True))
        else:
            name = ''

        # 입찰금액(최종)
        if adj_price is not None and 0 <= adj_price < len(cells):
            price = clean_price(cells[adj_price].get_text(strip=True))
        else:
            price = clean_price(cells[-1].get_text(strip=True))

        if name:
            vendors.append(VendorBid(name=name, unit_price=price, rank=rank))

    return vendors


def _extract_vendor_ranking_section(soup: BeautifulSoup) -> tuple:
    """
    '입찰정보 및 낙찰업체' 표에서 순위·업체명·입찰금액(최종)을 추출.
    전략 1: 낙찰 관련 fieldset 내부 테이블
    전략 2: 헤더에 '순위'+'업체명'+'금액'이 모두 있는 테이블
    Returns (vendors, selected_vendor, final_price)
    """
    # 전략 1: fieldset 기반 탐색
    for fieldset in soup.find_all('fieldset'):
        legend = fieldset.find('legend')
        if not legend:
            continue
        lt = legend.get_text()
        if '낙찰' not in lt and not ('입찰' in lt and '정보' in lt):
            continue
        table = fieldset.find('table')
        if not table:
            continue
        vendors = _parse_ranking_table(table)
        if vendors:
            vendors.sort(key=lambda v: v.rank or 999)
            return vendors, vendors[0].name, vendors[0].unit_price

    # 전략 2: 헤더에 순위+업체명+금액이 모두 있는 테이블 탐색
    for table in soup.find_all('table'):
        header_texts = [c.get_text(strip=True) for c in (table.find('tr') or {}).find_all('td')]
        if ('순위' in header_texts and '업체명' in header_texts
                and any('금액' in h for h in header_texts)):
            vendors = _parse_ranking_table(table)
            if vendors:
                vendors.sort(key=lambda v: v.rank or 999)
                return vendors, vendors[0].name, vendors[0].unit_price

    return [], '', 0


# ── SAP 업체별 입찰내역 메인 테이블 ──────────────────────────────────────────
def _extract_main_bid_table(soup: BeautifulSoup) -> tuple:
    """
    '업체별 입찰내역' fieldset의 메인 테이블에서 전체 업체 목록 파싱.
    헤더에서 업체명 추출 → 금액합계 행에서 최종 투찰가 추출.
    Returns (vendors, selected_vendor, final_price)
    """
    for fieldset in soup.find_all('fieldset'):
        legend = fieldset.find('legend')
        if not legend:
            continue
        legend_text = legend.get_text()
        if '입찰내역' not in legend_text and '업체별' not in legend_text and '시가별' not in legend_text:
            continue

        table = fieldset.find('table')
        if not table:
            continue

        rows = table.find_all('tr')
        if not rows:
            continue

        # ── 1. 헤더에서 업체명 추출 ─────────────────────────────────────────
        # SAP 구조: 헤더 3개 행 (번호 행 / 업체코드 행 / 업체명 행)
        vendor_names = []
        fixed_col_count = 0  # 순번, 사업내역, 수량, 목표가, 목표금액 = 5 cols

        for row in rows[:6]:  # 헤더는 앞 6행 이내
            cells = row.find_all(['td', 'th'])
            texts = [c.get_text(strip=True) for c in cells]
            if '업체명' in texts:
                nm_idx = texts.index('업체명')
                fixed_col_count = nm_idx  # 업체명 레이블 컬럼 위치
                vendor_names = [
                    clean_vendor_name(t) for t in texts[nm_idx + 1:]
                    if t and t not in ('업체명',)
                ]
                break

        if not vendor_names:
            continue

        # ── 2. 금액합계 행(노란색 #FFEB9C) 탐색 ──────────────────────────────
        # 해당 섹션에는 3개 부속 행: 최이, 최종, 낙찰여부
        in_total = False
        total_final = [0] * len(vendor_names)
        award_flags = [False] * len(vendor_names)

        for row in rows:
            cells = row.find_all('td')
            styles = ' '.join(c.get('style', '') for c in cells)
            row_text = row.get_text()

            # 금액합계 행 진입 감지 (노란색 배경)
            if '#FFEB9C' in styles and ('합계' in row_text or '합  계' in row_text or '합　계' in row_text):
                in_total = True

            if not in_total:
                continue

            # 최종 투찰가 행
            if '최종' in row_text and ('투찰' in row_text or '가' in row_text):
                price_vals = _extract_price_cells(cells, fixed_col_count, len(vendor_names))
                total_final = price_vals

            # 낙찰여부 행
            elif '낙찰여부' in row_text or ('[낙찰]' in row_text):
                for i, c in enumerate(cells):
                    cell_text = c.get_text(strip=True)
                    if '낙찰여부' in cell_text:
                        continue
                    if '[낙찰]' in cell_text or '낙찰' == cell_text:
                        # 이 셀의 인덱스가 vendor_names의 인덱스와 대응
                        v_idx = _vendor_col_index(i, fixed_col_count)
                        if 0 <= v_idx < len(award_flags):
                            award_flags[v_idx] = True
                in_total = False

        if not any(total_final):
            continue

        vendors = []
        selected_vendor = ''
        final_price = 0
        for i, name in enumerate(vendor_names):
            price = total_final[i] if i < len(total_final) else 0
            awarded = award_flags[i] if i < len(award_flags) else False
            is_excluded = (price == 0)
            vb = VendorBid(name=name, unit_price=price, is_excluded=is_excluded)
            vendors.append(vb)
            if awarded:
                selected_vendor = name
                final_price = price

        if not selected_vendor:
            active = [v for v in vendors if not v.is_excluded and v.unit_price > 0]
            if active:
                best = min(active, key=lambda v: v.unit_price)
                selected_vendor = best.name
                final_price = best.unit_price

        return vendors, selected_vendor, final_price

    return [], '', 0


def _extract_price_cells(cells: list, label_offset: int, n_vendors: int) -> list:
    """헤더 오프셋 이후의 금액 셀을 추출."""
    prices = []
    # 레이블 셀들을 건너뛰고 금액 셀만 추출
    # 금액 패턴: 숫자, 쉼표, 공백으로만 구성
    for cell in cells:
        txt = cell.get_text(strip=True).replace(',', '').replace(' ', '')
        if txt == '' or txt == '0':
            prices.append(0)
        elif re.match(r'^\d+$', txt):
            prices.append(int(txt))
        elif re.match(r'^\d+\.\d+$', txt):
            prices.append(int(float(txt)))

        if len(prices) >= n_vendors + label_offset:
            break

    # label_offset 이전 값 제거 (헤더 레이블 셀)
    if len(prices) > n_vendors:
        prices = prices[-n_vendors:]
    while len(prices) < n_vendors:
        prices.append(0)
    return prices[:n_vendors]


def _vendor_col_index(cell_idx: int, fixed_cols: int) -> int:
    """낙찰 셀 인덱스를 0-based 업체 인덱스로 변환."""
    return cell_idx - fixed_cols - 1


# ── 사업내역(구매품목) 목록 추출 ────────────────────────────────────────────
def _extract_line_items(soup: BeautifulSoup) -> list:
    """
    '업체별 입찰내역' fieldset의 메인 테이블에서 사업내역 항목 추출.
    - 순번(rowspan=2) 행의 두 번째 TD가 사업내역
    - 금액합계 행(rowspan=3 또는 '합계' 텍스트 포함) 제외
    """
    for fieldset in soup.find_all('fieldset'):
        legend = fieldset.find('legend')
        if not legend:
            continue
        legend_text = legend.get_text()
        if '입찰내역' not in legend_text and '업체별' not in legend_text and '시가별' not in legend_text:
            continue

        table = fieldset.find('table')
        if not table:
            continue

        items = []
        for tr in table.find_all('tr'):
            cells = tr.find_all('td')
            if len(cells) < 2:
                continue

            first = cells[0]
            first_text = first.get_text(strip=True)

            # 순번이 숫자인 셀만 (헤더 / 합계 제외)
            if not re.match(r'^\d+$', first_text):
                continue

            # rowspan=2 or 3 → 항목의 첫 행 (원가별=2, 품목별=3)
            if str(first.get('rowspan', '1')) not in ('2', '3'):
                continue

            item_text = cells[1].get_text(strip=True)
            # 합계 행 이중 체크
            if item_text and '합계' not in item_text:
                items.append(item_text)

        if items:
            return items

    return []


# ── 범용 테이블 파싱 (최후 fallback) ────────────────────────────────────────
def _extract_generic_table(soup: BeautifulSoup) -> tuple:
    _VENDOR_KW = ['업체', '공급업체', '벤더', '업체명', '회사명', 'vendor', 'supplier', '협력사']
    _PRICE_KW = ['금액', '단가', '입찰금액', '제출단가', '총금액', 'price', 'amount', '견적']
    _SEL_KW = ['낙찰', '선정', '최저가', 'awarded', 'selected']

    best_table, best_score = None, 0
    for table in soup.find_all('table'):
        headers = [th.get_text(strip=True) for th in table.find_all('th')]
        if not headers:
            fr = table.find('tr')
            if fr:
                headers = [td.get_text(strip=True) for td in fr.find_all(['td', 'th'])]
        score = sum(1 for kw in (_VENDOR_KW + _PRICE_KW)
                    if any(kw.lower() in h.lower() for h in headers))
        if score > best_score:
            best_score, best_table = score, table

    if not best_table or best_score == 0:
        return [], '', 0

    rows = best_table.find_all('tr')
    headers = [c.get_text(strip=True) for c in rows[0].find_all(['th', 'td'])]

    def cidx(kws):
        for i, h in enumerate(headers):
            if any(kw.lower() in h.lower() for kw in kws):
                return i
        return -1

    v_idx, p_idx, s_idx = cidx(_VENDOR_KW), cidx(_PRICE_KW), cidx(_SEL_KW)
    if v_idx == -1:
        return [], '', 0

    vendors, selected_vendor, final_price = [], '', 0
    for row in rows[1:]:
        cells = row.find_all(['td', 'th'])
        vals = [c.get_text(strip=True) for c in cells]
        name = clean_vendor_name(vals[v_idx]) if v_idx < len(vals) else ''
        if not name:
            continue
        price = clean_price(vals[p_idx]) if p_idx != -1 and p_idx < len(vals) else 0
        is_selected = (s_idx != -1 and s_idx < len(vals) and
                       bool(re.search(r'[✓✔○●]|선정|낙찰|Y', vals[s_idx])))
        is_excluded = bool(re.search(r'포기|무효|취소|미참여', row.get_text()))
        vb = VendorBid(name=name, unit_price=price, is_excluded=is_excluded)
        vendors.append(vb)
        if is_selected and not is_excluded:
            selected_vendor, final_price = name, price

    if vendors and not selected_vendor:
        active = [v for v in vendors if not v.is_excluded and v.unit_price > 0]
        if active:
            best = min(active, key=lambda v: v.unit_price)
            selected_vendor, final_price = best.name, best.unit_price

    return vendors, selected_vendor, final_price


# ── 메인 파싱 진입점 ─────────────────────────────────────────────────────────
def parse_html(content: str) -> tuple:
    """
    Returns (ExtractedData, warnings).
    Raises MissingFieldsError if critical fields cannot be extracted.
    """
    soup = BeautifulSoup(content, 'lxml')
    warnings = []

    rfx_name = _extract_rfx_name(soup)
    payment_terms = _extract_payment_terms(soup)
    delivery_condition = _extract_delivery_condition(soup)
    line_items = _extract_line_items(soup)

    # 전략 1: 하단 낙찰업체 섹션 (가장 신뢰도 높음)
    vendors, selected_vendor, final_price = _extract_vendor_ranking_section(soup)

    # 전략 2: 메인 입찰내역 테이블
    if not vendors:
        vendors, selected_vendor, final_price = _extract_main_bid_table(soup)
        if vendors:
            warnings.append("낙찰업체 섹션을 찾지 못해 입찰내역 테이블에서 추출했습니다.")

    # 전략 3: 범용 테이블
    if not vendors:
        vendors, selected_vendor, final_price = _extract_generic_table(soup)
        if vendors:
            warnings.append("SAP 전용 섹션을 찾지 못해 범용 테이블 파싱을 사용했습니다.")

    # 최저가 자동 선정
    if vendors and not selected_vendor:
        active = [v for v in vendors if not v.is_excluded and v.unit_price > 0]
        if active:
            best = min(active, key=lambda v: v.unit_price)
            selected_vendor, final_price = best.name, best.unit_price
            warnings.append("낙찰업체를 명시적으로 감지하지 못해 최저가 업체를 자동 선정했습니다.")

    if not payment_terms:
        warnings.append("대금지급조건을 자동 추출하지 못했습니다. 직접 입력해 주세요.")

    missing = [
        f for f, v in [
            ('rfx_name', rfx_name),
            ('vendors', vendors),
            ('selected_vendor', selected_vendor),
            ('final_price', final_price),
        ] if not v
    ]
    if missing:
        raise MissingFieldsError(missing)

    data = ExtractedData(
        rfx_name=rfx_name,
        rfx_name_clean=clean_rfx_name(rfx_name),
        vendors=vendors,
        selected_vendor=selected_vendor,
        final_price=final_price,
        payment_terms=payment_terms,
        extraction_method='dom',
        line_items=line_items,
    )
    # 납기조건을 payment_terms에 없으면 추가 메타로 보존
    if delivery_condition and '납기' not in (payment_terms or ''):
        data.payment_terms = payment_terms  # 별도 필드 없으므로 그대로

    return data, warnings
