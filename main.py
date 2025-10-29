import os
import logging
import pickle
import hashlib
from io import BytesIO
from PIL import Image
import numpy as np
import asyncio
import shutil
import face_recognition

from telegram import (
    Update,
    InputMediaPhoto,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# ---------------- Logging ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- Constants ----------------
AWAITING_NAME, COLLECTING_PHOTOS, AWAITING_DELETE_CHOICE = range(3)
MIN_PHOTOS = 3
DATA_DIR = "/config/known_faces"
TELEGRAM_BOT_API_TOKEN = os.getenv("TELEGRAM_BOT_API_TOKEN")

user_sessions = {}

# ---------------- Utility Functions ----------------
def get_user_folder(user_id: int):
    return os.path.join(DATA_DIR, str(user_id))

def get_name_folder(user_id: int, name: str):
    return os.path.join(get_user_folder(user_id), name)

def save_encodings(encodings, path):
    with open(path, "wb") as f:
        pickle.dump(encodings, f)

def load_encodings(path):
    if os.path.exists(path):
        with open(path, "rb") as f:
            return pickle.load(f)
    return []

def pil_to_rgb_uint8_np(pil_img):
    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")
    np_img = np.asarray(pil_img)
    return np_img[:, :, :3].astype(np.uint8)

def save_image(user_id: int, name: str, img_data: BytesIO, idx: int):
    name_folder = get_name_folder(user_id, name)
    os.makedirs(name_folder, exist_ok=True)
    file_path = os.path.join(name_folder, f"{idx}.jpg")
    img_data.seek(0)
    img = Image.open(img_data).convert("RGB")
    img.save(file_path, format="JPEG")
    return file_path

def hash_bytesio(bio):
    bio.seek(0)
    return hashlib.sha256(bio.read()).hexdigest()

# ---------------- Bot Handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! You can:\n"
        "• Use /add to teach me a person's face\n"
        "• Use /list to see known faces\n"
        "• Use /delete to remove a trained face\n\n"
        "Or simply send me photos — after 5s of inactivity, "
        "I'll try to find known faces in them."
    )

# ---------- ADD ----------
async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_sessions[user_id] = {"state": AWAITING_NAME, "name": None, "photos": []}
    await update.message.reply_text("Please send the name of the person to add.")
    return AWAITING_NAME

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Name cannot be empty.")
        return AWAITING_NAME
    user_sessions[user_id]["name"] = text
    user_sessions[user_id]["state"] = COLLECTING_PHOTOS
    await update.message.reply_text(
        f"Got it! Send at least {MIN_PHOTOS} pictures of {text}. Type 'done' when finished."
    )
    return COLLECTING_PHOTOS

async def receive_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    session = user_sessions.get(user_id)

    if not session or session["state"] != COLLECTING_PHOTOS:
        await update.message.reply_text("You need to start with /add first.")
        return ConversationHandler.END

    if update.message.text and update.message.text.lower() == "done":
        count = len(session["photos"])
        if count < MIN_PHOTOS:
            await update.message.reply_text(
                f"You've sent only {count}. Need {MIN_PHOTOS - count} more."
            )
            return COLLECTING_PHOTOS

        folder = get_name_folder(user_id, session["name"])
        os.makedirs(folder, exist_ok=True)
        encodings = []
        image_paths = []

        for idx, img_data in enumerate(session["photos"], start=1):
            file_path = save_image(user_id, session["name"], img_data, idx)
            image_paths.append(file_path)
            try:
                np_img = pil_to_rgb_uint8_np(Image.open(file_path))
                faces = face_recognition.face_encodings(np_img)
            except Exception as e:
                logger.error(f"Error in {file_path}: {e}")
                continue
            if faces:
                encodings.append(faces[0])

        if not encodings:
            await update.message.reply_text("No faces detected. Please try again.")
            return ConversationHandler.END

        save_encodings(encodings, os.path.join(folder, "encodings.pkl"))

        # 🧹 Delete training images after encodings saved
        for img_path in image_paths:
            try:
                os.remove(img_path)
            except Exception as e:
                logger.warning(f"Failed to delete {img_path}: {e}")

        await update.message.reply_text(f"{len(encodings)} faces saved for '{session['name']}'!")
        user_sessions.pop(user_id, None)
        return ConversationHandler.END

    if update.message.photo:
        largest_photo = update.message.photo[-1]
        photo_file = await largest_photo.get_file()
        bio = BytesIO()
        await photo_file.download_to_memory(out=bio)
        session["photos"].append(bio)
        await update.message.reply_text(
            f"Photo received ({len(session['photos'])}). Send more or type 'done'."
        )
        return COLLECTING_PHOTOS

    await update.message.reply_text("Please send a photo or type 'done'.")
    return COLLECTING_PHOTOS

# ---------- AUTO FIND ----------
async def queue_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    session = user_sessions.setdefault(user_id, {"find_photos": [], "hashes": set(), "timer": None})

    largest_photo = update.message.photo[-1]
    photo_file = await largest_photo.get_file()
    bio = BytesIO()
    await photo_file.download_to_memory(out=bio)

    photo_hash = hash_bytesio(bio)
    if photo_hash in session["hashes"]:
        return
    session["hashes"].add(photo_hash)
    session["find_photos"].append(bio)
    await update.message.reply_text(f"Photo queued ({len(session['find_photos'])}).")

    if session.get("timer"):
        session["timer"].cancel()

    async def process_after_idle():
        await asyncio.sleep(5)
        await process_find_batch(update, context, user_id)

    session["timer"] = asyncio.create_task(process_after_idle())

