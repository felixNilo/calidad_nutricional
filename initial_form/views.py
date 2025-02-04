from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
import math
import json
import os
import csv
from api.espocrm_client import EspoAPI
from django.conf import settings
from datetime import datetime, time
from django.core.exceptions import ValidationError
from collections import Counter
from django.http import JsonResponse
from io import BytesIO
from django.http import JsonResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import base64
from django.views.decorators.csrf import csrf_exempt
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

from reportlab.lib import colors
import tempfile
from .tasks import send_email_task
from django.utils import timezone
from .models import UnmatchedSearch

client = EspoAPI(settings.ESPO_API_URL, settings.ESPO_API_KEY)

def get_id_comida(comida_name, porcion, comidas):
    default_comida = None
    for comida in comidas:
        if comida['name'] == comida_name:
            if comida['porcion'].lower() == porcion:
                result = comida
                break
            if default_comida is None:
                default_comida = comida
    
    found_comida = result if 'result' in locals() else default_comida
    return found_comida

def get_TMR_times_PA(gender, age, weight, physical_activity):
    # Convertir weight a float
    try:
        weight = float(weight)
    except ValueError:
        raise ValueError("El peso debe ser un número válido.")

    if gender not in ['male', 'female']:
        raise ValueError("El género debe ser 'male', 'female'")

    formula_TMR = {
        'male': [
            (0, 3, lambda w: 60.9 * w - 54),
            (3, 10, lambda w: 22.7 * w + 495),
            (10, 18, lambda w: 17.5 * w + 651),
            (18, 30, lambda w: 15.3 * w + 679),
            (30, 60, lambda w: 11.6 * w + 879),
            (60, float('inf'), lambda w: 13.5 * w + 487),
        ],
        'female': [
            (0, 3, lambda w: 61.0 * w - 51),
            (3, 10, lambda w: 22.5 * w + 499),
            (10, 18, lambda w: 12.2 * w + 746),
            (18, 30, lambda w: 14.7 * w + 496),
            (30, 60, lambda w: 8.7 * w + 829),
            (60, float('inf'), lambda w: 10.5 * w + 596),
        ],
    }
    
    # Factores de actividad física
    activity_factors = {
        'male': [1.2, 1.55, 1.78, 2.1],  # Sedentaria, Ligera, Activo, Muy activo
        'female': [1.2, 1.56, 1.64, 1.82],  # Sedentaria, Ligera, Activo, Muy activo
    }

    tmr = 0
    # Seleccionar la fórmula adecuada según el rango de edad
    for min_age, max_age, formula in formula_TMR[gender]:
        if min_age <= age < max_age:
            tmr = formula(weight)
            break
    if tmr == 0:
        # Si no se encuentra un rango válido, devolver un error
        raise ValueError("No se encontró un rango de edad válido para calcular el TMR.")
    
    # Validar el nivel de actividad física
    if not (0 <= physical_activity < len(activity_factors[gender])):
        raise ValueError("El nivel de actividad física debe estar entre 0 y 3.")

    # Multiplicar TMR por el factor de actividad física
    tmr_with_activity = tmr * activity_factors[gender][physical_activity]
    #print(tmr_with_activity)
    return tmr_with_activity
        
def set_basic_data(request):
    if request.method == 'POST':
        # Obtener los datos del formulario
        name = request.POST.get('name')
        birthdate = request.POST.get('birthdate')
        gender = request.POST.get('gender')
        physical_activity = request.POST.get("physical_activity", "").strip()
        weight = request.POST.get('weight')
        
        # Validar que physical_activity sea un número entero entre 0 y 3
        try:
            physical_activity = int(physical_activity)
            if physical_activity < 0 or physical_activity > 3:
                raise ValidationError("La actividad física debe estar entre 0 y 3.")
        except ValueError:
            return JsonResponse({"error": "El valor de actividad física no es válido."}, status=400)

        # Validar peso y convertirlo a un número flotante
        try:
            weight = weight.replace(',', '.')  # Reemplazar coma con punto
            weight = float(weight)
        except ValueError:
            return JsonResponse({'success': False, 'message': 'El peso debe ser un número válido.'}, status=400)
        
        # Validar los datos (opcional)
        if not name or not birthdate or not gender:
            return JsonResponse({'success': False, 'message': 'Todos los campos son obligatorios.'}, status=400)
        
        # Calcular la edad
        birthdate_obj = datetime.strptime(birthdate, '%Y-%m-%d')
        today = datetime.today()
        age = today.year - birthdate_obj.year - ((today.month, today.day) < (birthdate_obj.month, birthdate_obj.day))
        
        tmr_with_activity = get_TMR_times_PA(gender, age, weight, physical_activity)
        #print(tmr_with_activity)
        # Guardar en la sesión
        request.session['user_info'] = {
            'name': name,
            'birthdate': birthdate,
            'age': age,
            'gender': gender,
            'physical_activity': physical_activity,
            'weight': weight,
            'tmr_with_activity': tmr_with_activity,
        }
        
        print(request.session['user_info'])

        return redirect('did_eat_breakfast') 
        #return redirect('set_breakfast') 
    else:
        return render(request, 'set_basic_data.html')  # Asegúrate de que el template esté en el lugar correcto.

