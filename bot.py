import telebot
import sqlite3
from datetime import datetime
from groq import Groq
from openai import OpenAI
import random
import base64

# =========================================
# ============  ТОКЕНЫ  ===================
# =========================================

BOT_TOKEN = "ВАШ_ТОКЕН"
GROQ_API_KEY = "ВАШ_КЛЮЧ_GROQ"
OPENROUTER_API_KEY = "ВАШ_КЛЮЧ_OPENROUTER"
groq_client = Groq(api_key=GROQ_API_KEY)
openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)
bot = telebot.TeleBot(BOT_TOKEN)

# =========================================
# ============  БАЗА ДАННЫХ  =============
# =========================================

def get_db():
    return sqlite3.connect("fridge.db", check_same_thread=False)

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            diet TEXT DEFAULT 'none',
            language TEXT DEFAULT 'ru',
            theme TEXT DEFAULT 'auto'
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "user_id": row[0],
            "diet": row[1],
            "language": row[2],
            "theme": row[3]
        }
    return None

def create_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def set_language(user_id, lang):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
    conn.commit()
    conn.close()

def set_diet(user_id, diet):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET diet = ? WHERE user_id = ?", (diet, user_id))
    conn.commit()
    conn.close()

def set_theme(user_id, theme):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET theme = ? WHERE user_id = ?", (theme, user_id))
    conn.commit()
    conn.close()

def t(user_id, ru, en):
    user = get_user(user_id)
    if user and user["language"] == "en":
        return en
    return ru

# =========================================
# ============  СОСТОЯНИЯ  ================
# =========================================

user_states = {}

def set_state(user_id, state):
    user_states[user_id] = state

def get_state(user_id):
    return user_states.get(user_id, "menu")

# =========================================
# ============  РАСПОЗНАВАНИЕ ФОТО  =======
# =========================================

def recognize_products_from_photo(image_bytes, user_id):
    lang = get_user(user_id)["language"] if get_user(user_id) else "ru"
    
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    
    if lang == "en":
        prompt = "List all the food products you see in this photo. Return ONLY a list separated by commas. Example: chicken, tomatoes, onion, carrot"
    else:
        prompt = "Перечисли все продукты питания, которые ты видишь на этом фото. Верни ТОЛЬКО список через запятую. Пример: курица, помидоры, лук, морковь"
    
    try:
        response = openrouter_client.chat.completions.create(
            model="google/gemini-3.5-flash",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            max_tokens=350
        )
        products_text = response.choices[0].message.content.strip()
        products = [p.strip() for p in products_text.split(",")]
        products = [p for p in products if p and len(p) > 1]
        return products
    except Exception as e:
        print(f"Vision error: {e}")
        return None

# =========================================
# ============  ГЕНЕРАЦИЯ РЕЦЕПТА  ========
# =========================================

