import asyncio
import html
import logging
import math
from urllib.parse import quote_plus

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from tmdb import TMDB

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
router = Router()
tmdb = TMDB(config.TMDB_API_KEY)

RESULTS = 5
CATEGORY_LABELS = {
    "movie": "🎬 фильм",
    "tv": "📺 сериал",
    "person": "🧑 актёра/режиссёра",
}


class AllowedFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id in config.ALLOWED_USERS


class AllowedCBFilter(BaseFilter):
    async def __call__(self, cb: CallbackQuery) -> bool:
        return cb.from_user.id in config.ALLOWED_USERS


class SearchState(StatesGroup):
    query = State()


def esc(text: str) -> str:
    return html.escape(text)


def menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎬 Фильмы", callback_data="cat:movie")
    b.button(text="📺 Сериалы", callback_data="cat:tv")
    b.button(text="🧑 Актёры и режиссёры", callback_data="cat:person")
    b.adjust(2, 1)
    return b.as_markup()


def item_label(item: dict, media_type: str) -> str:
    name = tmdb.name(item, media_type)
    year = tmdb.year(item, media_type)
    rating = item.get("vote_average") or 0
    label = name
    if year:
        label += f" ({year})"
    if media_type != "person" and rating:
        label += f" ⭐{rating:.1f}"
    return label[:60]


def card_kb(title: str, media_type: str, item_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="▶️ RuTube", url=f"https://rutube.ru/search/?query={quote_plus(title)}")
    b.button(text="▶️ YouTube", url=f"https://www.youtube.com/results?search_query={quote_plus(title)}")
    b.button(text="🎬 Трейлер", url=f"https://www.youtube.com/results?search_query={quote_plus(title + ' трейлер')}")
    b.button(text="🧑 Актёры", callback_data=f"actors:{media_type}:{item_id}")
    b.button(text="🎥 Режиссёр", callback_data=f"director:{media_type}:{item_id}")
    b.button(text="🔀 Похожие", callback_data=f"similar:{media_type}:{item_id}")
    b.button(text="❌ Отмена", callback_data="cancel:card")
    b.adjust(2, 1, 2, 1, 1)
    return b.as_markup()


def person_kb(person_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎬 Фильмография", callback_data=f"credits:{person_id}")
    b.button(text="❌ Отмена", callback_data="cancel:card")
    b.adjust(1)
    return b.as_markup()


def media_caption(d: dict, media_type: str) -> str:
    title = d.get("title") or d.get("name") or "?"
    year = (d.get("release_date") or d.get("first_air_date") or "")[:4]
    rating = d.get("vote_average") or 0
    genres = ", ".join(g["name"] for g in d.get("genres", []))

    caption = f"🎬 <b>{esc(title)}</b>"
    if year:
        caption += f" ({year})"
    lines = []
    if rating:
        lines.append(f"⭐ Рейтинг: {rating:.1f}")
    if genres:
        lines.append(f"🎭 Жанры: {esc(genres)}")
    if media_type == "movie" and d.get("runtime"):
        lines.append(f"⏱ {d['runtime']} мин")
    if media_type == "tv" and d.get("number_of_seasons"):
        lines.append(f"📺 {d['number_of_seasons']} сез.")
    if lines:
        caption += "\n" + "\n".join(lines)

    overview = (d.get("overview") or "").strip()
    if overview:
        if len(overview) > 700:
            overview = overview[:700].rsplit(" ", 1)[0] + "…"
        caption += "\n\n" + esc(overview)
    return caption


def person_caption(d: dict) -> str:
    name = d.get("name") or "?"
    dept = d.get("known_for_department") or ""
    popularity = d.get("popularity") or 0

    caption = f"🧑 <b>{esc(name)}</b>"
    extra = []
    if dept:
        extra.append(dept)
    if popularity:
        extra.append(f"⭐ {popularity:.0f}")
    if extra:
        caption += "\n" + " · ".join(extra)

    bio = (d.get("biography") or "").strip()
    if bio:
        if len(bio) > 350:
            bio = bio[:350].rsplit(" ", 1)[0] + "…"
        caption += "\n\n" + esc(bio)
    return caption


async def safe_delete(message: Message):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


@router.message(CommandStart(), AllowedFilter())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🔍 Что ищем? Выбери категорию:", reply_markup=menu_kb())


@router.message(Command("cancel"), AllowedFilter())
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=menu_kb())


