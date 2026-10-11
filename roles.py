"""
Определение ролей и команд для игры в Мафию.
"""

from enum import Enum
from typing import Dict, Any


class Team(Enum):
    CITIZENS = "Город (Мирные жители)"
    MAFIA = "Мафия"


class RoleType(Enum):
    CITIZEN = "citizen"
    MAFIA = "mafia"
    DON = "don"
    SHERIFF = "sheriff"
    DOCTOR = "doctor"
    PROSTITUTE = "prostitute"


ROLE_INFO: Dict[RoleType, Dict[str, Any]] = {
    RoleType.CITIZEN: {
        "title": "Мирный житель",
        "emoji": "👱‍♂️",
        "team": Team.CITIZENS,
        "night_active": False,
        "description": (
            "Ваша задача — вычислить мафию в ходе дневных дискуссий и "
            "проголосовать против неё на суде Линча. Ночью вы крепко спите."
        ),
    },
    RoleType.MAFIA: {
        "title": "Мафия",
        "emoji": "🔫",
        "team": Team.MAFIA,
        "night_active": True,
        "description": (
            "Ваша цель — устранить всех мирных жителей. "
            "Ночью вы советуетесь с сообщниками и выбираете жертву. "
            "Днем ведите себя как честный гражданин!"
        ),
    },
    RoleType.DON: {
        "title": "Дон мафии",
        "emoji": "🎩",
        "team": Team.MAFIA,
        "night_active": True,
        "description": (
            "Вы — глава мафиозного синдиката. "
            "Ночью вы голосуете за убийство и можете искать Шерифа, "
            "проверяя подозреваемых."
        ),
    },
    RoleType.SHERIFF: {
        "title": "Шериф (Комиссар)",
        "emoji": "🕵️‍♂️",
        "team": Team.CITIZENS,
        "night_active": True,
        "description": (
            "Вы — защитник закона. Каждую ночь вы можете проверить одного "
            "игрока и узнать, принадлежит ли он к мафии."
        ),
    },
    RoleType.DOCTOR: {
        "title": "Доктор",
        "emoji": "🩺",
        "team": Team.CITIZENS,
        "night_active": True,
        "description": (
            "Каждую ночь вы можете исцелить одного жителя от смертельного "
            "нападения мафии. Можно лечить и себя (но осторожно!)."
        ),
    },
    RoleType.PROSTITUTE: {
        "title": "Любовница (Путана)",
        "emoji": "💃",
        "team": Team.CITIZENS,
        "night_active": True,
        "description": (
            "Каждую ночь вы навещаете одного игрока. Он проводит ночь с вами "
            "и блокируется — его ночное действие отменяется, но на дневном "
            "голосовании у него есть алиби."
        ),
    },
}


def get_role_distribution(player_count: int) -> list[RoleType]:
    """
    Распределение ролей в зависимости от количества игроков.
    """
    if player_count < 3:
        raise ValueError("Минимум 3 игрока для распределения ролей.")

    if player_count == 3:
        # Для быстрого тестирования: 1 мафия, 1 шериф, 1 доктор
        return [RoleType.MAFIA, RoleType.SHERIFF, RoleType.DOCTOR]
    elif player_count == 4:
        # 1 мафия, 1 шериф, 1 доктор, 1 мирный
        return [RoleType.MAFIA, RoleType.SHERIFF, RoleType.DOCTOR, RoleType.CITIZEN]
    elif player_count == 5:
        # 1 мафия, 1 шериф, 1 доктор, 2 мирных
        return [
            RoleType.MAFIA,
            RoleType.SHERIFF,
            RoleType.DOCTOR,
            RoleType.CITIZEN,
            RoleType.CITIZEN,
        ]
    elif player_count == 6:
        # 2 мафии (Дон + Мафия), 1 шериф, 1 доктор, 2 мирных
        return [
            RoleType.DON,
            RoleType.MAFIA,
            RoleType.SHERIFF,
            RoleType.DOCTOR,
            RoleType.CITIZEN,
            RoleType.CITIZEN,
        ]
    elif player_count == 7:
        # 2 мафии, 1 шериф, 1 доктор, 1 путана, 2 мирных
        return [
            RoleType.DON,
            RoleType.MAFIA,
            RoleType.SHERIFF,
            RoleType.DOCTOR,
            RoleType.PROSTITUTE,
            RoleType.CITIZEN,
            RoleType.CITIZEN,
        ]
    elif player_count == 8:
        # 2 мафии, 1 шериф, 1 доктор, 1 путана, 3 мирных
        return [
            RoleType.DON,
            RoleType.MAFIA,
            RoleType.SHERIFF,
            RoleType.DOCTOR,
            RoleType.PROSTITUTE,
            RoleType.CITIZEN,
            RoleType.CITIZEN,
            RoleType.CITIZEN,
        ]
    else:
        # 9+ игроков: ~1/3 мафии, спецроли, остальное мирные
        mafia_count = max(2, player_count // 3)
        roles = [RoleType.DON]
        roles.extend([RoleType.MAFIA] * (mafia_count - 1))
        roles.extend([RoleType.SHERIFF, RoleType.DOCTOR, RoleType.PROSTITUTE])
        peaceful_needed = player_count - len(roles)
        roles.extend([RoleType.CITIZEN] * max(0, peaceful_needed))
        return roles[:player_count]