def generate_recipe(products, user_id):
    diet = get_user(user_id)["diet"] if get_user(user_id) else "none"
    lang = get_user(user_id)["language"] if get_user(user_id) else "ru"
    diet_text = f" Диета: {diet}." if diet != "none" else ""
    products_text = ', '.join(products)
    
    state = get_state(user_id)
    
    # Запрос по названию блюда
    if len(products) == 1 and "," not in products_text:
        dish_name = products[0]
        if lang == "en":
            prompt = f"Give a detailed recipe for the dish: {dish_name}. Include ingredients, step-by-step cooking instructions, and calories per serving."
        else:
            prompt = f"Дай подробный рецепт блюда: {dish_name}. Включи ингредиенты, пошаговое приготовление и калорийность на порцию."
    
    # Обед с категорией (первое/второе/салат)
    elif state in ["lunch_soup", "lunch_main", "lunch_salat"]:
        state_names = {
            "lunch_soup": "первое блюдо (суп)",
            "lunch_main": "второе блюдо (горячее)",
            "lunch_salat": "салат"
        }
        dish_type = state_names.get(state, "блюдо")
        if lang == "en":
            prompt = f"Products: {products_text}.{diet_text} Give a recipe for {dish_type}. Include ingredients, step-by-step cooking instructions, and calories per serving."
        else:
            prompt = f"Продукты: {products_text}.{diet_text} Дай рецепт для {dish_type}. Включи ингредиенты, пошаговое приготовление и калорийность на порцию."
    
    # Полноценный обед (первое + второе + салат)
    elif state == "lunch":
        if lang == "en":
            prompt = f"""Products: {products_text}.{diet_text}
Give a COMPLETE LUNCH MENU with THREE separate dishes:
1. FIRST COURSE (soup)
2. SECOND COURSE (main dish)  
3. SALAD

For EACH dish include:
- Name
- Ingredients with quantities
- Step-by-step cooking instructions
- Calories per serving

Make sure all three dishes are clearly separated and easy to read."""
        else:
            prompt = f"""Продукты: {products_text}.{diet_text}
Дай ПОЛНОЕ МЕНЮ ДЛЯ ОБЕДА из ТРЁХ отдельных блюд:
1. ПЕРВОЕ БЛЮДО (суп)
2. ВТОРОЕ БЛЮДО (горячее)
3. САЛАТ

Для КАЖДОГО блюда укажи:
- Название
- Ингредиенты с количеством
- Пошаговое приготовление
- Калорийность на порцию

Чётко раздели все три блюда, чтобы они были легко читаемы."""
    
    # Обычный рецепт из продуктов
    else:
        if lang == "en":
            prompt = f"Products: {products_text}.{diet_text} Give a recipe with ingredients, steps and calories."
        else:
            prompt = f"Продукты: {products_text}.{diet_text} Дай рецепт с ингредиентами, шагами и калориями."
    
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=random.uniform(0.7, 1.0),
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ Ошибка: {e}"# =========================================
# ============  КЛАВИАТУРЫ  ===============
# =========================================

def main_menu(user_id):
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        telebot.types.InlineKeyboardButton(t(user_id, "🥗 Диета", "🥗 Diet"), callback_data="diet"),
        telebot.types.InlineKeyboardButton(t(user_id, "🍽 Рецепт", "🍽 Recipe"), callback_data="recipe")
    )
    kb.add(
        telebot.types.InlineKeyboardButton(t(user_id, "🌅 Завтрак", "🌅 Breakfast"), callback_data="breakfast"),
        telebot.types.InlineKeyboardButton(t(user_id, "☀️ Обед", "☀️ Lunch"), callback_data="lunch")
    )
    kb.add(
        telebot.types.InlineKeyboardButton(t(user_id, "🌙 Ужин", "🌙 Dinner"), callback_data="dinner"),
        telebot.types.InlineKeyboardButton(t(user_id, "⚙️ Настройки", "⚙️ Settings"), callback_data="settings")
    )
    return kb

def diet_menu(user_id):
    kb = telebot.types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        telebot.types.InlineKeyboardButton(t(user_id, "🍽 Худею", "🍽 Lose weight"), callback_data="diet_lose"),
        telebot.types.InlineKeyboardButton(t(user_id, "💪 Спортсмен", "💪 Athlete"), callback_data="diet_sport"),
        telebot.types.InlineKeyboardButton(t(user_id, "🩺 Диабет", "🩺 Diabetes"), callback_data="diet_diabetes"),
        telebot.types.InlineKeyboardButton(t(user_id, "❤️ Здоровое питание", "❤️ Healthy"), callback_data="diet_healthy"),
        telebot.types.InlineKeyboardButton(t(user_id, "🚫 Без диеты", "🚫 No diet"), callback_data="diet_none"),
        telebot.types.InlineKeyboardButton(t(user_id, "🔙 Назад", "🔙 Back"), callback_data="menu")
    )
    return kb

def settings_menu(user_id):
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        telebot.types.InlineKeyboardButton(t(user_id, "🌐 Язык", "🌐 Language"), callback_data="settings_lang"),
        telebot.types.InlineKeyboardButton(t(user_id, "🌙 Тема", "🌙 Theme"), callback_data="settings_theme"),
        telebot.types.InlineKeyboardButton(t(user_id, "🔙 Назад", "🔙 Back"), callback_data="menu")
    )
    return kb

def lang_menu(user_id):
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        telebot.types.InlineKeyboardButton("🇷🇺 Русский", callback_data="set_lang_ru"),
        telebot.types.InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en"),
        telebot.types.InlineKeyboardButton(t(user_id, "🔙 Назад", "🔙 Back"), callback_data="settings")
    )
    return kb

