# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
import os
import requests
from a2ui.schema.manager import A2uiSchemaManager
from a2ui.basic_catalog.provider import BasicCatalog
from google import genai
from google.cloud import firestore, storage
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from .a2ui_utils import a2ui_callback

# Explicitly hardcoded GCP Project ID and GCS Bucket Name
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-02-a2c8afe1ed1a"
BUCKET_NAME = "recipe-assistant-media-qwiklabs-gcp-02-a2c8afe1ed1a"
COLLECTION_NAME = "recipes"
DEPLOYMENT_METADATA_PATH = os.path.join(os.path.dirname(__file__), "..", "deployment_metadata.json")

# Standard nutritional reference database (per typical serving / standard quantity)
NUTRITION_DATABASE = {
    "chicken": {"calories": 165, "protein_g": 31.0, "carbs_g": 0.0, "fat_g": 3.6},
    "chicken breast": {"calories": 165, "protein_g": 31.0, "carbs_g": 0.0, "fat_g": 3.6},
    "garlic": {"calories": 10, "protein_g": 0.5, "carbs_g": 2.2, "fat_g": 0.1},
    "lemon": {"calories": 15, "protein_g": 0.4, "carbs_g": 5.0, "fat_g": 0.1},
    "olive oil": {"calories": 119, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 13.5},
    "pasta": {"calories": 220, "protein_g": 8.0, "carbs_g": 43.0, "fat_g": 1.3},
    "fettuccine": {"calories": 220, "protein_g": 8.0, "carbs_g": 43.0, "fat_g": 1.3},
    "heavy cream": {"calories": 100, "protein_g": 0.8, "carbs_g": 0.8, "fat_g": 10.5},
    "parmesan": {"calories": 110, "protein_g": 10.0, "carbs_g": 1.0, "fat_g": 7.0},
    "butter": {"calories": 102, "protein_g": 0.1, "carbs_g": 0.0, "fat_g": 11.5},
    "rice": {"calories": 205, "protein_g": 4.2, "carbs_g": 45.0, "fat_g": 0.4},
    "tomato": {"calories": 22, "protein_g": 1.1, "carbs_g": 4.8, "fat_g": 0.2},
    "egg": {"calories": 72, "protein_g": 6.3, "carbs_g": 0.4, "fat_g": 4.8},
}


def get_db():
    """Instantiates a Firestore client with the hardcoded project ID."""
    return firestore.Client(project=FIRESTORE_PROJECT_ID)


def get_sandbox_code_executor():
    """Loads or initializes an AgentEngineSandboxCodeExecutor using deployment_metadata.json if available."""
    try:
        if os.path.exists(DEPLOYMENT_METADATA_PATH):
            with open(DEPLOYMENT_METADATA_PATH, "r") as f:
                metadata = json.load(f)
            
            sandbox_name = metadata.get("sandbox_resource_name")
            ae_resource = metadata.get("remote_agent_runtime_id")
            
            if sandbox_name:
                return AgentEngineSandboxCodeExecutor(sandbox_resource_name=sandbox_name)
            elif ae_resource:
                return AgentEngineSandboxCodeExecutor(agent_engine_resource_name=ae_resource)
    except Exception as e:
        print(f"Notice: Sandbox code executor fallback: {e}")
    return None