def set_params_comidas(offset, tipo):
    params = {
                "select": "id,name,tipo,porcion",
                "offset": str(offset),
                "where": [
                    {
                        "type": "equals",
                        "attribute": "deleted",
                        "value": '0',
                    },
                    {
                        "type": "arrayAnyOf",
                        "attribute": "tipo",
                        "value": [tipo],
                    },
                ],
            }
    return params

def load_comidas_from_api(request):
    if request.method == "GET":
        try:
            # Verificar si los datos ya están cargados
            # if "data_breakfast" in request.session and "data_lunch" in request.session and "data_dinner" in request.session:
            #     return JsonResponse({'success': True}, status=200)

            # Cargar datos desde la API
            request.session["data_breakfast"] = client.request(
                'GET', 'comida', params=set_params_comidas(offset=0, tipo='Desayuno')
            )
            for i in range(1, math.ceil(request.session["data_breakfast"]["total"] / 500)):
                request.session["data_breakfast"]["list"] += client.request(
                    'GET', 'comida', params=set_params_comidas(offset=i * 500, tipo='Desayuno')
                )['list']

            request.session["data_lunch"] = client.request(
                'GET', 'comida', params=set_params_comidas(offset=0, tipo='Almuerzo')
            )
            for i in range(1, math.ceil(request.session["data_lunch"]["total"] / 500)):
                request.session["data_lunch"]["list"] += client.request(
                    'GET', 'comida', params=set_params_comidas(offset=i * 500, tipo='Almuerzo')
                )['list']

            request.session["data_dinner"] = client.request(
                'GET', 'comida', params=set_params_comidas(offset=0, tipo='Cena')
            )
            for i in range(1, math.ceil(request.session["data_dinner"]["total"] / 500)):
                request.session["data_dinner"]["list"] += client.request(
                    'GET', 'comida', params=set_params_comidas(offset=i * 500, tipo='Cena')
                )['list']
            
            # Ruta del archivo alimentos_encontrados.csv
            ruta_encontrados = os.path.join(settings.BASE_DIR, 'static/data/alimentos_encontrados.csv')
            # Ruta del archivo con porciones y equivalencias
            ruta_porciones = os.path.join(settings.BASE_DIR, 'static/data/consolidado_alimentos.csv')
            
            alimentos_data = []

            # Leer los alimentos encontrados
            alimentos_encontrados = []
            with open(ruta_encontrados, mode='r', encoding='utf-8') as file:
                reader = csv.reader(file)
                next(reader, None)  # Saltar encabezado
                for row in reader:
                    if row:  # Asegurar que la fila no esté vacía
                        alimentos_encontrados.append(row[0].strip())

            # Leer el archivo de porciones y equivalencias
            with open(ruta_porciones, mode='r', encoding='utf-8') as file:
                reader = csv.reader(file)
                for row in reader:
                    if row and row[0] in alimentos_encontrados:  # Solo procesar alimentos encontrados
                        alimento = row[0].strip()
                        porcion = row[1].strip()
                         # Construir las porciones como lista de diccionarios
                        porciones = json.dumps([
                            {
                                'medida': f"{row[2].strip()} {porcion}",
                                'equivalencia': float(row[3].strip())
                            },
                            {
                                'medida': f"{row[4].strip()} {porcion}",
                                'equivalencia': float(row[5].strip())
                            },
                            {
                                'medida': f"{row[6].strip()} {porcion}",
                                'equivalencia': float(row[7].strip())
                            }
                        ])

                        # Construir el diccionario para el alimento
                        alimento_data = {
                            'type': 'alimento',
                            'name': alimento,
                            'porciones': porciones
                        }   
                        alimentos_data.append(alimento_data)

            # Almacenar en la sesión
            request.session['alimentos'] = alimentos_data
            
            request.session.modified = True  
            
            return JsonResponse({'success': True}, status=200)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)

def group_comidas_by_name(comidas):
    """
    Agrupa las comidas por nombre, manteniendo las porciones y sus IDs en un diccionario.
    """
    grouped_comidas = {}
    for comida in comidas:
        name = comida['name'].lower()  # Normalizamos el nombre
        porcion = {'medida': comida['porcion'], 'id': comida['id']}
        
        if name not in grouped_comidas:
            # Si el nombre no está, creamos un nuevo registro
            grouped_comidas[name] = {
                'name': comida['name'],
                'porciones': [porcion]  # Lista de porciones
            }
        else:
            # Si ya existe, agregamos la porción
            grouped_comidas[name]['porciones'].append(porcion)
    
    return grouped_comidas.values()  # Retornamos como lista para facilitar la iteración en la plantilla

