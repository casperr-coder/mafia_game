"""
Конфигурация бота Mafia Game Bot.
Загрузка переменных окружения и настройка параметров игры.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные из .env файла
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# Токен бота Telegram (получить у @BotFather)
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# Минимальное количество игроков для начала игры
# Для тестирования можно поставить 3 или 4, классический режим 5-6+
MIN_PLAYERS: int = int(os.getenv("MIN_PLAYERS", "3"))

# Длительность фаз в секундах
LOBBY_TIMEOUT: int = int(os.getenv("LOBBY_TIMEOUT", "120"))  # Время сбора лобби
NIGHT_TIMEOUT: int = int(os.getenv("NIGHT_TIMEOUT", "45"))    # Ночь (выбор ролей)
DAY_DISCUSSION_TIMEOUT: int = int(os.getenv("DAY_DISCUSSION_TIMEOUT", "45"))  # Дневное обсуждение
DAY_VOTING_TIMEOUT: int = int(os.getenv("DAY_VOTING_TIMEOUT", "40"))          # Голосование днем
