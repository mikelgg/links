# type: ignore
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, JobQueue
import requests
from bs4 import BeautifulSoup
import re
import os
import logging
import sys
import asyncio
from collections import deque
from datetime import datetime, timedelta, time
import pytz

# Modificar la configuración de logging para que sea mínima
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.ERROR
)

# Desactivar logs de las bibliotecas
logging.getLogger('httpx').setLevel(logging.CRITICAL)
logging.getLogger('httpcore').setLevel(logging.CRITICAL)
logging.getLogger('telegram').setLevel(logging.CRITICAL)

logger = logging.getLogger(__name__)

# Tokens y códigos
TOKEN = "7912304550:AAHvWRVO3j4lwOUcD7soyyGxv8bsFFUwUdY"
MONITOR_GROUP_ID = "-1002429457610"
OOTDBUY_INVITE = "K3YUN0O7N"
WEMIMI_ID = "1700341715280059890"
FISHGOO_ID = "2189734375162456157"

# Estados para la conversación
TITULO, IMAGEN, ENLACE = range(3)
datos_temporales = {}
canal_estado = {}
canal_datos = {}

# Sistema de cola para mensajes de monitoreo
class MessageQueue:
    def __init__(self):
        self.queue = deque()
        self.last_sent = datetime.now()
        self.is_processing = False

    async def add_message(self, context, message_data):
        self.queue.append(message_data)
        if not self.is_processing:
            self.is_processing = True
            await self.process_queue(context)

    async def process_queue(self, context):
        while self.queue:
            # Esperar si es necesario para respetar el rate limit
            time_since_last = datetime.now() - self.last_sent
            if time_since_last.total_seconds() < 2:  # Esperar al menos 2 segundos entre mensajes
                await asyncio.sleep(2 - time_since_last.total_seconds())

            try:
                message_data = self.queue.popleft()
                await self._send_message(context, message_data)
                self.last_sent = datetime.now()
            except Exception as e:
                if "Flood control exceeded" in str(e):
                    # Volver a poner el mensaje en la cola
                    self.queue.appendleft(message_data)
                    retry_time = int(str(e).split("Retry in ")[1].split(" ")[0])
                    logger.warning(f"Flood control activado. Esperando {retry_time} segundos...")
                    await asyncio.sleep(retry_time)
                else:
                    logger.error(f"Error al enviar mensaje al monitor: {e}")

        self.is_processing = False

    async def _send_message(self, context, message_data):
        text = message_data.get('text', '')
        extra_info = message_data.get('extra_info', '')
        media = message_data.get('media', {})

        if extra_info:
            text = f"{text}\n\n<i>Info adicional:</i>\n{extra_info}"

        if media:
            media_type = media.get('type')
            media_file = media.get('file')
            
            if media_type == 'photo':
                await context.bot.send_photo(
                    chat_id=MONITOR_GROUP_ID,
                    photo=media_file,
                    caption=text,
                    parse_mode='HTML'
                )
            elif media_type == 'document':
                await context.bot.send_document(
                    chat_id=MONITOR_GROUP_ID,
                    document=media_file,
                    caption=text,
                    parse_mode='HTML'
                )
            # ... (resto de tipos de media)
        else:
            await context.bot.send_message(
                chat_id=MONITOR_GROUP_ID,
                text=text,
                parse_mode='HTML'
            )

# Crear instancia global de la cola de mensajes
message_queue = MessageQueue()

async def forward_to_monitor(context: ContextTypes.DEFAULT_TYPE, message_text: str, extra_info=None,
                           photo=None, document=None, video=None, audio=None, voice=None, sticker=None):
    """Envía información al grupo monitor usando el sistema de cola"""
    if not MONITOR_GROUP_ID:
        return

    message_data = {
        'text': message_text,
        'extra_info': extra_info,
        'media': {}
    }

    if photo:
        message_data['media'] = {'type': 'photo', 'file': photo}
    elif document:
        message_data['media'] = {'type': 'document', 'file': document}
    elif video:
        message_data['media'] = {'type': 'video', 'file': video}
    elif audio:
        message_data['media'] = {'type': 'audio', 'file': audio}
    elif voice:
        message_data['media'] = {'type': 'voice', 'file': voice}
    elif sticker:
        message_data['media'] = {'type': 'sticker', 'file': sticker}

    await message_queue.add_message(context, message_data)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Hola! Vamos a crear tu enlace paso a paso.\n"
        "Por favor, envíame primero el título del producto:"
    )
    return TITULO