def set_breakfast(request):
    """
    Vista que agrupa las comidas del tipo 'Desayuno' por nombre y las pasa a la plantilla.
    """        
    
    # Obtén las comidas de la sesión
    comidas_breakfast = request.session.get("data_breakfast", {}).get("list", [])    
    
    # Filtrar las comidas con el tipo "Desayuno"
    desayuno_comidas = [
        comida for comida in comidas_breakfast if "Desayuno" in comida.get("tipo", [])
    ]
    
    # Agrupar las comidas por nombre
    grouped_comidas = group_comidas_by_name(desayuno_comidas)
    
    # Construir los datos con el tipo 'comida'
    comidas_con_tipo = [{"name": comida["name"], "type": "comida", "porciones": comida["porciones"]} for comida in grouped_comidas]
    
    comidas_con_tipo += request.session.get("alimentos", {})
    # print(comidas_con_tipo)
    if request.method == 'POST':
        # Obtener la hora del desayuno
        breakfast_time = request.POST.get('breakfast_time', None)
        
        # Obtener las comidas seleccionadas
        selected_comidas_json = request.POST.get('selected_comidas', '[]')
        try:
            selected_comidas = json.loads(selected_comidas_json)
        except json.JSONDecodeError:
            print(f"Error al decodificar JSON: {selected_comidas_json}")
            selected_comidas = []  # Inicializa como lista vacía si hay error
        
        try:
            updateComidaPortionAndID(request, selected_comidas, "data_breakfast")
        except:
            print("Error obteniendo la porcion y el Id de las comidas")
            
        
            
        # Guardar en la sesión junto con las comidas seleccionadas
        request.session['breakfast'] = {
            'time': breakfast_time,  # Guardar la cadena válida
            'selected_comidas': selected_comidas,
        }
        
        # Marcar la sesión como modificada
        request.session.modified = True
        
        # Debugging
        print("Comidas seleccionadas:", request.session['breakfast']['selected_comidas'])
        print("Hora:", request.session['breakfast']['time'])
        
        # Redirigir a la vista del almuerzo
        return redirect('did_eat_breakfast_additional')
    
    return render(request, "set_breakfast.html", {"comidas": comidas_con_tipo})

def set_lunch(request):
    """
    Vista que agrupa las comidas del tipo 'Almuerzo' por nombre y las pasa a la plantilla.
    """        
    
    # Obtén las comidas de la sesión
    comidas_lunch = request.session.get("data_lunch", {}).get("list", [])    
    
    # Filtrar las comidas con el tipo "Desayuno"
    almuerzo_comidas = [
        comida for comida in comidas_lunch if "Almuerzo" in comida.get("tipo", [])
    ]
    
    # Agrupar las comidas por nombre
    grouped_comidas = group_comidas_by_name(almuerzo_comidas)
    
    # Construir los datos con el tipo 'comida'
    comidas_con_tipo = [{"name": comida["name"], "type": "comida", "porciones": comida["porciones"]} for comida in grouped_comidas]
    
    comidas_con_tipo += request.session.get("alimentos", {})

    if request.method == 'POST':
        # Obtener la hora del almuerzo
        lunch_time = request.POST.get('lunch_time', None)
        
        # Obtener las comidas seleccionadas
        selected_comidas_json = request.POST.get('selected_comidas', '[]')
        try:
            selected_comidas = json.loads(selected_comidas_json)
        except json.JSONDecodeError:
            print(f"Error al decodificar JSON: {selected_comidas_json}")
            selected_comidas = []  # Inicializa como lista vacía si hay error
        
        try:
            updateComidaPortionAndID(request, selected_comidas, "data_lunch")
        except:
            print("Error obteniendo la porcion y el Id de las comidas")

        # Guardar en la sesión junto con las comidas seleccionadas
        request.session['lunch'] = {
            'time': lunch_time,  # Guardar la cadena válida
            'selected_comidas': selected_comidas,
        }
        
        # Marcar la sesión como modificada
        request.session.modified = True
        
        # Debugging
        print("Comidas seleccionadas:", request.session['lunch']['selected_comidas'])
        print("Hora:", request.session['lunch']['time'])
        
        # Redirigir a la vista del almuerzo
        return redirect('did_eat_lunch_additional')
    
    return render(request, "set_lunch.html", {"comidas": comidas_con_tipo})

def set_lunch_additional(request):
    """
    Vista que agrupa las comidas del tipo 'Almuerzo' por nombre y las pasa a la plantilla.
    """        
    
    # Obtén las comidas de la sesión
    comidas_lunch = request.session.get("data_lunch", {}).get("list", [])
    
    # Filtrar las comidas con el tipo "Desayuno"
    almuerzo_comidas = [
        comida for comida in comidas_lunch if "Almuerzo" in comida.get("tipo", [])
    ]
    
    # Agrupar las comidas por nombre
    grouped_comidas = group_comidas_by_name(almuerzo_comidas)
    
    
    # Construir los datos con el tipo 'comida'
    comidas_con_tipo = [{"name": comida["name"], "type": "comida", "porciones": comida["porciones"]} for comida in grouped_comidas]
    
    comidas_con_tipo += request.session.get("alimentos", {})
    
    if request.method == 'POST':

        # Obtener las comidas seleccionadas
        selected_comidas_json = request.POST.get('selected_comidas', '[]')
        try:
            selected_comidas = json.loads(selected_comidas_json)
        except json.JSONDecodeError:
            print(f"Error al decodificar JSON: {selected_comidas_json}")
            selected_comidas = []  # Inicializa como lista vacía si hay error
        
        try:
            updateComidaPortionAndID(request, selected_comidas, "data_lunch")
        except:
            print("Error obteniendo la porcion y el Id de las comidas")

        # Guardar en la sesión junto con las comidas seleccionadas
        request.session['data_lunch_additional'] = {
            'selected_comidas': selected_comidas,
        }
        
        # Marcar la sesión como modificada
        request.session.modified = True
        
        # Debugging
        print("Comidas seleccionadas:", request.session['data_lunch_additional']['selected_comidas'])
        
        # Redirigir a la vista de la cena
        return redirect('did_eat_dinner')
    
    return render(request, "set_lunch_additional.html", {"comidas": comidas_con_tipo})

