"""
Обработчики личных сообщений (ЛС) с ботом: /start и ночные действия ролей.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from game_manager import game_manager
from roles import ROLE_INFO

logger = logging.getLogger(__name__)


async def cmd_start_pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start в личных сообщениях."""
    user = update.effective_user
    args = context.args
    bot_username = context.bot.username or "bot"

    # Если игрок перешел по ссылке для проверки ЛС перед игрой
    if args and args[0] == "check":
        welcome_text = (
            f"✅ <b>Отлично, {user.first_name}!</b>\n\n"
            f"Личные сообщения с ботом активированы. "
            f"Теперь вы сможете получать секретные роли и делать ночные ходы.\n\n"
            f"Возвращайтесь в группу и нажимайте <b>«Присоединиться»</b>!"
        )
    else:
        add_link = f"https://t.me/{bot_username}?startgroup=true"
        welcome_text = (
            f"🎩 <b>Приветствую, {user.first_name}!</b>\n\n"
            f"Я — бот для легендарной игры <b>«Мафия»</b> в групповых чатах Telegram.\n\n"
            f"<b>Как играть:</b>\n"
            f"1. Добавьте меня в группу с друзьями.\n"
            f"2. Дайте боту права отправлять сообщения.\n"
            f"3. Напишите в группе команду <b>/game</b>, чтобы начать сбор лобби!\n\n"
            f"<i>Здесь, в личных сообщениях, я буду присылать вам вашу роль и кнопки для ночных действий (убийство, проверка, лечение).</i>"
        )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ Добавить бота в группу",
                    url=f"https://t.me/{bot_username}?startgroup=true",
                )
            ],
            [
                InlineKeyboardButton("📜 Правила игры", callback_data="pm_rules"),
            ],
        ]
    )

    await update.effective_message.reply_text(
        welcome_text, reply_markup=keyboard, parse_mode=ParseMode.HTML
    )


async def handle_pm_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ночных действий и меню в личных сообщениях."""
    query = update.callback_query
    data = query.data
    user = query.from_user

    # 1. Просмотр правил в ЛС
    if data == "pm_rules":
        rules_text = (
            "📜 <b>Правила игры в Мафию</b>\n\n"
            "<b>Цель игры:</b>\n"
            "• <b>Мирные жители:</b> вычислить и казнить всю мафию днем на суде Линча.\n"
            "• <b>Мафия:</b> уничтожить мирных жителей до численного перевеса.\n\n"
            "<b>Роли:</b>\n"
        )
        for r_type, info in ROLE_INFO.items():
            rules_text += f"{info['emoji']} <b>{info['title']}</b>: {info['description']}\n\n"

        await query.answer()
        await query.message.reply_text(rules_text, parse_mode=ParseMode.HTML)
        return

    # 2. Обработка ночных действий
    # Формат data: night_{role}_{chat_id}_{target_id}
    if data.startswith("night_"):
        parts = data.split("_")
        if len(parts) >= 4:
            action_type = parts[1]  # mafia, sheriff, doctor, prostitute
            chat_id = int(parts[2])
            target_id = int(parts[3])

            game = game_manager.get_game(chat_id)
            if not game:
                await query.answer("Матч уже завершен или не найден.", show_alert=True)
                return

            success, resp = await game.handle_night_action(
                user_id=user.id,
                action_type=action_type,
                target_id=target_id,
            )

            await query.answer(resp if not success else "Выбор зафиксирован!")
            if success:
                # Обновляем сообщение в ЛС, чтобы зафиксировать выбор
                await query.edit_message_text(
                    text=f"✅ {resp}\n\n<i>Ожидайте наступления утра в общем чате.</i>",
                    parse_mode=ParseMode.HTML,
                )
