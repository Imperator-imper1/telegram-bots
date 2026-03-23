import io
import os
import tempfile
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FileProcessor:
    """Класс для обработки файлов: PDF, DOCX, TXT, OCR"""
    
    async def read_pdf(self, file_data: bytes) -> Optional[str]:
        """Читает текст из PDF файла"""
        try:
            import PyPDF2
            pdf_file = io.BytesIO(file_data)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            text = ""
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            
            if text.strip():
                logger.info(f"PDF прочитан, {len(text)} символов")
                return text.strip()
            else:
                return None
        except Exception as e:
            logger.error(f"Ошибка чтения PDF: {e}")
            return None
    
    async def read_docx(self, file_data: bytes) -> Optional[str]:
        """Читает текст из DOCX файла"""
        try:
            import docx
            docx_file = io.BytesIO(file_data)
            doc = docx.Document(docx_file)
            
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            
            if text.strip():
                logger.info(f"DOCX прочитан, {len(text)} символов")
                return text.strip()
            else:
                return None
        except Exception as e:
            logger.error(f"Ошибка чтения DOCX: {e}")
            return None
    
    async def read_txt(self, file_data: bytes) -> Optional[str]:
        """Читает текст из TXT файла"""
        try:
            text = file_data.decode('utf-8')
            if text.strip():
                logger.info(f"TXT прочитан, {len(text)} символов")
                return text.strip()
            else:
                return None
        except UnicodeDecodeError:
            try:
                text = file_data.decode('cp1251')
                if text.strip():
                    return text.strip()
            except:
                pass
            return None
        except Exception as e:
            logger.error(f"Ошибка чтения TXT: {e}")
            return None
    
    async def read_image_ocr(self, file_data: bytes) -> Optional[str]:
        """Извлекает текст из картинки (OCR)"""
        try:
            from PIL import Image
            import pytesseract
            
            # Сохраняем временно
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp.write(file_data)
                tmp_path = tmp.name
            
            # Открываем и распознаем
            image = Image.open(tmp_path)
            text = pytesseract.image_to_string(image, lang='rus+eng')
            
            # Удаляем временный файл
            os.unlink(tmp_path)
            
            if text.strip():
                logger.info(f"OCR распознано, {len(text)} символов")
                return text.strip()
            else:
                return None
        except Exception as e:
            logger.error(f"Ошибка OCR: {e}")
            return None
    
    async def process_file(self, file_data: bytes, file_name: str) -> dict:
        """Определяет тип файла и обрабатывает его"""
        file_ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
        
        result = {
            "success": False,
            "text": None,
            "error": None,
            "file_type": file_ext
        }
        
        if file_ext == 'pdf':
            text = await self.read_pdf(file_data)
            if text:
                result["success"] = True
                result["text"] = text
            else:
                result["error"] = "Не удалось прочитать PDF файл"
                
        elif file_ext in ['docx', 'doc']:
            text = await self.read_docx(file_data)
            if text:
                result["success"] = True
                result["text"] = text
            else:
                result["error"] = "Не удалось прочитать DOCX файл"
                
        elif file_ext == 'txt':
            text = await self.read_txt(file_data)
            if text:
                result["success"] = True
                result["text"] = text
            else:
                result["error"] = "Не удалось прочитать TXT файл"
                
        elif file_ext in ['png', 'jpg', 'jpeg', 'bmp', 'gif']:
            text = await self.read_image_ocr(file_data)
            if text:
                result["success"] = True
                result["text"] = text
            else:
                result["error"] = "Не удалось распознать текст на картинке"
                
        else:
            result["error"] = f"Неподдерживаемый формат: {file_ext}"
        
        return result

# Глобальный экземпляр
file_processor = FileProcessor()