from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
import uuid
import sqlite3
import os
import time
import asyncio
import config

MOVE_TIMEOUT = 30

bot = Bot(config.TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)

users = {}
admin_pending = {}  

games = {}
DEFAULT_GAME_PRICE = 1000
DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")

ITEMS = {
    'symbol_stars': {'id':'symbol_stars','category':'symbol','name':'Звёздочки','price':500,'preview':{'x':'⭐','o':'✴️'},'desc':'X→⭐, O→✴️'},
    'symbol_fox': {'id':'symbol_fox','category':'symbol','name':'Лисички','price':700,'preview':{'x':'🦊','o':'🌕'},'desc':'Лисички вместо X/O'},

    # Emoji packs (use emojis as alternatives)
    'emoji_party': {'id':'emoji_party','category':'emoji_pack','name':'Пак «Вечеринка»','price':800,'preview':'🎉🥳🍾','desc':'Яркие эмоции вместо X/O'},
    'emoji_space': {'id':'emoji_space','category':'emoji_pack','name':'Пак «Космос»','price':900,'preview':'🚀🌟👾','desc':'Космические эмодзи'},

    # Backgrounds
    'bg_neon': {'id':'bg_neon','category':'background','name':'Неоновое поле','price':700,'preview':'🔵🔴','desc':'Стильный неоновый фон поля'},
    'bg_wood': {'id':'bg_wood','category':'background','name':'Деревянное поле','price':600,'preview':'🪵','desc':'Тёплый деревянный фон'},

    # Animations
    'anim_confetti': {'id':'anim_confetti','category':'animation','name':'Конфетти','price':1200,'preview':'🎊','desc':'Праздничная анимация при победе'},
    'anim_fireworks': {'id':'anim_fireworks','category':'animation','name':'Фейерверки','price':1400,'preview':'🎆','desc':'Взрыв эмоций при победе'}
}


def find_item(item_id):
    return ITEMS.get(item_id)


def items_by_category(cat):
    return [it for it in ITEMS.values() if it['category'] == cat]


