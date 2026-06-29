import os
import json
import requests
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# --- КОНФИГУРАЦИЯ ---
load_dotenv()
API_TOKEN = os.getenv('BOT_TOKEN')
if not API_TOKEN:
    raise ValueError("Не найден BOT_TOKEN в .env файле. Создайте .env и добавьте BOT_TOKEN=ваш_токен")

BASE_URL = "https://www.themealdb.com/api/json/v1/1"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ (JSON) ---
FAV_FILE = "favorites.json"
RATING_FILE = "ratings.json"

# Кэш для поиска (чтобы не терять список при клике)
search_cache = {}

# --- ФУНКЦИИ БАЗЫ ДАННЫХ ---

def load_db(filename):
    if not os.path.exists(filename):
        return {}
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_db(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Избранное
def add_fav(chat_id, meal):
    db = load_db(FAV_FILE)
    uid = str(chat_id)
    if uid not in db: db[uid] = []
    if not any(m['idMeal'] == meal['idMeal'] for m in db[uid]):
        db[uid].append(meal)
        save_db(FAV_FILE, db)
        return True
    return False

def remove_fav(chat_id, meal_id):
    db = load_db(FAV_FILE)
    uid = str(chat_id)
    if uid in db:
        db[uid] = [m for m in db[uid] if m['idMeal'] != meal_id]
        save_db(FAV_FILE, db)
    return True

def get_favs(chat_id):
    return load_db(FAV_FILE).get(str(chat_id), [])

def is_in_fav(chat_id, meal_id):
    return any(m['idMeal'] == meal_id for m in get_favs(chat_id))

# Рейтинг
def set_rating(meal_id, user_id, rating):
    db = load_db(RATING_FILE)
    if meal_id not in db: db[meal_id] = {}
    db[meal_id][str(user_id)] = rating
    save_db(RATING_FILE, db)

# --- ЛОГИКА ОТОБРАЖЕНИЯ РЕЦЕПТА ---

async def show_recipe_update(chat_id, meal_id, message):
    """Обновляет текущее сообщение с рецептом (кнопки, текст)"""
    res = requests.get(f"{BASE_URL}/lookup.php?i={meal_id}").json()
    if 'meals' not in res or not res['meals']:
        return

    meal = res['meals'][0]
    instructions = meal['strInstructions'].replace('<br>', '\n').replace('<br />', '\n')
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    
    # Кнопки действий
    if is_in_fav(chat_id, meal_id):
        kb.inline_keyboard.append([InlineKeyboardButton(text="🗑 Удалить из избранного", callback_data=f"del_direct_{meal_id}")])
    else:
        kb.inline_keyboard.append([InlineKeyboardButton(text="⭐ В избранное", callback_data=f"add_direct_{meal_id}")])
        
    # Кнопки рейтинга
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="1 ⭐", callback_data=f"rate_{meal_id}_1"),
        InlineKeyboardButton(text="2 ⭐", callback_data=f"rate_{meal_id}_2"),
        InlineKeyboardButton(text="3 ⭐", callback_data=f"rate_{meal_id}_3"),
        InlineKeyboardButton(text="4 ⭐", callback_data=f"rate_{meal_id}_4"),
        InlineKeyboardButton(text="5 ⭐", callback_data=f"rate_{meal_id}_5"),
    ])
    
    caption = f"🍽 Рецепт: {meal['strMeal']}\n\n📝 Инструкция:\n{instructions}"
    
    try:
        await message.edit_caption(caption=caption, reply_markup=kb)
    except:
        pass

async def send_new_recipe(chat_id, meal_id, message):
    """Отправляет новое сообщение с рецептом"""
    res = requests.get(f"{BASE_URL}/lookup.php?i={meal_id}").json()
    if 'meals' not in res or not res['meals']:
        await message.answer("❌ Ошибка загрузки рецепта.")
        return

    meal = res['meals'][0]
    instructions = meal['strInstructions'].replace('<br>', '\n').replace('<br />', '\n')
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    
    if is_in_fav(chat_id, meal_id):
        kb.inline_keyboard.append([InlineKeyboardButton(text="🗑 Удалить из избранного", callback_data=f"del_direct_{meal_id}")])
    else:
        kb.inline_keyboard.append([InlineKeyboardButton(text="⭐ В избранное", callback_data=f"add_direct_{meal_id}")])
        
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="1 ⭐", callback_data=f"rate_{meal_id}_1"),
        InlineKeyboardButton(text="2 ⭐", callback_data=f"rate_{meal_id}_2"),
        InlineKeyboardButton(text="3 ⭐", callback_data=f"rate_{meal_id}_3"),
        InlineKeyboardButton(text="4 ⭐", callback_data=f"rate_{meal_id}_4"),
        InlineKeyboardButton(text="5 ⭐", callback_data=f"rate_{meal_id}_5"),
    ])
    
    caption = f"🍽 Рецепт: {meal['strMeal']}\n\n📝 Инструкция:\n{instructions}"
    
    await message.answer_photo(photo=meal['strMealThumb'], caption=caption, reply_markup=kb)

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я кулинарный бот. 🍳\n"
        "Введите ингредиент (лучше на английском), и я найду рецепты.\n"
        "После просмотра рецепта можно поставить оценку или сохранить его."
    )