def generate_recipe_image(
    recipe_title: str,
    description: str = "",
    tool_context: ToolContext = None
) -> str:
    """Generates an image for a recipe or food item using gemini-3.1-flash-lite-image model in global region.

    Saves the image artifact to the ADK session and uploads it directly to Cloud Storage.

    Args:
        recipe_title: The name of the dish or recipe (e.g., 'Garlic Herb Roasted Chicken').
        description: Optional details describing how the dish should look (e.g., 'golden brown skin, fresh parsley garnish').
        tool_context: ADK ToolContext automatically injected by the framework.

    Returns:
        The public Cloud Storage HTTPS URL of the generated image.
    """
    prompt = f"A high-quality food photography shot of {recipe_title}."
    if description:
        prompt += f" {description}"

    try:
        # 1. Generate image using gemini-3.1-flash-lite-image model in global region
        genai_client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT_ID,
            location="global"
        )
        res = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["IMAGE"])
        )

        img_bytes = None
        mime_type = "image/png"
        if res.candidates and res.candidates[0].content and res.candidates[0].content.parts:
            for part in res.candidates[0].content.parts:
                if part.inline_data:
                    img_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/png"
                    break

        if not img_bytes:
            return "Failed to retrieve image bytes from model response."

        # 2. Save artifact using tool_context.save_artifact
        doc_slug = recipe_title.strip().lower().replace(" ", "_")
        ext = "png" if "png" in mime_type else "jpg"
        filename = f"{doc_slug}.{ext}"

        if tool_context:
            artifact_part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type)
            tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 3. Upload image bytes directly to GCS bucket (no local file)
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
        gcs_blob_name = f"recipes/{doc_slug}_{timestamp}.{ext}"
        blob = bucket.blob(gcs_blob_name)
        blob.upload_from_string(img_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{gcs_blob_name}"
        return f"### 📷 Recipe Image Generated Successfully!\n- **Public Image URL:** {public_url}"
    except Exception as e:
        return f"Image generation failed: {e}"


def generate_recipe_video(
    recipe_title: str,
    description: str = "",
    tool_context: ToolContext = None
) -> str:
    """Generates a short video for a recipe or cooking item using Google's Omni model (gemini-omni-flash-preview) in the global region.

    Saves the video artifact to the ADK session and uploads it directly to Cloud Storage.

    Args:
        recipe_title: The name of the dish or cooking technique (e.g., 'Sizzling Garlic Herb Chicken').
        description: Optional details describing what should happen in the video (e.g., 'garlic sizzling in olive oil in a pan').
        tool_context: ADK ToolContext automatically injected by the framework.

    Returns:
        The public Cloud Storage HTTPS URL of the generated video.
    """
    prompt = f"A short video of {recipe_title}."
    if description:
        prompt += f" {description}"

    try:
        # 1. Generate video using gemini-omni-flash-preview model in global region
        genai_client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT_ID,
            location="global"
        )

        interaction = genai_client.interactions.create(
            model="gemini-omni-flash-preview",
            input=prompt,
        )

        video_bytes = None
        mime_type = "video/mp4"

        if interaction and hasattr(interaction, "output_video") and interaction.output_video:
            ov = interaction.output_video
            mime_type = getattr(ov, "mime_type", None) or "video/mp4"
            if hasattr(ov, "data") and ov.data:
                if isinstance(ov.data, bytes):
                    video_bytes = ov.data
                elif isinstance(ov.data, str):
                    video_bytes = base64.b64decode(ov.data)

        if not video_bytes:
            return "Failed to retrieve video bytes from model response."

        # 2. Save artifact using tool_context.save_artifact
        doc_slug = recipe_title.strip().lower().replace(" ", "_")
        ext = "mp4"
        filename = f"{doc_slug}.{ext}"

        if tool_context:
            artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
            tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 3. Upload video bytes directly to GCS bucket (no local file)
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
        gcs_blob_name = f"recipes/{doc_slug}_{timestamp}.{ext}"
        blob = bucket.blob(gcs_blob_name)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{gcs_blob_name}"
        return f"### 🎥 Recipe Video Generated Successfully!\n- **Public Video URL:** {public_url}"
    except Exception as e:
        return f"Video generation failed: {e}"


