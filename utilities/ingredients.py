import re
import math
from dataclasses import dataclass
from decimal import Decimal


UNITS = ("τεμάχιο", "συσκευασία", "κιλό", "λίτρο", "ml", "κ.σ.", "κ.γ.")
CATEGORIES = (
    "λαχανικά", "φρούτα", "κρέατα", "αλλαντικά", "τυριά",
    "όσπρια", "ζυμαρικά και ρύζι", "γαλακτοκομικά",
    "ψάρια και θαλασσινά", "βασικά", "άλλα",
)
CATEGORY_ORDER = {category: index for index, category in enumerate(CATEGORIES)}
UNIT_ALIASES = {
    "τεμάχιο": "τεμάχιο", "τεμάχια": "τεμάχιο", "τεμαχιο": "τεμάχιο",
    "τεμαχια": "τεμάχιο", "temaxio": "τεμάχιο", "temaxia": "τεμάχιο",
    "συσκευασία": "συσκευασία", "συσκευασίες": "συσκευασία",
    "συσκευασια": "συσκευασία", "συσκευασιες": "συσκευασία",
    "syskevasia": "συσκευασία", "syskevasies": "συσκευασία",
    "κιλό": "κιλό", "κιλά": "κιλό", "κιλο": "κιλό", "κιλα": "κιλό",
    "kilo": "κιλό", "kila": "κιλό",
    "γρ": "κιλό", "γρ.": "κιλό", "γραμμάριο": "κιλό", "γραμμάρια": "κιλό",
    "γραμμο": "κιλό", "γραμμάρια": "κιλό",
    "ml": "ml", "milliliter": "ml", "milliliters": "ml",
    "λίτρο": "λίτρο", "λίτρα": "λίτρο", "λιτρο": "λίτρο", "λιτρα": "λίτρο",
    "l": "λίτρο",
    "κ.σ": "κ.σ.", "κ.σ.": "κ.σ.", "κσ": "κ.σ.", "κουταλιάς": "κ.σ.",
    "κ.γ": "κ.γ.", "κ.γ.": "κ.γ.", "κγ": "κ.γ.", "κουταλιά": "κ.γ.",
}


@dataclass(frozen=True)
class Ingredient:
    id: int | None
    name: str
    unit: str
    quantity: float | None = None
    category: str = "άλλα"


@dataclass(frozen=True)
class ShoppingItem:
    name: str
    unit: str
    quantity: Decimal | None
    category: str = "άλλα"
    more_than: bool = False

    def quantity_text(self) -> str:
        if self.quantity is None:
            return ""
        return f"{'>' if self.more_than else ''}{self.quantity.normalize():f}"


_LEGACY_ITEM = re.compile(
    r"\s*(?P<name>[^,\n]+?)\s*,\s*(?P<quantity>\d+(?:[.,]\d+)?)"
    r"\s*,?\s*(?P<unit>" + "|".join(sorted(UNIT_ALIASES, key=len, reverse=True))
    + r")(?=\s|,|$)",
    re.IGNORECASE,
)
_NATURAL_QUANTITY = re.compile(
    r"^\s*(?P<quantity>\d+(?:\s*/\s*\d+|[.,]\d+)?)\s*(?:(?P<unit>γρ\.?|γραμμάρια?|"
    r"ml|λίτρο|λίτρα|λιτρο|λιτρα|l|κ\.?\s*σ\.?|κ\.?\s*γ\.?|κιλά?|κιλο|"
    r"τεμάχια?|φύλλα?|φιλέτα?|σκελίδες?|κύβος|κύβοι|κονσέρβα|"
    r"κονσέρβες|αυγά?|μπουκάλια?|φέτες?|κιλά?|κιλό)(?=\s|$))?\s*(?P<name>.+?)\s*$",
    re.IGNORECASE,
)
_RECIPE_SECTION_HEADING = re.compile(
    r"^(?:υλικ[αά]\s+)?για\s+(?:το|τον|τη|την|τα|τις|τους)\b",
    re.IGNORECASE,
)