def set_dinner(request):
    """
    Vista que agrupa las comidas del tipo 'Cena' por nombre y las pasa a la plantilla.
    """        
    
    # Obtén las comidas de la sesión
    comidas_dinner = request.session.get("data_dinner", {}).get("list", [])    
    
    # Filtrar las comidas con el tipo "Cena"
    dinner_comidas = [
        comida for comida in comidas_dinner if "Cena" in comida.get("tipo", [])
    ]
    
    # Agrupar las comidas por nombre
    grouped_comidas = group_comidas_by_name(dinner_comidas)
    
    # Construir los datos con el tipo 'comida'
    comidas_con_tipo = [{"name": comida["name"], "type": "comida", "porciones": comida["porciones"]} for comida in grouped_comidas]
    
    comidas_con_tipo += request.session.get("alimentos", {})

    if request.method == 'POST':
        # Obtener la hora de la cena
        dinner_time = request.POST.get('dinner_time', None)
        
        # Obtener las comidas seleccionadas
        selected_comidas_json = request.POST.get('selected_comidas', '[]')
        try:
            selected_comidas = json.loads(selected_comidas_json)
        except json.JSONDecodeError:
            print(f"Error al decodificar JSON: {selected_comidas_json}")
            selected_comidas = []  # Inicializa como lista vacía si hay error
        
        try:
            updateComidaPortionAndID(request, selected_comidas, "data_dinner")
        except:
            print("Error obteniendo la porcion y el Id de las comidas")

        # Guardar en la sesión junto con las comidas seleccionadas
        request.session['dinner'] = {
            'time': dinner_time,  # Guardar la cadena válida
            'selected_comidas': selected_comidas,
        }
        
        # Marcar la sesión como modificada
        request.session.modified = True
        
        # Debugging
        print("Comidas seleccionadas:", request.session['dinner']['selected_comidas'])
        print("Hora:", request.session['dinner']['time'])
        
        # Redirigir a la vista del almuerzo
        return redirect('did_eat_dinner_additional')
    
    return render(request, "set_dinner.html", {"comidas": comidas_con_tipo})

def set_dinner_additional(request):
    """
    Vista que agrupa las comidas del tipo 'Cena' por nombre y las pasa a la plantilla.
    """        
    
    # Obtén las comidas de la sesión
    comidas_dinner = request.session.get("data_dinner", {}).get("list", [])
    
    # Filtrar las comidas con el tipo "Desayuno"
    cena_comidas = [
        comida for comida in comidas_dinner if "Cena" in comida.get("tipo", [])
    ]
    
    # Agrupar las comidas por nombre
    grouped_comidas = group_comidas_by_name(cena_comidas)
    
    
    # Construir los datos con el tipo 'comida'
    comidas_con_tipo = [{"name": comida["name"], "type": "comida", "porciones": comida["porciones"]} for comida in grouped_comidas]
    
    comidas_con_tipo += request.session.get("alimentos", {})
    
    if request.method == 'POST':

        # Obtener las comidas seleccionadas
        selected_comidas_json = request.POST.get('selected_comidas', '[]')
        try:
            selected_comidas = json.loads(selected_comidas_json)
        except json.JSONDecodeError:
            print(f"Error al decodificar JSON: {selected_comidas_json}")
            selected_comidas = []  # Inicializa como lista vacía si hay error
        
        try:
            updateComidaPortionAndID(request, selected_comidas, "data_dinner")
        except:
            print("Error obteniendo la porcion y el Id de las comidas")

        # Guardar en la sesión junto con las comidas seleccionadas
        request.session['data_dinner_additional'] = {
            'selected_comidas': selected_comidas,
        }
        
        # Marcar la sesión como modificada
        request.session.modified = True
        
        # Debugging
        print("Comidas seleccionadas:", request.session['data_dinner_additional']['selected_comidas'])
        
        # Redirigir a la vista de la cena
        return redirect('dashboard')
    
    return render(request, "set_dinner_additional.html", {"comidas": comidas_con_tipo})

