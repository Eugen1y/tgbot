import asyncio
import sqlite3
import datetime
from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import Command
from credentials import API_TOKEN

# Создаём экземпляр бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)  # Добавляем router в диспетчер

# Подключение к базе данных и создание таблицы для расписания
conn = sqlite3.connect("schedule.db")
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS schedule (
        user_id INTEGER,
        date DATE,
        schedule TEXT,
        UNIQUE(user_id, date)
    )
""")
conn.commit()


# Обработчики команд
@router.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.answer("Привет! Я помогу тебе с расписанием.\n\n"
                         "Команды:\n"
                         "/setschedule <день> <расписание> - Установить расписание на день\n"
                         "/viewschedule - Показать расписание на неделю\n"
                         "/today - Показать расписание на сегодня\n"
                         "/tomorrow - Показать расписание на завтра")


# Функция добавления расписания и другие обработчики
@router.message(Command("setschedule"))
async def set_schedule(message: types.Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Использование: /setschedule <день> <расписание>")
        return

    date = args[1].capitalize()
    schedule_text = args[2]
    user_id = message.from_user.id

    cursor.execute("""
        INSERT OR REPLACE INTO schedule (user_id, date, schedule)
        VALUES (?, ?, ?)
    """, (user_id, date, schedule_text))
    conn.commit()

    await message.answer(f"Расписание на {date} установлено: {schedule_text}")


# Функция добавления расписания на несколько дней
@router.message(Command("setschedule_multiple"))
async def set_schedule_multiple(message: types.Message):
    args = message.text.split()
    if len(args) < 3:
        await message.answer("Использование: /setschedule_multiple <дата1> <расписание><дата2><расписание> ...")
        return

    dates = args[1::2]  # Последний аргумент — это расписание
    schedules = list(filter(lambda item: item not in dates, args[1:])) # Остальные аргументы — это даты

    user_id = message.from_user.id

    for idx,date in enumerate(dates):
        try:
            date = datetime.datetime.strptime(date, "%d-%m-%Y").date()  # Преобразуем строку в дату
            cursor.execute("""
                INSERT OR REPLACE INTO schedule (user_id, date, schedule)
                VALUES (?, ?, ?)
            """, (user_id, date, schedules[idx]))
        except ValueError:
            await message.answer(f"Неверный формат даты: {date}. Используйте формат: ДД-ММ-ГГГГ")
            return

    conn.commit()
    dates = [date+'\n' for date in dates]
    await message.answer(f"Расписание на указанные дни установлено:\n{''.join(date for date in dates)}")


@router.message(Command("update_schedule"))
async def update_schedule(message: types.Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Использование: /update_schedule <дата в формате ДД-ММ-ГГГГ> <новое расписание>")
        return

    try:
        date = datetime.datetime.strptime(args[1], "%Y-%m-%d").date()  # Преобразуем строку в дату
    except ValueError:
        await message.answer("Неверный формат даты. Используйте формат: ДД-ММ-ГГГГ")
        return

    new_schedule_text = args[2]
    user_id = message.from_user.id

    cursor.execute("""
        UPDATE schedule SET schedule = ? WHERE user_id = ? AND date = ?
    """, (new_schedule_text, user_id, date))

    if cursor.rowcount == 0:
        await message.answer(f"Расписание на {date} не найдено.")
    else:
        conn.commit()
        await message.answer(f"Расписание на {date} обновлено: {new_schedule_text}")


@router.message(Command("viewschedule"))
async def view_schedule(message: types.Message):
    user_id = message.from_user.id
    cursor.execute("SELECT date, schedule FROM schedule WHERE user_id=?", (user_id,))
    week_schedule = cursor.fetchall()

    if not week_schedule:
        await message.answer("Расписание не установлено.")
        return

    schedule_text = "\n".join([f"{day}: {schedule}" for day, schedule in week_schedule])
    await message.answer(f"Ваше расписание на неделю:\n{schedule_text}")


@router.message(Command("today"))
async def today_schedule(message: types.Message):
    day = datetime.datetime.now().strftime("%A")
    await send_schedule(message, day)


@router.message(Command("tomorrow"))
async def tomorrow_schedule(message: types.Message):
    tomorrow = datetime.datetime.now() + datetime.timedelta(days=1)
    day = tomorrow.strftime("%A")
    await send_schedule(message, day)


async def send_schedule(message, date):
    user_id = message.from_user.id
    cursor.execute("SELECT schedule FROM schedule WHERE user_id=? AND date=?", (user_id, date))
    result = cursor.fetchone()

    if result:
        await message.answer(f"Расписание на {date}: {result[0]}")
    else:
        await message.answer(f"Расписание на {date} не установлено.")


# Фоновая задача для ежедневных уведомлений
async def send_daily_schedule():
    while True:
        now = datetime.datetime.now()
        if now.hour == 20 and now.minute == 0:
            tomorrow = (now + datetime.timedelta(days=1)).strftime("%A")

            cursor.execute("SELECT user_id, schedule FROM schedule WHERE date=?", (tomorrow,))
            schedules = cursor.fetchall()

            for user_id, schedule in schedules:
                try:
                    await bot.send_message(chat_id=user_id, text=f"Напоминание на завтра:\n{schedule}")
                except Exception as e:
                    print(f"Ошибка при отправке сообщения пользователю {user_id}: {e}")

            await asyncio.sleep(60)  # Ожидание, чтобы избежать повторного срабатывания
        await asyncio.sleep(10)


# Запуск бота и фоновой задачи
async def main():
    # Убедимся, что обновления очищены перед началом
    await bot.delete_webhook(drop_pending_updates=True)

    # Запуск фоновой задачи для отправки расписания каждый вечер
    asyncio.create_task(send_daily_schedule())

    # Запуск диспетчера
    await dp.start_polling(bot)


if __name__ == "__main__":
    print('started')
    asyncio.run(main())
