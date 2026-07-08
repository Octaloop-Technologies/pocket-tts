conda create --name pocket-tts python=3.10;

conda activate pocket-tts;

python -m pip install --upgrade pip

pip install -e .
pip install -e . --group dev
