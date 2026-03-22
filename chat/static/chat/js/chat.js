let currentConversationId = null;
let isProcessing = false;
let selectedAdapters = ['business'];

const ADAPTER_INFO = {
    business: {
        icon: '💼',
        short: 'Бизнес',
        name: 'Бизнес-консультант',
        hint: 'Стратегия, рост и решения',
        dative: 'в режиме бизнес-консультанта',
    },
    legal: {
        icon: '⚖️',
        short: 'Юрист',
        name: 'Юридический консультант',
        hint: 'Риски, договоры и право',
        dative: 'в режиме юридического консультанта',
    },
    psych: {
        icon: '🧠',
        short: 'Психолог',
        name: 'Предпринимательский психолог',
        hint: 'Стресс, мотивация и фокус',
        dative: 'в режиме предпринимательского психолога',
    },
};

const ADAPTER_ORDER = ['business', 'legal', 'psych'];
const LEGACY_CONSULTANT_TO_ADAPTERS = {
    business: ['business'],
    legal: ['legal'],
    psych: ['psych'],
    hybrid: ['business', 'legal'],
    custom: ['business'],
};

/** Читает значение cookie по имени. Используется для получения CSRF-токена. */
function getCookie(name) {
    const cookies = document.cookie ? document.cookie.split(';') : [];
    for (const cookie of cookies) {
        const trimmed = cookie.trim();
        if (trimmed.startsWith(name + '=')) {
            return decodeURIComponent(trimmed.slice(name.length + 1));
        }
    }
    return '';
}

const csrfToken = getCookie('csrftoken');

/** Экранирует HTML-спецсимволы для безопасной вставки в DOM. */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(text == null ? '' : String(text)));
    return div.innerHTML;
}

/**
 * Приводит список адаптеров к каноническому виду: принимает массив, строку или JSON.
 * Убирает дубли и неизвестные ключи, сортирует в порядке ADAPTER_ORDER.
 * Если список пуст — определяет адаптеры по полю consultant.
 */
function normalizeAdapters(adapters, consultant = 'business') {
    let parsed = adapters;

    if (typeof parsed === 'string') {
        try {
            parsed = JSON.parse(parsed);
        } catch (error) {
            parsed = parsed.split(',').map((item) => item.trim()).filter(Boolean);
        }
    }

    if (!Array.isArray(parsed)) {
        parsed = [];
    }

    const normalized = [];
    const seen = new Set();

    for (const adapter of parsed) {
        const key = String(adapter).trim().toLowerCase();
        if (ADAPTER_INFO[key] && !seen.has(key)) {
            normalized.push(key);
            seen.add(key);
        }
    }

    if (normalized.length) {
        return normalized.sort((a, b) => ADAPTER_ORDER.indexOf(a) - ADAPTER_ORDER.indexOf(b));
    }

    return [...(LEGACY_CONSULTANT_TO_ADAPTERS[consultant] || ['business'])];
}

/** Определяет тип консультанта по набору активных адаптеров (для отправки на сервер). */
function adaptersToConsultant(adapters) {
    const normalized = normalizeAdapters(adapters);
    if (normalized.length === 1) {
        return normalized[0];
    }
    if (normalized.length === 2 && normalized[0] === 'business' && normalized[1] === 'legal') {
        return 'hybrid';
    }
    return 'custom';
}

/** Возвращает метаданные (иконку, название, подсказку) для отображения в шапке чата. */
function getHeaderInfo(adapters) {
    const normalized = normalizeAdapters(adapters);

    if (normalized.length === 1) {
        return ADAPTER_INFO[normalized[0]];
    }

    return {
        icon: '🤝',
        short: 'Гибрид',
        name: normalized.map((adapter) => ADAPTER_INFO[adapter].short).join(' + '),
        hint: normalized.map((adapter) => ADAPTER_INFO[adapter].hint).join(' • '),
        dative: 'в гибридном режиме',
    };
}

function getConversationAdaptersFromData(data) {
    return normalizeAdapters(data.selected_adapters, data.consultant);
}

function getConversationAdaptersFromElement(element) {
    return normalizeAdapters(element.dataset.adapters, element.dataset.consultant);
}

function updateChatHeader(adapters) {
    const info = getHeaderInfo(adapters);
    const iconEl = document.getElementById('chat-consultant-icon');
    const nameEl = document.getElementById('chat-consultant-name');

    if (iconEl) iconEl.textContent = info.icon;
    if (nameEl) nameEl.textContent = info.name;
}

