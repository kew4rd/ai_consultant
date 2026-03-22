from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
import json


class UserProfile(models.Model):
    """Расширение стандартной модели User: хранит план подписки и дневной расход токенов."""

    PLAN_FREE = 'free'
    PLAN_PREMIUM = 'premium'
    PLAN_CHOICES = [
        (PLAN_FREE, 'Бесплатный'),
        (PLAN_PREMIUM, 'Премиум'),
    ]

    FREE_DAILY_TOKENS = 10000
    PREMIUM_DAILY_TOKENS = 100000

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    plan = models.CharField(max_length=10, choices=PLAN_CHOICES, default=PLAN_FREE)
    tokens_used_today = models.IntegerField(default=0)
    tokens_reset_date = models.DateField(default=timezone.now)

    def get_token_limit(self):
        """Возвращает дневной лимит токенов в зависимости от плана пользователя."""
        if self.plan == self.PLAN_PREMIUM:
            return self.PREMIUM_DAILY_TOKENS
        return self.FREE_DAILY_TOKENS

    def reset_tokens_if_needed(self):
        """Сбрасывает счётчик токенов если наступил новый день."""
        today = timezone.now().date()
        if self.tokens_reset_date < today:
            self.tokens_used_today = 0
            self.tokens_reset_date = today
            self.save(update_fields=['tokens_used_today', 'tokens_reset_date'])

    def can_send_message(self):
        """Проверяет, не исчерпан ли дневной лимит токенов."""
        self.reset_tokens_if_needed()
        return self.tokens_used_today < self.get_token_limit()

    def tokens_remaining(self):
        """Возвращает количество токенов, оставшихся на сегодня."""
        return max(0, self.get_token_limit() - self.tokens_used_today)

    def __str__(self):
        return f"{self.user.username} ({self.get_plan_display()})"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Автоматически создаёт UserProfile при регистрации нового пользователя."""
    if created:
        UserProfile.objects.create(user=instance)


class Conversation(models.Model):
    """Диалог пользователя с AI-консультантом. Хранит набор активных адаптеров и историю сообщений."""

    CONSULTANT_BUSINESS = 'business'
    CONSULTANT_LEGAL = 'legal'
    CONSULTANT_PSYCH = 'psych'
    CONSULTANT_HYBRID = 'hybrid'
    CONSULTANT_CUSTOM = 'custom'

    CONSULTANT_CHOICES = [
        (CONSULTANT_BUSINESS, 'Бизнес-консультант'),
        (CONSULTANT_LEGAL, 'Юридический консультант'),
        (CONSULTANT_PSYCH, 'Предпринимательский психолог'),
        (CONSULTANT_HYBRID, 'Бизнес + Юридический'),
        (CONSULTANT_CUSTOM, 'Кастомный гибрид'),
    ]

    # Метаданные адаптеров для отображения в интерфейсе
    ADAPTER_CATALOG = [
        {
            'key': CONSULTANT_BUSINESS,
            'label': 'Бизнес',
            'name': 'Бизнес-консультант',
            'icon': '💼',
            'hint': 'Стратегия, рост и решения',
        },
        {
            'key': CONSULTANT_LEGAL,
            'label': 'Юрист',
            'name': 'Юридический консультант',
            'icon': '⚖️',
            'hint': 'Риски, договоры и право',
        },
        {
            'key': CONSULTANT_PSYCH,
            'label': 'Психолог',
            'name': 'Предпринимательский психолог',
            'icon': '🧠',
            'hint': 'Стресс, мотивация и фокус',
        },
    ]
    SUPPORTED_ADAPTERS = [item['key'] for item in ADAPTER_CATALOG]
    LEGACY_CONSULTANT_TO_ADAPTERS = {
        CONSULTANT_BUSINESS: [CONSULTANT_BUSINESS],
        CONSULTANT_LEGAL: [CONSULTANT_LEGAL],
        CONSULTANT_PSYCH: [CONSULTANT_PSYCH],
        CONSULTANT_HYBRID: [CONSULTANT_BUSINESS, CONSULTANT_LEGAL],
        CONSULTANT_CUSTOM: [CONSULTANT_BUSINESS],
    }

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations')
    title = models.CharField(max_length=200, default='Новый чат')
    consultant = models.CharField(max_length=20, choices=CONSULTANT_CHOICES, default=CONSULTANT_BUSINESS)
    selected_adapters = models.TextField(default='["business"]', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    @classmethod
    def get_adapter_catalog(cls):
        """Возвращает список всех доступных адаптеров с их метаданными."""
        return cls.ADAPTER_CATALOG

    @classmethod
    def normalize_adapters(cls, adapters=None, consultant=None):
        """
        Приводит список адаптеров к каноническому виду: убирает дубли,
        фильтрует неизвестные ключи, возвращает хотя бы один адаптер.
        Если adapters пуст или None — определяет набор по полю consultant.
        """
        if isinstance(adapters, str):
            try:
                adapters = json.loads(adapters)
            except json.JSONDecodeError:
                adapters = [part.strip() for part in adapters.split(',') if part.strip()]

        if not adapters:
            adapters = cls.LEGACY_CONSULTANT_TO_ADAPTERS.get(consultant, [cls.CONSULTANT_BUSINESS])

        normalized = []
        seen = set()
        for adapter in adapters:
            if not isinstance(adapter, str):
                continue
            key = adapter.strip().lower()
            if key in cls.SUPPORTED_ADAPTERS and key not in seen:
                normalized.append(key)
                seen.add(key)

        return normalized or [cls.CONSULTANT_BUSINESS]

    @classmethod
    def adapters_to_consultant(cls, adapters):
        """Определяет тип консультанта по набору активных адаптеров."""
        normalized = cls.normalize_adapters(adapters)
        if len(normalized) == 1:
            return normalized[0]
        if normalized == [cls.CONSULTANT_BUSINESS, cls.CONSULTANT_LEGAL]:
            return cls.CONSULTANT_HYBRID
        return cls.CONSULTANT_CUSTOM

    def get_selected_adapters(self):
        """Возвращает нормализованный список активных адаптеров для этого диалога."""
        return self.normalize_adapters(self.selected_adapters, consultant=self.consultant)

    def set_selected_adapters(self, adapters):
        """Сохраняет список адаптеров и синхронизирует поле consultant."""
        normalized = self.normalize_adapters(adapters, consultant=self.consultant)
        self.selected_adapters = json.dumps(normalized, ensure_ascii=False)
        self.consultant = self.adapters_to_consultant(normalized)
        return normalized

    def __str__(self):
        return f"{self.title} ({self.user.username})"


class Message(models.Model):
    """Одно сообщение в диалоге. Роль — 'user' или 'assistant'."""

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    role = models.CharField(max_length=10)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."
