"""
Менеджер активных игр. Обеспечивает независимую работу игр в разных групповых чатах.
"""

from typing import Dict, Optional
from telegram import Bot

from game import Game
from models import GamePhase


class GameManager:
    def __init__(self):
        # chat_id -> Game
        self._games: Dict[int, Game] = {}

    def get_game(self, chat_id: int) -> Optional[Game]:
        return self._games.get(chat_id)

    def create_game(
        self, chat_id: int, chat_title: str, creator_id: int, bot: Bot
    ) -> Game:
        game = Game(
            chat_id=chat_id,
            chat_title=chat_title,
            creator_id=creator_id,
            bot=bot,
        )
        self._games[chat_id] = game
        return game

    def remove_game(self, chat_id: int) -> Optional[Game]:
        game = self._games.pop(chat_id, None)
        if game and game.timer_task and not game.timer_task.done():
            game.timer_task.cancel()
        return game

    def find_game_with_player(self, user_id: int) -> Optional[Game]:
        """Поиск активной игры, в которой участвует указанный игрок."""
        for game in self._games.values():
            if game.phase != GamePhase.FINISHED and user_id in game.players:
                return game
        return None


# Глобальный синглтон менеджера игр
game_manager = GameManager()