function updateAdapterSummary(adapters) {
    const normalized = normalizeAdapters(adapters);
    const badge = document.getElementById('adapter-count-badge');
    const summary = document.getElementById('consultant-selector-summary');
    const hints = document.getElementById('consultant-selector-hints');

    if (badge) {
        badge.textContent = `${normalized.length} / ${ADAPTER_ORDER.length}`;
    }

    if (summary) {
        summary.textContent = `Выбрано: ${normalized.map((adapter) => ADAPTER_INFO[adapter].short).join(', ')}`;
    }

    if (hints) {
        hints.textContent = normalized.map((adapter) => ADAPTER_INFO[adapter].hint).join(' • ');
    }
}

/**
 * Устанавливает активные адаптеры: обновляет состояние кнопок и сводку.
 * @param {boolean} silent — если true, не перерисовывает шапку чата.
 */
function setSelectedAdapters(adapters, silent = false) {
    selectedAdapters = normalizeAdapters(adapters);

    document.querySelectorAll('.consultant-btn').forEach((button) => {
        const isActive = selectedAdapters.includes(button.dataset.adapter);
        button.classList.toggle('active', isActive);
        button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });

    updateAdapterSummary(selectedAdapters);

    if (!silent) {
        updateChatHeader(selectedAdapters);
    }
}

/** Включает или выключает адаптер по клику на кнопку. Минимум один адаптер всегда активен. */
function toggleAdapter(adapterKey) {
    const key = String(adapterKey).trim().toLowerCase();
    if (!ADAPTER_INFO[key]) {
        return;
    }

    if (selectedAdapters.includes(key)) {
        if (selectedAdapters.length === 1) {
            showError('Хотя бы один адаптер должен оставаться активным.');
            return;
        }
        setSelectedAdapters(selectedAdapters.filter((adapter) => adapter !== key));
        return;
    }

    setSelectedAdapters([...selectedAdapters, key]);
}