def _category_for(name: str) -> str:
    lowered = name.casefold()
    groups = (
        ("τυριά", ("τυρί", "φέτα", "παρμεζάνα", "γραβιέρα", "κεφαλοτύρι")),
        ("κρέατα", ("κοτό", "μοσχ", "χοιρ", "κιμά", "κρέας", "μπιφτέ")),
        ("αλλαντικά", ("μπέικον", "ζαμπόν", "λουκάν")),
        ("όσπρια", ("φακ", "φασόλ", "ρεβίθ", "φάβα")),
        ("ζυμαρικά και ρύζι", ("μακαρ", "ζυμαρ", "ρύζ", "κριθαράκ", "χυλοπ")),
        ("λαχανικά", ("κρεμμ", "πιπερ", "καρότ", "ντομάτ", "πατάτ", "σκόρδ",
                       "κολοκυθ", "μανιτάρ", "μελιτζ", "σέλιν")),
        ("γαλακτοκομικά", ("γάλα", "κρέμα γάλακτος", "βούτυρο", "γιαούρ")),
        ("φρούτα", ("λεμόν", "πορτοκ", "μήλ", "μπανάν")),
    )
    for category, keywords in groups:
        if any(keyword in lowered for keyword in keywords):
            return category
    return "άλλα"


def _natural_item(text: str) -> Ingredient | None:
    text = text.strip(" ,.;")
    if not text:
        return None
    match = _NATURAL_QUANTITY.match(text)
    if not match:
        return Ingredient(None, text, "τεμάχιο", 1, _category_for(text))
    raw_quantity = match.group("quantity").replace(",", ".")
    if "/" in raw_quantity:
        numerator, denominator = raw_quantity.split("/")
        if int(denominator) == 0:
            return None
        quantity = int(numerator) / int(denominator)
    else:
        quantity = float(raw_quantity)
    raw_unit = (match.group("unit") or "τεμάχιο").lower().replace(" ", "")
    name = match.group("name").strip(" ,.;")
    if raw_unit in {"γρ", "γρ.", "γραμμάριο", "γραμμάρια"}:
        quantity /= 1000
        unit = "κιλό"
    elif raw_unit in {"ml"}:
        unit = "ml"
    elif raw_unit in {"λίτρο", "λίτρα", "λιτρο", "λιτρα", "l"}:
        unit = "λίτρο"
    elif "κ.σ" in raw_unit or raw_unit == "κουταλιάς":
        unit = "κ.σ."
    elif "κ.γ" in raw_unit or raw_unit == "κουταλιά":
        unit = "κ.γ."
    elif raw_unit in {"κιλό", "κιλά", "κιλο"}:
        unit = "κιλό"
    else:
        unit = "τεμάχιο"
    if not name or quantity <= 0 or not math.isfinite(quantity):
        return None
    return Ingredient(None, name, unit, quantity, _category_for(name))


def parse_legacy_ingredients(value: str) -> tuple[Ingredient, ...] | None:
    items = []
    position = 0
    while position < len(value):
        while position < len(value) and (value[position].isspace() or value[position] == ","):
            position += 1
        if position == len(value):
            break
        match = _LEGACY_ITEM.match(value, position)
        if not match:
            return None
        quantity = float(match.group("quantity").replace(",", "."))
        name = match.group("name").strip()
        if not name or not math.isfinite(quantity) or quantity <= 0:
            return None
        items.append(Ingredient(
            None, name, UNIT_ALIASES[match.group("unit").lower()], quantity
        ))
        position = match.end()
    if not items or len({item.name.casefold() for item in items}) != len(items):
        return None
    return tuple(items)


def parse_recipe_ingredients(value: str) -> tuple[Ingredient, ...] | None:
    """Parse the pipe-separated ingredient text used by the imported recipes."""
    if not re.search(r"[|\n;]", value):
        return None
    parts = [part.strip() for part in re.split(r"\s*[|;\n]\s*", value) if part.strip()]
    parsed = [
        item for part in parts
        if not _RECIPE_SECTION_HEADING.match(part)
        if (item := _natural_item(part)) is not None
    ]
    combined: dict[tuple[str, str], Ingredient] = {}
    for item in parsed:
        key = (item.name.casefold(), item.unit)
        previous = combined.get(key)
        if previous is None:
            combined[key] = item
        else:
            combined[key] = Ingredient(
                None, previous.name, previous.unit,
                (previous.quantity or 0) + (item.quantity or 0),
                previous.category,
            )
    return tuple(combined.values()) or None
