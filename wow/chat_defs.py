"""Chat enums pinned to yggdrasilcore src/server/shared/SharedDefines.h."""
from enum import IntEnum


class ChatMsg(IntEnum):
    ADDON = 0xFFFFFFFF & 0xFFFFFFFF  # wire uint32; handled as unsigned
    SYSTEM = 0x00
    SAY = 0x01
    PARTY = 0x02
    RAID = 0x03
    GUILD = 0x04
    OFFICER = 0x05
    YELL = 0x06
    WHISPER = 0x07
    WHISPER_FOREIGN = 0x08
    WHISPER_INFORM = 0x09
    EMOTE = 0x0A
    TEXT_EMOTE = 0x0B
    MONSTER_SAY = 0x0C
    MONSTER_PARTY = 0x0D
    MONSTER_YELL = 0x0E
    MONSTER_WHISPER = 0x0F
    MONSTER_EMOTE = 0x10
    CHANNEL = 0x11
    CHANNEL_JOIN = 0x12
    CHANNEL_LEAVE = 0x13
    CHANNEL_LIST = 0x14
    CHANNEL_NOTICE = 0x15
    CHANNEL_NOTICE_USER = 0x16
    AFK = 0x17
    DND = 0x18
    IGNORED = 0x19
    SKILL = 0x1A
    LOOT = 0x1B
    MONEY = 0x1C
    OPENING = 0x1D
    TRADESKILLS = 0x1E
    PET_INFO = 0x1F
    COMBAT_MISC_INFO = 0x20
    COMBAT_XP_GAIN = 0x21
    COMBAT_HONOR_GAIN = 0x22
    COMBAT_FACTION_CHANGE = 0x23
    BG_SYSTEM_NEUTRAL = 0x24
    BG_SYSTEM_ALLIANCE = 0x25
    BG_SYSTEM_HORDE = 0x26
    RAID_LEADER = 0x27
    RAID_WARNING = 0x28
    RAID_BOSS_EMOTE = 0x29
    RAID_BOSS_WHISPER = 0x2A
    FILTERED = 0x2B
    BATTLEGROUND = 0x2C
    BATTLEGROUND_LEADER = 0x2D
    RESTRICTED = 0x2E
    BATTLENET = 0x2F
    ACHIEVEMENT = 0x30
    GUILD_ACHIEVEMENT = 0x31
    ARENA_POINTS = 0x32
    PARTY_LEADER = 0x33


# Sendable chat types from the UI (subset of ChatMsg).
SENDABLE = {
    "say": ChatMsg.SAY,
    "yell": ChatMsg.YELL,
    "emote": ChatMsg.EMOTE,
    "party": ChatMsg.PARTY,
    "guild": ChatMsg.GUILD,
    "officer": ChatMsg.OFFICER,
    "raid": ChatMsg.RAID,
    "raid_warning": ChatMsg.RAID_WARNING,
    "raid_leader": ChatMsg.RAID_LEADER,
    "battleground": ChatMsg.BATTLEGROUND,
    "whisper": ChatMsg.WHISPER,
    "channel": ChatMsg.CHANNEL,
    "afk": ChatMsg.AFK,
    "dnd": ChatMsg.DND,
}


class Language:
    UNIVERSAL = 0
    ORCISH = 1
    DWARVEN = 2
    DARNASSIAN = 3
    TAURAHE = 4
    GUTTERSPEAK = 5
    DRAENEI = 6
    COMMON = 7
    ADDON = 0xFFFFFFFF


# Player race ids (SharedDefines.h) grouped per RACEMASK_ALLIANCE; the rest
# of the playable races are Horde (RACEMASK_HORDE = ALL_PLAYABLE & ~ALLIANCE).
ALLIANCE_RACES = frozenset({1, 3, 4, 7, 11})  # Human, Dwarf, NElf, Gnome, Draenei
HORDE_RACES = frozenset({2, 5, 6, 8, 10})     # Orc, Undead, Tauren, Troll, Belf


def faction_of_race(race: int) -> str:
    """'alliance' | 'horde' | 'unknown' (mirrors RACEMASK_ALLIANCE)."""
    if race in ALLIANCE_RACES:
        return "alliance"
    if race in HORDE_RACES:
        return "horde"
    return "unknown"


def default_language_for_race(race: int) -> int:
    """Faction tongue a character can always speak: Common (7) for
    Alliance, Orcish (1) for Horde. Unknown races fall back to Common."""
    if faction_of_race(race) == "horde":
        return Language.ORCISH
    return Language.COMMON


class ChannelNotify(IntEnum):
    JOINED = 0x00
    LEFT = 0x01
    LIST = 0x02
    NOT_IN = 0x03
    NOT_MODERATOR = 0x04
    NOT_OWNER = 0x05
    NOT_ON = 0x06
    ALREADY_ON = 0x07
    INVITED = 0x08
    BANNED = 0x09
    THROTTLED = 0x0A
    INVALID_NAME = 0x0B
    KICKED = 0x0C
    BANNED2 = 0x0D
    YOUS_ARE_BANNED = 0x0E
    NOT_BANNED = 0x0F
    PLAYER_NOT_FOUND = 0x10
    NOT_MODERATED = 0x11
    PLAYER_INVITED = 0x12
    PLAYER_INVITE_BANNED = 0x13
    THROTTLE = 0x14
    NOT_IN_AREA = 0x15
    NOT_IN_LFG = 0x16
    VOICE_ON = 0x17
    VOICE_OFF = 0x18
    MODE_CHANGE = 0x19
    ANNOUNCEMENTS_ON = 0x1A
    ANNOUNCEMENTS_OFF = 0x1B
    MODERATION_ON = 0x1C
    MODERATION_OFF = 0x1D
    MUTED = 0x1E
    PLAYER_KICKED = 0x1F
    PLAYER_BANNED = 0x20
    PLAYER_UNBANNED = 0x21
    PLAYER_NOT_BANNED = 0x22
    PLAYER_ALREADY_MEMBER = 0x23
    INVITE = 0x24
    INVITE_WRONG_FACTION = 0x25
    WRONG_PASSWORD = 0x26
    INVALID_CHANNEL = 0x27
    PASSWORD_CHANGED = 0x28
    OWNER_CHANGED = 0x29
    PLAYER_NO_LONGER = 0x2A
    NOT_OWNER2 = 0x2B
    CHANNEL_OWNER = 0x2C
    MODE_QUERY = 0x2D
    ANNOUNCEMENTS_QUERY = 0x2E
    MODERATION_QUERY = 0x2F
    PASSWORD_QUERY = 0x30
    OWNER_QUERY = 0x31
    KICK_QUERY = 0x32
    BAN_QUERY = 0x33


CHAT_TYPE_NAMES = {
    0x00: "system",
    0x01: "say",
    0x02: "party",
    0x03: "raid",
    0x04: "guild",
    0x05: "officer",
    0x06: "yell",
    0x07: "whisper",
    0x08: "whisper",
    0x09: "whisper",
    0x0A: "emote",
    0x0B: "emote",
    0x11: "channel",
}