async def recibir_titulo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    datos_temporales[user_id] = {'titulo': update.message.text}
    await update.message.reply_text("Título guardado. Ahora envía la imagen o el enlace de la imagen: (o escribe 'cancelar' para detener el proceso)")
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
        message_text += f"<b><a href='{links['sugargoo']}'>SUGARGOO</a></b> | "
        message_text += f"<b><a href='{links['fishgoo']}'>FISHGOO</a></b>\n\n"
        message_text += f"QC:\n"
        message_text += f"<b><a href='{links['finderqc']}'>FINDERQC</a></b> | "
        message_text += f"<b><a href='{links['doppel']}'>DOPPEL</a></b>"

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

        # Crear información adicional para el monitor
        user_info = f"Usuario: {message.from_user.first_name if message.from_user else 'Desconocido'}"
        chat_info = f"Chat: {message.chat.title if message.chat.title else message.chat.id}"
        if message.message_thread_id:
            chat_info += f" (Hilo: {message.message_thread_id})"

        monitor_extra = f"{user_info}\n{chat_info}\nTipo: {'Grupo' if message.chat.type in ['group', 'supergroup'] else 'Canal'}"

        # Enviar al monitor con la información adicional
        await forward_to_monitor(context, message_text, monitor_extra)

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
        finderqc_url = f"https://finderqc.com/search?q={product_url}"
        doppel_url = f"https://doppel.fit/item/WEIDIAN/{item_id}"
    elif "taobao.com" in product_url:
        channel = "TAOBAO"
        finderqc_url = f"https://finderqc.com/search?q={product_url}"
        doppel_url = f"https://doppel.fit/item/taobao/{item_id}"
    else:  # 1688.com
        channel = "1688"
        finderqc_url = f"https://finderqc.com/search?q={product_url}"
        doppel_url = f"https://doppel.fit/item/1688/{item_id}"

    links = {
        'ootdbuy': f"https://www.ootdbuy.com/goods/details?id={item_id}&channel={channel}&inviteCode={OOTDBUY_INVITE}",
        'wemimi': f"https://www.wemimi.com/#/home/productDetail?productLink={double_encoded_url}&memberId={WEMIMI_ID}",
        'sugargoo': f"https://www.sugargoo.com/#/home/productDetail?productLink={encoded_url}",
        'fishgoo': f"https://www.fishgoo.com/#/product?productLink={encoded_url}&memberId={FISHGOO_ID}",
        'finderqc': finderqc_url,
        'doppel': doppel_url
    }

    return links

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

async def get_bot_groups(context: ContextTypes.DEFAULT_TYPE):
    """Obtiene la lista de grupos donde está añadido el bot"""
    try:
        # Obtener información sobre el bot
        bot_info = await context.bot.get_me()
        
        # Crear mensaje con información de los grupos
        # Nota: La API de Telegram no permite obtener directamente la lista de chats
        # donde está el bot, por lo que mostraremos información general
        message = f"🤖 <b>Estado del Bot</b>\n\n"
        message += f"📊 <b>Bot:</b> @{bot_info.username}\n"
        message += f"🆔 <b>ID:</b> {bot_info.id}\n"
        message += f"📅 <b>Fecha:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
        message += f"ℹ️ <i>El bot está activo y monitoreando todos los grupos donde ha sido añadido.</i>\n"
        message += f"📈 <i>Todos los mensajes son procesados y reenviados al grupo monitor.</i>"
        
        return message
    except Exception as e:
        logger.error(f"Error al obtener información del bot: {e}")
        return f"❌ Error al obtener información del bot: {str(e)}"

async def send_startup_message(context: ContextTypes.DEFAULT_TYPE):
    """Envía un mensaje cuando el bot se inicia"""
    try:
        startup_message = f"🚀 <b>Bot Iniciado</b>\n\n"
        startup_message += f"✅ El bot se ha puesto en marcha correctamente\n"
        startup_message += f"🕐 <b>Hora de inicio:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
        startup_message += f"🔄 <b>Estado:</b> Activo y listo para procesar mensajes\n\n"
        startup_message += f"📋 <i>Todas las funcionalidades están operativas</i>"
        
        await context.bot.send_message(
            chat_id=MONITOR_GROUP_ID,
            text=startup_message,
            parse_mode='HTML'
        )
        logger.info("Mensaje de inicio enviado correctamente")
    except Exception as e:
        logger.error(f"Error al enviar mensaje de inicio: {e}")

async def send_startup_message_direct(bot):
    """Envía un mensaje de inicio directamente sin JobQueue"""
    try:
        startup_message = f"🚀 <b>Bot Iniciado</b>\n\n"
        startup_message += f"✅ El bot se ha puesto en marcha correctamente\n"
        startup_message += f"🕐 <b>Hora de inicio:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
        startup_message += f"🔄 <b>Estado:</b> Activo y listo para procesar mensajes\n\n"
        startup_message += f"📋 <i>Todas las funcionalidades están operativas</i>\n"
        startup_message += f"⚠️ <i>Nota: Tareas programadas no disponibles</i>"
        
        await bot.send_message(
            chat_id=MONITOR_GROUP_ID,
            text=startup_message,
            parse_mode='HTML'
        )
        print("✅ Mensaje de inicio enviado correctamente")
    except Exception as e:
        print(f"❌ Error al enviar mensaje de inicio: {e}")

