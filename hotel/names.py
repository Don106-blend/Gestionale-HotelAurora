"""Libreria di nomi, cognomi e citta per generare dati di prova."""

import random
import string

MALE_NAMES = (
    "Marco", "Luca", "Andrea", "Giuseppe", "Francesco", "Alessandro",
    "Matteo", "Lorenzo", "Davide", "Simone", "Stefano", "Roberto",
    "Antonio", "Riccardo", "Federico", "Giovanni", "Paolo", "Michele",
    "Fabio", "Daniele", "Emanuele", "Nicola", "Gabriele", "Tommaso",
)

FEMALE_NAMES = (
    "Giulia", "Francesca", "Chiara", "Sara", "Martina", "Valentina",
    "Federica", "Alessia", "Elena", "Anna", "Laura", "Silvia",
    "Elisa", "Giorgia", "Marta", "Beatrice", "Camilla", "Sofia",
    "Ilaria", "Roberta", "Cristina", "Paola", "Serena", "Alice",
)

LAST_NAMES = (
    "Rossi", "Russo", "Ferrari", "Esposito", "Bianchi", "Romano",
    "Colombo", "Ricci", "Marino", "Greco", "Bruno", "Gallo",
    "Conti", "De Luca", "Mancini", "Costa", "Giordano", "Rizzo",
    "Lombardi", "Moretti", "Barbieri", "Fontana", "Santoro", "Marini",
)

CITIES = (
    "Milano", "Roma", "Napoli", "Torino", "Palermo", "Genova",
    "Bologna", "Firenze", "Bari", "Catania", "Venezia", "Verona",
    "Padova", "Trieste", "Brescia", "Parma", "Modena", "Bergamo",
)


def random_first_name(rng: random.Random) -> str:
    """Nome casuale, pescato indifferentemente tra maschili e femminili."""
    return rng.choice(MALE_NAMES + FEMALE_NAMES)


def random_last_name(rng: random.Random) -> str:
    return rng.choice(LAST_NAMES)


def random_city(rng: random.Random) -> str:
    return rng.choice(CITIES)


def random_phone(rng: random.Random) -> str:
    return f"+39 3{rng.randint(10, 99)} {rng.randint(1000000, 9999999)}"


def make_email(first: str, last: str, rng: random.Random) -> str:
    base = f"{first}.{last}".lower().replace(" ", "")
    return f"{base}@{rng.choice(('example.com', 'email.it', 'posta.it'))}"


def random_document_number(rng: random.Random) -> str:
    letters = "".join(rng.choice(string.ascii_uppercase) for _ in range(2))
    digits = "".join(str(rng.randint(0, 9)) for _ in range(7))
    return letters + digits


def random_birth_date(rng: random.Random, child: bool = False) -> str:
    """Data di nascita in formato gg/mm/aaaa (bambino oppure adulto)."""
    year = rng.randint(2013, 2021) if child else rng.randint(1950, 2003)
    return f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/{year}"