@router.callback_query(F.data.startswith("cat:"), AllowedCBFilter())
async def choose_category(cb: CallbackQuery, state: FSMContext):
    media_type = cb.data.split(":", 1)[1]
    await state.set_state(SearchState.query)
    await state.set_data({"media_type": media_type, "prompt_msg_id": cb.message.message_id})
    try:
        await cb.message.edit_text(
            f"Введи название {CATEGORY_LABELS[media_type]}:", reply_markup=None
        )
    except TelegramBadRequest:
        pass
    await cb.answer()


@router.message(SearchState.query, AllowedFilter(), F.text)
async def on_query(message: Message, state: FSMContext):
    data = await state.get_data()
    query = message.text.strip()
    if len(query) < 2:
        await message.answer("Запрос слишком короткий.")
        return
    media_type = data["media_type"]
    result = await tmdb.search(media_type, query)
    items = result.get("results", [])
    if data.get("prompt_msg_id"):
        try:
            await bot.delete_message(message.chat.id, data["prompt_msg_id"])
        except TelegramBadRequest:
            pass

    if not items:
        await message.answer("😕 Ничего не найдено. Попробуй другое название.")
        return

    b = InlineKeyboardBuilder()
    for item in items[:RESULTS]:
        b.button(text=item_label(item, media_type), callback_data=f"item:{media_type}:{item['id']}")
    b.button(text="⬅️ Назад", callback_data="back:menu")
    b.adjust(1)
    await message.answer(f"Найдено {len(items)}:", reply_markup=b.as_markup())


@router.callback_query(F.data == "back:menu", AllowedCBFilter())
async def back_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("🔍 Что ищем? Выбери категорию:", reply_markup=menu_kb())
    await cb.answer()


@router.callback_query(F.data.startswith("item:"), AllowedCBFilter())
async def show_item(cb: CallbackQuery):
    _, media_type, item_id = cb.data.split(":")
    details = await tmdb.details(media_type, int(item_id))
    if media_type == "person":
        await show_person(cb, details)
    else:
        await show_media(cb, details, media_type)


async def show_media(cb: CallbackQuery, d: dict, media_type: str):
    title = d.get("title") or d.get("name") or "?"
    caption = media_caption(d, media_type)

    poster = await tmdb.fetch_image(d.get("poster_path"))
    kb = card_kb(title, media_type, d["id"])
    if poster:
        try:
            await cb.message.answer_photo(BufferedInputFile(poster, filename="poster.jpg"), caption=caption, reply_markup=kb)
        except TelegramBadRequest:
            await cb.message.answer(caption, reply_markup=kb)
    else:
        await cb.message.answer(caption, reply_markup=kb)
    await safe_delete(cb.message)
    await cb.answer()


async def show_person(cb: CallbackQuery, d: dict):
    name = d.get("name") or "?"
    caption = person_caption(d)

    photo = await tmdb.fetch_image(d.get("profile_path"))
    kb = person_kb(d["id"])
    if photo:
        try:
            await cb.message.answer_photo(BufferedInputFile(photo, filename="photo.jpg"), caption=caption, reply_markup=kb)
        except TelegramBadRequest:
            await cb.message.answer(caption, reply_markup=kb)
    else:
        await cb.message.answer(caption, reply_markup=kb)
    await safe_delete(cb.message)
    await cb.answer()


CREDITS_PER_PAGE = 6


