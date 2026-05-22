"""Notification service — one entry point, multiple downstream channels.

The persistent store is :class:`monitoring.models.Notification`; that's
what the bell-icon UI reads. Additional channel adapters (email, Slack)
plug in here as well: if ``settings.NOTIFICATION_EMAIL_ENABLED`` is true
the same payload is also pushed via ``django.core.mail.send_mail`` to
the recipient's e-mail; Slack/webhook hooks can be added similarly.

Existing call sites such as ``orders.services._send_notification`` route
through :func:`notify` so the *whole* legacy print-stub path is replaced
without touching its 20+ call sites in business logic.
"""
from __future__ import annotations

import logging
from contextlib import suppress
from typing import Iterable

from django.conf import settings
from django.core.mail import send_mail

from .models import Notification

log = logging.getLogger(__name__)


def notify(
    recipient,
    *,
    title: str,
    body: str = '',
    level: str = Notification.Level.INFO,
    kind: str = Notification.Kind.SYSTEM,
    related_order=None,
    related_stage=None,
    related_equipment=None,
) -> Notification | None:
    """Persist a notification and broadcast on opt-in channels.

    Returns the saved row, or ``None`` when ``recipient`` is missing /
    unresolvable. Logs (never raises) on downstream channel errors —
    the row itself is the source of truth, side-channels are best
    effort.
    """
    if recipient is None:
        return None

    # Resolve UUID / pk-string callers without forcing every site to
    # fetch the User first.
    user = recipient
    if not hasattr(user, 'username'):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.filter(pk=user).first()
        except (ValueError, TypeError):
            user = None
        if user is None:
            log.debug('notify(): recipient %r could not be resolved', recipient)
            return None

    notification = Notification.objects.create(
        recipient=user,
        level=level,
        kind=kind,
        title=title,
        body=body,
        related_order=related_order,
        related_stage=related_stage,
        related_equipment=related_equipment,
    )

    if getattr(settings, 'NOTIFICATION_EMAIL_ENABLED', False) and user.email:
        with suppress(Exception):
            send_mail(
                subject=f'[LIMS] {title}',
                message=body or title,
                from_email=getattr(
                    settings, 'DEFAULT_FROM_EMAIL', 'lims@example.com',
                ),
                recipient_list=[user.email],
                fail_silently=True,
            )
    return notification


def notify_many(
    recipients: Iterable,
    **kwargs,
) -> list:
    """Convenience fan-out — same payload, many recipients."""
    return [n for n in (notify(r, **kwargs) for r in recipients) if n is not None]