async def send_groups_report(context: ContextTypes.DEFAULT_TYPE):
    """Envía el reporte de grupos cada 2 días a las 2 PM"""
    try:
        groups_info = await get_bot_groups(context)
        
        report_message = f"📊 <b>Reporte Automático de Grupos</b>\n\n"
        report_message += groups_info
        report_message += f"\n\n🔄 <i>Próximo reporte en 2 días</i>"
        
        await context.bot.send_message(
            chat_id=MONITOR_GROUP_ID,
            text=report_message,
            parse_mode='HTML'
        )
        logger.info("Reporte de grupos enviado correctamente")
    except Exception as e:
        logger.error(f"Error al enviar reporte de grupos: {e}")

async def process_channel_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post
    if not message:
        return
    
    chat_id = message.chat_id
    
    # Determinar el tipo de contenido
    content_type = "desconocido"
    content_data = None
    
    if message.text:
        content_type = "texto"
        content_data = message.text.strip()
        
        # Verificar si quiere cancelar el proceso (solo para mensajes de texto)
        if content_data.lower() in ["cancelar", "cancel", "stop", "parar", "detener"]:
            if chat_id in canal_estado:
                del canal_estado[chat_id]
            if chat_id in canal_datos:
                del canal_datos[chat_id]
            await context.bot.send_message(
                chat_id=chat_id,
                text="Proceso cancelado. Puedes iniciar uno nuevo escribiendo 'iniciar'."
            )
            return
        
        # Iniciar proceso en el canal (solo para mensajes de texto)
        if content_data.lower() in ["iniciar", "crear", "nuevo", "/iniciar", "/crear", "/nuevo"]:
            # Inicializar estado y datos
            canal_estado[chat_id] = "TITULO"
            canal_datos[chat_id] = {
                "mensajes_a_eliminar": []
            }
            
            # Enviar mensaje de instrucciones
            response = await context.bot.send_message(
                chat_id=chat_id,
                text="🔄 <b>Proceso iniciado</b>\n\nPor favor, envía el título del producto:",
                parse_mode='HTML'
            )
            
            # Guardar ID del mensaje para eliminarlo después
            canal_datos[chat_id]["mensajes_a_eliminar"].append(response.message_id)
            return
    elif message.photo:
        content_type = "foto"
        content_data = message.photo[-1].file_id
        caption = message.caption
        
        # Si hay un caption, procesarlo como texto adicional
        if caption and chat_id in canal_estado:
            if canal_estado[chat_id] == "IMAGEN":
                # Si estamos esperando una imagen, usar esta foto
                canal_datos[chat_id]["imagen"] = content_data
                canal_estado[chat_id] = "ENLACE"
                
                # Enviar mensaje pidiendo el enlace
                response = await context.bot.send_message(
                    chat_id=chat_id,
                    text="✅ Imagen recibida.\n\nAhora envía el enlace del producto:",
                    parse_mode='HTML'
                )
                
                # Guardar ID del mensaje para eliminarlo después
                canal_datos[chat_id]["mensajes_a_eliminar"].append(response.message_id)
                return
    elif message.document:
        content_type = "documento"
        content_data = message.document.file_id
    elif message.video:
        content_type = "video"
        content_data = message.video.file_id
    elif message.audio:
        content_type = "audio"
        content_data = message.audio.file_id
    elif message.voice:
        content_type = "voz"
        content_data = message.voice.file_id
    elif message.sticker:
        content_type = "sticker"
        content_data = message.sticker.file_id
    else:
        # Otro tipo de contenido no manejado específicamente
        return
    
    # Si no hay un estado activo para este canal, ignorar el mensaje
    if chat_id not in canal_estado:
        return
    
    # Procesar según el estado actual
    estado = canal_estado[chat_id]
    
    if estado == "TITULO":
        # Guardar título y pedir imagen
        canal_datos[chat_id]["titulo"] = content_data
        canal_estado[chat_id] = "IMAGEN"
        
        # Enviar mensaje y guardar su ID
        img_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="Título guardado. Ahora envía la imagen o el enlace de la imagen: (o escribe 'cancelar' para detener el proceso)",
            message_thread_id=message.message_thread_id
        )
        canal_datos[chat_id]["mensajes_a_eliminar"].append(img_msg.message_id)
    
    elif estado == "IMAGEN":
        # Si es una foto enviada directamente
        if message.photo:
            # Usar el ID de la foto más grande (mejor calidad)
            photo_id = message.photo[-1].file_id
            canal_datos[chat_id]["imagen"] = photo_id
            canal_datos[chat_id]["es_file_id"] = True  # Marcar que es un file_id y no una URL
            canal_estado[chat_id] = "ENLACE"
            
            # Enviar mensaje y guardar su ID
            enlace_msg = await context.bot.send_message(
                chat_id=chat_id,
                text="Imagen guardada. Por último, envía el enlace de Sugargoo o el enlace directo: (o escribe 'cancelar' para detener el proceso)",
                message_thread_id=message.message_thread_id
            )
            canal_datos[chat_id]["mensajes_a_eliminar"].append(enlace_msg.message_id)
            return

        # Verificar si quiere saltar la imagen
        if content_data.lower() in ["saltar", "skip", "no", "ninguna"]:
            canal_datos[chat_id]["imagen"] = ""
            canal_estado[chat_id] = "ENLACE"
            
            # Enviar mensaje y guardar su ID
            enlace_msg = await context.bot.send_message(
                chat_id=chat_id,
                text="Imagen omitida. Por último, envía el enlace de Sugargoo o el enlace directo: (o escribe 'cancelar' para detener el proceso)",
                message_thread_id=message.message_thread_id
            )
            canal_datos[chat_id]["mensajes_a_eliminar"].append(enlace_msg.message_id)
            
        # Verificar si es una URL de imgur sin http/https
        elif "imgur.com" in content_data or "i.imgur.com" in content_data:
            # Añadir https:// si falta
            if not content_data.startswith("http"):
                image_url = f"https://{content_data}"
            else:
                image_url = content_data
            
            canal_datos[chat_id]["imagen"] = image_url
            canal_estado[chat_id] = "ENLACE"
            
            # Enviar mensaje y guardar su ID
            enlace_msg = await context.bot.send_message(
                chat_id=chat_id,
                text="Imagen guardada. Por último, envía el enlace de Sugargoo o el enlace directo: (o escribe 'cancelar' para detener el proceso)",
                message_thread_id=message.message_thread_id
            )
            canal_datos[chat_id]["mensajes_a_eliminar"].append(enlace_msg.message_id)
            
        # Verificar si es una URL de imagen válida (incluyendo otras plataformas)
        elif (content_data.startswith("http") and 
              (content_data.endswith(".jpg") or content_data.endswith(".jpeg") or content_data.endswith(".png") or 
               content_data.endswith(".webp") or content_data.endswith(".gif") or
               "img" in content_data or "ibb.co" in content_data)):
            # Guardar imagen y pedir enlace
            canal_datos[chat_id]["imagen"] = content_data
            canal_estado[chat_id] = "ENLACE"
            
            # Enviar mensaje y guardar su ID
            enlace_msg = await context.bot.send_message(
                chat_id=chat_id,
                text="Imagen guardada. Por último, envía el enlace de Sugargoo o el enlace directo: (o escribe 'cancelar' para detener el proceso)",
                message_thread_id=message.message_thread_id
            )
            canal_datos[chat_id]["mensajes_a_eliminar"].append(enlace_msg.message_id)
            
        else:
            # Si no parece una URL de imagen, preguntar de nuevo
            error_msg = await context.bot.send_message(
                chat_id=chat_id,
                text="No parece una URL de imagen válida. Puedes enviar una URL de imgur (como i.imgur.com/ejemplo.jpg), escribir 'saltar' para omitir este paso, o 'cancelar' para detener todo el proceso:",
                message_thread_id=message.message_thread_id
            )
            canal_datos[chat_id]["mensajes_a_eliminar"].append(error_msg.message_id)
    
    elif estado == "ENLACE":
        # Procesar el enlace final
        try:
            product_url = content_data
            datos = canal_datos.get(chat_id, {})
            title = datos.get("titulo", "")
            image_url = datos.get("imagen", "")
            
            print(f"Procesando: Título: {title}, Imagen: {image_url}, URL: {product_url}")
            
            # Si es un enlace de Sugargoo, extraer el enlace original
            if "sugargoo.com" in product_url:
                product_link_match = re.search(r'productLink=(.*?)(?:&|$)', product_url)
                if product_link_match:
                    product_url = requests.utils.unquote(product_link_match.group(1))
            
            # Obtener ID y generar enlaces
            item_id = extract_item_id(product_url)
            if not item_id:
                error_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text="No se pudo extraer el ID del producto. Intenta con otro enlace.",
                    message_thread_id=message.message_thread_id
                )
                canal_datos[chat_id]["mensajes_a_eliminar"].append(error_msg.message_id)
                return
            
            links = generate_links(product_url, item_id)
            
            # Crear mensaje final
            message_text = f"{title} 🔥\n"
            message_text += f"<b><a href='{links['ootdbuy']}'>OOTDBUY</a></b> | "
            message_text += f"<b><a href='{links['wemimi']}'>WEMIMI</a></b> | "
            message_text += f"<b><a href='{links['sugargoo']}'>SUGARGOO</a></b> | "
            message_text += f"<b><a href='{links['fishgoo']}'>FISHGOO</a></b>\n\n"
            message_text += f"QC:\n"
            message_text += f"<b><a href='{links['finderqc']}'>FINDERQC</a></b> | "
            message_text += f"<b><a href='{links['doppel']}'>DOPPEL</a></b>"
            
            # Eliminar todos los mensajes intermedios
            for msg_id in canal_datos[chat_id].get("mensajes_a_eliminar", []):
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception as e:
                    print(f"Error al eliminar mensaje {msg_id}: {e}")
            
            # Enviar respuesta final
            if image_url:
                try:
                    if canal_datos[chat_id].get("es_file_id", False):
                        # Si es un file_id, usar send_photo directamente con el ID
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=image_url,  # aquí image_url es en realidad el file_id
                            caption=message_text,
                            parse_mode='HTML',
                            message_thread_id=message.message_thread_id
                        )
                    else:
                        # Si es una URL, usar el código existente
                        if "imgur.com" in image_url and not image_url.startswith("https://i."):
                            image_id = image_url.split("/")[-1]
                            image_url = f"https://i.imgur.com/{image_id}.jpg"
                        
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=image_url,
                            caption=message_text,
                            parse_mode='HTML',
                            message_thread_id=message.message_thread_id
                        )
                except Exception as e:
                    print(f"Error al enviar imagen: {e}")
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=message_text,
                        parse_mode='HTML',
                        message_thread_id=message.message_thread_id
                    )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode='HTML',
                    message_thread_id=message.message_thread_id
                )
            
            # Crear información adicional para el monitor
            user_info = f"Usuario: {message.from_user.first_name if message.from_user else 'Desconocido'}"
            chat_info = f"Chat: {message.chat.title if message.chat.title else message.chat.id}"
            if message.message_thread_id:
                chat_info += f" (Hilo: {message.message_thread_id})"

            monitor_extra = f"{user_info}\n{chat_info}\nTipo: {'Grupo' if message.chat.type in ['group', 'supergroup'] else 'Canal'}"

            # Enviar al monitor con la información adicional
            await forward_to_monitor(context, message_text, monitor_extra)
            
        except Exception as e:
            print(f"Error en proceso de enlace: {e}")
            error_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"Error al procesar el enlace: {str(e)}",
                message_thread_id=message.message_thread_id
            )
            # No eliminamos este mensaje de error
        
        # Limpiar estado y datos
        if chat_id in canal_estado:
            del canal_estado[chat_id]
        if chat_id in canal_datos:
            del canal_datos[chat_id]

