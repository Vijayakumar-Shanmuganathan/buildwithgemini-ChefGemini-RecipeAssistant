#!/usr/bin/env python3
"""Seed Firestore collection for recipe-assistant with hardcoded project ID."""

import datetime
from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-02-a2c8afe1ed1a"
COLLECTION_NAME = "recipes"

SEED_RECIPES = [
    {
        "title": "Lemon Garlic Roasted Chicken",
        "ingredients": [
            "2 chicken breasts",
            "3 cloves garlic, minced",
            "1 lemon (juiced and sliced)",
            "2 tbsp olive oil",
            "Salt and black pepper to taste"
        ],
        "instructions": "1. Preheat oven to 400°F (200°C).\n2. Whisk olive oil, garlic, lemon juice, salt, and pepper.\n3. Coat chicken in baking dish and top with lemon slices.\n4. Roast for 20-25 minutes until internal temp reaches 165°F.",
        "prep_time_minutes": 15,
        "cook_time_minutes": 25,
        "cuisine": "Mediterranean",
        "notes": "Pairs great with roasted vegetables or rice.",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    },
    {
        "title": "Pan-Seared Lemon Garlic Chicken",
        "ingredients": [
            "2 chicken breasts, butterflied",
            "3 cloves garlic, minced",
            "1 lemon",
            "2 tbsp olive oil",
            "Salt and black pepper to taste"
        ],
        "instructions": "1. Season chicken breasts with salt and pepper.\n2. Heat olive oil in skillet over medium-high heat.\n3. Sear chicken 5-7 mins per side.\n4. Stir in garlic and squeeze fresh lemon juice in final 2 minutes.",
        "prep_time_minutes": 10,
        "cook_time_minutes": 15,
        "cuisine": "Mediterranean",
        "notes": "Quick and juicy weeknight favorite.",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    },
    {
        "title": "Creamy Garlic Parmesan Pasta",
        "ingredients": [
            "8 oz fettuccine or pasta",
            "4 cloves garlic, minced",
            "1 cup heavy cream",
            "1 cup freshly grated Parmesan",
            "2 tbsp butter",
            "Fresh parsley for garnish"
        ],
        "instructions": "1. Boil pasta in salted water until al dente.\n2. Melt butter in skillet, add garlic and cook for 1 minute.\n3. Stir in heavy cream and bring to simmer.\n4. Whisk in Parmesan until smooth, then toss in warm pasta.",
        "prep_time_minutes": 10,
        "cook_time_minutes": 12,
        "cuisine": "Italian",
        "notes": "Rich and comforting classic pasta dish.",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
]

def seed_database():
    print(f"Connecting to Firestore for project: {PROJECT_ID}...")
    db = firestore.Client(project=PROJECT_ID)
    collection_ref = db.collection(COLLECTION_NAME)

    for recipe in SEED_RECIPES:
        doc_id = recipe["title"].lower().replace(" ", "_")
        doc_ref = collection_ref.document(doc_id)
        doc_ref.set(recipe)
        print(f"Seeded recipe document: {doc_id} -> '{recipe['title']}'")

    print(f"Successfully seeded {len(SEED_RECIPES)} recipes into collection '{COLLECTION_NAME}'!")

if __name__ == "__main__":
    seed_database()
