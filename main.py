"""
Главный входной файл для запуска Telegram-бота Mafia.
Использует библиотеку python-telegram-bot (v20+).
"""

import logging
import sys
from telegram import Update
from telegram.constants import ChatType
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import config
from handlers.group_handlers import (
    cmd_game,
    cmd_rules,
    cmd_status,
    cmd_stop_game,
    handle_group_callbacks,
)
from handlers.pm_handlers import cmd_start_pm, handle_pm_callbacks

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("MafiaBot")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Глобальный обработчик ошибок."""
    logger.error("Произошла ошибка при обработке обновления:", exc_info=context.error)


async def post_init(application) -> None:
    """Вызывается после инициализации бота."""
    bot_info = await application.bot.get_me()
    logger.info(f"Бот успешно запущен: @{bot_info.username} (ID: {bot_info.id})")
    print(f"==================================================")
    print(f" 🎩 Mafia Bot успешно запущен как @{bot_info.username}")
    print(f" Добавьте бота в группу и используйте команду /game")
    print(f"==================================================")


def main():
    if not config.BOT_TOKEN or config.BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("❌ ОШИБКА: BOT_TOKEN не указан!")
        print("Создайте бота через @BotFather в Telegram, скопируйте токен")
        print("и укажите его в файле .env (BOT_TOKEN=123456:ABC-DEF...)")
        sys.exit(1)

    # Инициализация приложения python-telegram-bot
    app = (
        ApplicationBuilder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # 1. Команды в личных сообщениях
    app.add_handler(
        CommandHandler("start", cmd_start_pm, filters=filters.ChatType.PRIVATE)
    )

    # 2. Общие команды (в группах и ЛС)
    app.add_handler(CommandHandler("rules", cmd_rules))
    app.add_handler(CommandHandler("help", cmd_rules))

    # 3. Игровые команды в группах
    app.add_handler(CommandHandler(["game", "start_mafia"], cmd_game))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stop_game", cmd_stop_game))

    # 4. Обработчики кнопок (Callback Queries)
    # Кнопки лобби и голосования в группах
    app.add_handler(
        CallbackQueryHandler(
            handle_group_callbacks,
            pattern=r"^(mafia_join|mafia_leave|mafia_start_game|vote_lynch_)",
        )
    )

    # Кнопки действий ролей и меню в ЛС
    app.add_handler(
        CallbackQueryHandler(
            handle_pm_callbacks,
            pattern=r"^(night_|pm_rules)",
        )
    )

    # Глобальный обработчик ошибок
    app.add_error_handler(error_handler)

    logger.info("Запуск Telegram Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
