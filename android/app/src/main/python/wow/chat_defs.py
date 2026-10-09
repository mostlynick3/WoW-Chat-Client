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
    # IDs pinned to yggdrasilcore SharedDefines.h enum Language.
    UNIVERSAL = 0
    ORCISH = 1
    DARNASSIAN = 2
    TAURAHE = 3
    DWARVISH = 6
    COMMON = 7
    DEMONIC = 8
    TITAN = 9
    THALASSIAN = 10
    DRACONIC = 11
    KALIMAG = 12
    GNOMISH = 13
    TROLL = 14
    GUTTERSPEAK = 33
    DRAENEI = 35
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


def language_name(lang: int) -> str:
    try:
        l = int(lang) & 0xFFFFFFFF
    except (TypeError, ValueError):
        return "auto"
    return {
        Language.UNIVERSAL: "Universal",
        Language.ORCISH: "Orcish",
        Language.DARNASSIAN: "Darnassian",
        Language.TAURAHE: "Taurahe",
        Language.DWARVISH: "Dwarvish",
        Language.COMMON: "Common",
        Language.THALASSIAN: "Thalassian",
        Language.GNOMISH: "Gnomish",
        Language.TROLL: "Troll",
        Language.GUTTERSPEAK: "Gutterspeak",
        Language.DRAENEI: "Draenei",
    }.get(l, f"lang:{l}")


# Racial mother tongues: faction tongue first, then the racial second
# language. No race spans the faction line, so Horde can never see
# Common and Alliance can never see Orcish.
RACE_LANGUAGES = {
    1: (7, ),        # Human: Common
    2: (1, ),        # Orc: Orcish
    3: (7, 6),       # Dwarf: Common, Dwarvish
    4: (7, 2),       # Night Elf: Common, Darnassian
    5: (1, 33),      # Undead: Orcish, Gutterspeak
    6: (1, 3),       # Tauren: Orcish, Taurahe
    7: (7, 13),      # Gnome: Common, Gnomish
    8: (1, 14),      # Troll: Orcish, Troll
    10: (1, 10),     # Blood Elf: Orcish, Thalassian
    11: (7, 35),     # Draenei: Common, Draenei
}


def speakable_languages(race: int) -> tuple[int, ...]:
    return RACE_LANGUAGES.get(int(race), (default_language_for_race(race),))


def realm_type_name(rtype: int) -> str:
    # RealmType in yggdrasilcore Realms/Realm.h.
    return {0: "Normal", 1: "PvP", 4: "Normal", 6: "RP",
            8: "RPPvP"}.get(int(rtype), "Normal")


def population_name(pop: float) -> str:
    try:
        p = float(pop)
    except (TypeError, ValueError):
        return "Low"
    if p < 0.5:
        return "Low"
    if p < 1.0:
        return "Medium"
    if p < 2.0:
        return "High"
    return "Full"


# Classic class colors for the character list.
CLASS_COLORS = {1: "#c79c6e", 2: "#f58cba", 3: "#abd473", 4: "#fff569",
                5: "#e8e8e8", 6: "#c41f3b", 7: "#0070de", 8: "#69ccf0",
                9: "#9482c9", 11: "#ff7d0a"}


# AreaTable.dbc ids for the character list zone line; unknown -> "".
ZONE_NAMES = {
    1: "Dun Morogh", 3: "Badlands", 4: "Blasted Lands",
    8: "Swamp of Sorrows", 10: "Duskwood", 11: "Wetlands",
    12: "Elwynn Forest", 14: "Durotar", 15: "Dustwallow Marsh",
    16: "Azshara", 17: "The Barrens", 28: "Western Plaguelands",
    33: "Stranglethorn Vale", 36: "Alterac Mountains", 40: "Westfall",
    44: "Redridge Mountains", 45: "Arathi Highlands", 46: "Burning Steppes",
    47: "The Hinterlands", 51: "Searing Gorge", 85: "Tirisfal Glades",
    130: "Silverpine Forest", 139: "Eastern Plaguelands", 141: "Teldrassil",
    148: "Darkshore", 215: "Mulgore", 267: "Hillsbrad Foothills",
    331: "Ashenvale", 361: "Felwood", 400: "Thousand Needles",
    405: "Desolace", 406: "Stonetalon Mountains", 440: "Tanaris",
    490: "Un'Goro Crater", 493: "Moonglade", 618: "Winterspring",
    1377: "Silithus", 1497: "Undercity", 1519: "Stormwind City",
    1637: "Orgrimmar", 1638: "Thunder Bluff", 1657: "Darnassus",
    3430: "Eversong Woods", 3483: "Hellfire Peninsula", 3487: "Silvermoon City",
    3518: "Nagrand", 3519: "Terokkar Forest", 3520: "Shadowmoon Valley",
    3521: "Zangarmarsh", 3522: "Blade's Edge Mountains", 3523: "Netherstorm",
    3524: "Azuremyst Isle", 3525: "Bloodmyst Isle", 3557: "The Exodar",
    3703: "Shattrath City", 65: "Dragonblight", 66: "Zul'Drak",
    67: "Sholazar Basin", 210: "Icecrown", 394: "Grizzly Hills",
    495: "Howling Fjord", 3537: "Borean Tundra", 4197: "Wintergrasp",
    4395: "Dalaran",
}


