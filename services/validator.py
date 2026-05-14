import yaml
import os

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')

with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
    _CONFIG = yaml.safe_load(f)

MAX_SIZE_BYTES = _CONFIG['validation']['max_file_size_mb'] * 1024 * 1024
BLOCKED_PATTERNS = _CONFIG['security']['blocked_script_patterns']
ALLOWED_EXTENSIONS = _CONFIG['validation']['allowed_extensions']


class ValidationError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def validate_extension(filename: str):
    ext = os.path.splitext(filename.lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            'ERR_FORMAT',
            f"지원하지 않는 파일 형식입니다: '{ext}'. HTML 파일(.html)만 허용됩니다."
        )


def validate_size(file_bytes: bytes):
    if len(file_bytes) > MAX_SIZE_BYTES:
        mb = len(file_bytes) / (1024 * 1024)
        raise ValidationError(
            'ERR_SIZE',
            f"파일 크기({mb:.1f}MB)가 제한({_CONFIG['validation']['max_file_size_mb']}MB)을 초과합니다."
        )
    if len(file_bytes) == 0:
        raise ValidationError('ERR_FORMAT', "빈 파일입니다.")


def validate_security(content: str):
    content_lower = content.lower()
    for pattern in BLOCKED_PATTERNS:
        if pattern.lower() in content_lower:
            raise ValidationError(
                'ERR_SECURITY',
                f"보안 위협이 감지되었습니다: '{pattern}' 패턴이 포함되어 있습니다."
            )


def validate_upload(filename: str, file_bytes: bytes) -> str:
    """Validate and return decoded HTML content. Raises ValidationError on failure."""
    validate_extension(filename)
    validate_size(file_bytes)

    # Decode
    try:
        import chardet
        detected = chardet.detect(file_bytes)
        encoding = detected.get('encoding') or 'utf-8'
        content = file_bytes.decode(encoding, errors='replace')
    except Exception:
        content = file_bytes.decode('utf-8', errors='replace')

    validate_security(content)
    return content