def geocode_address(address: str) -> str:
    """Converts a human-readable address or landmark into geographic coordinates (latitude, longitude) using Google Geocoding API.

    Args:
        address: The street address, city, or landmark name to geocode (e.g., '1600 Amphitheatre Pkwy, Mountain View, CA').

    Returns:
        A Markdown summary containing formatted address, latitude, and longitude.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={requests.utils.quote(address)}&key={api_key}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data.get("status") != "OK" or not data.get("results"):
            return f"Could not geocode address '{address}': {data.get('status', 'NO_RESULTS')}"

        result = data["results"][0]
        formatted_address = result.get("formatted_address", address)
        loc = result["geometry"]["location"]
        lat = loc["lat"]
        lng = loc["lng"]

        return f"### 📍 Geocoding Result:\n- **Address:** {formatted_address}\n- **Latitude:** `{lat}`\n- **Longitude:** `{lng}`"
    except Exception as e:
        return f"Geocoding request failed: {e}"


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "grocery_store",
    radius_meters: float = 3000.0
) -> str:
    """Finds nearby places of a given type around a coordinate using Google Places API (New).

    Args:
        latitude: Latitude of the center location.
        longitude: Longitude of the center location.
        place_type: Type of place to search for (e.g. 'grocery_store', 'supermarket', 'restaurant', 'bakery').
        radius_meters: Search radius in meters (default: 3000.0).

    Returns:
        A Markdown list of nearby places including name, address, and location.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location"
    }
    body = {
        "includedTypes": [place_type],
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude
                },
                "radius": radius_meters
            }
        }
    }

    try:
        response = requests.post(url, headers=headers, json=body, timeout=10)
        if response.status_code != 200:
            return f"Error from Places API (HTTP {response.status_code}): {response.text}"

        data = response.json()
        places = data.get("places", [])
        if not places:
            return f"No nearby places of type '{place_type}' found within {radius_meters}m."

        results = []
        for place in places[:5]:
            display_name = place.get("displayName", {}).get("text", "Unknown Place")
            addr = place.get("formattedAddress", "No address provided")
            loc = place.get("location", {})
            p_lat = loc.get("latitude")
            p_lng = loc.get("longitude")
            results.append(
                f"- **{display_name}**\n  - Address: {addr}\n  - Location: `{p_lat}, {p_lng}`"
            )

        return f"### 🏪 Nearby '{place_type}' Places:\n" + "\n".join(results)
    except Exception as e:
        return f"Places API search request failed: {e}"


def search_online_recipes_api(query: str) -> str:
    """Searches the public TheMealDB API for real online recipes matching a keyword or ingredient.

    Args:
        query: Ingredient or meal search query (e.g. 'chicken', 'pasta', 'arrabiata', 'curry').

    Returns:
        A Markdown list of real recipes retrieved from TheMealDB API including titles, categories, and instructions summary.
    """
    api_key = os.environ.get("THEMEALDB_API_KEY", "1")
    url = f"https://www.themealdb.com/api/json/v1/{api_key}/search.php?s={query.strip()}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return f"Error querying online recipe API (HTTP {response.status_code})."
        
        data = response.json()
        meals = data.get("meals")
        if not meals:
            filter_url = f"https://www.themealdb.com/api/json/v1/{api_key}/filter.php?i={query.strip()}"
            f_resp = requests.get(filter_url, timeout=10)
            if f_resp.status_code == 200 and f_resp.json().get("meals"):
                meals = f_resp.json()["meals"]

        if not meals:
            return f"No online recipes found matching '{query}' from TheMealDB API."

        results = []
        for meal in meals[:3]:
            title = meal.get("strMeal", "Unknown Dish")
            category = meal.get("strCategory", "General")
            area = meal.get("strArea", "International")
            instructions = meal.get("strInstructions", "")
            summary = instructions[:150] + "..." if len(instructions) > 150 else instructions
            results.append(
                f"- **{title}** ({category} / {area})\n  *Summary*: {summary}"
                if summary else f"- **{title}** ({category})"
            )

        return f"### 🌐 Online Recipe Search Results for '{query}':\n" + "\n\n".join(results)
    except Exception as e:
        return f"Failed to connect to online recipe API: {e}"


