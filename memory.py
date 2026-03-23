from collections import deque
from typing import Dict, List, Optional
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConversationMemory:
    """Класс для хранения истории диалогов"""
    
    def __init__(self, max_messages: int = 15):
        self.max_messages = max_messages
        self.memories: Dict[int, deque] = {}  # user_id -> deque of messages
        
    def add_message(self, user_id: int, role: str, content: str):
        """Добавляет сообщение в историю"""
        if user_id not in self.memories:
            self.memories[user_id] = deque(maxlen=self.max_messages)
        
        self.memories[user_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        logger.info(f"Добавлено сообщение для {user_id}, всего: {len(self.memories[user_id])}")
    
    def get_history(self, user_id: int) -> List[Dict]:
        """Возвращает историю сообщений"""
        if user_id not in self.memories:
            return []
        
        # Возвращаем только role и content (без timestamp)
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.memories[user_id]
        ]
    
    def clear_history(self, user_id: int):
        """Очищает историю пользователя"""
        if user_id in self.memories:
            self.memories[user_id].clear()
            logger.info(f"История очищена для {user_id}")
    
    def get_stats(self, user_id: int) -> Dict:
        """Статистика по истории"""
        if user_id not in self.memories:
            return {"count": 0, "max": self.max_messages}
        
        return {
            "count": len(self.memories[user_id]),
            "max": self.max_messages,
            "oldest": self.memories[user_id][0]["timestamp"] if self.memories[user_id] else None,
            "newest": self.memories[user_id][-1]["timestamp"] if self.memories[user_id] else None
        }

# Глобальный экземпляр
conversation_memory = ConversationMemory(max_messages=15)