@dp.message(Command("favorites"))
async def cmd_favorites(message: types.Message):
    chat_id = message.chat.id
    favs = get_favs(chat_id)
    
    if not favs:
        await message.answer("📚 У вас пока нет сохраненных рецептов.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for i, meal in enumerate(favs[:20]):
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"🍽 {meal['strMeal']}", callback_data=f"open_fav_{i}"),
            InlineKeyboardButton(text="🗑", callback_data=f"del_fav_{i}")
        ])
    await message.answer("📚 Ваши рецепты:", reply_markup=kb)

@dp.message()
async def search_recipe(message: types.Message):
    if message.text.startswith('/'): return
    ingredient = message.text.strip()
    
    try:
        res = requests.get(f"{BASE_URL}/filter.php?i={ingredient}").json()
        meals = res.get('meals', [])
        
        if not meals:
            await message.answer(f"😕 Ничего не найдено по '{ingredient}'.")
            return
            
        search_cache[message.chat.id] = [m['idMeal'] for m in meals]
        
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        for i, meal in enumerate(meals[:10]):
            kb.inline_keyboard.append([
                InlineKeyboardButton(text=f"👁 {meal['strMeal']}", callback_data=f"lookup_{meal['idMeal']}"),
                InlineKeyboardButton(text="⭐", callback_data=f"add_fav_search_{i}")
            ])
        await message.answer(f"🔍 Найдено {len(meals)}. Топ-10:", reply_markup=kb)
    except Exception as e:
        await message.answer(f"⚠️ Ошибка поиска: {e}")

@dp.callback_query(lambda c: c.data.startswith(('lookup_', 'add_fav_search_', 'open_fav_', 'del_fav_', 'rate_', 'add_direct_', 'del_direct_', 'back_search')))
async def handle_callback(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    
    # 1. Открыть рецепт (создать новое сообщение)
    if callback.data.startswith('lookup_'):
        meal_id = callback.data.split('_')[1]
        await send_new_recipe(chat_id, meal_id, callback.message)
        await callback.answer()
        return

    # 2. Добавить в избранное из поиска
    if callback.data.startswith('add_fav_search_'):
        idx = int(callback.data.split('_')[3])
        ids = search_cache.get(chat_id, [])
        if idx < len(ids):
            res = requests.get(f"{BASE_URL}/lookup.php?i={ids[idx]}").json()
            if res.get('meals'):
                if add_fav(chat_id, res['meals'][0]):
                    await callback.answer("✅ Сохранено!", show_alert=True)
                else:
                    await callback.answer("⚠️ Уже сохранено.", show_alert=True)
        return

    # 3. Открыть рецепт из избранного
    if callback.data.startswith('open_fav_'):
        idx = int(callback.data.split('_')[2])
        favs = get_favs(chat_id)
        if idx < len(favs):
            meal_id = favs[idx]['idMeal']
            await send_new_recipe(chat_id, meal_id, callback.message)
        await callback.answer()
        return

    # 4. Удалить из избранного (список)
    if callback.data.startswith('del_fav_'):
        idx = int(callback.data.split('_')[2])
        favs = get_favs(chat_id)
        if idx < len(favs):
            remove_fav(chat_id, favs[idx]['idMeal'])
            await cmd_favorites(callback.message)
        await callback.answer()
        return
    
    # 5. Рейтинг
    if callback.data.startswith('rate_'):
        parts = callback.data.split('_')
        meal_id = parts[1]
        rating = parts[2]
        set_rating(meal_id, chat_id, rating)
        await callback.answer(f"Вы оценили на {rating} ⭐")
        await show_recipe_update(chat_id, meal_id, callback.message)
        return

    # 6. Добавить в избранное (из просмотра рецепта)
    if callback.data.startswith('add_direct_'):
        meal_id = callback.data.split('_')[2]
        res = requests.get(f"{BASE_URL}/lookup.php?i={meal_id}").json()
        if res.get('meals'):
            add_fav(chat_id, res['meals'][0])
        await show_recipe_update(chat_id, meal_id, callback.message)
        await callback.answer()
        return

    # 7. Удалить из избранного (из просмотра рецепта)
    if callback.data.startswith('del_direct_'):
        meal_id = callback.data.split('_')[2]
        remove_fav(chat_id, meal_id)
        await show_recipe_update(chat_id, meal_id, callback.message)
        await callback.answer()
        return
        
    if callback.data == 'back_search':
        await callback.answer()

if __name__ == "__main__":
    print("Бот запущен...")
    dp.run_polling(bot)