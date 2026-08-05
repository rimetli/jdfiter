import hashlib
import re
from pathlib import Path

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:(?:\+?\s*8\s*6)[-\s]?)?1[-\s]*[3-9](?:[-\s]*\d){9}")
RESUME_TITLE_WORDS = {
    "个人信息", "个人简历", "求职简历", "简历", "基本信息", "个人简介",
    "教育背景", "教育经历", "工作经历", "工作经验", "项目经历", "项目经验",
    "核心能力", "专业技能", "技能特长", "自我评价", "求职意向", "联系方式",
}


def normalize(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def value_hash(value: str | None) -> str | None:
    normalized = normalize(value)
    return hashlib.sha256(normalized.lower().encode("utf-8")).hexdigest() if normalized else None


def normalize_phone(value: str | None) -> str | None:
    normalized = normalize(value)
    if normalized is None:
        return None
    digits = re.sub(r"\D", "", normalized)
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    return digits if len(digits) >= 7 else None


def _name_from_filename(filename: str) -> str | None:
    stem = Path(filename).stem.strip()
    match = re.search(r"】\s*([一-龥]{2,4})(?:[\s·-]*\d+\s*年?)?\s*$", stem)
    if match:
        return match.group(1)
    match = re.search(r"([一-龥]{2,4})\s*[-·]\s*\d+\s*年", stem)
    if match:
        return match.group(1)
    match = re.match(r"^([一-龥]{2,4})(?:\s+|\s*[-_·]\s*)(?:简历|resume|cv)?", stem, re.IGNORECASE)
    if match and match.group(1) not in RESUME_TITLE_WORDS:
        return match.group(1)
    return None


def extract_identity(text: str, filename: str) -> tuple[str | None, str | None, str | None]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    compact_text = re.sub(r"\s+", "", text)
    email = EMAIL_RE.search(text) or EMAIL_RE.search(compact_text)
    phone = PHONE_RE.search(text) or PHONE_RE.search(compact_text)
    name = None
    for line in lines[:12]:
        cleaned = re.sub(r"^(姓名|Name|name)[:：\s]*", "", line).strip()
        if EMAIL_RE.search(cleaned) or PHONE_RE.search(cleaned):
            continue
        explicit = re.match(r"^(?:姓名|Name|name)[:：\s]*([一-龥]{2,4})(?=\s|$)", line)
        if explicit:
            name = explicit.group(1)
            break
        if cleaned not in RESUME_TITLE_WORDS and re.fullmatch(r"[一-龥]{2,4}", cleaned):
            name = cleaned
            break
    if name is None or name in RESUME_TITLE_WORDS:
        name = _name_from_filename(filename) or name
    return name, email.group(0).lower() if email else None, normalize_phone(phone.group(0) if phone else None)
