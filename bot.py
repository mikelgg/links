# type: ignore
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
from bs4 import BeautifulSoup
import re
import os
import logging
import sys

# Configurar logging más detallado
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)

logger = logging.getLogger(__name__)

# Imprimir todas las variables de entorno (sin valores sensibles)
logger.info("Variables de entorno disponibles:")
for key in os.environ:
    logger.info(f"Variable encontrada: {key}")

# Tokens directamente en el código
TOKEN = "7912304550:AAHvWRVO3j4lwOUcD7soyyGxv8bsFFUwUdY"
MONITOR_GROUP_ID = "-1002429457610"

# Verificar token al inicio
if not TOKEN:
    logger.error("No se encontró el token del bot. Variables disponibles:")
    for key in os.environ:
        logger.error(f"- {key}")
    sys.exit(1)

logger.info(f"Token encontrado: {TOKEN[:5]}...{TOKEN[-5:]}")
logger.info(f"Monitor ID configurado: {MONITOR_GROUP_ID}")

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
    
    # Monitorear el mensaje recibido
    await forward_to_monitor(context, message.text)
    
    # Separar el mensaje en líneas
    lines = message.text.split('\n')
    if len(lines) != 3:
        await message.reply_text(
            "Por favor, usa el siguiente formato:\n"
            "título\n"
            "URL de la imagen\n"
            "enlace de sugargoo"
        )
        return
    
    title, image_url, sugargoo_url = lines
    
    # Verificar si es un enlace de SugarGoo
    if "sugargoo.com" not in sugargoo_url:
        print("URL no válida de SugarGoo")
        await message.reply_text("El tercer enlace debe ser de SugarGoo.")
        return
    
    try:
        # Extraer la URL original del producto
        product_link_match = re.search(r'productLink=(.*?)(?:&|$)', sugargoo_url)
        if not product_link_match:
            raise ValueError("No se pudo encontrar el enlace del producto")
            
        product_url = requests.utils.unquote(product_link_match.group(1))
        print("URL del producto:", product_url)
        
        # Obtener el ID del producto
        item_id = extract_item_id(product_url)
        if not item_id:
            raise ValueError("No se pudo extraer el ID del producto")
            
        # Generar enlaces alternativos según la plataforma
        encoded_product_url = requests.utils.quote(product_url)
        wemimi_link = f"https://www.wemimi.com/#/home/productDetail?productLink={encoded_product_url}&memberId=1700341715280059890"
        
        # Para Weidian usamos un formato diferente en OOTDBUY
        if "weidian.com" in product_url:
            ootdbuy_link = f"https://www.ootdbuy.com/goods/details?id={item_id}&channel=weidian&inviteCode=IVA6HF6CN"
        else:
            ootdbuy_link = f"https://www.ootdbuy.com/goods/details?id={item_id}&channel=1688&inviteCode=IVA6HF6CN"
        
        try:
            await message.reply_photo(
                photo=image_url,
                caption=f"{title}\n\n"
                        f"<a href='{ootdbuy_link}'>OOTDBUY</a> | "
                        f"<a href='{wemimi_link}'>WEMIMI</a> | "
                        f"<a href='{sugargoo_url}'>SUGARGOO</a>",
                parse_mode='HTML'
            )
        except Exception as e:
            print(f"Error al enviar imagen: {e}")
            await message.reply_text(
                f"{title}\n\n"
                f"<a href='{ootdbuy_link}'>OOTDBUY</a> | "
                f"<a href='{wemimi_link}'>WEMIMI</a> | "
                f"<a href='{sugargoo_url}'>SUGARGOO</a>",
                parse_mode='HTML'
            )
    
    except requests.RequestException as e:
        await message.reply_text("Error al acceder al enlace. Por favor, verifica que el enlace sea válido.")
        print(f"Error de solicitud: {e}")
    except ValueError as e:
        await message.reply_text(f"Error al procesar el producto: {str(e)}")
        print(f"Error de valor: {e}")
    except Exception as e:
        await message.reply_text("Lo siento, ocurrió un error inesperado.")
        print(f"Error inesperado: {e}")

def extract_item_id(url):
    # Extraer el ID del producto de diferentes plataformas
    if "1688.com" in url:
        # Para enlaces de 1688.com
        pattern = r'offer/(\d+)\.html'
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    elif "weidian.com" in url:
        # Para enlaces de Weidian
        pattern = r'itemID=(\d+)'
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

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