def calculate_recipe_nutrition(ingredients: list[str]) -> str:
    """Calculates estimated nutritional information (calories, protein, carbs, fats, dietary tags) for a list of ingredients.

    Args:
        ingredients: A list of ingredients with quantities (e.g. ['2 chicken breasts', '2 tbsp olive oil', '1 lemon']).

    Returns:
        A Markdown summary of total estimated calories, macronutrients, and dietary badges.
    """
    total_calories = 0
    total_protein = 0.0
    total_carbs = 0.0
    total_fat = 0.0

    breakdown = []
    for ing in ingredients:
        ing_lower = ing.lower()
        matched = False
        for name, data in NUTRITION_DATABASE.items():
            if name in ing_lower:
                total_calories += data["calories"]
                total_protein += data["protein_g"]
                total_carbs += data["carbs_g"]
                total_fat += data["fat_g"]
                breakdown.append(
                    f"  - **{ing}**: ~{data['calories']} kcal (P: {data['protein_g']}g, C: {data['carbs_g']}g, F: {data['fat_g']}g)"
                )
                matched = True
                break
        if not matched:
            total_calories += 40
            total_protein += 1.0
            total_carbs += 5.0
            total_fat += 1.0
            breakdown.append(f"  - **{ing}**: ~40 kcal (estimated)")

    tags = []
    if total_carbs < 20:
        tags.append("Low Carb")
    if total_protein > 25:
        tags.append("High Protein")
    if total_fat < 10:
        tags.append("Low Fat")
    if not any(meat in ing.lower() for ing in ingredients for meat in ["chicken", "meat", "beef", "pork", "fish"]):
        tags.append("Vegetarian-Friendly")

    tags_str = ", ".join(f"`{t}`" for t in tags) if tags else "`Balanced`"

    output = [
        "### 🥗 Nutritional Estimate & Analysis",
        f"**Dietary Badges:** {tags_str}",
        f"- **Total Calories:** ~{int(total_calories)} kcal",
        f"- **Protein:** ~{round(total_protein, 1)} g",
        f"- **Carbohydrates:** ~{round(total_carbs, 1)} g",
        f"- **Fat:** ~{round(total_fat, 1)} g",
        "\n**Ingredient Breakdown:**",
        "\n".join(breakdown),
    ]

    return "\n".join(output)


