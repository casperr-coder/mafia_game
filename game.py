"""
Основной класс управления логикой матча Mafia (Game).
"""

import asyncio
import logging
import random
from collections import Counter
from typing import Dict, List, Optional, Tuple, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

import config
from models import GamePhase, Player
from roles import RoleType, ROLE_INFO, Team, get_role_distribution

logger = logging.getLogger(__name__)


class Game:
    def __init__(self, chat_id: int, chat_title: str, creator_id: int, bot: Bot):
        self.chat_id: int = chat_id
        self.chat_title: str = chat_title
        self.creator_id: int = creator_id
        self.bot: Bot = bot

        self.players: Dict[int, Player] = {}
        self.phase: GamePhase = GamePhase.LOBBY
        self.round_number: int = 0
        self.lobby_message_id: Optional[int] = None
        self.timer_task: Optional[asyncio.Task] = None

        # Хранилище ночных и дневных выборов
        # user_id -> target_user_id
        self.night_actions: Dict[int, int] = {}
        # voter_id -> target_id (или -1 для пропуска)
        self.day_votes: Dict[int, int] = {}

    @property
    def alive_players(self) -> List[Player]:
        return [p for p in self.players.values() if p.is_alive]

    @property
    def alive_mafia(self) -> List[Player]:
        return [p for p in self.alive_players if p.team == Team.MAFIA]

    @property
    def alive_citizens(self) -> List[Player]:
        return [p for p in self.alive_players if p.team == Team.CITIZENS]

    # ==========================================
    #             ЛОББИ (LOBBY)
    # ==========================================

    def add_player(self, user) -> Tuple[bool, str]:
        if self.phase != GamePhase.LOBBY:
            return False, "Игра уже началась!"
        if user.id in self.players:
            return False, "Вы уже присоединились к игре!"

        self.players[user.id] = Player(
            user_id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
        )
        return True, "Успешно!"

    def remove_player(self, user_id: int) -> Tuple[bool, str]:
        if self.phase != GamePhase.LOBBY:
            return False, "Нельзя покинуть игру во время матча!"
        if user_id not in self.players:
            return False, "Вы не участвуете в игре!"

        del self.players[user_id]
        return True, "Успешно!"

    def get_lobby_text(self) -> str:
        count = len(self.players)
        min_p = config.MIN_PLAYERS
        text = (
            f"🎩 <b>Набор игроков в Мафию!</b>\n\n"
            f"Чат: <b>{self.chat_title}</b>\n"
            f"Игроков собралось: <b>{count}</b> (минимум: {min_p})\n\n"
            f"<b>Список участников:</b>\n"
        )
        if not self.players:
            text += "<i>Пока никто не присоединился...</i>\n"
        else:
            for idx, p in enumerate(self.players.values(), 1):
                text += f"{idx}. {p.mention}\n"

        text += (
            f"\n⚠️ <b>Обязательно:</b> каждый участник должен нажать "
            f"кнопку <b>«Включить ЛС бота»</b> ниже, чтобы бот мог прислать секретную роль!\n"
        )
        return text

    def get_lobby_keyboard(self, bot_username: str) -> InlineKeyboardMarkup:
        pm_link = f"https://t.me/{bot_username}?start=check"
        keyboard = [
            [
                InlineKeyboardButton("✅ Присоединиться", callback_data="mafia_join"),
                InlineKeyboardButton("❌ Выйти", callback_data="mafia_leave"),
            ],
            [
                InlineKeyboardButton("💬 Включить ЛС бота", url=pm_link),
            ],
            [
                InlineKeyboardButton("🚀 Начать игру", callback_data="mafia_start_game"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)

    # ==========================================
    #            СТАРТ ИГРЫ И РОЛИ
    # ==========================================

    async def start_game(self) -> Tuple[bool, str]:
        if self.phase != GamePhase.LOBBY:
            return False, "Игра уже запущена!"
        if len(self.players) < config.MIN_PLAYERS:
            return (
                False,
                f"Недостаточно игроков! Нужно минимум {config.MIN_PLAYERS}, а сейчас {len(self.players)}.",
            )

        # Отменяем таймер сбора лобби, если был
        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()

        # Распределяем роли
        player_list = list(self.players.values())
        random.shuffle(player_list)
        roles = get_role_distribution(len(player_list))
        random.shuffle(roles)

        for p, role in zip(player_list, roles):
            p.role = role

        # Рассылаем роли в ЛС игрокам
        failed_dms: List[Player] = []
        for p in self.players.values():
            success = await self._send_role_dm(p)
            if not success:
                failed_dms.append(p)

        if failed_dms:
            failed_mentions = ", ".join(p.mention for p in failed_dms)
            msg = (
                f"⚠️ <b>Внимание!</b> Бот не смог отправить роль в ЛС следующим игрокам:\n"
                f"{failed_mentions}\n\n"
                f"Пожалуйста, запустите бота в личных сообщениях и начните заново!"
            )
            await self.bot.send_message(
                chat_id=self.chat_id, text=msg, parse_mode=ParseMode.HTML
            )
            # Сбрасываем роли и возвращаем в лобби
            for p in self.players.values():
                p.role = None
            return False, "Не все игроки активировали бота в ЛС!"

        # Роли успешно розданы, начинаем игру!
        self.phase = GamePhase.NIGHT
        self.round_number = 0

        roles_summary = []
        for r_type in set(roles):
            info = ROLE_INFO[r_type]
            count = roles.count(r_type)
            roles_summary.append(f"{info['emoji']} {info['title']}: {count}")

        intro_text = (
            f"🎉 <b>Игра началась! В игре {len(self.players)} жителей.</b>\n\n"
            f"<b>Роли в этом матче:</b>\n"
            + "\n".join(roles_summary)
            + "\n\n<i>Роли отправлены всем участникам в личные сообщения. "
            "Никому не раскрывайте свою тайну!</i>"
        )
        await self.bot.send_message(
            chat_id=self.chat_id, text=intro_text, parse_mode=ParseMode.HTML
        )

        # Переход к первой ночи
        await self.start_night()
        return True, "Игра успешно началась!"

    async def _send_role_dm(self, player: Player) -> bool:
        """Отправляет описание роли игроку в личные сообщения."""
        if not player.role:
            return False

        info = ROLE_INFO[player.role]
        text = (
            f"🎭 <b>Ваша роль в чате «{self.chat_title}»:</b>\n\n"
            f"<b>{info['emoji']} {info['title']}</b>\n"
            f"Команда: <b>{info['team'].value}</b>\n\n"
            f"📖 <i>{info['description']}</i>\n"
        )

        # Если мафия, сообщаем сообщников
        if player.team == Team.MAFIA:
            all_mafia = [
                p.display_name for p in self.players.values() if p.team == Team.MAFIA
            ]
            if len(all_mafia) > 1:
                text += f"\n👥 <b>Ваши сообщники (Мафия):</b>\n" + "\n".join(
                    f"• {m}" for m in all_mafia
                )
            else:
                text += "\n👤 Вы — единственный представитель мафии в этом городе."

        try:
            await self.bot.send_message(
                chat_id=player.user_id, text=text, parse_mode=ParseMode.HTML
            )
            return True
        except TelegramError as e:
            logger.warning(
                f"Не удалось отправить ЛС игроку {player.user_id} ({player.full_name}): {e}"
            )
            return False

    # ==========================================
    #               НОЧЬ (NIGHT)
    # ==========================================

    async def start_night(self):
        self.round_number += 1
        self.phase = GamePhase.NIGHT
        self.night_actions.clear()

        # Сброс временных состояний
        for p in self.alive_players:
            p.reset_round_state()

        msg = (
            f"🌃 <b>Наступила ночь №{self.round_number}</b>\n\n"
            f"<i>Город засыпает... Просыпается мафия и особые службы.</i>\n\n"
            f"У активных ролей есть <b>{config.NIGHT_TIMEOUT} секунд</b>, "
            f"чтобы сделать свой выбор через кнопки в ЛС бота!"
        )
        await self.bot.send_message(
            chat_id=self.chat_id, text=msg, parse_mode=ParseMode.HTML
        )

        # Рассылка кнопок действий в ЛС
        for player in self.alive_players:
            if not player.role:
                continue

            # Мафия выбирает жертву
            if player.role in (RoleType.MAFIA, RoleType.DON):
                await self._send_mafia_night_menu(player)
            # Шериф проверяет игрока
            elif player.role == RoleType.SHERIFF:
                await self._send_sheriff_night_menu(player)
            # Доктор лечит игрока
            elif player.role == RoleType.DOCTOR:
                await self._send_doctor_night_menu(player)
            # Путана блокирует игрока
            elif player.role == RoleType.PROSTITUTE:
                await self._send_prostitute_night_menu(player)

        # Запускаем таймер ночи
        self.timer_task = asyncio.create_task(self._night_timer())

    async def _send_mafia_night_menu(self, player: Player):
        # Цели для мафии: любые живые не-мафиози
        targets = [p for p in self.alive_players if p.team != Team.MAFIA]
        if not targets:
            return

        buttons = [
            [
                InlineKeyboardButton(
                    f"🎯 {t.full_name}",
                    callback_data=f"night_mafia_{self.chat_id}_{t.user_id}",
                )
            ]
            for t in targets
        ]
        keyboard = InlineKeyboardMarkup(buttons)
        text = "🌃 <b>Ночь №{}: Мафия выбирает жертву.</b>\nКого ликвидируем?".format(
            self.round_number
        )
        try:
            await self.bot.send_message(
                chat_id=player.user_id,
                text=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
        except TelegramError as e:
            logger.error(f"Ошибка отправки ночного меню мафии: {e}")

    async def _send_sheriff_night_menu(self, player: Player):
        # Шериф может проверить любого живого игрока, кроме себя
        targets = [p for p in self.alive_players if p.user_id != player.user_id]
        buttons = [
            [
                InlineKeyboardButton(
                    f"🔍 {t.full_name}",
                    callback_data=f"night_sheriff_{self.chat_id}_{t.user_id}",
                )
            ]
            for t in targets
        ]
        keyboard = InlineKeyboardMarkup(buttons)
        text = "🕵️‍♂️ <b>Ночь №{}: Шериф выходит на расследование.</b>\nКого проверить?".format(
            self.round_number
        )
        try:
            await self.bot.send_message(
                chat_id=player.user_id,
                text=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
        except TelegramError as e:
            logger.error(f"Ошибка отправки меню шерифу: {e}")

    async def _send_doctor_night_menu(self, player: Player):
        # Доктор может лечить любого живого игрока (включая себя)
        targets = self.alive_players
        buttons = [
            [
                InlineKeyboardButton(
                    f"💊 {t.full_name}",
                    callback_data=f"night_doctor_{self.chat_id}_{t.user_id}",
                )
            ]
            for t in targets
        ]
        keyboard = InlineKeyboardMarkup(buttons)
        text = "🩺 <b>Ночь №{}: Доктор на дежурстве.</b>\nКого спасти этой ночью?".format(
            self.round_number
        )
        try:
            await self.bot.send_message(
                chat_id=player.user_id,
                text=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
        except TelegramError as e:
            logger.error(f"Ошибка отправки меню доктору: {e}")

    async def _send_prostitute_night_menu(self, player: Player):
        # Путана может навестить любого, кроме себя
        targets = [p for p in self.alive_players if p.user_id != player.user_id]
        buttons = [
            [
                InlineKeyboardButton(
                    f"💋 {t.full_name}",
                    callback_data=f"night_prostitute_{self.chat_id}_{t.user_id}",
                )
            ]
            for t in targets
        ]
        keyboard = InlineKeyboardMarkup(buttons)
        text = "💃 <b>Ночь №{}: Путана выбирает компанию.</b>\nК кому пойти в гости?".format(
            self.round_number
        )
        try:
            await self.bot.send_message(
                chat_id=player.user_id,
                text=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
        except TelegramError as e:
            logger.error(f"Ошибка отправки меню путане: {e}")

    async def handle_night_action(
        self, user_id: int, action_type: str, target_id: int
    ) -> Tuple[bool, str]:
        """Обработка выбора ночного действия от игрока."""
        if self.phase != GamePhase.NIGHT:
            return False, "Сейчас не ночь!"

        player = self.players.get(user_id)
        if not player or not player.is_alive:
            return False, "Вы не можете совершать действия."

        target = self.players.get(target_id)
        if not target or not target.is_alive:
            return False, "Выбранный игрок уже мертв или не существует!"

        player.night_action_target_id = target_id
        self.night_actions[user_id] = target_id

        # Ответ игроку
        if action_type == "mafia":
            response = f"🎯 Ваша цель: <b>{target.full_name}</b>. Ожидайте наступления утра."
        elif action_type == "sheriff":
            response = f"🔍 Вы следите за <b>{target.full_name}</b>. Результат будет готов к рассвету."
        elif action_type == "doctor":
            response = f"💊 Вы оказали помощь игроку <b>{target.full_name}</b>."
        elif action_type == "prostitute":
            response = f"💋 Вы провели незабываемую ночь с <b>{target.full_name}</b>."
        else:
            response = "Выбор принят."

        # Проверяем, все ли активные ночные роли проголосовали
        if self._all_night_actions_collected():
            if self.timer_task and not self.timer_task.done():
                self.timer_task.cancel()
            asyncio.create_task(self.resolve_night())

        return True, response

    def _all_night_actions_collected(self) -> bool:
        """Проверяет, сделали ли все живые активные ночные роли свой ход."""
        for p in self.alive_players:
            if p.role in (
                RoleType.MAFIA,
                RoleType.DON,
                RoleType.SHERIFF,
                RoleType.DOCTOR,
                RoleType.PROSTITUTE,
            ):
                if p.night_action_target_id is None:
                    return False
        return True

    async def _night_timer(self):
        try:
            await asyncio.sleep(config.NIGHT_TIMEOUT)
            await self.resolve_night()
        except asyncio.CancelledError:
            pass

    # ==========================================
    #         РАЗРЕШЕНИЕ НОЧИ И УТРО
    # ==========================================

    async def resolve_night(self):
        if self.phase != GamePhase.NIGHT:
            return

        morning_events: List[str] = []

        # 1. Действие путаны (блокировка)
        prostitute = next(
            (p for p in self.alive_players if p.role == RoleType.PROSTITUTE), None
        )
        blocked_user_id: Optional[int] = None
        if prostitute and prostitute.night_action_target_id:
            blocked_user_id = prostitute.night_action_target_id
            blocked_player = self.players.get(blocked_user_id)
            if blocked_player:
                blocked_player.is_blocked = True
                try:
                    await self.bot.send_message(
                        chat_id=blocked_user_id,
                        text="💋 <i>Этой ночью к вам заглянула Путана. Вы увлечены и пропустили ночные дела!</i>",
                        parse_mode=ParseMode.HTML,
                    )
                except TelegramError:
                    pass

        # 2. Проверка шерифа
        sheriff = next(
            (p for p in self.alive_players if p.role == RoleType.SHERIFF), None
        )
        if sheriff and sheriff.night_action_target_id:
            if sheriff.is_blocked:
                result_text = "🕵️‍♂️ <i>Вы были заблокированы этой ночью и не смогли провести проверку!</i>"
            else:
                target = self.players.get(sheriff.night_action_target_id)
                if target:
                    if target.team == Team.MAFIA:
                        result_text = (
                            f"🕵️‍♂️ <b>Результат проверки:</b>\n"
                            f"Игрок <b>{target.full_name}</b> — 😈 <b>МАФИЯ!</b>"
                        )
                    else:
                        result_text = (
                            f"🕵️‍♂️ <b>Результат проверки:</b>\n"
                            f"Игрок <b>{target.full_name}</b> — 🕊️ <b>Мирный житель</b>."
                        )
                else:
                    result_text = "🕵️‍♂️ Не удалось проверить игрока."
            try:
                await self.bot.send_message(
                    chat_id=sheriff.user_id,
                    text=result_text,
                    parse_mode=ParseMode.HTML,
                )
            except TelegramError:
                pass

        # 3. Выбор мафии (убийство)
        mafia_votes = [
            p.night_action_target_id
            for p in self.alive_mafia
            if p.night_action_target_id and not p.is_blocked
        ]
        kill_target_id: Optional[int] = None
        if mafia_votes:
            # Находим цель с наибольшим числом голосов
            vote_counts = Counter(mafia_votes)
            kill_target_id = vote_counts.most_common(1)[0][0]

        # 4. Лечение доктора
        doctor = next(
            (p for p in self.alive_players if p.role == RoleType.DOCTOR), None
        )
        healed_target_id: Optional[int] = None
        if doctor and doctor.night_action_target_id and not doctor.is_blocked:
            healed_target_id = doctor.night_action_target_id

        # 5. Итог убийства
        victim: Optional[Player] = None
        if kill_target_id:
            victim = self.players.get(kill_target_id)
            if victim and kill_target_id == healed_target_id:
                # Спасен доктором!
                morning_events.append(
                    "🩺 <b>Доктор совершил чудо!</b> Этой ночью нападение мафии было предотвращено, "
                    "никто не пострадал!"
                )
            elif victim:
                victim.is_alive = False
                morning_events.append(
                    f"💀 <b>Кровавое утро...</b> Этой ночью мафия жестоко расправилась с игроком "
                    f"{victim.mention}.\nОн был: <b>{victim.role_title}</b>."
                )
        else:
            morning_events.append("🕊️ <b>Тихая ночь...</b> Никто не погиб.")

        # Публикуем утреннюю сводку
        morning_text = (
            f"☀️ <b>Наступило утро дня №{self.round_number}!</b>\n\n"
            + "\n\n".join(morning_events)
        )
        await self.bot.send_message(
            chat_id=self.chat_id, text=morning_text, parse_mode=ParseMode.HTML
        )

        # Проверяем условие победы после ночи
        if await self.check_win_conditions():
            return

        # Переходим к дневному обсуждению
        await self.start_day_discussion()

    # ==========================================
    #       ДЕНЬ: ОБСУЖДЕНИЕ И ГОЛОСОВАНИЕ
    # ==========================================

    async def start_day_discussion(self):
        self.phase = GamePhase.DAY_DISCUSSION

        alive_list = "\n".join(f"• {p.mention}" for p in self.alive_players)
        msg = (
            f"🗣 <b>Дневное обсуждение (День №{self.round_number})</b>\n\n"
            f"Живые жители:\n{alive_list}\n\n"
            f"У вас есть <b>{config.DAY_DISCUSSION_TIMEOUT} секунд</b> на поиск подозреваемых и споры.\n"
            f"После этого начнется суд Линча (голосование)!"
        )
        await self.bot.send_message(
            chat_id=self.chat_id, text=msg, parse_mode=ParseMode.HTML
        )

        self.timer_task = asyncio.create_task(self._day_discussion_timer())

    async def _day_discussion_timer(self):
        try:
            await asyncio.sleep(config.DAY_DISCUSSION_TIMEOUT)
            await self.start_day_voting()
        except asyncio.CancelledError:
            pass

    async def start_day_voting(self):
        self.phase = GamePhase.DAY_VOTING
        self.day_votes.clear()

        # Кнопки для голосования в общем чате
        buttons = []
        for p in self.alive_players:
            buttons.append(
                [
                    InlineKeyboardButton(
                        f"⚖️ {p.full_name}",
                        callback_data=f"vote_lynch_{self.chat_id}_{p.user_id}",
                    )
                ]
            )
        buttons.append(
            [
                InlineKeyboardButton(
                    "⚪️ Воздержаться (Пропустить)",
                    callback_data=f"vote_lynch_{self.chat_id}_-1",
                )
            ]
        )
        keyboard = InlineKeyboardMarkup(buttons)

        msg = (
            f"⚖️ <b>Суд Линча начался!</b>\n\n"
            f"Каждый живой житель должен проголосовать, кого исключить из города.\n"
            f"Время на голосование: <b>{config.DAY_VOTING_TIMEOUT} секунд</b>."
        )
        await self.bot.send_message(
            chat_id=self.chat_id,
            text=msg,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )

        self.timer_task = asyncio.create_task(self._day_voting_timer())

    async def handle_day_vote(
        self, voter_id: int, target_id: int
    ) -> Tuple[bool, str]:
        if self.phase != GamePhase.DAY_VOTING:
            return False, "Сейчас не идет голосование!"

        voter = self.players.get(voter_id)
        if not voter or not voter.is_alive:
            return False, "Вы не можете голосовать!"

        self.day_votes[voter_id] = target_id
        voter.day_vote_target_id = target_id

        if target_id == -1:
            resp = "Вы воздержались от голосования."
        else:
            target = self.players.get(target_id)
            resp = f"Ваш голос против: {target.full_name if target else 'Игрок'}!"

        # Если все живые игроки проголосовали, завершаем досрочно
        if len(self.day_votes) >= len(self.alive_players):
            if self.timer_task and not self.timer_task.done():
                self.timer_task.cancel()
            asyncio.create_task(self.resolve_day_voting())

        return True, resp

    async def _day_voting_timer(self):
        try:
            await asyncio.sleep(config.DAY_VOTING_TIMEOUT)
            await self.resolve_day_voting()
        except asyncio.CancelledError:
            pass

    async def resolve_day_voting(self):
        if self.phase != GamePhase.DAY_VOTING:
            return

        # Подсчет голосов
        if not self.day_votes:
            summary_text = "⚖️ <b>Итоги голосования:</b> никто не проголосовал. День прошел впустую."
            lynched_player = None
        else:
            counts = Counter(self.day_votes.values())
            # Выводим кто за кого проголосовал
            vote_lines = []
            for t_id, cnt in counts.most_common():
                if t_id == -1:
                    vote_lines.append(f"• Воздержались: <b>{cnt}</b> голосов")
                else:
                    t_player = self.players.get(t_id)
                    name = t_player.full_name if t_player else "Неизвестный"
                    vote_lines.append(f"• {name}: <b>{cnt}</b> голосов")

            top_candidate, top_count = counts.most_common(1)[0]
            # Проверяем ничью
            top_ties = [t for t, c in counts.items() if c == top_count]

            if top_candidate == -1:
                summary_text = (
                    "⚖️ <b>Итоги суда:</b>\n"
                    + "\n".join(vote_lines)
                    + "\n\nБольшинство решило воздержаться. Никто не казнен."
                )
                lynched_player = None
            elif len(top_ties) > 1:
                summary_text = (
                    "⚖️ <b>Итоги суда:</b>\n"
                    + "\n".join(vote_lines)
                    + "\n\nГолоса разделились поровну! Суд не вынес решения, никто не казнен."
                )
                lynched_player = None
            else:
                lynched_player = self.players.get(top_candidate)
                lynched_player.is_alive = False
                summary_text = (
                    "⚖️ <b>Итоги суда:</b>\n"
                    + "\n".join(vote_lines)
                    + f"\n\nПо решению большинства казнен игрок {lynched_player.mention}.\n"
                    f"Его роль была: <b>{lynched_player.role_title}</b>!"
                )

        await self.bot.send_message(
            chat_id=self.chat_id, text=summary_text, parse_mode=ParseMode.HTML
        )

        # Проверка победы после суда
        if await self.check_win_conditions():
            return

        # Иначе переходим к следующей ночи
        await self.start_night()

    # ==========================================
    #          ПРОВЕРКА ПОБЕДЫ И ФИНАЛ
    # ==========================================

    async def check_win_conditions(self) -> bool:
        mafia_count = len(self.alive_mafia)
        citizens_count = len(self.alive_citizens)

        winner_team: Optional[Team] = None

        if mafia_count == 0:
            winner_team = Team.CITIZENS
        elif mafia_count >= citizens_count:
            winner_team = Team.MAFIA

        if winner_team:
            await self.finish_game(winner_team)
            return True
        return False

    async def finish_game(self, winner_team: Team):
        self.phase = GamePhase.FINISHED
        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()

        if winner_team == Team.MAFIA:
            title = "🕶️ <b>ПОБЕДА МАФИИ!</b> 🔫"
            desc = "Мафия взяла полный контроль над городом. Закон пал!"
        else:
            title = "🕊️ <b>ПОБЕДА МИРНЫХ ЖИТЕЛЕЙ!</b> 🎉"
            desc = "Все мафиози ликвидированы! В городе воцарился порядок и покой."

        # Раскрываем роли всех участников
        roles_reveal = []
        for p in self.players.values():
            status = "Жив" if p.is_alive else "Погиб 🪦"
            roles_reveal.append(
                f"• {p.display_name} — <b>{p.role_title}</b> [{status}]"
            )

        final_msg = (
            f"🏆 {title}\n\n"
            f"{desc}\n\n"
            f"📋 <b>Роли всех участников:</b>\n"
            + "\n".join(roles_reveal)
            + "\n\nСпасибо за игру! Чтобы сыграть снова, напишите /game"
        )
        await self.bot.send_message(
            chat_id=self.chat_id, text=final_msg, parse_mode=ParseMode.HTML
        )