async def process_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    
    chat_id = message.chat_id
    message_id = message.message_id
    thread_id = message.message_thread_id  # ID del hilo de discusión si existe
    
    # Determinar el tipo de contenido
    content_type = "desconocido"
    content_data = None
    
    if message.text:
        content_type = "texto"
        content_data = message.text.strip()
    elif message.photo:
        content_type = "foto"
        content_data = message.photo[-1].file_id
    elif message.document:
        content_type = "documento"
        content_data = message.document.file_id
    elif message.video:
        content_type = "video"
        content_data = message.video.file_id
    elif message.audio:
        content_type = "audio"
        content_data = message.audio.file_id
    elif message.voice:
        content_type = "voz"
        content_data = message.voice.file_id
    elif message.sticker:
        content_type = "sticker"
        content_data = message.sticker.file_id
    else:
        # Otro tipo de contenido no manejado específicamente
        return
    
    print(f"Mensaje recibido en grupo: tipo={content_type}")
    print(f"Chat ID: {chat_id}, Thread ID: {thread_id}")
    
    # Crear una clave única para cada chat+hilo
    chat_key = f"{chat_id}_{thread_id}" if thread_id else str(chat_id)
    
    # Si no hay un estado activo para este chat+hilo, ignorar el mensaje
    if chat_key not in canal_estado:
        return
    
    print(f"Procesando mensaje en estado: {canal_estado[chat_key]}")
    
    # Lista para almacenar IDs de mensajes a eliminar después
    if "mensajes_a_eliminar" not in canal_datos[chat_key]:
        canal_datos[chat_key]["mensajes_a_eliminar"] = []
    
    # Guardar ID del mensaje del usuario para eliminarlo después
    canal_datos[chat_key]["mensajes_a_eliminar"].append(message_id)
    
    # Procesar según el estado actual
    estado = canal_estado[chat_key]
    
    if estado == "TITULO":
        # Guardar título y pedir imagen
        canal_datos[chat_key]["titulo"] = content_data
        canal_estado[chat_key] = "IMAGEN"
        
        # Enviar mensaje y guardar su ID
        img_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="Título guardado. Ahora envía la imagen o el enlace de la imagen: (o escribe 'cancelar' para detener el proceso)",
            message_thread_id=thread_id
        )
        canal_datos[chat_key]["mensajes_a_eliminar"].append(img_msg.message_id)
    
    elif estado == "IMAGEN":
        # Si es una foto enviada directamente
        if message.photo:
            # Usar el ID de la foto más grande (mejor calidad)
            photo_id = message.photo[-1].file_id
            canal_datos[chat_key]["imagen"] = photo_id
            canal_datos[chat_key]["es_file_id"] = True  # Marcar que es un file_id y no una URL
            canal_estado[chat_key] = "ENLACE"
            
            # Enviar mensaje y guardar su ID
            enlace_msg = await context.bot.send_message(
                chat_id=chat_id,
                text="Imagen guardada. Por último, envía el enlace de Sugargoo o el enlace directo: (o escribe 'cancelar' para detener el proceso)",
                message_thread_id=thread_id
            )
            canal_datos[chat_key]["mensajes_a_eliminar"].append(enlace_msg.message_id)
            return

        # Verificar si quiere saltar la imagen
        if content_data.lower() in ["saltar", "skip", "no", "ninguna"]:
            canal_datos[chat_key]["imagen"] = ""
            canal_estado[chat_key] = "ENLACE"
            
            # Enviar mensaje y guardar su ID
            enlace_msg = await context.bot.send_message(
                chat_id=chat_id,
                text="Imagen omitida. Por último, envía el enlace de Sugargoo o el enlace directo: (o escribe 'cancelar' para detener el proceso)",
                message_thread_id=thread_id
            )
            canal_datos[chat_key]["mensajes_a_eliminar"].append(enlace_msg.message_id)
            
        # Verificar si es una URL de imgur sin http/https
        elif "imgur.com" in content_data or "i.imgur.com" in content_data:
            # Añadir https:// si falta
            if not content_data.startswith("http"):
                image_url = f"https://{content_data}"
            else:
                image_url = content_data
            
            canal_datos[chat_key]["imagen"] = image_url
            canal_estado[chat_key] = "ENLACE"
            
            # Enviar mensaje y guardar su ID
            enlace_msg = await context.bot.send_message(
                chat_id=chat_id,
                text="Imagen guardada. Por último, envía el enlace de Sugargoo o el enlace directo: (o escribe 'cancelar' para detener el proceso)",
                message_thread_id=thread_id
            )
            canal_datos[chat_key]["mensajes_a_eliminar"].append(enlace_msg.message_id)
            
        # Verificar si es una URL de imagen válida (incluyendo otras plataformas)
        elif (content_data.startswith("http") and 
              (content_data.endswith(".jpg") or content_data.endswith(".jpeg") or content_data.endswith(".png") or 
               content_data.endswith(".webp") or content_data.endswith(".gif") or
               "img" in content_data or "ibb.co" in content_data)):
            # Guardar imagen y pedir enlace
            canal_datos[chat_key]["imagen"] = content_data
            canal_estado[chat_key] = "ENLACE"
            
            # Enviar mensaje y guardar su ID
            enlace_msg = await context.bot.send_message(
                chat_id=chat_id,
                text="Imagen guardada. Por último, envía el enlace de Sugargoo o el enlace directo: (o escribe 'cancelar' para detener el proceso)",
                message_thread_id=thread_id
            )
            canal_datos[chat_key]["mensajes_a_eliminar"].append(enlace_msg.message_id)
            
        else:
            # Si no parece una URL de imagen, preguntar de nuevo
            error_msg = await context.bot.send_message(
                chat_id=chat_id,
                text="No parece una URL de imagen válida. Puedes enviar una URL de imgur (como i.imgur.com/ejemplo.jpg), escribir 'saltar' para omitir este paso, o 'cancelar' para detener todo el proceso:",
                message_thread_id=thread_id
            )
            canal_datos[chat_key]["mensajes_a_eliminar"].append(error_msg.message_id)
    
    elif estado == "ENLACE":
        # Procesar el enlace final
        try:
            product_url = content_data
            datos = canal_datos.get(chat_key, {})
            title = datos.get("titulo", "")
            image_url = datos.get("imagen", "")
            
            print(f"Procesando: Título: {title}, Imagen: {image_url}, URL: {product_url}")
            
            # Si es un enlace de Sugargoo, extraer el enlace original
            if "sugargoo.com" in product_url:
                product_link_match = re.search(r'productLink=(.*?)(?:&|$)', product_url)
                if product_link_match:
                    product_url = requests.utils.unquote(product_link_match.group(1))
            
            # Obtener ID y generar enlaces
            item_id = extract_item_id(product_url)
            if not item_id:
                error_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text="No se pudo extraer el ID del producto. Intenta con otro enlace.",
                    message_thread_id=thread_id
                )
                canal_datos[chat_key]["mensajes_a_eliminar"].append(error_msg.message_id)
                return
            
            links = generate_links(product_url, item_id)
            
            # Crear mensaje final
            message_text = f"{title} 🔥\n"
            message_text += f"<b><a href='{links['ootdbuy']}'>OOTDBUY</a></b> | "
            message_text += f"<b><a href='{links['wemimi']}'>WEMIMI</a></b> | "
            message_text += f"<b><a href='{links['sugargoo']}'>SUGARGOO</a></b> | "
            message_text += f"<b><a href='{links['fishgoo']}'>FISHGOO</a></b>\n\n"
            message_text += f"QC:\n"
            message_text += f"<b><a href='{links['finderqc']}'>FINDERQC</a></b> | "
            message_text += f"<b><a href='{links['doppel']}'>DOPPEL</a></b>"
            
            # Eliminar todos los mensajes intermedios
            for msg_id in canal_datos[chat_key].get("mensajes_a_eliminar", []):
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception as e:
                    print(f"Error al eliminar mensaje {msg_id}: {e}")
            
            # Enviar respuesta final
            if image_url:
                try:
                    if canal_datos[chat_key].get("es_file_id", False):
                        # Si es un file_id, usar send_photo directamente con el ID
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=image_url,  # aquí image_url es en realidad el file_id
                            caption=message_text,
                            parse_mode='HTML',
                            message_thread_id=thread_id
                        )
                    else:
                        # Si es una URL, usar el código existente
                        if "imgur.com" in image_url and not image_url.startswith("https://i."):
                            image_id = image_url.split("/")[-1]
                            image_url = f"https://i.imgur.com/{image_id}.jpg"
                        
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=image_url,
                            caption=message_text,
                            parse_mode='HTML',
                            message_thread_id=thread_id
                        )
                except Exception as e:
                    print(f"Error al enviar imagen: {e}")
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=message_text,
                        parse_mode='HTML',
                        message_thread_id=thread_id
                    )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode='HTML',
                    message_thread_id=thread_id
                )
            
            # Crear información adicional para el monitor
            user_info = f"Usuario: {message.from_user.first_name if message.from_user else 'Desconocido'}"
            chat_info = f"Chat: {message.chat.title if message.chat.title else message.chat.id}"
            if thread_id:
                chat_info += f" (Hilo: {thread_id})"

            monitor_extra = f"{user_info}\n{chat_info}\nTipo: {'Grupo' if message.chat.type in ['group', 'supergroup'] else 'Canal'}"

            # Enviar al monitor con la información adicional
            await forward_to_monitor(context, message_text, monitor_extra)
            
        except Exception as e:
            print(f"Error en proceso de enlace: {e}")
            error_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"Error al procesar el enlace: {str(e)}",
                message_thread_id=thread_id
            )
            # No eliminamos este mensaje de error
        
        # Limpiar estado y datos
        if chat_key in canal_estado:
            del canal_estado[chat_key]
        if chat_key in canal_datos:
            del canal_datos[chat_key]

