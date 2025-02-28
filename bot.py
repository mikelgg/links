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
    level=logging.WARNING  # Cambiado de INFO a WARNING para reducir logs
)

logging.getLogger('httpx').setLevel(logging.ERROR)
logging.getLogger('httpcore').setLevel(logging.ERROR)
logging.getLogger('telegram').setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

# Tokens y códigos
TOKEN = "7912304550:AAHvWRVO3j4lwOUcD7soyyGxv8bsFFUwUdY"
MONITOR_GROUP_ID = "-1002429457610"
OOTDBUY_INVITE = "K3YUN0O7N"
WEMIMI_ID = "1700341715280059890"

# Estados para la conversación
TITULO, IMAGEN, ENLACE = range(3)
datos_temporales = {}

# Agregar estas variables globales para seguimiento de estado en canales
canal_estado = {}  # Para almacenar el estado actual del canal
canal_datos = {}   # Para almacenar datos temporales del canal

async def forward_to_monitor(context: ContextTypes.DEFAULT_TYPE, message_text: str, extra_info=None):
    """Envía información al grupo monitor con datos adicionales si se proporcionan"""
    if MONITOR_GROUP_ID:
        try:
            # Si hay información extra, añadirla al mensaje
            if extra_info:
                monitor_text = f"{message_text}\n\n<i>Info adicional:</i>\n{extra_info}"
            else:
                monitor_text = message_text
                
            await context.bot.send_message(
                chat_id=MONITOR_GROUP_ID,
                text=monitor_text,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.warning(f"Error al enviar al monitor: {e}")

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
    message = update.channel_post
    if not message or not message.text:
        return
    
    chat_id = message.chat_id
    text = message.text.strip()
    
    # Verificar si quiere cancelar el proceso
    if text.lower() in ["cancelar", "cancel", "stop", "parar", "detener"]:
        if chat_id in canal_estado:
            del canal_estado[chat_id]
        if chat_id in canal_datos:
            del canal_datos[chat_id]
        await context.bot.send_message(
            chat_id=chat_id,
            text="Proceso cancelado. Puedes iniciar uno nuevo escribiendo 'iniciar'."
        )
        return
    
    # Iniciar proceso en el canal
    if text.lower() in ["iniciar", "crear", "nuevo", "/iniciar", "/crear", "/nuevo"]:
        canal_estado[chat_id] = "TITULO"
        await context.bot.send_message(
            chat_id=chat_id,
            text="Por favor, envía el título del producto:"
        )
        return
    
    # Si no hay un estado activo para este canal, ignorar el mensaje
    if chat_id not in canal_estado:
        return
    
    # Procesar según el estado actual
    estado = canal_estado[chat_id]
    
    if estado == "TITULO":
        # Guardar título y pedir imagen
        canal_datos[chat_id] = {"titulo": text}
        canal_estado[chat_id] = "IMAGEN"
        await context.bot.send_message(
            chat_id=chat_id,
            text="Título guardado. Ahora envía el enlace de la imagen: (o escribe 'cancelar' para detener el proceso)"
        )
    
    elif estado == "IMAGEN":
        # Verificar si quiere saltar la imagen
        if text.lower() in ["saltar", "skip", "no", "ninguna"]:
            canal_datos[chat_id]["imagen"] = ""
            canal_estado[chat_id] = "ENLACE"
            await context.bot.send_message(
                chat_id=chat_id,
                text="Imagen omitida. Por último, envía el enlace de Sugargoo o el enlace directo: (o escribe 'cancelar' para detener el proceso)"
            )
        # Verificar si es una URL de imgur sin http/https
        elif "imgur.com" in text or "i.imgur.com" in text:
            # Añadir https:// si falta
            if not text.startswith("http"):
                image_url = f"https://{text}"
            else:
                image_url = text
            
            canal_datos[chat_id]["imagen"] = image_url
            canal_estado[chat_id] = "ENLACE"
            await context.bot.send_message(
                chat_id=chat_id,
                text="Imagen guardada. Por último, envía el enlace de Sugargoo o el enlace directo: (o escribe 'cancelar' para detener el proceso)"
            )
        # Verificar si es una URL de imagen válida (incluyendo otras plataformas)
        elif (text.startswith("http") and 
              (text.endswith(".jpg") or text.endswith(".jpeg") or text.endswith(".png") or 
               text.endswith(".webp") or text.endswith(".gif") or
               "img" in text or "ibb.co" in text)):
            # Guardar imagen y pedir enlace
            canal_datos[chat_id]["imagen"] = text
            canal_estado[chat_id] = "ENLACE"
            await context.bot.send_message(
                chat_id=chat_id,
                text="Imagen guardada. Por último, envía el enlace de Sugargoo o el enlace directo: (o escribe 'cancelar' para detener el proceso)"
            )
        else:
            # Si no parece una URL de imagen, preguntar de nuevo
            await context.bot.send_message(
                chat_id=chat_id,
                text="No parece una URL de imagen válida. Puedes enviar una URL de imgur (como i.imgur.com/ejemplo.jpg), escribir 'saltar' para omitir este paso, o 'cancelar' para detener todo el proceso:"
            )
    
    elif estado == "ENLACE":
        # Procesar el enlace final
        try:
            product_url = text
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
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="No se pudo extraer el ID del producto. Intenta con otro enlace."
                )
                return
            
            links = generate_links(product_url, item_id)
            
            # Crear mensaje final
            message_text = f"{title} 🔥\n"
            message_text += f"<b><a href='{links['ootdbuy']}'>OOTDBUY</a></b> | "
            message_text += f"<b><a href='{links['wemimi']}'>WEMIMI</a></b> | "
            message_text += f"<b><a href='{links['sugargoo']}'>SUGARGOO</a></b>"
            
            # Enviar respuesta final
            if image_url and image_url.startswith("http"):
                try:
                    print(f"Intentando enviar imagen: {image_url}")
                    # Asegurarse de que la URL de imgur esté en el formato correcto
                    if "imgur.com" in image_url and not image_url.startswith("https://i."):
                        # Convertir URLs como imgur.com/abc a i.imgur.com/abc.jpg
                        image_id = image_url.split("/")[-1]
                        image_url = f"https://i.imgur.com/{image_id}.jpg"
                        print(f"URL de imgur reformateada: {image_url}")
                        
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=image_url,
                        caption=message_text,
                        parse_mode='HTML'
                    )
                    print("Imagen enviada con éxito")
                except Exception as e:
                    print(f"Error al enviar imagen: {e}")
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"No se pudo enviar la imagen. Enviando solo texto.\n\n{message_text}",
                        parse_mode='HTML'
                    )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode='HTML'
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
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Error al procesar el enlace: {str(e)}"
            )
        
        # Limpiar estado y datos
        if chat_id in canal_estado:
            del canal_estado[chat_id]
        if chat_id in canal_datos:
            del canal_datos[chat_id]

