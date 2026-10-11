"""
Модели данных для игры в Мафию.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict
import html

from roles import RoleType, ROLE_INFO, Team


class GamePhase(Enum):
    LOBBY = "lobby"
    NIGHT = "night"
    DAY_DISCUSSION = "day_discussion"
    DAY_VOTING = "day_voting"
    FINISHED = "finished"


@dataclass
class Player:
    user_id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    role: Optional[RoleType] = None
    is_alive: bool = True
    is_blocked: bool = False  # заблокирован ли путаной
    night_action_target_id: Optional[int] = None
    day_vote_target_id: Optional[int] = None

    @property
    def full_name(self) -> str:
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name

    @property
    def display_name(self) -> str:
        safe_name = html.escape(self.full_name)
        if self.username:
            return f"{safe_name} (@{self.username})"
        return safe_name

    @property
    def mention(self) -> str:
        safe_name = html.escape(self.full_name)
        return f'<a href="tg://user?id={self.user_id}">{safe_name}</a>'

    @property
    def role_title(self) -> str:
        if not self.role:
            return "Не назначена"
        info = ROLE_INFO[self.role]
        return f"{info['emoji']} {info['title']}"

    @property
    def team(self) -> Optional[Team]:
        if not self.role:
            return None
        return ROLE_INFO[self.role]["team"]

    def reset_round_state(self):
        """Сброс временных состояний раунда."""
        self.is_blocked = False
        self.night_action_target_id = None
        self.day_vote_target_id = None
