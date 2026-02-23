"""Ingrediëntenlijsten voor hybride producten detectie.

Bron: Suzan D'Rose / Foodvalley - The Protein Community
"""

# Plantaardige ingrediënten met alle variaties
PLANTAARDIG = {
    "Veldboon": [
        "veldboon", "veldbonen", "veldbooneiwit", "veldboneneiwit",
        "veldbooneiwitisolaat", "veldboneneiwitisolaat", "favaboon eiwit",
    ],
    "Jackfruit": ["jackfruit"],
    "Tuinboon": [
        "tuinboon", "tuinbonen", "tuinbooneiwit", "tuinboneneiwit",
        "tuinbooneiwitisolaat", "tuinboneneiwitisolaat",
    ],
    "Boterboon": ["boterboon", "boterbonen"],
    "Suikerbietpulp": ["suikerbietpulp"],
    "Suikerbietenvezel": ["suikerbietenvezel"],
    "Mycoproteine": ["mycoproteine", "mycoproteïne"],
    "Soja eiwit": [
        "soja eiwit", "soja-eiwit", "soja eiwitconcentraat",
        "sojaeiwitconcentraat", "gehydrolyseerd soja-eiwit",
        "gehydrolyseerd sojaeiwitconcentraat", "sojaeiwitgehydroliseerd",
        "soja texturaat", "sojameel",
    ],
    "Erwteneiwit": [
        "erwteneiwit", "erwteneiwitisolaat", "gehydrateerd erwteneiwit",
        "getextureerd erwteneiwit", "geextrudeerd erwteneiwit",
        "erwtenmeel", "gefermenteerd erwteneiwit",
    ],
    "Zeewier": ["zeewier"],
    "Kikkererw": [
        "kikkererw", "kikkererwten", "kikkererwtenmeel",
    ],
    "Aardappeleiwit": ["aardappeleiwit"],
    "Rijstebloem": ["rijstebloem"],
    "Linzen": [
        "linzen", "linzenmeel", "linzeneiwitconcentraat",
        "linzeneiwit", "linzenproteineconcentraat",
    ],
    "Lupine": [
        "lupine", "lupine-eiwit", "lupine eiwit", "lupinemeel",
    ],
    "Witte bonen": ["witte bonen", "witte bonenmeel"],
    "Mung boon": ["mung boon", "mungboon", "mungboneneiwit"],
    "Limaboon": ["limaboon", "limabonen"],
    "Paddenstoelen": ["paddenstoelen", "paddenstoel"],
}

# Dierlijke ingrediënten met alle variaties
DIERLIJK = {
    "Rundvlees": ["rundvlees"],
    "Varkensvlees": ["varkensvlees"],
    "Kippenvlees": ["kippenvlees", "kippenseparatorvlees"],
    "Koemelk": [
        "koemelk", "magere melk", "halfvolle melk", "volle melk", "melkeiwit",
    ],
}


def find_matches(ingredients_text: str) -> dict:
    """Zoek plantaardige en dierlijke ingrediënten in een ingrediëntenlijst.

    Returns dict met:
        plantaardig: [(groep, gevonden_term), ...]
        dierlijk: [(groep, gevonden_term), ...]
        is_hybride: bool
    """
    text = ingredients_text.lower()

    plantaardig_matches = []
    for groep, termen in PLANTAARDIG.items():
        for term in termen:
            if term.lower() in text:
                plantaardig_matches.append((groep, term))
                break  # 1 match per groep is genoeg

    dierlijk_matches = []
    for groep, termen in DIERLIJK.items():
        for term in termen:
            if term.lower() in text:
                dierlijk_matches.append((groep, term))
                break

    return {
        "plantaardig": plantaardig_matches,
        "dierlijk": dierlijk_matches,
        "is_hybride": len(plantaardig_matches) > 0 and len(dierlijk_matches) > 0,
    }
