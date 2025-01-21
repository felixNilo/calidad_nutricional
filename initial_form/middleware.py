from django.shortcuts import redirect, resolve_url
from django.http import JsonResponse

class FlowValidationMiddleware:
    """
    Middleware para validar el flujo de llenado de información en la sesión.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Nombres de las rutas (coherentes con urls.py)
        user_info_url = resolve_url('set_basic_data')  # Resolver URL a ruta real
        breakfast_url = resolve_url('set_breakfast')
        lunch_url = resolve_url('set_lunch')
        dinner_url = resolve_url('set_dinner')
        dashboard_url = resolve_url('dashboard')

        # Rutas actuales
        current_path = request.path

        # Excluir la vista inicial "set_basic_data" y AJAX para cargar datos
        if current_path == user_info_url or request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return None

        # Validar flujo
        if not request.session.get('user_info') and current_path != user_info_url:
            return self._handle_redirect(request, user_info_url)

        if not request.session.get('breakfast') and current_path == lunch_url:
            return self._handle_redirect(request, breakfast_url)

        if not request.session.get('lunch') and current_path == dinner_url:
            return self._handle_redirect(request, lunch_url)

        if current_path == dashboard_url and (
            not request.session.get('breakfast') or 
            not request.session.get('lunch') or 
            not request.session.get('dinner')
        ):
            return self._handle_redirect(request, user_info_url)

        return None

    def _handle_redirect(self, request, redirect_url):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            # Si es AJAX, devolver un JSON con la URL de redirección
            return JsonResponse({'redirect_url': redirect_url}, status=403)
        # Si no es AJAX, redirigir normalmente
        return redirect(redirect_url)
