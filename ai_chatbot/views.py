"""
ShopAI — ARIA Chatbot Views
"""
import json
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from .models import ChatSession, ChatMessage
from .aria_engine import process_message
from .intent_classifier import train_classifier
from django.contrib.auth.decorators import login_required

@login_required
def _get_or_create_session(request):
    """Get or create a chat session for current user/visitor."""
    if request.user.is_authenticated:
        session, _ = ChatSession.objects.get_or_create(
            user=request.user,
            is_active=True,
            defaults={'session_key': request.session.session_key or ''}
        )
    else:
        if not request.session.session_key:
            request.session.create()
        session, _ = ChatSession.objects.get_or_create(
            session_key=request.session.session_key,
            user=None,
            is_active=True,
        )
    return session


@require_POST
def send_message(request):
    """
    Main chat endpoint — receives user message, returns ARIA reply.
    POST /ai/chat/message/
    Body: { "message": "...", "session_id": "..." (optional) }
    """
    try:
        data    = json.loads(request.body)
        message = data.get('message', '').strip()
        if not message:
            return JsonResponse({'success': False, 'error': 'Empty message.'}, status=400)
        if len(message) > 1000:
            return JsonResponse({'success': False, 'error': 'Message too long.'}, status=400)

        session = _get_or_create_session(request)

        # Load conversation history (last 10 messages)
        history = list(session.messages.order_by('-created_at')[:10])[::-1]
        conv_history = [{'role': m.role, 'content': m.content} for m in history]

        # Save user message
        ChatMessage.objects.create(
            session=session, role='user', content=message
        )

        # Process with ARIA
        reply, meta, intent, confidence = process_message(
            request.user, message, conv_history
        )

        # Save assistant reply
        ChatMessage.objects.create(
            session    = session,
            role       = 'assistant',
            content    = reply,
            intent     = intent,
            confidence = confidence,
            metadata   = meta,
        )

        # Update session timestamp
        session.save()

        return JsonResponse({
            'success':    True,
            'reply':      reply,
            'intent':     intent,
            'confidence': round(confidence, 3),
            'session_id': str(session.id),
            'metadata':   meta,
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'reply':   "Oops! Something went wrong. Please try again ",
            'error':   str(e)
        }, status=500)


@require_GET
def get_history(request):
    """Return chat history for current session."""
    session = _get_or_create_session(request)
    messages = session.messages.order_by('created_at').values(
        'role', 'content', 'intent', 'created_at'
    )
    return JsonResponse({
        'success':  True,
        'messages': [
            {
                'role':       m['role'],
                'content':    m['content'],
                'intent':     m['intent'],
                'created_at': m['created_at'].isoformat(),
            }
            for m in messages
        ],
        'session_id': str(session.id),
    })


@require_POST
def clear_history(request):
    """Clear current session chat history."""
    session = _get_or_create_session(request)
    session.messages.all().delete()
    return JsonResponse({'success': True, 'message': 'Chat cleared.'})


@require_POST
def request_handoff(request):
    """Mark session for human support handoff."""
    session = _get_or_create_session(request)
    session.handed_off = True
    session.save()
    ChatMessage.objects.create(
        session = session,
        role    = 'system',
        content = 'Handoff requested — connecting to human support...',
    )
    return JsonResponse({
        'success': True,
        'message': 'You will be connected to our support team shortly. Average wait: 2 minutes.',
    })

@login_required
def chat_page(request):
    """Full-page chat interface (optional standalone page)."""
    session  = _get_or_create_session(request)
    messages = session.messages.order_by('created_at')
    return render(request, 'ai_chatbot/chat_page.html', {
        'session': session, 'messages': messages,
    })