def save_recipe_to_firestore(
    title: str,
    ingredients: list[str],
    instructions: str,
    prep_time_minutes: int = 15,
    cook_time_minutes: int = 20,
    cuisine: str = "General",
    notes: str = ""
) -> str:
    """Saves a new recipe or favorite to the Firestore 'recipes' collection.

    Args:
        title: Title of the recipe (e.g., 'Lemon Garlic Chicken').
        ingredients: List of required ingredients with quantities.
        instructions: Step-by-step cooking instructions.
        prep_time_minutes: Preparation time in minutes.
        cook_time_minutes: Cooking time in minutes.
        cuisine: Cuisine category (e.g., 'Italian', 'Mediterranean', 'American').
        notes: Additional tips or user notes.

    Returns:
        Confirmation message that the recipe was saved to Firestore.
    """
    db = get_db()
    doc_id = title.strip().lower().replace(" ", "_")
    doc_ref = db.collection(COLLECTION_NAME).document(doc_id)
    
    recipe_data = {
        "title": title.strip(),
        "ingredients": ingredients,
        "instructions": instructions.strip(),
        "prep_time_minutes": prep_time_minutes,
        "cook_time_minutes": cook_time_minutes,
        "cuisine": cuisine.strip(),
        "notes": notes.strip(),
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    
    doc_ref.set(recipe_data, merge=True)
    return f"Successfully saved '{title.strip()}' to Firestore recipes collection!"


def list_recipes_from_firestore(cuisine: str = "") -> str:
    """Retrieves and lists all recipes saved in the Firestore 'recipes' collection.

    Args:
        cuisine: Optional filter to return recipes matching a specific cuisine category.

    Returns:
        A Markdown list of recipes from Firestore.
    """
    db = get_db()
    query = db.collection(COLLECTION_NAME)
    
    docs = list(query.stream())
    if not docs:
        return "No recipes found in the Firestore database."

    results = []
    for doc in docs:
        data = doc.to_dict()
        if cuisine and cuisine.lower() not in data.get("cuisine", "").lower():
            continue
        title = data.get("title", doc.id)
        ing_count = len(data.get("ingredients", []))
        c_type = data.get("cuisine", "General")
        p_time = data.get("prep_time_minutes", 0)
        c_time = data.get("cook_time_minutes", 0)
        
        results.append(f"- **{title}** ({c_type}): {ing_count} ingredients | Prep: {p_time}m, Cook: {c_time}m")

    if not results:
        return f"No recipes matching cuisine '{cuisine}' found in Firestore."

    return "### Firestore Recipe Catalog:\n" + "\n".join(results)


def get_recipe_from_firestore(title: str) -> str:
    """Gets detailed information for a specific recipe from the Firestore database.

    Args:
        title: The title or name of the recipe to look up.

    Returns:
        Full details of the recipe including ingredients, instructions, and timing.
    """
    db = get_db()
    doc_id = title.strip().lower().replace(" ", "_")
    doc_ref = db.collection(COLLECTION_NAME).document(doc_id)
    doc = doc_ref.get()

    if not doc.exists:
        docs = db.collection(COLLECTION_NAME).stream()
        matched_doc = None
        for d in docs:
            data = d.to_dict()
            if title.lower() in data.get("title", "").lower() or doc_id in d.id:
                matched_doc = data
                break
        if not matched_doc:
            return f"Recipe '{title}' not found in Firestore database."
        data = matched_doc
    else:
        data = doc.to_dict()

    ingredients_formatted = "\n".join(f"  - {ing}" for ing in data.get("ingredients", []))
    
    output = [
        f"### {data.get('title')}",
        f"**Cuisine:** {data.get('cuisine', 'General')}",
        f"**Prep Time:** {data.get('prep_time_minutes', 0)} mins | **Cook Time:** {data.get('cook_time_minutes', 0)} mins",
        "**Ingredients:**",
        ingredients_formatted,
        "**Instructions:**",
        data.get("instructions", ""),
    ]
    if data.get("notes"):
        output.append(f"**Notes:** {data['notes']}")

    return "\n\n".join(output)


def delete_recipe_from_firestore(title: str) -> str:
    """Removes a recipe document from the Firestore database.

    Args:
        title: The name of the recipe to delete.

    Returns:
        Confirmation message regarding the deletion.
    """
    db = get_db()
    doc_id = title.strip().lower().replace(" ", "_")
    doc_ref = db.collection(COLLECTION_NAME).document(doc_id)
    
    if doc_ref.get().exists:
        doc_ref.delete()
        return f"Deleted recipe '{title}' from Firestore."
        
    docs = db.collection(COLLECTION_NAME).stream()
    for d in docs:
        data = d.to_dict()
        if title.lower() in data.get("title", "").lower() or doc_id in d.id:
            db.collection(COLLECTION_NAME).document(d.id).delete()
            return f"Deleted recipe '{data.get('title')}' from Firestore."

    return f"Could not find a recipe titled '{title}' in Firestore to delete."


# Compatibility functions mapped to Firestore
def save_favorite_recipe(title: str, ingredients: list[str], instructions: str, notes: str = "") -> str:
    return save_recipe_to_firestore(title=title, ingredients=ingredients, instructions=instructions, notes=notes)


def list_favorite_recipes() -> str:
    return list_recipes_from_firestore()


def get_favorite_recipe(title: str) -> str:
    return get_recipe_from_firestore(title=title)


def delete_favorite_recipe(title: str) -> str:
    return delete_recipe_from_firestore(title=title)


async def generate_memories_callback(callback_context: CallbackContext):
    """Writes conversation turns to Memory Bank after each turn."""
    try:
        await callback_context.add_session_to_memory()
    except ValueError as e:
        if "memory service is not available" in str(e):
            pass
        else:
            raise
    return None


# Build system prompt with A2uiSchemaManager (version 0.8) and BasicCatalog
a2ui_schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = a2ui_schema_manager.generate_system_prompt(
    role_description=(
        "You are 'Chef Gemini', an encouraging, creative, and knowledgeable culinary assistant. "
        "Your mission is to help users create delicious meals with ingredients they have on hand, "
        "generate food photography images and cooking demonstration videos (using generate_recipe_video), search real online recipes, geocode user locations, find nearby grocery stores, "
        "manage recipes using your Cloud Firestore database, compute nutritional analysis, and execute safe Python code for recipe scaling and calculations."
    ),
    workflow_description="Analyze the request, invoke appropriate tools, and return structured UI when appropriate.",
    ui_description=(
        "MEMORY & ALLERGIES: Always remember and store any food allergies, intolerances, or dietary restrictions mentioned by the user (e.g., peanuts, shellfish, gluten, dairy). Check your preloaded memories at the start of every interaction and NEVER suggest recipes, ingredients, or meals containing a user's allergen.\n"
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    code_executor=get_sandbox_code_executor(),
    tools=[
        PreloadMemoryTool(),
        generate_recipe_image,
        generate_recipe_video,
        geocode_address,
        find_nearby_places,
        search_online_recipes_api,
        calculate_recipe_nutrition,
        save_recipe_to_firestore,
        list_recipes_from_firestore,
        get_recipe_from_firestore,
        delete_recipe_from_firestore,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
