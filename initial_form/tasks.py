# tasks.py
from celery import shared_task
from django.core.mail import EmailMessage
import base64

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