def theme_menu(user_id):
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        telebot.types.InlineKeyboardButton(t(user_id, "☀️ Светлая", "☀️ Light"), callback_data="set_theme_light"),
        telebot.types.InlineKeyboardButton(t(user_id, "🌙 Тёмная", "🌙 Dark"), callback_data="set_theme_dark"),
        telebot.types.InlineKeyboardButton(t(user_id, "🔄 Авто", "🔄 Auto"), callback_data="set_theme_auto"),
        telebot.types.InlineKeyboardButton(t(user_id, "🔙 Назад", "🔙 Back"), callback_data="settings")
    )
    return kb

def lunch_menu(user_id):
    kb = telebot.types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        telebot.types.InlineKeyboardButton(t(user_id, "🍲 Первые блюда", "🍲 Soups"), callback_data="lunch_soups"),
        telebot.types.InlineKeyboardButton(t(user_id, "🍗 Вторые блюда", "🍗 Main dishes"), callback_data="lunch_mains")
    )
    kb.add(
        telebot.types.InlineKeyboardButton(t(user_id, "🥗 Салаты", "🥗 Salads"), callback_data="lunch_salads"),
        telebot.types.InlineKeyboardButton(t(user_id, "🔙 Назад", "🔙 Back"), callback_data="menu")
    )
    return kb

# =========================================
# ============  ОБРАБОТЧИКИ  ==============
# =========================================

