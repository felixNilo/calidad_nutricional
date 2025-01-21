from django.http import JsonResponse
from .espocrm_client import EspoAPI
from django.conf import settings
import csv
from django.http import HttpResponse
import os

client = EspoAPI(settings.ESPO_API_URL, settings.ESPO_API_KEY)

def test_connection(request):
    print('get comidas')
    try:
        # Get accounts with search params
        
        params = {
            "select": "id,name",
            "where": [
                {
                    "type": "equals",
                    "attribute": "deleted",
                    "value": '0',
                },
            ],
        }
        data = client.request('GET', 'Comida', params)

        return JsonResponse({'success': True, 'data': data}, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def test_data(request):
    ingredientes = read_csv()
    chunk_size = 150  # Tamaño máximo del fragmento para evitar URLs largas
    resultados = []  # Almacenar resultados de todas las peticiones

    try:
        # Dividir la lista de ingredientes en fragmentos
        for i in range(0, len(ingredientes), chunk_size):
            chunk_limit = i + chunk_size
            last_index = len(ingredientes)
            if chunk_limit >= last_index:
                chunk = ingredientes[i:last_index]  # Tomar un fragmento de la lista
            else:
                chunk = ingredientes[i:i + chunk_size]  # Tomar un fragmento de la lista
            # Construir los parámetros para la consulta
            params = {
                "select": "name",
                "where": [
                    {
                        "type": "equals",
                        "attribute": "deleted",
                        "value": '0',
                    },
                    {
                        "type": "in",
                        "attribute": "name",
                        "value": chunk,  # Usar solo este fragmento
                    },
                ],
            }
            
            # Realizar la petición a la API
            data = client.request('GET', 'ingrediente', params=params)
            resultados.extend(data['list'])  # Agregar los resultados al acumulador
        
        # Escribir los encontrados y no encontrados en archivos CSV
        guardar_en_csv(resultados, 'alimentos_encontrados.csv')
        guardar_no_encontrados(ingredientes, resultados, 'alimentos_no_encontrados.csv')

        # Devolver los resultados combinados como JSON
        return JsonResponse({'success': True, 'data': resultados}, status=200)
    except Exception as e:
        # Manejar errores de conexión o API
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def read_csv():
    # Ruta del archivo CSV
    ruta_csv = os.path.join(settings.BASE_DIR, 'static/data/alimentos.csv')
    
    # Lista para almacenar los elementos
    ingredientes = []
    errores = []
    
    try:
        # Leer el archivo manualmente
        with open(ruta_csv, mode='r', encoding='latin1') as file:
            for i, line in enumerate(file):
                try:
                    # Limpiar cada línea
                    cleaned_line = line.strip()  # Remueve espacios y saltos de línea
                    if cleaned_line:  # Ignorar líneas vacías
                        ingredientes.append(cleaned_line)
                except Exception as e:
                    errores.append(f"Línea {i + 1}: {str(e)}")
        
    except FileNotFoundError:
        return HttpResponse("El archivo CSV no se encontró.")
    except Exception as e:
        return HttpResponse(f"Error general al procesar el archivo CSV: {str(e)}")
    
    return ingredientes

def guardar_en_csv(resultados, filename):
    # Ruta del archivo CSV
    ruta_salida = os.path.join(settings.BASE_DIR, f'static/data/{filename}')
    # Escribir los resultados en el archivo CSV
    with open(ruta_salida, mode='w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file)
        # Escribir encabezados
        writer.writerow(['Nombre'])
        
        # Escribir datos
        for resultado in resultados:
            writer.writerow([resultado['name']])

def guardar_no_encontrados(ingredientes, resultados, filename):
    # Ruta del archivo CSV
    ruta_salida = os.path.join(settings.BASE_DIR, f'static/data/{filename}')
    
    # Extraer los nombres de los resultados encontrados
    nombres_encontrados = {res['name'] for res in resultados}
    # Escribir los ingredientes no encontrados en el archivo CSV
    with open(ruta_salida, mode='w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file)
        # Escribir encabezados
        writer.writerow(['Nombre'])
        
        # Verificar qué ingredientes no están en los resultados
        for ingrediente in ingredientes:
            if ingrediente.upper() not in {nombre.upper() for nombre in nombres_encontrados}:
                writer.writerow([ingrediente])


def create_alimentos_data(request):
    #funcion que crea csv de alimentos que si existen en la base de datos.
    #[{'id': '', 'name': 'alimentoX', 'porcion': 'Taza', 'medida_1': '1/4', 'medida_2': '1','medida_3': '2', 'equivalencia_1': 37.5,'equivalencia_2': 100.0,'equivalencia_3': 200.0},...]
       
    # Ruta del archivo alimentos_encontrados.csv
    ruta_encontrados = os.path.join(settings.BASE_DIR, 'static/data/alimentos_encontrados.csv')
    # Ruta del archivo con porciones y equivalencias
    ruta_porciones = os.path.join(settings.BASE_DIR, 'static/data/consolidado_alimentos.csv')
    
    alimentos_data = []

    try:
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
                    # Construir el diccionario para el alimento
                    alimento_data = {
                        'type': 'alimento',  # Deja este campo vacío si no tienes un ID
                        'name': alimento,
                        'porcion': porcion,
                        'medida_1': row[2].strip(),
                        'medida_2': row[4].strip(),
                        'medida_3': row[6].strip(),
                        'equivalencia_1': float(row[3].strip()),
                        'equivalencia_2': float(row[5].strip()),
                        'equivalencia_3': float(row[7].strip()),
                    }
                    alimentos_data.append(alimento_data)

        # Almacenar en la sesión
        request.session['alimentos'] = alimentos_data

        return JsonResponse({'success': True, 'data': alimentos_data}, status=200)

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)