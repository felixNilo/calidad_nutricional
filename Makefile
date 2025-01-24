# Nombre del entorno virtual
VENV_DIR = venv
PYTHON = python3
PIP = $(VENV_DIR)/bin/pip

# Ruta de systemctl para reiniciar servicios
SYSTEMCTL = sudo systemctl

# Servicios a reiniciar
GUNICORN_SERVICE = calidad_nutricional_gunicorn
CELERY_SERVICE = celery
REDIS_SERVICE = redis
NGINX_SERVICE = nginx

# Define las acciones del Makefile
.PHONY: all clean venv install restart-services

# 1. Limpiar el entorno virtual
clean:
	@echo "Comprobando si el entorno virtual existe..."
	@if [ -d "$(VENV_DIR)" ]; then \
		echo "Eliminando el entorno virtual..."; \
		rm -rf $(VENV_DIR); \
	else \
		echo "El entorno virtual no existe. Continuando..."; \
	fi

# 2. Crear un entorno virtual e instalar dependencias
venv: clean
	@echo "Creando el entorno virtual..."
	@$(PYTHON) -m venv $(VENV_DIR)
	@echo "Activando el entorno virtual..."
	@. $(VENV_DIR)/bin/activate && echo "Instalando dependencias..."
	@$(PIP) install --upgrade pip
	@$(PIP) install -r requirements.txt

# 3. Reiniciar los servicios necesarios
restart-services:
	@echo "Reiniciando servicios..."
	@$(SYSTEMCTL) daemon-reload
	@$(SYSTEMCTL) restart $(GUNICORN_SERVICE)
	@$(SYSTEMCTL) restart $(NGINX_SERVICE)
	@$(SYSTEMCTL) restart $(REDIS_SERVICE)
	@$(SYSTEMCTL) restart $(CELERY_SERVICE)
	
	@echo "Todos los servicios se han reiniciado correctamente."

# 4. Comando principal: Crear entorno virtual, instalar dependencias y reiniciar servicios
all: venv restart-services
	@echo "Proceso completado. Servidor listo."
