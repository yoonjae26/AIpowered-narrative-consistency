from backend.core.security import hash_password, verify_password


def create_password_hash(password: str) -> str:
	return hash_password(password)


def check_password(password: str, password_hash: str) -> bool:
	return verify_password(password, password_hash)
