from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
from PIL import Image
import img2pdf
import random
import os
import subprocess
import shutil
from pathlib import Path

CHOOSING, CHOOSING_LEVEL, RECEIVING_FILE = range(3)


def get_ghostscript_path():
    return shutil.which("gs")


# GHOSTSCRIPT_PATH = r"C:\Program Files\gs\gs10.05.1\bin\gswin64c.exe"
GHOSTSCRIPT_PATH = get_ghostscript_path()
TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "there"
    keyboard = [
        [InlineKeyboardButton("📄 Convert Images to PDF",
                              callback_data="convert")],
        [InlineKeyboardButton("🗜️ Compress File",
                              callback_data="compression")],
    ]
    await update.message.reply_text(
        f"👋 Welcome, *{name}*! What would you like to do?\n\n"
        "You can also send /cancel anytime to stop.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cleanup_user_temp(update.effective_user.id)
    context.user_data.clear()
    await update.message.reply_text("🚫 Operation cancelled. Send /start to begin again.")
    return ConversationHandler.END


def cleanup_user_temp(user_id: int):
    user_dir = TEMP_DIR / str(user_id)
    if user_dir.exists():
        shutil.rmtree(user_dir)


def get_user_temp(user_id: int):
    user_dir = TEMP_DIR / str(user_id)
    user_dir.mkdir(exist_ok=True)
    return user_dir


async def start_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "convert":
        context.user_data["image_list"] = []
        await query.edit_message_text(
            "📷 Please send me all the images you want in the PDF."
        )
        return RECEIVING_FILE

    elif query.data == "compression":
        keyboard = [
            [
                InlineKeyboardButton(
                    "📷 Image", callback_data="compression_image"),
                InlineKeyboardButton("📄 PDF", callback_data="compression_pdf"),
            ]
        ]
        await query.edit_message_text(
            "🔧 Choose what to compress:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CHOOSING


async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_dir = get_user_temp(update.effective_user.id)
    image_list = context.user_data.setdefault("image_list", [])
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_path = user_dir / f"{len(image_list) + 1}.jpg"
    await file.download_to_drive(str(file_path))
    image_list.append(str(file_path))

    if len(image_list) == 1:
        await update.message.reply_text(
            f"✅ Image saved (1)! 📝 When ready, type `/done`."
        )
    else:
        await update.message.reply_text(
            f"✅ Image saved ({len(image_list)})!"
        )


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    image_list = context.user_data.get("image_list", [])
    if not image_list:
        await update.message.reply_text("⚠️ No images received. Send /start to try again.")
        return ConversationHandler.END

    username = update.effective_user.username or f"user{update.effective_user.id}"
    rand_num = random.randint(100, 999)
    pdf_filename = f"{username}-{rand_num}.pdf"

    try:
        with open(pdf_filename, "wb") as f:
            f.write(img2pdf.convert(image_list))

        await update.message.reply_document(open(pdf_filename, "rb"), caption="📄 Here is your PDF!")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to create PDF: {e}")
    finally:
        cleanup_user_temp(update.effective_user.id)
        if os.path.exists(pdf_filename):
            os.remove(pdf_filename)
        context.user_data.clear()

    return ConversationHandler.END


async def compression_type_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "compression_image":
        context.user_data["compression_mode"] = "Image"
    elif query.data == "compression_pdf":
        context.user_data["compression_mode"] = "PDF"

    keyboard = [
        [
            InlineKeyboardButton("🔷 High", callback_data="level_high"),
            InlineKeyboardButton("🔷 Medium", callback_data="level_medium"),
            InlineKeyboardButton("🔷 Low", callback_data="level_low"),
        ]
    ]
    await query.edit_message_text(
        f"🔧 Selected: *{context.user_data['compression_mode']} compression*.\nNow choose compression level:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_LEVEL


async def compression_level_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    quality_map = {
        "level_high": 90,
        "level_medium": 60,
        "level_low": 30,
    }
    context.user_data["compression_quality"] = quality_map.get(query.data, 60)

    await query.edit_message_text("📂 Now send me the file or photo to compress.")
    return RECEIVING_FILE


async def handle_compression(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_dir = get_user_temp(update.effective_user.id)
    compression_mode = context.user_data.get("compression_mode", "Image")

    if update.message.document:
        file = await update.message.document.get_file()
        file_name = update.message.document.file_name
    elif update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        file_name = f"photo_{random.randint(1000, 9999)}.jpg"
    else:
        await update.message.reply_text("⚠️ Please send a valid file or photo.")
        return RECEIVING_FILE

    file_path = user_dir / file_name
    await file.download_to_drive(str(file_path))

    output_path = user_dir / f"compressed_{file_name}"

    try:
        if compression_mode == "Image":
            img = Image.open(file_path)
            img = img.convert("RGB")
            img.save(
                output_path,
                format="JPEG",
                quality=context.user_data["compression_quality"],
                optimize=True,
                progressive=True
            )
            await update.message.reply_document(open(output_path, "rb"), caption="✅ Here is your compressed image.")

        elif compression_mode == "PDF":
            if not os.path.exists(GHOSTSCRIPT_PATH):
                await update.message.reply_text(
                    "⚠️ Ghostscript not found at the specified path.\nPlease check the path and try again."
                )
                return ConversationHandler.END

            await compress_pdf_with_gs(
                GHOSTSCRIPT_PATH,
                str(file_path),
                str(output_path),
                context.user_data["compression_quality"]
            )
            await update.message.reply_document(open(output_path, "rb"), caption="✅ Here is your compressed PDF.")

    except Exception as e:
        await update.message.reply_text(f"❌ Failed to compress: {e}")

    finally:
        cleanup_user_temp(update.effective_user.id)
        context.user_data.clear()

    return ConversationHandler.END


async def compress_pdf_with_gs(gs_exe, input_path, output_path, quality):
    quality_settings = {
        90: "/printer",
        60: "/ebook",
        30: "/screen",
    }
    gs_quality = quality_settings.get(quality, "/ebook")

    cmd = [
        gs_exe,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        "-dPDFSETTINGS=" + gs_quality,
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        f"-sOutputFile={output_path}",
        input_path,
    ]
    subprocess.run(cmd, check=True)


def main():
    TOKEN = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler_convert = ConversationHandler(
        entry_points=[CallbackQueryHandler(
            start_button_handler, pattern="^convert$")],
        states={
            RECEIVING_FILE: [
                MessageHandler(filters.PHOTO, receive_image),
                CommandHandler("done", done),
                CommandHandler("cancel", cancel),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True
    )

    conv_handler_compression = ConversationHandler(
        entry_points=[CallbackQueryHandler(
            start_button_handler, pattern="^compression$")],
        states={
            CHOOSING: [
                CallbackQueryHandler(
                    compression_type_handler, pattern="^compression_(image|pdf)$"),
            ],
            CHOOSING_LEVEL: [
                CallbackQueryHandler(
                    compression_level_handler, pattern="^level_(high|medium|low)$"),
            ],
            RECEIVING_FILE: [
                MessageHandler(filters.Document.ALL |
                               filters.PHOTO, handle_compression),
                CommandHandler("cancel", cancel),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(conv_handler_convert)
    app.add_handler(conv_handler_compression)

    print("🤖 Bot is running…")
    app.run_polling()


if __name__ == "__main__":
    main()
