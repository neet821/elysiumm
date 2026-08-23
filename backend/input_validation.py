"""Shared validation rules for account fields accepted from clients."""

import unicodedata


MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 32
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_BYTES = 72


def validate_username(value: str) -> str:
    username = unicodedata.normalize("NFC", str(value or "")).strip()
    if not MIN_USERNAME_LENGTH <= len(username) <= MAX_USERNAME_LENGTH:
        raise ValueError("用户名长度必须为 3 到 32 个字符")
    if not username[0].isalnum():
        raise ValueError("用户名必须以字母或数字开头")
    if any(not (character.isalnum() or character in "_.-") for character in username):
        raise ValueError("用户名只能包含字母、数字、下划线、点和连字符")
    return username


def validate_new_password(value: str) -> str:
    password = str(value or "")
    encoded = password.encode("utf-8")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError("密码长度至少为 12 个字符")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError("密码的 UTF-8 长度不能超过 72 字节")
    if any(character.isspace() for character in password):
        raise ValueError("密码不能包含空白字符")
    if not any(character.isalpha() for character in password):
        raise ValueError("密码必须包含字母")
    if not any(character.isdigit() for character in password):
        raise ValueError("密码必须包含数字")
    return password


def password_bytes_for_bcrypt(value: str) -> bytes:
    password = str(value or "")
    encoded = password.encode("utf-8")
    if not encoded:
        raise ValueError("密码不能为空")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError("密码的 UTF-8 长度不能超过 72 字节")
    return encoded
