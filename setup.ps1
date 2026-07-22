Write-Output "Make Sure you have cuda 11.8 installed system wide or in your environment."

Write-Output "Creating Conda Environment with python 3.12"
conda create --name pocket-tts python=3.12;

Write-Output "Activating conda environment 'pocket-tts'"
conda activate pocket-tts;

Write-Output "Upgrading pip"
python -m pip install --upgrade pip

Write-Output "installing pytorch compatible with cuda 11.8"
pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu118

pip install -e .
pip install -e . --group dev
