# type: ignore
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import requests
from bs4 import BeautifulSoup
import re
import os
import logging
import sys

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Tokens y códigos
TOKEN = "7912304550:AAHvWRVO3j4lwOUcD7soyyGxv8bsFFUwUdY"
MONITOR_GROUP_ID = "-1002429457610"
OOTDBUY_INVITE = "K3YUN0O7N"
WEMIMI_ID = "1700341715280059890"

# Estados para la conversación
TITULO, IMAGEN, ENLACE = range(3)
datos_temporales = {}

async def forward_to_monitor(context: ContextTypes.DEFAULT_TYPE, message_text: str):
    if MONITOR_GROUP_ID:
        try:
            await context.bot.send_message(
                chat_id=MONITOR_GROUP_ID,
                text=message_text,
                parse_mode='HTML'
            )
        except Exception as e:
            print(f"Error al enviar al monitor: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Hola! Vamos a crear tu enlace paso a paso.\n"
        "Por favor, envíame primero el título del producto:"
    )
    return TITULO

async def recibir_titulo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    datos_temporales[user_id] = {'titulo': update.message.text}
    await update.message.reply_text("Título guardado. Ahora envíame el enlace de la imagen:")
    return IMAGEN

async def recibir_imagen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    datos_temporales[user_id]['imagen'] = update.message.text
    await update.message.reply_text("Imagen guardada. Por último, envíame el enlace de Sugargoo o el enlace directo de 1688/Weidian/Taobao:")
    return ENLACE

async def recibir_enlace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    message = update.message
    product_url = message.text
    
    datos = datos_temporales.get(user_id, {})
    title = datos.get('titulo', '')
    image_url = datos.get('imagen', '')
    
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
        
        # Preparar el mensaje con los enlaces en negrita y el emoji
        message_text = f"{title} 🔥\n"
        message_text += f"<b><a href='{links['ootdbuy']}'>OOTDBUY</a></b> | "
        message_text += f"<b><a href='{links['wemimi']}'>WEMIMI</a></b> | "
        message_text += f"<b><a href='{links['sugargoo']}'>SUGARGOO</a></b>"

        # Enviar al usuario
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

        # Enviar solo el resultado final al monitor
        await forward_to_monitor(context, message_text)

    except Exception as e:
        await message.reply_text(f"Error al procesar el enlace: {str(e)}")
        print(f"Error: {e}")
    
    # Limpiar datos temporales
    if user_id in datos_temporales:
        del datos_temporales[user_id]
    
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in datos_temporales:
        del datos_temporales[user_id]
    await update.message.reply_text("Proceso cancelado. Puedes empezar de nuevo con /start")
    return ConversationHandler.END

def generate_links(product_url, item_id):
    """Genera todos los enlaces necesarios"""
    encoded_url = requests.utils.quote(product_url)
    double_encoded_url = requests.utils.quote(encoded_url)

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

async def process_channel_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Intentar obtener el mensaje del canal de diferentes formas
    message = update.channel_post or update.message or update.effective_message
    if not message or not message.text:
        print("No se pudo obtener el mensaje del canal")
        return
        
    print(f"Mensaje recibido del canal: {message.text}")
    lines = message.text.split('\n')
    
    # Procesar según el número de líneas
    if len(lines) == 3:  # Formato: título, imagen, sugargoo
        title, image_url, product_url = lines
    elif len(lines) == 2:  # Formato: título, enlace directo
        title, product_url = lines
        image_url = None
    else:
        print(f"Formato incorrecto. Número de líneas: {len(lines)}")
        return
    
    try:
        # Si es un enlace de Sugargoo, extraer el enlace original
        if "sugargoo.com" in product_url:
            product_link_match = re.search(r'productLink=(.*?)(?:&|$)', product_url)
            if not product_link_match:
                print("No se pudo encontrar el enlace del producto en Sugargoo")
                return
            product_url = requests.utils.unquote(product_link_match.group(1))
            print(f"URL extraída de Sugargoo: {product_url}")
        
        # Obtener el ID del producto
        item_id = extract_item_id(product_url)
        if not item_id:
            print(f"No se pudo extraer el ID del producto de: {product_url}")
            return
        
        print(f"ID del producto extraído: {item_id}")
        
        # Generar todos los enlaces
        links = generate_links(product_url, item_id)
        
        # Preparar el mensaje con los enlaces en negrita y el emoji
        message_text = f"{title} 🔥\n"
        message_text += f"<b><a href='{links['ootdbuy']}'>OOTDBUY</a></b> | "
        message_text += f"<b><a href='{links['wemimi']}'>WEMIMI</a></b> | "
        message_text += f"<b><a href='{links['sugargoo']}'>SUGARGOO</a></b>"

        # Intentar enviar la respuesta al canal
        try:
            if image_url:
                await context.bot.send_photo(
                    chat_id=message.chat_id,
                    photo=image_url,
                    caption=message_text,
                    parse_mode='HTML',
                    reply_to_message_id=message.message_id
                )
            else:
                await context.bot.send_message(
                    chat_id=message.chat_id,
                    text=message_text,
                    parse_mode='HTML',
                    reply_to_message_id=message.message_id
                )
            
            # Enviar al monitor
            await forward_to_monitor(context, message_text)
            
        except Exception as e:
            print(f"Error al enviar mensaje al canal: {e}")
            
    except Exception as e:
        print(f"Error en proceso de canal: {e}")

def main():
    try:
        logger.info("Iniciando el bot...")
        application = Application.builder().token(TOKEN).build()
        
        # Agregar manejador para mensajes en canales y grupos PRIMERO
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & (filters.ChatType.CHANNEL | filters.ChatType.GROUP),
            process_channel_message
        ))
        
        # Crear el manejador de conversación para chats privados
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                TITULO: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, recibir_titulo)],
                IMAGEN: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, recibir_imagen)],
                ENLACE: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, recibir_enlace)]
            },
            fallbacks=[CommandHandler('cancelar', cancelar)]
        )
        
        # Agregar el manejador de conversación para chats privados
        application.add_handler(conv_handler)
        
        logger.info("Bot iniciado correctamente")
        application.run_polling()
    except Exception as e:
        logger.error(f"Error al iniciar el bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
