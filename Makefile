build:
	git submodule init
	git submodule update
	python3 -m venv env
	env/bin/pip install -r ./requirements.txt
	env/bin/pip install -e ./fogl

run:
	env/bin/python -m oldpaint
