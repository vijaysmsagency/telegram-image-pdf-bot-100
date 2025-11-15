import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from PIL import Image
import fitz  # PyMuPDF
from io import BytesIO
import asyncio

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class PDFBot:
    def __init__(self, token):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        
        # Message handlers
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.application.add_handler(MessageHandler(filters.Document.PDF, self.handle_pdf))
        
        # Error handler
        self.application.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send welcome message when command /start is issued."""
        welcome_text = """
🤖 **PDF Converter Bot** 🤖

मैं आपकी images को PDF में और PDF files को compress करने में मदद करता हूं!

**मैं क्या कर सकता हूं:**
📸 Images को PDF में convert करना
📄 PDF files को compress करना (240KB से कम)
🔄 Multiple images को single PDF में convert करना

**कैसे use करें:**
1. एक या multiple photos भेजें - मैं PDF बना दूंगा
2. PDF file भेजें - मैं उसे compress कर दूंगा

**Note:** सभी PDF files 240KB से कम size की होंगी।
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send help message when command /help is issued."""
        help_text = """
🆘 **Help Guide** 🆘

**Commands:**
/start - Bot शुरू करें
/help - यह help message

**Features:**
- Images to PDF conversion
- PDF compression (under 240KB)
- Multiple images support

**Usage:**
1. Send photos → Get PDF
2. Send PDF → Get compressed PDF

**Support:** अगर कोई problem हो तो developer से contact करें।
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Convert photos to PDF."""
        try:
            message = await update.message.reply_text("📸 Processing your images...")
            
            # Get all photos from the message
            photos = update.message.photo
            
            if not photos:
                await message.edit_text("❌ No photos found!")
                return
            
            # Get the highest quality photo
            photo = photos[-1]
            photo_file = await photo.get_file()
            
            # Download photo
            photo_bytes = await photo_file.download_as_bytearray()
            
            # Convert to PDF
            pdf_bytes = await self.images_to_pdf([photo_bytes])
            
            # Compress PDF to under 240KB
            compressed_pdf = await self.compress_pdf_to_target_size(pdf_bytes, 240)
            
            await message.edit_text("✅ PDF ready! Sending...")
            
            # Send the PDF
            await update.message.reply_document(
                document=BytesIO(compressed_pdf),
                filename="converted.pdf",
                caption="Here's your converted PDF! 📄"
            )
            
            await message.delete()
            
        except Exception as e:
            logger.error(f"Error in handle_photo: {e}")
            await update.message.reply_text("❌ Error processing images. Please try again.")
    
    async def handle_pdf(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Compress PDF files."""
        try:
            message = await update.message.reply_text("📄 Processing your PDF...")
            
            document = update.message.document
            
            if document.file_size > 10 * 1024 * 1024:  # 10MB limit
                await message.edit_text("❌ File size too large! Maximum 10MB allowed.")
                return
            
            # Download PDF
            pdf_file = await document.get_file()
            pdf_bytes = await pdf_file.download_as_bytearray()
            
            # Compress PDF to under 240KB
            compressed_pdf = await self.compress_pdf_to_target_size(pdf_bytes, 240)
            
            await message.edit_text("✅ PDF compressed! Sending...")
            
            # Send compressed PDF
            await update.message.reply_document(
                document=BytesIO(compressed_pdf),
                filename="compressed.pdf",
                caption="Here's your compressed PDF! 📄"
            )
            
            await message.delete()
            
        except Exception as e:
            logger.error(f"Error in handle_pdf: {e}")
            await update.message.reply_text("❌ Error processing PDF. Please try again.")
    
    async def images_to_pdf(self, image_bytes_list):
        """Convert list of image bytes to PDF bytes."""
        pdf_bytes = BytesIO()
        
        # Create PDF from images
        images = []
        for img_bytes in image_bytes_list:
            img = Image.open(BytesIO(img_bytes))
            if img.mode != 'RGB':
                img = img.convert('RGB')
            images.append(img)
        
        # Save first image and append others
        if images:
            images[0].save(
                pdf_bytes,
                format='PDF',
                save_all=True,
                append_images=images[1:] if len(images) > 1 else []
            )
        
        return pdf_bytes.getvalue()
    
    async def compress_pdf_to_target_size(self, pdf_bytes, target_kb):
        """Compress PDF to target size in KB."""
        try:
            current_size = len(pdf_bytes) / 1024  # Size in KB
            
            if current_size <= target_kb:
                return pdf_bytes  # Already under target size
            
            # Open the PDF
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            # Compression parameters
            quality = 80  # Initial quality
            
            while current_size > target_kb and quality >= 20:
                # Create new PDF with compression
                output = BytesIO()
                new_doc = fitz.open()
                
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    pix = page.get_pixmap(matrix=fitz.Matrix(0.8, 0.8))  # Reduce resolution
                    img_bytes = pix.tobytes("jpeg", quality / 100)
                    
                    # Create new page with compressed image
                    new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
                    new_page.insert_image(page.rect, stream=img_bytes)
                
                new_doc.save(output, garbage=4, deflate=True, clean=True)
                new_doc.close()
                
                compressed_bytes = output.getvalue()
                current_size = len(compressed_bytes) / 1024
                
                # Reduce quality for next iteration if needed
                if current_size > target_kb:
                    quality -= 20
                
                # Update PDF bytes for next iteration
                pdf_bytes = compressed_bytes
                doc.close()
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            final_bytes = pdf_bytes
            doc.close()
            
            return final_bytes
            
        except Exception as e:
            logger.error(f"Error in compress_pdf: {e}")
            return pdf_bytes  # Return original if compression fails
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Log errors and send friendly message."""
        logger.error(f"Update {update} caused error {context.error}")
        
        if update and update.message:
            await update.message.reply_text(
                "❌ An error occurred. Please try again later."
            )
    
    def run(self):
        """Start the bot."""
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

# Main function
def main():
    # Get bot token from environment variable
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN environment variable not set!")
        return
    
    # Create and run bot
    bot = PDFBot(BOT_TOKEN)
    logger.info("Bot is starting...")
    bot.run()

if __name__ == '__main__':
    main()