async def process_find_batch(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    session = user_sessions.get(user_id)
    if not session or not session.get("find_photos"):
        return

    photos = session["find_photos"]
    user_folder = get_user_folder(user_id)
    if not os.path.exists(user_folder):
        await update.message.reply_text("No trained faces yet. Use /add first.")
        user_sessions.pop(user_id, None)
        return

    known_faces, known_names = [], []
    for name in os.listdir(user_folder):
        folder_path = os.path.join(user_folder, name)
        enc_file = os.path.join(folder_path, "encodings.pkl")
        if os.path.exists(enc_file):
            encs = load_encodings(enc_file)
            known_faces.extend(encs)
            known_names.extend([name] * len(encs))

    if not known_faces:
        await update.message.reply_text("No known faces found. Use /add first.")
        user_sessions.pop(user_id, None)
        return

    matching_media = []
    used_hashes = set()
    matched_names = set()

    for bio in photos:
        bio.seek(0)
        try:
            img = Image.open(bio).convert("RGB")
            np_img = pil_to_rgb_uint8_np(img)
            faces = face_recognition.face_encodings(np_img)
        except Exception as e:
            logger.error(f"Error reading photo: {e}")
            continue

        if not faces:
            continue

        match_found = False
        for f in faces:
            results = face_recognition.compare_faces(known_faces, f, tolerance=0.5)
            if any(results):
                match_found = True
                name = known_names[results.index(True)]
                matched_names.add(name)
                break

        if match_found:
            photo_hash = hash_bytesio(bio)
            if photo_hash not in used_hashes:
                used_hashes.add(photo_hash)
                matching_media.append(InputMediaPhoto(BytesIO(bio.getvalue())))

    if matching_media:
        await update.message.reply_text(f"Matched faces: {', '.join(matched_names)}")
        await update.message.reply_media_group(media=matching_media)
    else:
        await update.message.reply_text("No matching faces found.")

    user_sessions.pop(user_id, None)

# ---------- LIST ----------
async def list_faces(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_folder = get_user_folder(user_id)
    if not os.path.exists(user_folder):
        await update.message.reply_text("You have no trained faces yet.")
        return

    names = [n for n in os.listdir(user_folder) if os.path.isdir(os.path.join(user_folder, n))]
    if not names:
        await update.message.reply_text("No known faces found.")
    else:
        await update.message.reply_text("🧠 Known faces:\n" + "\n".join(f"• {n}" for n in names))

# ---------- DELETE ----------
async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_folder = get_user_folder(user_id)
    if not os.path.exists(user_folder):
        await update.message.reply_text("You have no trained faces yet.")
        return ConversationHandler.END

    names = [n for n in os.listdir(user_folder) if os.path.isdir(os.path.join(user_folder, n))]
    if not names:
        await update.message.reply_text("No known faces to delete.")
        return ConversationHandler.END

    # Send reply keyboard with names as rows
    keyboard = [[name] for name in names]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Select a face to delete:", reply_markup=reply_markup)

    # Save state for delete selection
    user_sessions[user_id] = {"state": AWAITING_DELETE_CHOICE}
    return AWAITING_DELETE_CHOICE

async def handle_delete_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    name = update.message.text.strip()
    user_folder = get_user_folder(user_id)
    folder = get_name_folder(user_id, name)

    # Only allow delete if keyboard is active
    session = user_sessions.get(user_id)
    if not session or session.get("state") != AWAITING_DELETE_CHOICE:
        await update.message.reply_text("Please use /delete first.")
        return ConversationHandler.END

    if not os.path.exists(folder):
        await update.message.reply_text(f"'{name}' does not exist.")
        user_sessions.pop(user_id, None)
        return ConversationHandler.END

    try:
        shutil.rmtree(folder)
        await update.message.reply_text(f"✅ '{name}' deleted successfully.")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to delete '{name}': {e}")

    user_sessions.pop(user_id, None)
    return ConversationHandler.END

# ---------- CANCEL ----------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in user_sessions:
        session = user_sessions.pop(user_id)
        if session.get("timer"):
            session["timer"].cancel()
    await update.message.reply_text("Operation cancelled.", reply_markup=None)
    return ConversationHandler.END

# ---------- MAIN ----------
def main():
    application = ApplicationBuilder().token(TELEGRAM_BOT_API_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_command)],
        states={
            AWAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)],
            COLLECTING_PHOTOS: [MessageHandler((filters.PHOTO | filters.TEXT) & ~filters.COMMAND, receive_photos)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    delete_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("delete", delete_command)],
        states={
            AWAITING_DELETE_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delete_choice)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", list_faces))
    application.add_handler(conv_handler)
    application.add_handler(delete_conv_handler)
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, queue_photo))

    application.run_polling()

if __name__ == "__main__":
    main()
