import io
import pypdf


def extract_pdf_text(file_bytes: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    if not pages:
        raise ValueError("PDF에서 텍스트를 추출할 수 없습니다. 스캔 이미지 PDF는 지원하지 않습니다.")
    return '\n'.join(pages)