def owns_item(user_id, item_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT 1 FROM purchases WHERE user_id=? AND item_id=?', (user_id, item_id))
    res = c.fetchone()
    conn.close()
    return bool(res)


def grant_item(user_id, item_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO purchases (user_id, item_id, bought_at) VALUES (?, ?, ?)', (user_id, item_id, int(time.time())))
    conn.commit()
    conn.close()


def get_user_items(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT item_id FROM purchases WHERE user_id=?', (user_id,))
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT DEFAULT '',
            coins INTEGER,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            draws INTEGER DEFAULT 0,
            rating INTEGER DEFAULT 1200,
            equipped_symbol TEXT DEFAULT '',
            equipped_bg TEXT DEFAULT '',
            equipped_emoji_pack TEXT DEFAULT '',
            equipped_animation TEXT DEFAULT ''
        )
        """
    )
    conn.commit()

    c.execute("PRAGMA table_info(users)")
    cols = [r[1] for r in c.fetchall()]
    if 'wins' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN wins INTEGER DEFAULT 0")
    if 'losses' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN losses INTEGER DEFAULT 0")
    if 'draws' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN draws INTEGER DEFAULT 0")
    if 'rating' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN rating INTEGER DEFAULT 1200")
    if 'name' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN name TEXT DEFAULT ''")
    if 'equipped_symbol' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN equipped_symbol TEXT DEFAULT ''")
    if 'equipped_bg' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN equipped_bg TEXT DEFAULT ''")
    if 'equipped_emoji_pack' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN equipped_emoji_pack TEXT DEFAULT ''")
    if 'equipped_animation' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN equipped_animation TEXT DEFAULT ''")

    # purchases table: records owned items per user
    c.execute(
        "CREATE TABLE IF NOT EXISTS purchases (user_id INTEGER, item_id TEXT, bought_at INTEGER, PRIMARY KEY(user_id, item_id))"
    )

    conn.commit()
    conn.close()

init_db()


def ensure_user_record(user):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id FROM users WHERE id=?', (user.id,))
    display_name = ' '.join(filter(None, [getattr(user, 'first_name', ''), getattr(user, 'last_name', '')])).strip() or (user.username or 'no_username')
    if not c.fetchone():
        c.execute('INSERT INTO users (id, username, name, coins, wins, losses, draws, rating, equipped_symbol, equipped_bg, equipped_emoji_pack, equipped_animation) VALUES (?, ?, ?, ?, 0, 0, 0, 1200, ?, ?, ?, ?)', (user.id, user.username or 'no_username', display_name, 5000, '', '', '', ''))
    else:
        c.execute('UPDATE users SET username=?, name=? WHERE id=?', (user.username or 'no_username', display_name, user.id))
    conn.commit()
    conn.close()


def load_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, username, name, coins, wins, losses, draws, rating, equipped_symbol, equipped_bg, equipped_emoji_pack, equipped_animation FROM users WHERE id=?', (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "username": row[1],
            "name": row[2] or row[1],
            "coins": row[3],
            "wins": row[4] or 0,
            "losses": row[5] or 0,
            "draws": row[6] or 0,
            "rating": row[7] or 1200,
            "equipped_symbol": row[8] or '',
            "equipped_bg": row[9] or '',
            "equipped_emoji_pack": row[10] or '',
            "equipped_animation": row[11] or ''
        }
    return None


def save_user(user):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET username=?, name=?, coins=?, wins=?, losses=?, draws=?, rating=?, equipped_symbol=?, equipped_bg=?, equipped_emoji_pack=?, equipped_animation=? WHERE id=?', (
        user['username'],
        user.get('name', user['username']),
        user['coins'],
        user.get('wins', 0),
        user.get('losses', 0),
        user.get('draws', 0),
        user.get('rating', 1200),
        user.get('equipped_symbol', ''),
        user.get('equipped_bg', ''),
        user.get('equipped_emoji_pack', ''),
        user.get('equipped_animation', ''),
        user['id']
    ))
    conn.commit()
    conn.close()


def get_all_user_ids():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id FROM users')
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]



def cancel_game_timer(game_id):
    t = games.get(game_id, {}).get('timer_task')
    if t and not t.done():
        t.cancel()


async def move_timer(game_id, inline_message_id):
    try:
        await asyncio.sleep(MOVE_TIMEOUT)
        game = games.get(game_id)
        if not game or not game.get('started'):
            return
        if time.time() - game.get('last_move_time', 0) >= MOVE_TIMEOUT:
            turn = game['turn']
            winner_symbol = 'O' if turn == 'X' else 'X'
            winner_id = game['x'] if winner_symbol == 'X' else game['o']
            loser_id = game['o'] if winner_id == game['x'] else game['x']
            price = game.get('price', DEFAULT_GAME_PRICE)
            # payout
            if winner_id in users:
                users[winner_id]['coins'] += price * 2
                users[winner_id]['wins'] = users[winner_id].get('wins', 0) + 1
                users[loser_id]['losses'] = users[loser_id].get('losses', 0) + 1
                # rating change
                ra = users[winner_id].get('rating', 1200)
                rb = users[loser_id].get('rating', 1200)
                delta = elo_delta(ra, rb, k=32)
                users[winner_id]['rating'] = ra + delta
                users[loser_id]['rating'] = rb - delta
                save_user(users[winner_id])
                save_user(users[loser_id])
                text = (
                    f"<b>🎮 Игра #{game_id}</b>\n\n"
                    f"⏱ Авто-поражение — игрок пропустил ход (>{MOVE_TIMEOUT}s)\n"
                    f"🏆 Победил <b>{users[winner_id].get('name') or users[winner_id]['username']}</b> (+{delta} рейтинга)\n"
                    f"💰 Выигрыш: <b>{price*2}</b> коинов"
                )
                # edit where the game message lives (chat or inline)
                if game.get('type') == 'chat' and game.get('chat_id') and game.get('message_id'):
                    try:
                        await bot.edit_message_text(text, chat_id=game['chat_id'], message_id=game['message_id'], parse_mode=types.ParseMode.HTML)
                    except Exception:
                        pass
                else:
                    try:
                        if inline_message_id:
                            await safe_edit_message_text(inline_message_id=inline_message_id, text=text, parse_mode=types.ParseMode.HTML)
                    except Exception:
                        pass
            games.pop(game_id, None)
    except asyncio.CancelledError:
        return
    except Exception:
        return


def reg_user(user):
    ensure_user_record(user)
    u = load_user(user.id)
    users[user.id] = u


def new_board():
    return [" "] * 9


def kb_join(game_id):
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton(
            "➕ Подключиться",
            callback_data=f"join:{game_id}"
        )
    )
    return kb


def kb_board(game_id):
    kb = InlineKeyboardMarkup(row_width=3)
    for i in range(9):
        text = games[game_id]["board"][i]
        kb.insert(
            InlineKeyboardButton(
                text=text if text != " " else "·",
                callback_data=f"move:{game_id}:{i}"
            )
        )
    return kb


def check_winner(board):
    win_lines = [
        (0,1,2),(3,4,5),(6,7,8),
        (0,3,6),(1,4,7),(2,5,8),
        (0,4,8),(2,4,6)
    ]

    for a, b, c in win_lines:
        if board[a] != " " and board[a] == board[b] == board[c]:
            return board[a]  # X или O

    if " " not in board:
        return "draw"

    return None


def get_rank_name(rating):
    if rating >= 2000:
        return "🔴 Легенда XO"
    if rating >= 1600:
        return "🟣 Профи"
    if rating >= 1300:
        return "🔵 Опытный"
    return "🟢 Новичок"


def elo_delta(r_a, r_b, k=32):
    ea = 1 / (1 + 10 ** ((r_b - r_a) / 400))
    delta = int(round(k * (1 - ea)))
    return delta


def format_user_info(u):
    rank = get_rank_name(u.get('rating', 1200))
    name = u.get('name') or ''
    username = u.get('username') or ''
    return (
        f"<b>👤 Имя:</b> <i>{name}</i>\n"
        f"<b>🔗 Юзернейм:</b> <i>@{username}</i>\n"
        f"<b>🆔 ID:</b> <code>{u['id']}</code>\n"
        f"<b>📊 Рейтинг:</b> <b>{u.get('rating', 1200)}</b> — <b>{rank}</b>\n"
        f"<b>💰 Коины:</b> <b>{u['coins']}</b>\n"
        f"<b>🏆 Победы:</b> <b>{u.get('wins', 0)}</b>\n"
        f"<b>❌ Поражения:</b> <b>{u.get('losses', 0)}</b>\n"
        f"<b>🤝 Ничьи:</b> <b>{u.get('draws', 0)}</b>"
    )

@dp.inline_handler()
async def inline_handler(query: InlineQuery):
    reg_user(query.from_user)

    q = (query.query or "").strip()
    price = DEFAULT_GAME_PRICE
    if q:
        try:
            p = int(q)
            if p > 0:
                price = p
        except Exception:
            price = DEFAULT_GAME_PRICE

    result = InlineQueryResultArticle(
        id=str(uuid.uuid4()),
        title=f"🎮 Создать игру — {price} коинов",
        description="Классические крестики-нолики — смело приглашайте игроков",
        input_message_content=InputTextMessageContent(
            f"🎮 Создание игры…|{price}"
        ),
    )

    await query.answer([result], cache_time=1)

@dp.message_handler(lambda m: m.text and m.text.startswith("🎮 Создание игры"))
async def create_game(message: types.Message):
    reg_user(message.from_user)

    user = users[message.from_user.id]

    try:
        parts = message.text.split("|")
        price = int(parts[-1]) if len(parts) > 1 else DEFAULT_GAME_PRICE
        if price <= 0:
            price = DEFAULT_GAME_PRICE
    except Exception:
        price = DEFAULT_GAME_PRICE

    if user["coins"] < price:
        # reply instead of editing to be safe in all contexts
        await message.reply("❌ <b>Недостаточно коинов</b>", parse_mode=types.ParseMode.HTML)
        return

    game_id = str(uuid.uuid4())[:8]
    games[game_id] = {
        "type": "inline",
        "x": message.from_user.id,
        "o": None,
        "board": new_board(),
        "turn": "X",
        "started": False,
        "price": price
    }

    text = (
        f"<b>🎮 Игра #{game_id}</b> — <i>Ставка:</i> <b>{price}</b> коинов\n\n"
        f"👑 Игрок: <b>{user.get('name') or user.get('username')}</b>\n"
        f"⏳ <i>Ожидание соперника…</i>"
    )

    # Try editing user's message (works for some inline contexts), otherwise send bot message in chat
    try:
        await message.edit_text(text, reply_markup=kb_join(game_id), parse_mode=types.ParseMode.HTML)
        games[game_id]['type'] = 'inline'
    except Exception:
        m = await bot.send_message(message.chat.id, text, reply_markup=kb_join(game_id), parse_mode=types.ParseMode.HTML)
        games[game_id]['type'] = 'chat'
        games[game_id]['chat_id'] = m.chat.id
        games[game_id]['message_id'] = m.message_id





@dp.callback_query_handler(lambda c: c.data and c.data.startswith("join:"))
async def join_game(call: types.CallbackQuery):
    reg_user(call.from_user)

    game_id = call.data.split(":")[1]
    game = games.get(game_id)

    if not game or game["started"]:
        await call.answer("Игра недоступна", show_alert=True)
        return

    if call.from_user.id == game["x"]:
        await call.answer("Нельзя играть с собой", show_alert=True)
        return

    user = users[call.from_user.id]
    price = game.get('price', DEFAULT_GAME_PRICE)
    if user["coins"] < price:
        await call.answer("Недостаточно коинов", show_alert=True)
        return

    game["o"] = call.from_user.id
    game["started"] = True

    users[game["x"]]["coins"] -= price
    users[game["o"]]["coins"] -= price
    save_user(users[game["x"]])
    save_user(users[game["o"]])

    # Инициализируем время последнего хода и запускаем наблюдатель таймаута
    game['last_move_time'] = time.time()
    game['timer_task'] = asyncio.create_task(move_timer(game_id, call.inline_message_id if game.get('type')=='inline' else None))

    text = (
        f"<b>🎮 Игра #{game_id}</b>\n\n"
        f"❌ X: <b>{users[game['x']].get('name') or users[game['x']]['username']}</b>\n"
        f"⭕ O: <b>{users[game['o']].get('name') or users[game['o']]['username']}</b>\n\n"
        f"<b>Ход:</b> ❌"
    )
    kb = kb_board(game_id)

    # Edit depending on where the game message lives
    if game.get('type') == 'chat' and game.get('chat_id') and game.get('message_id'):
        try:
            await bot.edit_message_text(text, chat_id=game['chat_id'], message_id=game['message_id'], reply_markup=kb, parse_mode=types.ParseMode.HTML)
        except Exception:
            pass
    else:
        try:
            await safe_edit_message_text(inline_message_id=call.inline_message_id, text=text, reply_markup=kb, parse_mode=types.ParseMode.HTML)
        except Exception:
            pass


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("move:"))
async def move(call: types.CallbackQuery):
    reg_user(call.from_user)

    _, game_id, idx = call.data.split(":")
    idx = int(idx)

    game = games.get(game_id)

    if not game or not game["started"]:
        return

    if call.from_user.id not in (game["x"], game["o"]):
        await call.answer("Вы не игрок", show_alert=True)
        return

    symbol = "X" if call.from_user.id == game["x"] else "O"

    if symbol != game["turn"]:
        await call.answer("Не ваш ход", show_alert=True)
        return

    if game["board"][idx] != " ":
        return

    game["board"][idx] = symbol
    # обновляем время последнего хода и сбрасываем таймер
    game["last_move_time"] = time.time()
    cancel_game_timer(game_id)

    result = check_winner(game["board"])

    def _render_result_text_for_end(game_id, result, price, winner_id=None, loser_id=None):
        if result == 'draw':
            return (
                f"<b>🎮 Игра #{game_id}</b>\n\n"
                f"🤝 Ничья\n"
                f"💰 Ставки возвращены: <b>{price}</b> коинов каждому"
            )
        else:
            return (
                f"<b>🎮 Игра #{game_id}</b>\n\n"
                f"🏆 Победил <b>{users[winner_id].get('name') or users[winner_id]['username']}</b>\n"
                f"💰 Выигрыш: <b>{price*2}</b> коинов"
            )

    if result:
        cancel_game_timer(game_id)
        price = game.get('price', DEFAULT_GAME_PRICE)
        if result == "draw":
            users[game['x']]['coins'] += price
            users[game['o']]['coins'] += price
            users[game['x']]['draws'] = users[game['x']].get('draws', 0) + 1
            users[game['o']]['draws'] = users[game['o']].get('draws', 0) + 1
            ra = users[game['x']].get('rating', 1200)
            rb = users[game['o']].get('rating', 1200)
            ea = 1 / (1 + 10 ** ((rb - ra) / 400))
            eb = 1 / (1 + 10 ** ((ra - rb) / 400))
            k = 24
            dra = int(round(k * (0.5 - ea)))
            drb = int(round(k * (0.5 - eb)))
            users[game['x']]['rating'] = users[game['x']].get('rating', 1200) + dra
            users[game['o']]['rating'] = users[game['o']].get('rating', 1200) + drb

            save_user(users[game['x']])
            save_user(users[game['o']])

            text = _render_result_text_for_end(game_id, result, price)
        else:
            winner_id = game["x"] if result == "X" else game["o"]
            loser_id = game['o'] if winner_id == game['x'] else game['x']
            users[winner_id]["coins"] += price * 2
            # обновляем статистику
            users[winner_id]['wins'] = users[winner_id].get('wins', 0) + 1
            users[loser_id]['losses'] = users[loser_id].get('losses', 0) + 1

            # ELO change
            ra = users[winner_id].get('rating', 1200)
            rb = users[loser_id].get('rating', 1200)
            delta = elo_delta(ra, rb, k=32)
            users[winner_id]['rating'] = ra + delta
            users[loser_id]['rating'] = rb - delta

            save_user(users[winner_id])
            save_user(users[loser_id])

            text = (
                f"<b>🎮 Игра #{game_id}</b>\n\n"
                f"🏆 Победил <b>{users[winner_id].get('name') or users[winner_id]['username']}</b> (+{delta} рейтинга)\n"
                f"💰 Выигрыш: <b>{price*2}</b> коинов\n\n"
                f"{users[winner_id].get('name') or users[winner_id]['username']} — {users[winner_id]['rating']} ({get_rank_name(users[winner_id]['rating'])})\n"
                f"{users[loser_id].get('name') or users[loser_id]['username']} — {users[loser_id]['rating']} ({get_rank_name(users[loser_id]['rating'])})"
            )

        # edit where the game message lives
        if game.get('type') == 'chat' and game.get('chat_id') and game.get('message_id'):
            try:
                await safe_edit_message_text(text, chat_id=game['chat_id'], message_id=game['message_id'], parse_mode=types.ParseMode.HTML)
            except Exception:
                pass
        else:
            try:
                await safe_edit_message_text(inline_message_id=call.inline_message_id, text=text, parse_mode=types.ParseMode.HTML)
            except Exception:
                pass

        # удаляем игру и завершаем таймер
        games.pop(game_id, None)
        return

    # продолжаем игру — переключаем ход и запускаем новый таймер
    game["turn"] = "O" if symbol == "X" else "X"
    game['timer_task'] = asyncio.create_task(move_timer(game_id, call.inline_message_id))

    # update board display in the chat where the game message exists
    text = (
        f"<b>🎮 Игра #{game_id}</b>\n\n"
        f"❌ X: <b>{users[game['x']].get('name') or users[game['x']]['username']}</b>\n"
        f"⭕ O: <b>{users[game['o']].get('name') or users[game['o']]['username']}</b>\n\n"
        f"<b>Ход:</b> {'❌' if game['turn']=='X' else '⭕'}"
    )
    kb = kb_board(game_id)
    if game.get('type') == 'chat' and game.get('chat_id') and game.get('message_id'):
        try:
            await bot.edit_message_text(text, chat_id=game['chat_id'], message_id=game['message_id'], reply_markup=kb, parse_mode=types.ParseMode.HTML)
        except Exception:
            pass
    else:
        try:
            await bot.edit_message_text(inline_message_id=call.inline_message_id, text=text, reply_markup=kb_board(game_id), parse_mode=types.ParseMode.HTML)
        except Exception:
            pass

@dp.callback_query_handler(lambda c: c.data and c.data == "show:ranks")
async def show_ranks(call: types.CallbackQuery):
    text = (
        "❝ <b>Рейтинговая система (ELO / Rank)</b> ❞\n\n"
        "🟢 <b>Новичок</b> — начинающий игрок, стартовый рейтинг: <b>1200</b>\n"
        "🔵 <b>Опытный</b> — стабильные игроки, рейтинг от <b>1300</b>\n"
        "🟣 <b>Профи</b> — сильные игроки, рейтинг от <b>1600</b>\n"
        "🔴 <b>Легенда XO</b> — элита, рейтинг от <b>2000</b>\n\n"
        "<b>Победа над сильным — больше очков.</b>\n"
        "<b>Поражение от слабого — минус.</b>\n\n"
        "Цель: долгосрочная мотивация и престиж."
    )
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("◀️ Назад", callback_data="back:start"))
    try:
        await bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=kb, parse_mode=types.ParseMode.HTML)
    except Exception:
        await call.answer()


@dp.callback_query_handler(lambda c: c.data and c.data == "show:profile")
async def show_profile(call: types.CallbackQuery):
    reg_user(call.from_user)
    u = load_user(call.from_user.id)
    if not u:
        await call.answer("Пользователь не найден", show_alert=True)
        return
    name = u.get('name') or ''
    username = u.get('username') or ''

    text = (
        f"<b>👤 Профиль: {name} @{username}</b>\n\n"
        f"{format_user_info(u)}\n"
    )
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("◀️ Назад", callback_data="back:start"))
    try:
        await bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=kb, parse_mode=types.ParseMode.HTML)
    except Exception:
        await call.answer()


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    reg_user(message.from_user)
    user = users[message.from_user.id]

    text = (
        f"<b>🎮 Крестики-Нолики</b>\n\n"
        f"Привет, <b>{user.get('name') or '@'+user['username']}</b>!\n\n"
        f"Создавайте игры прямо здесь — нажмите на кнопку ниже или используйте инлайн, чтобы пригласить игроков в чат."
    )

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("▶️ Создать игру (инлайн)", switch_inline_query=""))
    kb.add(InlineKeyboardButton("👤 Профиль", callback_data="show:profile"))
    kb.add(InlineKeyboardButton("📊 Ранги", callback_data="show:ranks"))
    kb.add(InlineKeyboardButton("🏆 Топ игроков", callback_data="show:top"))
    if message.from_user.id == config.ADMIN_ID:
        kb.add(InlineKeyboardButton("🔧 Админ панель", callback_data="admin:menu"))

    await message.reply(text, reply_markup=kb)



def _compute_winrate(u):
    games = (u.get('wins',0) + u.get('losses',0) + u.get('draws',0))
    if games == 0:
        return 0.0
    return u.get('wins',0) / games


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("show:top"))
async def show_top(call: types.CallbackQuery):
    ids = get_all_user_ids()
    users_list = [load_user(uid) for uid in ids if load_user(uid)]
    if not users_list:
        await call.answer("Нет игроков", show_alert=True)
        return
    sorted_by_wins = sorted(users_list, key=lambda u: u.get('wins',0), reverse=True)
    text = "<b>🏆 Топ игроков (по победам)</b>\n\n"
    for i, u in enumerate(sorted_by_wins[:10], 1):
        display = u.get('name') or ('@' + u.get('username','?'))
        text += f"{i}. {display} — {u.get('wins',0)} побед — {u.get('rating',1200)} ({get_rank_name(u.get('rating',1200))})\n"

    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("По победам", callback_data="top:wins"),
        InlineKeyboardButton("По коинам", callback_data="top:coins"),
        InlineKeyboardButton("По рейтингу", callback_data="top:rating")
    )
    kb.add(InlineKeyboardButton("◀️ Назад", callback_data="back:start"))
    await bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=kb, parse_mode=types.ParseMode.HTML)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("top:"))
async def top_callback(call: types.CallbackQuery):
    _, mode = call.data.split(":", 1)
    ids = get_all_user_ids()
    users_list = [load_user(uid) for uid in ids if load_user(uid)]
    if mode == 'wins':
        users_sorted = sorted(users_list, key=lambda u: u.get('wins',0), reverse=True)
        header = "<b>🏆 Топ по победам</b>"
    elif mode == 'coins':
        users_sorted = sorted(users_list, key=lambda u: u.get('coins',0), reverse=True)
        header = "<b>💰 Топ по коинам</b>"
    elif mode == 'rating':
        users_sorted = sorted(users_list, key=lambda u: u.get('rating',1200), reverse=True)
        header = "<b>🏆 Топ по рейтингу</b>"
    else:
        await call.answer("Неподдерживаемый режим", show_alert=True)
        return

    text = header + "\n\n"
    for i, u in enumerate(users_sorted[:10], 1):
        display = u.get('name') or ('@' + u.get('username','?'))
        text += f"{i}. {display} — {u.get('wins',0)} побед, {u.get('coins',0)} 💰, рейтинг: {u.get('rating',1200)} ({get_rank_name(u.get('rating',1200))})\n"

    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("По победам", callback_data="top:wins"),
        InlineKeyboardButton("По коинам", callback_data="top:coins"),
        InlineKeyboardButton("По рейтингу", callback_data="top:rating")
    )
    kb.add(InlineKeyboardButton("◀️ Назад", callback_data="back:start"))
    await bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=kb, parse_mode=types.ParseMode.HTML)


@dp.callback_query_handler(lambda c: c.data == 'back:start')
async def back_to_start(call: types.CallbackQuery):
    # Восстанавливаем основное меню
    reg_user(call.from_user)
    user = users[call.from_user.id]
    text = (
        f"<b>🎮 Крестики-Нолики</b>\n\n"
        f"Привет, <b>{user.get('name') or '@'+user['username']}</b>!\n\n"
        f"Создавайте игры прямо здесь — нажмите на кнопку ниже или используйте инлайн, чтобы пригласить игроков в чат."
    )

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("▶️ Создать игру (инлайн)", switch_inline_query=""))
    kb.add(InlineKeyboardButton("👤 Профиль", callback_data="show:profile"))
    kb.add(InlineKeyboardButton("📊 Ранги", callback_data="show:ranks"))
    kb.add(InlineKeyboardButton("🏆 Топ игроков", callback_data="show:top"))
    if call.from_user.id == config.ADMIN_ID:
        kb.add(InlineKeyboardButton("🔧 Админ панель", callback_data="admin:menu"))

    try:
        await bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=kb, parse_mode=types.ParseMode.HTML)
    except Exception:
        await call.answer()


@dp.callback_query_handler(lambda c: c.data == 'show:shop')
async def show_shop(call: types.CallbackQuery):
    # show categories
    text = "<b>🛍️ Магазин — трать коины, прокачай стиль!</b>\n\nВыбирай категорию: символы, фоны, эмодзи или анимации. Всё четко, красиво и ахуенно."
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Символы", callback_data="shop:cat:symbol"),
        InlineKeyboardButton("Фоны", callback_data="shop:cat:background"),
        InlineKeyboardButton("Эмодзи", callback_data="shop:cat:emoji_pack"),
        InlineKeyboardButton("Анимации", callback_data="shop:cat:animation")
    )
    kb.add(InlineKeyboardButton("◀️ Назад", callback_data="back:start"))
    try:
        await bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=kb, parse_mode=types.ParseMode.HTML)
    except Exception:
        await call.answer()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('shop:cat:'))
async def shop_category(call: types.CallbackQuery):
    _, _, cat = call.data.split(':', 2)
    items = items_by_category(cat)
    if not items:
        await call.answer("Нет предметов в этой категории", show_alert=True)
        return
    text = f"<b>🛍️ Магазин — {cat.title()}</b>\n\n"
    kb = InlineKeyboardMarkup()
    for it in items:
        text += f"{it['name']} — {it['price']} 💰\n{it.get('desc','')}\n\n"
        kb.add(InlineKeyboardButton(f"Просмотр: {it['name']}", callback_data=f"shop:item:{it['id']}"))
    kb.add(InlineKeyboardButton("◀️ Назад", callback_data="show:shop"))
    try:
        await bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=kb, parse_mode=types.ParseMode.HTML)
    except Exception:
        await call.answer()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('shop:item:'))
async def shop_item(call: types.CallbackQuery):
    _, _, item_id = call.data.split(':', 2)
    it = find_item(item_id)
    if not it:
        await call.answer("Предмет не найден", show_alert=True)
        return
    user = load_user(call.from_user.id)
    owned = owns_item(call.from_user.id, item_id)
    equipped = False
    eq_field = ''
    if it['category'] == 'symbol':
        current = user.get('equipped_symbol','')
        eq_field = 'equipped_symbol'
    elif it['category'] == 'background':
        current = user.get('equipped_bg','')
        eq_field = 'equipped_bg'
    elif it['category'] == 'emoji_pack':
        current = user.get('equipped_emoji_pack','')
        eq_field = 'equipped_emoji_pack'
    elif it['category'] == 'animation':
        current = user.get('equipped_animation','')
        eq_field = 'equipped_animation'
    else:
        current = ''
    if current == item_id:
        equipped = True

    text = f"<b>{it['name']}</b> — {it['price']} 💰\n\n{it.get('desc','')}\n\nПревью: {it.get('preview','')}."
    kb = InlineKeyboardMarkup(row_width=2)
    if not owned:
        kb.add(InlineKeyboardButton(f"Купить — {it['price']} 💰", callback_data=f"shop:buy:{item_id}"))
    else:
        if equipped:
            kb.add(InlineKeyboardButton(f"Снять", callback_data=f"shop:unequip:{item_id}"))
        else:
            kb.add(InlineKeyboardButton(f"Надеть", callback_data=f"shop:equip:{item_id}"))
    kb.add(InlineKeyboardButton("◀️ Назад", callback_data=f"shop:cat:{it['category']}"))
    try:
        await bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=kb, parse_mode=types.ParseMode.HTML)
    except Exception:
        await call.answer()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('shop:buy:'))
async def shop_buy(call: types.CallbackQuery):
    _, _, item_id = call.data.split(':', 2)
    it = find_item(item_id)
    if not it:
        await call.answer("Предмет не найден", show_alert=True)
        return
    u = load_user(call.from_user.id)
    if u['coins'] < it['price']:
        await call.answer("Недостаточно коинов", show_alert=True)
        return
    # charge and grant
    u['coins'] -= it['price']
    save_user(u)
    grant_item(call.from_user.id, item_id)
    await call.answer(f"Куплено: {it['name']} — {it['price']} 💰", show_alert=True)
    # refresh item view
    await shop_item(call)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('shop:equip:'))
async def shop_equip(call: types.CallbackQuery):
    _, _, item_id = call.data.split(':', 2)
    it = find_item(item_id)
    if not it:
        await call.answer("Предмет не найден", show_alert=True)
        return
    if not owns_item(call.from_user.id, item_id):
        await call.answer("Сначала купите предмет", show_alert=True)
        return
    u = load_user(call.from_user.id)
    # set equipped field
    if it['category'] == 'symbol':
        u['equipped_symbol'] = item_id
    elif it['category'] == 'background':
        u['equipped_bg'] = item_id
    elif it['category'] == 'emoji_pack':
        u['equipped_emoji_pack'] = item_id
    elif it['category'] == 'animation':
        u['equipped_animation'] = item_id
    save_user(u)
    await call.answer(f"Экипировано: {it['name']}", show_alert=True)
    await shop_item(call)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('shop:unequip:'))
async def shop_unequip(call: types.CallbackQuery):
    _, _, item_id = call.data.split(':', 2)
    it = find_item(item_id)
    if not it:
        await call.answer("Предмет не найден", show_alert=True)
        return
    u = load_user(call.from_user.id)
    if it['category'] == 'symbol' and u.get('equipped_symbol','') == item_id:
        u['equipped_symbol'] = ''
    elif it['category'] == 'background' and u.get('equipped_bg','') == item_id:
        u['equipped_bg'] = ''
    elif it['category'] == 'emoji_pack' and u.get('equipped_emoji_pack','') == item_id:
        u['equipped_emoji_pack'] = ''
    elif it['category'] == 'animation' and u.get('equipped_animation','') == item_id:
        u['equipped_animation'] = ''
    else:
        await call.answer("Предмет не экипирован", show_alert=True)
        return
    save_user(u)
    await call.answer(f"Снято: {it['name']}", show_alert=True)
    await shop_item(call)
    # Вернуться в главное меню
    await back_to_start(call)


@dp.message_handler(commands=['admin'])
async def cmd_admin(message: types.Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.reply("❌ Доступ запрещен.")
        return
    await show_admin_menu(message)


async def show_admin_menu(source):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🧑‍💼 Управление пользователями", callback_data="admin:users"))
    kb.add(InlineKeyboardButton("✖️ Закрыть", callback_data="admin:close"))

    text = "<b>🔧 Админ панель</b>\nВыберите действие"

    if isinstance(source, types.Message):
        await source.reply(text, reply_markup=kb)
    else:
        await safe_edit_message_text(text, chat_id=source.message.chat.id, message_id=source.message.message_id, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('admin:'))
async def admin_callback(call: types.CallbackQuery):
    if call.from_user.id != config.ADMIN_ID:
        await call.answer("Доступно только админу", show_alert=True)
        return

    parts = call.data.split(":")
    action = parts[1]

    if action == 'menu':
        await show_admin_menu(call)
    elif action == 'close':
        await bot.edit_message_text("<i>Панель закрыта</i>", chat_id=call.message.chat.id, message_id=call.message.message_id)
    elif action == 'users':
        # Список пользователей
        ids = get_all_user_ids()
        kb = InlineKeyboardMarkup(row_width=1)
        if not ids:
            kb.add(InlineKeyboardButton("◀️ Назад", callback_data="admin:menu"))
            await bot.edit_message_text("<b>Пользователей нет</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=kb)
            return
        for uid in ids:
            u = load_user(uid)
            if u:
                label = f"@{u['username']} — {u['coins']} 💰"
                kb.add(InlineKeyboardButton(label, callback_data=f"admin:user:{uid}"))
        kb.add(InlineKeyboardButton("◀️ Назад", callback_data="admin:menu"))
        await bot.edit_message_text("<b>🧾 Список пользователей</b>\nНажмите на пользователя для управления", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=kb)

    elif action == 'user' and len(parts) >= 3:
        uid = int(parts[2])
        u = load_user(uid)
        if not u:
            await call.answer("Пользователь не найден", show_alert=True)
            return
        text = format_user_info(u)
        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton("+100 💸", callback_data=f"admin:modify:{uid}:100"),
            InlineKeyboardButton("+500 💸", callback_data=f"admin:modify:{uid}:500"),
            InlineKeyboardButton("+1000 💸", callback_data=f"admin:modify:{uid}:1000")
        )
        kb.row(
            InlineKeyboardButton("-100 ⚠️", callback_data=f"admin:modify:{uid}:-100"),
            InlineKeyboardButton("-500 ⚠️", callback_data=f"admin:modify:{uid}:-500"),
            InlineKeyboardButton("-1000 ⚠️", callback_data=f"admin:modify:{uid}:-1000")
        )
        kb.row(
            InlineKeyboardButton("✍️ Ввести сумму", callback_data=f"admin:input:{uid}"),
            InlineKeyboardButton("◀️ Назад", callback_data="admin:users")
        )
        await bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=kb)

    elif action == 'input' and len(parts) >= 3:
        uid = int(parts[2])
        admin_pending[call.from_user.id] = uid
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("❌ Отмена", callback_data=f"admin:cancel_input:{uid}"))
        await bot.edit_message_text(
            f"<b>Ввод суммы</b>\nОтправьте сообщение с целым числом (например: 500 или -200) — это будет добавлено к балансу пользователя @{load_user(uid)['username']}.\nДля отмены нажмите кнопку ❌ Отмена или отправьте 'отмена'.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=kb
        )

    elif action == 'cancel_input' and len(parts) >= 3:
        uid = int(parts[2])
        admin_pending.pop(call.from_user.id, None)
        await bot.edit_message_text(f"<i>Ввод суммы отменён</i>", chat_id=call.message.chat.id, message_id=call.message.message_id)

    elif action == 'modify' and len(parts) >= 4:
        uid = int(parts[2])
        amt = int(parts[3])
        u = load_user(uid)
        if not u:
            await call.answer("Пользователь не найден", show_alert=True)
            return
        u['coins'] += amt
        if u['coins'] < 0:
            u['coins'] = 0
        save_user(u)
        text = format_user_info(u)
        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton("+100 💸", callback_data=f"admin:modify:{uid}:100"),
            InlineKeyboardButton("+500 💸", callback_data=f"admin:modify:{uid}:500"),
            InlineKeyboardButton("+1000 💸", callback_data=f"admin:modify:{uid}:1000")
        )
        kb.row(
            InlineKeyboardButton("-100 ⚠️", callback_data=f"admin:modify:{uid}:-100"),
            InlineKeyboardButton("-500 ⚠️", callback_data=f"admin:modify:{uid}:-500"),
            InlineKeyboardButton("-1000 ⚠️", callback_data=f"admin:modify:{uid}:-1000")
        )
        kb.add(InlineKeyboardButton("◀️ Назад", callback_data="admin:users"))
        await bot.edit_message_text(f"✅ Изменено на <b>{amt}</b> коинов.\n\n" + text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=kb)

from aiogram.utils.exceptions import MessageNotModified
async def safe_edit_message_text(*args, **kwargs):
    try:
        return await bot.edit_message_text(*args, **kwargs)
    except MessageNotModified:
        return None
    except Exception:
        return None

@dp.message_handler(lambda m: m.text and m.from_user.id == config.ADMIN_ID)
async def admin_amount_input(message: types.Message):
    if message.from_user.id not in admin_pending:
        return
    text = message.text.strip()
    if text.lower() in ("отмена", "cancel"):
        uid = admin_pending.pop(message.from_user.id)
        await message.reply("❌ Ввод суммы отменён.")
        u = load_user(uid)
        if u:
            kb = InlineKeyboardMarkup()
            kb.row(
                InlineKeyboardButton("+100 💸", callback_data=f"admin:modify:{uid}:100"),
                InlineKeyboardButton("+500 💸", callback_data=f"admin:modify:{uid}:500"),
                InlineKeyboardButton("+1000 💸", callback_data=f"admin:modify:{uid}:1000")
            )
            kb.row(
                InlineKeyboardButton("-100 ⚠️", callback_data=f"admin:modify:{uid}:-100"),
                InlineKeyboardButton("-500 ⚠️", callback_data=f"admin:modify:{uid}:-500"),
                InlineKeyboardButton("-1000 ⚠️", callback_data=f"admin:modify:{uid}:-1000")
            )
            kb.row(
                InlineKeyboardButton("✍️ Ввести сумму", callback_data=f"admin:input:{uid}"),
                InlineKeyboardButton("◀️ Назад", callback_data="admin:users")
            )
            await message.reply(format_user_info(u), reply_markup=kb, parse_mode=types.ParseMode.HTML)
        return
    try:
        amt = int(text)
    except ValueError:
        await message.reply("❌ Неверный формат. Введите целое число, например 500 или -200.")
        return
    uid = admin_pending.pop(message.from_user.id)
    u = load_user(uid)
    if not u:
        await message.reply("Пользователь не найден")
        return
    u['coins'] += amt
    if u['coins'] < 0:
        u['coins'] = 0
    save_user(u)
    await message.reply(f"✅ Изменено на <b>{amt}</b> коинов.\n\n" + format_user_info(u), parse_mode=types.ParseMode.HTML)

if __name__ == "__main__":
    executor.start_polling(dp)