def dashboard(request):
    user_info = request.session.get('user_info', {})
    breakfast_data = request.session.get('breakfast', {}).get('selected_comidas', []) or []
    breakfast_additional_data = request.session.get('data_breakfast_additional', {}).get('selected_comidas', []) or []
    lunch_data = request.session.get('lunch', {}).get('selected_comidas', []) or []
    lunch_additional_data = request.session.get('data_lunch_additional', {}).get('selected_comidas', []) or []
    dinner_data = request.session.get('dinner', {}).get('selected_comidas', []) or []
    dinner_additional_data = request.session.get('data_dinner_additional', {}).get('selected_comidas', []) or []
    return render(request, "dashboard.html", {
        'user_info': user_info,
        'breakfast_data': breakfast_data,
        'breakfast_additional_data': breakfast_additional_data,
        'lunch_data': lunch_data,
        'lunch_additional_data':lunch_additional_data,
        'dinner_data': dinner_data,
        'dinner_additional_data': dinner_additional_data,
    })
    
def get_type_comidas_from_name(request,type,name):
    type_comida = {}
    
    # Definir todas las claves de comidas
    meal_keys = [ 'breakfast', 'data_breakfast_additional','lunch', 'data_lunch_additional', 'dinner', 'data_dinner_additional']
    
    for key in meal_keys:
        comidas = request.session.get(key, {}).get('selected_comidas', [])
        
        for comida in comidas:
            if comida.get('comidaType') == type and comida.get('name') == name:
                # Obtener la porción según el tipo
                if type == 'comida':
                    # Buscar la porción seleccionada en las opciones disponibles
                    selected_porcion = next(
                        (p['medida'] for p in comida.get('porciones', []) 
                         if p['id'] == comida.get('id')),
                        comida.get('porcion', '')
                    )
                    equivalencia = None
                else:
                    # Buscar la medida equivalente en alimentos
                    equivalencia = comida.get('equivalencia') 
                    selected_porcion = next(
                        (p['medida'] for p in comida.get('porciones', [])
                         if p.get('equivalencia') == equivalencia),
                        f"{equivalencia}g"  # Fallback por si no encuentra
                    )
                #type_comida[(f'{key}_equivalencia')] = equivalencia
                type_comida[key] = {'porcion': selected_porcion, 'equivalencia': equivalencia}
    
    #print(f"Porciones para {name} ({type}):", type_comida)
    return type_comida

def get_selected_comidas_and_alimentos(request):
    # Extraer las comidas seleccionadas desde la sesión
    selected_ids = []
    selected_alimentos = []

    # Procesar comidas con IDs
    for key in ['breakfast', 'data_breakfast_additional', 'lunch', 'data_lunch_additional', 'dinner', 'data_dinner_additional']:
        comidas = request.session.get(key, {}).get('selected_comidas', [])
        #print(comidas)
        selected_ids += [comida['id'] for comida in comidas if comida.get('comidaType') == 'comida' and 'id' in comida]
        selected_alimentos += [{"name": alimento['name'], "equivalencia": alimento['equivalencia']} for alimento in comidas if alimento.get('comidaType') == 'alimento']

    return selected_ids, selected_alimentos