@bot.message_handler(commands=["start"])
def start(message):
    print("✅ START получен!")
    user_id = message.from_user.id
    init_db()
    create_user(user_id)
    bot.send_message(
        user_id,
        t(user_id,
            "🍳 ХОЛОДИЛЬНИК\n\n📸 Отправьте фото холодильника\n📖 Или введите название блюда\n🥗 Или список продуктов через запятую\n\n🔓 Бот полностью бесплатный!",
            "🍳 FRIDGE\n\n📸 Send photo of your fridge\n📖 Or enter dish name\n🥗 Or list products with commas\n\n🔓 Bot is completely free!"
        ),
        reply_markup=main_menu(user_id)
    )

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    user_id = message.from_user.id
    lang = get_user(user_id)["language"] if get_user(user_id) else "ru"
    
    bot.reply_to(message, t(user_id, "⏳ Анализирую фото...", "⏳ Analyzing photo..."))
    
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        file_bytes = bot.download_file(file_info.file_path)
        
        products = recognize_products_from_photo(file_bytes, user_id)
        
        if not products:
            bot.reply_to(
                message,
                t(user_id, "❌ Не удалось распознать продукты. Попробуйте сфотографировать крупнее.", "❌ Could not recognize products. Try taking a closer photo."),
                reply_markup=main_menu(user_id)
            )
            return
        
        products_text = ", ".join(products)
        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            telebot.types.InlineKeyboardButton(t(user_id, "✅ Да, верно", "✅ Yes, correct"), callback_data=f"confirm_{user_id}_{products_text}"),
            telebot.types.InlineKeyboardButton(t(user_id, "✏️ Изменить", "✏️ Edit"), callback_data=f"edit_{user_id}")
        )
        kb.add(telebot.types.InlineKeyboardButton(t(user_id, "🔙 Назад", "🔙 Back"), callback_data="menu"))
        
        bot.reply_to(
            message,
            t(user_id, f"🛒 Я вижу: {products_text}\n\nЭто верно?", f"🛒 I see: {products_text}\n\nIs this correct?"),
            reply_markup=kb
        )
        
    except Exception as e:
        bot.reply_to(
            message,
            t(user_id, f"❌ Ошибка: {e}", f"❌ Error: {e}"),
            reply_markup=main_menu(user_id)
        )

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    user_id = call.from_user.id
    data = call.data
    print(f"✅ Кнопка: {data}")

    if data == "menu":
        bot.edit_message_text(
            t(user_id,
                "🍳 ХОЛОДИЛЬНИК\n\n📸 Отправьте фото холодильника\n📖 Или введите название блюда\n🥗 Или список продуктов через запятую",
                "🍳 FRIDGE\n\n📸 Send photo of your fridge\n📖 Or enter dish name\n🥗 Or list products with commas"
            ),
            user_id, call.message.message_id,
            reply_markup=main_menu(user_id)
        )
        bot.answer_callback_query(call.id)
        return

    # ===== ПОДТВЕРЖДЕНИЕ ФОТО =====
    if data.startswith("confirm_"):
        parts = data.split("_")
        products_text = "_".join(parts[2:])
        products = [p.strip() for p in products_text.split(",")]
        products = [p for p in products if p and len(p) > 1]
        
        bot.edit_message_text(
            t(user_id, "⏳ Готовлю рецепт...", "⏳ Cooking..."),
            user_id, call.message.message_id
        )
        recipe = generate_recipe(products, user_id)
        bot.edit_message_text(
            f"🍽 {recipe}",
            user_id, call.message.message_id,
            reply_markup=main_menu(user_id)
        )
        bot.answer_callback_query(call.id)
        return

    # ===== ИЗМЕНЕНИЕ ФОТО =====
    if data.startswith("edit_"):
        bot.edit_message_text(
            t(user_id, "✏️ Напишите правильный список продуктов через запятую", "✏️ Write the correct list of products with commas"),
            user_id, call.message.message_id
        )
        set_state(user_id, "edit_products")
        bot.answer_callback_query(call.id)
        return

    # ===== ДИЕТА =====
    if data == "diet":
        bot.edit_message_text(
            t(user_id, "🥗 ВЫБЕРИТЕ ДИЕТУ:", "🥗 CHOOSE DIET:"),
            user_id, call.message.message_id,
            reply_markup=diet_menu(user_id)
        )
        bot.answer_callback_query(call.id)
        return

    if data.startswith("diet_"):
        diet = data.split("_")[1]
        set_diet(user_id, diet)
        diet_names = {"lose": "Похудение", "sport": "Спортсмен", "diabetes": "Диабет", "healthy": "Здоровое питание", "none": "Без диеты"}
        bot.answer_callback_query(call.id, f"✅ {diet_names.get(diet, diet)}")
        bot.edit_message_text(
            t(user_id, f"🥗 Диета: {diet_names.get(diet, diet)}", f"🥗 Diet: {diet_names.get(diet, diet)}"),
            user_id, call.message.message_id,
            reply_markup=main_menu(user_id)
        )
        return

    # ===== РЕЦЕПТ =====
    if data == "recipe":
        bot.edit_message_text(
            t(user_id, "🍽 Напишите продукты или название блюда", "🍽 Write products or dish name"),
            user_id, call.message.message_id
        )
        bot.answer_callback_query(call.id)
        return

    # ===== ЗАВТРАК =====
    if data == "breakfast":
        bot.edit_message_text(
            t(user_id, "🌅 ЗАВТРАК\n\nНапишите продукты или название блюда", "🌅 BREAKFAST\n\nWrite products or dish name"),
            user_id, call.message.message_id
        )
        bot.answer_callback_query(call.id)
        return

    # ===== ОБЕД =====
    if data == "lunch":
        set_state(user_id, "lunch")
        bot.edit_message_text(
            t(user_id,
                "☀️ ОБЕД\n\nВыберите категорию:",
                "☀️ LUNCH\n\nChoose category:"
            ),
            user_id, call.message.message_id,
            reply_markup=lunch_menu(user_id)
        )
        bot.answer_callback_query(call.id)
        return

    if data == "lunch_soups":
        set_state(user_id, "lunch_soup")
        bot.edit_message_text(
            t(user_id,
                "🍲 ПЕРВЫЕ БЛЮДА\n\nНапишите продукты или название супа",
                "🍲 SOUPS\n\nWrite products or soup name"
            ),
            user_id, call.message.message_id
        )
        bot.answer_callback_query(call.id)
        return

    if data == "lunch_mains":
        set_state(user_id, "lunch_main")
        bot.edit_message_text(
            t(user_id,
                "🍗 ВТОРЫЕ БЛЮДА\n\nНапишите продукты или название блюда",
                "🍗 MAIN DISHES\n\nWrite products or dish name"
            ),
            user_id, call.message.message_id
        )
        bot.answer_callback_query(call.id)
        return

    if data == "lunch_salads":
        set_state(user_id, "lunch_salat")
        bot.edit_message_text(
            t(user_id,
                "🥗 САЛАТЫ\n\nНапишите продукты или название салата",
                "🥗 SALADS\n\nWrite products or salad name"
            ),
            user_id, call.message.message_id
        )
        bot.answer_callback_query(call.id)
        return

    # ===== УЖИН =====
    if data == "dinner":
        bot.edit_message_text(
            t(user_id, "🌙 УЖИН\n\nНапишите продукты или название блюда", "🌙 DINNER\n\nWrite products or dish name"),
            user_id, call.message.message_id
        )
        bot.answer_callback_query(call.id)
        return

    # ===== НАСТРОЙКИ =====
    if data == "settings":
        user = get_user(user_id)
        lang = "Русский" if user["language"] == "ru" else "English"
        theme = user["theme"]
        theme_names = {"light": "☀️ Светлая", "dark": "🌙 Тёмная", "auto": "🔄 Авто"}
        if user["language"] == "en":
            theme_names = {"light": "☀️ Light", "dark": "🌙 Dark", "auto": "🔄 Auto"}
        bot.edit_message_text(
            t(user_id,
                f"⚙️ НАСТРОЙКИ\n\n🌐 Язык: {lang}\n🌙 Тема: {theme_names.get(theme, 'Авто')}",
                f"⚙️ SETTINGS\n\n🌐 Language: {lang}\n🌙 Theme: {theme_names.get(theme, 'Auto')}"
            ),
            user_id, call.message.message_id,
            reply_markup=settings_menu(user_id)
        )
        bot.answer_callback_query(call.id)
        return

    if data == "settings_lang":
        bot.edit_message_text(
            t(user_id, "🌐 ВЫБЕРИТЕ ЯЗЫК:", "🌐 SELECT LANGUAGE:"),
            user_id, call.message.message_id,
            reply_markup=lang_menu(user_id)
        )
        bot.answer_callback_query(call.id)
        return

    if data.startswith("set_lang_"):
        lang = data.split("_")[2]
        set_language(user_id, lang)
        bot.answer_callback_query(call.id, "✅ Язык сохранён!")
        user = get_user(user_id)
        lang_text = "Русский" if user["language"] == "ru" else "English"
        theme = user["theme"]
        theme_names = {"light": "☀️ Светлая", "dark": "🌙 Тёмная", "auto": "🔄 Авто"}
        if user["language"] == "en":
            theme_names = {"light": "☀️ Light", "dark": "🌙 Dark", "auto": "🔄 Auto"}
        bot.edit_message_text(
            t(user_id,
                f"⚙️ НАСТРОЙКИ\n\n🌐 Язык: {lang_text}\n🌙 Тема: {theme_names.get(theme, 'Авто')}",
                f"⚙️ SETTINGS\n\n🌐 Language: {lang_text}\n🌙 Theme: {theme_names.get(theme, 'Auto')}"
            ),
            user_id, call.message.message_id,
            reply_markup=settings_menu(user_id)
        )
        return

    if data == "settings_theme":
        bot.edit_message_text(
            t(user_id, "🌙 ВЫБЕРИТЕ ТЕМУ:", "🌙 SELECT THEME:"),
            user_id, call.message.message_id,
            reply_markup=theme_menu(user_id)
        )
        bot.answer_callback_query(call.id)
        return

    if data.startswith("set_theme_"):
        theme = data.split("_")[2]
        set_theme(user_id, theme)
        bot.answer_callback_query(call.id, "✅ Тема сохранена!")
        user = get_user(user_id)
        lang_text = "Русский" if user["language"] == "ru" else "English"
        theme = user["theme"]
        theme_names = {"light": "☀️ Светлая", "dark": "🌙 Тёмная", "auto": "🔄 Авто"}
        if user["language"] == "en":
            theme_names = {"light": "☀️ Light", "dark": "🌙 Dark", "auto": "🔄 Auto"}
        bot.edit_message_text(
            t(user_id,
                f"⚙️ НАСТРОЙКИ\n\n🌐 Язык: {lang_text}\n🌙 Тема: {theme_names.get(theme, 'Авто')}",
                f"⚙️ SETTINGS\n\n🌐 Language: {lang_text}\n🌙 Theme: {theme_names.get(theme, 'Auto')}"
            ),
            user_id, call.message.message_id,
            reply_markup=settings_menu(user_id)
        )
        return

    bot.answer_callback_query(call.id, "❌ Неизвестная команда")