function scrollToBottom() {
    const container = document.getElementById('chat-container');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

/**
 * Рендерит текст ответа ассистента в HTML через marked.js.
 * Перед парсингом экранирует < и > чтобы модель не могла внедрить HTML-теги.
 */
function renderAssistantMarkdown(text) {
    const safeSource = String(text || '')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    if (typeof marked !== 'undefined') {
        return marked.parse(safeSource, {
            breaks: true,
            gfm: true,
        });
    }

    return safeSource.replace(/\n/g, '<br>');
}

/**
 * Добавляет сообщение в чат. Ответы ассистента рендерятся как markdown,
 * сообщения пользователя — как plain text.
 */
function addMessage(text, role, scroll = true) {
    const container = document.getElementById('chat-container');
    const welcomeMsg = container.querySelector('.welcome-message');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    if (role === 'assistant') {
        messageDiv.innerHTML = renderAssistantMarkdown(text);
    } else {
        messageDiv.textContent = text;
    }

    container.appendChild(messageDiv);

    if (scroll) {
        scrollToBottom();
    }

    return messageDiv;
}

/** Добавляет в чат анимированный индикатор печати (три точки) пока идёт запрос. */
function addLoadingMessage() {
    const container = document.getElementById('chat-container');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant loading';

    const indicator = document.createElement('div');
    indicator.className = 'typing-indicator';

    for (let i = 0; i < 3; i += 1) {
        const dot = document.createElement('div');
        dot.className = 'typing-dot';
        indicator.appendChild(dot);
    }

    messageDiv.appendChild(indicator);
    container.appendChild(messageDiv);
    scrollToBottom();
    return messageDiv;
}

/** Обновляет счётчик и прогресс-бар расхода токенов в шапке. */
function updateTokenDisplay(tokensRemaining) {
    tokensUsed = TOKENS_LIMIT - tokensRemaining;
    const percent = Math.min(100, Math.round((tokensUsed / TOKENS_LIMIT) * 100));

    const display = document.getElementById('tokens-display');
    const bar = document.getElementById('tokens-bar');

    if (display) {
        display.textContent = `${tokensUsed.toLocaleString('ru')} / ${TOKENS_LIMIT.toLocaleString('ru')}`;
    }

    if (bar) {
        bar.style.width = `${percent}%`;
    }
}

/** Показывает всплывающее уведомление об ошибке (исчезает через 4 секунды). */
function showError(message) {
    const existing = document.querySelector('.error-toast');
    if (existing) {
        existing.remove();
    }

    const toast = document.createElement('div');
    toast.className = 'error-toast';
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideInRight 0.3s ease-out reverse';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function setActiveConversation(conversationId) {
    document.querySelectorAll('.conversation-item').forEach((item) => {
        item.classList.toggle('active', item.dataset.id === String(conversationId));
    });
}

function buildWelcomeMessage(title, adapters) {
    const info = getHeaderInfo(adapters);
    return `
        <div class="welcome-message">
            <h2>${escapeHtml(title)}</h2>
            <p>Задайте вопрос ${escapeHtml(info.dative)}.</p>
        </div>
    `;
}

function newConversation() {
    if (isProcessing) {
        return;
    }

    currentConversationId = null;
    setActiveConversation(null);
    updateChatHeader(selectedAdapters);

    const container = document.getElementById('chat-container');
    container.innerHTML = buildWelcomeMessage('Новый чат', selectedAdapters);

    const input = document.getElementById('user-input');
    if (input) {
        input.focus();
    }
}

async function loadConversation(conversationId) {
    if (isProcessing || currentConversationId === conversationId) {
        return;
    }

    currentConversationId = conversationId;
    setActiveConversation(conversationId);

    const container = document.getElementById('chat-container');
    container.innerHTML = '<div class="loading-chat">Загрузка...</div>';

    try {
        const response = await fetch(`/conversations/${conversationId}/`);
        const data = await response.json();

        const adapters = getConversationAdaptersFromData(data);
        setSelectedAdapters(adapters);
        container.innerHTML = '';

        if (Array.isArray(data.messages) && data.messages.length > 0) {
            for (const msg of data.messages) {
                addMessage(msg.content, msg.role, false);
            }
            scrollToBottom();
        } else {
            container.innerHTML = buildWelcomeMessage(data.title || 'Новый чат', adapters);
        }
    } catch (error) {
        container.innerHTML = '<div class="loading-chat">Ошибка загрузки чата</div>';
        console.error(error);
    }
}

/**
 * Добавляет или обновляет элемент диалога в боковом списке.
 * Если диалог уже есть — перемещает его в начало списка.
 */
function addConversationToSidebar(id, title, consultant, adapters) {
    const list = document.getElementById('conversations-list');
    const normalizedAdapters = normalizeAdapters(adapters, consultant);
    const info = getHeaderInfo(normalizedAdapters);

    const existing = list.querySelector(`[data-id="${id}"]`);
    if (existing) {
        existing.dataset.consultant = consultant || adaptersToConsultant(normalizedAdapters);
        existing.dataset.adapters = JSON.stringify(normalizedAdapters);
        existing.querySelector('.conv-title').textContent = title;
        existing.querySelector('.conv-icon').textContent = info.icon;
        list.insertBefore(existing, list.firstChild);
        return;
    }

    const item = document.createElement('div');
    item.className = 'conversation-item';
    item.dataset.id = String(id);
    item.dataset.consultant = consultant || adaptersToConsultant(normalizedAdapters);
    item.dataset.adapters = JSON.stringify(normalizedAdapters);
    item.onclick = () => loadConversation(id);
    item.innerHTML = `
        <span class="conv-icon">${info.icon}</span>
        <span class="conv-title">${escapeHtml(title)}</span>
        <button type="button" class="conv-delete" onclick="deleteConversation(event, ${id})" title="Удалить">×</button>
    `;
    list.insertBefore(item, list.firstChild);
}

/** Удаляет диалог после подтверждения. Если диалог был активным — открывает новый чат. */
async function deleteConversation(event, conversationId) {
    event.stopPropagation();

    if (!confirm('Удалить этот чат?')) {
        return;
    }

    try {
        const response = await fetch(`/conversations/${conversationId}/delete/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
        });

        const data = await response.json();

        if (data.status === 'ok') {
            const item = document.querySelector(`.conversation-item[data-id="${conversationId}"]`);
            if (item) {
                item.remove();
            }

            if (currentConversationId === conversationId) {
                newConversation();
            }
        } else {
            showError(data.error || 'Не удалось удалить чат');
        }
    } catch (error) {
        console.error(error);
        showError('Не удалось удалить чат');
    }
}

/**
 * Отправляет сообщение на /stream/ и читает SSE-поток токенов.
 * Во время генерации рендерит markdown через requestAnimationFrame (scheduleRender).
 * По завершении потока ([DONE]) обновляет сайдбар и счётчик токенов.
 */
async function sendMessage() {
    if (isProcessing) {
        return;
    }

    const input = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const message = input.value.trim();

    if (!message) {
        showError('Пожалуйста, введите сообщение');
        return;
    }

    addMessage(message, 'user');
    input.value = '';
    autoResize(input);

    const loadingMsg = addLoadingMessage();
    sendBtn.disabled = true;
    isProcessing = true;

    let streamingDiv = null;
    let accumulatedText = '';

    try {
        const response = await fetch('/stream/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
            body: JSON.stringify({
                message,
                conversation_id: currentConversationId,
                consultant: adaptersToConsultant(selectedAdapters),
                adapters: selectedAdapters,
            }),
        });

        if (!response.ok) {
            loadingMsg.remove();
            try {
                const errData = await response.json();
                showError(errData.error || `Ошибка сервера: ${response.status}`);
            } catch {
                showError(`Ошибка сервера: ${response.status}`);
            }
            return;
        }

        loadingMsg.remove();
        streamingDiv = document.createElement('div');
        streamingDiv.className = 'message assistant';
        document.getElementById('chat-container').appendChild(streamingDiv);
        scrollToBottom();

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        // Throttled рендеринг: перерисовываем markdown не чаще одного раза за кадр (60fps)
        let renderPending = false;
        const scheduleRender = () => {
            if (renderPending) return;
            renderPending = true;
            requestAnimationFrame(() => {
                streamingDiv.innerHTML = renderAssistantMarkdown(accumulatedText);
                scrollToBottom();
                renderPending = false;
            });
        };

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const payload = line.slice(6);

                if (payload.startsWith('[ERROR]')) {
                    let errMsg = 'Произошла ошибка';
                    try {
                        errMsg = JSON.parse(payload.slice(7)).error || errMsg;
                    } catch {}
                    streamingDiv.remove();
                    streamingDiv = null;
                    showError(errMsg);
                    break;
                }

                if (payload.startsWith('[DONE]')) {
                    let meta = {};
                    try { meta = JSON.parse(payload.slice(7)); } catch {}

                    // Финальный рендер (на случай если последний токен ещё не отрисован)
                    streamingDiv.innerHTML = renderAssistantMarkdown(accumulatedText);
                    renderPending = false;

                    if (meta.truncated) {
                        const notice = document.createElement('div');
                        notice.className = 'truncated-notice';
                        notice.textContent = '⚠️ Ответ обрезан — модель достигла лимита длины.';
                        streamingDiv.appendChild(notice);
                    }

                    const adapters = getConversationAdaptersFromData(meta);
                    if (meta.conversation_id && meta.conversation_id !== currentConversationId) {
                        currentConversationId = meta.conversation_id;
                    }

                    addConversationToSidebar(
                        meta.conversation_id,
                        meta.conversation_title,
                        meta.consultant,
                        adapters,
                    );
                    setActiveConversation(currentConversationId);
                    setSelectedAdapters(adapters, true);
                    updateChatHeader(adapters);
                    if (meta.tokens_remaining !== undefined) {
                        updateTokenDisplay(meta.tokens_remaining);
                    }
                    scrollToBottom();
                    break;
                }

                try {
                    const tokenData = JSON.parse(payload);
                    const token = tokenData.token || '';
                    if (token) {
                        accumulatedText += token;
                        scheduleRender();
                    }
                } catch {}
            }
        }
    } catch (error) {
        if (streamingDiv) streamingDiv.remove();
        else loadingMsg.remove();
        console.error(error);
        showError('Ошибка соединения. Проверьте, что Django и сервер модели запущены.');
    } finally {
        sendBtn.disabled = false;
        isProcessing = false;
        input.focus();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('user-input');
    const selector = document.getElementById('consultant-selector');

    document.querySelectorAll('.conversation-item').forEach((item) => {
        item.dataset.adapters = JSON.stringify(getConversationAdaptersFromElement(item));
    });

    if (selector) {
        selector.addEventListener('click', (event) => {
            const button = event.target.closest('.consultant-btn');
            if (!button) {
                return;
            }

            event.preventDefault();
            toggleAdapter(button.dataset.adapter);
        });
    }

    const initialFromButtons = Array.from(document.querySelectorAll('.consultant-btn.active'))
        .map((button) => button.dataset.adapter);
    setSelectedAdapters(initialFromButtons.length ? initialFromButtons : ['business']);

    input.focus();
    input.addEventListener('input', function onInput() {
        autoResize(this);
    });
    input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    });
});

window.newConversation = newConversation;
window.loadConversation = loadConversation;
window.deleteConversation = deleteConversation;
window.sendMessage = sendMessage;