def query_selected_comidas_details(request):
    if request.method != "GET":
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)

    try:
        selected_ids, selected_alimentos = get_selected_comidas_and_alimentos(request)
        #print('selected comidas: ', selected_ids, ' ', selected_alimentos)

        if not selected_ids and not selected_alimentos:
            return JsonResponse({'success': False, 'error': 'No hay comidas ni alimentos seleccionados'}, status=500)

        results = {}
        
        comidas_counter = Counter(selected_ids)
        alimentos_counter = Counter([alimento['name'] for alimento in selected_alimentos])

        # Consulta para comidas
        if selected_ids:
            params_comidas = {
                "select": "name,hdeC,lipidos,proteinas",
                "where": [
                    {
                        "type": "equals",
                        "attribute": "deleted",
                        "value": '0',
                    },
                    {
                        "type": "in",
                        "attribute": "id",
                        "value": selected_ids,
                    },
                ],
            }
            response_comidas = client.request('GET', 'comida', params=params_comidas)
            #Aqui tengo el id, y con el id puedo obtener el nombre.
            #pasar el nombre a una funcion que entregue una lista que contenga los tipos de comida en donde se encuentra el nombre.
            comidas_data = [
                {
                    "id": comida['id'],
                    "name": comida['name'],
                    "hdeC": comida['hdeC'],
                    "lipidos": comida['lipidos'],
                    "proteinas": comida['proteinas'],
                    "types_comida":get_type_comidas_from_name(request,'comida',comida['name']),
                    "count": comidas_counter[comida['id']],  # Agregar cantidad al resultado
                }
                for comida in response_comidas.get('list', [])
            ]
            results['comidas'] = {
                "total": len(comidas_data),
                "list": comidas_data
            }

        # Consulta para alimentos
        if selected_alimentos:
            selected_names = [alimento['name'] for alimento in selected_alimentos]
            params_alimentos = {
                "select": "name,hdeC,lipidos,protenas",
                "where": [
                    {
                        "type": "equals",
                        "attribute": "deleted",
                        "value": '0',
                    },
                    {
                        "type": "in",
                        "attribute": "name",
                        "value": selected_names,
                    },
                ],
            }
            response_alimentos = client.request('GET', 'ingrediente', params=params_alimentos)
            #Aqui tengo el nombre del alimento
            #pasar el nombre a una funcion que entregue una lista que contenga los tipos de comida en donde se encuentra el nombre
            # Combinar la información obtenida de la API con las equivalencias
            alimentos_data = []
            for alimento_api in response_alimentos.get('list', []):
                # Buscar el alimento correspondiente en `selected_alimentos`
                matching_alimento = next(
                    (alimento for alimento in selected_alimentos if alimento['name'] == alimento_api['name']),
                    None
                )
                alimentos_data.append({
                    "name": alimento_api['name'],
                    "hdeC": alimento_api['hdeC'],
                    "lipidos": alimento_api['lipidos'],
                    "proteinas": alimento_api['protenas'],
                    "equivalencia": matching_alimento['equivalencia'],
                    "types_comida":get_type_comidas_from_name(request,'alimento',alimento_api['name']),
                    "count": alimentos_counter[alimento_api['name']],
                })

            results['alimentos'] = {
                "total": len(alimentos_data),
                "list": alimentos_data
            }

        return JsonResponse({'success': True, 'data': results}, status=200)

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def set_breakfast_additional(request):
    """
    Vista que agrupa las comidas del tipo 'Desayuno' por nombre y las pasa a la plantilla.
    """        
    
    # Obtén las comidas de la sesión
    comidas_breakfast = request.session.get("data_breakfast", {}).get("list", [])
    
    # Filtrar las comidas con el tipo "Desayuno"
    desayuno_comidas = [
        comida for comida in comidas_breakfast if "Desayuno" in comida.get("tipo", [])
    ]
    
    # Agrupar las comidas por nombre
    grouped_comidas = group_comidas_by_name(desayuno_comidas)
    
    
    # Construir los datos con el tipo 'comida'
    comidas_con_tipo = [{"name": comida["name"], "type": "comida", "porciones": comida["porciones"]} for comida in grouped_comidas]
    
    comidas_con_tipo += request.session.get("alimentos", {})
    
    if request.method == 'POST':

        # Obtener las comidas seleccionadas
        selected_comidas_json = request.POST.get('selected_comidas', '[]')
        try:
            selected_comidas = json.loads(selected_comidas_json)
        except json.JSONDecodeError:
            print(f"Error al decodificar JSON: {selected_comidas_json}")
            selected_comidas = []  # Inicializa como lista vacía si hay error
        
        try:
            updateComidaPortionAndID(request, selected_comidas, "data_breakfast")
        except:
            print("Error obteniendo la porcion y el Id de las comidas")

        # Guardar en la sesión junto con las comidas seleccionadas
        request.session['data_breakfast_additional'] = {
            'selected_comidas': selected_comidas,
        }
        
        # Marcar la sesión como modificada
        request.session.modified = True
        
        # Debugging
        #print("Comidas seleccionadas:", request.session['data_breakfast_additional']['selected_comidas'])
        
        # Redirigir a la vista del almuerzo
        return redirect('set_lunch')
    
    return render(request, "set_breakfast_additional.html", {"comidas": comidas_con_tipo})

def updateComidaPortionAndID(request, selected_comidas, data):
    """
    Actualiza cada comida seleccionada con su ID, porción original y equivalencia (si es alimento).
    """
    for comida in selected_comidas:
        if comida['comidaType'] == 'comida':
            # Buscar el ID y la porción original para las comidas
            found_comida = get_id_comida(
                comida['name'],
                comida['porcion'],
                request.session[data]['list']
            )
            if found_comida:
                comida['id'] = found_comida['id']  # Agregar ID al objeto comida
                comida['original_porcion'] = found_comida.get('porcion', [])  # Agregar porción original

        elif comida['comidaType'] == 'alimento':
            # Buscar la equivalencia correspondiente a la porción seleccionada
            porciones = comida.get('porciones', [])
            porcion_key = comida.get('porcion')  # Por ejemplo: 'medida_2'
            
            # Obtener la equivalencia correspondiente a la porción seleccionada
            equivalencia = None
            for idx, porcion in enumerate(porciones):
                if f"medida_{idx + 1}" == porcion_key:  # Comparar con la porción seleccionada
                    equivalencia = porcion.get('equivalencia')
                    break
            
            # Agregar la equivalencia al objeto comida
            comida['equivalencia'] = equivalencia if equivalencia is not None else 0

    return True