# =========================================
# ============  ОБРАБОТКА ТЕКСТА ==========
# =========================================

@bot.message_handler(func=lambda msg: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Если пользователь в режиме редактирования продуктов из фото
    if get_state(user_id) == "edit_products":
        if "," in text and len(text.split(",")) >= 2:
            products = [p.strip() for p in text.split(",")]
            products = [p for p in products if p]
            if len(products) >= 2:
                set_state(user_id, "menu")
                bot.reply_to(message, "⏳ Готовлю рецепт...")
                recipe = generate_recipe(products, user_id)
                bot.reply_to(message, f"🍽 {recipe}", reply_markup=main_menu(user_id))
                return
        bot.reply_to(message, "❌ Напишите минимум 2 продукта через запятую")
        return
    
    # Если пользователь выбрал категорию обеда (первое, второе или салат)
    if get_state(user_id) in ["lunch_soup", "lunch_main", "lunch_salat"]:
        state = get_state(user_id)
        state_names = {
            "lunch_soup": "первое блюдо (суп)",
            "lunch_main": "второе блюдо (горячее)",
            "lunch_salat": "салат"
        }
        bot.reply_to(message, f"⏳ Готовлю рецепт {state_names.get(state, 'блюда')}...")
        
        if "," in text and len(text.split(",")) >= 2:
            products = [p.strip() for p in text.split(",")]
        else:
            products = [text]
        
        set_state(user_id, "menu")
        recipe = generate_recipe(products, user_id)
        bot.reply_to(message, f"🍽 {recipe}", reply_markup=main_menu(user_id))
        return
    
    # Если пользователь в режиме обеда без категории — выдаём полное меню
    if get_state(user_id) == "lunch":
        set_state(user_id, "menu")
        bot.reply_to(message, "⏳ Готовлю полноценное меню для обеда...")
        if "," in text and len(text.split(",")) >= 2:
            products = [p.strip() for p in text.split(",")]
        else:
            products = [text]
        recipe = generate_recipe(products, user_id)
        bot.reply_to(message, f"🍽 {recipe}", reply_markup=main_menu(user_id))
        return
    
    # Проверяем: это название блюда (нет запятых, до 5 слов)
    is_dish_name = "," not in text and len(text.split()) <= 5
    
    # Если пользователь просто хочет рецепт по названию
    if is_dish_name and not text.startswith("/"):
        bot.reply_to(message, "⏳ Ищу рецепт...")
        recipe = generate_recipe([text], user_id)
        bot.reply_to(message, f"🍽 {recipe}", reply_markup=main_menu(user_id))
        return
    
    # Если пользователь ввел список продуктов через запятую
    if "," in text and len(text.split(",")) >= 2:
        products = [p.strip() for p in text.split(",")]
        products = [p for p in products if p]
        if len(products) >= 2:
            bot.reply_to(message, "⏳ Готовлю рецепт...")
            recipe = generate_recipe(products, user_id)
            bot.reply_to(message, f"🍽 {recipe}", reply_markup=main_menu(user_id))
            return
    
    bot.reply_to(
        message,
        t(user_id,
            "🍳 Напишите:\n\n📖 Название блюда: борщ, греческий салат\n🥗 Список продуктов: курица, рис, лук\n📸 Или отправьте фото холодильника",
            "🍳 Write:\n\n📖 Dish name: borscht, Greek salad\n🥗 Products list: chicken, rice, onion\n📸 Or send photo of your fridge"
        ),
        reply_markup=main_menu(user_id)
    )

# =========================================
# ============  ЗАПУСК  ===================
# =========================================

if __name__ == "__main__":
    init_db()
    print("🚀 Бот ХОЛОДИЛЬНИК (с фото + обедами) запущен!")
    bot.infinity_polling()