"""SQLite database voor hybride producten."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "hybride_producten.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Maak tabellen aan als ze nog niet bestaan."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supermarket TEXT NOT NULL,
            name TEXT NOT NULL,
            url TEXT,
            category TEXT,
            ingredients_raw TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(supermarket, url)
        );

        CREATE TABLE IF NOT EXISTS ingredient_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            ingredient_term TEXT NOT NULL,
            ingredient_group TEXT NOT NULL,
            ingredient_type TEXT NOT NULL,
            UNIQUE(product_id, ingredient_term)
        );

        CREATE INDEX IF NOT EXISTS idx_products_supermarket ON products(supermarket);
        CREATE INDEX IF NOT EXISTS idx_matches_type ON ingredient_matches(ingredient_type);
        CREATE INDEX IF NOT EXISTS idx_matches_product ON ingredient_matches(product_id);
    """)
    conn.commit()
    conn.close()


def upsert_product(supermarket: str, name: str, url: str | None,
                   category: str | None, ingredients_raw: str | None) -> int:
    """Voeg product toe of update als het al bestaat. Returnt product id."""
    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO products (supermarket, name, url, category, ingredients_raw, scraped_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(supermarket, url) DO UPDATE SET
            name = excluded.name,
            category = excluded.category,
            ingredients_raw = excluded.ingredients_raw,
            scraped_at = CURRENT_TIMESTAMP
        RETURNING id
    """, (supermarket, name, url, category, ingredients_raw))
    product_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return product_id


def save_matches(product_id: int, matches: dict):
    """Sla ingrediënt-matches op voor een product."""
    conn = get_connection()
    # Verwijder oude matches
    conn.execute("DELETE FROM ingredient_matches WHERE product_id = ?", (product_id,))

    for match_type in ("plantaardig", "dierlijk"):
        for groep, term in matches.get(match_type, []):
            conn.execute("""
                INSERT OR IGNORE INTO ingredient_matches
                    (product_id, ingredient_term, ingredient_group, ingredient_type)
                VALUES (?, ?, ?, ?)
            """, (product_id, term, groep, match_type))

    conn.commit()
    conn.close()


def get_stats() -> dict:
    """Haal statistieken op."""
    conn = get_connection()

    total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    with_ingredients = conn.execute(
        "SELECT COUNT(*) FROM products WHERE ingredients_raw IS NOT NULL AND ingredients_raw != ''"
    ).fetchone()[0]

    per_supermarket = {}
    for row in conn.execute(
        "SELECT supermarket, COUNT(*) as cnt FROM products GROUP BY supermarket ORDER BY cnt DESC"
    ):
        per_supermarket[row["supermarket"]] = row["cnt"]

    hybride_count = conn.execute("""
        SELECT COUNT(DISTINCT p.id) FROM products p
        WHERE EXISTS (
            SELECT 1 FROM ingredient_matches m1
            WHERE m1.product_id = p.id AND m1.ingredient_type = 'plantaardig'
        ) AND EXISTS (
            SELECT 1 FROM ingredient_matches m2
            WHERE m2.product_id = p.id AND m2.ingredient_type = 'dierlijk'
        )
    """).fetchone()[0]

    conn.close()
    return {
        "totaal_producten": total,
        "met_ingredienten": with_ingredients,
        "per_supermarkt": per_supermarket,
        "hybride_producten": hybride_count,
    }


def search_products(supermarkets: list[str] | None = None,
                    plantaardig_groepen: list[str] | None = None,
                    dierlijk_groepen: list[str] | None = None,
                    alleen_hybride: bool = False,
                    zoekterm: str | None = None) -> list[dict]:
    """Zoek producten met filters."""
    conn = get_connection()

    query = """
        SELECT DISTINCT p.id, p.supermarket, p.name, p.url, p.category,
               p.ingredients_raw, p.scraped_at
        FROM products p
        LEFT JOIN ingredient_matches m ON m.product_id = p.id
        WHERE 1=1
    """
    params = []

    if supermarkets:
        placeholders = ",".join("?" * len(supermarkets))
        query += f" AND p.supermarket IN ({placeholders})"
        params.extend(supermarkets)

    if zoekterm:
        query += " AND (p.name LIKE ? OR p.ingredients_raw LIKE ?)"
        params.extend([f"%{zoekterm}%", f"%{zoekterm}%"])

    if plantaardig_groepen:
        placeholders = ",".join("?" * len(plantaardig_groepen))
        query += f"""
            AND EXISTS (
                SELECT 1 FROM ingredient_matches mp
                WHERE mp.product_id = p.id
                AND mp.ingredient_type = 'plantaardig'
                AND mp.ingredient_group IN ({placeholders})
            )
        """
        params.extend(plantaardig_groepen)

    if dierlijk_groepen:
        placeholders = ",".join("?" * len(dierlijk_groepen))
        query += f"""
            AND EXISTS (
                SELECT 1 FROM ingredient_matches md
                WHERE md.product_id = p.id
                AND md.ingredient_type = 'dierlijk'
                AND md.ingredient_group IN ({placeholders})
            )
        """
        params.extend(dierlijk_groepen)

    if alleen_hybride:
        query += """
            AND EXISTS (
                SELECT 1 FROM ingredient_matches m1
                WHERE m1.product_id = p.id AND m1.ingredient_type = 'plantaardig'
            )
            AND EXISTS (
                SELECT 1 FROM ingredient_matches m2
                WHERE m2.product_id = p.id AND m2.ingredient_type = 'dierlijk'
            )
        """

    query += " ORDER BY p.supermarket, p.name"

    rows = conn.execute(query, params).fetchall()

    results = []
    for row in rows:
        product = dict(row)
        # Haal matches op
        matches = conn.execute("""
            SELECT ingredient_group, ingredient_term, ingredient_type
            FROM ingredient_matches WHERE product_id = ?
        """, (row["id"],)).fetchall()

        product["matches_plantaardig"] = [
            f"{m['ingredient_group']} ({m['ingredient_term']})"
            for m in matches if m["ingredient_type"] == "plantaardig"
        ]
        product["matches_dierlijk"] = [
            f"{m['ingredient_group']} ({m['ingredient_term']})"
            for m in matches if m["ingredient_type"] == "dierlijk"
        ]
        results.append(product)

    conn.close()
    return results


# Initialiseer DB bij import
init_db()