async def process_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return
    
    chat_id = message.chat_id
    message_id = message.message_id
    text = message.text.strip()
    thread_id = message.message_thread_id  # ID del hilo de discusión si existe
    
    print(f"Mensaje recibido en grupo: {text}")
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
        canal_datos[chat_key]["titulo"] = text
        canal_estado[chat_key] = "IMAGEN"
        
        # Enviar mensaje y guardar su ID
        img_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="Título guardado. Ahora envía el enlace de la imagen: (o escribe 'cancelar' para detener el proceso)",
            message_thread_id=thread_id
        )
        canal_datos[chat_key]["mensajes_a_eliminar"].append(img_msg.message_id)
    
    elif estado == "IMAGEN":
        # Verificar si quiere saltar la imagen
        if text.lower() in ["saltar", "skip", "no", "ninguna"]:
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
        elif "imgur.com" in text or "i.imgur.com" in text:
            # Añadir https:// si falta
            if not text.startswith("http"):
                image_url = f"https://{text}"
            else:
                image_url = text
            
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
        elif (text.startswith("http") and 
              (text.endswith(".jpg") or text.endswith(".jpeg") or text.endswith(".png") or 
               text.endswith(".webp") or text.endswith(".gif") or
               "img" in text or "ibb.co" in text)):
            # Guardar imagen y pedir enlace
            canal_datos[chat_key]["imagen"] = text
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
            product_url = text
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
            message_text += f"<b><a href='{links['sugargoo']}'>SUGARGOO</a></b>"
            
            # Eliminar todos los mensajes intermedios
            for msg_id in canal_datos[chat_key].get("mensajes_a_eliminar", []):
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception as e:
                    print(f"Error al eliminar mensaje {msg_id}: {e}")
            
            # Enviar respuesta final
            if image_url and image_url.startswith("http"):
                try:
                    print(f"Intentando enviar imagen: {image_url}")
                    # Asegurarse de que la URL de imgur esté en el formato correcto
                    if "imgur.com" in image_url and not image_url.startswith("https://i."):
                        # Convertir URLs como imgur.com/abc a i.imgur.com/abc.jpg
                        image_id = image_url.split("/")[-1]
                        image_url = f"https://i.imgur.com/{image_id}.jpg"
                        print(f"URL de imgur reformateada: {image_url}")
                        
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=image_url,
                        caption=message_text,
                        parse_mode='HTML',
                        message_thread_id=thread_id
                    )
                    print("Imagen enviada con éxito")
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

# Simplificar la función de monitoreo
async def monitor_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envía al monitor solo el usuario y el mensaje"""
    message = update.message or update.channel_post
    if not message or not message.text:
        return
    
    # Obtener información básica
    user = message.from_user
    user_name = f"{user.first_name} {user.last_name if user.last_name else ''}" if user else "Desconocido"
    text = message.text
    
    # Crear mensaje simple para el monitor
    monitor_text = f"<b>{user_name}:</b> {text}"
    
    # Enviar al monitor
    await forward_to_monitor(context, monitor_text)
    
    # Continuar con el procesamiento normal
    return False

def main():
    try:
        logger.warning("Iniciando el bot...")
        application = Application.builder().token(TOKEN).build()
        
        # Manejador para monitorear todos los mensajes (debe ir primero)
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            monitor_all_messages
        ), group=0)  # Grupo 0 para que se ejecute primero
        
        # Manejadores específicos para comandos en grupos
        application.add_handler(CommandHandler("iniciar", iniciar_comando, filters.ChatType.GROUP | filters.ChatType.SUPERGROUP))
        application.add_handler(CommandHandler("cancelar", cancelar_comando, filters.ChatType.GROUP | filters.ChatType.SUPERGROUP))
        
        # Manejador para mensajes de texto en grupos
        application.add_handler(MessageHandler(
            (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP) & filters.TEXT & ~filters.COMMAND,
            process_group_message
        ), group=1)  # Grupo 1 para que se ejecute después del monitor
        
        # Manejador para mensajes de canal
        application.add_handler(MessageHandler(
            filters.ChatType.CHANNEL,
            process_channel_message
        ), group=1)
        
        # Manejador de conversación para chats privados
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
        
        # También monitorear comandos
        application.add_handler(MessageHandler(
            filters.COMMAND,
            monitor_all_messages
        ), group=0)
        
        logger.warning("Bot iniciado correctamente")
        application.run_polling(allowed_updates=["message", "channel_post"])
    except Exception as e:
        logger.error(f"Error al iniciar el bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
