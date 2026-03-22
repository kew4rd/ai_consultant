import json
import re

import requests
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .models import Conversation, Message


def _resolve_selected_adapters(data):
    """Извлекает и нормализует список адаптеров из тела запроса."""
    data = data or {}
    return Conversation.normalize_adapters(
        data.get('adapters'),
        consultant=data.get('consultant', Conversation.CONSULTANT_BUSINESS),
    )


def estimate_tokens_fallback(*parts: str) -> int:
    """
    Оценивает количество токенов по количеству слов (коэффициент 1.3).
    Используется как запасной вариант, если Flask не вернул точный счётчик.
    """
    text = ' '.join(part for part in parts if part)
    if not text:
        return 0
    words = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
    return max(1, int(len(words) * 1.3))


def clean_ai_response(text: str) -> str:
    """
    Очищает сырой вывод модели от служебных токенов и артефактов:
    блоков <think>, специальных токенов Qwen (<|im_start|> и др.),
    лишних переносов строк и префиксов роли.
    """
    if not text:
        return ''

    cleaned = str(text)
    cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r'</?think>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<\|im_start\|>assistant\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<\|im_end\|>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<\|endoftext\|>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<\|[^>]+\|>', '', cleaned)
    cleaned = re.sub(r'^\s*assistant\s*:\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def login_view(request):
    """Страница входа. Аутентифицирует пользователя и перенаправляет в чат."""
    if request.user.is_authenticated:
        return redirect('chat')

    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('chat')
        error = 'Неверное имя пользователя или пароль'

    return render(request, 'chat/login.html', {'error': error})


def register_view(request):
    """Страница регистрации. Создаёт пользователя и сразу авторизует его."""
    if request.user.is_authenticated:
        return redirect('chat')

    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')

        if not username or not password:
            error = 'Заполните все поля'
        elif password != password2:
            error = 'Пароли не совпадают'
        elif len(password) < 8:
            error = 'Пароль должен содержать минимум 8 символов'
        elif User.objects.filter(username=username).exists():
            error = 'Пользователь с таким именем уже существует'
        else:
            user = User.objects.create_user(username=username, password=password)
            login(request, user)
            return redirect('chat')

    return render(request, 'chat/register.html', {'error': error})


def logout_view(request):
    """Завершает сессию и перенаправляет на страницу входа."""
    logout(request)
    return redirect('login')


@login_required(login_url='/login/')
@ensure_csrf_cookie
def chat_view(request):
    """Главная страница чата. Передаёт в шаблон данные профиля и список диалогов."""
    profile = request.user.profile
    profile.reset_tokens_if_needed()
    tokens_limit = profile.get_token_limit()
    tokens_used = profile.tokens_used_today
    tokens_percent = min(100, round(tokens_used / tokens_limit * 100)) if tokens_limit > 0 else 0

    return render(request, 'chat/index.html', {
        'profile': profile,
        'conversations': request.user.conversations.all(),
        'available_adapters': Conversation.get_adapter_catalog(),
        'tokens_limit': tokens_limit,
        'tokens_used': tokens_used,
        'tokens_remaining': profile.tokens_remaining(),
        'tokens_percent': tokens_percent,
    })


@login_required(login_url='/login/')
@require_POST
def new_conversation(request):
    """Создаёт новый диалог с выбранным набором адаптеров."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        data = {}

    selected_adapters = _resolve_selected_adapters(data)
    conv = Conversation(user=request.user, title='Новый чат')
    conv.set_selected_adapters(selected_adapters)
    conv.save()

    return JsonResponse({
        'conversation_id': conv.id,
        'title': conv.title,
        'consultant': conv.consultant,
        'selected_adapters': conv.get_selected_adapters(),
        'status': 'success'
    })


@login_required(login_url='/login/')
def get_conversations(request):
    """Возвращает список всех диалогов текущего пользователя."""
    convs = []
    for conv in request.user.conversations.all():
        convs.append({
            'id': conv.id,
            'title': conv.title,
            'updated_at': conv.updated_at,
            'consultant': conv.consultant,
            'selected_adapters': conv.get_selected_adapters(),
        })
    return JsonResponse({'conversations': convs})


@login_required(login_url='/login/')
def get_conversation_messages(request, conversation_id):
    """Возвращает все сообщения указанного диалога вместе с его метаданными."""
    conv = get_object_or_404(Conversation, id=conversation_id, user=request.user)
    messages = list(conv.messages.values('role', 'content'))
    return JsonResponse({
        'messages': messages,
        'title': conv.title,
        'consultant': conv.consultant,
        'selected_adapters': conv.get_selected_adapters(),
        'status': 'success'
    })


@login_required(login_url='/login/')
@require_POST
def delete_conversation(request, conversation_id):
    """Удаляет диалог вместе со всеми его сообщениями."""
    conv = get_object_or_404(Conversation, id=conversation_id, user=request.user)
    conv.delete()
    return JsonResponse({'status': 'ok'})


@login_required(login_url='/login/')
@require_POST
def send_message(request):
    """
    Отправляет сообщение на Flask LLM-сервер и возвращает полный ответ одним JSON.
    Используется как запасной маршрут — основной способ общения через /stream/.
    Сохраняет оба сообщения (user + assistant) в БД и обновляет счётчик токенов.
    """
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')

        if not user_message:
            return JsonResponse({'error': 'Сообщение не может быть пустым', 'status': 'error'}, status=400)

        profile = request.user.profile
        if not profile.can_send_message():
            return JsonResponse({
                'error': f'Достигнут дневной лимит ({profile.get_token_limit():,} токенов). '
                         f'Обновите план до Премиум или подождите следующего дня.',
                'status': 'limit_exceeded'
            }, status=429)

        selected_adapters = _resolve_selected_adapters(data)

        if conversation_id:
            try:
                conversation = Conversation.objects.get(id=conversation_id, user=request.user)
            except Conversation.DoesNotExist:
                conversation = Conversation(user=request.user, title='Новый чат')
        else:
            conversation = Conversation(user=request.user, title='Новый чат')

        conversation.set_selected_adapters(selected_adapters)
        if conversation.pk is None:
            conversation.save()

        messages_qs = conversation.messages.order_by('timestamp')
        history = [{'role': m.role, 'content': m.content} for m in messages_qs]
        is_first_message = len(history) == 0

        Message.objects.create(conversation=conversation, role='user', content=user_message)

        if is_first_message:
            conversation.title = user_message[:60] + ('...' if len(user_message) > 60 else '')

        if not settings.MODEL_API_URL:
            return JsonResponse({
                'error': 'MODEL_API_URL не настроен. Укажи адрес сервера модели в .env.',
                'status': 'error'
            }, status=503)

        headers = {}
        if settings.MODEL_API_TOKEN:
            headers['X-Model-Api-Key'] = settings.MODEL_API_TOKEN

        try:
            response = requests.post(
                settings.MODEL_API_URL,
                json={
                    'message': user_message,
                    'history': history,
                    'consultant': conversation.consultant,
                    'adapters': conversation.get_selected_adapters(),
                },
                headers=headers,
                timeout=180,
            )

            if response.status_code == 200:
                response_data = response.json()
                ai_response = clean_ai_response(response_data.get('response', ''))

                if not ai_response:
                    return JsonResponse({'error': 'Модель вернула пустой ответ', 'status': 'error'}, status=500)

                Message.objects.create(conversation=conversation, role='assistant', content=ai_response)

                total_tokens = response_data.get('total_tokens')
                if not isinstance(total_tokens, int) or total_tokens <= 0:
                    total_tokens = estimate_tokens_fallback(user_message, ai_response)

                profile.tokens_used_today += total_tokens
                profile.save(update_fields=['tokens_used_today'])

                conversation.save()

                return JsonResponse({
                    'response': ai_response,
                    'conversation_id': conversation.id,
                    'conversation_title': conversation.title,
                    'consultant': conversation.consultant,
                    'selected_adapters': conversation.get_selected_adapters(),
                    'tokens_remaining': profile.tokens_remaining(),
                    'tokens_used': profile.tokens_used_today,
                    'token_usage': {
                        'total_tokens': total_tokens,
                        'prompt_tokens': response_data.get('prompt_tokens'),
                        'response_tokens': response_data.get('response_tokens'),
                    },
                    'status': 'success'
                })

            if response.status_code == 403:
                return JsonResponse(
                    {'error': 'Сервер модели отклонил запрос. Проверь MODEL_API_TOKEN.', 'status': 'error'},
                    status=502,
                )

            return JsonResponse(
                {'error': f'Ошибка сервера модели: {response.status_code}', 'status': 'error'},
                status=500,
            )

        except requests.exceptions.Timeout:
            return JsonResponse({'error': 'Превышено время ожидания ответа модели', 'status': 'error'}, status=504)
        except requests.exceptions.ConnectionError:
            return JsonResponse({'error': 'Не удалось подключиться к серверу модели', 'status': 'error'}, status=503)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Неверный формат данных', 'status': 'error'}, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e), 'status': 'error'}, status=500)


@login_required(login_url='/login/')
@require_POST
def send_message_stream(request):
    """
    Основной маршрут для отправки сообщений. Возвращает SSE-поток (text/event-stream).

    Формат событий:
      data: {"token": "..."}          — очередной токен ответа модели
      data: [ERROR] {"error": "..."}  — ошибка генерации или соединения
      data: [DONE] {...метаданные...} — конец потока; содержит conversation_id,
                                        tokens_remaining, token_usage и флаг truncated

    После получения [DONE] сохраняет ответ ассистента в БД и обновляет счётчик токенов.
    """
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')

        if not user_message:
            return JsonResponse({'error': 'Сообщение не может быть пустым', 'status': 'error'}, status=400)

        profile = request.user.profile
        profile.reset_tokens_if_needed()
        if not profile.can_send_message():
            return JsonResponse({
                'error': f'Достигнут дневной лимит ({profile.get_token_limit():,} токенов). '
                         f'Обновите план до Премиум или подождите следующего дня.',
                'status': 'limit_exceeded'
            }, status=429)

        selected_adapters = _resolve_selected_adapters(data)

        if conversation_id:
            try:
                conversation = Conversation.objects.get(id=conversation_id, user=request.user)
            except Conversation.DoesNotExist:
                conversation = Conversation(user=request.user, title='Новый чат')
        else:
            conversation = Conversation(user=request.user, title='Новый чат')

        conversation.set_selected_adapters(selected_adapters)
        if conversation.pk is None:
            conversation.save()

        messages_qs = conversation.messages.order_by('timestamp')
        history = [{'role': m.role, 'content': m.content} for m in messages_qs]
        is_first_message = len(history) == 0

        Message.objects.create(conversation=conversation, role='user', content=user_message)

        if is_first_message:
            conversation.title = user_message[:60] + ('...' if len(user_message) > 60 else '')

        if not settings.MODEL_API_URL:
            return JsonResponse({
                'error': 'MODEL_API_URL не настроен. Укажи адрес сервера модели в .env.',
                'status': 'error'
            }, status=503)

        # Строим URL стримингового эндпоинта из базового MODEL_API_URL
        stream_url = settings.MODEL_API_URL.replace('/generate', '/generate_stream')
        if stream_url == settings.MODEL_API_URL:
            stream_url = settings.MODEL_API_URL.rstrip('/') + '_stream'

        headers = {}
        if settings.MODEL_API_TOKEN:
            headers['X-Model-Api-Key'] = settings.MODEL_API_TOKEN

        # Копируем нужные данные диалога до входа в генератор,
        # чтобы не держать открытым ORM-объект внутри потока
        conv_id = conversation.id
        conv_title = conversation.title
        conv_consultant = conversation.consultant
        conv_adapters = conversation.get_selected_adapters()

        def stream_generator():
            """
            Генератор SSE-событий: проксирует поток от Flask, накапливает текст,
            по завершении сохраняет ответ в БД и отправляет итоговый [DONE].
            """
            full_text = ''
            try:
                with requests.post(
                    stream_url,
                    json={
                        'message': user_message,
                        'history': history,
                        'consultant': conv_consultant,
                        'adapters': conv_adapters,
                    },
                    headers=headers,
                    timeout=180,
                    stream=True,
                ) as flask_resp:
                    if flask_resp.status_code == 403:
                        yield f"data: [ERROR] {json.dumps({'error': 'Сервер модели отклонил запрос. Проверь MODEL_API_TOKEN.'})}\n\n"
                        return
                    if flask_resp.status_code != 200:
                        yield f"data: [ERROR] {json.dumps({'error': f'Ошибка сервера модели: {flask_resp.status_code}'})}\n\n"
                        return

                    for raw_line in flask_resp.iter_lines():
                        if not raw_line:
                            continue
                        line = raw_line.decode('utf-8') if isinstance(raw_line, bytes) else raw_line
                        if not line.startswith('data: '):
                            continue
                        payload = line[6:]

                        if payload.startswith('[ERROR]'):
                            yield f"data: {payload}\n\n"
                            return

                        if payload.startswith('[DONE]'):
                            try:
                                meta = json.loads(payload[7:])
                            except Exception:
                                meta = {}

                            # Сохраняем ответ ассистента и обновляем счётчик токенов
                            ai_response = clean_ai_response(full_text)
                            if ai_response:
                                Message.objects.create(
                                    conversation=conversation,
                                    role='assistant',
                                    content=ai_response,
                                )

                            total_tokens = meta.get('total_tokens', 0)
                            if not isinstance(total_tokens, int) or total_tokens <= 0:
                                total_tokens = estimate_tokens_fallback(user_message, ai_response)

                            profile.tokens_used_today += total_tokens
                            profile.save(update_fields=['tokens_used_today'])
                            conversation.save()

                            final = {
                                'conversation_id': conv_id,
                                'conversation_title': conv_title,
                                'consultant': conv_consultant,
                                'selected_adapters': conv_adapters,
                                'tokens_remaining': profile.tokens_remaining(),
                                'tokens_used': profile.tokens_used_today,
                                'token_usage': {
                                    'total_tokens': total_tokens,
                                    'prompt_tokens': meta.get('prompt_tokens'),
                                    'response_tokens': meta.get('response_tokens'),
                                },
                                'truncated': meta.get('truncated', False),
                                'status': 'success',
                            }
                            yield f"data: [DONE] {json.dumps(final, ensure_ascii=False)}\n\n"
                            return

                        # Передаём токен клиенту и накапливаем полный текст
                        try:
                            token_data = json.loads(payload)
                            token = token_data.get('token', '')
                            if token:
                                full_text += token
                                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
                        except json.JSONDecodeError:
                            pass

            except requests.exceptions.Timeout:
                yield f"data: [ERROR] {json.dumps({'error': 'Превышено время ожидания ответа модели'})}\n\n"
            except requests.exceptions.ConnectionError:
                yield f"data: [ERROR] {json.dumps({'error': 'Не удалось подключиться к серверу модели'})}\n\n"
            except Exception as e:
                import traceback
                traceback.print_exc()
                yield f"data: [ERROR] {json.dumps({'error': str(e)})}\n\n"

        response = StreamingHttpResponse(stream_generator(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Неверный формат данных', 'status': 'error'}, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e), 'status': 'error'}, status=500)