@csrf_exempt
def send_report(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Método no permitido"}, status=405)

    try:
        email = request.POST.get("email")
        chart_image = request.POST.get("chart_image")
        total_kcal = request.POST.get("total_kcal")
        total_hdec = request.POST.get("total_hdec")
        total_grams_hdec = request.POST.get("total_grams_hdec")
        total_proteins = request.POST.get("total_proteins")
        total_grams_proteins = request.POST.get("total_grams_proteins")
        total_lipids = request.POST.get("total_lipids")
        total_grams_lipids = request.POST.get("total_grams_lipids")
        recommended_kcal = request.POST.get("recommended_kcal")
        recommended_hdec = request.POST.get("recommended_hdec")
        recommended_grams_hdec = request.POST.get("recommended_grams_hdec")
        recommended_proteins = request.POST.get("recommended_proteins")
        recommended_grams_proteins = request.POST.get("recommended_grams_proteins")
        recommended_lipids = request.POST.get("recommended_lipids")
        recommended_grams_lipids = request.POST.get("recommended_grams_lipids")
        
        # Leer las tablas dinámicas enviadas desde el frontend
        tables_json = request.POST.get("tables", "[]")
        try:
            tables = json.loads(tables_json)
        except json.JSONDecodeError:
            tables = []

        if not email or not chart_image:
            return JsonResponse({"success": False, "error": "Datos insuficientes."}, status=400)

        # Decodificar la imagen base64
        try:
            chart_data = base64.b64decode(chart_image.split(",")[1])
        except Exception as e:
            return JsonResponse({"success": False, "error": "Error al decodificar la imagen."}, status=400)

        if not chart_data:
            return JsonResponse({"success": False, "error": "La imagen está vacía o es inválida."}, status=400)

        # Guardar la imagen en un archivo temporal
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_image:
            temp_image.write(chart_data)
            temp_image_path = temp_image.name

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)
        page_width, page_height = letter
        
        LEFT_MARGIN = 50
        RIGHT_MARGIN = 50
        TOP_MARGIN = 750
        BOTTOM_MARGIN = 50
        FONT_SIZE_TITLE = 16
        FONT_SIZE_SUBTITLE = 12
        FONT_SIZE_TABLE_HEADER = 10
        FONT_SIZE_TABLE_BODY = 9
        ROW_HEIGHT = 16
        LINE_PADDING = 10
        TABLE_BOTTOM_PADDING = 10

        def get_table_style():
            return TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F81BD")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), FONT_SIZE_TABLE_HEADER),
                ("FONTSIZE", (0, 1), (-1, -1), FONT_SIZE_TABLE_BODY),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ])
        
        def new_page():
            pdf.showPage()
            pdf.setFont("Helvetica-Bold", FONT_SIZE_SUBTITLE)
            pdf.drawCentredString(page_width/2, TOP_MARGIN, "Reporte Nutricional (Continuación)")
            return TOP_MARGIN - 30

        current_y = TOP_MARGIN
        pdf.setFont("Helvetica-Bold", FONT_SIZE_TITLE)
        pdf.drawCentredString(page_width/2, current_y, "Reporte Nutricional")
        current_y -= 30
        
        img_width, img_height = 400, 200
        pdf.drawImage(temp_image_path, (page_width - img_width) / 2, current_y - img_height, width=img_width, height=img_height)
        current_y -= (img_height + 20)
        os.unlink(temp_image_path)

        pdf.setFont("Helvetica-Bold", FONT_SIZE_SUBTITLE)
        pdf.drawCentredString(page_width/2, current_y, "Resumen de Macronutrientes")
        current_y -= 20
        
        summary_data = [
            ["Macronutriente", "Calorías\nIngeridas", "Gramos\nIngeridos", "Calorías\nRecomendadas", "Gramos\nRecomendados"],
            ["Calorías", total_kcal, " ", recommended_kcal, " "],
            ["Hidratos de Carbono", total_hdec, total_grams_hdec, recommended_hdec, recommended_grams_hdec],
            ["Proteínas", total_proteins, total_grams_proteins, recommended_proteins, recommended_grams_proteins],
            ["Lípidos", total_lipids, total_grams_lipids, recommended_lipids, recommended_grams_lipids],
        ]
        
        col_widths = [120, 80, 80, 100, 100]
        summary_table = Table(summary_data, colWidths=col_widths)
        summary_table.setStyle(get_table_style())
        table_height = (len(summary_data) * ROW_HEIGHT) + TABLE_BOTTOM_PADDING
        
        if current_y - table_height < BOTTOM_MARGIN:
            current_y = new_page()
        
        summary_table.wrapOn(pdf, page_width, table_height)
        summary_table.drawOn(pdf, (page_width - sum(col_widths)) / 2, current_y - table_height)
        current_y -= (table_height + 20)
        
        for table_data in tables:
            pdf.setFont("Helvetica-Bold", FONT_SIZE_SUBTITLE)
            title_height = FONT_SIZE_SUBTITLE + 5
            if current_y - title_height < BOTTOM_MARGIN:
                current_y = new_page()
            pdf.drawCentredString(page_width/2, current_y, table_data["title"])
            current_y -= title_height + 10

            table_content = [["Comida", "Porción", "HDC (g)", "Proteínas (g)", "Lípidos (g)"]] + table_data["rows"]
            dynamic_table = Table(table_content, colWidths=[140, 70, 70, 70, 70])
            dynamic_table.setStyle(get_table_style())
            table_height = (len(table_content) * ROW_HEIGHT) + TABLE_BOTTOM_PADDING
            
            if current_y - table_height < BOTTOM_MARGIN:
                current_y = new_page()
            
            dynamic_table.wrapOn(pdf, page_width, table_height)
            dynamic_table.drawOn(pdf, (page_width - sum([140, 70, 70, 70, 70])) / 2, current_y - table_height)
            current_y -= (table_height + 20)
        
        pdf.save()
        buffer.seek(0)
        pdf_content = buffer.getvalue()
        buffer.close()

        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        
        send_email_task.delay(
            subject="Reporte Nutricional",
            body="Adjunto encontrarás el reporte nutricional en formato PDF.",
            recipient_list=[email],
            pdf_content=pdf_base64
        )

        return JsonResponse({"success": True, "message": "Reporte enviado con éxito."}, status=200)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