def credits_items(data: dict) -> list[dict]:
    merged = {}
    for item in data.get("cast", []) or []:
        merged[item["id"]] = item
    for item in data.get("crew", []) or []:
        merged.setdefault(item["id"], item)
    items = [v for v in merged.values() if v.get("media_type") in ("movie", "tv")]
    items.sort(key=lambda x: x.get("release_date") or x.get("first_air_date") or "", reverse=True)
    return items


async def render_credits(cb: CallbackQuery, person_id: int, page: int):
    data = await tmdb.person_credits(person_id)
    items = credits_items(data)
    if not items:
        await cb.answer("Фильмография не найдена", show_alert=True)
        return

    total = len(items)
    pages = max(1, (total + CREDITS_PER_PAGE - 1) // CREDITS_PER_PAGE)
    page = min(max(1, page), pages)
    chunk = items[(page - 1) * CREDITS_PER_PAGE: page * CREDITS_PER_PAGE]

    rows = [
        [InlineKeyboardButton(text=item_label(item, item["media_type"]), callback_data=f"item:{item['media_type']}:{item['id']}")]
        for item in chunk
    ]
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"crednav:{person_id}:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{pages}", callback_data="noop"))
    if page < pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"crednav:{person_id}:{page + 1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"person:{person_id}")])

    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    header = f"🎬 Фильмография — {total} (стр. {page}/{pages}):"
    try:
        await cb.message.edit_text(header, reply_markup=kb)
    except TelegramBadRequest:
        await cb.message.answer(header, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("credits:"), AllowedCBFilter())
async def show_credits(cb: CallbackQuery):
    person_id = int(cb.data.split(":", 1)[1])
    await render_credits(cb, person_id, 1)


@router.callback_query(F.data.startswith("crednav:"), AllowedCBFilter())
async def credits_page(cb: CallbackQuery):
    _, person_id, page = cb.data.split(":")
    await render_credits(cb, int(person_id), int(page))


@router.callback_query(F.data == "noop", AllowedCBFilter())
async def noop(cb: CallbackQuery):
    await cb.answer()


ACTORS_PER_PAGE = 8
SIMILAR_PER_PAGE = 6
SIMILAR_MAX = 30
MIN_VOTES = 20


def quality(item: dict) -> float:
    votes = item.get("vote_count") or 0
    rating = item.get("vote_average") or 0
    if votes < MIN_VOTES or rating <= 0:
        return 0.0
    return rating * math.log10(votes + 1)


async def similar_items(media_type: str, item_id: int) -> list[dict]:
    data = await tmdb.similar(media_type, item_id)
    merged = {it["id"]: it for it in data.get("results", []) or [] if quality(it) > 0}
    if len(merged) < 3:
        rec = await tmdb.recommendations(media_type, item_id)
        for it in rec.get("results", []) or []:
            if quality(it) > 0:
                merged.setdefault(it["id"], it)
    items = sorted(merged.values(), key=quality, reverse=True)
    return items[:SIMILAR_MAX]


def person_label(item: dict) -> str:
    name = item.get("name") or "?"
    role = item.get("character") or ""
    label = name
    if role:
        label += f" — {role}"
    return label[:60]


async def render_actors(cb: CallbackQuery, media_type: str, item_id: int, page: int):
    data = await tmdb.credits(media_type, item_id)
    cast = data.get("cast", []) or []
    if not cast:
        await cb.answer("Актёры не указаны", show_alert=True)
        return

    total = len(cast)
    pages = max(1, (total + ACTORS_PER_PAGE - 1) // ACTORS_PER_PAGE)
    page = min(max(1, page), pages)
    chunk = cast[(page - 1) * ACTORS_PER_PAGE: page * ACTORS_PER_PAGE]

    rows = [
        [InlineKeyboardButton(text=person_label(a), callback_data=f"item:person:{a['id']}")]
        for a in chunk
    ]
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"actpg:{media_type}:{item_id}:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{pages}", callback_data="noop"))
    if page < pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"actpg:{media_type}:{item_id}:{page + 1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"item:{media_type}:{item_id}")])

    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    header = f"🧑 Актёры — {total} (стр. {page}/{pages}):"
    try:
        await cb.message.edit_text(header, reply_markup=kb)
    except TelegramBadRequest:
        await cb.message.answer(header, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("actors:"), AllowedCBFilter())