def zone_name(zone: int) -> str:
    try:
        return ZONE_NAMES.get(int(zone), "")
    except (TypeError, ValueError):
        return ""


class ChannelNotify(IntEnum):
    # Pinned to yggdrasilcore Channel.h ChatNotify (NOT the old MaNGOS ids).
    JOINED = 0x00                      # "%s joined channel." + guid u64
    LEFT = 0x01                        # "%s left channel." + guid u64
    YOU_JOINED = 0x02                  # "Joined Channel: [%s]" + u8 flags/u32 id/u32 0
    YOU_LEFT = 0x03                    # "Left Channel: [%s]" + u32 id/u8 constant
    WRONG_PASSWORD = 0x04
    NOT_MEMBER = 0x05
    NOT_MODERATOR = 0x06
    PASSWORD_CHANGED = 0x07            # + guid u64
    OWNER_CHANGED = 0x08               # + guid u64
    PLAYER_NOT_FOUND = 0x09            # + name cstr
    NOT_OWNER = 0x0A
    CHANNEL_OWNER = 0x0B               # + string?
    MODE_CHANGE = 0x0C                 # + guid + u8 old + u8 new
    ANNOUNCEMENTS_ON = 0x0D           # + guid u64
    ANNOUNCEMENTS_OFF = 0x0E          # + guid u64
    MODERATION_ON = 0x0F              # + guid u64
    MODERATION_OFF = 0x10             # + guid u64
    MUTED = 0x11
    PLAYER_KICKED = 0x12               # + guid victim + guid kicker
    BANNED = 0x13
    PLAYER_BANNED = 0x14               # + guid victim + guid banner
    PLAYER_UNBANNED = 0x15             # + guid victim + guid unbanner
    PLAYER_NOT_BANNED = 0x16          # + name cstr
    PLAYER_ALREADY_MEMBER = 0x17      # + guid u64
    INVITE = 0x18
    INVITE_WRONG_FACTION = 0x19
    WRONG_FACTION = 0x1A
    INVALID_NAME = 0x1B
    NOT_MODERATED = 0x1C
    PLAYER_INVITED = 0x1D             # + name cstr
    PLAYER_INVITE_BANNED = 0x1E       # + name cstr
    THROTTLED = 0x1F
    NOT_IN_AREA = 0x20
    NOT_IN_LFG = 0x21
    VOICE_ON = 0x22                    # + guid u64
    VOICE_OFF = 0x23                   # + guid u64
    # Old MaNGOS-style names kept as aliases (same values as above).
    LIST = 0x02
    YOUS_ARE_BANNED = 0x13


CHAT_TYPE_NAMES = {
    0x00: "system",
    0x01: "say",
    0x02: "party",
    0x03: "raid",
    0x04: "guild",
    0x05: "officer",
    0x06: "yell",
    0x07: "whisper",
    0x08: "whisper",      # foreign -> whisper tab
    0x09: "whisper",      # inform (server echo of our outgoing whisper)
    0x0A: "emote",
    0x0B: "emote",        # text emote
    0x0C: "monster_say",
    0x0D: "monster_party",
    0x0E: "monster_yell",
    0x0F: "monster_whisper",
    0x10: "monster_emote",
    0x11: "channel",
    0x12: "channel",      # channel system traffic
    0x13: "channel",
    0x14: "channel",
    0x15: "channel",
    0x16: "channel",
    0x17: "afk",
    0x18: "dnd",
    0x19: "system",       # ignored
    0x1A: "system",       # skill
    0x1B: "system",       # loot
    0x1C: "system",       # money
    0x1D: "system",       # opening
    0x1E: "system",       # tradeskills
    0x1F: "system",       # pet info
    0x20: "system",       # combat misc
    0x21: "system",       # xp gain
    0x22: "system",       # honor gain
    0x23: "system",       # faction change
    0x24: "bg",
    0x25: "bg",
    0x26: "bg",
    0x27: "raid",         # raid leader
    0x28: "raid_warning",
    0x29: "boss_emote",
    0x2A: "boss_whisper",
    0x2B: "system",       # filtered
    0x2C: "bg",           # battleground
    0x2D: "bg",           # battleground leader
    0x2E: "system",       # restricted
    0x2F: "battlenet",
    0x30: "achievement",
    0x31: "achievement",  # guild achievement
    0x32: "system",       # arena points
    0x33: "party",        # party leader
}
