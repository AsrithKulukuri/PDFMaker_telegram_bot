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


def get_ghostscript_path():
    return shutil.which("gs")


IMAGE_LIST = []
COMPRESSION_MODE = None

CHOOSING, CHOOSING_LEVEL, RECEIVING_FILE = range(3)

# GHOSTSCRIPT_PATH = r"C:\Program Files\gs\gs10.05.1\bin\gswin64c.exe"
GHOSTSCRIPT_PATH = get_ghostscript_path()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "there"
    keyboard = [
        [InlineKeyboardButton("📄 Convert Images to PDF",
                              callback_data="convert")],
        [InlineKeyboardButton("🗜️ Compress File",
                              callback_data="compression")],
    ]
    await update.message.reply_text(
        f"👋 Welcome, *{name}*! What would you like to do?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def start_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "convert":
        IMAGE_LIST.clear()
        await query.edit_message_text(
            "📷 Please send me *all the images you want in the PDF*. Send `/done` when finished.",
            parse_mode="Markdown"
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
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_path = f"temp_{len(IMAGE_LIST)}.jpg"
    await file.download_to_drive(file_path)
    IMAGE_LIST.append(file_path)
    await update.message.reply_text("✅ Image saved! Send more or `/done`.")


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not IMAGE_LIST:
        await update.message.reply_text("⚠️ No images received.")
        return ConversationHandler.END

    username = update.effective_user.username or "user"
    rand_num = random.randint(10, 99)
    pdf_filename = f"{username}-{rand_num}.pdf"

    with open(pdf_filename, "wb") as f:
        f.write(img2pdf.convert(IMAGE_LIST))

    for img in IMAGE_LIST:
        os.remove(img)
    IMAGE_LIST.clear()

    await update.message.reply_document(open(pdf_filename, "rb"), caption="📄 Here is your PDF!")
    os.remove(pdf_filename)
    return ConversationHandler.END


async def compression_type_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global COMPRESSION_MODE
    query = update.callback_query
    await query.answer()

    if query.data == "compression_image":
        COMPRESSION_MODE = "Image"
    elif query.data == "compression_pdf":
        COMPRESSION_MODE = "PDF"

    keyboard = [
        [
            InlineKeyboardButton("🔷 High", callback_data="level_high"),
            InlineKeyboardButton("🔷 Medium", callback_data="level_medium"),
            InlineKeyboardButton("🔷 Low", callback_data="level_low"),
        ]
    ]
    await query.edit_message_text(
        f"🔧 Selected: *{COMPRESSION_MODE} compression*.\nNow choose compression level:",
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
    if update.message.document:  # file sent as document
        file = await update.message.document.get_file()
        file_name = update.message.document.file_name
    elif update.message.photo:  # file sent as photo
        photo = update.message.photo[-1]
        file = await photo.get_file()
        file_name = f"photo_{random.randint(1000, 9999)}.jpg"
    else:
        await update.message.reply_text("⚠️ Please send a file or photo.")
        return RECEIVING_FILE

    file_path = f"received_{file_name}"
    await file.download_to_drive(file_path)

    if COMPRESSION_MODE == "Image":
        output_path = f"compressed_{os.path.splitext(file_name)[0]}.jpg"
        img = Image.open(file_path)
        img = img.convert("RGB")  # ensures it can save as JPEG
        img.save(
            output_path,
            format="JPEG",
            quality=context.user_data["compression_quality"],
            optimize=True,
            progressive=True
        )

        await update.message.reply_document(open(output_path, "rb"), caption="✅ Here is your compressed image.")

    elif COMPRESSION_MODE == "PDF":
        output_path = f"compressed_{file_name}"

        if not os.path.exists(GHOSTSCRIPT_PATH):
            await update.message.reply_text(
                "⚠️ Ghostscript not found at the specified path.\n"
                "Please check the path and try again."
            )
            os.remove(file_path)
            return ConversationHandler.END

        await compress_pdf_with_gs(GHOSTSCRIPT_PATH, file_path, output_path, context.user_data["compression_quality"])

        await update.message.reply_document(open(output_path, "rb"), caption="✅ Here is your compressed PDF.")

    os.remove(file_path)
    os.remove(output_path)
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
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Ghostscript failed: {e}")


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
            ],
        },
        fallbacks=[],
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
            ],
        },
        fallbacks=[],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler_convert)
    app.add_handler(conv_handler_compression)

    print("🤖 Bot is running…")
    app.run_polling()


if __name__ == "__main__":
    main()