async def show_actors(cb: CallbackQuery):
    _, media_type, item_id = cb.data.split(":")
    await render_actors(cb, media_type, int(item_id), 1)


@router.callback_query(F.data.startswith("actpg:"), AllowedCBFilter())
async def actors_page(cb: CallbackQuery):
    _, media_type, item_id, page = cb.data.split(":")
    await render_actors(cb, media_type, int(item_id), int(page))


@router.callback_query(F.data.startswith("director:"), AllowedCBFilter())
async def show_director(cb: CallbackQuery):
    _, media_type, item_id = cb.data.split(":")
    data = await tmdb.credits(media_type, int(item_id))
    directors = [c for c in data.get("crew", []) or [] if c.get("job") == "Director"]
    if not directors:
        await cb.answer("Режиссёр не указан", show_alert=True)
        return
    details = await tmdb.details("person", directors[0]["id"])
    await show_person(cb, details)


async def render_similar(cb: CallbackQuery, media_type: str, item_id: int, page: int):
    items = await similar_items(media_type, item_id)
    if not items:
        await cb.answer("Похожих пока нет", show_alert=True)
        return

    total = len(items)
    pages = max(1, (total + SIMILAR_PER_PAGE - 1) // SIMILAR_PER_PAGE)
    page = min(max(1, page), pages)
    chunk = items[(page - 1) * SIMILAR_PER_PAGE: page * SIMILAR_PER_PAGE]

    rows = [
        [InlineKeyboardButton(text=item_label(item, media_type), callback_data=f"item:{media_type}:{item['id']}")]
        for item in chunk
    ]
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"simpg:{media_type}:{item_id}:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{pages}", callback_data="noop"))
    if page < pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"simpg:{media_type}:{item_id}:{page + 1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"item:{media_type}:{item_id}")])

    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    header = f"🔀 Похожие — {total} (стр. {page}/{pages}):"
    try:
        await cb.message.edit_text(header, reply_markup=kb)
    except TelegramBadRequest:
        await cb.message.answer(header, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("similar:"), AllowedCBFilter())
async def show_similar(cb: CallbackQuery):
    _, media_type, item_id = cb.data.split(":")
    await render_similar(cb, media_type, int(item_id), 1)


@router.callback_query(F.data.startswith("simpg:"), AllowedCBFilter())
async def similar_page(cb: CallbackQuery):
    _, media_type, item_id, page = cb.data.split(":")
    await render_similar(cb, media_type, int(item_id), int(page))


@router.callback_query(F.data.startswith("person:"), AllowedCBFilter())
async def back_to_person(cb: CallbackQuery):
    person_id = int(cb.data.split(":", 1)[1])
    details = await tmdb.details("person", person_id)
    await show_person(cb, details)


@router.callback_query(F.data == "cancel:card", AllowedCBFilter())
async def cancel_card(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_delete(cb.message)
    await cb.message.answer("🔍 Что ищем? Выбери категорию:", reply_markup=menu_kb())
    await cb.answer()


@router.message(F.from_user.id.not_in(list(config.ALLOWED_USERS)))
async def denied(message: Message):
    await message.answer("⛔ Доступ ограничен.")


@router.callback_query(F.from_user.id.not_in(list(config.ALLOWED_USERS)))
async def denied_cb(cb: CallbackQuery):
    await cb.answer("⛔ Доступ ограничен", show_alert=True)


async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await tmdb.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