def did_eat_breakfast(request):
    """
    Vista que pregunta si el usuario consumió algo en el desayuno.
    """
    if request.method == 'POST':
        did_eat = request.POST.get('did_eat')

        # Validar respuesta
        if did_eat == 'yes':
            # Redirigir a la vista del desayuno
            return redirect('set_breakfast')
        elif did_eat == 'no':
            # Redirigir a la siguiente pregunta (desayuno adicional en este caso)
            return redirect('did_eat_breakfast_additional')
        else:
            return JsonResponse({'success': False, 'message': 'Respuesta inválida.'}, status=400)

    return render(request, 'did_eat_breakfast.html')

def did_eat_breakfast_additional(request):
    """
    Vista que pregunta si el usuario consumió algo entre el desayuno y el almuerzo
    """
    if request.method == 'POST':
        did_eat = request.POST.get('did_eat')

        # Validar respuesta
        if did_eat == 'yes':
            # Redirigir a la vista
            return redirect('set_breakfast_additional')
        elif did_eat == 'no':
            # Redirigir a la siguiente pregunta o comida (almuerzo en este caso)
            return redirect('did_eat_lunch')
        else:
            return JsonResponse({'success': False, 'message': 'Respuesta inválida.'}, status=400)

    return render(request, 'did_eat_breakfast_additional.html')

def did_eat_lunch(request):
    """
    Vista que pregunta si el usuario consumió algo en el almuerzo
    """
    if request.method == 'POST':
        did_eat = request.POST.get('did_eat')

        # Validar respuesta
        if did_eat == 'yes':
            # Redirigir a la vista del almuerzo
            return redirect('set_lunch')
        elif did_eat == 'no':
            # Redirigir a la siguiente pregunta o comida (almuerzo adicional en este caso)
            return redirect('did_eat_lunch_additional')
        else:
            return JsonResponse({'success': False, 'message': 'Respuesta inválida.'}, status=400)

    return render(request, 'did_eat_lunch.html')

def did_eat_lunch_additional(request):
    """
    Vista que pregunta si el usuario consumió algo entre el almuerzo y la cena
    """
    if request.method == 'POST':
        did_eat = request.POST.get('did_eat')

        # Validar respuesta
        if did_eat == 'yes':
            # Redirigir a la vista del almuerzo
            return redirect('set_lunch_additional')
        elif did_eat == 'no':
            # Redirigir a la siguiente pregunta o comida (cena en este caso)
            return redirect('did_eat_dinner')
        else:
            return JsonResponse({'success': False, 'message': 'Respuesta inválida.'}, status=400)

    return render(request, 'did_eat_lunch_additional.html')

def did_eat_dinner(request):
    """
    Vista que pregunta si el usuario consumió algo en la cena
    """
    if request.method == 'POST':
        did_eat = request.POST.get('did_eat')

        # Validar respuesta
        if did_eat == 'yes':
            # Redirigir a la vista de la cena
            return redirect('set_dinner')
        elif did_eat == 'no':
            # Redirigir a la siguiente pregunta o comida (cena adicional en este caso)
            return redirect('did_eat_dinner_additional')
        else:
            return JsonResponse({'success': False, 'message': 'Respuesta inválida.'}, status=400)

    return render(request, 'did_eat_dinner.html')

def did_eat_dinner_additional(request):
    """
    Vista que pregunta si el usuario consumió algo despues de la cena
    """
    if request.method == 'POST':
        did_eat = request.POST.get('did_eat')

        # Validar respuesta
        if did_eat == 'yes':
            # Redirigir a la vista
            return redirect('set_dinner_additional')
        elif did_eat == 'no':
            # Redirigir al dashboard
            return redirect('dashboard')
        else:
            return JsonResponse({'success': False, 'message': 'Respuesta inválida.'}, status=400)

    return render(request, 'did_eat_dinner_additional.html')

@csrf_exempt
def guardar_busqueda_sin_coincidencia(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            term = data.get("term")
            hasPriority1 = data.get("hasPriority1")
            hasPriority2 = data.get("hasPriority2")
            
            if (not hasPriority1 and not hasPriority2):
                hasResults = False
            else:
                hasResults = True
                
            if term:
                # Verificar si el término ya existe en la base de datos
                if not UnmatchedSearch.objects.filter(term=term).exists():
                    # Guardar el término en la base de datos
                    UnmatchedSearch.objects.create(term=term, has_results=hasResults, created_at=timezone.now())
                    return JsonResponse({"status": "success"})
                else:
                    return JsonResponse({"status": "exists"})  # Término ya existe
            else:
                return JsonResponse({"status": "error", "message": "Término no proporcionado"}, status=400)
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)
    return JsonResponse({"status": "error", "message": "Método no permitido"}, status=405)