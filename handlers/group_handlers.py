"""
Обработчики команд и событий в групповых чатах.
"""

import logging
from telegram import Update, InlineKeyboardMarkup
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

import config
from game_manager import game_manager
from models import GamePhase
from roles import ROLE_INFO

logger = logging.getLogger(__name__)


async def cmd_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет правила игры и описание ролей."""
    rules_text = (
        "📜 <b>Правила игры в Мафию</b>\n\n"
        "<b>Цель игры:</b>\n"
        "• <b>Мирные жители:</b> вычислить и казнить всю мафию днем на суде Линча.\n"
        "• <b>Мафия:</b> уничтожить мирных жителей, чтобы количество мафии сравнялось с числом горожан.\n\n"
        "<b>Фазы игры:</b>\n"
        "1. <b>Ночь:</b> Мафия выбирает жертву. Шериф проверяет подозрительных лиц. Доктор спасает раненого. Путана блокирует ночные ходы.\n"
        "2. <b>Утро:</b> Город просыпается, оглашаются ночные события (кто погиб, кого спасли).\n"
        "3. <b>День (Обсуждение):</b> Жители общаются в чате и высказывают подозрения.\n"
        "4. <b>Суд Линча (Голосование):</b> Все живые голосуют кнопками. Набравший большинство покидает игру.\n\n"
        "<b>🎭 Описание ролей:</b>\n"
    )
    for r_type, info in ROLE_INFO.items():
        rules_text += f"{info['emoji']} <b>{info['title']}</b> ({info['team'].value})\n{info['description']}\n\n"

    await update.effective_message.reply_text(rules_text, parse_mode=ParseMode.HTML)


async def cmd_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск набора игроков (лобби) в группу."""
    chat = update.effective_chat
    user = update.effective_user

    # Игра работает только в группах и супергруппах
    if chat.type == ChatType.PRIVATE:
        bot_username = context.bot.username or "bot"
        add_link = f"https://t.me/{bot_username}?startgroup=true"
        await update.effective_message.reply_text(
            "🎩 Игра в Мафию проводится в групповых чатах!\n\n"
            f"Добавьте бота в вашу группу по кнопке ниже:",
            reply_markup=InlineKeyboardMarkup(
                [[{"text": "➕ Добавить бота в группу", "url": add_link}]]
            ),
        )
        return

    # Проверяем, есть ли уже активная игра в этом чате
    existing_game = game_manager.get_game(chat.id)
    if existing_game and existing_game.phase != GamePhase.FINISHED:
        await update.effective_message.reply_text(
            "⚠️ В этом чате уже идет игра! Дождитесь окончания или отмените её командой /stop_game."
        )
        return

    # Создаем новую игру
    game = game_manager.create_game(
        chat_id=chat.id,
        chat_title=chat.title or "Групповой чат",
        creator_id=user.id,
        bot=context.bot,
    )

    # Добавляем создателя сразу в список участников
    game.add_player(user)

    bot_username = context.bot.username or ""
    text = game.get_lobby_text()
    keyboard = game.get_lobby_keyboard(bot_username)

    sent_msg = await update.effective_message.reply_text(
        text, reply_markup=keyboard, parse_mode=ParseMode.HTML
    )
    game.lobby_message_id = sent_msg.message_id


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает текущий статус матча."""
    chat = update.effective_chat
    game = game_manager.get_game(chat.id)

    if not game or game.phase == GamePhase.FINISHED:
        await update.effective_message.reply_text("В этом чате сейчас нет активной игры. Начните с /game")
        return

    alive = [p.display_name for p in game.alive_players]
    dead = [p.display_name for p in game.players.values() if not p.is_alive]

    status_text = (
        f"📊 <b>Статус игры (Раунд #{game.round_number}):</b>\n\n"
        f"Фаза: <b>{game.phase.value}</b>\n\n"
        f"🟢 <b>Живые ({len(alive)}):</b>\n" + ("\n".join(f"• {n}" for n in alive) if alive else "Никого") + "\n\n"
        f"💀 <b>Погибшие ({len(dead)}):</b>\n" + ("\n".join(f"• {n}" for n in dead) if dead else "Потерь нет")
    )
    await update.effective_message.reply_text(status_text, parse_mode=ParseMode.HTML)


async def cmd_stop_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Останавливает текущую игру (доступно создателю лобби или администраторам)."""
    chat = update.effective_chat
    user = update.effective_user

    game = game_manager.get_game(chat.id)
    if not game or game.phase == GamePhase.FINISHED:
        await update.effective_message.reply_text("Активная игра не найдена.")
        return

    # Проверка прав: создатель игры или администратор чата
    is_admin = False
    try:
        member = await chat.get_member(user.id)
        is_admin = member.status in ("creator", "administrator")
    except Exception:
        pass

    if user.id != game.creator_id and not is_admin:
        await update.effective_message.reply_text("❌ Только создатель игры или администратор чата может остановить игру.")
        return

    game_manager.remove_game(chat.id)
    await update.effective_message.reply_text("🛑 Игра была принудительно остановлена.")


async def handle_group_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок в группе (лобби и дневное голосование)."""
    query = update.callback_query
    data = query.data
    user = query.from_user
    chat = update.effective_chat

    if not chat:
        return

    game = game_manager.get_game(chat.id)
    if not game:
        await query.answer("Эта игра уже не существует или завершена.", show_alert=True)
        return

    # 1. Присоединиться к лобби
    if data == "mafia_join":
        success, msg = game.add_player(user)
        await query.answer(msg)
        if success:
            bot_username = context.bot.username or ""
            await query.edit_message_text(
                text=game.get_lobby_text(),
                reply_markup=game.get_lobby_keyboard(bot_username),
                parse_mode=ParseMode.HTML,
            )

    # 2. Выйти из лобби
    elif data == "mafia_leave":
        success, msg = game.remove_player(user.id)
        await query.answer(msg)
        if success:
            bot_username = context.bot.username or ""
            await query.edit_message_text(
                text=game.get_lobby_text(),
                reply_markup=game.get_lobby_keyboard(bot_username),
                parse_mode=ParseMode.HTML,
            )

    # 3. Начать игру
    elif data == "mafia_start_game":
        if len(game.players) < config.MIN_PLAYERS:
            await query.answer(
                f"Недостаточно игроков! Нужно минимум {config.MIN_PLAYERS}, сейчас: {len(game.players)}",
                show_alert=True,
            )
            return

        await query.answer("Запуск игры...")
        success, msg = await game.start_game()
        if not success:
            await query.answer(msg, show_alert=True)

    # 4. Дневное голосование (суд Линча)
    elif data.startswith("vote_lynch_"):
        parts = data.split("_")
        # format: vote_lynch_{chat_id}_{target_id}
        if len(parts) == 4:
            target_id = int(parts[3])
            success, resp = await game.handle_day_vote(user.id, target_id)
            await query.answer(resp, show_alert=not success)
