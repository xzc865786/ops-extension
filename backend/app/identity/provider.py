from dataclasses import dataclass
from typing import Protocol


@dataclass
class Sub2APIUser:
    id: int
    username: str
    email: str
    role: str
    status: str


class IdentityProvider(Protocol):
    def verify_and_get_user(self, bearer_token: str) -> Sub2APIUser: ...
