# tasks.py
from celery import shared_task
from django.core.mail import EmailMessage
import base64
from django.utils import timezone
from .models import UnmatchedSearch

@shared_task
def send_email_task(subject, body, recipient_list, pdf_content=None):
    try:
        # Decodifica el contenido del PDF desde base64
        if pdf_content:
            pdf_content = base64.b64decode(pdf_content)

        email_message = EmailMessage(
            subject=subject,
            body=body,
            from_email='Calidad Nutricional <app@calidadnutricional.cl>',
            to=recipient_list,
        )
        if pdf_content:
            email_message.attach("reporte_nutricional.pdf", pdf_content, "application/pdf")
        email_message.send()
        return "Email enviado exitosamente."
    except Exception as e:
        return f"Error al enviar el correo: {str(e)}"

@shared_task
def notify_admin_unmatched_searches():
    try:
        # Obtener todas las búsquedas sin coincidencia del día
        today = timezone.now().date()
        unmatched_searches = UnmatchedSearch.objects.filter(created_at__date=today)

        if unmatched_searches.exists():
            # Crear el cuerpo del correo
            subject = "Resumen de búsquedas sin coincidencia"
            body = "Las siguientes búsquedas no tuvieron coincidencia hoy:\n\n"
            body += "\n".join([f"- {search.term} ({search.created_at})" for search in unmatched_searches])

            # Enviar el correo
            send_email_task.delay(
                subject=subject,
                body=body,
                recipient_list=["angelmeya1332@gmail.com"],  # Correo del administrador
            )

            return f"Notificación enviada con {unmatched_searches.count()} búsquedas sin coincidencia."
        else:
            return "No hay búsquedas sin coincidencia para notificar hoy."
    except Exception as e:
        return f"Error al notificar al administrador: {str(e)}"