# Agregar estos manejadores específicos para comandos en grupos
async def iniciar_comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejador específico para el comando /iniciar en grupos"""
    message = update.message
    if not message:
        return
    
    chat_id = message.chat_id
    message_id = message.message_id
    thread_id = message.message_thread_id
    
    print(f"Comando /iniciar recibido en chat: {chat_id}, thread: {thread_id}")
    
    # Crear una clave única para cada chat+hilo
    chat_key = f"{chat_id}_{thread_id}" if thread_id else str(chat_id)
    
    # Inicializar datos
    canal_estado[chat_key] = "TITULO"
    if chat_key not in canal_datos:
        canal_datos[chat_key] = {"mensajes_a_eliminar": []}
    
    # Guardar ID del mensaje de inicio
    canal_datos[chat_key]["mensajes_a_eliminar"].append(message_id)
    
    # Enviar mensaje pidiendo título
    try:
        titulo_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="Por favor, envía el título del producto:",
            message_thread_id=thread_id
        )
        canal_datos[chat_key]["mensajes_a_eliminar"].append(titulo_msg.message_id)
        print(f"Mensaje de título enviado con ID: {titulo_msg.message_id}")
    except Exception as e:
        print(f"Error al enviar mensaje de título: {e}")

async def cancelar_comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejador específico para el comando /cancelar en grupos"""
    message = update.message
    if not message:
        return
    
    chat_id = message.chat_id
    thread_id = message.message_thread_id
    
    # Crear una clave única para cada chat+hilo
    chat_key = f"{chat_id}_{thread_id}" if thread_id else str(chat_id)
    
    if chat_key in canal_estado:
        del canal_estado[chat_key]
        
        # Eliminar mensajes intermedios
        for msg_id in canal_datos[chat_key].get("mensajes_a_eliminar", []):
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception as e:
                print(f"Error al eliminar mensaje {msg_id}: {e}")
        
        if chat_key in canal_datos:
            del canal_datos[chat_key]
            
        # Enviar mensaje de cancelación
        await context.bot.send_message(
            chat_id=chat_id,
            text="Proceso cancelado. Puedes iniciar uno nuevo con /iniciar",
            message_thread_id=thread_id
        )

