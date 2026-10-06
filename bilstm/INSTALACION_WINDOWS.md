# Preparar el entorno BiLSTM en Windows

Esta guía instala las dependencias del modelo BiLSTM en Windows 10/11, dentro de un entorno virtual propio de `bilstm`. Los comandos están escritos para **PowerShell**.

## Requisitos

- Windows 10 u 11 de 64 bits.
- GPU NVIDIA compatible con CUDA 13.0 y controlador NVIDIA 580 o posterior.
- Python 3.14.4 de 64 bits para coincidir con el entorno BiLSTM actual de Linux. El índice oficial de PyTorch publica ruedas CUDA 12.6 para Windows y Python 3.14.
- El repositorio ScanTrue descargado en el equipo.

## 1. Comprobar Python y la GPU

Abre PowerShell y comprueba Python:

```powershell
py -3.14 --version
```

Si no está instalado, instala Python 3.14.4 de 64 bits desde [python.org](https://www.python.org/downloads/windows/). Durante la instalación, selecciona **Add Python to PATH**.

Comprueba que Windows detecta la GPU y el controlador NVIDIA:

```powershell
nvidia-smi
```

Debe aparecer el modelo de la tarjeta. Si el comando no se reconoce o no detecta la tarjeta, instala/actualiza el controlador NVIDIA para tu GPU y reinicia Windows antes de continuar.

## 2. Crear y activar el entorno virtual

En PowerShell, cambia a la carpeta donde clonaste el repositorio. Por ejemplo:

```powershell
cd C:\ruta\a\ScanTrue
```

Crea el entorno dentro de `bilstm` y actívalo:

```powershell
py -3.14 -m venv bilstm\.venv
.\bilstm\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Al activarse, PowerShell mostrará `(.venv)` al inicio de la línea. Si PowerShell bloquea el script de activación, permite scripts solo para esta sesión y vuelve a activarlo:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\bilstm\.venv\Scripts\Activate.ps1
```

## 3. Instalar PyTorch con CUDA 13.0

La configuración objetivo es **PyTorch 2.14.1 con CUDA 13.0**. Con `(.venv)` activo, ejecuta:

```powershell
python -m pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cu130
```

El índice oficial publica la rueda `torch 2.14.1+cu130` para Windows x64 y Python 3.14. No instales una rueda CPU. Para la distribución precompilada no hace falta instalar el CUDA Toolkit por separado; sí se necesita un controlador NVIDIA compatible (CUDA 13.x requiere la rama 580 o posterior para compatibilidad menor).

En Ubuntu, el entorno actual usa PyTorch con CUDA 12.6. Para que ambos equipos usen CUDA 13.0, cambia también el build de PyTorch en Ubuntu. No es necesario desinstalar el CUDA Toolkit 12.5 del sistema si solo entrenas con las ruedas precompiladas de PyTorch. Si compilas extensiones CUDA con `nvcc`, entonces sí necesitas instalar y configurar el Toolkit 13.0.

## 4. Instalar las dependencias fijadas del proyecto

Manteniendo `(.venv)` activo, ejecuta:

```powershell
python -m pip install -r bilstm\requirements.txt
```

Las versiones directas coinciden con las registradas en el entorno BiLSTM de Linux. `torchvision` está instalado en ese entorno, pero no se necesita para clasificar texto con BiLSTM. PyTorch incluye las capas LSTM y las herramientas de carga de datos (`Dataset` y `DataLoader`).

## 5. Verificar que PyTorch usa la GPU

```powershell
python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA de PyTorch:', torch.version.cuda); print('GPU disponible:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'No detectada')"
```

`GPU disponible` debe mostrar `True` y la última línea debe mostrar el nombre de la tarjeta NVIDIA. También se puede revisar la actividad de la GPU con:

```powershell
nvidia-smi
```

Si PyTorch muestra `False`, confirma que `nvidia-smi` funciona, que activaste `bilstm\.venv` y que instalaste el comando CUDA generado por el selector oficial.

## 6. Activar el entorno en sesiones futuras

Cada vez que abras una nueva terminal de PowerShell:

```powershell
cd C:\ruta\a\ScanTrue
.\bilstm\.venv\Scripts\Activate.ps1
```

Para salir del entorno virtual:

```powershell
deactivate
```

## Referencias oficiales

- [Instalación local de PyTorch](https://pytorch.org/get-started/locally/)
- [Índice oficial de ruedas CUDA 13.0 para PyTorch](https://download.pytorch.org/whl/cu130/torch/)
- [Documentación de `torch.nn.LSTM`](https://docs.pytorch.org/docs/stable/generated/torch.nn.LSTM.html)
- [Documentación de `torch.utils.data`](https://docs.pytorch.org/docs/stable/data.html)
