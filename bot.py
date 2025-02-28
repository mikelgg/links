# type: ignore
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
from bs4 import BeautifulSoup
import re
import os
import logging
import sys

# Configurar logging solo para información importante
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Desactivar logs de httpx y otros módulos
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Tokens y códigos
TOKEN = "7912304550:AAHvWRVO3j4lwOUcD7soyyGxv8bsFFUwUdY"
MONITOR_GROUP_ID = "-1002429457610"
OOTDBUY_INVITE = "K3YUN0O7N"
WEMIMI_ID = "1700341715280059890"

async def forward_to_monitor(context: ContextTypes.DEFAULT_TYPE, message_text: str):
    """Envía una copia del mensaje al grupo de monitoreo"""
    if MONITOR_GROUP_ID:
        try:
            await context.bot.send_message(
                chat_id=MONITOR_GROUP_ID,
                text=f"💬 Nuevo mensaje:\n{message_text}"
            )
        except Exception as e:
            print(f"Error al enviar al monitor: {e}")

def generate_links(product_url, item_id):
    """Genera todos los enlaces necesarios"""
    # Codificar URL para Wemimi y Sugargoo
    encoded_url = requests.utils.quote(product_url)
    double_encoded_url = requests.utils.quote(encoded_url)  # Para Wemimi

    # Determinar el canal para OOTDBUY
    if "weidian.com" in product_url:
        channel = "weidian"
    elif "taobao.com" in product_url:
        channel = "TAOBAO"
    else:  # 1688.com
        channel = "1688"

    return {
        'ootdbuy': f"https://www.ootdbuy.com/goods/details?id={item_id}&channel={channel}&inviteCode={OOTDBUY_INVITE}",
        'wemimi': f"https://www.wemimi.com/#/home/productDetail?productLink={double_encoded_url}&memberId={WEMIMI_ID}",
        'sugargoo': f"https://www.sugargoo.com/#/home/productDetail?productLink={encoded_url}"
    }

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"¡Hola! Este es el ID del chat: {chat_id}\n"
        "Envíame un enlace de SugarGoo y te generaré enlaces alternativos."
    )
    # Monitorear el comando start
    await forward_to_monitor(context, "Usó el comando /start")

async def process_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.channel_post
    if not message:
        print("No se pudo obtener el mensaje")
        return
        
    print("Recibido mensaje:", message.text)
    await forward_to_monitor(context, message.text)
    
    # Separar el mensaje en líneas
    lines = message.text.split('\n')
    
    # Procesar según el número de líneas
    if len(lines) == 3:  # Formato original: título, imagen, sugargoo
        title, image_url, product_url = lines
    elif len(lines) == 2:  # Nuevo formato: título, enlace directo
        title, product_url = lines
        image_url = None
    else:
        await message.reply_text(
            "Por favor, usa uno de estos formatos:\n\n"
            "1. título\nURL de la imagen\nenlace de sugargoo\n\n"
            "2. título\nenlace directo de 1688/weidian/taobao"
        )
        return

    try:
        # Si es un enlace de Sugargoo, extraer el enlace original
        if "sugargoo.com" in product_url:
            product_link_match = re.search(r'productLink=(.*?)(?:&|$)', product_url)
            if not product_link_match:
                raise ValueError("No se pudo encontrar el enlace del producto")
            product_url = requests.utils.unquote(product_link_match.group(1))
        
        # Obtener el ID del producto
        item_id = extract_item_id(product_url)
        if not item_id:
            raise ValueError("No se pudo extraer el ID del producto")
        
        # Generar todos los enlaces
        links = generate_links(product_url, item_id)
        
        # Preparar el mensaje con los enlaces en negrita
        message_text = f"{title} 🔥\n"
        message_text += f"<b><a href='{links['ootdbuy']}'>OOTDBUY</a></b> | "
        message_text += f"<b><a href='{links['wemimi']}'>WEMIMI</a></b> | "
        message_text += f"<b><a href='{links['sugargoo']}'>SUGARGOO</a></b>"

        if image_url:
            try:
                await message.reply_photo(
                    photo=image_url,
                    caption=message_text,
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Error al enviar imagen: {e}")
                await message.reply_text(message_text, parse_mode='HTML')
        else:
            await message.reply_text(message_text, parse_mode='HTML')

    except Exception as e:
        await message.reply_text(f"Error al procesar el enlace: {str(e)}")
        print(f"Error: {e}")

def extract_item_id(url):
    """Extraer el ID del producto de diferentes plataformas"""
    if "1688.com" in url:
        pattern = r'offer/(\d+)\.html'
    elif "weidian.com" in url:
        pattern = r'itemID=(\d+)'
    elif "taobao.com" in url:
        pattern = r'id=(\d+)'
    else:
        return None

    match = re.search(pattern, url)
    return match.group(1) if match else None

def main():
    try:
        logger.info("Iniciando el bot...")
        application = Application.builder().token(TOKEN).build()
        
        # Manejadores
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_link))
        
        logger.info("Bot iniciado correctamente")
        application.run_polling()
    except Exception as e:
        logger.error(f"Error al iniciar el bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