async def monitor_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Versión simplificada del monitor de mensajes"""
    message = update.message or update.channel_post
    if not message or str(message.chat_id) == MONITOR_GROUP_ID:
        return True

    if message.text and message.text.startswith('/'):
        if message.text not in ['/iniciar', '/start', '/cancelar']:
            return True

    # Obtener solo el nombre del usuario
    user = message.from_user
    user_name = f"{user.first_name} {user.last_name if user.last_name else ''}" if user else "Desconocido"
    
    base_info = f"👤 {user_name}"

    # Procesar según el tipo de contenido
    if message.text:
        await forward_to_monitor(context, f"{base_info}: {message.text}")
    elif message.photo:
        await forward_to_monitor(
            context,
            f"{base_info}: {message.caption if message.caption else '[Foto]'}",
            photo=message.photo[-1].file_id
        )
    elif message.document:
        await forward_to_monitor(
            context,
            f"{base_info}: {message.caption if message.caption else '[Documento]'}",
            document=message.document.file_id
        )
    elif message.video:
        await forward_to_monitor(
            context,
            f"{base_info}: {message.caption if message.caption else '[Video]'}",
            video=message.video.file_id
        )
    elif message.audio:
        await forward_to_monitor(
            context,
            f"{base_info}: {message.caption if message.caption else '[Audio]'}",
            audio=message.audio.file_id
        )
    elif message.voice:
        await forward_to_monitor(
            context,
            f"{base_info}: {message.caption if message.caption else '[Nota de voz]'}",
            voice=message.voice.file_id
        )
    elif message.sticker:
        await forward_to_monitor(
            context,
            f"{base_info}: [Sticker]",
            sticker=message.sticker.file_id
        )
    else:
        await forward_to_monitor(context, f"{base_info}: [Contenido no reconocido]")

    return True

def main():
    try:
        # Crear la aplicación con job queue habilitado
        application = Application.builder().token(TOKEN).build()
        
        # Verificar que el job queue esté disponible
        job_queue = application.job_queue
        if job_queue is None:
            logger.error("JobQueue no está disponible")
            # Continuar sin las funciones programadas
            print("⚠️ Advertencia: Las tareas programadas no estarán disponibles")
            print("🚀 Bot iniciando...")
            
            # Crear un handler especial para enviar el mensaje de inicio
            async def post_init(application):
                await send_startup_message_direct(application.bot)
            
            application.post_init = post_init
            
        else:
            # Programar mensaje de inicio (se ejecuta una vez al iniciar)
            job_queue.run_once(send_startup_message, when=1)
            
            # Programar reporte de grupos cada 2 días a las 2 PM
            # Usar timezone de España (puedes cambiar según tu zona horaria)
            spain_tz = pytz.timezone('Europe/Madrid')
            
            # Calcular el próximo momento para las 2 PM
            now = datetime.now(spain_tz)
            next_2pm = now.replace(hour=14, minute=0, second=0, microsecond=0)
            
            # Si ya pasaron las 2 PM de hoy, programar para mañana
            if now.hour >= 14:
                next_2pm += timedelta(days=1)
            
            # Programar para que se ejecute cada 2 días a las 2 PM
            job_queue.run_repeating(
                send_groups_report,
                interval=timedelta(days=2),
                first=next_2pm,
                name='groups_report_every_2_days'
            )
            
            print("🚀 Bot iniciando...")
            print("📅 Reporte de grupos programado cada 2 días a las 2:00 PM")
        
        # Handlers (mantener el mismo orden)
        application.add_handler(MessageHandler(
            (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP) & ~filters.COMMAND,
            process_group_message
        ), group=1)
        
        application.add_handler(MessageHandler(
            filters.ChatType.CHANNEL,
            process_channel_message
        ), group=1)
        
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                TITULO: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, recibir_titulo)],
                IMAGEN: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, recibir_imagen)],
                ENLACE: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, recibir_enlace)]
            },
            fallbacks=[CommandHandler('cancelar', cancelar)]
        )
        
        application.add_handler(conv_handler, group=1)
        application.add_handler(CommandHandler("iniciar", iniciar_comando), group=1)
        application.add_handler(CommandHandler("cancelar", cancelar_comando), group=1)
        
        # Monitor con prioridad más baja
        application.add_handler(MessageHandler(
            ~filters.Chat(chat_id=int(MONITOR_GROUP_ID)),
            monitor_all_messages
        ), group=2)
        
        print("🚀 Bot iniciando...")
        print("📅 Reporte de grupos programado cada 2 días a las 2:00 PM")
        
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Error crítico del bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
